"""add attendance monthly export settings

Revision ID: 009_add_attendance_monthly_export_settings
Revises: 008_add_attendance_rule_settings
Create Date: 2026-05-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009_add_attendance_monthly_export_settings"
down_revision = "008_add_attendance_rule_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_monthly_export_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("system_user_id", sa.Integer(), nullable=False),
        sa.Column("selected_fields_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["system_user_id"], ["system_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("system_user_id"),
    )


def downgrade() -> None:
    op.drop_table("attendance_monthly_export_settings")
