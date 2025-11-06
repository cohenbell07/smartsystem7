"""
SQLModel data models for Agent Factory.
"""

from datetime import datetime
from typing import Optional
from enum import Enum

from sqlmodel import Field, SQLModel, JSON, Column
from pydantic import BaseModel


# Enums
class ProjectStatus(str, Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    ANALYZING = "analyzing"
    SPEC_GENERATED = "spec_generated"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# Database Models
class Project(SQLModel, table=True):
    """A research project initiated by a user question."""

    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    question: str = Field(index=True)
    status: ProjectStatus = Field(default=ProjectStatus.PENDING)

    # Research outputs
    sources_count: int = Field(default=0)
    research_brief: Optional[str] = None  # Markdown with citations
    viability_score: Optional[int] = None  # 0-100
    viability_rationale: Optional[str] = None  # JSON with breakdown
    sensitivity_analysis: Optional[str] = None  # JSON table

    # Agent spec (JSON)
    agent_spec: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # User (stub for now)
    user_id: str = Field(default="dev_user")


class ResearchSource(SQLModel, table=True):
    """A source document from research."""

    __tablename__ = "research_sources"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)

    url: str
    title: Optional[str] = None
    content: Optional[str] = None  # Extracted text
    content_hash: Optional[str] = None  # For deduplication
    meta_data: Optional[dict] = Field(default=None, sa_column=Column("metadata", JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Agent(SQLModel, table=True):
    """A saved agent in the user's portfolio."""

    __tablename__ = "agents"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    agent_spec: dict = Field(sa_column=Column(JSON))  # Full AgentSpec

    # Links back to original project
    source_project_id: Optional[int] = Field(default=None, foreign_key="projects.id")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: str = Field(default="dev_user")

    # Stats
    run_count: int = Field(default=0)
    success_count: int = Field(default=0)


class Run(SQLModel, table=True):
    """An execution of an agent."""

    __tablename__ = "runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: Optional[int] = Field(default=None, foreign_key="agents.id", index=True)
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id", index=True)

    status: RunStatus = Field(default=RunStatus.QUEUED)

    # For multi-agent runtime
    prompt: Optional[str] = None  # User prompt for agent manager
    recalled_memory: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # Recalled context

    inputs: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    outputs: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Execution details
    job_id: Optional[str] = None  # RQ job ID
    logs: Optional[str] = None  # Concatenated logs
    error: Optional[str] = None

    # Cost tracking
    cost_estimate: Optional[float] = None  # Estimated cost in USD before run
    actual_cost: Optional[float] = None  # Actual cost in USD after run
    cost_breakdown: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # Detailed cost info
    total_tokens: Optional[int] = None  # Total tokens used (input + output)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user_id: str = Field(default="dev_user")


class Artifact(SQLModel, table=True):
    """Output artifacts from agent runs."""

    __tablename__ = "artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id", index=True)

    name: str
    artifact_type: str  # "markdown", "json", "code", "image", etc.
    content: str
    meta_data: Optional[dict] = Field(default=None, sa_column=Column("metadata", JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Approval(SQLModel, table=True):
    """Approval gates for risky agent actions."""

    __tablename__ = "approvals"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    step_id: str  # Identifier for the step requiring approval

    action: str  # Description of action
    risk_level: str  # "low", "medium", "high"
    details: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Secret(SQLModel, table=True):
    """User secrets (API keys, tokens)."""

    __tablename__ = "secrets"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    key: str  # e.g., "OPENAI_API_KEY"
    value: str  # Encrypted in production
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Pydantic schemas for API
class ViabilityScore(BaseModel):
    """Business viability scoring breakdown."""

    overall: int  # 0-100
    market_demand: int
    competition: int
    feasibility: int
    capital_requirement: int
    moat: int
    rationale: str
    sensitivity: dict  # Table of what-if scenarios


class AgentSpec(BaseModel):
    """Specification for a custom agent."""

    name: str
    description: str
    objective: str
    tools: list[str]  # Tool IDs needed
    apis: list[str]  # External APIs required
    graph_type: str  # "video_generation", "outreach", "site_builder", "custom"
    nodes: list[dict]  # Node definitions
    edges: list[dict]  # Edge definitions
    test_plan: list[str]
    success_criteria: list[str]
    approval_gates: list[str]  # Steps requiring approval
    estimated_runtime: int  # seconds


class ResearchBrief(BaseModel):
    """Research synthesis with citations."""

    summary: str  # Markdown with inline [#] citations
    key_findings: list[str]
    sources: list[dict]  # [{id, title, url, relevance}]
    total_sources: int
    content_length: int
