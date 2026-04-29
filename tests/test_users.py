from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager

import pytest

from app.models import User
from app.schemas import UserCreate
from app.services.user import UserService
from app.core.zk_client import ZKClient


def device_user(**kwargs):
    defaults = {
        "uid": 1,
        "user_id": "EMP001",
        "name": "张三",
        "privilege": 0,
        "password": "",
        "group_id": "",
        "card": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_create_user(db_session):
    svc = UserService()
    user = await svc.create_user(
        db_session,
        UserCreate(name="张三", user_id="EMP001", device_ip="192.168.1.201"),
    )

    assert user.user_id == "EMP001"
    assert user.status == "active"
    assert user.sync_status == "pending"


@pytest.mark.asyncio
async def test_get_users_sorts_full_dataset_by_user_id_across_pages(db_session):
    db_session.add_all(
        [
            User(uid=1, user_id="600", name="U600", privilege=0, password="", group_id="", card=0, sync_status="synced"),
            User(uid=2, user_id="10", name="U010", privilege=0, password="", group_id="", card=0, sync_status="synced"),
            User(uid=3, user_id="2", name="U002", privilege=0, password="", group_id="", card=0, sync_status="synced"),
            User(uid=4, user_id="1", name="U001", privilege=0, password="", group_id="", card=0, sync_status="synced"),
        ]
    )
    await db_session.commit()

    svc = UserService()
    page1, total = await svc.get_users(db_session, page=1, page_size=2, sort_field="user_id", sort_order="asc")
    page2, _ = await svc.get_users(db_session, page=2, page_size=2, sort_field="user_id", sort_order="asc")

    assert total == 4
    assert [user.user_id for user in page1] == ["1", "2"]
    assert [user.user_id for user in page2] == ["10", "600"]


@pytest.mark.asyncio
async def test_disable_user_marks_status_disabled(db_session):
    db_session.add(User(uid=5, user_id="EMP005", name="离职用户", privilege=0, password="", group_id="", card=0, status="active", sync_status="synced"))
    await db_session.commit()

    svc = UserService()
    await svc.delete_user(db_session, "EMP005")
    updated = await svc.repository.get_by_user_id(db_session, "EMP005")

    assert updated.status == "disabled"
    assert updated.sync_status == "pending_disable"


@pytest.mark.asyncio
@patch("app.services.user.ZKClient.get_users")
async def test_preview_marks_missing_and_different(mock_get_users, db_session):
    db_session.add(User(uid=2, user_id="EMP002", name="李四", privilege=0, password="", group_id="", card=0, sync_status="synced"))
    await db_session.commit()

    mock_get_users.return_value = [
        device_user(uid=1, user_id="EMP001", name="张三"),
        device_user(uid=2, user_id="EMP002", name="李四-设备"),
    ]

    svc = UserService()
    result = await svc.sync_users_from_device(db_session, "192.168.1.201", "preview")

    assert result["missing_in_local_count"] == 1
    assert result["different_in_local_count"] == 1
    assert result["inserted_count"] == 0
    assert result["updated_count"] == 0


@pytest.mark.asyncio
@patch("app.services.user.ZKClient.get_users")
async def test_overwrite_local_updates_different_users(mock_get_users, db_session):
    db_session.add(User(uid=2, user_id="EMP002", name="李四", privilege=0, password="", group_id="", card=0, sync_status="failed"))
    await db_session.commit()

    mock_get_users.return_value = [device_user(uid=2, user_id="EMP002", name="李四-设备", card=1234)]

    svc = UserService()
    result = await svc.sync_users_from_device(db_session, "192.168.1.201", "overwrite_local")
    updated = await svc.repository.get_by_user_id(db_session, "EMP002")

    assert result["updated_count"] == 1
    assert updated.name == "李四-设备"
    assert updated.card == 1234
    assert updated.sync_status == "synced"


@pytest.mark.asyncio
@patch("app.services.user.ZKClient.get_users")
@patch("app.services.user.ZKClient.save_user")
async def test_sync_user_to_device_verifies_single_user_after_save(mock_save_user, mock_get_users, db_session):
    db_session.add(User(uid=9, user_id="EMP009", name="王五", privilege=14, password="1234", group_id="1", card=5678, sync_status="pending"))
    await db_session.commit()

    mock_save_user.return_value = True
    mock_get_users.return_value = [device_user(uid=9, user_id="EMP009", name="王五", privilege=14, password="1234", group_id="1", card=5678)]

    svc = UserService()
    result = await svc.sync_user_to_device(db_session, "192.168.1.201", "EMP009")
    updated = await svc.repository.get_by_user_id(db_session, "EMP009")

    assert result["status"] == "success"
    assert "校验通过" in result["message"]
    assert updated.sync_status == "synced"
    assert updated.sync_error is None
    mock_save_user.assert_called_once_with(9, "王五", 14, "1234", "1", "EMP009", 5678)


@pytest.mark.asyncio
@patch("app.services.user.ZKClient.get_users")
@patch("app.services.user.ZKClient.save_user")
async def test_sync_user_to_device_marks_failed_when_device_verification_mismatches(mock_save_user, mock_get_users, db_session):
    db_session.add(User(uid=10, user_id="EMP010", name="赵六", privilege=0, password="", group_id="", card=1, sync_status="pending"))
    await db_session.commit()

    mock_save_user.return_value = True
    mock_get_users.return_value = [device_user(uid=10, user_id="EMP010", name="赵六-旧", privilege=0, password="", group_id="", card=1)]

    svc = UserService()
    result = await svc.sync_user_to_device(db_session, "192.168.1.201", "EMP010")
    updated = await svc.repository.get_by_user_id(db_session, "EMP010")

    assert result["status"] == "error"
    assert "字段不一致" in result["message"]
    assert updated.sync_status == "failed"
    assert updated.sync_error == result["message"]


@pytest.mark.asyncio
@patch("app.services.user.ZKClient.get_users")
@patch("app.services.user.ZKClient.save_user")
async def test_disable_user_clears_password_and_card_on_device(mock_save_user, mock_get_users, db_session):
    db_session.add(User(uid=11, user_id="EMP011", name="停用用户", privilege=0, password="9988", group_id="2", card=7788, sync_status="pending_disable"))
    await db_session.commit()

    mock_save_user.return_value = True
    mock_get_users.return_value = [device_user(uid=11, user_id="EMP011", name="停用用户", privilege=0, password="", group_id="2", card=0)]

    svc = UserService()
    result = await svc.sync_user_to_device(db_session, "192.168.1.201", "EMP011")
    updated = await svc.repository.get_by_user_id(db_session, "EMP011")

    assert result["status"] == "success"
    assert "离职同步成功" in result["message"]
    assert updated.sync_status == "synced_disabled"
    mock_save_user.assert_called_once_with(11, "停用用户", 0, "", "2", "EMP011", 0)


def test_zk_client_save_user_uses_set_user_when_available():
    calls = []

    class FakeConn:
        def set_user(self, **kwargs):
            calls.append(kwargs)

    client = ZKClient("127.0.0.1")

    @contextmanager
    def fake_connect():
        yield FakeConn()

    client.connect = fake_connect

    assert client.save_user(1, "张三", 14, "1234", "1", "EMP001", 99) is True
    assert calls == [
        {
            "uid": 1,
            "name": "张三",
            "privilege": 14,
            "password": "1234",
            "group_id": "1",
            "user_id": "EMP001",
            "card": 99,
        }
    ]
