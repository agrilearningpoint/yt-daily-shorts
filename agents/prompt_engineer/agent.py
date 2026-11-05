"""Prompt Engineer Agent — builds the script-writing prompt from research."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from prompts import render_prompt

# Natural Hindi narration speed (words/second)
WORDS_PER_SEC = {"news": 2.5, "knowledge": 2.4}  # measured on Gemini TTS Hindi


class PromptEngineerAgent(BaseAgent):
    name = "prompt_engineer"

    def word_bounds(self, video_type: str = "knowledge") -> tuple:
        v = self.config.video
        if video_type == "news":
            n = self.config.video.news_headline_count
            return n * 13 + 10, n * 16 + 14
        wps = WORDS_PER_SEC["knowledge"]
        return int(v.target_duration * 0.95 * wps), int(v.max_duration * 1.15 * wps)

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        research_data = kwargs.get("research_data", {}) or {}
        category = kwargs.get("topic_category", "")
        items = research_data.get("items", [])
        min_w, max_w = self.word_bounds(video_type)

        if video_type == "news":
            n = self.config.video.news_headline_count
            if len(items) < n:
                return AgentResult(success=False, errors=[f"only {len(items)} candidate stories, need {n}"])
            prompt = render_prompt("scripting/news_script.j2", {
                "items": items, "count": n, "seconds": self.config.video.news_max_duration, "min_words": min_w, "max_words": max_w})
        else:
            if not items:
                return AgentResult(success=False, errors=["No research topic available"])
            prompt = render_prompt("scripting/knowledge_script.j2", {
                "topic": items[0], "category": category, "min_words": min_w, "max_words": max_w})

        return AgentResult(success=True, data={"prompt": prompt, "min_words": min_w, "max_words": max_w},
                           metadata={"video_type": video_type})
