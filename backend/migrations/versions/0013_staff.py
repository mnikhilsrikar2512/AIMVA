"""AIMVA team console: support staff and a log of every staff action

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-08 07:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'staff_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('added_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['added_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('staff_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_members_email'), ['email'], unique=True)
    op.create_table(
        'staff_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_email', sa.String(length=255), nullable=False),
        sa.Column('actor_role', sa.String(length=20), nullable=False),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('target_label', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('staff_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_actions_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_actions_target_id'), ['target_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_actions_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('staff_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_actions_created_at'))
        batch_op.drop_index(batch_op.f('ix_staff_actions_target_id'))
        batch_op.drop_index(batch_op.f('ix_staff_actions_action'))
    op.drop_table('staff_actions')
    with op.batch_alter_table('staff_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_members_email'))
    op.drop_table('staff_members')
