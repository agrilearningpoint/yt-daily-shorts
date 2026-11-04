"""Creative Director Agent — picks a visual theme that rotates across videos."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from video.creative_variation import CreativeVariationEngine


class CreativeDirectorAgent(BaseAgent):
    name = "creative_director"

    def __init__(self, config, state_manager, history=None):
        super().__init__(config, state_manager)
        recent = [v.get("theme", "") for v in (history.videos() if history else [])][-3:]
        self.variation_engine = CreativeVariationEngine(history=recent)

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        theme = self.variation_engine.get_next_theme(script.get("video_type", "news"))
        return AgentResult(success=True, data=theme.to_dict())
