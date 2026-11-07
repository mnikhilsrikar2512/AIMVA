"""scheduled WhatsApp messages

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wa_scheduled',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('contact', sa.String(length=40), nullable=False),
        sa.Column('contact_name', sa.String(length=160), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('template', sa.String(length=120), nullable=False),
        sa.Column('template_lang', sa.String(length=12), nullable=False),
        sa.Column('send_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.String(length=500), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wa_scheduled', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wa_scheduled_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wa_scheduled_send_at'), ['send_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_wa_scheduled_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wa_scheduled', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wa_scheduled_status'))
        batch_op.drop_index(batch_op.f('ix_wa_scheduled_send_at'))
        batch_op.drop_index(batch_op.f('ix_wa_scheduled_user_id'))
    op.drop_table('wa_scheduled')
