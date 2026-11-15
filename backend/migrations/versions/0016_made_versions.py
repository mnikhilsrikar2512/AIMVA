"""versions for call scripts and campaign drafts, and an on/off switch for call-backs

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-15 16:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'made_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('ref_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('request', sa.String(length=300), nullable=False),
        sa.Column('note', sa.String(length=120), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('made_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_made_versions_ref_id'), ['ref_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_made_versions_user_id'), ['user_id'], unique=False)
    with op.batch_alter_table('voice_agents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('voice_agents', schema=None) as batch_op:
        batch_op.drop_column('enabled')
    with op.batch_alter_table('made_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_made_versions_user_id'))
        batch_op.drop_index(batch_op.f('ix_made_versions_ref_id'))
    op.drop_table('made_versions')
