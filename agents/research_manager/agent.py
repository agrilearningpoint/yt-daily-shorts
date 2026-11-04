"""Research Manager Agent — discovers topics and collects information."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from research.news_collector import NewsCollector, ProcessedNewsItem
from research.trend_discovery import TrendDiscovery, TopicDetails


class ResearchManagerAgent(BaseAgent):
    """Discovers relevant topics and collects reliable information."""

    name = "research_manager"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.collector = NewsCollector()
        self.trend = TrendDiscovery()

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        topic_category = kwargs.get("topic_category", "")

        self.logger.info("Researching for %s — %s", video_type, topic_category)

        if video_type == "news":
            items = self.collector.collect_and_rank_news(target_count=3)
            data_items = [vars(i) for i in items]
            sources = [i.source_url for i in items]
        else:
            day_name = topic_category.split()[0] if topic_category else "tuesday"
            topic_detail = self.trend.discover_calendar_topic(day_name=day_name)
            data_items = [vars(topic_detail)]
            sources = [topic_detail.source_url]

        return AgentResult(
            success=bool(data_items),
            data={"items": data_items, "sources": sources},
            metadata={"video_type": video_type, "topic_category": topic_category},
        )
