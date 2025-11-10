"""
Agent Factory - FastAPI Main Application
"""

import logging
import os
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

from app.database import create_db_and_tables, get_session, engine
from app.models import (
    Project,
    ProjectStatus,
    Agent,
    Run,
    RunStatus,
    Artifact,
    ResearchSource,
    Orchestration,
    AgentPlan,
    AgentPlanState,
    AgentBuild,
    AgentBuildStatus,
)
from app.services import (
    LLMRouter,
    ApprovalService,
    NotificationService,
    SecretsService,
    estimate_run_cost,
    get_current_pricing,
    run_research,
    PlanService,
    BuildService,
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
    await refresh_service_health()
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
plan_service = PlanService()
build_service = BuildService()

REQUIRED_GITHUB_SCOPES = ["repo", "workflow", "admin:repo_hook", "delete_repo"]
service_health: Dict[str, Any] = {
    "github": {"ok": False, "missing": REQUIRED_GITHUB_SCOPES, "scopes": []},
    "vercel": {"ok": build_service.vercel_client.is_available()},
    "docker": {"ok": build_service.docker_executor.is_available()},
    "db": {"ok": True},
}


async def refresh_service_health() -> None:
    """Update cached service health information."""
    global service_health

    if build_service.github_client.is_available():
        github_validation = build_service.github_client.validate_scopes(REQUIRED_GITHUB_SCOPES)
        github_status = {
            "ok": github_validation["valid"],
            "missing": github_validation["missing"],
            "scopes": github_validation["scopes"],
        }
        if github_validation["missing"]:
            logger.warning("GitHub token missing scopes: %s", github_validation["missing"])
    else:
        github_status = {
            "ok": False,
            "missing": REQUIRED_GITHUB_SCOPES,
            "scopes": [],
        }

    docker_ok = build_service.docker_executor.is_available()
    vercel_ok = build_service.vercel_client.is_available()

    try:
        with Session(engine) as session:
            session.exec(select(Project.id).limit(1))
        database_ok = True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        database_ok = False

    service_health.update(
        {
            "github": github_status,
            "vercel": {"ok": vercel_ok},
            "docker": {"ok": docker_ok},
            "db": {"ok": database_ok},
        }
    )


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


class SetKeysRequest(BaseModel):
    keys: dict[str, str]


class CreateRepoRequest(BaseModel):
    pass  # No body needed, uses agent_id from path


class CreateOrchestrationRequest(BaseModel):
    agent_ids: List[int]
    prompt: str
    strategy: str = "manager-led"  # "sequential", "parallel", "manager-led"


class CodingBuildRequest(BaseModel):
    prompt: str
    project_context: Optional[dict] = None
    tech_stack_preferences: Optional[dict] = None
    quality_threshold: Optional[float] = 0.95
    max_iterations: Optional[int] = 5


class ResearchRequest(BaseModel):
    prompt: str


class PlanCreateRequest(BaseModel):
    prompt: str


class PlanRevisionRequest(BaseModel):
    revision: str
    mark_ready: bool = False


class BuildPlanRequest(BaseModel):
    plan_id: str
    enable_deployment: bool = False


def serialize_plan(plan: AgentPlan) -> Dict[str, Any]:
    state_value = plan.state.value if isinstance(plan.state, AgentPlanState) else str(plan.state)
    return {
        "plan_id": plan.id,
        "prompt": plan.prompt,
        "plan": plan.plan,
        "graph": plan.graph,
        "suggested_stack": plan.suggested_stack,
        "risks": plan.risks,
        "state": state_value,
        "chat_history": plan.chat_history,
        "summary": plan.summary,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        "last_revision_at": plan.last_revision_at.isoformat() if plan.last_revision_at else None,
    }


def serialize_build(build: AgentBuild) -> Dict[str, Any]:
    status_value = build.status.value if isinstance(build.status, AgentBuildStatus) else str(build.status)
    return {
        "run_id": build.run_id,
        "plan_id": build.plan_id,
        "status": status_value,
        "quality_score": build.quality_score,
        "repo_url": build.repo_url,
        "vercel_url": build.vercel_url,
        "artifacts": build.artifacts,
        "created_at": build.created_at.isoformat() if build.created_at else None,
        "updated_at": build.updated_at.isoformat() if build.updated_at else None,
        "logs": build.logs,
    }


# Routes

@app.get("/")
async def root():
    """Health check."""
    return {
        "message": "Agent Factory API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    await refresh_service_health()
    overall_ok = all(section.get("ok") for section in service_health.values())
    return {
        "status": "ok" if overall_ok else "degraded",
        "services": service_health,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health/github")
async def health_github():
    await refresh_service_health()
    github_status = service_health.get("github", {})
    if not github_status.get("ok"):
        raise HTTPException(status_code=503, detail=github_status)
    return github_status


@app.post("/api/research")
async def research_endpoint(request: ResearchRequest):
    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    try:
        return await run_research(prompt)
    except Exception as exc:
        logger.error("Research workflow failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/agents/plan")
async def create_plan_endpoint(
    request: PlanCreateRequest,
    session: Session = Depends(get_session),
):
    try:
        plan = await plan_service.create_plan(session, request.prompt)
        return serialize_plan(plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/agents/plan/{plan_id}")
async def get_plan_endpoint(plan_id: str, session: Session = Depends(get_session)):
    try:
        plan = plan_service.get_plan(session, plan_id)
        return serialize_plan(plan)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.patch("/api/agents/plan/{plan_id}")
async def revise_plan_endpoint(
    plan_id: str,
    request: PlanRevisionRequest,
    session: Session = Depends(get_session),
):
    try:
        plan = await plan_service.apply_revision(
            session,
            plan_id,
            request.revision,
            mark_ready=request.mark_ready,
        )
        return serialize_plan(plan)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message)


@app.post("/api/agents/build")
async def start_build_endpoint(
    request: BuildPlanRequest,
    session: Session = Depends(get_session),
):
    try:
        run_id = await build_service.start_build(
            session, request.plan_id, request.enable_deployment
        )
        return {"run_id": run_id, "status": "queued"}
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message)


@app.get("/api/agents/builds/{run_id}/stream")
async def stream_build_logs(run_id: str):
    async def event_generator():
        try:
            async for event in build_service.stream_events(run_id):
                yield f"data: {json.dumps(event)}\n\n"
        except ValueError:
            error_payload = {"type": "error", "data": {"message": "Run not found"}}
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            yield "event: end\ndata: {}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@app.get("/api/agents/builds/{run_id}")
async def get_build_endpoint(run_id: str, session: Session = Depends(get_session)):
    try:
        build = build_service.get_build(session, run_id)
        return serialize_build(build)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/agents/builds/{run_id}/files")
async def list_build_files(run_id: str, session: Session = Depends(get_session)):
    try:
        build = build_service.get_build(session, run_id)
        return build_service.list_files(build)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/agents/builds/{run_id}/file")
async def get_build_file(
    run_id: str,
    path: str,
    session: Session = Depends(get_session),
):
    if not path:
        raise HTTPException(status_code=400, detail="Query parameter 'path' is required")
    try:
        build = build_service.get_build(session, run_id)
        return build_service.get_file(build, path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/agents/deploy/{run_id}")
async def force_deploy_endpoint(run_id: str):
    try:
        new_run_id = await build_service.force_deploy(run_id)
        return {"run_id": new_run_id, "status": "queued"}
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message)


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

    agent_spec_dict = project.agent_spec if isinstance(project.agent_spec, dict) else {}

    # Create agent
    agent = Agent(
        name=request.name,
        description=request.description or project.question,
        agent_spec=project.agent_spec,
        default_model=
            agent_spec_dict.get("default_model")
            or agent_spec_dict.get("model")
            or os.getenv("DEFAULT_LLM", "gpt-4o-mini"),
        instructions=
            agent_spec_dict.get("instructions")
            or agent_spec_dict.get("objective")
            or project.question,
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
                "default_model": agent.default_model,
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
        "default_model": agent.default_model,
        "instructions": agent.instructions,
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
            status_code=428,
            detail={
                "error": "Missing required API keys",
                "missing_keys": missing_keys,
                "missing_with_instructions": report["missing_with_instructions"]
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


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: int):
    """Stream run logs and status updates in real time via SSE."""

    async def event_generator():
        last_log_length = 0
        last_status = None

        while True:
            with Session(engine) as session:
                run = session.get(Run, run_id)
                if not run:
                    payload = {"event": "error", "data": "Run not found"}
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

                logs = run.logs or ""
                if len(logs) > last_log_length:
                    new_chunk = logs[last_log_length:]
                    last_log_length = len(logs)
                    payload = {"event": "log", "data": new_chunk}
                    yield f"data: {json.dumps(payload)}\n\n"

                status_value = run.status.value if isinstance(run.status, RunStatus) else str(run.status)
                if status_value != last_status:
                    last_status = status_value
                    payload = {"event": "status", "data": status_value}
                    yield f"data: {json.dumps(payload)}\n\n"

                if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                    break

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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


@app.get("/api/settings/required_keys")
async def get_required_keys(agent_id: Optional[int] = None, session: Session = Depends(get_session)):
    """
    Get list of required API keys for an agent.
    Returns missing keys with instructions for obtaining them.
    """
    from app.services import APIKeyValidator

    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id parameter is required")

    # Get agent
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Validate keys
    validator = APIKeyValidator()
    report = validator.get_validation_report(agent.agent_spec)

    return {
        "valid": report["valid"],
        "missing_keys": report["missing_keys"],
        "missing_with_instructions": report["missing_with_instructions"]
    }


@app.post("/api/settings/keys")
async def set_keys(request: SetKeysRequest):
    """
    Save API keys to environment and .env file.
    Reloads LLM clients to pick up new keys.
    """
    from datetime import datetime

    secrets_service = SecretsService()
    saved_keys = []

    # Save each key
    for key, value in request.keys.items():
        if value and value.strip():
            # Redact from logs
            logger.info(f"Setting API key: {key}")

            # Save to DB and .env
            success = secrets_service.set_secret(key, value, save_to_env=True)

            if success:
                saved_keys.append(key)

    # Reload LLM clients to pick up new keys
    global llm_router
    llm_router = LLMRouter()

    logger.info(f"Saved and reloaded {len(saved_keys)} API keys")

    return {
        "saved": saved_keys,
        "message": f"Saved {len(saved_keys)} API key(s) and reloaded clients"
    }


@app.post("/api/agents/{agent_id}/repo")
async def create_agent_repo(
    agent_id: int,
    session: Session = Depends(get_session)
):
    """
    Create a GitHub repository for an agent and clone it locally.
    Requires GITHUB_TOKEN in environment.
    """
    import subprocess
    import json
    from pathlib import Path

    # Get agent
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check if repo already exists
    if agent.repo_url:
        return {
            "repo_url": agent.repo_url,
            "local_path": agent.repo_local_path,
            "message": "Repository already exists"
        }

    # Get GitHub token
    secrets_service = SecretsService()
    github_token = secrets_service.get_secret("GITHUB_TOKEN")

    if not github_token:
        raise HTTPException(
            status_code=428,
            detail={
                "error": "GitHub token required",
                "missing_keys": ["GITHUB_TOKEN"],
                "missing_with_instructions": [{
                    "key": "GITHUB_TOKEN",
                    "url": "https://github.com/settings/tokens",
                    "description": "Generate a Personal Access Token with repo permissions"
                }]
            }
        )

    try:
        # Create repo name from agent name
        import re
        repo_name = f"agent-{re.sub(r'[^a-z0-9-]', '-', agent.name.lower())}"

        # Create GitHub repo using gh CLI or API
        # Using GitHub API directly
        import requests

        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # Create repo
        create_response = requests.post(
            "https://api.github.com/user/repos",
            headers=headers,
            json={
                "name": repo_name,
                "description": agent.description or f"Agent: {agent.name}",
                "private": False,
                "auto_init": True
            }
        )

        if create_response.status_code not in [200, 201]:
            error_msg = create_response.json().get("message", "Unknown error")
            logger.error(f"GitHub API error: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Failed to create GitHub repo: {error_msg}")

        repo_data = create_response.json()
        repo_url = repo_data["html_url"]
        clone_url = repo_data["clone_url"]

        # Clone repo locally
        repos_dir = Path("./repos")
        repos_dir.mkdir(exist_ok=True)

        local_path = repos_dir / str(agent_id)
        local_path.mkdir(exist_ok=True)

        # Clone the repo
        subprocess.run(
            ["git", "clone", clone_url.replace("https://", f"https://{github_token}@"), str(local_path)],
            check=True,
            capture_output=True
        )

        # Create initial agent files
        agent_file = local_path / f"{repo_name}" / "agent_spec.json"
        agent_file.parent.mkdir(exist_ok=True)

        with open(agent_file, "w") as f:
            json.dump(agent.agent_spec, f, indent=2)

        readme_file = local_path / f"{repo_name}" / "README.md"
        with open(readme_file, "w") as f:
            f.write(f"# {agent.name}\n\n")
            f.write(f"{agent.description or 'AI Agent'}\n\n")
            f.write(f"## Agent Specification\n\nSee `agent_spec.json` for the full agent specification.\n")

        # Commit and push
        subprocess.run(
            ["git", "-C", str(local_path / repo_name), "add", "."],
            check=True
        )
        subprocess.run(
            ["git", "-C", str(local_path / repo_name), "commit", "-m", "Initial agent specification"],
            check=True
        )
        subprocess.run(
            ["git", "-C", str(local_path / repo_name), "push"],
            check=True
        )

        # Update agent record
        agent.repo_url = repo_url
        agent.repo_local_path = str(local_path / repo_name)
        agent.updated_at = datetime.utcnow()
        session.add(agent)
        session.commit()

        logger.info(f"Created GitHub repo for agent {agent_id}: {repo_url}")

        return {
            "repo_url": repo_url,
            "local_path": str(local_path / repo_name),
            "message": "Repository created and initialized"
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e.stderr.decode() if e.stderr else str(e)}")
        raise HTTPException(status_code=500, detail=f"Git operation failed: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create repo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create repository: {str(e)}")


@app.get("/api/agents/{agent_id}/files")
async def get_agent_files(
    agent_id: int,
    session: Session = Depends(get_session)
):
    """
    Get list of files in the agent's GitHub repository.
    """
    from pathlib import Path

    # Get agent
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.repo_local_path:
        return {
            "files": [],
            "message": "No repository configured for this agent"
        }

    try:
        # List files in the local clone
        local_path = Path(agent.repo_local_path)

        if not local_path.exists():
            return {
                "files": [],
                "message": "Local repository not found"
            }

        files = []
        for file_path in local_path.rglob("*"):
            if file_path.is_file() and ".git" not in str(file_path):
                relative_path = file_path.relative_to(local_path)

                # Read file content (limit size)
                try:
                    if file_path.stat().st_size < 100000:  # 100KB limit
                        content = file_path.read_text()
                    else:
                        content = "[File too large to display]"
                except:
                    content = "[Binary file]"

                files.append({
                    "path": str(relative_path),
                    "name": file_path.name,
                    "size": file_path.stat().st_size,
                    "content": content
                })

        return {
            "files": files,
            "repo_url": agent.repo_url
        }

    except Exception as e:
        logger.error(f"Failed to list files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@app.post("/api/orchestrations")
async def create_orchestration(
    request: CreateOrchestrationRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Create a multi-agent orchestration.
    Combines multiple agents to work on a task collaboratively.
    """
    logger.info(f"Creating orchestration with {len(request.agent_ids)} agents")

    # Validate agents exist
    agents = []
    for agent_id in request.agent_ids:
        agent = session.get(Agent, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        agents.append(agent)

    # Create orchestration record
    orchestration = Orchestration(
        agent_ids=request.agent_ids,
        prompt=request.prompt,
        strategy=request.strategy,
        status=RunStatus.QUEUED,
        agent_progress={str(aid): 0 for aid in request.agent_ids},
        agent_outputs={},
        created_at=datetime.utcnow()
    )

    session.add(orchestration)
    session.commit()
    session.refresh(orchestration)

    # Queue orchestration job
    from workers.runner import run_orchestration_job
    background_tasks.add_task(run_orchestration_job, orchestration.id)

    logger.info(f"Created orchestration {orchestration.id}")

    return {
        "orchestration_id": orchestration.id,
        "status": orchestration.status,
        "agent_count": len(request.agent_ids),
        "message": "Orchestration started"
    }


@app.get("/api/orchestrations/{orchestration_id}")
async def get_orchestration(
    orchestration_id: int,
    session: Session = Depends(get_session)
):
    """
    Get orchestration status and results.
    """
    orchestration = session.get(Orchestration, orchestration_id)

    if not orchestration:
        raise HTTPException(status_code=404, detail="Orchestration not found")

    return {
        "id": orchestration.id,
        "agent_ids": orchestration.agent_ids,
        "prompt": orchestration.prompt,
        "strategy": orchestration.strategy,
        "status": orchestration.status,
        "agent_progress": orchestration.agent_progress,
        "agent_outputs": orchestration.agent_outputs,
        "outputs": orchestration.outputs,
        "logs": orchestration.logs,
        "error": orchestration.error,
        "total_cost": orchestration.total_cost,
        "total_tokens": orchestration.total_tokens,
        "generated_agent_id": orchestration.generated_agent_id,
        "started_at": orchestration.started_at,
        "completed_at": orchestration.completed_at,
        "created_at": orchestration.created_at
    }


@app.get("/api/orchestrations/{orchestration_id}/stream")
async def stream_orchestration(orchestration_id: int):
    """Stream orchestration logs and status updates via SSE."""

    async def event_generator():
        last_log_length = 0
        last_status = None

        while True:
            with Session(engine) as session:
                orchestration = session.get(Orchestration, orchestration_id)
                if not orchestration:
                    payload = {"event": "error", "data": "Orchestration not found"}
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

                logs = orchestration.logs or ""
                if len(logs) > last_log_length:
                    new_chunk = logs[last_log_length:]
                    last_log_length = len(logs)
                    payload = {"event": "log", "data": new_chunk}
                    yield f"data: {json.dumps(payload)}\n\n"

                status_value = (
                    orchestration.status.value
                    if isinstance(orchestration.status, RunStatus)
                    else str(orchestration.status)
                )
                if status_value != last_status:
                    last_status = status_value
                    payload = {"event": "status", "data": status_value}
                    yield f"data: {json.dumps(payload)}\n\n"

                if orchestration.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                    break

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/coding/build")
async def create_coding_build(
    request: CodingBuildRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Create a fully autonomous coding build from natural language.

    This endpoint activates the Coding Orchestrator system which:
    1. Parses requirements from the prompt
    2. Coordinates specialized AI coders (frontend, backend, database, etc.)
    3. Implements self-correction loops with validation
    4. Produces production-ready code with zero errors
    5. Learns from each build to improve future results

    The orchestrator will iterate up to max_iterations times until
    quality_threshold is met or exceeded.
    """
    logger.info(f"Starting coding build: {request.prompt[:100]}...")

    # Create a Run record to track this build
    run = Run(
        status=RunStatus.QUEUED,
        prompt=request.prompt,
        inputs={
            "project_context": request.project_context or {},
            "tech_stack_preferences": request.tech_stack_preferences or {},
            "quality_threshold": request.quality_threshold or 0.95,
            "max_iterations": request.max_iterations or 5
        },
        created_at=datetime.utcnow()
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Queue the coding build job
    from workers.runner import run_coding_build_job
    background_tasks.add_task(run_coding_build_job, run.id, request.dict())

    logger.info(f"Created coding build run {run.id}")

    return {
        "run_id": run.id,
        "status": run.status,
        "message": "Coding build started - specialized AI coders are working on your request",
        "execution_mode": "coding_orchestrator"
    }


@app.get("/api/coding/builds/{run_id}")
async def get_coding_build(run_id: int, session: Session = Depends(get_session)):
    """Get detailed status and outputs from a coding build."""
    run = session.get(Run, run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Build not found")

    # Parse outputs for coding build specific data
    outputs = run.outputs or {}
    requirements = outputs.get("requirements", {})
    iterations = outputs.get("all_iterations", [])
    final_outputs = outputs.get("outputs", {})
    validation = outputs.get("validation", {})

    return {
        "id": run.id,
        "status": run.status,
        "prompt": run.prompt,
        "logs": run.logs,
        "error": run.error,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "total_cost": run.total_cost,
        "total_tokens": run.total_tokens,
        # Coding build specific fields
        "requirements": requirements,
        "project_name": requirements.get("project_name"),
        "project_type": requirements.get("project_type"),
        "tech_stack": requirements.get("tech_stack"),
        "complexity": requirements.get("complexity"),
        "iterations": len(iterations),
        "final_score": outputs.get("final_score"),
        "passed": outputs.get("passed"),
        "coders_used": list(final_outputs.keys()) if final_outputs else [],
        "validation": validation,
        "build_summary": outputs.get("build_summary"),
        "all_iterations": iterations,
        "codebase": final_outputs  # Complete generated code from all coders
    }


@app.get("/api/coding/builds/{run_id}/download")
async def download_coding_build(run_id: int, session: Session = Depends(get_session)):
    """
    Download the complete codebase from a coding build as a zip file.
    """
    import zipfile
    import io
    from fastapi.responses import Response

    run = session.get(Run, run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Build not found")

    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Build not completed yet")

    outputs = run.outputs or {}
    codebase = outputs.get("outputs", {})
    requirements = outputs.get("requirements", {})
    project_name = requirements.get("project_name", "codebase")

    # Create zip file in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add README
        readme = f"""# {project_name}

Generated by Smartsystem7 Coding Orchestrator

## Project Details
- Type: {requirements.get('project_type', 'unknown')}
- Tech Stack: {requirements.get('tech_stack', {})}
- Complexity: {requirements.get('complexity', 'unknown')}
- Quality Score: {outputs.get('final_score', 0):.2%}

## Build Summary
{outputs.get('build_summary', 'No summary available')}

## Generated Components
"""
        for coder_name in codebase.keys():
            readme += f"- {coder_name.upper()}\n"

        zip_file.writestr(f"{project_name}/README.md", readme)

        # Add each coder's output
        for coder_name, coder_output in codebase.items():
            if isinstance(coder_output, dict) and coder_output.get("success"):
                output_text = coder_output.get("output", "")
                zip_file.writestr(f"{project_name}/{coder_name}/{coder_name}_output.md", output_text)

        # Add build metadata
        import json
        metadata = {
            "prompt": run.prompt,
            "requirements": requirements,
            "final_score": outputs.get("final_score"),
            "iterations": outputs.get("iterations"),
            "validation": outputs.get("validation")
        }
        zip_file.writestr(f"{project_name}/build_metadata.json", json.dumps(metadata, indent=2))

    zip_buffer.seek(0)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project_name}.zip"}
    )


@app.get("/api/coding/builds/{run_id}/stream")
async def stream_coding_build(run_id: int):
    """Stream coding build logs and status updates via SSE."""

    async def event_generator():
        last_log_length = 0
        last_status = None

        while True:
            with Session(engine) as session:
                run = session.get(Run, run_id)
                if not run:
                    payload = {"event": "error", "data": "Build not found"}
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

                logs = run.logs or ""
                if len(logs) > last_log_length:
                    new_chunk = logs[last_log_length:]
                    last_log_length = len(logs)
                    payload = {"event": "log", "data": new_chunk}
                    yield f"data: {json.dumps(payload)}\n\n"

                status_value = run.status.value if isinstance(run.status, RunStatus) else str(run.status)
                if status_value != last_status:
                    last_status = status_value
                    payload = {"event": "status", "data": status_value}
                    yield f"data: {json.dumps(payload)}\n\n"

                # Send progress updates
                if run.outputs:
                    outputs = run.outputs
                    if outputs.get("final_score") is not None:
                        payload = {
                            "event": "progress",
                            "data": {
                                "score": outputs.get("final_score"),
                                "iteration": outputs.get("iterations", 0)
                            }
                        }
                        yield f"data: {json.dumps(payload)}\n\n"

                if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                    break

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ===== Telemetry & Dashboard Endpoints =====

@app.get("/api/telemetry/builds")
async def get_telemetry_builds(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None
):
    """
    Get paginated list of past builds from memory database.

    Args:
        limit: Maximum number of records (default 20)
        offset: Offset for pagination (default 0)
        status: Filter by status (optional)

    Returns:
        List of build records with telemetry data
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        builds = await memory_db.get_builds(limit=limit, offset=offset, status_filter=status)

        return {
            "builds": builds,
            "limit": limit,
            "offset": offset,
            "count": len(builds)
        }

    except Exception as e:
        logger.error(f"Failed to get telemetry builds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve builds: {str(e)}")


@app.get("/api/telemetry/builds/{run_id}")
async def get_telemetry_build(run_id: str):
    """
    Get full details for a specific build from memory database.

    Args:
        run_id: Build run ID

    Returns:
        Complete build record with model calls
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        build = await memory_db.get_build_by_id(run_id)

        if not build:
            raise HTTPException(status_code=404, detail="Build not found in memory database")

        # Get associated model calls
        model_calls = await memory_db.get_model_calls_for_run(run_id)

        return {
            "build": build,
            "model_calls": model_calls
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get build {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve build: {str(e)}")


@app.get("/api/telemetry/models")
async def get_telemetry_models():
    """
    Get average performance stats for all models.

    Returns:
        List of model statistics (latency, success rate, call counts)
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        model_stats = await memory_db.get_model_stats()

        return {
            "models": model_stats,
            "count": len(model_stats)
        }

    except Exception as e:
        logger.error(f"Failed to get model stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve model stats: {str(e)}")


@app.get("/api/telemetry/stats")
async def get_telemetry_stats():
    """
    Get overall telemetry statistics summary.

    Returns:
        Summary statistics for builds, models, and deployments
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        stats = await memory_db.get_stats_summary()

        return stats

    except Exception as e:
        logger.error(f"Failed to get telemetry stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stats: {str(e)}")


@app.get("/api/dashboard/deployments")
async def get_dashboard_deployments(limit: int = 20, offset: int = 0):
    """
    Get last N successful builds for dashboard display.

    Args:
        limit: Maximum number of records (default 20)
        offset: Offset for pagination (default 0)

    Returns:
        List of deployment records with GitHub and Vercel URLs
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        builds = await memory_db.get_builds(limit=limit, offset=offset, status_filter="completed")

        # Format for dashboard display
        deployments = []
        for build in builds:
            deployments.append({
                "run_id": build["run_id"],
                "prompt": build["prompt"][:100] + "..." if len(build["prompt"]) > 100 else build["prompt"],
                "quality": build["quality"],
                "model_map": build.get("model_map", {}),
                "repo_url": build.get("repo_url"),
                "vercel_url": build.get("vercel_url"),
                "created_at": build["created_at"],
                "duration_sec": build.get("duration_sec"),
                "project_type": build.get("project_type"),
                "tech_stack": build.get("tech_stack"),
                "github_deployed": build.get("github_deployed", False),
                "vercel_deployed": build.get("vercel_deployed", False),
            })

        return {
            "deployments": deployments,
            "limit": limit,
            "offset": offset,
            "count": len(deployments)
        }

    except Exception as e:
        logger.error(f"Failed to get dashboard deployments: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve deployments: {str(e)}")


@app.get("/api/dashboard/deployments/{run_id}")
async def get_dashboard_deployment(run_id: str):
    """
    Get full detail view for a specific deployment.

    Args:
        run_id: Build run ID

    Returns:
        Complete deployment record
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        build = await memory_db.get_build_by_id(run_id)

        if not build:
            raise HTTPException(status_code=404, detail="Deployment not found")

        # Get associated model calls
        model_calls = await memory_db.get_model_calls_for_run(run_id)

        return {
            "deployment": build,
            "model_calls": model_calls
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get deployment {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve deployment: {str(e)}")


# ===== Multi-Agent Chain Build Endpoints =====

class ChainBuildRequest(BaseModel):
    chain_name: str
    agent_ids: List[int]
    goal: str
    strategy: str = "sequential"  # "sequential", "parallel", "manager-led"


@app.post("/api/agents/chain-build")
async def create_chain_build(
    request: ChainBuildRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Start a multi-agent chain build.

    Coordinates multiple agents to work together on a single goal.
    Supports sequential, parallel, and manager-led execution strategies.

    Args:
        request: Chain build configuration

    Returns:
        Chain build ID and status
    """
    import uuid

    logger.info(
        f"Creating chain build '{request.chain_name}' with {len(request.agent_ids)} agents"
    )

    # Validate agents exist
    for agent_id in request.agent_ids:
        agent = session.get(Agent, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Generate chain ID
    chain_id = str(uuid.uuid4())

    # Create orchestration record to track the chain
    orchestration = Orchestration(
        agent_ids=request.agent_ids,
        prompt=f"[{request.chain_name}] {request.goal}",
        strategy=request.strategy,
        status=RunStatus.QUEUED,
        agent_progress={str(aid): 0 for aid in request.agent_ids},
        agent_outputs={},
        created_at=datetime.utcnow()
    )

    session.add(orchestration)
    session.commit()
    session.refresh(orchestration)

    # Queue the chain build job
    from workers.runner import run_chain_build_job
    try:
        background_tasks.add_task(
            run_chain_build_job,
            orchestration.id,
            chain_id,
            request.chain_name,
            request.agent_ids,
            request.goal,
            request.strategy
        )
    except ImportError:
        # Fallback: if worker not available, use inline execution
        logger.warning("Worker not available, executing chain inline (not recommended for production)")

    logger.info(f"Created chain build {chain_id} (orchestration {orchestration.id})")

    return {
        "chain_id": chain_id,
        "orchestration_id": orchestration.id,
        "status": "queued",
        "agent_count": len(request.agent_ids),
        "strategy": request.strategy,
        "message": "Multi-agent chain build started"
    }


@app.get("/api/agents/chain-builds/{chain_id}")
async def get_chain_build(chain_id: str):
    """
    Get aggregated outputs from a chain build.

    Args:
        chain_id: Chain build ID

    Returns:
        Chain build status and outputs
    """
    from app.services.memory_db import get_memory_db
    from app.config import settings

    try:
        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
        build = await memory_db.get_build_by_id(chain_id)

        if not build:
            raise HTTPException(status_code=404, detail="Chain build not found")

        # Get model calls for this chain
        model_calls = await memory_db.get_model_calls_for_run(chain_id)

        # Parse chain metadata from requirements
        requirements = build.get("requirements", {})
        agent_ids = requirements.get("agent_ids", [])
        strategy = requirements.get("strategy", "sequential")

        return {
            "chain_id": chain_id,
            "chain_name": requirements.get("chain_name", "Unnamed Chain"),
            "goal": build["prompt"].replace("[CHAIN: ", "").split("]", 1)[-1].strip(),
            "status": build["status"],
            "quality": build["quality"],
            "agent_ids": agent_ids,
            "strategy": strategy,
            "duration_sec": build.get("duration_sec"),
            "created_at": build["created_at"],
            "model_calls": model_calls,
            "error": build.get("error")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chain build {chain_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chain build: {str(e)}")


@app.get("/api/agents/chain-builds/{chain_id}/stream")
async def stream_chain_build(chain_id: str):
    """
    Live SSE stream of chain build progress.

    Args:
        chain_id: Chain build ID

    Returns:
        Server-Sent Events stream with progress updates
    """

    async def event_generator():
        """Generate SSE events for chain build progress."""
        last_status = None
        check_count = 0
        max_checks = 300  # 5 minutes at 1s intervals

        while check_count < max_checks:
            try:
                from app.services.memory_db import get_memory_db
                from app.config import settings

                memory_db = await get_memory_db(settings.MEMORY_DB_PATH)
                build = await memory_db.get_build_by_id(chain_id)

                if not build:
                    if check_count == 0:
                        # Not found on first check
                        payload = {"event": "error", "data": "Chain build not found"}
                        yield f"data: {json.dumps(payload)}\n\n"
                        break
                    else:
                        # Wait for it to be created
                        await asyncio.sleep(1)
                        check_count += 1
                        continue

                # Send status updates
                status = build["status"]
                if status != last_status:
                    last_status = status
                    payload = {"event": "status", "data": status}
                    yield f"data: {json.dumps(payload)}\n\n"

                # Send progress data
                payload = {
                    "event": "progress",
                    "data": {
                        "quality": build["quality"],
                        "duration_sec": build.get("duration_sec", 0)
                    }
                }
                yield f"data: {json.dumps(payload)}\n\n"

                # Check if completed
                if status in ["completed", "failed"]:
                    payload = {
                        "event": "complete" if status == "completed" else "error",
                        "data": build.get("error", "Chain build completed")
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

            except Exception as e:
                logger.error(f"Error streaming chain build {chain_id}: {e}")
                payload = {"event": "error", "data": str(e)}
                yield f"data: {json.dumps(payload)}\n\n"
                break

            await asyncio.sleep(1)
            check_count += 1

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
