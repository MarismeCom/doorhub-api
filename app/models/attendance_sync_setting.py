import json

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AttendanceSyncSetting(Base):
    __tablename__ = "attendance_sync_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time: Mapped[str] = mapped_column(String(5), nullable=False, default="23:00")
    device_ips_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def device_ips(self) -> list[str]:
        try:
            data = json.loads(self.device_ips_json or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(ip) for ip in data if ip]

    @device_ips.setter
    def device_ips(self, values: list[str] | None) -> None:
        self.device_ips_json = json.dumps([str(ip) for ip in (values or []) if ip], ensure_ascii=True)
