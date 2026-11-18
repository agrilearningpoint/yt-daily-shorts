"""Motion Graphics Agent — designs broadcast-level graphics, overlays, and kinetic typography."""

from __future__ import annotations

from typing import Any, Dict, List
from agents.base_agent import AgentResult, BaseAgent
from video.motion_graphics import MotionGraphicsEngine


class MotionGraphicsAgent(BaseAgent):
    """Orchestrates broadcast news lower-thirds, live tickers, category badges, and story counters."""

    name = "motion_graphics"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        channel = getattr(self.config.general, "channel_name", "BHARAT KI SOCH")
        self.engine = MotionGraphicsEngine(channel_name=channel)

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        scenes = script.get("scenes", [])
        hook = script.get("hook", "")
        out_dir = kwargs.get("out_dir", "output/temp")

        self.logger.info("Generating broadcast motion graphics overlays for %d scenes", len(scenes))

        overlays: List[str] = []
        total = len(scenes)

        # Hook overlay
        if hook:
            hook_overlay = f"{out_dir}/overlay_hook.png"
            self.engine.compose_broadcast_overlay(
                out_path=hook_overlay,
                headline=hook,
                category="बड़ी खबर",
                story_index=0,
                total_stories=total,
                is_hook=True
            )
            overlays.append(hook_overlay)

        # Scene overlays
        for idx, s in enumerate(scenes, 1):
            sc_overlay = f"{out_dir}/overlay_scene_{idx:03d}.png"
            headline = s.get("on_screen_text") or s.get("headline") or s.get("narration") or ""
            cat = s.get("category") or "राष्ट्रीय"
            self.engine.compose_broadcast_overlay(
                out_path=sc_overlay,
                headline=headline[:60],
                category=cat,
                story_index=idx,
                total_stories=total,
                is_hook=False
            )
            overlays.append(sc_overlay)

        return AgentResult(
            success=True,
            data={"overlays": overlays, "total_overlays": len(overlays)}
        )
