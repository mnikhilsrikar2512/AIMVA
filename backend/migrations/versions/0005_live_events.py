"""live updates too large for a Postgres NOTIFY

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 17:40:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'live_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('live_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_live_events_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('live_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_live_events_created_at'))
    op.drop_table('live_events')
