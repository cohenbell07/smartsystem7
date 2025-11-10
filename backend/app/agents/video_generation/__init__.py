"""
Cinematic Video Generation Agent pipeline.

This package provides a production-grade pipeline for transforming natural
language scripts into multi-scene cinematic videos.  The pipeline is composed
of four main stages:

1. Storyboard generation – break the script into coherent scenes and camera
   shots with rich metadata.
2. Scene orchestration – translate each scene into rendering directives that
   can be handed to text-to-video APIs.
3. Character and voice consistency – maintain a shared memory of characters,
   environments, and voices to ensure continuity across scenes.
4. Video synthesis – render the final video either by calling external AI
   providers or via the local cinematic fallback renderer.

The public entry point is :class:`CinematicVideoAgent`, which coordinates the
complete workflow and returns structured artifacts plus the rendered video.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .consistency import ConsistencyMemory
from .scene_orchestrator import SceneOrchestrator
from .storyboard import StoryboardGenerator
from .synthesis import VideoSynthesisResult, VideoSynthesisService


class CinematicVideoAgent:
    """
    High-level orchestrator that turns a natural language script into a
    cinematic, multi-scene video with consistent characters and narration.
    """

    def __init__(
        self,
        llm_router,
        *,
        output_root: Path,
        vector_memory=None,
    ) -> None:
        self.llm_router = llm_router
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

        self.storyboard = StoryboardGenerator(llm_router=llm_router)
        self.scene_orchestrator = SceneOrchestrator(llm_router=llm_router)
        self.consistency_memory = ConsistencyMemory(vector_memory=vector_memory)
        self.synthesis_service = VideoSynthesisService(base_output_dir=self.output_root)

    async def generate_video(
        self,
        script: str,
        *,
        project_name: str,
        target_duration: int = 60,
        visual_style: str | None = None,
        music_style: str | None = None,
        voice_profile: str | None = None,
        enable_external_apis: bool = True,
    ) -> dict[str, Any]:
        """
        Execute the full cinematic pipeline.

        Args:
            script: Natural language script or short story.
            project_name: Friendly name used to namespace generated assets.
            target_duration: Desired total duration (seconds).
            visual_style: Optional art-direction cue (e.g. "neo-noir", "pixar").
            music_style: Optional soundtrack cue.
            voice_profile: Preferred voice (maps to ElevenLabs or fallback voice).
            enable_external_apis: If False, force the local cinematic renderer.

        Returns:
            Dictionary containing storyboard, scene directives, synthesis
            metadata, and the absolute path to the rendered video file.
        """
        if not script or not script.strip():
            raise ValueError("Script cannot be empty")

        # Stage 1: Storyboard / breakdown
        storyboard = await self.storyboard.compose_storyboard(
            raw_script=script,
            preferred_duration=target_duration,
            visual_style=visual_style,
        )

        # Stage 2: Scene orchestration (text-to-scene directives)
        scene_requests = await self.scene_orchestrator.build_scene_requests(
            storyboard=storyboard,
            consistency_memory=self.consistency_memory,
            visual_style=visual_style,
            music_style=music_style,
            voice_profile=voice_profile,
        )

        # Stage 3: Memory update (store key facts about characters/environments)
        self.consistency_memory.record_storyboard(project_name=project_name, storyboard=storyboard)

        # Stage 4: Synthesis
        synthesis_result: VideoSynthesisResult = await self.synthesis_service.render_video(
            project_name=project_name,
            scene_requests=scene_requests,
            voice_profile=voice_profile,
            use_external_apis=enable_external_apis,
        )

        return {
            "storyboard": storyboard,
            "scene_requests": scene_requests,
            "consistency": self.consistency_memory.describe(project_name=project_name),
            "synthesis": synthesis_result.to_dict(),
            "video_path": str(synthesis_result.output_path),
        }


__all__ = [
    "CinematicVideoAgent",
    "ConsistencyMemory",
    "SceneOrchestrator",
    "StoryboardGenerator",
    "VideoSynthesisResult",
    "VideoSynthesisService",
]

