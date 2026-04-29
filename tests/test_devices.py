from unittest.mock import patch

import pytest

from app.services.device import DeviceService


@pytest.mark.asyncio
@patch("app.services.device.ZKClient.get_device_info")
async def test_get_device_status_creates_device_record(mock_get_device_info, db_session):
    mock_get_device_info.return_value = {
        "ip": "192.168.1.201",
        "port": 4370,
        "serial_number": "SN001",
        "firmware_version": "1.0",
    }

    svc = DeviceService()
    result = await svc.get_status(db_session, "192.168.1.201")
    devices = await svc.list_active(db_session)

    assert result["serial_number"] == "SN001"
    assert len(devices) == 1
    assert devices[0].ip == "192.168.1.201"
