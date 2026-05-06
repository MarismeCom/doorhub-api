"""add attendance rule settings

Revision ID: 008_add_attendance_rule_settings
Revises: 007_add_attendance_sync_settings
Create Date: 2026-05-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "008_add_attendance_rule_settings"
down_revision = "007_add_attendance_sync_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_rule_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_start", sa.String(length=5), nullable=False, server_default="10:00"),
        sa.Column("plan_end", sa.String(length=5), nullable=False, server_default="18:00"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO attendance_rule_settings (id, plan_start, plan_end)
            VALUES (1, '10:00', '18:00')
            """
        )
    )


def downgrade() -> None:
    op.drop_table("attendance_rule_settings")
