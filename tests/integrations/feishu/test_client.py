import json

from app.core.config import Settings
from app.integrations.feishu.client import FeishuClientFactory


def test_feishu_client_factory_reports_configuration():
    settings = Settings(
        FEISHU_APP_ID="cli_xxx",
        FEISHU_APP_SECRET="secret_xxx",
        FEISHU_EVENT_SUBSCRIPTIONS="approval.approval.updated_v4, contact.user.updated_v3",
        FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY="door_open",
    )
    factory = FeishuClientFactory(settings)

    assert factory.is_configured() is True
    assert factory.get_event_subscriptions() == [
        "approval.approval.updated_v4",
        "contact.user.updated_v3",
        "application.bot.menu_v6",
    ]


def test_feishu_client_factory_requires_credentials():
    settings = Settings(
        FEISHU_APP_ID="",
        FEISHU_APP_SECRET="",
        FEISHU_EVENT_SUBSCRIPTIONS="",
        FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY="",
    )
    factory = FeishuClientFactory(settings)

    assert factory.is_configured() is False
    assert factory.get_event_subscriptions() == []


def test_get_user_display_name_uses_basic_batch(monkeypatch):
    settings = Settings(
        FEISHU_APP_ID="cli_xxx",
        FEISHU_APP_SECRET="secret_xxx",
        FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY="door_open",
    )
    factory = FeishuClientFactory(settings)

    class FakeRaw:
        content = json.dumps(
            {
                "code": 0,
                "msg": "success",
                "data": {
                    "users": [
                        {
                            "user_id": "db2f58e5",
                            "name": "张三",
                        }
                    ]
                },
            }
        ).encode("utf-8")

    class FakeResponse:
        code = 0
        msg = "success"
        raw = FakeRaw()

        def success(self):
            return True

        def get_log_id(self):
            return "log_xxx"

    class FakeClient:
        def request(self, request):
            assert request.uri == "/open-apis/contact/v3/users/basic_batch"
            assert ("user_id_type", "user_id") in request.queries
            assert request.body == {"user_ids": ["db2f58e5"]}
            return FakeResponse()

    monkeypatch.setattr(factory, "build_sdk_client", lambda: FakeClient())

    assert factory.get_user_display_name(user_id="db2f58e5", open_id="ou_test") == "张三"
