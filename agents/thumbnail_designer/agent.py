"""Thumbnail Designer Agent — 1080x1920 cover with proper Hindi typography."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from video.scene_composer import SceneComposer


class ThumbnailDesignerAgent(BaseAgent):
    name = "thumbnail_designer"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        theme = kwargs.get("creative_brief", {}) or {}
        production = kwargs.get("production", {}) or {}
        video_id = kwargs.get("video_id", "daily_short")
        out_path = Path("output") / video_id / "thumbnail.jpg"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        comp = SceneComposer(theme, channel_name=self.config.general.channel_name)
        path = comp.compose_thumbnail(production.get("first_image"), str(out_path),
                                      script.get("title", "आज की बड़ी खबर"))
        return AgentResult(success=Path(path).exists(), data={"thumbnail_path": path})
