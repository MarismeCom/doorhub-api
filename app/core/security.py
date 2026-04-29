from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models import ApiSecret, SystemUser

settings = get_settings()
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

BOOTSTRAP_ADMIN_USERNAME = "admin"
BOOTSTRAP_ADMIN_PASSWORD = "admin"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


async def ensure_bootstrap_admin(db: AsyncSession) -> SystemUser:
    result = await db.execute(select(SystemUser).where(SystemUser.username == BOOTSTRAP_ADMIN_USERNAME))
    admin = result.scalar_one_or_none()
    if admin:
        if admin.role != "admin":
            admin.role = "admin"
        if not admin.is_active:
            admin.is_active = True
        await db.commit()
        await db.refresh(admin)
        return admin

    admin = SystemUser(
        username=BOOTSTRAP_ADMIN_USERNAME,
        password_hash=get_password_hash(BOOTSTRAP_ADMIN_PASSWORD),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-Secret"),
    db: AsyncSession = Depends(get_db),
) -> SystemUser:
    secret_candidate = x_api_secret
    if credentials is not None and credentials.scheme.lower() == "bearer":
        bearer_value = credentials.credentials
        if bearer_value.startswith("sk_"):
            secret_candidate = bearer_value

    if secret_candidate:
        user = await authenticate_api_secret(db, secret_candidate)
        if user is not None:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 4001, "message": "未授权", "detail": "API Secret 无效或已过期"},
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 4001, "message": "未授权", "detail": "缺少认证凭证"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 4001, "message": "未授权", "detail": "Token 无效"},
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 4001, "message": "未授权", "detail": "Token 载荷无效"},
        )

    result = await db.execute(select(SystemUser).where(SystemUser.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": "用户不存在或已禁用"},
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_secret: Optional[str] = Header(default=None, alias="X-API-Secret"),
    db: AsyncSession = Depends(get_db),
) -> Optional[SystemUser]:
    if credentials is None and not x_api_secret:
        return None
    try:
        return await get_current_user(credentials=credentials, x_api_secret=x_api_secret, db=db)
    except HTTPException:
        return None


async def require_admin(current_user: SystemUser = Depends(get_current_user)) -> SystemUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 4003, "message": "权限不足，需要管理员角色"},
        )
    return current_user


async def authenticate_api_secret(db: AsyncSession, raw_secret: str) -> Optional[SystemUser]:
    prefix = raw_secret[:12]
    result = await db.execute(
        select(ApiSecret, SystemUser)
        .join(SystemUser, ApiSecret.system_user_id == SystemUser.id)
        .where(
            ApiSecret.secret_prefix == prefix,
            ApiSecret.revoked_at.is_(None),
            or_(ApiSecret.expires_at.is_(None), ApiSecret.expires_at > datetime.now(timezone.utc)),
        )
    )
    rows = result.all()
    for api_secret, user in rows:
        if verify_password(raw_secret, api_secret.secret_hash):
            if not user.is_active:
                return None
            api_secret.last_used_at = datetime.now(timezone.utc)
            await db.commit()
            return user
    return None
