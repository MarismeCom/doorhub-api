import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1 import (
    attendance_records_router,
    attendances_router,
    auth_router,
    dashboard_router,
    devices_router,
    door_router,
    feishu_router,
    system_users_router,
    users_router,
)
from app.core.attendance_sync_manager import attendance_sync_manager
from app.core.config import get_settings
from app.core.holiday_cache_manager import holiday_cache_manager
from app.core.runtime import set_app_loop
from app.core.security import ensure_bootstrap_admin
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.exceptions import register_exception_handlers
from app.integrations.feishu.longconn import feishu_longconn_manager

settings = get_settings()
START_TIME = time.time()

logger.add(
    "logs/app.log",
    rotation="500 MB",
    retention="10 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("门禁系统启动...")
    set_app_loop(asyncio.get_running_loop())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        await ensure_bootstrap_admin(db)

    attendance_sync_manager.start()
    holiday_cache_manager.start()
    feishu_longconn_manager.start()

    yield
    feishu_longconn_manager.stop()
    holiday_cache_manager.stop()
    attendance_sync_manager.stop()
    set_app_loop(None)
    logger.info("门禁系统关闭...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="门禁管理系统 API",
        description="基于 ZKTeco 的门禁管理系统",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(system_users_router)
    app.include_router(users_router)
    app.include_router(attendances_router)
    app.include_router(attendance_records_router)
    app.include_router(door_router)
    app.include_router(devices_router)
    app.include_router(feishu_router)

    @app.get("/health")
    async def health_check():
        uptime = int(time.time() - START_TIME)
        return {
            "status": "healthy",
            "uptime_seconds": uptime,
            "timestamp": datetime.now().isoformat(),
        }

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s")
        return response

    return app


app = create_app()
