"""AIMVA team console: tasks the owner or a manager assigns to teammates

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-08 08:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'staff_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('assignee_email', sa.String(length=255), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_by_email', sa.String(length=255), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('customer_label', sa.String(length=255), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('due_on', sa.Date(), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('staff_tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_tasks_assignee_email'), ['assignee_email'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_tasks_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_tasks_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('staff_tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_tasks_status'))
        batch_op.drop_index(batch_op.f('ix_staff_tasks_customer_id'))
        batch_op.drop_index(batch_op.f('ix_staff_tasks_assignee_email'))
    op.drop_table('staff_tasks')
