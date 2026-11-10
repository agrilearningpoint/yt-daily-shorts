"""SEO Manager Agent: search-first title, description (no links/credits), tags, hashtags."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List
from zoneinfo import ZoneInfo

from agents.base_agent import AgentResult, BaseAgent
from prompts import render_prompt
from youtube.seo import (YouTubeSEOFormatter, build_hashtags, build_tags, lint_title, pick_best_title,
                         query_coverage)

BASE_TAGS = {
    "news": ["hindi news", "aaj ki khabar", "today news", "breaking news hindi", "current affairs", "india news"],
    "knowledge": ["hindi facts", "rochak tathya", "gk in hindi", "history in hindi", "india facts", "knowledge"],
}


HINDI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
                "नवंबर", "दिसंबर"]


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
        raw_hashtags: List[str] = []
        headlines: List[str] = []
        keywords_paragraph = ""
        queries: List[str] = []
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        date_en = now.strftime("%d %B %Y").lstrip("0").lower()
        date_hi = f"{now.day} {HINDI_MONTHS[now.month - 1]} {now.year}"
        if self.llm is not None:
            try:
                # titles/tags decide the click-through rate — best model first
                meta = await self.llm.generate_json(render_prompt("seo/metadata.j2", {
                    "script": script, "video_type": video_type, "date_en": date_en,
                    "date_hi": date_hi}), tier="quality")
                cands = [str(t) for t in (meta.get("titles") or []) if str(t).strip()]
                if meta.get("title"):
                    cands.append(str(meta["title"]))
                best = pick_best_title(cands)
                if best:
                    title = best
                l1 = str(meta.get("description_line1") or meta.get("description_hook") or "").strip()
                l2 = str(meta.get("description_line2") or "").strip()
                if l1:
                    hook_line = l1 + ("\n" + l2 if l2 else "")
                headlines = [str(h).strip() for h in (meta.get("headlines") or []) if str(h).strip()]
                keywords_paragraph = str(meta.get("keywords_paragraph") or "").strip()
                tags = [str(t).strip().lstrip("#") for t in (meta.get("tags") or []) if str(t).strip()]
                raw_hashtags = [str(h) for h in (meta.get("hashtags") or [])]
                queries = [str(q) for q in (meta.get("search_queries") or [])]
                self.logger.info("SEO title=%r lint=%s queries=%s coverage=%.0f%%", title,
                                 lint_title(title)["score"], queries,
                                 100 * query_coverage(queries, title, hook_line))
            except Exception as exc:
                self.logger.warning("SEO LLM step failed, using script title: %s", exc)

        if not headlines:   # fallback: story chips from the script, no links
            headlines = [str(sc.get("on_screen_text") or sc.get("headline") or "").strip()
                         for sc in script.get("scenes", [])]
            headlines = [h for h in dict.fromkeys(headlines) if h]
        title = YouTubeSEOFormatter.format_title(title, max_length=self.config.seo.max_title_length)
        if video_type == "news":
            hashtags = build_hashtags(raw_hashtags, ["#Shorts", "#HindiNews"], max_n=5)
        else:
            hashtags = build_hashtags(raw_hashtags, ["#Shorts", "#gk"], max_n=5)
        description = YouTubeSEOFormatter.format_description(
            summary_hook=hook_line,
            story_lines=headlines[:20] if video_type == "news" else [],
            headlines_title=f"आज की बड़ी खबरें ({date_hi})" if video_type == "news" else "",
            keywords_paragraph=keywords_paragraph,
            hashtags=hashtags,
            channel_name=self.config.general.channel_name,
            media_credits=production.get("media_credits", []),
            max_length=self.config.seo.max_description_length,
        )
        date_tags = [f"{date_en} news", f"{date_hi} news", "aaj ki taza khabar"] if video_type == "news" else []
        trimmed = build_tags(tags + date_tags + BASE_TAGS.get(video_type, []) + ["shorts", "hindi"])
        category = self.config.youtube.news_category_id if video_type == "news" else self.config.youtube.knowledge_category_id
        return AgentResult(success=True, data={"title": title, "description": description, "tags": trimmed,
                                               "hashtags": hashtags, "category_id": category})
