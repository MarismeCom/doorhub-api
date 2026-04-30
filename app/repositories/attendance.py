from datetime import date, datetime

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attendance, AttendanceDaily, DoorLog
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


class AttendanceDailyRepository:
    async def get_existing_user_ids(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
        user_ids: list[str] | None = None,
    ) -> set[str]:
        statement = select(AttendanceDaily.user_id).where(
            AttendanceDaily.attend_date >= start_date,
            AttendanceDaily.attend_date <= end_date,
        )
        if user_ids:
            statement = statement.where(AttendanceDaily.user_id.in_(user_ids))
        result = await db.execute(statement.distinct())
        return set(result.scalars().all())

    async def delete_records(
        self,
        db: AsyncSession,
        user_ids: list[str],
        start_date: date,
        end_date: date,
    ) -> None:
        if not user_ids:
            return
        await db.execute(
            delete(AttendanceDaily).where(
                AttendanceDaily.user_id.in_(user_ids),
                AttendanceDaily.attend_date >= start_date,
                AttendanceDaily.attend_date <= end_date,
            )
        )

    async def replace_records(
        self,
        db: AsyncSession,
        user_id: str,
        start_date: date,
        end_date: date,
        records: list[AttendanceDaily],
    ) -> None:
        await db.execute(
            delete(AttendanceDaily).where(
                AttendanceDaily.user_id == user_id,
                AttendanceDaily.attend_date >= start_date,
                AttendanceDaily.attend_date <= end_date,
            )
        )
        db.add_all(records)

    async def list_records(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
        keyword: str | None = None,
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        join_condition = and_(User.user_id == AttendanceDaily.user_id, User.deleted_at.is_(None))
        query = select(AttendanceDaily, User.name.label("user_name")).outerjoin(User, join_condition)
        count_query = select(func.count()).select_from(AttendanceDaily).outerjoin(User, join_condition)

        condition = [
            AttendanceDaily.attend_date >= start_date,
            AttendanceDaily.attend_date <= end_date,
        ]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            condition.append(or_(AttendanceDaily.user_id.ilike(like_keyword), User.name.ilike(like_keyword)))
        if status:
            condition.append(AttendanceDaily.status == status)

        query = query.where(*condition)
        count_query = count_query.where(*condition)

        total = await db.scalar(count_query)
        result = await db.execute(
            query.order_by(AttendanceDaily.attend_date.desc(), AttendanceDaily.user_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        records = [
            {
                "id": record.id,
                "user_id": record.user_id,
                "user_name": user_name,
                "attend_date": record.attend_date,
                "plan_start": record.plan_start,
                "plan_end": record.plan_end,
                "actual_checkin": record.actual_checkin,
                "actual_checkout": record.actual_checkout,
                "late_minutes": record.late_minutes,
                "early_minutes": record.early_minutes,
                "work_minutes": record.work_minutes,
                "overtime_minutes": record.overtime_minutes,
                "status": record.status,
                "is_workday": record.is_workday,
                "calc_time": record.calc_time,
            }
            for record, user_name in result.all()
        ]
        return records, int(total or 0)

    async def list_all_records(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
        keyword: str | None = None,
        status: int | None = None,
    ) -> list[dict]:
        records, _ = await self.list_records(
            db=db,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            status=status,
            page=1,
            page_size=100000,
        )
        return records

    async def monthly_summary(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
        keyword: str | None = None,
    ) -> dict:
        join_condition = and_(User.user_id == AttendanceDaily.user_id, User.deleted_at.is_(None))
        query = select(
            func.coalesce(func.count().filter(AttendanceDaily.is_workday.is_(True)), 0).label("workday_count"),
            func.coalesce(
                func.count().filter(
                    and_(
                        AttendanceDaily.is_workday.is_(True),
                        AttendanceDaily.status.in_([1, 2, 3, 5, 6]),
                    )
                ),
                0,
            ).label("attendance_days"),
            func.coalesce(func.count().filter(AttendanceDaily.status == 7), 0).label("overtime_days"),
            func.coalesce(func.count().filter(AttendanceDaily.status.in_([2, 6])), 0).label("late_count"),
            func.coalesce(func.count().filter(AttendanceDaily.status.in_([3, 6])), 0).label("early_count"),
            func.coalesce(func.count().filter(AttendanceDaily.status == 4), 0).label("absence_count"),
            func.coalesce(func.count().filter(AttendanceDaily.status == 5), 0).label("missing_count"),
            func.coalesce(func.sum(AttendanceDaily.work_minutes), 0).label("total_work_minutes"),
            func.coalesce(func.sum(AttendanceDaily.overtime_minutes), 0).label("total_overtime_minutes"),
        ).select_from(AttendanceDaily).outerjoin(User, join_condition)

        condition = [
            AttendanceDaily.attend_date >= start_date,
            AttendanceDaily.attend_date <= end_date,
        ]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            condition.append(or_(AttendanceDaily.user_id.ilike(like_keyword), User.name.ilike(like_keyword)))

        query = query.where(*condition)
        result = (await db.execute(query)).mappings().one()
        return dict(result)
