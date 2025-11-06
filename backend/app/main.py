"""
Agent Factory - FastAPI Main Application
"""

import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

from app.database import create_db_and_tables, get_session
from app.models import (
    Project,
    ProjectStatus,
    Agent,
    Run,
    RunStatus,
    Artifact,
    ResearchSource,
)
from app.services import (
    LLMRouter,
    ApprovalService,
    NotificationService,
    SecretsService,
    estimate_run_cost,
    get_current_pricing,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Agent Factory...")
    
    # Validate environment variables
    required_keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
    }
    optional_keys = {
        "BING_SEARCH_API_KEY": os.getenv("BING_SEARCH_API_KEY"),
        "SERPAPI_KEY": os.getenv("SERPAPI_KEY"),
        "REDIS_URL": os.getenv("REDIS_URL"),
        "DATABASE_URL": os.getenv("DATABASE_URL"),
    }
    
    # Check if at least one LLM key is present
    has_openai = bool(required_keys["OPENAI_API_KEY"])
    has_anthropic = bool(required_keys["ANTHROPIC_API_KEY"])
    
    if not has_openai and not has_anthropic:
        logger.warning("⚠️  No LLM API keys found! Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env file")
    else:
        if has_openai:
            logger.info("✓ OPENAI_API_KEY found")
        if has_anthropic:
            logger.info("✓ ANTHROPIC_API_KEY found")
    
    # Check optional keys
    if not optional_keys["BING_SEARCH_API_KEY"] and not optional_keys["SERPAPI_KEY"]:
        logger.warning("⚠️  No search API keys found! Set BING_SEARCH_API_KEY or SERPAPI_KEY for better research results")
    else:
        if optional_keys["BING_SEARCH_API_KEY"]:
            logger.info("✓ BING_SEARCH_API_KEY found")
        if optional_keys["SERPAPI_KEY"]:
            logger.info("✓ SERPAPI_KEY found")
    
    if optional_keys["REDIS_URL"]:
        logger.info("✓ REDIS_URL found")
    else:
        logger.info("ℹ️  REDIS_URL not set (optional, for background jobs)")
    
    if optional_keys["DATABASE_URL"]:
        db_info = optional_keys["DATABASE_URL"].split("@")[-1] if "@" in optional_keys["DATABASE_URL"] else "configured"
        logger.info(f"✓ DATABASE_URL found: {db_info}")
    else:
        logger.info("ℹ️  Using default SQLite database")
    
    create_db_and_tables()
    yield
    logger.info("Shutting down Agent Factory...")


# Create FastAPI app
app = FastAPI(
    title="Agent Factory",
    description="Self-assembling AI agent platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services (initialized on startup)
llm_router = LLMRouter()
approval_service = ApprovalService()
notification_service = NotificationService()


# Pydantic models for requests
class AskRequest(BaseModel):
    question: str
    email: Optional[str] = None


class RunAgentRequest(BaseModel):
    project_id: Optional[int] = None
    agent_id: Optional[int] = None
    inputs: dict = {}


class EstimateCostRequest(BaseModel):
    project_id: Optional[int] = None
    agent_id: Optional[int] = None
    inputs: dict = {}


class ApproveRequest(BaseModel):
    approval_id: int
    approved: bool


class SaveAgentRequest(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None


class UpdateSecretsRequest(BaseModel):
    secrets: dict[str, str]


class AgentPromptRequest(BaseModel):
    prompt: str


class AgentRunRequest(BaseModel):
    prompt: Optional[str] = None
    inputs: Optional[dict] = None


# Routes

@app.get("/")
async def root():
    """Health check."""
    return {
        "message": "Agent Factory API",
        "version": "0.1.0",
        "status": "running"
    }


@app.post("/api/ask")
async def ask(
    request: AskRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Start a new research project from a question.

    Flow:
    1. Create Project
    2. Queue research job
    3. Return project ID
    """
    logger.info(f"New question: {request.question}")

    # Create project
    project = Project(
        question=request.question,
        status=ProjectStatus.PENDING,
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    # Queue research job in background
    from workers.runner import run_research_job
    background_tasks.add_task(run_research_job, project.id)

    logger.info(f"Created project {project.id}")

    return {
        "project_id": project.id,
        "status": project.status,
        "message": "Research started"
    }


@app.get("/api/projects/{project_id}")
async def get_project(project_id: int, session: Session = Depends(get_session)):
    """Get project details including logs and status."""
    project = session.get(Project, project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get sources
    sources_stmt = select(ResearchSource).where(ResearchSource.project_id == project_id)
    sources = session.exec(sources_stmt).all()

    # Get runs
    runs_stmt = select(Run).where(Run.project_id == project_id)
    runs = session.exec(runs_stmt).all()

    return {
        "id": project.id,
        "question": project.question,
        "status": project.status,
        "sources_count": len(sources),
        "research_brief": project.research_brief,
        "viability_score": project.viability_score,
        "viability_rationale": project.viability_rationale,
        "sensitivity_analysis": project.sensitivity_analysis,
        "agent_spec": project.agent_spec,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "completed_at": project.completed_at,
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
            }
            for run in runs
        ],
    }


@app.post("/api/estimate-cost")
async def estimate_cost(
    request: EstimateCostRequest,
    session: Session = Depends(get_session),
):
    """
    Estimate the cost of running an agent before execution.
    """
    logger.info(f"Estimating cost: project={request.project_id}, agent={request.agent_id}")

    # Get agent spec
    agent_spec = None

    if request.agent_id:
        agent = session.get(Agent, request.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent_spec = agent.agent_spec
    elif request.project_id:
        project = session.get(Project, request.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        agent_spec = project.agent_spec
    else:
        raise HTTPException(status_code=400, detail="Must provide project_id or agent_id")

    if not agent_spec:
        raise HTTPException(status_code=400, detail="No agent spec available")

    # Estimate cost
    input_text = str(request.inputs)
    cost_estimate = await estimate_run_cost(agent_spec, input_text)

    logger.info(f"Estimated cost: ${cost_estimate['total_estimated_cost']}")

    return cost_estimate


@app.post("/api/run")
async def run_agent(
    request: RunAgentRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Execute an agent (from project spec or saved agent).
    """
    logger.info(f"Running agent: project={request.project_id}, agent={request.agent_id}")

    # Get agent spec
    agent_spec = None
    agent_id = request.agent_id
    project_id = request.project_id

    if request.agent_id:
        agent = session.get(Agent, request.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent_spec = agent.agent_spec
    elif request.project_id:
        project = session.get(Project, request.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        agent_spec = project.agent_spec
    else:
        raise HTTPException(status_code=400, detail="Must provide project_id or agent_id")

    if not agent_spec:
        raise HTTPException(status_code=400, detail="No agent spec available")

    # Validate API keys
    from app.services import APIKeyValidator
    validator = APIKeyValidator()
    is_valid, missing_keys, key_status = validator.validate_agent_keys(agent_spec)

    if not is_valid:
        logger.warning(f"Cannot run agent: missing API keys {missing_keys}")
        report = validator.get_validation_report(agent_spec)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Missing required API keys",
                "missing_keys": missing_keys,
                "validation_report": report
            }
        )

    # Estimate cost
    input_text = str(request.inputs)
    try:
        cost_estimate = await estimate_run_cost(agent_spec, input_text)
        estimated_cost = cost_estimate["total_estimated_cost"]
        cost_breakdown = cost_estimate
    except Exception as e:
        logger.warning(f"Failed to estimate cost: {e}")
        estimated_cost = None
        cost_breakdown = None

    # Create run
    run = Run(
        agent_id=agent_id,
        project_id=project_id,
        status=RunStatus.QUEUED,
        inputs=request.inputs,
        cost_estimate=estimated_cost,
        cost_breakdown=cost_breakdown,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Queue execution job
    from workers.runner import run_agent_job
    background_tasks.add_task(run_agent_job, run.id)

    logger.info(f"Created run {run.id} with estimated cost ${estimated_cost}")

    return {
        "run_id": run.id,
        "status": run.status,
        "message": "Agent execution queued",
        "cost_estimate": estimated_cost,
    }


@app.post("/api/approve")
async def approve(request: ApproveRequest, session: Session = Depends(get_session)):
    """Approve or reject a gated action."""
    logger.info(f"Approval request: {request.approval_id} -> {request.approved}")

    if request.approved:
        success = await approval_service.approve(request.approval_id)
    else:
        success = await approval_service.reject(request.approval_id)

    if not success:
        raise HTTPException(status_code=404, detail="Approval not found")

    return {
        "success": True,
        "approved": request.approved,
    }


@app.post("/api/save-agent")
async def save_agent(request: SaveAgentRequest, session: Session = Depends(get_session)):
    """Save an agent from a project to the portfolio."""
    logger.info(f"Saving agent from project {request.project_id}")

    project = session.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.agent_spec:
        raise HTTPException(status_code=400, detail="Project has no agent spec")

    # Create agent
    agent = Agent(
        name=request.name,
        description=request.description or project.question,
        agent_spec=project.agent_spec,
        source_project_id=project.id,
    )

    session.add(agent)
    session.commit()
    session.refresh(agent)

    logger.info(f"Created agent {agent.id}: {agent.name}")

    return {
        "agent_id": agent.id,
        "name": agent.name,
        "message": "Agent saved to portfolio"
    }


@app.get("/api/agents")
async def list_agents(session: Session = Depends(get_session)):
    """List all saved agents."""
    agents = session.exec(select(Agent)).all()

    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "run_count": agent.run_count,
                "success_count": agent.success_count,
                "created_at": agent.created_at,
            }
            for agent in agents
        ]
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: int, session: Session = Depends(get_session)):
    """Get agent details."""
    agent = session.get(Agent, agent_id)

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get runs
    runs_stmt = select(Run).where(Run.agent_id == agent_id)
    runs = session.exec(runs_stmt).all()

    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "agent_spec": agent.agent_spec,
        "source_project_id": agent.source_project_id,
        "run_count": agent.run_count,
        "success_count": agent.success_count,
        "created_at": agent.created_at,
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "prompt": run.prompt,
            }
            for run in runs
        ],
    }


@app.post("/api/agents/{agent_id}/run")
async def run_saved_agent(
    agent_id: int,
    request: AgentRunRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Execute a saved agent with optional prompt and inputs.

    This endpoint supports both:
    - Prompt-based execution (uses Agent Manager runtime with sub-agents)
    - Input-based execution (direct graph execution)
    """
    logger.info(f"Running saved agent {agent_id}")

    # Get agent
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Validate API keys
    from app.services import APIKeyValidator
    validator = APIKeyValidator()
    is_valid, missing_keys, key_status = validator.validate_agent_keys(agent.agent_spec)

    if not is_valid:
        logger.warning(f"Cannot run agent: missing API keys {missing_keys}")
        report = validator.get_validation_report(agent.agent_spec)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Missing required API keys",
                "missing_keys": missing_keys,
                "validation_report": report
            }
        )

    # Create run record
    run = Run(
        agent_id=agent_id,
        status=RunStatus.QUEUED,
        prompt=request.prompt,
        inputs=request.inputs,
        created_at=datetime.utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Choose execution strategy based on whether prompt is provided
    if request.prompt:
        # Use Agent Manager runtime for prompt-based execution
        logger.info(f"Using Agent Manager runtime for agent {agent_id} with prompt")
        from workers.runner import run_agent_prompt_job
        background_tasks.add_task(run_agent_prompt_job, run.id)
    else:
        # Use direct graph execution for input-based execution
        logger.info(f"Using direct graph execution for agent {agent_id} with inputs")
        from workers.runner import run_agent_job
        background_tasks.add_task(run_agent_job, run.id)

    return {
        "run_id": run.id,
        "agent_id": agent.id,
        "status": run.status,
        "message": "Agent execution queued",
        "execution_mode": "prompt" if request.prompt else "inputs"
    }


@app.post("/api/agents/{agent_id}/prompt")
async def run_agent_with_prompt(
    agent_id: int,
    request: AgentPromptRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Execute an agent with a direct prompt using the Agent Manager runtime.
    This enables multi-agent orchestration with sub-agents and memory recall.

    Note: This endpoint is maintained for backward compatibility.
    Use POST /api/agents/{agent_id}/run instead.
    """
    logger.info(f"Running agent {agent_id} with prompt: {request.prompt[:100]}...")

    # Get agent
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Create run record
    run = Run(
        agent_id=agent_id,
        status=RunStatus.QUEUED,
        prompt=request.prompt,
        created_at=datetime.utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Start background job
    try:
        from workers.runner import run_agent_prompt_job
        background_tasks.add_task(run_agent_prompt_job, run.id)
        logger.info(f"Queued agent prompt job for run {run.id}")
    except ImportError:
        logger.warning("Background worker not available, running synchronously")
        # Fallback to synchronous execution if worker not available
        from workers.runner import run_agent_prompt_job
        await run_agent_prompt_job(run.id)

    return {
        "run_id": run.id,
        "agent_id": agent.id,
        "status": run.status,
        "message": "Agent execution started with prompt"
    }


@app.get("/api/runs/{run_id}")
async def get_run(run_id: int, session: Session = Depends(get_session)):
    """Get run details including logs and artifacts."""
    run = session.get(Run, run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get artifacts
    artifacts_stmt = select(Artifact).where(Artifact.run_id == run_id)
    artifacts = session.exec(artifacts_stmt).all()

    return {
        "id": run.id,
        "agent_id": run.agent_id,
        "project_id": run.project_id,
        "status": run.status,
        "prompt": run.prompt,
        "recalled_memory": run.recalled_memory,
        "inputs": run.inputs,
        "outputs": run.outputs,
        "logs": run.logs,
        "error": run.error,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "cost_estimate": run.cost_estimate,
        "actual_cost": run.actual_cost,
        "total_cost": run.total_cost,
        "cost_breakdown": run.cost_breakdown,
        "total_tokens": run.total_tokens,
        "token_usage": run.token_usage,
        "artifacts": [
            {
                "id": artifact.id,
                "name": artifact.name,
                "type": artifact.artifact_type,
                "content": artifact.content,
            }
            for artifact in artifacts
        ],
    }


@app.get("/api/settings/secrets")
async def get_secrets():
    """Get secret placeholders (redacted values)."""
    secrets_service = SecretsService()
    secrets = secrets_service.get_all_secrets(redact=True)

    return {
        "secrets": secrets,
    }


@app.get("/api/settings")
async def get_settings():
    """Get general settings."""
    return {
        "api_url": os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000"),
        "app_name": os.getenv("NEXT_PUBLIC_APP_NAME", "Agent Factory"),
    }


@app.put("/api/settings/secrets")
async def update_secrets(request: UpdateSecretsRequest):
    """Update secrets."""
    secrets_service = SecretsService()

    for key, value in request.secrets.items():
        if value and value.strip():  # Only update non-empty values
            secrets_service.set_secret(key, value)

    return {
        "success": True,
        "message": f"Updated {len(request.secrets)} secrets"
    }


@app.post("/api/agents/validate-keys")
async def validate_agent_keys(request: EstimateCostRequest, session: Session = Depends(get_session)):
    """
    Validate that all required API keys are present for an agent.
    Returns validation status and missing keys with instructions.
    """
    from app.services import APIKeyValidator

    # Get agent spec
    agent_spec = None

    if request.agent_id:
        agent = session.get(Agent, request.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent_spec = agent.agent_spec
    elif request.project_id:
        project = session.get(Project, request.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        agent_spec = project.agent_spec
    else:
        raise HTTPException(status_code=400, detail="Must provide project_id or agent_id")

    if not agent_spec:
        raise HTTPException(status_code=400, detail="No agent spec available")

    # Validate keys
    validator = APIKeyValidator()
    report = validator.get_validation_report(agent_spec)

    logger.info(f"API key validation: {report['message']}")

    return report


@app.get("/api/pricing")
async def get_pricing():
    """
    Get current pricing for all supported LLM models.
    """
    pricing = await get_current_pricing()
    return pricing


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
