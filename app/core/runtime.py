from __future__ import annotations

import asyncio

_app_loop: asyncio.AbstractEventLoop | None = None


def set_app_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _app_loop
    _app_loop = loop


def get_app_loop() -> asyncio.AbstractEventLoop | None:
    return _app_loop
