from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    SORTABLE_FIELDS = {
        "uid": User.uid,
        "name": User.name,
        "privilege": User.privilege,
        "password": User.password,
        "card": User.card,
        "status": User.status,
        "sync_status": User.sync_status,
    }

    async def get_active_by_user_id(self, db: AsyncSession, user_id: str) -> User | None:
        result = await db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, db: AsyncSession, user_id: str) -> User | None:
        result = await db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_uid_owner(self, db: AsyncSession, uid: int) -> User | None:
        result = await db.execute(select(User).where(User.uid == uid))
        return result.scalar_one_or_none()

    async def get_max_uid(self, db: AsyncSession) -> int:
        result = await db.execute(select(func.max(User.uid)))
        return result.scalar() or 0

    async def list_active(
        self,
        db: AsyncSession,
        page: int,
        page_size: int,
        keyword: str | None = None,
        sort_field: str | None = None,
        sort_order: str = "desc",
    ) -> tuple[list[User], int]:
        conditions = []
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            conditions.append(or_(User.user_id.ilike(like_keyword), User.name.ilike(like_keyword)))

        total = await db.scalar(select(func.count()).select_from(User).where(*conditions))
        order_clauses = self._build_order_clauses(sort_field, sort_order)
        result = await db.execute(
            select(User)
            .where(*conditions)
            .order_by(*order_clauses)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_active_all(self, db: AsyncSession) -> list[User]:
        result = await db.execute(select(User))
        return list(result.scalars().all())

    async def list_pending(self, db: AsyncSession) -> list[User]:
        result = await db.execute(
            select(User).where(User.sync_status.in_(["pending", "pending_disable", "pending_delete"]))
        )
        return list(result.scalars().all())

    async def list_failed_or_pending(self, db: AsyncSession) -> list[User]:
        result = await db.execute(
            select(User).where(User.sync_status.in_(["pending", "pending_disable", "pending_delete", "failed"]))
        )
        return list(result.scalars().all())

    def _build_order_clauses(self, sort_field: str | None, sort_order: str):
        descending = str(sort_order).lower() == "desc"
        if sort_field == "user_id":
            length_expr = func.length(User.user_id)
            return [
                length_expr.desc() if descending else length_expr.asc(),
                User.user_id.desc() if descending else User.user_id.asc(),
                User.id.desc(),
            ]

        column = self.SORTABLE_FIELDS.get(sort_field)
        if column is not None:
            return [
                column.desc() if descending else column.asc(),
                User.id.desc(),
            ]

        return [User.created_at.desc(), User.id.desc()]
