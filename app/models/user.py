from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    privilege: Mapped[int] = mapped_column(SmallInteger, default=0)
    password: Mapped[str] = mapped_column(String(32), default="")
    group_id: Mapped[str] = mapped_column(String(8), default="")
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    card: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    device_sn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
