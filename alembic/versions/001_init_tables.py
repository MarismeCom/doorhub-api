"""init tables

Revision ID: 001
Revises:
Create Date: 2026-04-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users 表
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('privilege', sa.SmallInteger(), nullable=True),
        sa.Column('password', sa.String(length=32), nullable=True),
        sa.Column('group_id', sa.String(length=8), nullable=True),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('card', sa.BigInteger(), nullable=True),
        sa.Column('device_sn', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uid'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('idx_users_user_id', 'users', ['user_id'])
    op.create_index('idx_users_uid', 'users', ['uid'])
    op.create_index('idx_users_deleted_at', 'users', ['deleted_at'])

    # attendances 表
    op.create_table(
        'attendances',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('uid', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.SmallInteger(), nullable=True),
        sa.Column('punch', sa.SmallInteger(), nullable=True),
        sa.Column('device_sn', sa.String(length=64), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_att_user_id', 'attendances', ['user_id'])
    op.create_index('idx_att_timestamp', 'attendances', ['timestamp'])
    op.create_index('idx_att_synced_at', 'attendances', ['synced_at'])
    op.create_index('idx_att_user_timestamp', 'attendances', ['user_id', 'timestamp'])

    # door_logs 表
    op.create_table(
        'door_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('operator', sa.String(length=64), nullable=False),
        sa.Column('device_sn', sa.String(length=64), nullable=True),
        sa.Column('device_ip', sa.String(length=45), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=True),
        sa.Column('result', sa.String(length=16), nullable=False),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('operated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_door_logs_operated_at', 'door_logs', ['operated_at'])

    # devices 表
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=False),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('serial_number', sa.String(length=64), nullable=True),
        sa.Column('location', sa.String(length=128), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip'),
    )


def downgrade() -> None:
    op.drop_table('devices')
    op.drop_table('door_logs')
    op.drop_table('attendances')
    op.drop_table('users')