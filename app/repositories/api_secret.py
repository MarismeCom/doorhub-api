from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiSecret


class ApiSecretRepository:
    async def list_by_user(self, db: AsyncSession, system_user_id: int) -> list[ApiSecret]:
        result = await db.execute(
            select(ApiSecret)
            .where(ApiSecret.system_user_id == system_user_id)
            .order_by(ApiSecret.created_at.desc(), ApiSecret.id.desc())
        )
        return list(result.scalars().all())

    async def count_active_by_user(self, db: AsyncSession, system_user_id: int) -> int:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ApiSecret).where(
                ApiSecret.system_user_id == system_user_id,
                ApiSecret.revoked_at.is_(None),
                or_(ApiSecret.expires_at.is_(None), ApiSecret.expires_at > now),
            )
        )
        return len(list(result.scalars().all()))

    async def get_by_id_for_user(self, db: AsyncSession, secret_id: int, system_user_id: int) -> ApiSecret | None:
        result = await db.execute(
            select(ApiSecret).where(ApiSecret.id == secret_id, ApiSecret.system_user_id == system_user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_prefix(self, db: AsyncSession, prefix: str) -> list[ApiSecret]:
        result = await db.execute(
            select(ApiSecret).where(ApiSecret.secret_prefix == prefix)
        )
        return list(result.scalars().all())
