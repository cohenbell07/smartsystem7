"""Initial migration

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Projects table
    op.create_table('projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'RESEARCHING', 'ANALYZING', 'SPEC_GENERATED', 'AWAITING_APPROVAL', 'RUNNING', 'COMPLETED', 'FAILED', name='projectstatus'), nullable=False),
        sa.Column('sources_count', sa.Integer(), nullable=False),
        sa.Column('research_brief', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('viability_score', sa.Integer(), nullable=True),
        sa.Column('viability_rationale', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('sensitivity_analysis', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('agent_spec', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_question'), 'projects', ['question'], unique=False)

    # Research sources table
    op.create_table('research_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('content_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_research_sources_project_id'), 'research_sources', ['project_id'], unique=False)

    # Agents table
    op.create_table('agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('agent_spec', sa.JSON(), nullable=False),
        sa.Column('source_project_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('run_count', sa.Integer(), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['source_project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agents_name'), 'agents', ['name'], unique=False)

    # Runs table
    op.create_table('runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('QUEUED', 'RUNNING', 'PAUSED', 'COMPLETED', 'FAILED', name='runstatus'), nullable=False),
        sa.Column('inputs', sa.JSON(), nullable=True),
        sa.Column('outputs', sa.JSON(), nullable=True),
        sa.Column('job_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('logs', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_runs_agent_id'), 'runs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_runs_project_id'), 'runs', ['project_id'], unique=False)

    # Artifacts table
    op.create_table('artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('artifact_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_artifacts_run_id'), 'artifacts', ['run_id'], unique=False)

    # Approvals table
    op.create_table('approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('step_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('risk_level', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='approvalstatus'), nullable=False),
        sa.Column('approved_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approvals_run_id'), 'approvals', ['run_id'], unique=False)

    # Secrets table
    op.create_table('secrets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('value', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_secrets_user_id'), 'secrets', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_secrets_user_id'), table_name='secrets')
    op.drop_table('secrets')
    op.drop_index(op.f('ix_approvals_run_id'), table_name='approvals')
    op.drop_table('approvals')
    op.drop_index(op.f('ix_artifacts_run_id'), table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_index(op.f('ix_runs_project_id'), table_name='runs')
    op.drop_index(op.f('ix_runs_agent_id'), table_name='runs')
    op.drop_table('runs')
    op.drop_index(op.f('ix_agents_name'), table_name='agents')
    op.drop_table('agents')
    op.drop_index(op.f('ix_research_sources_project_id'), table_name='research_sources')
    op.drop_table('research_sources')
    op.drop_index(op.f('ix_projects_question'), table_name='projects')
    op.drop_table('projects')
