"""
High-level memory manager that wraps the VectorMemoryTool for storing and recalling context.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.agents.tools.vector_memory import VectorMemoryTool

logger = logging.getLogger(__name__)


class MemoryManagerTool:
    """Convenience wrapper to store and retrieve execution context from vector memory."""

    def __init__(self, vector_memory: Optional[VectorMemoryTool] = None):
        self.vector_memory = vector_memory or VectorMemoryTool()

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch memory operations to the underlying vector store.

        Supported actions:
            - store: persist text
            - recall/query: retrieve related context
            - delete: remove entry
        """
        action = inputs.get("action", "store")

        try:
            if action in {"store", "remember"}:
                text = inputs.get("text") or inputs.get("content")
                if not text:
                    return {"success": False, "error": "Memory store requires 'text'."}

                metadata = inputs.get("metadata") or {}
                agent_id = inputs.get("agent_id")
                result = self.vector_memory.remember([text], [metadata], agent_id=agent_id)
                return {"success": True, "details": result}

            if action in {"recall", "query"}:
                query_text = inputs.get("query") or inputs.get("query_text")
                if not query_text:
                    return {"success": False, "error": "Memory recall requires 'query'."}

                results = self.vector_memory.recall(
                    context_query=query_text,
                    n_results=int(inputs.get("n_results", 5)),
                    agent_id=inputs.get("agent_id"),
                )
                return {"success": True, "results": results}

            if action == "delete":
                doc_id = inputs.get("id")
                if not doc_id:
                    return {"success": False, "error": "Memory delete requires 'id'."}
                result = self.vector_memory._delete(doc_id)
                return {"success": True, "details": result}

            return {"success": False, "error": f"Unknown memory action: {action}"}

        except Exception as exc:
            logger.error(f"Memory manager operation failed: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

