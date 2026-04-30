from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Attendance(Base):
    __tablename__ = "attendances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[int] = mapped_column(SmallInteger, default=0)
    punch: Mapped[int] = mapped_column(SmallInteger, default=0)
    device_sn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DoorLog(Base):
    __tablename__ = "door_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    device_sn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    action: Mapped[str] = mapped_column(String(32), default="unlock")
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    operated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttendanceDaily(Base):
    __tablename__ = "attendance_daily"
    __table_args__ = (UniqueConstraint("user_id", "attend_date", name="uq_attendance_daily_user_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attend_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    plan_start: Mapped[str | None] = mapped_column(String(8), nullable=True)
    plan_end: Mapped[str | None] = mapped_column(String(8), nullable=True)
    actual_checkin: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_checkout: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_minutes: Mapped[int] = mapped_column(Integer, default=0)
    work_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=1, index=True)
    is_workday: Mapped[bool] = mapped_column(default=True)
    calc_time: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendar"
    __table_args__ = (UniqueConstraint("holiday_date", name="uq_holiday_calendar_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    holiday_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_holiday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    fetched_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
