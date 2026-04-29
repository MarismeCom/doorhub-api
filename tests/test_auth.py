from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import BOOTSTRAP_ADMIN_USERNAME, authenticate_api_secret, create_access_token, decode_token
from app.schemas import ApiSecretCreate, ChangePasswordRequest, SystemUserCreate, SystemUserUpdate
from app.services.system_user import SystemUserService


@pytest.mark.asyncio
async def test_ensure_default_admin(db_session):
    svc = SystemUserService()
    admin = await svc.ensure_default_admin(db_session)

    assert admin.username == BOOTSTRAP_ADMIN_USERNAME
    assert admin.role == "admin"
    assert admin.is_active is True


@pytest.mark.asyncio
async def test_create_and_update_system_user(db_session):
    svc = SystemUserService()
    await svc.ensure_default_admin(db_session)

    user = await svc.create_user(
        db_session,
        SystemUserCreate(username="operator", password="secret123", role="user"),
    )
    updated = await svc.update_user(
        db_session,
        user.username,
        SystemUserUpdate(role="admin", is_active=False),
    )

    assert updated.role == "admin"
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_change_password(db_session):
    svc = SystemUserService()
    user = await svc.create_user(
        db_session,
        SystemUserCreate(username="alice", password="oldpass1", role="user"),
    )

    await svc.change_password(
        db_session,
        user,
        ChangePasswordRequest(old_password="oldpass1", new_password="newpass1"),
    )

    refreshed = await svc.get_user(db_session, "alice")
    assert refreshed.password_hash != "newpass1"


def test_access_token_can_carry_role():
    token = create_access_token({"sub": "admin", "role": "admin"})
    payload = decode_token(token)

    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_create_api_secret_limits_to_three_active_items(db_session):
    svc = SystemUserService()
    await svc.create_user(
        db_session,
        SystemUserCreate(username="secret-user", password="pass123", role="user"),
    )
    future = datetime.now(timezone.utc) + timedelta(days=1)

    for idx in range(3):
        secret, raw_secret = await svc.create_api_secret(
            db_session,
            "secret-user",
            ApiSecretCreate(name=f"secret-{idx}", expires_at=future),
        )
        assert secret.name == f"secret-{idx}"
        assert raw_secret.startswith("sk_")

    with pytest.raises(ValueError, match="最多只支持 3 个有效 API Secret"):
        await svc.create_api_secret(
            db_session,
            "secret-user",
            ApiSecretCreate(name="secret-3", expires_at=future),
        )


@pytest.mark.asyncio
async def test_api_secret_can_authenticate_system_user(db_session):
    svc = SystemUserService()
    user = await svc.create_user(
        db_session,
        SystemUserCreate(username="api-user", password="pass123", role="admin"),
    )
    _, raw_secret = await svc.create_api_secret(
        db_session,
        "api-user",
        ApiSecretCreate(name="integration", expires_at=datetime.now(timezone.utc) + timedelta(days=1)),
    )

    authenticated = await authenticate_api_secret(db_session, raw_secret)

    assert authenticated is not None
    assert authenticated.id == user.id
    assert authenticated.username == "api-user"
