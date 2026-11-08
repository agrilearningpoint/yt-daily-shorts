"""Prompt Engineer Agent — builds the script-writing prompt from research."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from core.duration import MIN_NEWS_STORIES as MIN_STORIES, news_targets
from prompts import render_prompt

# Natural Hindi narration speed (words/second)
WORDS_PER_SEC = {"news": 2.3, "knowledge": 2.4}  # measured on Gemini TTS Hindi


class PromptEngineerAgent(BaseAgent):
    name = "prompt_engineer"

    def word_bounds(self, video_type: str = "knowledge") -> tuple:
        v = self.config.video
        if video_type == "news":
            secs = self.config.video.news_target_duration
            return int(secs * 2.35), int(secs * 2.75)
        wps = WORDS_PER_SEC["knowledge"]
        return int(v.target_duration * 0.95 * wps), int(v.max_duration * 1.15 * wps)

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        research_data = kwargs.get("research_data", {}) or {}
        category = kwargs.get("topic_category", "")
        items = research_data.get("items", [])
        min_w, max_w = self.word_bounds(video_type)

        if video_type == "news":
            t = news_targets(self.config.video, items)
            if t["total"] < MIN_STORIES:
                return AgentResult(success=False, errors=[
                    f"only {t['total']} fresh (<24h, dated) stories available, need {MIN_STORIES}; not using old news"])
            min_w, max_w = int(t["seconds"] * 2.35), int(t["seconds"] * 2.75)
            prompt = render_prompt("scripting/news_script.j2", {
                "items": items, "count": t["total"], "seconds": t["seconds"],
                "national": t["national"], "international": t["international"],
                "min_words": min_w, "max_words": max_w})
            return AgentResult(success=True, data={"prompt": prompt, "min_words": min_w, "max_words": max_w,
                                                   "targets": t}, metadata={"video_type": video_type})
        else:
            if not items:
                return AgentResult(success=False, errors=["No research topic available"])
            prompt = render_prompt("scripting/knowledge_script.j2", {
                "topic": items[0], "category": category, "min_words": min_w, "max_words": max_w})

        return AgentResult(success=True, data={"prompt": prompt, "min_words": min_w, "max_words": max_w},
                           metadata={"video_type": video_type})
