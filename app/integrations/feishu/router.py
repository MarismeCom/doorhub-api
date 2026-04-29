from __future__ import annotations

from fastapi import APIRouter, Request, Response
from lark_oapi.core.model import RawRequest

from app.integrations.feishu.longconn import feishu_longconn_manager
from app.integrations.feishu.schemas import FeishuStatusSchema

router = APIRouter(prefix="/api/v1/feishu", tags=["飞书集成"])


@router.get("/status", response_model=FeishuStatusSchema)
async def get_feishu_status() -> FeishuStatusSchema:
    return FeishuStatusSchema(
        enabled=feishu_longconn_manager.is_enabled(),
        configured=feishu_longconn_manager.is_configured(),
        long_connection_enabled=feishu_longconn_manager.is_enabled(),
        event_subscriptions=feishu_longconn_manager.get_event_subscriptions(),
    )


@router.post("/callbacks/events")
async def handle_feishu_callback(request: Request) -> Response:
    body = await request.body()
    raw_request = RawRequest()
    raw_request.uri = str(request.url.path)
    raw_request.headers = dict(request.headers.items())
    raw_request.body = body

    dispatcher = feishu_longconn_manager.build_event_dispatcher()
    raw_response = dispatcher.do(raw_request)
    media_type = raw_response.headers.get("Content-Type", "application/json")

    return Response(
        content=raw_response.content or b"",
        status_code=raw_response.status_code or 200,
        media_type=media_type,
    )
