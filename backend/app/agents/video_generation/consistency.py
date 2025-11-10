"""
Character and voice consistency utilities.

Maintains a lightweight memory of characters, environments, and stylistic
choices so that subsequent scenes – and future runs of the agent – preserve a
coherent aesthetic.
"""

from __future__ import annotations

from typing import Any


class ConsistencyMemory:
    """Stores cross-scene continuity data for characters, environments, and voices."""

    def __init__(self, vector_memory=None) -> None:
        self.vector_memory = vector_memory
        self._project_store: dict[str, dict[str, Any]] = {}

    def record_storyboard(self, project_name: str, storyboard: list[dict[str, Any]]) -> None:
        """
        Persist a storyboard into memory.  We store a summary per project and,
        when a vector database is supplied, we also upsert embeddings so future
        runs can recall continuity details.
        """
        if not project_name:
            return

        characters: dict[str, dict[str, Any]] = {}
        environments: list[str] = []

        for scene in storyboard:
            environments.append(scene.get("environment", ""))
            for character in scene.get("characters", []):
                name = character.get("name")
                if not name:
                    continue
                existing = characters.setdefault(name, {
                    "name": name,
                    "role": character.get("role", "character"),
                    "appearance": character.get("appearance", "consistent attire"),
                    "scenes": [],
                })
                existing["scenes"].append(scene.get("scene_id"))

        self._project_store[project_name] = {
            "characters": characters,
            "environments": environments,
        }

        if self.vector_memory:
            # Upsert summary for retrieval
            summary_text = self._build_summary(project_name)
            try:
                self.vector_memory.store(
                    context=f"video_project::{project_name}",
                    content=summary_text,
                    metadata={"type": "video_generation", "project": project_name},
                )
            except Exception:
                # Vector storage failure should not interrupt pipeline
                pass

    def describe(self, project_name: str) -> dict[str, Any]:
        """Return a human-readable summary of stored memory for a project."""
        project_data = self._project_store.get(project_name)
        if not project_data:
            return {"characters": [], "environments": []}

        characters = [
            {
                "name": name,
                "role": data.get("role"),
                "appearance": data.get("appearance"),
                "scene_count": len(data.get("scenes", [])),
            }
            for name, data in project_data.get("characters", {}).items()
        ]
        environments = project_data.get("environments", [])
        return {"characters": characters, "environments": environments}

    def describe_characters(self, characters: list[dict[str, Any]]) -> str:
        """Return a textual description of characters leveraging stored memory."""
        if not characters:
            return ""

        descriptions = []
        for character in characters:
            name = character.get("name")
            if not name:
                continue
            existing = self._find_character(name)
            if existing:
                desc = (
                    f"{name}: role {existing.get('role')}, appearance {existing.get('appearance')}, "
                    f"previous scenes {existing.get('scenes', [])}"
                )
            else:
                desc = (
                    f"{name}: new appearance ({character.get('appearance', 'consistent attire')}) "
                    f"role {character.get('role', 'character')}"
                )
            descriptions.append(desc)
        return "; ".join(descriptions)

    def _find_character(self, name: str) -> dict[str, Any] | None:
        for project in self._project_store.values():
            candidate = project.get("characters", {}).get(name)
            if candidate:
                return candidate
        return None

    def _build_summary(self, project_name: str) -> str:
        project_data = self._project_store.get(project_name, {})
        lines = [f"Project {project_name} character bible:"]
        for name, data in project_data.get("characters", {}).items():
            lines.append(
                f"- {name}: role={data.get('role')}, appearance={data.get('appearance')}, "
                f"scenes={', '.join(data.get('scenes', []))}"
            )
        if project_data.get("environments"):
            lines.append("Key environments:")
            for env in project_data["environments"]:
                if env:
                    lines.append(f"  * {env}")
        return "\n".join(lines)


