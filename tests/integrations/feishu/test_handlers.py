import pytest

from app.core.config import Settings
from app.integrations.feishu.handlers import FeishuEventHandlers, FeishuOperatorIdentity


class DummyHeader:
    def __init__(self, event_type: str):
        self.event_type = event_type


class DummyEvent:
    def __init__(self, event_type: str, payload: dict):
        self.header = DummyHeader(event_type)
        self.event = payload


class DummyOperatorId:
    def __init__(self, open_id: str = "ou_test", user_id: str = "u_test", union_id: str = "un_test"):
        self.open_id = open_id
        self.user_id = user_id
        self.union_id = union_id


class DummyOperator:
    def __init__(self, operator_name: str = "Tester"):
        self.operator_name = operator_name
        self.operator_id = DummyOperatorId()


class DummyBotMenuPayload:
    def __init__(self, event_key: str):
        self.event_key = event_key
        self.operator = DummyOperator()


class DummyBotMenuEvent:
    def __init__(self, event_key: str):
        self.event = DummyBotMenuPayload(event_key)


@pytest.mark.asyncio
async def test_handle_approval_updated_logs_payload(monkeypatch):
    handlers = FeishuEventHandlers()
    captured: list[dict] = []

    async def fake_handle(payload: dict):
        captured.append(payload)

    monkeypatch.setattr(handlers, "handle_approval_updated", fake_handle)

    await handlers.handle_customized_event(
        DummyEvent(
            "approval.approval.updated_v4",
            {"instance_code": "INS_001", "status": "APPROVED"},
        )
    )

    assert captured == [{"instance_code": "INS_001", "status": "APPROVED"}]


@pytest.mark.asyncio
async def test_handle_unknown_event_does_not_raise():
    handlers = FeishuEventHandlers()

    await handlers.handle_customized_event(
        DummyEvent(
            "contact.user.updated_v3",
            {"open_id": "ou_xxx"},
        )
    )


@pytest.mark.asyncio
async def test_handle_bot_menu_event_routes_door_open(monkeypatch):
    handlers = FeishuEventHandlers(
        settings=Settings(FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY="door_open")
    )
    captured: list[str] = []

    async def fake_handle(operator, event_key):
        captured.append(f"{operator.display_name}:{event_key}")

    monkeypatch.setattr(handlers, "handle_door_open_menu", fake_handle)

    await handlers.handle_bot_menu_event(DummyBotMenuEvent("door_open"))

    assert captured == ["Tester:door_open"]


@pytest.mark.asyncio
async def test_handle_unknown_bot_menu_event_does_not_raise():
    handlers = FeishuEventHandlers(
        settings=Settings(FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY="door_open")
    )

    await handlers.handle_bot_menu_event(DummyBotMenuEvent("other_action"))


def test_device_event_map_can_register_additional_event_keys():
    handlers = FeishuEventHandlers(
        settings=Settings(
            FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY="door_open",
            FEISHU_BOT_MENU_DEVICE_EVENT_MAP='{"door_open_hq":"192.168.1.201","door_open_lab":"192.168.1.202"}',
        )
    )

    assert handlers._is_door_open_event("door_open_hq") is True
    assert handlers._resolve_door_open_device_ip("door_open_lab") == "192.168.1.202"


def test_operator_whitelist_blocks_unlisted_user():
    handlers = FeishuEventHandlers(
        settings=Settings(
            FEISHU_BOT_MENU_ALLOWED_OPEN_IDS="ou_admin",
            FEISHU_BOT_MENU_ALLOWED_USER_IDS="u_admin",
        )
    )
    operator = FeishuOperatorIdentity(display_name="Tester", open_id="ou_test", user_id="u_test")

    assert handlers._is_operator_allowed(operator) is False


def test_operator_whitelist_allows_listed_open_id():
    handlers = FeishuEventHandlers(
        settings=Settings(
            FEISHU_BOT_MENU_ALLOWED_OPEN_IDS="ou_test",
        )
    )
    operator = FeishuOperatorIdentity(display_name="Tester", open_id="ou_test", user_id="u_test")

    assert handlers._is_operator_allowed(operator) is True


@pytest.mark.asyncio
async def test_extract_operator_identity_prefers_event_name():
    handlers = FeishuEventHandlers()

    operator = await handlers._extract_operator_identity(DummyBotMenuPayload("door_open"))

    assert operator.display_name == "Tester"
