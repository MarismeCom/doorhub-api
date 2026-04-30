import calendar
import asyncio
import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta
import zlib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.zk_client import DEVICE_TIMEZONE
from app.core.config import get_settings
from app.models import Attendance, AttendanceDaily, User
from app.repositories.attendance import AttendanceDailyRepository
from app.repositories.holiday_calendar import HolidayCalendarRepository
from app.schemas import AttendanceMonthlySummaryResponse
from app.services.workday import build_workday_provider


class AttendanceRecordService:
    def __init__(self):
        settings = get_settings()
        self.repository = AttendanceDailyRepository()
        self.holiday_repository = HolidayCalendarRepository()
        self.plan_start = self._parse_time(settings.ATTENDANCE_PLAN_START, default=time(hour=9, minute=0))
        self.plan_end = self._parse_time(settings.ATTENDANCE_PLAN_END, default=time(hour=18, minute=0))
        self.workday_provider = build_workday_provider()
        self._ensure_locks: dict[str, asyncio.Lock] = {}

    def parse_year_month(self, year_month: str) -> tuple[date, date]:
        try:
            year, month = [int(part) for part in year_month.split("-", 1)]
            last_day = calendar.monthrange(year, month)[1]
        except ValueError as exc:
            raise ValueError("year_month 必须为 YYYY-MM") from exc
        return date(year, month, 1), date(year, month, last_day)

    async def ensure_monthly_records(
        self,
        db: AsyncSession,
        year_month: str,
        keyword: str | None = None,
        user_id: str | None = None,
        force: bool = False,
    ) -> None:
        lock_key = f"{year_month}:{user_id or keyword or '__all__'}"
        lock = self._ensure_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            await self._acquire_generation_lock(db, lock_key)
            await self._ensure_monthly_records_inner(db, year_month, keyword=keyword, user_id=user_id, force=force)

    async def _acquire_generation_lock(self, db: AsyncSession, lock_key: str) -> None:
        bind = db.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            return
        advisory_key = zlib.crc32(lock_key.encode("utf-8"))
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": advisory_key})

    async def _ensure_monthly_records_inner(
        self,
        db: AsyncSession,
        year_month: str,
        keyword: str | None = None,
        user_id: str | None = None,
        force: bool = False,
    ) -> None:
        start_date, end_date = self.parse_year_month(year_month)

        timestamps_start = datetime.combine(start_date, time.min, tzinfo=DEVICE_TIMEZONE)
        timestamps_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=DEVICE_TIMEZONE)
        attendance_query = select(Attendance).where(
            Attendance.timestamp >= timestamps_start,
            Attendance.timestamp < timestamps_end,
        )
        if user_id:
            attendance_query = attendance_query.where(Attendance.user_id == user_id)
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            attendance_query = attendance_query.where(Attendance.user_id.ilike(like_keyword))
        attendance_query = attendance_query.order_by(Attendance.user_id.asc(), Attendance.timestamp.asc())
        attendance_rows = list((await db.execute(attendance_query)).scalars().all())

        if not attendance_rows:
            if force and user_id:
                await self.repository.delete_records(db, [user_id], start_date, end_date)
                await db.commit()
            return

        raw_user_ids = sorted({row.user_id for row in attendance_rows})
        target_user_ids = raw_user_ids
        if not force:
            existing_user_ids = await self.repository.get_existing_user_ids(db, start_date, end_date, raw_user_ids)
            target_user_ids = [item for item in raw_user_ids if item not in existing_user_ids]
            if not target_user_ids:
                return

        users_query = select(User).where(
            User.deleted_at.is_(None),
            User.user_id.in_(target_user_ids),
        )
        users = list((await db.execute(users_query.order_by(User.user_id.asc()))).scalars().all())
        if not users:
            return

        workday_map = await self.workday_provider.get_workday_map(db, start_date, end_date)

        records_by_user_date: dict[tuple[str, date], list[datetime]] = defaultdict(list)
        for row in attendance_rows:
            local_timestamp = self._to_local_timestamp(row.timestamp)
            local_date = local_timestamp.date()
            records_by_user_date[(row.user_id, local_date)].append(local_timestamp)

        now = datetime.now(DEVICE_TIMEZONE)
        for user in users:
            daily_records: list[AttendanceDaily] = []
            current_date = start_date
            while current_date <= end_date:
                daily_records.append(
                    self._build_daily_record(
                        user.user_id,
                        current_date,
                        records_by_user_date,
                        workday_map.get(current_date, True),
                        now,
                    )
                )
                current_date += timedelta(days=1)
            await self.repository.replace_records(db, user.user_id, start_date, end_date, daily_records)

        await db.commit()

    def _build_daily_record(
        self,
        user_id: str,
        attend_date: date,
        records_by_user_date: dict[tuple[str, date], list[datetime]],
        is_workday: bool,
        calc_time: datetime,
    ) -> AttendanceDaily:
        day_records = records_by_user_date.get((user_id, attend_date), [])
        plan_start_dt = datetime.combine(attend_date, self.plan_start)
        plan_end_dt = datetime.combine(attend_date, self.plan_end)

        actual_checkin = day_records[0] if day_records else None
        actual_checkout = day_records[-1] if len(day_records) >= 2 else None

        late_minutes = 0
        early_minutes = 0
        work_minutes = 0
        overtime_minutes = 0

        if not is_workday:
            if not day_records:
                status = 1
            else:
                checkin_local = actual_checkin.replace(tzinfo=None) if actual_checkin else None
                checkout_local = actual_checkout.replace(tzinfo=None) if actual_checkout else None
                if checkin_local and checkout_local:
                    work_minutes = max(0, int((checkout_local - checkin_local).total_seconds() // 60))
                    overtime_minutes = work_minutes
                    status = 7
                else:
                    status = 5
        elif not day_records:
            status = 4
        else:
            checkin_local = actual_checkin.replace(tzinfo=None) if actual_checkin else None
            checkout_local = actual_checkout.replace(tzinfo=None) if actual_checkout else None

            if checkin_local and checkin_local > plan_start_dt:
                late_minutes = int((checkin_local - plan_start_dt).total_seconds() // 60)
            if actual_checkout:
                if checkout_local and checkout_local < plan_end_dt:
                    early_minutes = int((plan_end_dt - checkout_local).total_seconds() // 60)
                work_minutes = max(
                    0,
                    int((checkout_local - checkin_local).total_seconds() // 60),
                )
                overtime_minutes = max(
                    0,
                    int((checkout_local - plan_end_dt).total_seconds() // 60),
                )

            if len(day_records) == 1 or not actual_checkout:
                status = 5
            elif late_minutes > 0 and early_minutes > 0:
                status = 6
            elif late_minutes > 0:
                status = 2
            elif early_minutes > 0:
                status = 3
            else:
                status = 1

        return AttendanceDaily(
            user_id=user_id,
            attend_date=attend_date,
            plan_start=self.plan_start.strftime("%H:%M"),
            plan_end=self.plan_end.strftime("%H:%M"),
            actual_checkin=actual_checkin,
            actual_checkout=actual_checkout,
            late_minutes=late_minutes,
            early_minutes=early_minutes,
            work_minutes=work_minutes,
            overtime_minutes=overtime_minutes,
            status=status,
            is_workday=is_workday,
            calc_time=calc_time,
        )

    async def list_daily_records(
        self,
        db: AsyncSession,
        year_month: str,
        keyword: str | None = None,
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
        ensure: bool = True,
    ) -> tuple[list[dict], int]:
        if ensure:
            await self.ensure_monthly_records(db, year_month, keyword=keyword)
        start_date, end_date = self.parse_year_month(year_month)
        return await self.repository.list_records(db, start_date, end_date, keyword, status, page, page_size)

    async def get_monthly_summary(
        self,
        db: AsyncSession,
        year_month: str,
        keyword: str | None = None,
        ensure: bool = True,
    ) -> AttendanceMonthlySummaryResponse:
        if ensure:
            await self.ensure_monthly_records(db, year_month, keyword=keyword)
        start_date, end_date = self.parse_year_month(year_month)
        summary = await self.repository.monthly_summary(db, start_date, end_date, keyword)
        return AttendanceMonthlySummaryResponse(year_month=year_month, **summary)

    async def export_monthly_csv(
        self,
        db: AsyncSession,
        year_month: str,
        keyword: str | None = None,
        status: int | None = None,
    ) -> bytes:
        await self.ensure_monthly_records(db, year_month, keyword=keyword)
        start_date, end_date = self.parse_year_month(year_month)
        records = await self.repository.list_all_records(db, start_date, end_date, keyword, status)
        holiday_rows = await self.holiday_repository.list_by_range(db, start_date, end_date)
        holiday_map = {row.holiday_date.isoformat(): row for row in holiday_rows}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "日期",
                "日类型",
                "工号",
                "姓名",
                "计划上班",
                "计划下班",
                "实际签到",
                "实际签退",
                "迟到分钟",
                "早退分钟",
                "工时分钟",
                "加班分钟",
                "状态",
            ]
        )
        for record in records:
            attend_date = record["attend_date"].isoformat()
            writer.writerow(
                [
                    attend_date,
                    self.day_type_label(attend_date, holiday_map),
                    record["user_id"],
                    record.get("user_name") or "",
                    record.get("plan_start") or "",
                    record.get("plan_end") or "",
                    self._format_datetime(record.get("actual_checkin")),
                    self._format_datetime(record.get("actual_checkout")),
                    record.get("late_minutes") or 0,
                    record.get("early_minutes") or 0,
                    record.get("work_minutes") or 0,
                    record.get("overtime_minutes") or 0,
                    self.status_label(record.get("status")),
                ]
            )

        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def status_label(value: int | None) -> str:
        mapping = {
            1: "正常",
            2: "迟到",
            3: "早退",
            4: "缺勤",
            5: "漏打卡",
            6: "迟到+早退",
            7: "加班",
        }
        return mapping.get(value, f"未知({value})")

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if not value:
            return ""
        localized = AttendanceRecordService._to_local_timestamp(value)
        return localized.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_time(value: str, default: time) -> time:
        try:
            hour, minute = [int(part) for part in value.split(":", 1)]
            return time(hour=hour, minute=minute)
        except (AttributeError, ValueError):
            return default

    @staticmethod
    def day_type_label(attend_date: str, holiday_map: dict) -> str:
        row = holiday_map.get(attend_date)
        if not row:
            return "工作日"
        if row.type == 4:
            return "调休班"
        if row.type in (2, 3) or row.is_holiday:
            return row.name or "节假日"
        if row.type == 1:
            return "周末"
        return "工作日"

    @staticmethod
    def _to_local_timestamp(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=DEVICE_TIMEZONE)
        return value.astimezone(DEVICE_TIMEZONE)
