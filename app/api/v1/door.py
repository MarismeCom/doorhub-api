from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.deps import CurrentUserDep, DBSessionDep
from app.schemas import ApiResponse, DoorLogResponse, UnlockRequest
from app.services.door import DoorService

router = APIRouter(prefix="/api/v1/door", tags=["门禁控制"])
door_svc = DoorService()


@router.post("/open", response_model=ApiResponse)
@router.post("/unlock", response_model=ApiResponse, include_in_schema=False)
async def open_door(data: UnlockRequest, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        log = await door_svc.open(db, data.device_ip, current_user.username, data)
        return ApiResponse(message="开门成功", data={"log_id": log.id, "device_ip": log.device_ip, "operator": log.operator, "result": log.result})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"code": 3001, "message": str(e)})


@router.post("/close", response_model=ApiResponse)
async def close_door(data: UnlockRequest, db: DBSessionDep, current_user: CurrentUserDep):
    return ApiResponse(code=0, message="设备不支持主动关门，门锁将按控制器策略自动闭合", data={"device_ip": data.device_ip})


@router.get("/logs", response_model=ApiResponse)
async def get_door_logs(
    db: DBSessionDep,
    device_ip: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    try:
        logs, total = await door_svc.get_logs(db, device_ip, start_date, end_date, page, page_size)
        return ApiResponse(data={"total": total, "page": page, "page_size": page_size, "logs": [DoorLogResponse.model_validate(l) for l in logs]})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})
