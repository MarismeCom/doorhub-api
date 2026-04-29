import asyncio
import signal
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.attendance import AttendanceService

settings = get_settings()
scheduler = BackgroundScheduler()
att_svc = AttendanceService()


def sync_attendance_job(device_ip: str):
    async def _run():
        async with SessionLocal() as db:
            result = await att_svc.sync_from_device(db, device_ip, incremental=True)
            logger.info(f"定时同步完成 | 设备={device_ip} | 新增={result.synced_count} 条")

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error(f"定时同步失败 | 设备={device_ip} | 错误={e}")


def start_scheduler():
    device_ips = [ip.strip() for ip in settings.ZK_DEVICE_IPS.split(",") if ip.strip()]

    for ip in device_ips:
        scheduler.add_job(
            sync_attendance_job,
            "interval",
            minutes=settings.SYNC_INTERVAL_MINUTES,
            args=[ip],
            id=f"sync_{ip.replace('.', '_')}",
            replace_existing=True,
        )

    def signal_handler(signum, frame):
        logger.info("收到退出信号，正在关闭定时任务...")
        scheduler.shutdown(wait=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    scheduler.start()
    logger.info(f"定时任务已启动 | 设备={device_ips} | 间隔={settings.SYNC_INTERVAL_MINUTES}分钟")


def stop_scheduler():
    scheduler.shutdown(wait=True)
    logger.info("定时任务已停止")
