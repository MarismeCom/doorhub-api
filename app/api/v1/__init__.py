from app.api.v1.attendance_records import router as attendance_records_router
from app.api.v1.attendances import router as attendances_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.devices import router as devices_router
from app.api.v1.door import router as door_router
from app.api.v1.feishu import router as feishu_router
from app.api.v1.system_users import router as system_users_router
from app.api.v1.users import router as users_router

__all__ = [
    "attendance_records_router",
    "attendances_router",
    "auth_router",
    "dashboard_router",
    "devices_router",
    "door_router",
    "feishu_router",
    "system_users_router",
    "users_router",
]
