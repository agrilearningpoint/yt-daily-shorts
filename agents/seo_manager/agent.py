"""SEO Manager Agent — formats optimized titles, descriptions, and tags."""

from __future__ import annotations

from typing import Any
from agents.base_agent import AgentResult, BaseAgent
from youtube.seo import YouTubeSEOFormatter


class SEOManagerAgent(BaseAgent):
    """Generates high-performing, compliant YouTube Shorts metadata."""

    name = "seo_manager"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        video_type = script.get("video_type", "news")

        raw_title = script.get("title", f"Daily {video_type.title()} Short")
        title = YouTubeSEOFormatter.format_title(raw_title, max_length=self.config.seo.max_title_length)

        sources = script.get("sources", [])
        hook = script.get("hook", "")
        hashtags = self.config.seo.default_hashtags
        description = YouTubeSEOFormatter.format_description(
            summary_hook=hook,
            source_urls=sources,
            hashtags=hashtags,
            channel_name=self.config.general.project_name
        )

        tags = ["shorts", "hindi", "news", "facts", "india", "upsc", "knowledge"]
        if video_type == "news":
            tags.extend(["daily news", "breaking news hindi", "current affairs"])
        else:
            tags.extend(["history facts", "science news", "bharat"])

        return AgentResult(
            success=True,
            data={
                "title": title,
                "description": description,
                "tags": tags,
                "hashtags": hashtags,
                "category_id": self.config.youtube.category_id
            }
        )
