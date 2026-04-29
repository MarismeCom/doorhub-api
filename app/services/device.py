import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device
from app.repositories.device import DeviceRepository
from app.core.zk_client import ZKClient
from app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceService:
    def __init__(self):
        self.repository = DeviceRepository()

    async def list_active(self, db: AsyncSession) -> list[Device]:
        return await self.repository.list_active(db)

    async def create_device(self, db: AsyncSession, data: DeviceCreate) -> Device:
        existing = await self.repository.get_by_ip(db, data.ip)
        if existing:
            raise ValueError(f"设备 IP {data.ip} 已存在")

        device = Device(
            name=data.name,
            ip=data.ip,
            port=data.port,
            serial_number=data.serial_number,
            location=data.location,
            is_active=data.is_active,
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device

    async def update_device(self, db: AsyncSession, device_id: int, data: DeviceUpdate) -> Device:
        device = await self.repository.get_by_id(db, device_id)
        if not device:
            raise ValueError("设备不存在")

        existing = await self.repository.get_by_ip(db, data.ip)
        if existing and existing.id != device_id:
            raise ValueError(f"设备 IP {data.ip} 已存在")

        device.name = data.name
        device.ip = data.ip
        device.port = data.port
        device.serial_number = data.serial_number
        device.location = data.location
        device.is_active = data.is_active
        await db.commit()
        await db.refresh(device)
        return device

    async def delete_device(self, db: AsyncSession, device_id: int) -> None:
        device = await self.repository.get_by_id(db, device_id)
        if not device:
            raise ValueError("设备不存在")

        device.is_active = False
        await db.commit()

    async def get_status(self, db: AsyncSession, ip: str) -> dict:
        client = ZKClient(ip)
        info = await asyncio.to_thread(client.get_device_info)
        device = await self.repository.get_by_ip(db, ip)
        if device:
            device.serial_number = info.get("serial_number")
        else:
            db.add(Device(name=f"设备-{ip}", ip=ip, serial_number=info.get("serial_number")))
        await db.commit()
        return info
