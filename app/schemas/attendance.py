from datetime import date, datetime
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


class AttendanceDailyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    user_name: Optional[str] = None
    attend_date: date
    plan_start: Optional[str] = None
    plan_end: Optional[str] = None
    actual_checkin: Optional[datetime] = None
    actual_checkout: Optional[datetime] = None
    late_minutes: int = 0
    early_minutes: int = 0
    work_minutes: int = 0
    overtime_minutes: int = 0
    status: int
    is_workday: bool = True
    calc_time: Optional[datetime] = None


class AttendanceDailyListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    records: list[AttendanceDailyResponse]


class AttendanceMonthlySummaryResponse(BaseModel):
    year_month: str
    workday_count: int = 0
    attendance_days: int = 0
    overtime_days: int = 0
    late_count: int = 0
    early_count: int = 0
    absence_count: int = 0
    missing_count: int = 0
    total_work_minutes: int = 0
    total_overtime_minutes: int = 0


class AttendanceRecalculateRequest(BaseModel):
    year_month: str
    user_id: Optional[str] = None


class AttendanceRuleSettingsResponse(BaseModel):
    plan_start: str = "10:00"
    plan_end: str = "18:00"


class AttendanceRuleSettingsUpdate(BaseModel):
    plan_start: str
    plan_end: str


class HolidayCacheRefreshRequest(BaseModel):
    year: int


class HolidayCacheScheduleUpdate(BaseModel):
    enabled: bool
    frequency: str = "daily"
    time: str
    weekday: int = 1


class HolidayCacheScheduleResponse(BaseModel):
    enabled: bool = False
    frequency: str = "daily"
    time: str = "03:00"
    weekday: int = 1
    next_run_at: str | None = None
    timezone: str | None = None


class HolidayCacheStatusResponse(BaseModel):
    running: bool = False
    stage: str = "idle"
    message: str = ""
    source: str | None = None
    year: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    refreshed_count: int = 0
