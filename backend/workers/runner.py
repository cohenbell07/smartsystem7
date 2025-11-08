"""
Background job runner for research and agent execution.
"""

import logging
import asyncio
import json
import os
import re
from datetime import datetime
from textwrap import shorten
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
import copy
from sqlmodel import Session, select
from app.database import engine
from app.models import (
    Project,
    ProjectStatus,
    ResearchSource,
    Run,
    RunStatus,
    Artifact,
    Orchestration,
    Agent,
)
from app.research import (
    search_web,
    crawl_urls,
    deduplicate_sources,
    synthesize_research,
    calculate_viability_score,
)
from app.services import LLMRouter, NotificationService, calculate_actual_cost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _init_vector_store():
    """Initialize vector store to ensure it's ready before agent jobs begin."""
    try:
        from app.agents.tools.vector_memory import VectorMemoryTool
        VectorMemoryTool()
        logger.info("Vector store initialized successfully.")
    except Exception as e:
        logger.error(f"Vector store initialization failed: {e}")
        raise


def _append_with_timestamp(existing: Optional[str], message: str) -> str:
    """Append a timestamped line to an existing log string."""

    timestamp = datetime.utcnow().isoformat()
    return (existing or "") + f"[{timestamp}] {message}\n"


def _calculate_cost_metrics(
    token_usage: Optional[list[dict]],
    fallback_total_cost: Optional[float],
) -> Tuple[Optional[float], Optional[int]]:
    """Derive total cost and tokens from usage breakdown."""

    total_tokens = 0
    cost_from_usage = 0.0
    has_usage_cost = False

    for entry in token_usage or []:
        usage = entry.get("usage", {}) or {}
        tokens = usage.get("total_tokens")
        if tokens:
            total_tokens += tokens

        step_cost = entry.get("cost")
        if step_cost is not None:
            cost_from_usage += step_cost
            has_usage_cost = True

    if fallback_total_cost is not None:
        total_cost_value: Optional[float] = fallback_total_cost
    elif has_usage_cost:
        total_cost_value = cost_from_usage
    else:
        total_cost_value = None

    total_tokens_value: Optional[int] = total_tokens or None
    return total_cost_value, total_tokens_value


def _generate_agent_name(question: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", question or "").strip()
    tokens = [token.capitalize() for token in cleaned.split() if token]
    if not tokens:
        return "Adaptive Research Agent"
    name = " ".join(tokens[:4])
    if not name.lower().endswith("agent"):
        name = f"{name} Agent"
    return name


def _format_viability_summary(viability: Dict[str, Any]) -> str:
    if not isinstance(viability, dict):
        return ""
    lines: list[str] = []
    for key, value in viability.items():
        pretty_key = key.replace("_", " ").title()
        if isinstance(value, (int, float)):
            lines.append(f"- {pretty_key}: {value}")
        elif isinstance(value, str) and value.strip():
            lines.append(f"- {pretty_key}: {value.strip()}")
    return "\n".join(lines)


def build_default_agent_spec(
    question: str,
    research_brief: str,
    viability: Dict[str, Any],
    default_model: str,
) -> Dict[str, Any]:
    """Construct a multi-node agent specification tailored to the research output."""

    agent_name = _generate_agent_name(question)
    viability_summary = _format_viability_summary(viability)
    research_excerpt = shorten(research_brief or "", width=1200, placeholder="…")

    narrative_context = (
        f"Question: {question}\n\n"
        f"Research Summary:\n{research_excerpt}\n\n"
        f"Viability Insights:\n{viability_summary or 'No viability data provided.'}"
    )

    base_inputs_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Primary user prompt or task description."},
            "context": {"type": "object", "description": "Shared context from prior nodes."},
            "agent_id": {"type": "integer", "description": "Identifier of the executing agent."},
        },
        "required": ["prompt"],
    }

    nodes = [
        {
            "name": "ReasoningLLM",
            "type": "llm",
            "model": default_model,
            "description": "Primary reasoning node that decomposes the task, drafts plans, and determines which tools to invoke.",
            "prompt_template": (
                "You are the lead coordinator. Analyse the question and research context.\n"
                "Create a concise plan, identify sub-problems, and outline how tools should be used.\n"
                "Inputs: {inputs}\nContext: {context}\n"
                "Respond with a step-by-step plan plus answer draft."
            ),
            "inputs_schema": base_inputs_schema,
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "plan": {"type": "string"},
                    "answer_draft": {"type": "string"},
                },
            },
        },
        {
            "name": "WebSearch",
            "type": "tool",
            "tool": "web_search",
            "description": "Performs targeted web searches to gather fresh evidence and data points.",
            "inputs_schema": base_inputs_schema,
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                },
            },
        },
        {
            "name": "PythonExecutor",
            "type": "tool",
            "tool": "python_executor",
            "description": "Runs lightweight Python code for computations, validations, or data wrangling.",
            "inputs_schema": {
                **base_inputs_schema,
                "properties": {
                    **base_inputs_schema["properties"],
                    "code": {"type": "string", "description": "Python snippet to execute."},
                },
            },
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "success": {"type": "boolean"},
                },
            },
        },
        {
            "name": "FileWriter",
            "type": "tool",
            "tool": "file_writer",
            "description": "Persists generated reports or artifacts to disk for downstream retrieval.",
            "inputs_schema": {
                **base_inputs_schema,
                "properties": {
                    **base_inputs_schema["properties"],
                    "content": {"type": "string", "description": "Document body to store."},
                    "filename": {"type": "string", "description": "Optional filename."},
                    "artifact_type": {"type": "string", "description": "Artifact mime/type hint."},
                },
            },
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "artifact": {"type": "object"},
                },
            },
        },
        {
            "name": "MemoryManager",
            "type": "tool",
            "tool": "memory_manager",
            "description": "Stores and retrieves short-term memory so subsequent runs can leverage new insights.",
            "inputs_schema": {
                **base_inputs_schema,
                "properties": {
                    **base_inputs_schema["properties"],
                    "action": {"type": "string", "enum": ["store", "recall"], "default": "store"},
                    "text": {"type": "string", "description": "Content to remember."},
                    "query": {"type": "string", "description": "Query when recalling memories."},
                },
            },
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "results": {"type": "array"},
                },
            },
        },
        {
            "name": "Validator",
            "type": "validator",
            "model": "gpt-4o-mini",
            "inputs_from": ["ReasoningLLM", "PythonExecutor", "WebSearch"],
            "tool_nodes": ["WebSearch", "PythonExecutor", "MemoryManager", "FileWriter"],
            "description": "Self-check node that reviews candidate answers for correctness and completeness.",
            "prompt_template": (
                "You are validating the solution. Candidate answer:\n{candidate_answer}\n\n"
                "Evidence and context:\n{context}\n\n"
                "Return JSON with fields verdict ('pass'|'fail'), issues (array of strings), "
                "improvements (array of strings), confidence (0-1)."
            ),
            "inputs_schema": base_inputs_schema,
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string"},
                    "issues": {"type": "array"},
                    "improvements": {"type": "array"},
                },
            },
        },
        {
            "name": "Aggregator",
            "type": "aggregator",
            "model": default_model,
            "reasoning_node": "ReasoningLLM",
            "validator_node": "Validator",
            "tool_nodes": ["WebSearch", "PythonExecutor", "FileWriter", "MemoryManager"],
            "description": "Synthesises reasoning, tool results, and validator feedback into the final answer.",
            "prompt_template": (
                "Produce the final response for the user. Incorporate reasoning, tool results, validator feedback, "
                "and research insights. Respond in JSON with keys final_answer, summary, actions, warnings."
            ),
            "inputs_schema": base_inputs_schema,
            "outputs_schema": {
                "type": "object",
                "properties": {
                    "final_answer": {"type": "string"},
                    "summary": {"type": "string"},
                    "actions": {"type": "array"},
                    "warnings": {"type": "array"},
                },
            },
        },
    ]

    edges = [
        {"from": "ReasoningLLM", "to": "WebSearch"},
        {"from": "ReasoningLLM", "to": "PythonExecutor"},
        {"from": "ReasoningLLM", "to": "MemoryManager"},
        {"from": "ReasoningLLM", "to": "FileWriter"},
        {"from": "WebSearch", "to": "Validator"},
        {"from": "PythonExecutor", "to": "Validator"},
        {"from": "MemoryManager", "to": "Validator"},
        {"from": "Validator", "to": "Aggregator"},
    ]

    return {
        "version": "1.0",
        "name": agent_name,
        "description": f"Adaptive multi-node agent derived from research on '{question}'.",
        "objective": f"Provide an end-to-end solution for: {question}",
        "graph_type": "multi_node",
        "default_model": default_model,
        "instructions": narrative_context,
        "execution": {
            "modes": ["sequential", "parallel"],
            "default": "sequential",
        },
        "tools": ["web_search", "python_executor", "file_writer", "memory_manager"],
        "apis": [
            {"name": "OPENAI_API_KEY", "required": True, "reason": "LLM reasoning, validation, and aggregation."},
            {"name": "BING_SEARCH_API_KEY", "required": False, "reason": "Web search fallback provider."},
            {"name": "SERPAPI_KEY", "required": False, "reason": "Web search provider for SERP results."},
        ],
        "nodes": nodes,
        "edges": edges,
        "success_criteria": [
            "Produces a validated answer with clear reasoning.",
            "Stores key learnings in short-term memory.",
            "Emits artifacts or reports when appropriate.",
        ],
        "test_plan": [
            "Verify the reasoning node creates a multi-step plan.",
            "Ensure the validator catches intentional errors in the reasoning chain.",
            "Confirm the aggregator returns a structured JSON response.",
        ],
        "metadata": {
            "viability": viability,
            "viability_summary": viability_summary,
        },
    }


async def _execute_agent_spec(
    agent_spec: Dict[str, Any],
    inputs: Dict[str, Any],
    llm_router: LLMRouter,
    log_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """Compile and execute an agent specification, returning final state."""

    from app.agents.factory import create_agent_from_spec, AgentState
    from app.agents.tools import (
        BrowserTool,
        GitHubTool,
        EmailTool,
        VectorMemoryTool,
        WebSearchTool,
        FileWriterTool,
        MemoryManagerTool,
        CodeExecutor,
    )

    vector_memory_tool = VectorMemoryTool()

    tools = {
        "browser": BrowserTool(),
        "github": GitHubTool(),
        "email": EmailTool(),
        "vector_memory": vector_memory_tool,
        "web_search": WebSearchTool(),
        "python_executor": CodeExecutor(),
        "file_writer": FileWriterTool(),
        "memory_manager": MemoryManagerTool(vector_memory_tool),
    }
    # Backwards compatibility aliases
    tools["code_executor"] = tools["python_executor"]

    spec_copy = copy.deepcopy(agent_spec)

    # Ensure aggregator executes only after validator to avoid concurrent writes
    edges = spec_copy.get("edges", [])
    if edges:
        filtered_edges = []
        for edge in edges:
            if edge.get("to") == "Aggregator" and edge.get("from") != "Validator":
                continue
            filtered_edges.append(edge)
        spec_copy["edges"] = filtered_edges

    graph = create_agent_from_spec(
        spec=spec_copy,
        llm_router=llm_router,
        tools=tools,
        approval_callback=None,
        log_callback=log_callback,
    )

    initial_state: AgentState = {
        "messages": [],
        "inputs": inputs,
        "outputs": {},
        "artifacts": [],
        "step_count": 0,
        "errors": [],
        "token_usage": [],
        "total_cost": 0.0,
        "node_metrics": [],
        "node_status": {},
    }

    if log_callback:
        await log_callback("🚀 Agent workflow started")

    final_state = await graph.ainvoke(initial_state)

    if log_callback:
        await log_callback("🏁 Agent workflow completed")

    return final_state


async def run_research_job(project_id: int):
    """
    Execute research pipeline for a project.

    Steps:
    1. Search web (50+ sources)
    2. Crawl content
    3. Deduplicate
    4. Synthesize brief
    5. Calculate viability score
    6. Generate agent spec
    """
    logger.info(f"Starting research job for project {project_id}")

    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            logger.error(f"Project {project_id} not found")
            return

        try:
            # Update status
            project.status = ProjectStatus.RESEARCHING
            session.add(project)
            session.commit()

            # Step 1: Search web
            logger.info("Step 1: Searching web...")
            search_results = await search_web(
                project.question,
                count=int(os.getenv("MAX_RESEARCH_SOURCES", "50"))
            )
            logger.info(f"Found {len(search_results)} search results")

            # Step 2: Crawl URLs
            logger.info("Step 2: Crawling content...")
            urls = [r["url"] for r in search_results[:50]]
            crawled = await crawl_urls(urls, use_playwright=False, max_concurrent=10)
            logger.info(f"Crawled {len(crawled)} URLs successfully")

            # Save sources
            for source_data in crawled:
                source = ResearchSource(
                    project_id=project.id,
                    url=source_data["url"],
                    title=source_data.get("title"),
                    content=source_data.get("content"),
                    metadata=source_data.get("metadata", {}),
                )
                session.add(source)
            session.commit()

            # Step 3: Deduplicate
            logger.info("Step 3: Deduplicating...")
            unique_sources = deduplicate_sources(crawled, similarity_threshold=3)
            logger.info(f"After deduplication: {len(unique_sources)} unique sources")

            project.sources_count = len(unique_sources)
            session.add(project)
            session.commit()

            # Step 4: Synthesize research
            logger.info("Step 4: Synthesizing research...")
            project.status = ProjectStatus.ANALYZING
            session.add(project)
            session.commit()

            llm_router = LLMRouter()
            synthesis = await synthesize_research(
                project.question,
                unique_sources,
                model=os.getenv("DEFAULT_LLM", "gpt-4o-mini")
            )

            project.research_brief = synthesis["summary"]
            session.add(project)
            session.commit()

            # Step 5: Calculate viability score
            logger.info("Step 5: Calculating viability score...")
            viability = await calculate_viability_score(
                project.question,
                synthesis["summary"],
                model=os.getenv("DEFAULT_LLM", "gpt-4o-mini")
            )

            project.viability_score = viability["overall"]
            project.viability_rationale = json.dumps({
                "market_demand": viability["market_demand"],
                "competition": viability["competition"],
                "feasibility": viability["feasibility"],
                "capital_requirement": viability["capital_requirement"],
                "moat": viability["moat"],
                "rationale": viability["rationale"],
            })
            project.sensitivity_analysis = json.dumps(viability.get("sensitivity", {}))
            session.add(project)
            session.commit()

            # Step 6: Generate agent spec
            logger.info("Step 6: Generating agent spec...")
            agent_spec = await generate_agent_spec(
                project.question,
                synthesis["summary"],
                viability,
                llm_router
            )

            project.agent_spec = agent_spec
            project.status = ProjectStatus.SPEC_GENERATED
            project.completed_at = datetime.utcnow()
            session.add(project)
            session.commit()

            # Persist generated agent to portfolio
            agent_name = (agent_spec.get("name") or f"Agent {project.id}").strip()
            if not agent_name:
                agent_name = f"Project {project.id} Agent"

            default_model = (
                agent_spec.get("default_model")
                or agent_spec.get("model")
                or os.getenv("DEFAULT_LLM", "gpt-4o-mini")
            )

            instructions = (
                agent_spec.get("instructions")
                or agent_spec.get("objective")
                or project.research_brief
                or project.question
            )

            existing_agent = session.exec(
                select(Agent).where(Agent.source_project_id == project.id)
            ).first()

            if existing_agent:
                existing_agent.name = agent_name
                existing_agent.description = agent_spec.get("description") or project.question
                existing_agent.agent_spec = agent_spec
                existing_agent.default_model = default_model
                existing_agent.instructions = instructions
                existing_agent.updated_at = datetime.utcnow()
                agent_record = existing_agent
            else:
                agent_record = Agent(
                    name=agent_name,
                    description=agent_spec.get("description") or project.question,
                    agent_spec=agent_spec,
                    default_model=default_model,
                    instructions=instructions,
                    source_project_id=project.id,
                    user_id=project.user_id,
                )
                session.add(agent_record)

            session.commit()
            session.refresh(agent_record)
            logger.info(
                f"Generated agent {agent_record.id} ('{agent_record.name}') for project {project_id}"
            )

            logger.info(f"Research job completed for project {project_id}")

            # Send notification
            notification_service = NotificationService()
            await notification_service.notify_completion(
                project_id=project.id,
                project_name=project.question[:50],
                status="Completed",
                result_url=f"http://localhost:3000/projects/{project.id}",
                email=None,  # TODO: Get from user settings
            )

        except Exception as e:
            logger.error(f"Research job failed for project {project_id}: {e}", exc_info=True)
            project.status = ProjectStatus.FAILED
            session.add(project)
            session.commit()


async def generate_agent_spec(question: str, research_brief: str, viability: dict, llm_router: LLMRouter) -> dict:
    """
    Generate a deterministic, production-ready multi-node agent specification.

    The llm_router parameter is kept for backward compatibility; generation is template-driven.
    """
    default_model = os.getenv("DEFAULT_LLM", "gpt-4o-mini")
    logger.info(f"Building default agent spec for '{question[:80]}...' with model={default_model}")
    return build_default_agent_spec(
        question=question,
        research_brief=research_brief,
        viability=viability or {},
        default_model=default_model,
    )


async def run_agent_job(run_id: int):
    """
    Execute an agent graph.
    """
    logger.info(f"Starting agent execution for run {run_id}")

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if not run:
            logger.error(f"Run {run_id} not found")
            return

        try:
            # Update status
            run.status = RunStatus.RUNNING
            run.started_at = datetime.utcnow()
            run.logs = _append_with_timestamp(run.logs, "Run picked up by worker")
            session.add(run)
            session.commit()

            # Resolve agent spec
            agent_label = f"Run {run.id}"
            agent_spec: Optional[Dict[str, Any]] = None

            if run.agent_id:
                agent = session.get(Agent, run.agent_id)
                if not agent:
                    raise ValueError(f"Agent {run.agent_id} not found")
                agent_spec = agent.agent_spec
                agent_label = agent.name or f"Agent {agent.id}"
            elif run.project_id:
                project = session.get(Project, run.project_id)
                if not project:
                    raise ValueError(f"Project {run.project_id} not found")
                agent_spec = project.agent_spec
                agent_label = project.question[:60]

            if not agent_spec:
                raise ValueError("No agent spec available")

            async def append_log(message: str) -> None:
                run.logs = _append_with_timestamp(run.logs, message)
                session.add(run)
                session.commit()

            await append_log(f"Loaded agent spec for '{agent_label}'")

            llm_router = LLMRouter()

            inputs: Dict[str, Any] = dict(run.inputs or {})
            if run.prompt:
                inputs.setdefault("prompt", run.prompt)
            inputs.setdefault("question", agent_spec.get("objective") or agent_label)
            inputs.setdefault(
                "research_brief",
                agent_spec.get("instructions") or agent_spec.get("description")
            )
            if run.agent_id:
                inputs.setdefault("agent_id", run.agent_id)
            context_block = dict(inputs.get("context") or {})
            context_block.setdefault("agent_name", agent_label)
            context_block.setdefault("run_id", run.id)
            context_block.setdefault(
                "viability_summary",
                agent_spec.get("metadata", {}).get("viability_summary"),
            )
            inputs["context"] = context_block

            async def agent_log(message: str) -> None:
                await append_log(f"[{agent_label}] {message}")

            final_state = await _execute_agent_spec(
                agent_spec=agent_spec,
                inputs=inputs,
                llm_router=llm_router,
                log_callback=agent_log,
            )

            final_outputs = final_state.get("outputs", {}) or {}
            if not isinstance(final_outputs, dict):
                final_outputs = {"result": final_outputs}

            node_metrics = final_state.get("node_metrics")
            node_status = final_state.get("node_status")
            if node_metrics:
                final_outputs["node_metrics"] = node_metrics
            if node_status:
                final_outputs["node_status"] = node_status

            run.outputs = final_outputs
            await append_log(f"Completed {final_state.get('step_count', 0)} steps")

            token_usage = final_state.get("token_usage") or []
            total_cost, total_tokens = _calculate_cost_metrics(
                token_usage,
                final_state.get("total_cost"),
            )

            if token_usage:
                run.token_usage = token_usage
                breakdown = {
                    "total_cost": total_cost,
                    "total_tokens": total_tokens,
                    "breakdown": token_usage,
                }
                if run.cost_breakdown:
                    run.cost_breakdown["actual"] = breakdown
                else:
                    run.cost_breakdown = {"actual": breakdown}

            if total_cost is not None:
                run.actual_cost = total_cost
                run.total_cost = total_cost
                logger.info(f"Run {run_id} actual cost: ${total_cost:.4f}")
                await append_log(f"Actual cost ${total_cost:.4f}")

            if total_tokens is not None:
                run.total_tokens = total_tokens
                await append_log(f"Token usage: {total_tokens} tokens")

            final_answer_payload = final_outputs.get("final_output")
            if final_answer_payload:
                if isinstance(final_answer_payload, dict):
                    rendered_answer = json.dumps(final_answer_payload, ensure_ascii=False, default=str)
                else:
                    rendered_answer = str(final_answer_payload)
                await append_log(f"🏁 Final answer:\n{rendered_answer}")

            # Persist artifacts
            for artifact_data in final_state.get("artifacts", []):
                artifact = Artifact(
                    run_id=run.id,
                    project_id=run.project_id,
                    name=artifact_data["name"],
                    artifact_type=artifact_data.get("type", "text"),
                    content=artifact_data["content"],
                )
                session.add(artifact)

            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()

            logger.info(f"Agent execution completed for run {run_id}")

        except Exception as e:
            logger.error(f"Agent execution failed for run {run_id}: {e}", exc_info=True)
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.utcnow()
            run.logs = _append_with_timestamp(run.logs, f"❌ Run failed: {e}")
            session.add(run)
            session.commit()


async def run_agent_prompt_job(run_id: int):
    """
    Execute an agent with a direct prompt using the LangGraph runtime.

    This mirrors run_agent_job but is triggered when the user supplies an
    ad-hoc prompt from the frontend "Run Agent" button.
    """
    logger.info(f"Starting agent prompt execution for run {run_id}")

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if not run:
            logger.error(f"Run {run_id} not found")
            return

        try:
            # Update status
            run.status = RunStatus.RUNNING
            run.started_at = datetime.utcnow()
            run.logs = _append_with_timestamp(run.logs, "Starting multi-agent runtime execution...")
            session.add(run)
            session.commit()

            async def append_log(message: str) -> None:
                run.logs = _append_with_timestamp(run.logs, message)
                session.add(run)
                session.commit()

            # Get agent
            from app.models import Agent
            agent = session.get(Agent, run.agent_id)
            if not agent:
                raise ValueError(f"Agent {run.agent_id} not found")

            await append_log(f"Agent: {agent.name}")
            await append_log(f"Prompt: {run.prompt}")

            # Resolve agent spec
            agent_spec = agent.agent_spec
            if not agent_spec:
                raise ValueError("Agent specification is missing; please rebuild the agent.")

            await append_log(f"Loaded agent spec with {len(agent_spec.get('nodes', []))} nodes")

            llm_router = LLMRouter()

            inputs: Dict[str, Any] = dict(run.inputs or {})
            if run.prompt:
                inputs.setdefault("prompt", run.prompt)
            inputs.setdefault("question", agent.description or agent.name)
            inputs.setdefault("agent_id", agent.id)
            inputs.setdefault("research_brief", agent.instructions or agent.description)

            context_block = dict(inputs.get("context") or {})
            context_block.setdefault("agent_name", agent.name)
            context_block.setdefault("run_id", run.id)
            context_block.setdefault("viability_summary", agent.agent_spec.get("metadata", {}).get("viability_summary"))
            inputs["context"] = context_block

            async def agent_log(message: str) -> None:
                await append_log(f"[{agent.name}] {message}")

            final_state = await _execute_agent_spec(
                agent_spec=agent_spec,
                inputs=inputs,
                llm_router=llm_router,
                log_callback=agent_log,
            )

            final_outputs = final_state.get("outputs", {}) or {}
            if not isinstance(final_outputs, dict):
                final_outputs = {"result": final_outputs}

            node_metrics = final_state.get("node_metrics")
            node_status = final_state.get("node_status")
            if node_metrics:
                final_outputs["node_metrics"] = node_metrics
            if node_status:
                final_outputs["node_status"] = node_status

            run.outputs = final_outputs

            await append_log(f"Completed {final_state.get('step_count', 0)} steps")

            token_usage = final_state.get("token_usage") or []
            total_cost, total_tokens = _calculate_cost_metrics(
                token_usage,
                final_state.get("total_cost"),
            )

            if token_usage:
                run.token_usage = token_usage
                breakdown = {
                    "total_cost": total_cost,
                    "total_tokens": total_tokens,
                    "breakdown": token_usage,
                }
                if run.cost_breakdown:
                    run.cost_breakdown["actual"] = breakdown
                else:
                    run.cost_breakdown = {"actual": breakdown}

            if total_cost is not None:
                run.actual_cost = total_cost
                run.total_cost = total_cost
                await append_log(f"Actual cost ${total_cost:.4f}")

            if total_tokens is not None:
                run.total_tokens = total_tokens
                await append_log(f"Token usage: {total_tokens} tokens")

            final_answer_payload = final_outputs.get("final_output")
            if final_answer_payload:
                if isinstance(final_answer_payload, dict):
                    rendered_answer = json.dumps(final_answer_payload, ensure_ascii=False, default=str)
                else:
                    rendered_answer = str(final_answer_payload)
                await append_log(f"🏁 Final answer:\n{rendered_answer}")

            # Persist artifacts emitted by the graph
            for artifact_data in final_state.get("artifacts", []):
                artifact = Artifact(
                    run_id=run.id,
                    project_id=run.project_id,
                    name=artifact_data["name"],
                    artifact_type=artifact_data.get("type", "text"),
                    content=artifact_data["content"],
                )
                session.add(artifact)

            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()

            logger.info(f"Agent prompt execution completed for run {run_id}")

        except Exception as e:
            logger.error(f"Agent prompt execution failed for run {run_id}: {e}", exc_info=True)
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.logs = _append_with_timestamp(run.logs, f"❌ Run failed: {e}")
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()


async def run_orchestration_job(orchestration_id: int):
    """
    Execute a multi-agent orchestration.

    Coordinates multiple agents to work on a task collaboratively.
    Supports strategies: manager-led, sequential, parallel.
    """
    logger.info(f"Starting orchestration job {orchestration_id}")

    with Session(engine) as session:
        orchestration = session.get(Orchestration, orchestration_id)
        if not orchestration:
            logger.error(f"Orchestration {orchestration_id} not found")
            return

        try:
            orchestration.status = RunStatus.RUNNING
            orchestration.started_at = datetime.utcnow()
            orchestration.logs = _append_with_timestamp(
                orchestration.logs, "Orchestration picked up by worker"
            )
            if orchestration.agent_outputs is None:
                orchestration.agent_outputs = {}
            if orchestration.agent_progress is None:
                orchestration.agent_progress = {}
            if orchestration.outputs is None:
                orchestration.outputs = {}
            session.add(orchestration)
            session.commit()

            async def append_log(message: str) -> None:
                orchestration.logs = _append_with_timestamp(orchestration.logs, message)
                session.add(orchestration)
                session.commit()

            agents: list[Agent] = []
            for agent_id in orchestration.agent_ids:
                agent = session.get(Agent, agent_id)
                if not agent:
                    raise ValueError(f"Agent {agent_id} not found")
                agents.append(agent)

            await append_log(
                f"Loaded agents: {', '.join(agent.name for agent in agents) or 'none'}"
            )

            llm_router = LLMRouter()

            total_cost_accum = 0.0
            total_tokens_accum = 0
            cost_present = False
            tokens_present = False

            def record_metrics(cost: Optional[float], tokens: Optional[int]) -> None:
                nonlocal total_cost_accum, total_tokens_accum, cost_present, tokens_present
                if cost is not None:
                    total_cost_accum += cost
                    cost_present = True
                if tokens is not None:
                    total_tokens_accum += tokens
                    tokens_present = True

            if orchestration.strategy == "manager-led":
                await append_log("Strategy: manager-led")
                from app.agents.manager import AgentManager
                from app.agents.tools import (
                    BrowserTool,
                    GitHubTool,
                    EmailTool,
                    VectorMemoryTool,
                    APICaller,
                    CodeExecutor,
                    WebSearchTool,
                    FileWriterTool,
                    MemoryManagerTool,
                )

                vector_memory = VectorMemoryTool()
                code_executor = CodeExecutor()
                tools = {
                    "browser": BrowserTool(),
                    "github": GitHubTool(),
                    "email": EmailTool(),
                    "vector_memory": vector_memory,
                    "api_caller": APICaller(),
                    "code_executor": code_executor,
                    "python_executor": code_executor,
                    "web_search": WebSearchTool(),
                    "file_writer": FileWriterTool(),
                    "memory_manager": MemoryManagerTool(vector_memory),
                }

                composite_context = {
                    "name": "Multi-Agent Orchestrator",
                    "description": f"Orchestrating {len(agents)} agents",
                    "agents": [
                        {
                            "id": agent.id,
                            "name": agent.name,
                            "description": agent.description,
                            "tools": agent.agent_spec.get("tools", []),
                        }
                        for agent in agents
                    ],
                    "tools": list(tools.keys()),
                }

                agent_manager = AgentManager(
                    llm_router=llm_router,
                    tools=tools,
                    vector_memory=vector_memory,
                )

                workflow_results = await agent_manager.execute_workflow(
                    user_prompt=orchestration.prompt,
                    agent_id=f"orchestration_{orchestration_id}",
                    agent_context=composite_context,
                )

                orchestration.outputs = {
                    "workflow_status": workflow_results.get("status"),
                    "intent": workflow_results.get("intent", {}),
                    "steps": workflow_results.get("steps", []),
                    "sub_agent_results": workflow_results.get("sub_agent_results", []),
                    "final_output": workflow_results.get("output", ""),
                    "logs": workflow_results.get("logs", []),
                }

                manager_usage = []
                sub_results = workflow_results.get("sub_agent_results", [])
                for idx, sub_result in enumerate(sub_results):
                    agent_ref = agents[idx] if idx < len(agents) else None
                    agent_key = str(agent_ref.id) if agent_ref else str(idx)
                    orchestration.agent_outputs[agent_key] = sub_result.get("output", "")
                    orchestration.agent_progress[agent_key] = 100

                    usage = sub_result.get("tokens_used") or {}
                    if usage:
                        model_name = (
                            agent_ref.default_model
                            if agent_ref and agent_ref.default_model
                            else llm_router.default_model
                        )
                        step_cost = calculate_actual_cost(usage, model_name)
                        manager_usage.append(
                            {
                                "agent_id": agent_ref.id if agent_ref else None,
                                "usage": usage,
                                "cost": step_cost,
                            }
                        )
                        record_metrics(step_cost, usage.get("total_tokens"))

                if manager_usage:
                    orchestration.outputs["token_usage"] = manager_usage

                for log_entry in workflow_results.get("logs", []):
                    orchestration.logs = _append_with_timestamp(
                        orchestration.logs, log_entry
                    )
                    session.add(orchestration)
                session.commit()

            elif orchestration.strategy == "sequential":
                await append_log("Strategy: sequential")
                sequential_results = []
                token_usage_log = []
                node_metrics_log: list[dict[str, Any]] = []

                def make_agent_logger(agent_name: str) -> Callable[[str], Awaitable[None]]:
                    async def agent_logger(message: str) -> None:
                        await append_log(f"[{agent_name}] {message}")

                    return agent_logger

                for position, agent in enumerate(agents, start=1):
                    agent_key = str(agent.id)
                    orchestration.agent_progress[agent_key] = 0
                    await append_log(
                        f"▶️ Sequential agent {position}/{len(agents)}: {agent.name}"
                    )

                    agent_inputs = {
                        "prompt": orchestration.prompt,
                        "previous_results": sequential_results,
                    }

                    final_state = await _execute_agent_spec(
                        agent_spec=agent.agent_spec,
                        inputs=agent_inputs,
                        llm_router=llm_router,
                        log_callback=make_agent_logger(agent.name),
                    )

                    outputs = final_state.get("outputs", {})
                    sequential_results.append(outputs)
                    orchestration.agent_outputs[agent_key] = outputs
                    orchestration.agent_progress[agent_key] = 100

                    token_usage = final_state.get("token_usage") or []
                    cost, tokens = _calculate_cost_metrics(
                        token_usage, final_state.get("total_cost")
                    )
                    record_metrics(cost, tokens)
                    if token_usage:
                        token_usage_log.append(
                            {
                                "agent_id": agent.id,
                                "token_usage": token_usage,
                                "cost": cost,
                                "tokens": tokens,
                            }
                        )
                    node_metrics = final_state.get("node_metrics") or []
                    for metric in node_metrics:
                        entry = dict(metric)
                        entry["agent_id"] = agent.id
                        node_metrics_log.append(entry)

                orchestration.outputs = {
                    "sequential_results": sequential_results,
                    "final_output": sequential_results[-1] if sequential_results else {},
                }
                if token_usage_log:
                    orchestration.outputs["token_usage"] = token_usage_log
                if node_metrics_log:
                    orchestration.outputs["node_metrics"] = node_metrics_log

            else:
                await append_log("Strategy: parallel")

                async def run_single(agent: Agent):
                    try:
                        final_state = await _execute_agent_spec(
                            agent_spec=agent.agent_spec,
                            inputs={"prompt": orchestration.prompt},
                            llm_router=llm_router,
                            log_callback=None,
                        )
                        return agent, final_state, None
                    except Exception as exc:  # pragma: no cover - defensive
                        return agent, None, exc

                results = await asyncio.gather(
                    *(run_single(agent) for agent in agents)
                )

                parallel_outputs = []
                node_metrics_log: list[dict[str, Any]] = []
                for agent, final_state, error in results:
                    agent_key = str(agent.id)
                    if error is not None or final_state is None:
                        message = f"Agent '{agent.name}' failed: {error}"
                        await append_log(f"❌ {message}")
                        orchestration.agent_outputs[agent_key] = {"error": str(error)}
                    else:
                        await append_log(f"✅ Agent '{agent.name}' completed")
                        outputs = final_state.get("outputs", {})
                        orchestration.agent_outputs[agent_key] = outputs
                        token_usage = final_state.get("token_usage") or []
                        cost, tokens = _calculate_cost_metrics(
                            token_usage, final_state.get("total_cost")
                        )
                        record_metrics(cost, tokens)
                        parallel_outputs.append(
                            {
                                "agent_id": agent.id,
                                "outputs": outputs,
                                "token_usage": token_usage,
                                "cost": cost,
                                "tokens": tokens,
                            }
                        )
                        node_metrics = final_state.get("node_metrics") or []
                        for metric in node_metrics:
                            entry = dict(metric)
                            entry["agent_id"] = agent.id
                            node_metrics_log.append(entry)

                    orchestration.agent_progress[agent_key] = 100

                orchestration.outputs = {"parallel_results": parallel_outputs}
                if node_metrics_log:
                    orchestration.outputs["node_metrics"] = node_metrics_log

            if cost_present:
                orchestration.total_cost = total_cost_accum
            if tokens_present:
                orchestration.total_tokens = total_tokens_accum

            orchestration.status = RunStatus.COMPLETED
            orchestration.completed_at = datetime.utcnow()
            await append_log("✓ Orchestration completed successfully")
            session.add(orchestration)
            session.commit()

            logger.info(f"Orchestration {orchestration_id} completed successfully")

        except Exception as e:
            logger.error(f"Orchestration {orchestration_id} failed: {e}", exc_info=True)
            orchestration.status = RunStatus.FAILED
            orchestration.error = str(e)
            orchestration.completed_at = datetime.utcnow()
            orchestration.logs = _append_with_timestamp(
                orchestration.logs, f"❌ Orchestration failed: {e}"
            )
            session.add(orchestration)
            session.commit()

# Simple worker loop (in production, use RQ or Celery)
if __name__ == "__main__":
    logger.info("Worker runner started (for development only)")
    logger.info("In production, use RQ or Celery for job processing")

    # Initialize vector store on startup
    _init_vector_store()

    # This is a simple loop for development
    # In production, you'd use RQ worker or Celery worker
    import time
    while True:
        logger.info("Worker idle...")
        time.sleep(10)
