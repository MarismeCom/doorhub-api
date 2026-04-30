from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HolidayCalendar


class HolidayCalendarRepository:
    async def list_by_year_month(self, db: AsyncSession, year: int, month: int) -> list[HolidayCalendar]:
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        result = await db.execute(
            select(HolidayCalendar)
            .where(HolidayCalendar.holiday_date >= start_date, HolidayCalendar.holiday_date < end_date)
            .order_by(HolidayCalendar.holiday_date.asc())
        )
        return list(result.scalars().all())

    async def list_by_range(self, db: AsyncSession, start_date: date, end_date: date) -> list[HolidayCalendar]:
        result = await db.execute(
            select(HolidayCalendar)
            .where(HolidayCalendar.holiday_date >= start_date, HolidayCalendar.holiday_date <= end_date)
            .order_by(HolidayCalendar.holiday_date.asc())
        )
        return list(result.scalars().all())

    async def list_years(self, db: AsyncSession, years: list[int]) -> list[int]:
        if not years:
            return []
        result = await db.execute(select(HolidayCalendar.year).where(HolidayCalendar.year.in_(years)).distinct())
        return [int(item) for item in result.scalars().all()]

    async def has_year(self, db: AsyncSession, year: int) -> bool:
        result = await db.execute(select(HolidayCalendar.id).where(HolidayCalendar.year == year).limit(1))
        return result.scalar_one_or_none() is not None

    async def replace_year(self, db: AsyncSession, year: int, records: list[HolidayCalendar]) -> None:
        await db.execute(delete(HolidayCalendar).where(HolidayCalendar.year == year))
        db.add_all(records)

    def build_record(
        self,
        holiday_date: date,
        type_value: int,
        is_holiday: bool,
        name: str,
        source: str,
        fetched_at: datetime,
    ) -> HolidayCalendar:
        return HolidayCalendar(
            holiday_date=holiday_date,
            year=holiday_date.year,
            type=type_value,
            is_holiday=is_holiday,
            name=name,
            source=source,
            fetched_at=fetched_at,
        )
