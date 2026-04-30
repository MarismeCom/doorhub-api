import asyncio
from concurrent.futures import Future
import json
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.runtime import get_app_loop
from app.db.session import SessionLocal
from app.models import Device
from app.services.attendance import AttendanceService


@dataclass
class AttendanceSyncSettings:
    enabled: bool = False
    time: str = "23:00"
    device_ips: list[str] | None = None


class AttendanceSyncManager:
    def __init__(self):
        settings = get_settings()
        self._timezone = ZoneInfo(settings.APP_TIMEZONE)
        self._scheduler = BackgroundScheduler(timezone=self._timezone)
        self._service = AttendanceService()
        self._state_lock = threading.Lock()
        self._running = False
        self._status = {
            "running": False,
            "progress": 0,
            "stage": "idle",
            "message": "",
            "source": None,
            "device_ip": None,
            "started_at": None,
            "finished_at": None,
            "fetched_count": 0,
            "synced_count": 0,
            "duplicate_count": 0,
            "skipped_invalid_count": 0,
        }
        self._settings_path = Path(__file__).resolve().parents[2] / "data" / "attendance_sync_settings.json"
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
        job = self._scheduler.get_job("attendance_daily_sync") if self._scheduler.running else None
        if job and job.next_run_time:
            next_run_at = job.next_run_time.isoformat()
        return {
            "enabled": self._settings.enabled,
            "time": self._settings.time,
            "device_ips": list(self._settings.device_ips or []),
            "next_run_at": next_run_at,
            "timezone": str(self._timezone),
        }

    def update_settings(self, enabled: bool, time_value: str, device_ips: list[str] | None = None) -> dict:
        self._settings = AttendanceSyncSettings(enabled=enabled, time=time_value, device_ips=device_ips or [])
        self._save_settings()
        self._refresh_schedule()
        return self.get_settings()

    def get_status(self) -> dict:
        with self._state_lock:
            return {
                "status": deepcopy(self._status),
                "schedule": self.get_settings(),
            }

    async def run_manual_sync(self, device_ip: str, incremental: bool) -> object:
        self._begin_run(device_ip=device_ip, source="manual")
        try:
            async with SessionLocal() as db:
                result = await self._service.sync_from_device(
                    db,
                    device_ip,
                    incremental=incremental,
                    progress_callback=self._update_progress,
                )
            self._finish_run(result=result, message="手动同步完成")
            return result
        except Exception as error:
            self._fail_run(str(error))
            raise

    def start_manual_sync(self, device_ip: str, incremental: bool) -> dict:
        loop = get_app_loop()
        if loop is None or not loop.is_running():
            raise RuntimeError("应用事件循环未就绪，无法启动同步任务")

        self._begin_run(device_ip=device_ip, source="manual")
        self._status.update(
            {
                "message": "同步任务已启动，正在排队执行",
                "incremental": incremental,
            }
        )

        future = asyncio.run_coroutine_threadsafe(
            self._run_manual_sync_task(device_ip=device_ip, incremental=incremental),
            loop,
        )
        self._manual_task = future
        return self.get_status()["status"]

    async def _run_manual_sync_task(self, device_ip: str, incremental: bool):
        try:
            async with SessionLocal() as db:
                result = await self._service.sync_from_device(
                    db,
                    device_ip,
                    incremental=incremental,
                    progress_callback=self._update_progress,
                )
            completion_message = "没有更多新数据" if incremental and getattr(result, "synced_count", 0) == 0 else "手动同步完成"
            self._finish_run(result=result, message=completion_message)
        except Exception as error:
            self._fail_run(str(error))
            logger.exception(f"手动同步失败: {error}")
        finally:
            self._manual_task = None

    async def run_scheduled_sync(self):
        device_ips = await self._load_scheduled_device_ips()
        if not device_ips:
            logger.warning("定时同步已跳过：当前没有启用设备")
            return

        self._begin_run(device_ip=",".join(device_ips), source="scheduled")
        total_fetched = 0
        total_synced = 0
        total_duplicate = 0
        total_skipped = 0
        try:
            async with SessionLocal() as db:
                for index, device_ip in enumerate(device_ips, start=1):
                    self._update_progress(
                        progress=min(10 + int(index / max(len(device_ips), 1) * 70), 85),
                        stage="syncing",
                        message=f"正在同步设备 {device_ip} ({index}/{len(device_ips)})",
                        device_ip=device_ip,
                    )
                    result = await self._service.sync_from_device(
                        db,
                        device_ip,
                        incremental=True,
                        progress_callback=self._update_progress,
                    )
                    total_fetched += result.fetched_count
                    total_synced += result.synced_count
                    total_duplicate += result.duplicate_count
                    total_skipped += result.skipped_invalid_count

            summary = type(
                "ScheduledSyncSummary",
                (),
                {
                    "fetched_count": total_fetched,
                    "synced_count": total_synced,
                    "duplicate_count": total_duplicate,
                    "skipped_invalid_count": total_skipped,
                },
            )()
            self._finish_run(result=summary, message="定时同步完成")
        except Exception as error:
            self._fail_run(str(error))
            raise

    def _begin_run(self, device_ip: str, source: str):
        with self._state_lock:
            if self._running:
                raise RuntimeError("当前已有同步任务正在执行")
            self._running = True
            self._status.update(
                {
                    "running": True,
                    "progress": 5,
                    "stage": "starting",
                    "message": "正在启动同步任务",
                    "source": source,
                    "device_ip": device_ip,
                    "incremental": False,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": None,
                    "fetched_count": 0,
                    "synced_count": 0,
                    "duplicate_count": 0,
                    "skipped_invalid_count": 0,
                }
            )

    def _finish_run(self, result: object, message: str):
        with self._state_lock:
            self._running = False
            self._status.update(
                {
                    "running": False,
                    "progress": 100,
                    "stage": "completed",
                    "message": message,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "fetched_count": getattr(result, "fetched_count", 0),
                    "synced_count": getattr(result, "synced_count", 0),
                    "duplicate_count": getattr(result, "duplicate_count", 0),
                    "skipped_invalid_count": getattr(result, "skipped_invalid_count", 0),
                }
            )

    def _fail_run(self, message: str):
        with self._state_lock:
            self._running = False
            self._status.update(
                {
                    "running": False,
                    "progress": 100,
                    "stage": "failed",
                    "message": message,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    def _update_progress(self, **kwargs):
        with self._state_lock:
            self._status.update(kwargs)

    def _load_settings(self) -> AttendanceSyncSettings:
        if not self._settings_path.exists():
            settings = AttendanceSyncSettings()
            self._write_settings(settings)
            return settings

        data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        return AttendanceSyncSettings(
            enabled=bool(data.get("enabled", False)),
            time=str(data.get("time", "23:00")),
            device_ips=[str(ip) for ip in data.get("device_ips", []) if ip],
        )

    def _save_settings(self):
        self._write_settings(self._settings)

    def _write_settings(self, settings: AttendanceSyncSettings):
        self._settings_path.write_text(
            json.dumps(
                {
                    "enabled": settings.enabled,
                    "time": settings.time,
                    "device_ips": list(settings.device_ips or []),
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _refresh_schedule(self):
        job_id = "attendance_daily_sync"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        if not self._settings.enabled:
            logger.info("打卡定时同步已禁用")
            return

        hour, minute = [int(part) for part in self._settings.time.split(":", 1)]
        self._scheduler.add_job(
            self._run_scheduled_job,
            CronTrigger(hour=hour, minute=minute, timezone=self._timezone),
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"打卡定时同步已启用：每天 {self._settings.time} ({self._timezone})")

    def _run_scheduled_job(self):
        loop = get_app_loop()
        if loop is None or not loop.is_running():
            logger.warning("定时同步已跳过：应用事件循环未就绪")
            return

        try:
            future = asyncio.run_coroutine_threadsafe(self.run_scheduled_sync(), loop)
            self._scheduled_task = future
            future.add_done_callback(self._handle_scheduled_task_result)
        except RuntimeError as error:
            logger.warning(f"定时同步已跳过：{error}")
        except Exception as error:
            logger.error(f"定时同步失败：{error}")

    def _handle_scheduled_task_result(self, future: Future):
        self._scheduled_task = None
        try:
            future.result()
        except RuntimeError as error:
            logger.warning(f"定时同步已跳过：{error}")
        except Exception as error:
            logger.exception(f"定时同步失败：{error}")

    async def _load_active_device_ips(self) -> list[str]:
        async with SessionLocal() as db:
            result = await db.execute(select(Device.ip).where(Device.is_active == True).order_by(Device.id.asc()))
            return [ip for ip in result.scalars().all() if ip]

    async def _load_scheduled_device_ips(self) -> list[str]:
        active_device_ips = await self._load_active_device_ips()
        selected_device_ips = list(self._settings.device_ips or [])
        if not selected_device_ips:
            return active_device_ips
        active_set = set(active_device_ips)
        return [ip for ip in selected_device_ips if ip in active_set]


attendance_sync_manager = AttendanceSyncManager()
