import asyncio
import json
import threading
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.core.config import get_settings
from app.core.runtime import get_app_loop
from app.db.session import SessionLocal
from app.services.workday import AilccCachedWorkdayProvider


@dataclass
class HolidayCacheSettings:
    enabled: bool = False
    frequency: str = "daily"
    time: str = "03:00"
    weekday: int = 1


class HolidayCacheManager:
    def __init__(self):
        settings = get_settings()
        self._timezone = ZoneInfo(settings.APP_TIMEZONE)
        self._scheduler = BackgroundScheduler(timezone=self._timezone)
        self._provider = AilccCachedWorkdayProvider(
            api_base_url=settings.ATTENDANCE_AILCC_API_BASE_URL,
            api_token=settings.ATTENDANCE_AILCC_API_TOKEN,
        )
        self._state_lock = threading.Lock()
        self._running = False
        self._status = {
            "running": False,
            "stage": "idle",
            "message": "",
            "source": None,
            "year": None,
            "started_at": None,
            "finished_at": None,
            "refreshed_count": 0,
        }
        self._settings_path = Path(__file__).resolve().parents[2] / "data" / "holiday_cache_settings.json"
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = self._load_settings()
        self._manual_task: Future | None = None
        self._scheduled_task: Future | None = None

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
        self._refresh_schedule()

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._manual_task = None
        self._scheduled_task = None

    def get_settings(self) -> dict:
        next_run_at = None
        job = self._scheduler.get_job("holiday_cache_refresh") if self._scheduler.running else None
        if job and job.next_run_time:
            next_run_at = job.next_run_time.isoformat()
        return {
            "enabled": self._settings.enabled,
            "frequency": self._settings.frequency,
            "time": self._settings.time,
            "weekday": self._settings.weekday,
            "next_run_at": next_run_at,
            "timezone": str(self._timezone),
        }

    def update_settings(self, enabled: bool, frequency: str, time_value: str, weekday: int) -> dict:
        self._settings = HolidayCacheSettings(
            enabled=enabled,
            frequency=frequency,
            time=time_value,
            weekday=weekday,
        )
        self._save_settings()
        self._refresh_schedule()
        return self.get_settings()

    def get_status(self) -> dict:
        with self._state_lock:
            return {
                "status": deepcopy(self._status),
                "schedule": self.get_settings(),
            }

    def start_manual_refresh(self, year: int) -> dict:
        loop = get_app_loop()
        if loop is None or not loop.is_running():
            raise RuntimeError("应用事件循环未就绪，无法启动节假日缓存刷新任务")

        self._begin_run(year=year, source="manual")
        self._status.update({"message": "节假日缓存刷新任务已启动，正在排队执行"})
        future = asyncio.run_coroutine_threadsafe(self._run_manual_refresh_task(year), loop)
        self._manual_task = future
        return self.get_status()["status"]

    async def run_scheduled_refresh(self):
        current_year = datetime.now(self._timezone).year
        self._begin_run(year=current_year, source="scheduled")
        try:
            async with SessionLocal() as db:
                refreshed_count = await self._provider.refresh_year(db, current_year)
            self._finish_run(year=current_year, refreshed_count=refreshed_count, message="节假日缓存定时刷新完成")
        except Exception as error:
            self._fail_run(str(error))
            raise

    async def _run_manual_refresh_task(self, year: int):
        try:
            async with SessionLocal() as db:
                refreshed_count = await self._provider.refresh_year(db, year)
            self._finish_run(year=year, refreshed_count=refreshed_count, message="节假日缓存手动刷新完成")
        except Exception as error:
            self._fail_run(str(error))
            logger.exception(f"节假日缓存手动刷新失败: {error}")
        finally:
            self._manual_task = None

    def _begin_run(self, year: int, source: str):
        with self._state_lock:
            if self._running:
                raise RuntimeError("当前已有节假日缓存刷新任务正在执行")
            self._running = True
            self._status.update(
                {
                    "running": True,
                    "stage": "refreshing",
                    "message": "正在启动节假日缓存刷新任务",
                    "source": source,
                    "year": year,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": None,
                    "refreshed_count": 0,
                }
            )

    def _finish_run(self, year: int, refreshed_count: int, message: str):
        with self._state_lock:
            self._running = False
            self._status.update(
                {
                    "running": False,
                    "stage": "completed",
                    "message": message,
                    "year": year,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "refreshed_count": refreshed_count,
                }
            )

    def _fail_run(self, message: str):
        with self._state_lock:
            self._running = False
            self._status.update(
                {
                    "running": False,
                    "stage": "failed",
                    "message": message,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    def _load_settings(self) -> HolidayCacheSettings:
        if not self._settings_path.exists():
            settings = HolidayCacheSettings()
            self._write_settings(settings)
            return settings

        data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        return HolidayCacheSettings(
            enabled=bool(data.get("enabled", False)),
            frequency=str(data.get("frequency", "daily")),
            time=str(data.get("time", "03:00")),
            weekday=int(data.get("weekday", 1)),
        )

    def _save_settings(self):
        self._write_settings(self._settings)

    def _write_settings(self, settings: HolidayCacheSettings):
        payload = {
            "enabled": settings.enabled,
            "frequency": settings.frequency,
            "time": settings.time,
            "weekday": settings.weekday,
        }
        self._settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_schedule(self):
        job_id = "holiday_cache_refresh"
        if self._scheduler.running:
            existing_job = self._scheduler.get_job(job_id)
            if existing_job:
                self._scheduler.remove_job(job_id)

        if not self._settings.enabled:
            logger.info("节假日缓存定时刷新已禁用")
            return

        hour, minute = [int(part) for part in self._settings.time.split(":", 1)]
        if self._settings.frequency == "weekly":
            trigger = CronTrigger(day_of_week=str(max(0, min(6, self._settings.weekday - 1))), hour=hour, minute=minute)
        else:
            trigger = CronTrigger(hour=hour, minute=minute)

        self._scheduler.add_job(self._schedule_job, trigger=trigger, id=job_id, replace_existing=True)
        logger.info(
            f"节假日缓存定时刷新已启用：frequency={self._settings.frequency}, time={self._settings.time}, weekday={self._settings.weekday}"
        )

    def _schedule_job(self):
        loop = get_app_loop()
        if loop is None or not loop.is_running():
            logger.warning("应用事件循环未就绪，跳过节假日缓存定时刷新")
            return
        self._scheduled_task = asyncio.run_coroutine_threadsafe(self._run_scheduled_refresh_task(), loop)

    async def _run_scheduled_refresh_task(self):
        try:
            await self.run_scheduled_refresh()
        except Exception as error:
            logger.exception(f"节假日缓存定时刷新失败: {error}")
        finally:
            self._scheduled_task = None


holiday_cache_manager = HolidayCacheManager()
