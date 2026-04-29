from __future__ import annotations

import asyncio
import threading

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_client
from loguru import logger

from app.core.config import Settings, get_settings
from app.integrations.feishu.client import FeishuClientFactory
from app.integrations.feishu.handlers import FeishuEventHandlers


class FeishuLongConnectionManager:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: FeishuClientFactory | None = None,
        handlers: FeishuEventHandlers | None = None,
    ):
        self.settings = settings or get_settings()
        self.client_factory = client_factory or FeishuClientFactory(self.settings)
        self.handlers = handlers or FeishuEventHandlers()
        self._thread: threading.Thread | None = None
        self._ws_client: lark.ws.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def is_enabled(self) -> bool:
        return self.settings.FEISHU_ENABLE_LONG_CONNECTION

    def is_configured(self) -> bool:
        return self.client_factory.is_configured()

    def get_event_subscriptions(self) -> list[str]:
        return self.client_factory.get_event_subscriptions()

    def build_event_dispatcher(self) -> lark.EventDispatcherHandler:
        builder = lark.EventDispatcherHandler.builder(
            self.settings.FEISHU_ENCRYPT_KEY,
            self.settings.FEISHU_VERIFICATION_TOKEN,
            self.client_factory._resolve_log_level(),
        )

        for event_type in self.get_event_subscriptions():
            if event_type == "application.bot.menu_v6":
                builder.register_p2_application_bot_menu_v6(self.handlers.on_bot_menu_event)
                continue
            builder.register_p2_customized_event(event_type, self.handlers.on_customized_event)

        return builder.build()

    def start(self) -> None:
        if not self.is_enabled():
            logger.info("飞书长连接未启用，跳过启动")
            return
        if not self.is_configured():
            logger.warning("飞书长连接已启用，但 FEISHU_APP_ID / FEISHU_APP_SECRET 未配置，跳过启动")
            return
        if self._thread and self._thread.is_alive():
            logger.info("飞书长连接已在运行")
            return

        event_dispatcher = self.build_event_dispatcher()
        self._ws_client = self.client_factory.build_ws_client(event_dispatcher)
        self._thread = threading.Thread(
            target=self._run_forever,
            name="feishu-longconn",
            daemon=True,
        )
        self._thread.start()
        logger.info("飞书长连接启动线程已创建，订阅事件: {}", self.get_event_subscriptions())

    def stop(self) -> None:
        if self._ws_client is None or self._loop is None:
            return

        try:
            if self._loop.is_running():
                disconnect_future = asyncio.run_coroutine_threadsafe(
                    self._ws_client._disconnect(),
                    self._loop,
                )
                disconnect_future.result(timeout=5)
                self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception as exc:
            logger.warning("飞书长连接停止时发生异常: {}", exc)
        finally:
            self._ws_client = None
            self._loop = None
            self._thread = None

    def _run_forever(self) -> None:
        if self._ws_client is None:
            return

        loop = asyncio.new_event_loop()
        self._loop = loop
        lark_ws_client.loop = loop
        asyncio.set_event_loop(loop)

        try:
            self._ws_client.start()
        except RuntimeError as exc:
            logger.info("飞书长连接事件循环已停止: {}", exc)
        except Exception:
            logger.exception("飞书长连接运行失败")
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()


feishu_longconn_manager = FeishuLongConnectionManager()
