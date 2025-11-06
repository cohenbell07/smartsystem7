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
    Orchestration,
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


class SetKeysRequest(BaseModel):
    keys: dict[str, str]


class CreateRepoRequest(BaseModel):
    pass  # No body needed, uses agent_id from path


class CreateOrchestrationRequest(BaseModel):
    agent_ids: List[int]
    prompt: str
    strategy: str = "manager-led"  # "sequential", "parallel", "manager-led"


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
