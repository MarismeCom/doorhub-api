from __future__ import annotations

import json

import lark_oapi as lark
from lark_oapi.core.enum import AccessTokenType, HttpMethod, LogLevel
from lark_oapi.core.model import BaseRequest
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from app.core.config import Settings, get_settings


class FeishuClientFactory:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.FEISHU_APP_ID and self.settings.FEISHU_APP_SECRET)

    def get_event_subscriptions(self) -> list[str]:
        raw = self.settings.FEISHU_EVENT_SUBSCRIPTIONS.strip()
        subscriptions = [item.strip() for item in raw.split(",") if item.strip()] if raw else []
        if self.settings.FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY and "application.bot.menu_v6" not in subscriptions:
            subscriptions.append("application.bot.menu_v6")
        return subscriptions

    def build_sdk_client(self) -> lark.Client:
        if not self.is_configured():
            raise ValueError("飞书应用未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")

        return (
            lark.Client.builder()
            .app_id(self.settings.FEISHU_APP_ID)
            .app_secret(self.settings.FEISHU_APP_SECRET)
            .log_level(self._resolve_log_level())
            .build()
        )

    def build_ws_client(self, event_handler: EventDispatcherHandler) -> lark.ws.Client:
        if not self.is_configured():
            raise ValueError("飞书应用未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")

        return lark.ws.Client(
            self.settings.FEISHU_APP_ID,
            self.settings.FEISHU_APP_SECRET,
            log_level=self._resolve_log_level(),
            event_handler=event_handler,
        )

    def send_text_message(self, open_id: str, text: str) -> None:
        client = self.build_sdk_client()
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(open_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(f"飞书消息发送失败: code={response.code}, msg={response.msg}")

    def get_user_display_name(
        self,
        *,
        open_id: str | None = None,
        user_id: str | None = None,
        union_id: str | None = None,
    ) -> str | None:
        if user_id:
            return self._get_user_display_name_by_basic_batch("user_id", user_id)
        if open_id:
            return self._get_user_display_name_by_basic_batch("open_id", open_id)
        if union_id:
            return self._get_user_display_name_by_basic_batch("union_id", union_id)
        return None

    def _get_user_display_name_by_basic_batch(self, user_id_type: str, user_value: str) -> str | None:
        client = self.build_sdk_client()
        request = BaseRequest()
        request.http_method = HttpMethod.POST
        request.uri = "/open-apis/contact/v3/users/basic_batch"
        request.token_types = {AccessTokenType.TENANT, AccessTokenType.USER}
        request.add_query("user_id_type", user_id_type)
        request.headers["Content-Type"] = "application/json; charset=utf-8"
        request.body = {"user_ids": [user_value]}

        response = client.request(request)
        if not response.success():
            raise RuntimeError(
                f"按 {user_id_type} 调用 basic_batch 查询飞书用户失败: code={response.code}, msg={response.msg}, log_id={response.get_log_id()}"
            )

        raw_content = response.raw.content if response.raw is not None else None
        if not raw_content:
            return None
        payload = json.loads(raw_content.decode("utf-8"))
        users = (payload.get("data") or {}).get("users") or []
        if not users:
            return None
        first_user = users[0] or {}
        return first_user.get("name") or first_user.get("en_name") or first_user.get("nickname")

    def _resolve_log_level(self) -> LogLevel:
        level_name = self.settings.FEISHU_LOG_LEVEL.upper()
        return getattr(LogLevel, level_name, LogLevel.INFO)
