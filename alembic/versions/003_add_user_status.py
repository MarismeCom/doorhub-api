"""add user status

Revision ID: 003
Revises: 002
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("status", sa.String(length=16), server_default="active", nullable=False))
    op.execute(
        """
        UPDATE users
        SET status = CASE
            WHEN deleted_at IS NOT NULL THEN 'disabled'
            WHEN sync_status IN ('pending_disable', 'synced_disabled') THEN 'disabled'
            ELSE 'active'
        END
        """
    )
    op.execute("UPDATE users SET deleted_at = NULL WHERE deleted_at IS NOT NULL")
    op.alter_column("users", "status", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "status")
