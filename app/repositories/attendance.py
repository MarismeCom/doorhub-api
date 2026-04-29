from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attendance, DoorLog
from app.models.user import User


class AttendanceRepository:
    async def exists_record(
        self,
        db: AsyncSession,
        user_id: str,
        timestamp: datetime,
        device_sn: str | None,
    ) -> bool:
        statement = select(
            exists().where(
                Attendance.user_id == user_id,
                Attendance.timestamp == timestamp,
                Attendance.device_sn == device_sn,
            )
        )
        return bool(await db.scalar(statement))

    async def list_records(
        self,
        db: AsyncSession,
        keyword: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        join_condition = and_(User.user_id == Attendance.user_id, User.deleted_at.is_(None))
        query = select(Attendance, User.name.label("user_name")).outerjoin(User, join_condition)
        count_query = select(func.count()).select_from(Attendance).outerjoin(User, join_condition)

        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            condition = or_(Attendance.user_id.ilike(like_keyword), User.name.ilike(like_keyword))
            query = query.where(condition)
            count_query = count_query.where(condition)
        if start_date:
            query = query.where(Attendance.timestamp >= start_date)
            count_query = count_query.where(Attendance.timestamp >= start_date)
        if end_date:
            query = query.where(Attendance.timestamp <= end_date)
            count_query = count_query.where(Attendance.timestamp <= end_date)

        total = await db.scalar(count_query)
        result = await db.execute(
            query.order_by(Attendance.timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        records = [
            {
                "id": attendance.id,
                "user_id": attendance.user_id,
                "user_name": user_name,
                "uid": attendance.uid,
                "timestamp": attendance.timestamp,
                "status": attendance.status,
                "punch": attendance.punch,
                "device_sn": attendance.device_sn,
            }
            for attendance, user_name in result.all()
        ]
        return records, int(total or 0)


class DoorLogRepository:
    async def list_logs(
        self,
        db: AsyncSession,
        device_ip: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DoorLog], int]:
        query = select(DoorLog)
        count_query = select(func.count()).select_from(DoorLog)

        if device_ip:
            query = query.where(DoorLog.device_ip == device_ip)
            count_query = count_query.where(DoorLog.device_ip == device_ip)
        if start_date:
            query = query.where(DoorLog.operated_at >= start_date)
            count_query = count_query.where(DoorLog.operated_at >= start_date)
        if end_date:
            query = query.where(DoorLog.operated_at <= end_date)
            count_query = count_query.where(DoorLog.operated_at <= end_date)

        total = await db.scalar(count_query)
        result = await db.execute(
            query.order_by(DoorLog.operated_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)
