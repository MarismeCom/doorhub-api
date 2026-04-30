"""add attendance daily

Revision ID: 005
Revises: 004
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("attend_date", sa.Date(), nullable=False),
        sa.Column("plan_start", sa.String(length=8), nullable=True),
        sa.Column("plan_end", sa.String(length=8), nullable=True),
        sa.Column("actual_checkin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_checkout", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late_minutes", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("early_minutes", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("work_minutes", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("overtime_minutes", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("status", sa.SmallInteger(), nullable=True, server_default="1"),
        sa.Column("is_workday", sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column("calc_time", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "attend_date", name="uq_attendance_daily_user_date"),
    )
    op.create_index("idx_attendance_daily_user_id", "attendance_daily", ["user_id"])
    op.create_index("idx_attendance_daily_attend_date", "attendance_daily", ["attend_date"])
    op.create_index("idx_attendance_daily_status", "attendance_daily", ["status"])


def downgrade() -> None:
    op.drop_index("idx_attendance_daily_status", table_name="attendance_daily")
    op.drop_index("idx_attendance_daily_attend_date", table_name="attendance_daily")
    op.drop_index("idx_attendance_daily_user_id", table_name="attendance_daily")
    op.drop_table("attendance_daily")
