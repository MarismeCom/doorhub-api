from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[dict] = None
    request_id: Optional[str] = None


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    user_id: str = Field(..., min_length=1, max_length=32)
    privilege: int = Field(default=0, ge=0, le=14)
    password: str = Field(default="", max_length=32)
    group_id: str = Field(default="", max_length=8)
    card: int = Field(default=0, ge=0)
    device_ip: str


class UserUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    privilege: int = Field(default=0, ge=0, le=14)
    password: str = Field(default="", max_length=32)
    group_id: str = Field(default="", max_length=8)
    card: int = Field(default=0, ge=0)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: int
    user_id: str
    name: str
    privilege: int
    password: str
    group_id: str
    card: int
    status: str = "active"
    sync_status: str = "pending"
    created_at: datetime


class SyncStatusResponse(BaseModel):
    user_id: str
    sync_status: str
    sync_error: Optional[str] = None


class SyncResultResponse(BaseModel):
    status: str
    message: str
    user_id: Optional[str] = None
    success_count: Optional[int] = None
    failed_count: Optional[int] = None


class UserListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    users: list[UserResponse]


class UserBatchCreate(BaseModel):
    users: list[UserCreate]
    device_ip: str


class UserBatchResult(BaseModel):
    success_count: int
    failed_count: int
    results: list[dict]


class UserSyncFromDeviceRequest(BaseModel):
    device_ip: str
    mode: Literal["preview", "write_missing", "overwrite_local"] = "preview"


class DeviceUserSyncPreviewItem(BaseModel):
    uid: int
    user_id: str
    name: str
    privilege: int
    password: str
    card: int
    action: Literal["missing_in_local", "different_in_local", "uid_conflict"]
    local_snapshot: Optional[dict] = None


class DeviceUserSyncResponse(BaseModel):
    device_ip: str
    mode: str
    device_total: int
    local_total: int
    matched_count: int
    missing_in_local_count: int
    different_in_local_count: int
    uid_conflict_count: int
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    supported_actions: list[str]
    missing_in_local: list[DeviceUserSyncPreviewItem]
    different_in_local: list[DeviceUserSyncPreviewItem]
    uid_conflicts: list[DeviceUserSyncPreviewItem]


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str
