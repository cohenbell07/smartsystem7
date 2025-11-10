"""
Storyboard generation utilities.

The :class:`StoryboardGenerator` breaks a narrative script into individual
scenes with cinematic metadata that downstream components (scene orchestration
and video synthesis) can consume.
"""

from __future__ import annotations

import json
import math
import re
import textwrap
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.llm_router import LLMRouter

SCENE_PROMPT_TEMPLATE = """You are a senior cinematic director.
Break the provided script into a structured storyboard that can be consumed by
an automated video generation pipeline.

Requirements:
- Return JSON with a top-level list called "scenes".
- Each scene must contain:
  * id (string slug, e.g. "scene-1")
  * title (<= 8 words)
  * summary (2-3 sentences describing the visuals)
  * dialogue (single string, trimmed)
  * camera_direction (specific camera shots, transitions, motions)
  * environment (brief description of setting + atmosphere)
  * characters (array of {name, role, appearance})
  * duration_seconds (integer, 5-20 range; total should roughly match {target_duration})
  * beats (array of short bullet strings)

Script:
\"\"\"{script}\"\"\"

Preferred visual style: {visual_style}
"""


@dataclass
class StoryboardScene:
    """Dataclass describing a storyboarded scene."""

    scene_id: str
    title: str
    summary: str
    dialogue: str
    camera_direction: str
    environment: str
    duration_seconds: int
    characters: list[dict[str, Any]] = field(default_factory=list)
    beats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StoryboardGenerator:
    """Generate cinematic storyboard scenes from a natural language script."""

    def __init__(self, llm_router: LLMRouter, *, fallback_scene_duration: int = 12) -> None:
        self.llm_router = llm_router
        self.fallback_scene_duration = fallback_scene_duration

    async def compose_storyboard(
        self,
        raw_script: str,
        preferred_duration: int,
        visual_style: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generate a storyboard from the supplied script.

        When an LLM provider is available we request a structured storyboard.
        If the request fails (missing API keys, malformed output, etc.) we fall
        back to a deterministic heuristic splitter to guarantee that downstream
        modules always receive well-formed data.
        """
        visual_style = visual_style or "cinematic realism with dynamic lighting"

        # Try LLM-powered storyboard first
        try:
            structured = await self._llm_storyboard(
                script=raw_script,
                target_duration=preferred_duration,
                visual_style=visual_style,
            )
            if structured:
                return [scene.to_dict() for scene in structured]
        except Exception:
            # We intentionally swallow errors here and fall back to heuristics
            pass

        # Deterministic fallback storyboard
        fallback = self._fallback_storyboard(
            script=raw_script,
            target_duration=preferred_duration,
            visual_style=visual_style,
        )
        return [scene.to_dict() for scene in fallback]

    async def _llm_storyboard(
        self,
        *,
        script: str,
        target_duration: int,
        visual_style: str,
    ) -> list[StoryboardScene] | None:
        """Attempt to use the configured LLM to obtain a rich storyboard."""
        if not self.llm_router:
            return None

        response = await self.llm_router.generate(
            prompt=SCENE_PROMPT_TEMPLATE.format(
                script=script.strip(),
                target_duration=target_duration,
                visual_style=visual_style,
            ),
            model="gpt-4o-mini",
            temperature=0.45,
        )

        content = response.get("content") if isinstance(response, dict) else getattr(response, "content", None)
        if not content:
            return None

        # Extract JSON from the response
        json_payload = self._extract_json(content)
        if not json_payload:
            return None

        scenes_data = json_payload.get("scenes")
        if not isinstance(scenes_data, list):
            return None

        storyboard: list[StoryboardScene] = []
        for idx, raw_scene in enumerate(scenes_data, start=1):
            try:
                storyboard.append(self._coerce_scene(idx, raw_scene))
            except Exception:
                continue

        return storyboard or None

    def _fallback_storyboard(
        self,
        *,
        script: str,
        target_duration: int,
        visual_style: str,
    ) -> list[StoryboardScene]:
        """
        Heuristic storyboard generator used when the LLM is unavailable.

        We split the script into paragraphs or sentences, then map each section
        into a simple shot with deterministic camera directions and durations.
        """
        cleaned_script = re.sub(r"\s+", " ", script).strip()
        if not cleaned_script:
            raise ValueError("Script is empty after normalization")

        # Split by double-newlines first, fallback to sentences
        sections = [s.strip() for s in re.split(r"\n{2,}", script) if s.strip()]
        if len(sections) < 2:
            sections = re.split(r"(?<=[.!?])\s+", cleaned_script)
        sections = [section.strip() for section in sections if section.strip()]

        num_scenes = max(2, min(8, len(sections)))
        base_duration = max(6, min(18, math.floor(target_duration / num_scenes)))

        scenes: list[StoryboardScene] = []
        for idx in range(num_scenes):
            chunk = sections[idx % len(sections)]
            scene_id = f"scene-{idx + 1}"
            title = self._generate_title(chunk, idx)
            summary = textwrap.shorten(chunk, width=320, placeholder="…")
            dialogue = self._extract_dialogue(chunk)
            camera_direction = self._fallback_camera_direction(idx, visual_style)
            environment = self._fallback_environment(idx, visual_style)
            beats = self._fallback_beats(chunk)
            characters = self._fallback_characters(chunk)

            scenes.append(
                StoryboardScene(
                    scene_id=scene_id,
                    title=title,
                    summary=summary,
                    dialogue=dialogue,
                    camera_direction=camera_direction,
                    environment=environment,
                    duration_seconds=base_duration,
                    characters=characters,
                    beats=beats,
                )
            )

        return scenes

    @staticmethod
    def _extract_json(response_text: str) -> dict[str, Any] | None:
        """Best-effort JSON extraction from LLM output."""
        match = re.search(r"\{.*\}", response_text, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _coerce_scene(index: int, payload: dict[str, Any]) -> StoryboardScene:
        """Convert raw JSON payload into :class:`StoryboardScene`."""
        scene_id = payload.get("id") or f"scene-{index}"
        title = payload.get("title") or f"Scene {index}"
        summary = payload.get("summary") or payload.get("description") or ""
        dialogue = payload.get("dialogue") or ""
        camera_direction = payload.get("camera_direction") or payload.get("camera") or ""
        environment = payload.get("environment") or payload.get("setting") or ""
        duration = int(payload.get("duration_seconds") or payload.get("duration") or 12)
        characters = payload.get("characters") or []
        beats = payload.get("beats") or []

        return StoryboardScene(
            scene_id=str(scene_id),
            title=str(title),
            summary=str(summary),
            dialogue=str(dialogue),
            camera_direction=str(camera_direction),
            environment=str(environment),
            duration_seconds=max(5, min(120, duration)),
            characters=characters if isinstance(characters, list) else [],
            beats=beats if isinstance(beats, list) else [],
        )

    @staticmethod
    def _generate_title(chunk: str, index: int) -> str:
        words = chunk.split()
        if not words:
            return f"Scene {index + 1}"
        descriptor = " ".join(words[:4]).title()
        return textwrap.shorten(descriptor, width=30, placeholder="…")

    @staticmethod
    def _extract_dialogue(chunk: str) -> str:
        dialogue_lines = re.findall(r"“([^”]+)”|\"([^\"]+)\"", chunk)
        flattened = [match[0] or match[1] for match in dialogue_lines if any(match)]
        if flattened:
            return " ".join(flattened)
        return ""

    @staticmethod
    def _fallback_camera_direction(index: int, visual_style: str) -> str:
        angles = [
            "Wide establishing shot drifting gently forward",
            "Medium tracking shot following the protagonist",
            "Close-up with shallow depth of field focusing on emotion",
            "Over-the-shoulder perspective transitioning to a sweeping crane",
            "Dynamic aerial shot descending into an intimate handheld frame",
        ]
        return f"{angles[index % len(angles)]}. Inspired by {visual_style} aesthetic."

    @staticmethod
    def _fallback_environment(index: int, visual_style: str) -> str:
        atmospheres = [
            "Golden-hour light spills through tall windows, dust motes shimmering.",
            "Rain-soaked streets glow under neon signs, reflections rippling across puddles.",
            "Soft moonlight bathes the scene, contrasted by warm fireplace hues.",
            "Sunrise paints the skyline in amber gradients, clouds rolling slowly overhead.",
            "Interior lit by practical lamps, rich shadows framing the characters.",
        ]
        return atmospheres[index % len(atmospheres)] + f" Overall style: {visual_style}."

    @staticmethod
    def _fallback_beats(chunk: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", chunk)
        beats = [textwrap.shorten(sentence.strip(), width=80, placeholder="…") for sentence in sentences if sentence.strip()]
        return beats[:4]

    @staticmethod
    def _fallback_characters(chunk: str) -> list[dict[str, Any]]:
        names = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", chunk)
        unique_names = []
        for name in names:
            if name.lower() not in {"the", "and"} and name not in unique_names:
                unique_names.append(name)
        characters = []
        for name in unique_names[:3]:
            characters.append({
                "name": name,
                "role": "protagonist" if not characters else "supporting",
                "appearance": "Consistent with previous scenes",
            })
        return characters


