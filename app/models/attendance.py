from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, Text
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
