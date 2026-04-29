from fastapi import APIRouter, HTTPException

from app.deps import DBSessionDep
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.schemas import ApiResponse, RefreshTokenRequest, TokenRequest
from app.services.system_user import SystemUserService

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])
system_user_svc = SystemUserService()


@router.post("/login", response_model=ApiResponse)
@router.post("/token", response_model=ApiResponse, include_in_schema=False)
async def login(data: TokenRequest, db: DBSessionDep):
    try:
        await system_user_svc.ensure_default_admin(db)
        try:
            user = await system_user_svc.get_user(db, data.username)
        except ValueError:
            raise HTTPException(status_code=401, detail={"code": 4001, "message": "用户名或密码错误"})

        if not user.is_active:
            raise HTTPException(status_code=403, detail={"code": 4003, "message": "用户已禁用"})
        if not verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail={"code": 4001, "message": "用户名或密码错误"})

        return ApiResponse(
            data={
                "access_token": create_access_token({"sub": user.username, "role": user.role}),
                "refresh_token": create_refresh_token({"sub": user.username, "role": user.role}),
                "token_type": "bearer",
                "expires_in": 3600,
                "role": user.role,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})


@router.post("/refresh", response_model=ApiResponse)
async def refresh_token(data: RefreshTokenRequest, db: DBSessionDep):
    try:
        payload = decode_token(data.refresh_token)
        if payload is None or payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail={"code": 4003, "message": "刷新 Token 失败", "detail": "无效的刷新令牌"})
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail={"code": 4003, "message": "刷新 Token 失败"})

        try:
            user = await system_user_svc.get_user(db, username)
        except ValueError:
            raise HTTPException(status_code=401, detail={"code": 4003, "message": "刷新 Token 失败"})

        if not user.is_active:
            raise HTTPException(status_code=403, detail={"code": 4003, "message": "用户已禁用"})
        return ApiResponse(
            data={
                "access_token": create_access_token({"sub": user.username, "role": user.role}),
                "token_type": "bearer",
                "expires_in": 3600,
                "role": user.role,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 5000, "message": str(e)})
