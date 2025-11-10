"""
Agent plan lifecycle management.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.models import AgentPlan, AgentPlanRevision, AgentPlanState
from .llm_router import LLMRouter

logger = logging.getLogger(__name__)


def _default_plan_structure(prompt: str) -> Dict[str, Any]:
    title = prompt.strip().capitalize()
    return {
        "title": title,
        "objective": f"Deliver an autonomous agent for: {prompt.strip()}",
        "phases": [
            {
                "id": "discovery",
                "title": "Discovery & Research",
                "description": "Gather requirements, constraints, and success criteria.",
                "children": [
                    {"id": "stakeholders", "title": "Stakeholder Mapping"},
                    {"id": "data", "title": "Data + API Audit"},
                ],
            },
            {
                "id": "architecture",
                "title": "Architecture & Workflow",
                "description": "Design nodes, tools, and orchestration graph.",
                "children": [
                    {"id": "graph", "title": "Define workflow graph"},
                    {"id": "tooling", "title": "Select tools & integrations"},
                ],
            },
            {
                "id": "implementation",
                "title": "Implementation & Validation",
                "description": "Implement agent, run validation, secure deployments.",
                "children": [
                    {"id": "build", "title": "Code generation + refactor"},
                    {"id": "validate", "title": "Docker validation & QA"},
                ],
            },
        ],
        "deliverables": [
            "Workflow graph JSON",
            "Generated code repository",
            "Validation report & score",
        ],
        "notes": [],
    }


def _default_graph(plan: Dict[str, Any]) -> Dict[str, Any]:
    nodes = []
    edges = []
    for phase in plan.get("phases", []):
        nodes.append(
            {
                "id": phase["id"],
                "label": phase.get("title"),
                "type": "phase",
            }
        )
        for child in phase.get("children", []):
            nodes.append(
                {
                    "id": child["id"],
                    "label": child.get("title"),
                    "type": "task",
                }
            )
            edges.append({"from": phase["id"], "to": child["id"]})
    return {"nodes": nodes, "edges": edges}


def _default_stack() -> Dict[str, Any]:
    return {
        "frontend": "Next.js 14 + Tailwind CSS",
        "backend": "FastAPI + SQLModel",
        "orchestration": "SmartSystem7 Enhanced Coding Orchestrator",
        "validation": "Docker (pytest, lint, smoke tests)",
        "deployment": "GitHub Actions + Vercel (optional)",
    }


def _default_risks() -> Dict[str, Any]:
    return {
        "technical": [
            "Third-party API rate limits may throttle automation nodes.",
            "LLM cost spikes if prompt/plan not optimised.",
        ],
        "operational": [
            "Need for human-in-the-loop approvals for sensitive actions.",
            "Repository secrets management for GitHub/Vercel tokens.",
        ],
        "mitigations": [
            "Implement caching + retries for external APIs.",
            "Use SafeRender components on frontend to avoid runtime crashes.",
        ],
    }


def _extract_plan_payload(content: str, prompt: str) -> Dict[str, Any]:
    if not content:
        return _default_plan_structure(prompt)
    try:
        payload = json.loads(content)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        logger.debug("LLM plan output not JSON, using fallback")
    return _default_plan_structure(prompt)


class PlanService:
    """Service responsible for plan creation, refinement, and retrieval."""

    def __init__(self):
        self.router = LLMRouter()

    async def create_plan(self, session: Session, prompt: str) -> AgentPlan:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt is required")

        llm_response = await self.router.generate(
            prompt=(
                "Respond in valid JSON with keys title, objective, phases (array of {id,title,description,children}), "
                "deliverables (array of strings). The user wants to build an autonomous software agent.\n"
                f"User prompt: {prompt}"
            ),
            system="You are an expert autonomous-agent architect.",
            temperature=0.25,
        )

        plan_payload = _extract_plan_payload(llm_response.get("content", ""), prompt)
        if "notes" not in plan_payload:
            plan_payload["notes"] = []

        graph = _default_graph(plan_payload)
        suggested_stack = _default_stack()
        risks = _default_risks()

        plan = AgentPlan(
            prompt=prompt,
            plan=plan_payload,
            graph=graph,
            suggested_stack=suggested_stack,
            risks=risks,
            summary=f"Draft plan created for '{prompt}'.",
            chat_history=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": llm_response.get("content", "")},
            ],
            state=AgentPlanState.DRAFT,
        )

        session.add(plan)
        session.commit()
        session.refresh(plan)
        return plan

    async def apply_revision(
        self,
        session: Session,
        plan_id: str,
        revision: str,
        mark_ready: bool = False,
    ) -> AgentPlan:
        plan: Optional[AgentPlan] = session.exec(
            select(AgentPlan).where(AgentPlan.id == plan_id)
        ).one_or_none()
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        revision = revision.strip()
        if not revision:
            raise ValueError("revision text is required")

        assistant_response = await self.router.generate(
            prompt=(
                "You are refining an existing agent implementation plan. "
                "Return JSON with keys: updates (array of strings), "
                "graph_changes (array), risks (array), notes (array). "
                f"Existing plan summary: {plan.summary}. "
                f"Revision request: {revision}"
            ),
            temperature=0.3,
        )

        delta_content = assistant_response.get("content", "")
        try:
            delta_payload = json.loads(delta_content)
        except json.JSONDecodeError:
            delta_payload = {"updates": [revision], "notes": [delta_content]}

        plan.plan.setdefault("notes", [])
        plan.plan["notes"].extend(delta_payload.get("notes", []) or delta_payload.get("updates", []))
        plan.summary = f"Plan refined at {datetime.utcnow().isoformat()}"
        plan.chat_history.append({"role": "user", "content": revision})
        plan.chat_history.append({"role": "assistant", "content": delta_content})
        plan.graph = _default_graph(plan.plan)
        plan.updated_at = datetime.utcnow()
        plan.last_revision_at = datetime.utcnow()

        if mark_ready or delta_payload.get("state") == "ready":
            plan.state = AgentPlanState.READY
        elif plan.state == AgentPlanState.DRAFT:
            plan.state = AgentPlanState.REFINING

        revision_record = AgentPlanRevision(
            plan_id=plan.id,
            delta=delta_payload,
            summary=revision[:240],
        )
        session.add(revision_record)
        session.add(plan)
        session.commit()
        session.refresh(plan)
        return plan

    def get_plan(self, session: Session, plan_id: str) -> AgentPlan:
        plan = session.exec(select(AgentPlan).where(AgentPlan.id == plan_id)).one_or_none()
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        return plan


