"""add holiday calendar

Revision ID: 006
Revises: 005
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "holiday_calendar",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("type", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("is_holiday", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("holiday_date", name="uq_holiday_calendar_date"),
    )
    op.create_index("idx_holiday_calendar_date", "holiday_calendar", ["holiday_date"])
    op.create_index("idx_holiday_calendar_year", "holiday_calendar", ["year"])


def downgrade() -> None:
    op.drop_index("idx_holiday_calendar_year", table_name="holiday_calendar")
    op.drop_index("idx_holiday_calendar_date", table_name="holiday_calendar")
    op.drop_table("holiday_calendar")
