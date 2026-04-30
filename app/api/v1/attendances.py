from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.deps import DBSessionDep
from app.core.attendance_sync_manager import attendance_sync_manager
from app.schemas import (
    ApiResponse,
    AttendanceResponse,
    AttendanceSyncScheduleUpdate,
    SyncRequest,
)
from app.services.attendance import AttendanceService

router = APIRouter(prefix="/api/v1/attendances", tags=["打卡记录"])
att_svc = AttendanceService()


@router.get("", response_model=ApiResponse)
async def get_attendances(
    db: DBSessionDep,
    keyword: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    try:
        records, total = await att_svc.get_records(db, keyword, start_date, end_date, page, page_size)
        return ApiResponse(data={"total": total, "page": page, "page_size": page_size, "records": [AttendanceResponse.model_validate(r) for r in records]})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.post("/sync", response_model=ApiResponse)
async def sync_attendances(data: SyncRequest, db: DBSessionDep):
    try:
        del db
        result = attendance_sync_manager.start_manual_sync(data.device_ip, data.incremental)
        return ApiResponse(
            message="同步任务已启动",
            data={
                "running": result.get("running", True),
                "progress": result.get("progress", 5),
                "stage": result.get("stage", "starting"),
                "message": result.get("message", "同步任务已启动，正在排队执行"),
                "source": result.get("source", "manual"),
                "device_ip": result.get("device_ip", data.device_ip),
                "incremental": result.get("incremental", data.incremental),
            },
        )
    except RuntimeError as e:
        status_code = 409 if "正在执行" in str(e) else 500
        raise HTTPException(status_code=status_code, detail={"code": 5002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.get("/sync/status", response_model=ApiResponse)
async def get_sync_status():
    return ApiResponse(data=attendance_sync_manager.get_status())


@router.get("/sync/settings", response_model=ApiResponse)
async def get_sync_settings():
    return ApiResponse(data=attendance_sync_manager.get_settings())


@router.put("/sync/settings", response_model=ApiResponse)
async def update_sync_settings(data: AttendanceSyncScheduleUpdate):
    try:
        hour, minute = [int(part) for part in data.time.split(":", 1)]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": "时间格式必须为 HH:mm"})

    settings = await attendance_sync_manager.update_settings(enabled=data.enabled, time_value=data.time, device_ips=data.device_ips)
    return ApiResponse(message="定时同步配置已更新", data=settings)
