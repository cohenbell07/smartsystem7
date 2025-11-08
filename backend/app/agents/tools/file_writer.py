"""
Lightweight artifact writer that stores generated content to disk and returns metadata.
"""

from __future__ import annotations

import logging
import os
import pathlib
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FileWriterTool:
    """Tool that materialises generated artifacts onto disk and reports metadata."""

    def __init__(self, base_dir: str | None = None):
        # Default to a generated artifacts directory beneath the repo root.
        base_dir = base_dir or os.getenv("AGENT_ARTIFACT_PATH", "./generated_artifacts")
        self.base_path = pathlib.Path(base_dir).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileWriterTool using base directory: {self.base_path}")

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Persist content to disk.

        Args:
            inputs -> {
                filename: Optional[str],
                content: str (required),
                extension: str (optional),
                description: str (optional),
                artifact_type: str (optional, default 'text')
            }
        """
        content = inputs.get("content")
        if not content:
            return {
                "success": False,
                "error": "file_writer requires 'content' to be provided."
            }

        filename = inputs.get("filename")
        extension = inputs.get("extension")
        if filename:
            path = self.base_path / filename
        else:
            timestamp = int(time.time())
            ext = extension or "md"
            path = self.base_path / f"artifact_{timestamp}.{ext}"

        # Ensure parent directories exist
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with path.open("w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Wrote artifact to {path}")
            artifact = {
                "name": path.name,
                "path": str(path),
                "type": inputs.get("artifact_type", "text"),
                "description": inputs.get("description"),
                "content": content,
            }
            return {
                "success": True,
                "artifact": artifact,
            }
        except Exception as exc:
            logger.error(f"Failed to write artifact {path}: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

