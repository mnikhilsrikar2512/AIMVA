"""approvals remember what was approved (a content fingerprint), so page views and stats syncs don't undo them;
users keep their sign-up onboarding answers

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-06 18:50:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_hash', sa.String(length=64), nullable=True))
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('onboarding_answers', sa.JSON(), server_default='{}', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('onboarding_answers')
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.drop_column('content_hash')
