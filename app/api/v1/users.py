from fastapi import APIRouter, HTTPException, Query

from app.deps import CurrentUserDep, DBSessionDep
from app.schemas import ApiResponse, UserCreate, UserResponse, UserSyncFromDeviceRequest, UserUpdate
from app.services.user import UserService

router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])
user_svc = UserService()


@router.get("", response_model=ApiResponse)
async def get_users(
    db: DBSessionDep,
    keyword: str = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_field: str = None,
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
):
    try:
        users, total = await user_svc.get_users(
            db,
            keyword=keyword,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
        )
        return ApiResponse(
            data={
                "total": total,
                "page": page,
                "page_size": page_size,
                "sort_field": sort_field,
                "sort_order": sort_order,
                "users": [UserResponse.model_validate(u) for u in users],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.post("", status_code=201, response_model=ApiResponse)
async def create_user(data: UserCreate, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        user = await user_svc.create_user(db, data, data.device_ip)
        return ApiResponse(message="用户创建成功（待同步）", data={"uid": user.uid, "user_id": user.user_id, "name": user.name, "sync_status": user.sync_status})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.put("/{user_id}", response_model=ApiResponse)
async def update_user(user_id: str, data: UserUpdate, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        user = await user_svc.update_user(db, user_id, data)
        return ApiResponse(
            message="用户更新成功（待同步）",
            data={"uid": user.uid, "user_id": user.user_id, "name": user.name, "sync_status": user.sync_status},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.delete("/{user_id}", response_model=ApiResponse)
async def delete_user(user_id: str, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        await user_svc.delete_user(db, user_id=user_id)
        return ApiResponse(message="用户离职设置成功（待同步）")
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.post("/{user_id}/sync", response_model=ApiResponse)
async def sync_user_to_device(user_id: str, device_ip: str, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        result = await user_svc.sync_user_to_device(db, device_ip, user_id)
        return ApiResponse(message=result["message"], data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5002, "message": str(e)})


@router.post("/sync/batch", response_model=ApiResponse)
async def sync_pending_users(device_ip: str, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        result = await user_svc.sync_pending_users(db, device_ip)
        return ApiResponse(message=f"批量同步完成: 成功 {result['success']}, 失败 {result['failed']}", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5002, "message": str(e)})


@router.post("/sync/from-device", response_model=ApiResponse)
async def sync_users_from_device(data: UserSyncFromDeviceRequest, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        result = await user_svc.sync_users_from_device(db, data.device_ip, data.mode)
        message_map = {"preview": "设备用户预览完成", "write_missing": "设备缺失用户已写入本地", "overwrite_local": "设备用户已覆盖同步到本地"}
        return ApiResponse(message=message_map[data.mode], data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5002, "message": str(e)})


@router.get("/sync/status", response_model=ApiResponse)
async def get_sync_status(db: DBSessionDep, user_id: str = None):
    try:
        return ApiResponse(data=await user_svc.get_sync_status(db, user_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})
