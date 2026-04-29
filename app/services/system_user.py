import secrets
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ensure_bootstrap_admin, get_password_hash, verify_password
from app.models import ApiSecret, SystemUser
from app.repositories.api_secret import ApiSecretRepository
from app.repositories.system_user import SystemUserRepository
from app.schemas import (
    ApiSecretCreate,
    ChangePasswordRequest,
    SystemUserCreate,
    SystemUserPasswordReset,
    SystemUserUpdate,
)


class SystemUserService:
    MAX_API_SECRETS_PER_USER = 3

    def __init__(self):
        self.repository = SystemUserRepository()
        self.api_secret_repository = ApiSecretRepository()

    async def ensure_default_admin(self, db: AsyncSession) -> SystemUser:
        return await ensure_bootstrap_admin(db)

    async def list_users(self, db: AsyncSession) -> list[SystemUser]:
        await self.ensure_default_admin(db)
        return await self.repository.list_all(db)

    async def get_user(self, db: AsyncSession, username: str) -> SystemUser:
        user = await self.repository.get_by_username(db, username)
        if user is None:
            raise ValueError(f"系统用户 {username} 不存在")
        return user

    async def create_user(self, db: AsyncSession, data: SystemUserCreate) -> SystemUser:
        existing = await self.repository.get_by_username(db, data.username)
        if existing:
            raise ValueError(f"系统用户 {data.username} 已存在")

        user = SystemUser(
            username=data.username,
            password_hash=get_password_hash(data.password),
            role=data.role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def update_user(self, db: AsyncSession, username: str, data: SystemUserUpdate) -> SystemUser:
        user = await self.get_user(db, username)
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        await db.commit()
        await db.refresh(user)
        return user

    async def reset_password(self, db: AsyncSession, username: str, data: SystemUserPasswordReset) -> SystemUser:
        user = await self.get_user(db, username)
        user.password_hash = get_password_hash(data.new_password)
        await db.commit()
        await db.refresh(user)
        return user

    async def change_password(
        self,
        db: AsyncSession,
        current_user: SystemUser,
        data: ChangePasswordRequest,
    ) -> SystemUser:
        if not verify_password(data.old_password, current_user.password_hash):
            raise ValueError("旧密码错误")
        current_user.password_hash = get_password_hash(data.new_password)
        await db.commit()
        await db.refresh(current_user)
        return current_user

    async def list_api_secrets(self, db: AsyncSession, username: str) -> list[ApiSecret]:
        user = await self.get_user(db, username)
        return await self.api_secret_repository.list_by_user(db, user.id)

    async def create_api_secret(self, db: AsyncSession, username: str, data: ApiSecretCreate) -> tuple[ApiSecret, str]:
        user = await self.get_user(db, username)
        if data.expires_at is not None:
            expires_at = data.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("过期时间必须晚于当前时间")
        else:
            expires_at = None

        active_count = await self.api_secret_repository.count_active_by_user(db, user.id)
        if active_count >= self.MAX_API_SECRETS_PER_USER:
            raise ValueError(f"每个系统用户最多只支持 {self.MAX_API_SECRETS_PER_USER} 个有效 API Secret")

        raw_secret = f"sk_{secrets.token_urlsafe(24)}"
        secret = ApiSecret(
            system_user_id=user.id,
            name=data.name,
            secret_prefix=raw_secret[:12],
            secret_hash=get_password_hash(raw_secret),
            expires_at=expires_at,
        )
        db.add(secret)
        await db.commit()
        await db.refresh(secret)
        return secret, raw_secret

    async def revoke_api_secret(self, db: AsyncSession, username: str, secret_id: int) -> ApiSecret:
        user = await self.get_user(db, username)
        secret = await self.api_secret_repository.get_by_id_for_user(db, secret_id, user.id)
        if secret is None:
            raise ValueError("API Secret 不存在")
        if secret.revoked_at is None:
            secret.revoked_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(secret)
        return secret
