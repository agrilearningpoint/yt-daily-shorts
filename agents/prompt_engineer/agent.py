"""Prompt Engineer Agent — crafts optimal instructions for script generation."""

from __future__ import annotations

from typing import Any
from agents.base_agent import AgentResult, BaseAgent
from prompts import render_prompt


class PromptEngineerAgent(BaseAgent):
    """Researches storytelling trends and generates optimized prompt instructions."""

    name = "prompt_engineer"

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        research_data = kwargs.get("research_data", {})

        self.logger.info("Generating storytelling prompt for %s", video_type)

        items = research_data.get("items", [])
        if video_type == "news":
            prompt = render_prompt("scripting/news_script.j2", {"items": items})
        else:
            topic_info = items[0] if items else {"title": "India History", "category": "General", "summary": "", "key_points": [], "source_url": "https://pib.gov.in"}
            prompt = render_prompt("scripting/knowledge_script.j2", {"topic": topic_info})

        return AgentResult(
            success=True,
            data={"prompt": prompt},
            metadata={"video_type": video_type},
        )
