"""Analytics Manager Agent — collects performance metrics."""

from __future__ import annotations

from typing import Any, List
from agents.base_agent import AgentResult, BaseAgent
from youtube.analytics import YouTubeAnalyticsFetcher
from youtube.oauth import YouTubeOAuthManager


class AnalyticsManagerAgent(BaseAgent):
    """Tracks views, likes, comments, and engagement."""

    name = "analytics_manager"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.oauth_manager = YouTubeOAuthManager(
            client_secret_json=self.config.youtube.client_secret_json,
            token_json=self.config.youtube.token_json
        )
        self.analytics = YouTubeAnalyticsFetcher(self.oauth_manager)

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_ids = kwargs.get("video_ids", [])
        metrics = []
        for vid in video_ids:
            stats = self.analytics.get_video_stats(vid)
            metrics.append(stats)

        return AgentResult(
            success=True,
            data={"metrics": metrics}
        )
