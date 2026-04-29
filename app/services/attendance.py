import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attendance
from app.core.zk_client import DEVICE_TIMEZONE
from app.repositories.attendance import AttendanceRepository
from app.schemas import SyncResponse
from app.core.zk_client import ZKClient, ZKOperationError


class AttendanceService:
    def __init__(self):
        self.repository = AttendanceRepository()

    async def sync_from_device(
        self,
        db: AsyncSession,
        device_ip: str,
        incremental: bool = True,
        progress_callback=None,
    ) -> SyncResponse:
        try:
            client = ZKClient(device_ip)
            if progress_callback:
                progress_callback(progress=15, stage="fetching", message=f"正在读取设备 {device_ip} 打卡记录")
            records, skipped_invalid_count = await asyncio.to_thread(client.get_attendance_safe)
            if progress_callback:
                progress_callback(
                    progress=55,
                    stage="processing",
                    message=f"设备 {device_ip} 记录已解析，准备写入数据库",
                    fetched_count=len(records),
                    skipped_invalid_count=skipped_invalid_count,
                )
            sn = await asyncio.to_thread(client.get_serial_number)
            fetched_count = len(records)
            synced_count = 0
            duplicate_count = 0

            for record in records:
                timestamp = record.timestamp
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=DEVICE_TIMEZONE)
                if incremental and await self.repository.exists_record(
                    db, str(record.user_id), timestamp, sn
                ):
                    duplicate_count += 1
                    continue
                db.add(
                    Attendance(
                        user_id=str(record.user_id),
                        uid=record.uid,
                        timestamp=timestamp,
                        status=record.status,
                        punch=record.punch,
                        device_sn=sn,
                    )
                )
                synced_count += 1

            if progress_callback:
                progress_callback(
                    progress=90,
                    stage="saving",
                    message=f"设备 {device_ip} 同步结果已写入数据库",
                    fetched_count=fetched_count,
                    synced_count=synced_count,
                    duplicate_count=duplicate_count,
                    skipped_invalid_count=skipped_invalid_count,
                )
            await db.commit()
            logger.info(
                f"打卡记录同步完成: 设备={device_ip}, 解析={fetched_count} 条, 新增={synced_count} 条, 重复={duplicate_count} 条, 跳过坏记录={skipped_invalid_count} 条"
            )
            return SyncResponse(
                fetched_count=fetched_count,
                synced_count=synced_count,
                duplicate_count=duplicate_count,
                skipped_invalid_count=skipped_invalid_count,
                device_ip=device_ip,
                synced_at=datetime.now(timezone.utc),
            )
        except ZKOperationError as e:
            raise RuntimeError(f"设备操作失败: {e}")
        except Exception:
            await db.rollback()
            raise

    async def get_records(
        self,
        db: AsyncSession,
        keyword: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        return await self.repository.list_records(db, keyword, start_date, end_date, page, page_size)
