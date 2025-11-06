"""
Background job runner for research and agent execution.
"""

import logging
import asyncio
from datetime import datetime
from sqlmodel import Session
from app.database import engine
from app.models import (
    Project,
    ProjectStatus,
    ResearchSource,
    Run,
    RunStatus,
    Artifact,
)
from app.research import (
    search_web,
    crawl_urls,
    deduplicate_sources,
    synthesize_research,
    calculate_viability_score,
)
from app.services import LLMRouter, NotificationService
import json
import os

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
    """Generate an agent specification from research and viability analysis."""
    from app.research.synthesize import load_prompt

    prompt = load_prompt("agent_spec") or "Generate an agent specification as JSON."

    llm = await llm_router.get_llm()

    user_prompt = f"""
Based on this research, design an AI agent:

Question: {question}

Research Summary:
{research_brief[:5000]}

Viability Score: {viability['overall']}/100

Generate a complete AgentSpec in JSON format.
"""

    response = await llm.ainvoke([
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_prompt}
    ])

    # Try to parse JSON from response
    content = response.content

    # Extract JSON if wrapped in markdown
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    try:
        agent_spec = json.loads(content)
        return agent_spec
    except json.JSONDecodeError:
        logger.error("Failed to parse agent spec JSON")
        # Return minimal spec
        return {
            "name": "GeneratedAgent",
            "description": "Agent based on research",
            "objective": question,
            "tools": [],
            "apis": [],
            "graph_type": "custom",
            "nodes": [],
            "edges": [],
            "test_plan": [],
            "success_criteria": [],
            "approval_gates": [],
            "estimated_runtime": 300,
        }


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
            run.logs = "Starting agent execution...\n"
            session.add(run)
            session.commit()

            # Get agent spec
            if run.agent_id:
                agent = session.get("Agent", run.agent_id)
                agent_spec = agent.agent_spec
            elif run.project_id:
                project = session.get(Project, run.project_id)
                agent_spec = project.agent_spec
            else:
                raise ValueError("No agent spec available")

            # Build and run agent
            from app.agents.factory import create_agent_from_spec, AgentState
            from app.agents.tools import BrowserTool, GitHubTool, EmailTool, VectorMemoryTool
            from app.services import LLMRouter

            llm_router = LLMRouter()

            # Initialize tools
            tools = {
                "browser": BrowserTool(),
                "github": GitHubTool(),
                "email": EmailTool(),
                "vector_memory": VectorMemoryTool(),
            }

            # Create agent graph
            graph = create_agent_from_spec(
                spec=agent_spec,
                llm_router=llm_router,
                tools=tools,
                approval_callback=None,  # TODO: Implement approval callback
            )

            # Execute graph
            initial_state: AgentState = {
                "messages": [],
                "inputs": run.inputs or {},
                "outputs": {},
                "artifacts": [],
                "step_count": 0,
                "errors": [],
                "token_usage": [],
                "total_cost": 0.0,
            }

            final_state = await graph.ainvoke(initial_state)

            # Update run with results
            run.outputs = final_state.get("outputs", {})
            run.logs += f"\nCompleted {final_state.get('step_count', 0)} steps.\n"

            # Save actual cost information
            token_usage = final_state.get("token_usage", [])
            total_cost = final_state.get("total_cost", 0.0)

            if token_usage:
                # Calculate total tokens
                total_tokens = sum(
                    usage.get("usage", {}).get("total_tokens", 0)
                    for usage in token_usage
                )

                run.actual_cost = total_cost
                run.total_tokens = total_tokens

                # Store detailed breakdown
                if run.cost_breakdown:
                    run.cost_breakdown["actual"] = {
                        "total_cost": total_cost,
                        "total_tokens": total_tokens,
                        "breakdown": token_usage,
                    }
                else:
                    run.cost_breakdown = {
                        "actual": {
                            "total_cost": total_cost,
                            "total_tokens": total_tokens,
                            "breakdown": token_usage,
                        }
                    }

                run.logs += f"\nActual cost: ${total_cost:.4f} ({total_tokens} tokens)\n"
                logger.info(f"Run {run_id} actual cost: ${total_cost:.4f}")

            # Save artifacts
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
            run.logs += f"\nError: {str(e)}\n"
            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()


async def run_agent_prompt_job(run_id: int):
    """
    Execute an agent with a direct prompt using the Agent Manager runtime.
    This enables multi-agent orchestration with sub-agents and memory recall.
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
            run.logs = "Starting multi-agent runtime execution...\n"
            session.add(run)
            session.commit()

            # Get agent
            from app.models import Agent
            agent = session.get(Agent, run.agent_id)
            if not agent:
                raise ValueError(f"Agent {run.agent_id} not found")

            run.logs += f"Agent: {agent.name}\n"
            run.logs += f"Prompt: {run.prompt}\n\n"
            session.add(run)
            session.commit()

            # Initialize components
            from app.agents.manager import AgentManager
            from app.agents.tools import BrowserTool, GitHubTool, EmailTool, VectorMemoryTool, APICaller, CodeExecutor
            from app.services import LLMRouter

            llm_router = LLMRouter()
            vector_memory = VectorMemoryTool()

            # Initialize tools
            tools = {
                "browser": BrowserTool(),
                "github": GitHubTool(),
                "email": EmailTool(),
                "vector_memory": vector_memory,
                "api_caller": APICaller(),
                "code_executor": CodeExecutor(),
            }

            run.logs += "Initializing Agent Manager...\n"
            session.add(run)
            session.commit()

            # Create Agent Manager
            agent_manager = AgentManager(
                llm_router=llm_router,
                tools=tools,
                vector_memory=vector_memory
            )

            # Prepare agent context
            agent_context = {
                "name": agent.name,
                "description": agent.description or "No description",
                "tools": list(tools.keys()),
                "agent_spec": agent.agent_spec
            }

            run.logs += "Starting workflow execution...\n"
            session.add(run)
            session.commit()

            # Execute workflow
            workflow_results = await agent_manager.execute_workflow(
                user_prompt=run.prompt,
                agent_id=agent.id,
                agent_context=agent_context
            )

            # Update run with results
            run.outputs = {
                "workflow_status": workflow_results.get("status"),
                "intent": workflow_results.get("intent", {}),
                "steps": workflow_results.get("steps", []),
                "sub_agent_results": workflow_results.get("sub_agent_results", []),
                "final_output": workflow_results.get("output", ""),
                "errors": workflow_results.get("errors", [])
            }

            # Store recalled memory
            run.recalled_memory = {
                "count": len(workflow_results.get("recalled_memory", [])),
                "items": workflow_results.get("recalled_memory", [])
            }

            # Append workflow logs
            for log_entry in workflow_results.get("logs", []):
                run.logs += f"{log_entry}\n"

            # Determine final status
            if workflow_results.get("status") == "completed":
                run.status = RunStatus.COMPLETED
                run.logs += "\n✓ Workflow completed successfully\n"
            elif workflow_results.get("status") == "completed_with_errors":
                run.status = RunStatus.COMPLETED
                run.logs += "\n⚠ Workflow completed with errors\n"
            else:
                run.status = RunStatus.FAILED
                run.logs += "\n✗ Workflow failed\n"

            # Save artifacts from sub-agents
            for i, sub_result in enumerate(workflow_results.get("sub_agent_results", [])):
                if sub_result.get("success"):
                    artifact = Artifact(
                        run_id=run.id,
                        project_id=run.project_id,
                        name=f"{sub_result.get('sub_agent', 'subagent')}_output",
                        artifact_type="text",
                        content=sub_result.get("output", ""),
                    )
                    session.add(artifact)

            run.completed_at = datetime.utcnow()
            session.add(run)
            session.commit()

            logger.info(f"Agent prompt execution completed for run {run_id}")

        except Exception as e:
            logger.error(f"Agent prompt execution failed for run {run_id}: {e}", exc_info=True)
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.logs += f"\nError: {str(e)}\n"
            run.completed_at = datetime.utcnow()
            session.add(run)
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
