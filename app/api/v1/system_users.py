from fastapi import APIRouter, HTTPException

from app.deps import AdminUserDep, CurrentUserDep, DBSessionDep
from app.schemas import (
    ApiResponse,
    ApiSecretCreate,
    ApiSecretCreateResponse,
    ApiSecretResponse,
    ChangePasswordRequest,
    CurrentUserResponse,
    SystemUserCreate,
    SystemUserPasswordReset,
    SystemUserResponse,
    SystemUserUpdate,
)
from app.services.system_user import SystemUserService

router = APIRouter(prefix="/api/v1/system-users", tags=["系统用户管理"])
system_user_svc = SystemUserService()


@router.get("/me", response_model=ApiResponse)
async def get_me(current_user: CurrentUserDep):
    return ApiResponse(data=CurrentUserResponse(username=current_user.username, role=current_user.role, is_active=current_user.is_active).model_dump())


@router.post("", response_model=ApiResponse)
async def create_system_user(data: SystemUserCreate, db: DBSessionDep, current_user: AdminUserDep):
    try:
        user = await system_user_svc.create_user(db, data)
        return ApiResponse(message="系统用户创建成功", data=SystemUserResponse.model_validate(user).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})


@router.get("", response_model=ApiResponse)
async def list_system_users(db: DBSessionDep, current_user: AdminUserDep):
    users = await system_user_svc.list_users(db)
    return ApiResponse(data={"total": len(users), "users": [SystemUserResponse.model_validate(user).model_dump() for user in users]})


@router.post("/me/change-password", response_model=ApiResponse)
async def change_password(data: ChangePasswordRequest, db: DBSessionDep, current_user: CurrentUserDep):
    try:
        await system_user_svc.change_password(db, current_user, data)
        return ApiResponse(message="密码修改成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})


@router.get("/{username}", response_model=ApiResponse)
async def get_system_user(username: str, db: DBSessionDep, current_user: AdminUserDep):
    try:
        user = await system_user_svc.get_user(db, username)
        return ApiResponse(data=SystemUserResponse.model_validate(user).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})


@router.patch("/{username}", response_model=ApiResponse)
async def update_system_user(username: str, data: SystemUserUpdate, db: DBSessionDep, current_user: AdminUserDep):
    try:
        user = await system_user_svc.update_user(db, username, data)
        return ApiResponse(message="系统用户更新成功", data=SystemUserResponse.model_validate(user).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})


@router.post("/{username}/reset-password", response_model=ApiResponse)
async def reset_system_user_password(username: str, data: SystemUserPasswordReset, db: DBSessionDep, current_user: AdminUserDep):
    try:
        await system_user_svc.reset_password(db, username, data)
        return ApiResponse(message="密码重置成功")
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})


@router.get("/{username}/api-secrets", response_model=ApiResponse)
async def list_api_secrets(username: str, db: DBSessionDep, current_user: AdminUserDep):
    try:
        secrets = await system_user_svc.list_api_secrets(db, username)
        return ApiResponse(data={"total": len(secrets), "items": [ApiSecretResponse.model_validate(item).model_dump() for item in secrets]})
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})


@router.post("/{username}/api-secrets", response_model=ApiResponse)
async def create_api_secret(username: str, data: ApiSecretCreate, db: DBSessionDep, current_user: AdminUserDep):
    try:
        secret, raw_secret = await system_user_svc.create_api_secret(db, username, data)
        return ApiResponse(
            message="API Secret 创建成功，请立即保存明文 Secret",
            data=ApiSecretCreateResponse(
                secret=raw_secret,
                secret_meta=ApiSecretResponse.model_validate(secret),
            ).model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 2002, "message": str(e)})


@router.delete("/{username}/api-secrets/{secret_id}", response_model=ApiResponse)
async def revoke_api_secret(username: str, secret_id: int, db: DBSessionDep, current_user: AdminUserDep):
    try:
        secret = await system_user_svc.revoke_api_secret(db, username, secret_id)
        return ApiResponse(message="API Secret 已撤销", data=ApiSecretResponse.model_validate(secret).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": 2001, "message": str(e)})
