"""add attendance sync settings

Revision ID: 007_add_attendance_sync_settings
Revises: 006_add_holiday_calendar
Create Date: 2026-04-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "007_add_attendance_sync_settings"
down_revision = "006_add_holiday_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_sync_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("time", sa.String(length=5), nullable=False, server_default="23:00"),
        sa.Column("device_ips_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO attendance_sync_settings (id, enabled, time, device_ips_json)
            VALUES (1, false, '23:00', '[]')
            """
        )
    )


def downgrade() -> None:
    op.drop_table("attendance_sync_settings")
