"""leads who reply STOP are opted out: no WhatsApp or calls until they reply START

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-08 02:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opt_outs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('contact', sa.String(length=40), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'contact', name='uq_opt_outs_user_contact'),
    )
    with op.batch_alter_table('opt_outs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_opt_outs_user_id'), ['user_id'], unique=False)
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('opted_out_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('opted_out_at')
    with op.batch_alter_table('opt_outs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_opt_outs_user_id'))
    op.drop_table('opt_outs')
