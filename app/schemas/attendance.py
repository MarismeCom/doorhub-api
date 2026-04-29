from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    user_name: Optional[str] = None
    uid: Optional[int]
    timestamp: datetime
    status: int
    punch: int
    device_sn: Optional[str]


class AttendanceListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    records: list[AttendanceResponse]


class SyncRequest(BaseModel):
    device_ip: str
    incremental: bool = True


class SyncResponse(BaseModel):
    fetched_count: int = 0
    synced_count: int
    duplicate_count: int = 0
    skipped_invalid_count: int = 0
    device_ip: str
    synced_at: datetime


class AttendanceSyncScheduleUpdate(BaseModel):
    enabled: bool
    time: str
    device_ips: list[str] = []


class AttendanceSyncStatusResponse(BaseModel):
    running: bool
    progress: int = 0
    stage: str = "idle"
    message: str = ""
    source: str | None = None
    device_ip: str | None = None
    incremental: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    fetched_count: int = 0
    synced_count: int = 0
    duplicate_count: int = 0
    skipped_invalid_count: int = 0


class AttendanceSyncScheduleResponse(BaseModel):
    enabled: bool = False
    time: str = "23:00"
    device_ips: list[str] = []
    next_run_at: str | None = None


class HealthCheckResponse(BaseModel):
    status: str
    checks: dict
    uptime_seconds: int
