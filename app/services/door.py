import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DoorLog
from app.repositories.attendance import DoorLogRepository
from app.schemas import UnlockRequest
from app.core.zk_client import ZKClient, ZKOperationError


class DoorService:
    def __init__(self):
        self.repository = DoorLogRepository()

    async def open(self, db: AsyncSession, device_ip: str, operator: str, data: UnlockRequest) -> DoorLog:
        result = "failed"
        error_msg = ""
        try:
            client = ZKClient(device_ip)
            await asyncio.to_thread(client.unlock, data.unlock_seconds)
            result = "success"
        except ZKOperationError as e:
            error_msg = str(e)

        log = DoorLog(
            operator=operator,
            device_ip=device_ip,
            action="open",
            result=result,
            remark=data.remark or error_msg,
            operated_at=datetime.now(timezone.utc),
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)

        if result == "failed":
            raise RuntimeError(f"开门失败: {error_msg}")
        return log

    async def get_logs(
        self,
        db: AsyncSession,
        device_ip: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DoorLog], int]:
        return await self.repository.list_logs(db, device_ip, start_date, end_date, page, page_size)
