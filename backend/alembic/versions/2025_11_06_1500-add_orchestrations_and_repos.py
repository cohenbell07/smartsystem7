"""add orchestrations and agent repos

Revision ID: add_orchestrations
Revises: 597f7615e8de
Create Date: 2025-11-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = 'add_orchestrations'
down_revision: Union[str, None] = '597f7615e8de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add repo fields to agents table
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('repo_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('repo_local_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    # Create orchestrations table
    op.create_table(
        'orchestrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_ids', sa.JSON(), nullable=False),
        sa.Column('prompt', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('strategy', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('agent_progress', sa.JSON(), nullable=True),
        sa.Column('agent_outputs', sa.JSON(), nullable=True),
        sa.Column('outputs', sa.JSON(), nullable=True),
        sa.Column('logs', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('total_cost', sa.Float(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('generated_agent_id', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['generated_agent_id'], ['agents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop orchestrations table
    op.drop_table('orchestrations')

    # Remove repo fields from agents table
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.drop_column('repo_local_path')
        batch_op.drop_column('repo_url')
