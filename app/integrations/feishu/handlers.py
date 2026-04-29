from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from loguru import logger
from lark_oapi.api.application.v6 import P2ApplicationBotMenuV6

from app.core.config import Settings, get_settings
from app.core.runtime import get_app_loop
from app.db.session import SessionLocal
from app.integrations.feishu.client import FeishuClientFactory
from app.schemas.device import UnlockRequest
from app.services.attendance import AttendanceService
from app.services.door import DoorService
from app.services.user import UserService


@dataclass
class FeishuOperatorIdentity:
    display_name: str
    open_id: str | None = None
    user_id: str | None = None
    union_id: str | None = None


class FeishuEventHandlers:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: FeishuClientFactory | None = None,
        user_service: UserService | None = None,
        attendance_service: AttendanceService | None = None,
        door_service: DoorService | None = None,
    ):
        self.settings = settings or get_settings()
        self.client_factory = client_factory or FeishuClientFactory(self.settings)
        self.user_service = user_service or UserService()
        self.attendance_service = attendance_service or AttendanceService()
        self.door_service = door_service or DoorService()

    def on_customized_event(self, event: Any) -> None:
        self._dispatch(self.handle_customized_event(event))

    def on_bot_menu_event(self, event: P2ApplicationBotMenuV6) -> None:
        self._dispatch(self.handle_bot_menu_event(event))

    async def handle_customized_event(self, event: Any) -> None:
        event_type = self._extract_event_type(event)
        payload = getattr(event, "event", {}) or {}

        if event_type == "approval.approval.updated_v4":
            await self.handle_approval_updated(payload)
            return

        logger.info("收到未专门实现的飞书事件: type={}, payload={}", event_type, payload)

    async def handle_bot_menu_event(self, event: P2ApplicationBotMenuV6) -> None:
        payload = event.event
        if payload is None:
            logger.warning("收到空的飞书机器人菜单事件")
            return

        event_key = payload.event_key or ""
        operator = await self._extract_operator_identity(payload)

        if self._is_door_open_event(event_key):
            await self.handle_door_open_menu(operator, event_key)
            return

        logger.info(
            "收到未处理的飞书机器人菜单事件: event_key={}, operator={}",
            event_key,
            operator.display_name,
        )

    async def handle_approval_updated(self, payload: dict[str, Any]) -> None:
        instance_code = payload.get("instance_code")
        status = payload.get("status")
        logger.info(
            "收到飞书审批事件: instance_code={}, status={}, payload={}",
            instance_code,
            status,
            payload,
        )

    async def handle_door_open_menu(self, operator: FeishuOperatorIdentity, event_key: str) -> None:
        if not self._is_operator_allowed(operator):
            logger.warning(
                "飞书机器人菜单开门被拒绝: operator={}, event_key={}",
                operator.display_name,
                event_key,
            )
            await self._notify_operator(operator, "你没有开门权限，请联系管理员。")
            return

        device_ip = self._resolve_door_open_device_ip(event_key)
        request = UnlockRequest(
            device_ip=device_ip,
            unlock_seconds=self.settings.FEISHU_BOT_MENU_DOOR_OPEN_SECONDS,
            remark="Triggered by Feishu bot menu",
        )

        try:
            async with SessionLocal() as db:
                log = await self.door_service.open(
                    db,
                    device_ip,
                    operator.display_name,
                    request,
                )
            logger.info(
                "飞书机器人菜单开门成功: operator={}, device_ip={}, log_id={}",
                operator.display_name,
                device_ip,
                log.id,
            )
            await self._notify_operator(
                operator,
                f"开门成功，设备 {device_ip} 已执行开门 {request.unlock_seconds} 秒。",
            )
        except Exception as exc:
            logger.exception(
                "飞书机器人菜单开门失败: operator={}, device_ip={}, err={}",
                operator.display_name,
                device_ip,
                exc,
            )
            await self._notify_operator(
                operator,
                f"开门失败，设备 {device_ip} 执行异常：{exc}",
            )

    async def _notify_operator(self, operator: FeishuOperatorIdentity, text: str) -> None:
        if not self.settings.FEISHU_BOT_MENU_NOTIFY_OPERATOR:
            return
        if not operator.open_id:
            logger.warning("飞书机器人菜单通知被跳过，缺少 open_id: operator={}", operator.display_name)
            return

        try:
            await asyncio.to_thread(self.client_factory.send_text_message, operator.open_id, text)
        except Exception as exc:
            logger.warning("飞书机器人菜单通知发送失败: operator={}, err={}", operator.display_name, exc)

    def _resolve_door_open_device_ip(self, event_key: str) -> str:
        event_map = self._get_device_event_map()
        if event_key in event_map:
            return event_map[event_key]
        if self.settings.FEISHU_BOT_MENU_DOOR_OPEN_DEVICE_IP:
            return self.settings.FEISHU_BOT_MENU_DOOR_OPEN_DEVICE_IP

        candidates = [item.strip() for item in self.settings.ZK_DEVICE_IPS.split(",") if item.strip()]
        if not candidates:
            raise ValueError("未配置可用于飞书菜单开门的门禁设备 IP")
        return candidates[0]

    def _get_device_event_map(self) -> dict[str, str]:
        raw = self.settings.FEISHU_BOT_MENU_DEVICE_EVENT_MAP.strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("FEISHU_BOT_MENU_DEVICE_EVENT_MAP 不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("FEISHU_BOT_MENU_DEVICE_EVENT_MAP 必须是 JSON object")
        return {
            str(key).strip(): str(value).strip()
            for key, value in data.items()
            if str(key).strip() and str(value).strip()
        }

    def _is_operator_allowed(self, operator: FeishuOperatorIdentity) -> bool:
        allowed_open_ids = self._parse_csv(self.settings.FEISHU_BOT_MENU_ALLOWED_OPEN_IDS)
        allowed_user_ids = self._parse_csv(self.settings.FEISHU_BOT_MENU_ALLOWED_USER_IDS)
        if not allowed_open_ids and not allowed_user_ids:
            return True
        if operator.open_id and operator.open_id in allowed_open_ids:
            return True
        if operator.user_id and operator.user_id in allowed_user_ids:
            return True
        return False

    def _is_door_open_event(self, event_key: str) -> bool:
        if event_key == self.settings.FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY:
            return True
        return event_key in self._get_device_event_map()

    def _dispatch(self, coro: asyncio.Future | asyncio.coroutines) -> None:
        target_loop = get_app_loop()
        current_loop = asyncio.get_running_loop()

        if target_loop is None or target_loop is current_loop:
            task = current_loop.create_task(coro)
            task.add_done_callback(self._log_task_exception)
            return

        future = asyncio.run_coroutine_threadsafe(coro, target_loop)
        future.add_done_callback(self._log_threadsafe_future_exception)

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("飞书事件异步任务执行失败")

    @staticmethod
    def _log_threadsafe_future_exception(future) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("飞书事件跨线程调度执行失败")

    @staticmethod
    def _parse_csv(value: str) -> set[str]:
        return {item.strip() for item in value.split(",") if item.strip()}

    async def _extract_operator_identity(self, payload: Any) -> FeishuOperatorIdentity:
        operator = getattr(payload, "operator", None)
        operator_id = getattr(operator, "operator_id", None)
        display_name = getattr(operator, "operator_name", None)
        open_id = getattr(operator_id, "open_id", None)
        user_id = getattr(operator_id, "user_id", None)

        if not display_name and self.client_factory.is_configured():
            union_id = getattr(operator_id, "union_id", None)
            try:
                display_name = await asyncio.to_thread(
                    self.client_factory.get_user_display_name,
                    open_id=open_id,
                    user_id=user_id,
                    union_id=union_id,
                )
            except Exception as exc:
                logger.warning(
                    "飞书用户姓名补查失败: open_id={}, user_id={}, union_id={}, err={}",
                    open_id,
                    user_id,
                    union_id,
                    exc,
                )

        return FeishuOperatorIdentity(
            display_name=display_name or user_id or open_id or "feishu_bot_menu",
            open_id=open_id,
            user_id=user_id,
            union_id=getattr(operator_id, "union_id", None),
        )

    @staticmethod
    def _extract_event_type(event: Any) -> str:
        header = getattr(event, "header", None)
        if header is not None and getattr(header, "event_type", None):
            return header.event_type
        return getattr(event, "type", "unknown")
