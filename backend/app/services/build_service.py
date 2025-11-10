"""
Agent build orchestration with streaming updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import (
    AgentPlan,
    AgentPlanState,
    AgentBuild,
    AgentBuildStatus,
)
from app.services.plan_service import PlanService
from app.services.executor.docker_executor import DockerExecutor
from app.services.github_client import GitHubClient
from app.services.vercel_client import VercelClient
from app.services.model_router import ModelRouter
from app.services.memory_db import get_memory_db
from app.agents.coding_orchestrator_enhanced import EnhancedCodingOrchestrator
from app.agents.tools import (
    BrowserTool,
    GitHubTool,
    EmailTool,
    VectorMemoryTool,
    CodeExecutor,
    APICaller,
    WebScraper,
    WebSearchTool,
    FileWriterTool,
    MemoryManagerTool,
)
from app.database import engine

logger = logging.getLogger(__name__)


@dataclass
class BuildStream:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    done: asyncio.Event = field(default_factory=asyncio.Event)


class BuildService:
    """Coordinates plan builds with enhanced orchestrator and SSE streaming."""

    def __init__(self) -> None:
        self.plan_service = PlanService()
        self.docker_executor = DockerExecutor(settings)
        self.github_client = GitHubClient(settings)
        self.vercel_client = VercelClient(settings)
        self.model_router = ModelRouter(settings)
        self.vector_memory = VectorMemoryTool()
        self.tools = {
            "browser": BrowserTool(),
            "github": GitHubTool(),
            "email": EmailTool(),
            "code_executor": CodeExecutor(),
            "api_caller": APICaller(),
            "web_scraper": WebScraper(),
            "web_search": WebSearchTool(),
            "file_writer": FileWriterTool(),
        }
        self.tools["python_executor"] = self.tools["code_executor"]
        self.tools["memory_manager"] = MemoryManagerTool(self.vector_memory)

        self.orchestrator = EnhancedCodingOrchestrator(
            llm_router=self.plan_service.router,
            tools=self.tools,
            vector_memory=self.vector_memory,
            config=settings,
            model_router=self.model_router,
            docker_executor=self.docker_executor,
            github_client=self.github_client,
            vercel_client=self.vercel_client,
        )

        self._streams: Dict[str, BuildStream] = {}
        self._lock = asyncio.Lock()

    async def start_build(
        self,
        session: Session,
        plan_id: str,
        enable_deployment: bool = False,
    ) -> str:
        plan = session.get(AgentPlan, plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        if plan.state != AgentPlanState.READY:
            logger.warning("Plan %s not marked ready; continuing with refining state", plan_id)

        run_id = str(uuid.uuid4())
        stream = BuildStream()

        build_record = AgentBuild(
            plan_id=plan_id,
            run_id=run_id,
            status=AgentBuildStatus.QUEUED,
        )
        session.add(build_record)
        session.commit()
        session.refresh(build_record)

        async with self._lock:
            self._streams[run_id] = stream

        asyncio.create_task(
            self._execute_build(plan_id, build_record.id, run_id, stream, enable_deployment)
        )
        return run_id

    async def _execute_build(
        self,
        plan_id: str,
        build_pk: int,
        run_id: str,
        stream: BuildStream,
        enable_deployment: bool,
    ) -> None:
        async def emit(event_type: str, data: Dict[str, Any]) -> None:
            payload = {"type": event_type, "data": data}
            await stream.queue.put(payload)

        async def log_callback(message: str) -> None:
            await emit("log", {"message": message})

        await emit("phase", {"status": "starting", "run_id": run_id})

        with Session(engine) as session:
            plan_obj: Optional[AgentPlan] = session.get(AgentPlan, plan_id)
            build_record: Optional[AgentBuild] = session.get(AgentBuild, build_pk)

            if not plan_obj or not build_record:
                await emit("log", {"message": "Plan or build record missing; aborting"})
                stream.done.set()
                return

            plan_snapshot = {
                "prompt": plan_obj.prompt,
                "plan": plan_obj.plan or {},
                "graph": plan_obj.graph or {},
                "stack": plan_obj.suggested_stack or {},
                "risks": plan_obj.risks or {},
            }

            build_record.status = AgentBuildStatus.RUNNING
            build_record.updated_at = datetime.utcnow()
            session.add(build_record)
            session.commit()

        memory_db = await get_memory_db(settings.MEMORY_DB_PATH)

        start_time = datetime.utcnow()
        result: Dict[str, Any] = {}
        try:
            orchestration_prompt = plan_snapshot["prompt"]
            context = {
                "plan": plan_snapshot["plan"],
                "graph": plan_snapshot["graph"],
                "stack": plan_snapshot["stack"],
                "risks": plan_snapshot["risks"],
            }

            result = await self.orchestrator.orchestrate_build_enhanced(
                user_prompt=orchestration_prompt,
                project_context=context,
                log_callback=log_callback,
                run_id=run_id if enable_deployment else None,
            )

            status = result.get("status", "failed")
            quality = result.get("final_score") or result.get("outputs", {}).get("quality")
            await emit("score", {"score": quality or 0})
            if quality is not None and quality < 0.7:
                await emit(
                    "log",
                    {
                        "message": f"⚠️ Quality score below threshold ({quality:.2%}); marking build as failed."
                    },
                )
                status = "failed"

            outputs = result.get("outputs", {}) if isinstance(result.get("outputs"), dict) else {}
            deployment_info = result.get("deployment", {}) if isinstance(result.get("deployment"), dict) else {}
            repo_url = outputs.get("repo_url") or deployment_info.get("repo_url")
            vercel_url = outputs.get("vercel_url") or deployment_info.get("vercel_url")

            with Session(engine) as session:
                build_record = session.get(AgentBuild, build_pk)
                if build_record:
                    build_record.status = (
                        AgentBuildStatus.COMPLETED if status == "completed" else AgentBuildStatus.FAILED
                    )
                    build_record.quality_score = quality

                    build_record.repo_url = repo_url
                    build_record.vercel_url = vercel_url
                    build_record.artifacts = outputs
                    build_record.logs = json.dumps(result, default=str)[:4000]
                    build_record.updated_at = datetime.utcnow()
                    session.add(build_record)
                    session.commit()

            await emit(
                "phase",
                {
                    "status": "completed" if status == "completed" else "failed",
                    "quality": quality,
                    "repo_url": repo_url,
                    "vercel_url": vercel_url,
                },
            )

            if repo_url:
                await emit("artifact", {"kind": "repository", "url": repo_url})
            if vercel_url:
                await emit("artifact", {"kind": "deployment", "url": vercel_url})
            file_artifacts = outputs.get("files")
            if isinstance(file_artifacts, dict):
                await emit(
                    "artifact",
                    {
                        "kind": "files",
                        "files": [{"path": path, "display": path.split('/')[-1]} for path in file_artifacts.keys()],
                    },
                )
            elif isinstance(file_artifacts, list):
                await emit(
                    "artifact",
                    {
                        "kind": "files",
                        "files": [
                            {
                                "path": item.get("path"),
                                "display": item.get("name") or item.get("path"),
                            }
                            for item in file_artifacts
                            if isinstance(item, dict) and item.get("path")
                        ],
                    },
                )

            if memory_db:
                duration_sec = (datetime.utcnow() - start_time).total_seconds()
                await memory_db.save_build(
                    run_id=run_id,
                    prompt=plan_snapshot["prompt"],
                    quality=quality or 0.0,
                    model_map=result.get("model_usage", {}),
                    duration_sec=duration_sec,
                    status="completed" if status == "completed" else "failed",
                    repo_url=repo_url,
                    vercel_url=vercel_url,
                    requirements=context,
                    docker_validated=result.get("docker_validation", {}).get("success", False),
                    github_deployed=bool(repo_url),
                    vercel_deployed=bool(vercel_url),
                )

        except Exception as exc:
            logger.error("Build failed: %s", exc, exc_info=True)
            with Session(engine) as session:
                build_record = session.get(AgentBuild, build_pk)
                if build_record:
                    build_record.status = AgentBuildStatus.FAILED
                    build_record.logs = f"Build failed: {exc}"
                    build_record.updated_at = datetime.utcnow()
                    session.add(build_record)
                    session.commit()
            await emit("phase", {"status": "failed", "error": str(exc)})
            await emit("log", {"message": f"❌ Build failed: {exc}"})
        finally:
            stream.done.set()
            await stream.queue.put(None)
            async with self._lock:
                self._streams.pop(run_id, None)

    async def stream_events(self, run_id: str):
        async with self._lock:
            stream = self._streams.get(run_id)
        if not stream:
            raise ValueError(f"Run {run_id} not found")

        while True:
            item = await stream.queue.get()
            if item is None:
                break
            yield item

    def get_build(self, session: Session, run_id: str) -> AgentBuild:
        build = session.exec(
            select(AgentBuild).where(AgentBuild.run_id == run_id)
        ).one_or_none()
        if not build:
            raise ValueError(f"Build {run_id} not found")
        return build

    async def force_deploy(self, existing_run_id: str) -> str:
        with Session(engine) as session:
            build = session.exec(
                select(AgentBuild).where(AgentBuild.run_id == existing_run_id)
            ).one_or_none()
            if not build:
                raise ValueError(f"Build {existing_run_id} not found")
            if not build.plan_id:
                raise ValueError("Build is not linked to a plan")
            plan_id = build.plan_id

        session = Session(engine)
        try:
            return await self.start_build(session, plan_id, enable_deployment=True)
        finally:
            session.close()

    def list_files(self, build: AgentBuild) -> Dict[str, Any]:
        outputs = build.artifacts or {}
        files = outputs.get("files") or []
        if isinstance(files, dict):
            files = [{"path": path, "content": content} for path, content in files.items()]
        return {"files": files}

    def get_file(self, build: AgentBuild, path: str) -> Dict[str, Any]:
        files = build.artifacts.get("files")
        if isinstance(files, dict):
            content = files.get(path)
            if content is None:
                raise ValueError(f"File {path} not found")
            return {"path": path, "content": content}
        for item in files or []:
            if item.get("path") == path:
                return item
        raise ValueError(f"File {path} not found")


