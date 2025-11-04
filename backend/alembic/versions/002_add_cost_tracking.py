"""Add cost tracking to runs

Revision ID: 002
Revises: 001
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cost tracking columns to runs table."""
    # Add cost tracking columns
    op.add_column('runs', sa.Column('cost_estimate', sa.Float(), nullable=True))
    op.add_column('runs', sa.Column('actual_cost', sa.Float(), nullable=True))
    op.add_column('runs', sa.Column('cost_breakdown', sa.JSON(), nullable=True))
    op.add_column('runs', sa.Column('total_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove cost tracking columns from runs table."""
    op.drop_column('runs', 'total_tokens')
    op.drop_column('runs', 'cost_breakdown')
    op.drop_column('runs', 'actual_cost')
    op.drop_column('runs', 'cost_estimate')
