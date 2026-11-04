"""Research Manager Agent — discovers topics and collects reliable information."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

import pytz

from agents.base_agent import AgentResult, BaseAgent
from research.news_collector import NewsCollector
from research.trend_discovery import TrendDiscovery, normalize_day


class ResearchManagerAgent(BaseAgent):
    name = "research_manager"

    def __init__(self, config, state_manager, history=None, llm=None):
        super().__init__(config, state_manager)
        self.history = history
        self.llm = llm
        self.collector = NewsCollector(allow_offline_fallback=not config.general.strict_mode)
        self.trend = TrendDiscovery()

    def _today(self) -> str:
        return datetime.now(pytz.timezone(self.config.general.timezone)).strftime("%A").lower()

    async def _llm_fresh_topic(self, category: str, used: List[str]) -> Optional[str]:
        if not self.llm:
            return None
        prompt = (
            f"Suggest ONE fresh, specific topic for a 50-second Hindi YouTube Short in the category "
            f"'{category}' for an Indian audience. It must have a dedicated English Wikipedia article. "
            f"Do NOT use any of these already-covered topics: {', '.join(used[-80:])}. "
            'Respond as JSON: {"wikipedia_title": "..."}'
        )
        try:
            data = await self.llm.generate_json(prompt)
            return (data.get("wikipedia_title") or "").strip() or None
        except Exception as exc:
            self.logger.warning("LLM topic suggestion failed: %s", exc)
            return None

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        topic_category = kwargs.get("topic_category", "")
        day_name = normalize_day(kwargs.get("day_name", "")) or self._today()
        self.logger.info("Researching %s — %s (%s)", video_type, topic_category, day_name)

        if video_type == "news":
            exclude = self.history.recent_news() if self.history else []
            n = self.config.video.news_headline_count
            items = self.collector.collect_and_rank_news(target_count=max(n + 18, 40), exclude=exclude)
            data_items = [vars(i) for i in items]
            sources = [i.source_url for i in items]
        else:
            used = self.history.used_topics() if self.history else []
            seed = self.trend.pick_seed(day_name, used)
            if seed is None:
                seed = await self._llm_fresh_topic(topic_category, used)
            topic = self.trend.discover_calendar_topic(day_name, used, seed_override=seed)
            if not topic.summary and self.config.general.strict_mode:
                return AgentResult(success=False, errors=[f"No Wikipedia content for topic '{topic.title}'"])
            data_items = [vars(topic)]
            sources = [topic.source_url]

        return AgentResult(
            success=bool(data_items),
            data={"items": data_items, "sources": sources, "day_name": day_name},
            metadata={"video_type": video_type, "topic_category": topic_category},
        )
