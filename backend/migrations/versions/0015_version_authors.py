"""page versions remember who saved them, the owner's words for AI edits, and which page they belong to

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-15 03:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('site_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('page', sa.String(length=60), server_default='', nullable=False))
        batch_op.add_column(sa.Column('request', sa.String(length=120), server_default='', nullable=False))
        batch_op.add_column(sa.Column('by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_site_versions_by_id_users', 'users', ['by_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('site_versions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_site_versions_by_id_users', type_='foreignkey')
        batch_op.drop_column('by_id')
        batch_op.drop_column('request')
        batch_op.drop_column('page')
