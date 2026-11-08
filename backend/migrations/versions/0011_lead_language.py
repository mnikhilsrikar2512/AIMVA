"""leads remember the language they write in, so replies and the welcome follow it

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-07 16:50:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.String(length=12), server_default='', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('language')
