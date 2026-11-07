"""billing: subscriptions, usage events, credit grants

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06 18:15:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plan', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('processor', sa.String(length=20), nullable=False),
        sa.Column('processor_subscription_id', sa.String(length=120), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_user_id'), ['user_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_subscriptions_processor_subscription_id'), ['processor_subscription_id'], unique=False)
    op.create_table(
        'usage_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('meter', sa.String(length=30), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('ref', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('usage_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usage_events_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_usage_events_meter'), ['meter'], unique=False)
        batch_op.create_index(batch_op.f('ix_usage_events_created_at'), ['created_at'], unique=False)
    op.create_table(
        'credit_grants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('meter', sa.String(length=30), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('credit_grants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_credit_grants_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('credit_grants')
    op.drop_table('usage_events')
    op.drop_table('subscriptions')
