from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeishuEventHeaderSchema(BaseModel):
    event_id: str | None = None
    token: str | None = None
    create_time: str | None = None
    event_type: str | None = None
    tenant_key: str | None = None
    app_id: str | None = None


class FeishuCallbackSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_name: str | None = Field(default=None, alias="schema")
    challenge: str | None = None
    header: FeishuEventHeaderSchema | None = None
    event: dict[str, Any] | None = None
    encrypt: str | None = None


class FeishuStatusSchema(BaseModel):
    enabled: bool
    configured: bool
    long_connection_enabled: bool
    event_subscriptions: list[str]
