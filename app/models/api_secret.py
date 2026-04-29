from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ApiSecret(Base):
    __tablename__ = "api_secrets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    system_user_id: Mapped[int] = mapped_column(ForeignKey("system_users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    system_user = relationship("SystemUser", back_populates="api_secrets")
