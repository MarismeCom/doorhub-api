from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device


class DeviceRepository:
    async def list_active(self, db: AsyncSession) -> list[Device]:
        result = await db.execute(select(Device).where(Device.is_active == True))
        return list(result.scalars().all())

    async def get_by_ip(self, db: AsyncSession, ip: str) -> Device | None:
        result = await db.execute(select(Device).where(Device.ip == ip))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, device_id: int) -> Device | None:
        result = await db.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()
