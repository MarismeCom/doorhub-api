from unittest.mock import patch

import pytest

from app.models import Device
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


@pytest.mark.asyncio
async def test_ensure_configured_devices_creates_missing_records(db_session):
    svc = DeviceService()
    original_ips = svc.settings.ZK_DEVICE_IPS
    original_port = svc.settings.ZK_DEVICE_PORT
    svc.settings.ZK_DEVICE_IPS = "172.30.25.103,172.30.25.104"
    svc.settings.ZK_DEVICE_PORT = 4370

    try:
        devices = await svc.ensure_configured_devices(db_session)
        active_devices = await svc.list_active(db_session)
    finally:
        svc.settings.ZK_DEVICE_IPS = original_ips
        svc.settings.ZK_DEVICE_PORT = original_port

    assert [device.ip for device in devices] == ["172.30.25.103", "172.30.25.104"]
    assert [device.ip for device in active_devices] == ["172.30.25.103", "172.30.25.104"]
    assert all(device.name.startswith("设备-") for device in active_devices)


@pytest.mark.asyncio
async def test_ensure_configured_devices_reactivates_existing_record(db_session):
    db_session.add(
        Device(
            name="旧设备",
            ip="172.30.25.103",
            port=4370,
            is_active=False,
        )
    )
    await db_session.commit()

    svc = DeviceService()
    original_ips = svc.settings.ZK_DEVICE_IPS
    svc.settings.ZK_DEVICE_IPS = "172.30.25.103"

    try:
        devices = await svc.ensure_configured_devices(db_session)
    finally:
        svc.settings.ZK_DEVICE_IPS = original_ips

    assert len(devices) == 1
    assert devices[0].ip == "172.30.25.103"
    assert devices[0].name == "旧设备"
    assert devices[0].is_active is True
