"""Video Producer Agent — coordinates TTS, visuals, subtitles, and rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent
from video.media_collector import MediaCollector
from video.renderer import VideoRenderer
from video.subtitle_generator import SubtitleGenerator
from video.tts import TTSEngine


class VideoProducerAgent(BaseAgent):
    """Produces the final 1080x1920 MP4 video."""

    name = "video_producer"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.tts = TTSEngine(
            voice=self.config.tts.voice,
            rate=self.config.tts.rate,
            pitch=self.config.tts.pitch
        )
        self.media_collector = MediaCollector(
            pexels_key=self.config.media.pexels_api_key,
            pixabay_key=self.config.media.pixabay_api_key,
            cache_dir=self.config.media.cache_dir
        )
        self.subtitle_gen = SubtitleGenerator()
        self.renderer = VideoRenderer(
            width=self.config.video.width,
            height=self.config.video.height,
            fps=self.config.video.fps
        )

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        creative_brief = kwargs.get("creative_brief", {})
        video_id = kwargs.get("video_id", "daily_short")

        self.logger.info("Starting complete video production for %s", video_id)

        out_dir = Path("output") / video_id
        out_dir.mkdir(parents=True, exist_ok=True)

        scenes = script.get("scenes", [])
        hook = script.get("hook", "")
        
        # 1. Generate Voiceover Audio
        full_narration = f"{hook}. " + " ".join(s.get("narration", "") for s in scenes)
        audio_path = str(out_dir / "voiceover.mp3")
        await self.tts.generate_audio(full_narration, audio_path)

        # 2. Collect Visuals per Scene
        visual_paths: List[str] = []
        for idx, s in enumerate(scenes, 1):
            query = s.get("visual_instructions") or s.get("narration") or "India Breaking News"
            dest = str(out_dir / f"scene_{idx}.jpg")
            v_path = self.media_collector.get_scene_visual(idx, query, dest, script.get("video_type", "news"))
            visual_paths.append(v_path)

        # 3. Generate Subtitles (SRT)
        srt_path = str(out_dir / "subtitles.srt")
        self.subtitle_gen.generate_srt(scenes, srt_path)

        # 4. Render Final Video
        final_video_path = str(out_dir / "final_short.mp4")
        self.renderer.render_vertical_short(
            scene_visuals=visual_paths,
            audio_path=audio_path,
            output_path=final_video_path,
            subtitle_path=srt_path,
            duration_per_scene=18.0
        )

        return AgentResult(
            success=Path(final_video_path).exists(),
            data={
                "video_path": final_video_path,
                "audio_path": audio_path,
                "subtitle_path": srt_path,
                "scene_visuals": visual_paths
            }
        )
