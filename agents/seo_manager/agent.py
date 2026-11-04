"""SEO Manager Agent — title, description (sources + credits), tags."""

from __future__ import annotations

from typing import Any, List

from agents.base_agent import AgentResult, BaseAgent
from prompts import render_prompt
from youtube.seo import YouTubeSEOFormatter

BASE_TAGS = {
    "news": ["hindi news", "aaj ki khabar", "today news", "breaking news hindi", "current affairs", "india news"],
    "knowledge": ["hindi facts", "rochak tathya", "gk in hindi", "history in hindi", "india facts", "knowledge"],
}


class SEOManagerAgent(BaseAgent):
    name = "seo_manager"

    def __init__(self, config, state_manager, llm=None):
        super().__init__(config, state_manager)
        self.llm = llm

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        production = kwargs.get("production", {}) or {}
        video_type = script.get("video_type", "news")

        title = script.get("title", "")
        hook_line = script.get("hook", "")
        tags: List[str] = []
        if self.llm is not None:
            try:
                meta = await self.llm.generate_json(render_prompt("seo/metadata.j2",
                                                                  {"script": script, "video_type": video_type}))
                title = (meta.get("title") or title).strip() or title
                hook_line = (meta.get("description_hook") or hook_line).strip()
                tags = [str(t).strip().lstrip("#") for t in (meta.get("tags") or []) if str(t).strip()]
            except Exception as exc:
                self.logger.warning("SEO LLM step failed, using script title: %s", exc)

        title = YouTubeSEOFormatter.format_title(title, max_length=self.config.seo.max_title_length)
        hashtags = list(self.config.seo.default_hashtags)
        hashtags.append("#news" if video_type == "news" else "#gk")
        description = YouTubeSEOFormatter.format_description(
            summary_hook=hook_line,
            source_urls=script.get("sources", []),
            hashtags=hashtags,
            channel_name=self.config.general.channel_name,
            media_credits=production.get("media_credits", []),
            max_length=self.config.seo.max_description_length,
        )
        all_tags = list(dict.fromkeys(["shorts", "hindi"] + tags + BASE_TAGS.get(video_type, [])))
        # YouTube allows ~500 chars of tags in total
        trimmed, size = [], 0
        for t in all_tags:
            if size + len(t) + 1 > 480:
                break
            trimmed.append(t)
            size += len(t) + 1
        category = self.config.youtube.news_category_id if video_type == "news" else self.config.youtube.knowledge_category_id
        return AgentResult(success=True, data={"title": title, "description": description, "tags": trimmed,
                                               "hashtags": hashtags, "category_id": category})
