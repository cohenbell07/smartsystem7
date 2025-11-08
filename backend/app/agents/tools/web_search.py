"""
Web search tool leveraging the research search utilities.
"""

from typing import Any, Dict
import logging

from app.research.search import search_web

logger = logging.getLogger(__name__)


class WebSearchTool:
    """Async tool wrapper around the research web search pipeline."""

    def __init__(self, default_results: int = 5):
        self.default_results = default_results

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a web search query.

        Args:
            inputs: {
                query: str (required),
                count: int (optional),
            }
        """
        query = inputs.get("query") or inputs.get("prompt") or inputs.get("task")
        if not query:
            return {
                "success": False,
                "error": "web_search requires a 'query' field."
            }

        count = int(inputs.get("count") or self.default_results)
        try:
            results = await search_web(query, count=count)
            logger.info(f"Web search executed for query='{query[:60]}...' results={len(results)}")
            return {
                "success": True,
                "query": query,
                "results": results[:count],
            }
        except Exception as exc:
            logger.error(f"Web search failed for query '{query}': {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
                "query": query,
            }

