from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=1, max_length=128)


class SystemUserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    role: Literal["admin", "user"] = "user"


class SystemUserUpdate(BaseModel):
    role: Optional[Literal["admin", "user"]] = None
    is_active: Optional[bool] = None


class SystemUserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=1, max_length=128)


class SystemUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class CurrentUserResponse(BaseModel):
    username: str
    role: str
    is_active: bool


class ApiSecretCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    expires_at: Optional[datetime] = None


class ApiSecretResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    secret_prefix: str
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    created_at: Optional[datetime]


class ApiSecretCreateResponse(BaseModel):
    secret: str
    secret_meta: ApiSecretResponse
