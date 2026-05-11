from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AttendanceMonthlyExportSetting


class AttendanceMonthlyExportSettingRepository:
    async def get_by_user_id(self, db: AsyncSession, system_user_id: int) -> AttendanceMonthlyExportSetting | None:
        result = await db.execute(
            select(AttendanceMonthlyExportSetting).where(
                AttendanceMonthlyExportSetting.system_user_id == system_user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, db: AsyncSession, system_user_id: int) -> AttendanceMonthlyExportSetting:
        row = await self.get_by_user_id(db, system_user_id)
        if row is None:
            row = AttendanceMonthlyExportSetting(system_user_id=system_user_id)
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return row
