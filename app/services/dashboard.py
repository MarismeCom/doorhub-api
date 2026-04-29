from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attendance, Device, User


class DashboardService:
    async def get_summary(self, db: AsyncSession) -> dict:
        total_users = int(await db.scalar(select(func.count()).select_from(User)) or 0)
        active_users = int(await db.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0)
        disabled_users = int(await db.scalar(select(func.count()).select_from(User).where(User.status == "disabled")) or 0)

        total_devices = int(await db.scalar(select(func.count()).select_from(Device)) or 0)
        active_devices = int(await db.scalar(select(func.count()).select_from(Device).where(Device.is_active.is_(True))) or 0)
        inactive_devices = total_devices - active_devices

        total_attendances = int(await db.scalar(select(func.count()).select_from(Attendance)) or 0)

        sync_status_rows = (
            await db.execute(
                select(User.sync_status, func.count())
                .group_by(User.sync_status)
                .order_by(User.sync_status.asc())
            )
        ).all()

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_series = []
        for offset in range(6, -1, -1):
            day_start = today_start - timedelta(days=offset)
            day_end = day_start + timedelta(days=1)
            count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Attendance)
                    .where(Attendance.timestamp >= day_start, Attendance.timestamp < day_end)
                )
                or 0
            )
            daily_series.append(
                {
                    "date": day_start.date().isoformat(),
                    "count": count,
                }
            )

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "disabled": disabled_users,
            },
            "devices": {
                "total": total_devices,
                "active": active_devices,
                "inactive": inactive_devices,
            },
            "attendances": {
                "total": total_attendances,
                "recent_7d": daily_series,
            },
            "sync_status": [
                {"status": status or "unknown", "count": int(count or 0)}
                for status, count in sync_status_rows
            ],
        }
