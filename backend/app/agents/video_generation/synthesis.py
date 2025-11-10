"""
Video synthesis orchestrator.

Attempts to render cinematic videos using provider APIs when available,
otherwise falls back to the built-in cinematic renderer powered by MoviePy.
"""

from __future__ import annotations

import asyncio
import os
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy.editor import AudioClip, ImageClip, concatenate_videoclips
except Exception as exc:  # pragma: no cover - lazily handle import issues
    ImageClip = None  # type: ignore
    concatenate_videoclips = None  # type: ignore
    AudioClip = None  # type: ignore
    MOVIEPY_IMPORT_ERROR = exc
else:
    MOVIEPY_IMPORT_ERROR = None


DEFAULT_RESOLUTION = (1280, 720)


@dataclass
class VideoSynthesisResult:
    """Container for synthesis metadata."""

    output_path: Path
    provider: str
    duration_seconds: int
    scene_count: int
    used_external_api: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "provider": self.provider,
            "duration_seconds": self.duration_seconds,
            "scene_count": self.scene_count,
            "used_external_api": self.used_external_api,
        }


class VideoSynthesisService:
    """Render cinematic videos from orchestrated scene directives."""

    def __init__(self, base_output_dir: Path) -> None:
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

    async def render_video(
        self,
        *,
        project_name: str,
        scene_requests: list[dict[str, Any]],
        voice_profile: str,
        use_external_apis: bool,
    ) -> VideoSynthesisResult:
        if use_external_apis:
            external_result = await self._try_external_provider(
                project_name=project_name,
                scene_requests=scene_requests,
                voice_profile=voice_profile,
            )
            if external_result:
                return external_result

        # Fallback to local cinematic renderer
        return await self._render_with_cinematic_fallback(
            project_name=project_name,
            scene_requests=scene_requests,
            voice_profile=voice_profile,
        )

    async def _try_external_provider(
        self,
        *,
        project_name: str,
        scene_requests: list[dict[str, Any]],
        voice_profile: str,
    ) -> VideoSynthesisResult | None:
        """
        Attempt to call a configured external provider (Veo, Runway, Pika, etc.).
        Currently this is a stub that validates environment configuration and
        returns ``None`` if no provider is configured.
        """
        provider = os.getenv("VIDEO_PROVIDER")
        api_key = os.getenv("VIDEO_PROVIDER_API_KEY")

        if not provider or not api_key:
            return None

        # TODO: Implement specific provider clients when APIs become available.
        # For now we log intent and fall back to cinematic renderer.
        return None

    async def _render_with_cinematic_fallback(
        self,
        *,
        project_name: str,
        scene_requests: list[dict[str, Any]],
        voice_profile: str,
    ) -> VideoSynthesisResult:
        if MOVIEPY_IMPORT_ERROR:
            raise RuntimeError(
                "MoviePy is required for the cinematic renderer. "
                f"Import error: {MOVIEPY_IMPORT_ERROR}"
            )

        project_slug = project_name.lower().replace(" ", "-")
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"{project_slug}-{timestamp}.mp4"
        output_path = self.base_output_dir / filename

        clips: list[ImageClip] = []
        total_duration = 0

        for scene in scene_requests:
            duration = int(scene.get("duration_seconds", 12))
            frame = self._render_scene_frame(scene)
            clip = ImageClip(frame).set_duration(duration)
            clips.append(clip)
            total_duration += duration

        if not clips:
            raise ValueError("No scene clips generated")

        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(self._create_ambient_audio(total_duration))

        # Write video asynchronously to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: video.write_videofile(
                str(output_path),
                fps=24,
                codec="libx264",
                audio_codec="aac",
                verbose=False,
                logger=None,
            ),
        )

        # Cleanup clips
        video.close()
        for clip in clips:
            clip.close()

        return VideoSynthesisResult(
            output_path=output_path,
            provider="cinematic_fallback",
            duration_seconds=total_duration,
            scene_count=len(scene_requests),
            used_external_api=False,
        )

    def _render_scene_frame(self, scene: dict[str, Any]) -> np.ndarray:
        width, height = DEFAULT_RESOLUTION
        img = Image.new("RGB", (width, height), color=(8, 10, 28))
        draw = ImageDraw.Draw(img)

        title_font = self._load_font(size=48)
        body_font = self._load_font(size=30)
        subtitle_font = self._load_font(size=24)

        # Title
        draw.text((60, 60), scene.get("title", "Scene"), fill=(255, 215, 0), font=title_font)

        # Summary
        wrapped_summary = textwrap.fill(scene.get("prompt", ""), width=48)
        draw.text((60, 150), wrapped_summary, fill=(220, 230, 255), font=body_font)

        # Camera direction
        camera_text = f"Camera: {scene.get('camera', '')}"
        wrapped_camera = textwrap.fill(camera_text, width=60)
        draw.text((60, 420), wrapped_camera, fill=(180, 190, 255), font=subtitle_font)

        # Characters
        characters = scene.get("characters", [])
        if characters:
            character_lines = [
                f"{char.get('name', 'Unknown')} – {char.get('appearance', 'consistent look')}"
                for char in characters
            ]
            wrapped_characters = "\n".join(character_lines[:4])
            draw.text((60, 520), wrapped_characters, fill=(200, 210, 240), font=subtitle_font)

        return np.array(img)

    def _load_font(self, *, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size=size)
        except Exception:
            return ImageFont.load_default()

    def _create_ambient_audio(self, duration: int) -> AudioClip | None:
        """
        Create a soft ambient synth pad using a simple sine wave.  This avoids
        external dependencies while still providing a cinematic audio bed.
        """
        if AudioClip is None:
            return None

        base_frequency = 220.0
        amplitude = 0.02

        def synth_wave(t: np.ndarray) -> np.ndarray:
            modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
            return amplitude * np.sin(2 * np.pi * base_frequency * t) * modulation

        return AudioClip(synth_wave, duration=duration, fps=44100)


