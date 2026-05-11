import csv
import io
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.attendance_sync_manager import AttendanceSyncManager
from app.core.config import get_settings
from app.core.zk_client import DEVICE_TIMEZONE, ZKClient, decode_zk_time, encode_zk_time
from app.db.base import Base
from app.db.session import build_async_database_url
from app.models import (
    Attendance,
    AttendanceDaily,
    AttendanceRuleSetting,
    AttendanceSyncSetting,
    SystemUser,
    User,
)
from app.repositories.attendance import AttendanceRepository
from app.services.attendance import AttendanceService
from app.services.attendance_record import AttendanceRecordService


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
    formatted = AttendanceRecordService._format_datetime(datetime(2026, 4, 28, 23, 20, 16, tzinfo=UTC))

    assert formatted == "2026-04-29 07:20:16"


@pytest.mark.asyncio
async def test_attendance_sync_manager_initializes_settings_from_database(monkeypatch, db_session):
    setting = AttendanceSyncSetting(id=1, enabled=True, time="08:20")
    setting.device_ips = ["172.30.25.103"]
    db_session.add(setting)
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr("app.core.attendance_sync_manager.SessionLocal", session_factory)

    manager = AttendanceSyncManager()
    await manager.initialize()

    assert manager.get_settings()["enabled"] is True
    assert manager.get_settings()["time"] == "08:20"
    assert manager.get_settings()["device_ips"] == ["172.30.25.103"]


@pytest.mark.asyncio
async def test_attendance_sync_manager_persists_settings_to_database(monkeypatch, db_session):
    session_factory = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr("app.core.attendance_sync_manager.SessionLocal", session_factory)

    manager = AttendanceSyncManager()
    await manager.initialize()
    await manager.update_settings(enabled=True, time_value="09:15", device_ips=["192.168.1.201"])

    saved = await db_session.get(AttendanceSyncSetting, 1)

    assert saved is not None
    assert saved.enabled is True
    assert saved.time == "09:15"
    assert saved.device_ips == ["192.168.1.201"]


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

    service.repository.delete_records.assert_not_called()
    service.repository.replace_records.assert_not_called()


@pytest.mark.asyncio
async def test_attendance_daily_force_clears_existing_records_when_no_raw_attendance(db_session):
    db_session.add(
        User(
            uid=72,
            user_id="72",
            name="Force Clear",
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

    await service.ensure_monthly_records(db_session, "2026-04", user_id="72", force=True)

    service.repository.delete_records.assert_awaited_once()
    service.repository.replace_records.assert_not_called()


@pytest.mark.asyncio
async def test_attendance_daily_only_generates_users_with_raw_attendance(db_session):
    db_session.add_all(
        [
            User(
                uid=73,
                user_id="73",
                name="Has Attendance",
                privilege=0,
                password="",
                group_id="",
                card=0,
                status="active",
                sync_status="pending",
            ),
            User(
                uid=74,
                user_id="74",
                name="No Attendance",
                privilege=0,
                password="",
                group_id="",
                card=0,
                status="active",
                sync_status="pending",
            ),
        ]
    )
    db_session.add_all(
        [
            Attendance(
                id=21,
                user_id="73",
                uid=73,
                timestamp=datetime(2026, 4, 10, 9, 0, 0, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="7984",
            ),
            Attendance(
                id=22,
                user_id="73",
                uid=73,
                timestamp=datetime(2026, 4, 10, 18, 0, 0, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="8166",
            ),
        ]
    )
    await db_session.commit()

    service = AttendanceRecordService()
    service.workday_provider.get_workday_map = AsyncMock(return_value={datetime(2026, 4, 10).date(): True})
    captured = {}

    async def fake_replace_records(db, user_id, start_date, end_date, records):
        del db, start_date, end_date
        captured[user_id] = records

    service.repository.replace_records = fake_replace_records
    await service.ensure_monthly_records(db_session, "2026-04")

    assert list(captured.keys()) == ["73"]


@pytest.mark.asyncio
async def test_attendance_daily_current_month_generates_only_through_yesterday_before_plan_end(db_session):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 5, 12, 0, 0, tzinfo=tz)

    db_session.add(
        User(
            uid=76,
            user_id="76",
            name="Current Month",
            privilege=0,
            password="",
            group_id="",
            card=0,
            status="active",
            sync_status="pending",
        )
    )
    db_session.add(
        Attendance(
            id=25,
            user_id="76",
            uid=76,
            timestamp=datetime(2026, 5, 3, 9, 0, 0, tzinfo=DEVICE_TIMEZONE),
            status=15,
            punch=0,
            device_sn="7984",
        )
    )
    await db_session.commit()

    service = AttendanceRecordService()
    service.workday_provider.get_workday_map = AsyncMock(return_value={})
    captured = {}

    async def fake_replace_records(db, user_id, start_date, end_date, records):
        del db
        captured[user_id] = {
            "start_date": start_date,
            "end_date": end_date,
            "records": records,
        }

    service.repository.replace_records = fake_replace_records
    with patch("app.services.attendance_record.datetime", FrozenDateTime):
        await service.ensure_monthly_records(db_session, "2026-05", user_id="76")

    generated = captured["76"]["records"]
    assert captured["76"]["start_date"] == date(2026, 5, 1)
    assert captured["76"]["end_date"] == date(2026, 5, 4)
    assert len(generated) == 4
    assert max(item.attend_date for item in generated) == date(2026, 5, 4)


@pytest.mark.asyncio
async def test_attendance_daily_current_month_includes_today_after_plan_end(db_session):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 5, 19, 0, 0, tzinfo=tz)

    db_session.add(
        User(
            uid=77,
            user_id="77",
            name="After Plan End",
            privilege=0,
            password="",
            group_id="",
            card=0,
            status="active",
            sync_status="pending",
        )
    )
    db_session.add(
        Attendance(
            id=26,
            user_id="77",
            uid=77,
            timestamp=datetime(2026, 5, 3, 9, 0, 0, tzinfo=DEVICE_TIMEZONE),
            status=15,
            punch=0,
            device_sn="7984",
        )
    )
    await db_session.commit()

    service = AttendanceRecordService()
    service.workday_provider.get_workday_map = AsyncMock(return_value={})
    captured = {}

    async def fake_replace_records(db, user_id, start_date, end_date, records):
        del db
        captured[user_id] = {
            "start_date": start_date,
            "end_date": end_date,
            "records": records,
        }

    service.repository.replace_records = fake_replace_records
    with patch("app.services.attendance_record.datetime", FrozenDateTime):
        await service.ensure_monthly_records(db_session, "2026-05", user_id="77")

    generated = captured["77"]["records"]
    assert captured["77"]["start_date"] == date(2026, 5, 1)
    assert captured["77"]["end_date"] == date(2026, 5, 5)
    assert len(generated) == 5
    assert max(item.attend_date for item in generated) == date(2026, 5, 5)


@pytest.mark.asyncio
async def test_attendance_daily_list_current_month_queries_only_through_yesterday_before_plan_end(db_session):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 5, 12, 0, 0, tzinfo=tz)

    service = AttendanceRecordService()
    service.repository.list_records = AsyncMock(return_value=([], 0))

    with patch("app.services.attendance_record.datetime", FrozenDateTime):
        records, total = await service.list_daily_records(db_session, "2026-05", ensure=False)

    assert records == []
    assert total == 0
    service.repository.list_records.assert_awaited_once_with(
        db_session,
        date(2026, 5, 1),
        date(2026, 5, 4),
        None,
        None,
        1,
        20,
    )


@pytest.mark.asyncio
async def test_attendance_rule_settings_persist_to_database(db_session):
    service = AttendanceRecordService()

    updated = await service.update_rule_settings(db_session, "10:00", "18:00")
    saved = await db_session.get(AttendanceRuleSetting, 1)

    assert updated == {"plan_start": "10:00", "plan_end": "18:00"}
    assert saved is not None
    assert saved.plan_start == "10:00"
    assert saved.plan_end == "18:00"


@pytest.mark.asyncio
async def test_attendance_daily_uses_database_rule_settings(db_session):
    db_session.add(AttendanceRuleSetting(id=1, plan_start="10:00", plan_end="18:00"))
    db_session.add(
        User(
            uid=78,
            user_id="78",
            name="Custom Rule",
            privilege=0,
            password="",
            group_id="",
            card=0,
            status="active",
            sync_status="pending",
        )
    )
    db_session.add_all(
        [
            Attendance(
                id=27,
                user_id="78",
                uid=78,
                timestamp=datetime(2026, 4, 15, 9, 30, 0, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="7984",
            ),
            Attendance(
                id=28,
                user_id="78",
                uid=78,
                timestamp=datetime(2026, 4, 15, 18, 0, 0, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="8166",
            ),
        ]
    )
    await db_session.commit()

    service = AttendanceRecordService()
    service.workday_provider.get_workday_map = AsyncMock(return_value={datetime(2026, 4, 15).date(): True})
    captured = {}

    async def fake_replace_records(db, user_id, start_date, end_date, records):
        del db, start_date, end_date
        captured[user_id] = records

    service.repository.replace_records = fake_replace_records
    await service.ensure_monthly_records(db_session, "2026-04", user_id="78")

    daily = next(item for item in captured["78"] if item.attend_date == date(2026, 4, 15))
    assert daily.plan_start == "10:00"
    assert daily.late_minutes == 0
    assert daily.status == 1


@pytest.mark.asyncio
async def test_attendance_daily_skips_rebuild_when_existing_records_present(db_session):
    db_session.add(
        User(
            uid=75,
            user_id="75",
            name="Already Generated",
            privilege=0,
            password="",
            group_id="",
            card=0,
            status="active",
            sync_status="pending",
        )
    )
    db_session.add_all(
        [
            Attendance(
                id=23,
                user_id="75",
                uid=75,
                timestamp=datetime(2026, 4, 11, 9, 0, 0, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="7984",
            ),
            Attendance(
                id=24,
                user_id="75",
                uid=75,
                timestamp=datetime(2026, 4, 11, 18, 0, 0, tzinfo=DEVICE_TIMEZONE),
                status=15,
                punch=0,
                device_sn="8166",
            ),
        ]
    )
    await db_session.commit()

    service = AttendanceRecordService()
    service.workday_provider.get_workday_map = AsyncMock(return_value={datetime(2026, 4, 11).date(): True})
    service.repository.get_existing_user_ids = AsyncMock(return_value={"75"})
    service.repository.replace_records = AsyncMock()

    await service.ensure_monthly_records(db_session, "2026-04")

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
async def test_monthly_export_settings_default_to_all_fields_when_missing(db_session):
    db_session.add(SystemUser(username="operator", password_hash="x", role="admin", is_active=True))
    await db_session.commit()
    current_user = (await db_session.execute(select(SystemUser).where(SystemUser.username == "operator"))).scalar_one()

    service = AttendanceRecordService()
    settings = await service.get_monthly_export_settings(db_session, current_user)

    assert settings["fixed_fields"] == [{"key": "attend_date", "label": "日期"}]
    assert [item["key"] for item in settings["available_fields"]] == [
        "day_type",
        "user_id",
        "user_name",
        "plan_start",
        "plan_end",
        "actual_checkin",
        "actual_checkout",
        "late_minutes",
        "early_minutes",
        "work_minutes",
        "overtime_minutes",
        "status",
    ]
    assert settings["selected_fields"] == [item["key"] for item in settings["available_fields"]]


@pytest.mark.asyncio
async def test_monthly_export_saves_selected_fields_and_formats_times_without_dates(db_session):
    db_session.add(SystemUser(username="operator", password_hash="x", role="admin", is_active=True))
    await db_session.commit()
    current_user = (await db_session.execute(select(SystemUser).where(SystemUser.username == "operator"))).scalar_one()

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

    content = await service.export_monthly_csv(
        db_session,
        "2026-03",
        keyword="70",
        current_user=current_user,
        selected_fields=["user_id", "actual_checkin", "actual_checkout", "status"],
    )
    csv_rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    saved = await service.get_monthly_export_settings(db_session, current_user)

    assert csv_rows[0] == ["日期", "工号", "签到时间", "签退时间", "状态"]
    assert csv_rows[1][0] == "2026-03-14"
    assert csv_rows[1][2] == "08:07:34"
    assert csv_rows[1][3] == "18:58:40"
    assert saved["selected_fields"] == ["user_id", "actual_checkin", "actual_checkout", "status"]


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
            original_rule = await session.get(AttendanceRuleSetting, 1)
            original_rule_values = None
            if original_rule is not None:
                original_rule_values = (original_rule.plan_start, original_rule.plan_end)
                original_rule.plan_start = "10:00"
                original_rule.plan_end = "18:00"
            else:
                session.add(AttendanceRuleSetting(id=1, plan_start="10:00", plan_end="18:00"))

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
            if original_rule_values is not None:
                restored_rule = await session.get(AttendanceRuleSetting, 1)
                restored_rule.plan_start = original_rule_values[0]
                restored_rule.plan_end = original_rule_values[1]
            await session.commit()
    finally:
        await engine.dispose()
