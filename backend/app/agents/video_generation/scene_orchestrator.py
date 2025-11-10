"""
Scene orchestration utilities.

Transforms storyboard scenes into concrete rendering directives that can be
submitted to text-to-video APIs.  Each directive includes prompt engineering,
camera instructions, voice-over script and soundtrack cues.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
from typing import Any

from app.services.llm_router import LLMRouter

SCENE_DIRECTIVE_PROMPT = """You are assisting an automated cinematic video generator.
Craft a detailed rendering directive for the following storyboard scene.

Return JSON with:
- "prompt": single paragraph describing visual content, mood, lighting, composition.
- "camera": cinematic camera instructions (shots, transitions, motion).
- "visual_details": bullet list (array) of specific elements to emphasize.
- "additional_tools": array of optional post-processing helpers (e.g. "color grade teal/orange").

Scene:
{scene}

Global style cues:
- Visual style: {visual_style}
- Music style: {music_style}
- Character profiles: {character_profiles}
"""


class SceneOrchestrator:
    """Build rich scene directives for text-to-video synthesis."""

    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def build_scene_requests(
        self,
        *,
        storyboard: list[dict[str, Any]],
        consistency_memory,
        visual_style: str | None,
        music_style: str | None,
        voice_profile: str | None,
    ) -> list[dict[str, Any]]:
        tasks = []
        for scene in storyboard:
            tasks.append(
                self._build_single_scene_request(
                    scene=scene,
                    consistency_memory=consistency_memory,
                    visual_style=visual_style,
                    music_style=music_style,
                    voice_profile=voice_profile,
                )
            )
        return await asyncio.gather(*tasks)

    async def _build_single_scene_request(
        self,
        *,
        scene: dict[str, Any],
        consistency_memory,
        visual_style: str | None,
        music_style: str | None,
        voice_profile: str | None,
    ) -> dict[str, Any]:
        visual_style = visual_style or "cinematic realism with rich volumetric lighting"
        music_style = music_style or "orchestral with subtle electronic undertones"
        voice_profile = voice_profile or "narrative cinematic"

        characters = scene.get("characters", [])
        character_profiles = consistency_memory.describe_characters(characters)

        directive = await self._llm_directive(
            scene=scene,
            visual_style=visual_style,
            music_style=music_style,
            character_profiles=character_profiles,
        )

        if not directive:
            directive = self._fallback_directive(
                scene=scene,
                visual_style=visual_style,
                music_style=music_style,
                character_profiles=character_profiles,
            )

        voiceover_script = scene.get("dialogue") or scene.get("summary") or ""
        voiceover_script = textwrap.shorten(voiceover_script.strip(), width=400, placeholder="…")

        return {
            "scene_id": scene["scene_id"],
            "title": scene.get("title"),
            "prompt": directive["prompt"],
            "camera": directive["camera"],
            "visual_details": directive.get("visual_details", []),
            "additional_tools": directive.get("additional_tools", []),
            "voiceover_script": voiceover_script,
            "voice_profile": voice_profile,
            "duration_seconds": scene.get("duration_seconds", 12),
            "environment": scene.get("environment"),
            "characters": characters,
        }

    async def _llm_directive(
        self,
        *,
        scene: dict[str, Any],
        visual_style: str,
        music_style: str,
        character_profiles: str,
    ) -> dict[str, Any] | None:
        if not self.llm_router:
            return None

        response = await self.llm_router.generate(
            prompt=SCENE_DIRECTIVE_PROMPT.format(
                scene=self._format_scene_for_prompt(scene),
                visual_style=visual_style,
                music_style=music_style,
                character_profiles=character_profiles or "N/A",
            ),
            model="gpt-4o-mini",
            temperature=0.35,
        )

        content = response.get("content") if isinstance(response, dict) else getattr(response, "content", None)
        if not content:
            return None

        try:
            payload = json.loads(content)
            if not isinstance(payload, dict):
                return None

            prompt = payload.get("prompt")
            camera = payload.get("camera")
            if not prompt or not camera:
                return None

            visual_details = payload.get("visual_details")
            if isinstance(visual_details, str):
                visual_details = [visual_details]

            additional_tools = payload.get("additional_tools")
            if isinstance(additional_tools, str):
                additional_tools = [additional_tools]

            return {
                "prompt": prompt.strip(),
                "camera": camera.strip(),
                "visual_details": visual_details or [],
                "additional_tools": additional_tools or [],
            }
        except Exception:
            return None

    @staticmethod
    def _fallback_directive(
        *,
        scene: dict[str, Any],
        visual_style: str,
        music_style: str,
        character_profiles: str,
    ) -> dict[str, Any]:
        prompt = (
            f"{scene.get('summary', '')} "
            f"Visual style: {visual_style}. "
            f"Atmosphere: {scene.get('environment', '')}. "
            f"Ensure characters {', '.join([c.get('name', '') for c in scene.get('characters', [])])} "
            f"match previous scenes ({character_profiles or 'consistent attire and facial features'})."
        )

        camera = (
            f"Begin with a sweeping establishing shot transitioning into a medium tracking shot. "
            f"Use smooth cinematic movements and a {music_style} rhythm."
        )

        visual_details = [
            "High dynamic range lighting with cinematic color grading",
            "Add volumetric atmosphere to enhance depth",
            "Emphasize character expressions and eye highlights",
        ]

        additional_tools = [
            "stabilize_motion",
            "color_grade_teal_orange",
        ]

        return {
            "prompt": prompt,
            "camera": camera,
            "visual_details": visual_details,
            "additional_tools": additional_tools,
        }

    @staticmethod
    def _format_scene_for_prompt(scene: dict[str, Any]) -> str:
        characters = scene.get("characters", [])
        characters_str = "\n".join(
            [
                f"- {char.get('name', 'Unknown')}: {char.get('role', 'character')} "
                f"({char.get('appearance', 'consistent look')})"
            ]
            for char in characters
        )

        beats = "\n".join(f"- {beat}" for beat in scene.get("beats", []))
        dialogue = scene.get("dialogue") or "(no dialogue)"

        return textwrap.dedent(
            f"""
            Scene ID: {scene.get('scene_id')}
            Title: {scene.get('title')}
            Summary: {scene.get('summary')}
            Environment: {scene.get('environment')}
            Duration: {scene.get('duration_seconds')} seconds
            Key beats:
            {beats or '- none'}

            Dialogue (if any):
            {dialogue}

            Characters:
            {characters_str or '- none'}
            """
        ).strip()


