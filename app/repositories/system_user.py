from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemUser


class SystemUserRepository:
    async def get_by_username(self, db: AsyncSession, username: str) -> SystemUser | None:
        result = await db.execute(select(SystemUser).where(SystemUser.username == username))
        return result.scalar_one_or_none()

    async def list_all(self, db: AsyncSession) -> list[SystemUser]:
        result = await db.execute(select(SystemUser).order_by(SystemUser.id.asc()))
        return list(result.scalars().all())
