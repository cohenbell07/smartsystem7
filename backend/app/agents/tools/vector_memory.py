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

    def __init__(self, collection_name: str = "agent-memory"):
        self.collection_name = collection_name

        # Get persist directory from env or use default
        persist_dir = os.getenv("CHROMA_DB_PATH", "./chroma_data")

        # Ensure directory exists
        os.makedirs(persist_dir, exist_ok=True)

        # Initialize Chroma client with new Settings API
        self.client = chromadb.Client(
            Settings(
                persist_directory=persist_dir,
                anonymized_telemetry=False
            )
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"source": "smartsystem7"}
        )

        logger.info(f"Initialized vector memory: {collection_name} at {persist_dir}")

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

    def upsert(self, ids: List[str], embeddings: Optional[List] = None, documents: Optional[List[str]] = None, metadatas: Optional[List[Dict]] = None):
        """
        Upsert documents into the vector store.

        Args:
            ids: List of document IDs
            embeddings: Optional list of embeddings (if None, will be auto-generated)
            documents: Optional list of document texts
            metadatas: Optional list of metadata dicts
        """
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(ids)} documents")

    def query(self, query_texts: Optional[List[str]] = None, query_embeddings: Optional[List] = None, n_results: int = 5, where: Optional[Dict] = None) -> Dict:
        """
        Query the vector store.

        Args:
            query_texts: Optional list of query texts
            query_embeddings: Optional list of query embeddings
            n_results: Number of results to return (default: 5)
            where: Optional metadata filter

        Returns:
            Dict with query results
        """
        return self.collection.query(
            query_texts=query_texts,
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where
        )

    def recall(self, context_query: str, n_results: int = 5, agent_id: Optional[int] = None, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Recall relevant past memories based on semantic similarity.

        This method is designed for automatic memory injection into agent prompts.

        Args:
            context_query: The query to find relevant memories (e.g., agent's current task)
            n_results: Maximum number of results to return (default: 5)
            agent_id: Optional agent ID to filter memories for specific agent
            filters: Optional additional metadata filters

        Returns:
            List of recalled memories with text, metadata, and relevance scores
        """
        try:
            # Build metadata filter
            where_filter = filters or {}
            if agent_id is not None:
                where_filter["agent_id"] = agent_id

            # Query the collection
            results = self.collection.query(
                query_texts=[context_query],
                n_results=n_results,
                where=where_filter if where_filter else None
            )

            # Format results for easy consumption
            documents = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            ids = results.get("ids", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            recalled_memories = []
            for i in range(len(documents)):
                recalled_memories.append({
                    "id": ids[i],
                    "text": documents[i],
                    "relevance_score": 1.0 - distances[i],  # Convert distance to similarity
                    "metadata": metadatas[i],
                })

            logger.info(f"Recalled {len(recalled_memories)} memories for query: '{context_query[:50]}...'")
            return recalled_memories

        except Exception as e:
            logger.error(f"Error recalling memories: {e}")
            return []

    def remember(self, documents: List[str], metadatas: Optional[List[Dict]] = None, agent_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Store new information in memory after agent runs.

        This method is designed for automatic memory storage after task completion.

        Args:
            documents: List of text documents to remember
            metadatas: Optional list of metadata dicts (one per document)
            agent_id: Optional agent ID to associate with these memories

        Returns:
            Dict with success status and stored document IDs
        """
        try:
            if not documents:
                return {"error": "No documents provided", "success": False}

            # Generate IDs for documents
            import hashlib
            import time
            ids = []
            for i, doc in enumerate(documents):
                # Create unique ID combining timestamp, content hash, and index
                unique_str = f"{time.time()}_{doc}_{i}"
                doc_id = hashlib.md5(unique_str.encode()).hexdigest()
                ids.append(doc_id)

            # Prepare metadatas
            if metadatas is None:
                metadatas = [{} for _ in documents]

            # Add agent_id to all metadatas if provided
            if agent_id is not None:
                for metadata in metadatas:
                    metadata["agent_id"] = agent_id

            # Add timestamps
            import datetime
            timestamp = datetime.datetime.utcnow().isoformat()
            for metadata in metadatas:
                metadata["stored_at"] = timestamp

            # Store in collection
            self.collection.add(
                documents=documents,
                ids=ids,
                metadatas=metadatas,
            )

            logger.info(f"Remembered {len(documents)} new memories (agent_id: {agent_id})")
            return {
                "success": True,
                "stored_ids": ids,
                "count": len(documents),
            }

        except Exception as e:
            logger.error(f"Error remembering documents: {e}")
            return {"error": str(e), "success": False}
