import json
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.zk_client import DEVICE_TIMEZONE
from app.repositories.holiday_calendar import HolidayCalendarRepository


class WorkdayProvider:
    async def get_workday_map(self, db: AsyncSession, start_date: date, end_date: date) -> dict[date, bool]:
        raise NotImplementedError


class WeekdayWorkdayProvider(WorkdayProvider):
    async def get_workday_map(self, db: AsyncSession, start_date: date, end_date: date) -> dict[date, bool]:
        del db
        result: dict[date, bool] = {}
        current = start_date
        while current <= end_date:
            result[current] = current.weekday() < 5
            current += timedelta(days=1)
        return result


class AilccCachedWorkdayProvider(WorkdayProvider):
    def __init__(self, api_base_url: str, api_token: str = ""):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_token = api_token.strip()
        self.repository = HolidayCalendarRepository()
        self.fallback_provider = WeekdayWorkdayProvider()

    async def get_workday_map(self, db: AsyncSession, start_date: date, end_date: date) -> dict[date, bool]:
        years = list(range(start_date.year, end_date.year + 1))
        cached_years = set(await self.repository.list_years(db, years))
        missing_years = [year for year in years if year not in cached_years]

        if missing_years:
            logger.info(f"holiday.ailcc.com 缺失缓存年份: {missing_years}，开始拉取并写入本地缓存")
            for year in missing_years:
                try:
                    await self.refresh_year(db, year)
                except Exception as exc:
                    logger.warning(f"拉取 ailcc 节假日数据失败，年份={year}，将降级为默认工作日规则: {exc}")

        cached_rows = await self.repository.list_by_range(db, start_date, end_date)
        cached_map = {row.holiday_date: self._is_workday_from_type(row.type, row.is_holiday) for row in cached_rows}

        if len(cached_map) == (end_date - start_date).days + 1:
            return cached_map

        fallback_map = await self.fallback_provider.get_workday_map(db, start_date, end_date)
        fallback_map.update(cached_map)
        return fallback_map

    async def refresh_year(self, db: AsyncSession, year: int) -> int:
        rows = self._fetch_year(year)
        fetched_at = datetime.now(DEVICE_TIMEZONE)
        await self.repository.replace_year(
            db,
            year,
            [
                self.repository.build_record(
                    holiday_date=item["holiday_date"],
                    type_value=item["type"],
                    is_holiday=item["is_holiday"],
                    name=item["name"],
                    source="ailcc",
                    fetched_at=fetched_at,
                )
                for item in rows
            ],
        )
        await db.commit()
        return len(rows)

    async def ensure_year_cached(self, db: AsyncSession, year: int) -> None:
        if await self.repository.has_year(db, year):
            return
        await self.refresh_year(db, year)

    def _fetch_year(self, year: int) -> list[dict]:
        url = f"{self.api_base_url}/api/holiday/allyear/{year}"
        request = Request(url, headers=self._build_headers(), method="GET")
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"ailcc 接口返回 HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"ailcc 接口访问失败: {exc.reason}") from exc

        if payload.get("code") != 0:
            raise RuntimeError(f"ailcc 接口返回异常: {payload}")

        data = payload.get("data") or []
        rows: list[dict] = []
        for item in data:
            holiday_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
            rows.append(
                {
                    "holiday_date": holiday_date,
                    "type": int(item.get("type", 0) or 0),
                    "is_holiday": bool(int(item.get("is_holiday", 0) or 0)),
                    "name": item.get("name") or "",
                }
            )
        return rows

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["X-API-TOKEN"] = self.api_token
        return headers

    @staticmethod
    def _is_workday_from_type(type_value: int, is_holiday: bool) -> bool:
        if type_value == 4:
            return True
        if is_holiday:
            return False
        return type_value == 0


def build_workday_provider() -> WorkdayProvider:
    settings = get_settings()
    provider_name = settings.ATTENDANCE_WORKDAY_PROVIDER.strip().lower()

    if provider_name == "ailcc":
        return AilccCachedWorkdayProvider(
            api_base_url=settings.ATTENDANCE_AILCC_API_BASE_URL,
            api_token=settings.ATTENDANCE_AILCC_API_TOKEN,
        )

    return WeekdayWorkdayProvider()
