import json

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AttendanceMonthlyExportSetting(Base):
    __tablename__ = "attendance_monthly_export_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    system_user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    selected_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def selected_fields(self) -> list[str]:
        try:
            data = json.loads(self.selected_fields_json or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if item]

    @selected_fields.setter
    def selected_fields(self, values: list[str] | None) -> None:
        self.selected_fields_json = json.dumps([str(item) for item in (values or []) if item], ensure_ascii=True)
