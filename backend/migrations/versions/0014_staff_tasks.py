"""AIMVA team console: tasks the owner or a manager assigns, worked on by any number of teammates at once

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
        sa.Column('version', sa.Integer(), nullable=False),
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
        batch_op.create_index(batch_op.f('ix_staff_tasks_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_tasks_status'), ['status'], unique=False)
    op.create_table(
        'staff_task_people',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['staff_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', 'email'),
    )
    with op.batch_alter_table('staff_task_people', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_task_people_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_task_people_email'), ['email'], unique=False)
    op.create_table(
        'staff_task_updates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('author_email', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['staff_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('staff_task_updates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_task_updates_task_id'), ['task_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('staff_task_updates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_task_updates_task_id'))
    op.drop_table('staff_task_updates')
    with op.batch_alter_table('staff_task_people', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_task_people_email'))
        batch_op.drop_index(batch_op.f('ix_staff_task_people_task_id'))
    op.drop_table('staff_task_people')
    with op.batch_alter_table('staff_tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_staff_tasks_status'))
        batch_op.drop_index(batch_op.f('ix_staff_tasks_customer_id'))
    op.drop_table('staff_tasks')
