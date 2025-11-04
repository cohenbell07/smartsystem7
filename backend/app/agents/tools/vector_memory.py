"""
Vector memory tool using Chroma for long-term agent memory.
"""

import logging
import os
from typing import Dict, Any, List, Optional
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class VectorMemoryTool:
    """Tool for vector-based memory storage and retrieval."""

    def __init__(self, collection_name: str = "agent_memory", persist_directory: str = "./chroma_db"):
        self.collection_name = collection_name
        self.persist_directory = persist_directory

        # Initialize Chroma client
        self.client = chromadb.Client(
            Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_directory,
            )
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Long-term agent memory"},
        )

        logger.info(f"Initialized vector memory: {collection_name}")

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute memory operation.

        Supported actions:
        - store: Store text in memory
        - query: Query memory for relevant texts
        - delete: Delete by ID

        Args:
            inputs: Dict with 'action' and action-specific params

        Returns:
            Dict with action result
        """
        action = inputs.get("action")

        try:
            if action == "store":
                return self._store(
                    inputs.get("text"),
                    inputs.get("id"),
                    inputs.get("metadata", {}),
                )
            elif action == "query":
                return self._query(
                    inputs.get("query_text"),
                    inputs.get("n_results", 5),
                )
            elif action == "delete":
                return self._delete(inputs.get("id"))
            else:
                return {"error": f"Unknown action: {action}"}

        except Exception as e:
            logger.error(f"Vector memory error: {e}")
            return {"error": str(e)}

    def _store(self, text: str, doc_id: Optional[str] = None, metadata: Dict = None) -> Dict[str, Any]:
        """Store text in vector memory."""
        if not text:
            return {"error": "No text provided"}

        # Generate ID if not provided
        if not doc_id:
            import hashlib
            doc_id = hashlib.md5(text.encode()).hexdigest()

        # Store in collection
        self.collection.add(
            documents=[text],
            ids=[doc_id],
            metadatas=[metadata or {}],
        )

        logger.info(f"Stored document {doc_id} ({len(text)} chars)")
        return {
            "success": True,
            "id": doc_id,
            "length": len(text),
        }

    def _query(self, query_text: str, n_results: int = 5) -> Dict[str, Any]:
        """Query vector memory for relevant texts."""
        if not query_text:
            return {"error": "No query text provided"}

        # Query collection
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )

        # Format results
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        formatted_results = []
        for i in range(len(documents)):
            formatted_results.append({
                "id": ids[i],
                "text": documents[i],
                "distance": distances[i],
                "metadata": metadatas[i],
            })

        logger.info(f"Query returned {len(formatted_results)} results")
        return {
            "success": True,
            "results": formatted_results,
            "count": len(formatted_results),
        }

    def _delete(self, doc_id: str) -> Dict[str, Any]:
        """Delete document by ID."""
        if not doc_id:
            return {"error": "No ID provided"}

        self.collection.delete(ids=[doc_id])

        logger.info(f"Deleted document {doc_id}")
        return {
            "success": True,
            "id": doc_id,
        }
