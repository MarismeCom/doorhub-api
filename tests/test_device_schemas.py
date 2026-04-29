from datetime import UTC, datetime

from app.schemas.device import DoorLogResponse


def test_door_log_response_serializes_to_asia_shanghai():
    payload = DoorLogResponse(
        id=1,
        operator="Tester",
        device_ip="172.30.25.103",
        action="open",
        result="success",
        remark="ok",
        operated_at=datetime(2026, 4, 29, 6, 23, 5, 468632, tzinfo=UTC),
    )

    data = payload.model_dump()

    assert data["operated_at"] == "2026-04-29T14:23:05.468632+08:00"
