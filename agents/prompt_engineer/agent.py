"""Prompt Engineer Agent — builds the script-writing prompt from research."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from prompts import render_prompt

# Hindi edge-tts at +8% speaks roughly 2.5 words/second.
WORDS_PER_SEC = 2.5


class PromptEngineerAgent(BaseAgent):
    name = "prompt_engineer"

    def word_bounds(self) -> tuple:
        v = self.config.video
        return int(v.target_duration * 0.85 * WORDS_PER_SEC), int(v.max_duration * 0.92 * WORDS_PER_SEC)

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        research_data = kwargs.get("research_data", {}) or {}
        category = kwargs.get("topic_category", "")
        items = research_data.get("items", [])
        min_w, max_w = self.word_bounds()

        if video_type == "news":
            prompt = render_prompt("scripting/news_script.j2", {
                "items": items, "pick_count": 3, "min_words": min_w, "max_words": max_w})
        else:
            if not items:
                return AgentResult(success=False, errors=["No research topic available"])
            prompt = render_prompt("scripting/knowledge_script.j2", {
                "topic": items[0], "category": category, "min_words": min_w, "max_words": max_w})

        return AgentResult(success=True, data={"prompt": prompt, "min_words": min_w, "max_words": max_w},
                           metadata={"video_type": video_type})
