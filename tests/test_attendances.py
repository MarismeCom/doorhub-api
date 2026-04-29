from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.zk_client import DEVICE_TIMEZONE, ZKClient, decode_zk_time, encode_zk_time
from app.repositories.attendance import AttendanceRepository
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
