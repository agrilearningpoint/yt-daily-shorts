"""Creative Director Agent — assigns unique themes and visual variations."""

from __future__ import annotations

from typing import Any
from agents.base_agent import AgentResult, BaseAgent
from video.creative_variation import CreativeVariationEngine


class CreativeDirectorAgent(BaseAgent):
    """Directs styling, themes, transitions, and audio moods."""

    name = "creative_director"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.variation_engine = CreativeVariationEngine()

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        video_type = script.get("video_type", "news")

        theme = self.variation_engine.get_next_theme(video_type)

        return AgentResult(
            success=True,
            data={
                "theme_name": theme.name,
                "primary_color": theme.primary_color,
                "secondary_color": theme.secondary_color,
                "background_color": theme.background_color,
                "transition": theme.transition,
                "music_mood": theme.music_mood,
                "font_name": theme.font_name,
            }
        )
