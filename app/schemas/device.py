from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_serializer

ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


class UnlockRequest(BaseModel):
    device_ip: str
    unlock_seconds: int = Field(default=3, ge=1, le=10)
    remark: str = ""


class DoorLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operator: str
    device_ip: str
    action: str
    result: str
    remark: Optional[str]
    operated_at: datetime

    @field_serializer("operated_at")
    def serialize_operated_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        return value.astimezone(ASIA_SHANGHAI).isoformat()


class DoorLogListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    logs: list[DoorLogResponse]


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip: str
    port: int
    serial_number: Optional[str]
    location: Optional[str]
    is_active: bool
    status: str = "inactive"
    created_at: datetime


class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    ip: str = Field(..., min_length=1, max_length=45)
    port: int = Field(default=4370, ge=1, le=65535)
    serial_number: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=128)
    is_active: bool = True


class DeviceUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    ip: str = Field(..., min_length=1, max_length=45)
    port: int = Field(default=4370, ge=1, le=65535)
    serial_number: Optional[str] = Field(default=None, max_length=64)
    location: Optional[str] = Field(default=None, max_length=128)
    is_active: bool = True
