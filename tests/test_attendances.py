from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.zk_client import DEVICE_TIMEZONE, ZKClient, decode_zk_time, encode_zk_time
from app.db.base import Base
from app.db.session import build_async_database_url
from app.models import Attendance, AttendanceDaily, User
from app.repositories.attendance import AttendanceRepository
from app.services.attendance_record import AttendanceRecordService
from app.services.attendance import AttendanceService


def attendance_record(user_id: str, timestamp: datetime, status: int = 0, punch: int = 0, uid: int = 1):
    return SimpleNamespace(user_id=user_id, timestamp=timestamp, status=status, punch=punch, uid=uid)


def pack_record_40(uid: int, user_id: str, status: int, timestamp: datetime, punch: int) -> bytes:
    user_id_bytes = user_id.encode().ljust(24, b"\x00")[:24]
    return (
        uid.to_bytes(2, "little")
        + user_id_bytes
        + status.to_bytes(1, "little")
        + encode_zk_time(timestamp.replace(tzinfo=None))
        + punch.to_bytes(1, "little")
        + b"\x00" * 8
    )


def pack_record_49(uid: int, user_id: str, status: int, timestamp: datetime, punch: int, workcode: int = 0) -> bytes:
    return pack_record_40(uid, user_id, status, timestamp, punch) + workcode.to_bytes(4, "little") + b"\x00" * 5


def test_decode_zk_time_round_trip_with_xface600_encoding():
    expected = datetime(2026, 4, 28, 18, 3, 44)

    decoded = decode_zk_time(encode_zk_time(expected))

    assert decoded == expected


def test_decode_zk_time_decodes_known_xface600_raw_values():
    assert decode_zk_time(bytes.fromhex("0f16bf31")) == datetime(2025, 12, 19, 19, 10, 7)
    assert decode_zk_time(bytes.fromhex("3317bf31")) == datetime(2025, 12, 19, 19, 14, 59)
    assert decode_zk_time(bytes.fromhex("4d17bf31")) == datetime(2025, 12, 19, 19, 15, 25)


def test_decode_attendance_time_rejects_unreasonable_future_datetime():
    future = datetime.now(DEVICE_TIMEZONE) + timedelta(days=400)
    raw = encode_zk_time(future.replace(tzinfo=None))

    decoded = ZKClient._decode_attendance_time(raw)

    assert decoded is None


def test_decode_attendance_time_uses_xface600_time_logic():
    decoded = ZKClient._decode_attendance_time(bytes.fromhex("0f16bf31"))

    assert decoded == datetime(2025, 12, 19, 19, 10, 7, tzinfo=DEVICE_TIMEZONE)


def test_export_datetime_formats_use_device_local_timezone():
    formatted = AttendanceRecordService._format_datetime(datetime(2026, 4, 28, 23, 20, 16, tzinfo=timezone.utc))

    assert formatted == "2026-04-29 07:20:16"


@pytest.mark.asyncio
async def test_sync_attendances_normalizes_naive_timestamp_before_persist():
    db_session = MagicMock()
    db_session.add = MagicMock()
    db_session.commit = AsyncMock()
    db_session.rollback = AsyncMock()

    record = attendance_record("EMP001", datetime(2026, 4, 28, 18, 3, 44))

    svc = AttendanceService()
    svc.repository.exists_record = AsyncMock(return_value=False)

    with patch("app.services.attendance.ZKClient.get_attendance_safe", return_value=([record], 0)), patch(
        "app.services.attendance.ZKClient.get_serial_number", return_value="SN001"
    ):
        result = await svc.sync_from_device(db_session, "192.168.1.201", incremental=True)

    persisted = db_session.add.call_args.args[0]

    assert result.fetched_count == 1
    assert result.synced_count == 1
    assert result.duplicate_count == 0
    assert persisted.timestamp == datetime(2026, 4, 28, 18, 3, 44, tzinfo=DEVICE_TIMEZONE)


def test_return_empty_when_total_size_exceeds_payload():
    client = ZKClient("192.168.1.201")

    conn = MagicMock()
    conn.records = 1
    conn.get_users.return_value = []
    conn.read_with_buffer.return_value = ((999).to_bytes(4, "little") + b"\x00" * 16, 20)
    conn.read_sizes.return_value = True

    client.connect = MagicMock()
    client.connect.return_value.__enter__.return_value = conn
    client.connect.return_value.__exit__.return_value = False

    records, skipped = client.get_attendance_safe()

    assert records == []
    assert skipped == 0


def test_resolve_record_size_with_padding_prefers_49_byte_layout():
    client = ZKClient("192.168.1.201")
    total_size = 2 * 49 + 3

    record_size = client._resolve_record_size(b"\x00" * total_size, 2, total_size)

    assert record_size == 49


def test_infer_record_size_from_payload_when_record_count_matches_40_byte_layout():
    client = ZKClient("192.168.1.201")
    timestamp = datetime(2026, 4, 28, 8, 0, 0, tzinfo=DEVICE_TIMEZONE)
    payload = pack_record_40(1, "EMP001", 0, timestamp, 2) + pack_record_40(2, "EMP002", 0, timestamp, 0)

    conn = MagicMock()
    conn.records = 2
    conn.get_users.return_value = []
    conn.read_with_buffer.return_value = (len(payload).to_bytes(4, "little") + payload, len(payload) + 4)
    conn.read_sizes.return_value = True

    client.connect = MagicMock()
    client.connect.return_value.__enter__.return_value = conn
    client.connect.return_value.__exit__.return_value = False

    records, skipped = client.get_attendance_safe()

    assert len(records) == 2
    assert records[0].user_id == "EMP001"
    assert records[1].user_id == "EMP002"
    assert skipped == 0


def test_infer_record_size_49_from_payload_when_device_uses_extended_layout():
    client = ZKClient("192.168.1.201")
    timestamp = datetime(2026, 4, 28, 8, 0, 0, tzinfo=DEVICE_TIMEZONE)
    payload = pack_record_49(1, "EMP001", 15, timestamp, 0, 1001) + pack_record_49(2, "EMP002", 4, timestamp, 1, 1002)

    conn = MagicMock()
    conn.records = 2
    conn.get_users.return_value = []
    conn.read_with_buffer.return_value = (len(payload).to_bytes(4, "little") + payload, len(payload) + 4)
    conn.read_sizes.return_value = True

    client.connect = MagicMock()
    client.connect.return_value.__enter__.return_value = conn
    client.connect.return_value.__exit__.return_value = False

    records, skipped = client.get_attendance_safe()

    assert len(records) == 2
    assert records[0].user_id == "EMP001"
    assert records[1].user_id == "EMP002"
    assert skipped == 0


@pytest.mark.asyncio
async def test_exists_record_returns_true_when_duplicate_rows_already_exist():
    db_session = MagicMock()
    db_session.scalar = AsyncMock(return_value=True)

    repository = AttendanceRepository()

    exists_record = await repository.exists_record(
        db_session,
        user_id="EMP001",
        timestamp=datetime(2026, 4, 28, 8, 0, 0, tzinfo=DEVICE_TIMEZONE),
        device_sn="SN001",
    )

    assert exists_record is True


@pytest.mark.asyncio
async def test_attendance_daily_groups_first_and_last_punch_with_local_timezone_same_day(db_session):
    user = User(
        uid=68,
        user_id="68",
        name="徐永杰",
        privilege=0,
        password="",
        group_id="",
        card=0,
        status="active",
        sync_status="pending",
    )
    db_session.add(user)
    db_session.add_all(
        [
            Attendance(
                id=1,
                user_id="68",
                uid=68,
                timestamp=datetime(2026, 4, 29, 7, 20, 16, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="7984",
            ),
            Attendance(
                id=2,
                user_id="68",
                uid=68,
                timestamp=datetime(2026, 4, 29, 18, 53, 56, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="8166",
            ),
        ]
    )
    await db_session.commit()

    service = AttendanceRecordService()
    captured_records = {}
    service.workday_provider.get_workday_map = AsyncMock(return_value={datetime(2026, 4, 29).date(): True})

    async def fake_replace_records(db, user_id, start_date, end_date, records):
        del db, start_date, end_date
        captured_records[user_id] = records

    service.repository.replace_records = fake_replace_records
    await service.ensure_monthly_records(db_session, "2026-04", user_id="68")

    daily = next(item for item in captured_records["68"] if item.attend_date == datetime(2026, 4, 29).date())

    assert daily.actual_checkin == datetime(2026, 4, 29, 7, 20, 16, tzinfo=DEVICE_TIMEZONE)
    assert daily.actual_checkout == datetime(2026, 4, 29, 18, 53, 56, tzinfo=DEVICE_TIMEZONE)
    assert daily.work_minutes == 693
    assert daily.overtime_minutes == 53
    assert daily.status == 1


@pytest.mark.asyncio
async def test_attendance_daily_marks_weekend_records_as_overtime(db_session):
    user = User(
        uid=69,
        user_id="69",
        name="Weekend Test",
        privilege=0,
        password="",
        group_id="",
        card=0,
        status="active",
        sync_status="pending",
    )
    db_session.add(user)
    db_session.add_all(
        [
            Attendance(
                id=11,
                user_id="69",
                uid=69,
                timestamp=datetime(2026, 3, 14, 8, 7, 34, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="7984",
            ),
            Attendance(
                id=12,
                user_id="69",
                uid=69,
                timestamp=datetime(2026, 3, 14, 18, 58, 40, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="8166",
            ),
        ]
    )
    await db_session.commit()

    service = AttendanceRecordService()
    captured_records = {}
    service.workday_provider.get_workday_map = AsyncMock(return_value={datetime(2026, 3, 14).date(): False})

    async def fake_replace_records(db, user_id, start_date, end_date, records):
        del db, start_date, end_date
        captured_records[user_id] = records

    service.repository.replace_records = fake_replace_records
    await service.ensure_monthly_records(db_session, "2026-03", user_id="69")

    daily = next(item for item in captured_records["69"] if item.attend_date == datetime(2026, 3, 14).date())

    assert daily.actual_checkin == datetime(2026, 3, 14, 8, 7, 34, tzinfo=DEVICE_TIMEZONE)
    assert daily.actual_checkout == datetime(2026, 3, 14, 18, 58, 40, tzinfo=DEVICE_TIMEZONE)
    assert daily.work_minutes == 651
    assert daily.overtime_minutes == 651
    assert daily.status == 7


@pytest.mark.asyncio
async def test_attendance_daily_skips_month_generation_when_no_raw_attendance(db_session):
    db_session.add(
        User(
            uid=71,
            user_id="71",
            name="No Attendance",
            privilege=0,
            password="",
            group_id="",
            card=0,
            status="active",
            sync_status="pending",
        )
    )
    await db_session.commit()

    service = AttendanceRecordService()
    service.workday_provider.get_workday_map = AsyncMock(return_value={})
    service.repository.delete_records = AsyncMock()
    service.repository.replace_records = AsyncMock()

    await service.ensure_monthly_records(db_session, "2026-04", user_id="71")

    service.repository.delete_records.assert_awaited_once()
    service.repository.replace_records.assert_not_called()


@pytest.mark.asyncio
async def test_export_monthly_csv_includes_overtime_status_and_duration_for_weekend_records(db_session):
    service = AttendanceRecordService()
    service.ensure_monthly_records = AsyncMock()
    service.repository.list_all_records = AsyncMock(
        return_value=[
            {
                "attend_date": datetime(2026, 3, 14).date(),
                "user_id": "70",
                "user_name": "Export Weekend",
                "plan_start": "10:00",
                "plan_end": "18:00",
                "actual_checkin": datetime(2026, 3, 14, 8, 7, 34, tzinfo=DEVICE_TIMEZONE),
                "actual_checkout": datetime(2026, 3, 14, 18, 58, 40, tzinfo=DEVICE_TIMEZONE),
                "late_minutes": 0,
                "early_minutes": 0,
                "work_minutes": 651,
                "overtime_minutes": 651,
                "status": 7,
            }
        ]
    )
    service.holiday_repository.list_by_range = AsyncMock(return_value=[])

    content = await service.export_monthly_csv(db_session, "2026-03", keyword="70")
    csv_text = content.decode("utf-8-sig")

    assert "加班" in csv_text
    assert "651" in csv_text


@pytest.mark.asyncio
async def test_attendance_daily_groups_first_and_last_punch_with_local_timezone_same_day_postgres():
    settings = get_settings()
    if not settings.DATABASE_URL.startswith("postgresql://") and not settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
        pytest.skip("当前 DATABASE_URL 不是 PostgreSQL，跳过 PostgreSQL 集成测试")

    engine = create_async_engine(build_async_database_url(settings.DATABASE_URL), pool_pre_ping=True, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    test_uid = 900000 + int(uuid4().int % 100000)
    test_user_id = f"tz-test-{uuid4().hex[:8]}"

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(
                User(
                    uid=test_uid,
                    user_id=test_user_id,
                    name="TZ Test",
                    privilege=0,
                    password="",
                    group_id="",
                    card=0,
                    status="active",
                    sync_status="pending",
                )
            )
            session.add_all(
                [
                    Attendance(
                        user_id=test_user_id,
                        uid=test_uid,
                        timestamp=datetime(2026, 4, 29, 7, 20, 16, tzinfo=DEVICE_TIMEZONE),
                        status=15,
                        punch=0,
                        device_sn="7984",
                    ),
                    Attendance(
                        user_id=test_user_id,
                        uid=test_uid,
                        timestamp=datetime(2026, 4, 29, 18, 53, 56, tzinfo=DEVICE_TIMEZONE),
                        status=15,
                        punch=0,
                        device_sn="8166",
                    ),
                ]
            )
            await session.commit()

            service = AttendanceRecordService()
            await service.ensure_monthly_records(session, "2026-04", user_id=test_user_id)

            result = await session.execute(
                select(AttendanceDaily).where(
                    AttendanceDaily.user_id == test_user_id,
                    AttendanceDaily.attend_date == datetime(2026, 4, 29).date(),
                )
            )
            daily = result.scalar_one()

            assert daily.actual_checkin == datetime(2026, 4, 29, 7, 20, 16, tzinfo=DEVICE_TIMEZONE)
            assert daily.actual_checkout == datetime(2026, 4, 29, 18, 53, 56, tzinfo=DEVICE_TIMEZONE)
            assert daily.work_minutes == 693
            assert daily.overtime_minutes == 53
            assert daily.status == 1

            await session.execute(AttendanceDaily.__table__.delete().where(AttendanceDaily.user_id == test_user_id))
            await session.execute(Attendance.__table__.delete().where(Attendance.user_id == test_user_id))
            await session.execute(User.__table__.delete().where(User.user_id == test_user_id))
            await session.commit()
    finally:
        await engine.dispose()
