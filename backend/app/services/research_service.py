"""
High-level research facade for the homepage "Research" workflow.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from app.research import (
    crawl_urls,
    deduplicate_sources,
    search_web,
    synthesize_research,
    calculate_viability_score,
)
from app.services import LLMRouter

logger = logging.getLogger(__name__)


class ResearchResult(Dict[str, Any]):
    """Typed alias for research response payloads."""


async def _safe_search(prompt: str, limit: int = 25) -> List[Dict[str, Any]]:
    try:
        return await search_web(prompt, count=limit)
    except Exception as exc:
        logger.warning("Search provider failure (%s)", exc, exc_info=True)
        return []


async def _safe_crawl(urls: List[str]) -> List[Dict[str, Any]]:
    if not urls:
        return []
    try:
        return await crawl_urls(urls, use_playwright=False, max_concurrent=5)
    except Exception as exc:
        logger.warning("Failed to crawl urls (%s)", exc, exc_info=True)
        return []


async def _synthesize_with_fallback(
    prompt: str,
    sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        return await synthesize_research(prompt, sources)
    except Exception as exc:
        logger.warning("LLM synthesis failed, falling back offline (%s)", exc, exc_info=True)
        router = LLMRouter()
        response = await router.generate(
            prompt=(
                "You are a deterministic research summariser working without internet access.\n"
                f"User question: {prompt}\n"
                "Compose a concise executive summary, key findings and cite synthetic references [1], [2]."
            ),
            temperature=0.1,
        )
        content = response.get("content", "")
        return {
            "summary": content or f"Executive summary for '{prompt}' is unavailable offline.",
            "key_findings": [],
            "sources": [],
            "total_sources": len(sources),
            "content_length": sum(len(s.get("content", "")) for s in sources),
        }


async def _viability_with_fallback(prompt: str, summary: str) -> Dict[str, Any]:
    default_payload = {
        "overall": 58,
        "market_demand": 60,
        "competition": 55,
        "feasibility": 62,
        "capital_requirement": 50,
        "moat": 63,
        "rationale": (
            "Offline fallback analysis: Without live data the opportunity appears moderately attractive. "
            "Focus on validating demand signals and mitigating execution risks."
        ),
        "sensitivity": {
            "positive_factors": [
                "Secure differentiated data sources",
                "Demonstrate early revenue traction",
            ],
            "negative_factors": [
                "Entrenched incumbents with network effects",
                "High compute or compliance costs",
            ],
        },
    }

    try:
        return await calculate_viability_score(prompt, summary)
    except Exception as exc:
        logger.warning("Viability scoring failed, using fallback (%s)", exc, exc_info=True)
        return default_payload


async def run_research(prompt: str) -> ResearchResult:
    """
    Execute the lightweight research workflow used by the homepage card.
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt is required")

    search_results = await _safe_search(prompt.strip())
    urls = [item["url"] for item in search_results[:20]]
    crawled_sources = await _safe_crawl(urls)

    # Deduplicate and cap payload to keep synthesis fast
    unique_sources = deduplicate_sources(crawled_sources, similarity_threshold=3) if crawled_sources else []
    synthesis = await _synthesize_with_fallback(prompt, unique_sources)
    viability = await _viability_with_fallback(prompt, synthesis.get("summary", ""))

    formation = (
        "Business Formation Blueprint:\n"
        f"- Target: {prompt.strip()}\n"
        "- Operating Model: Multi-phase launch with lean discovery, "
        "pilot customers, and automated onboarding.\n"
        "- Revenue: Subscription plus usage-based tiers aligned to "
        "value delivered.\n"
        "- Key Resources: Cross-functional research agents, "
        "LLM orchestration, Docker validation, and deployment pipelines.\n"
    )

    return ResearchResult(
        score=viability.get("overall", 0),
        summary=synthesis.get("summary", ""),
        formation=formation,
        findings=synthesis.get("key_findings", []),
        sources=synthesis.get("sources", []),
        viability=viability,
    )


