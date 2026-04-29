"""add api secrets

Revision ID: 004
Revises: 003
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_secrets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("system_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("secret_prefix", sa.String(length=16), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["system_user_id"], ["system_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_secrets_system_user_id", "api_secrets", ["system_user_id"], unique=False)
    op.create_index("ix_api_secrets_secret_prefix", "api_secrets", ["secret_prefix"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_secrets_secret_prefix", table_name="api_secrets")
    op.drop_index("ix_api_secrets_system_user_id", table_name="api_secrets")
    op.drop_table("api_secrets")
