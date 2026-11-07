"""extra pages on a site (About, Pricing, Contact…)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 12:50:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pages', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('sites', schema=None) as batch_op:
        batch_op.drop_column('pages')
