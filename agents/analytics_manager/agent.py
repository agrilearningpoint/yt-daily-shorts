"""Analytics Manager Agent — refreshes view/like stats of recently published videos."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from youtube.analytics import YouTubeAnalyticsFetcher
from youtube.oauth import YouTubeOAuthManager


class AnalyticsManagerAgent(BaseAgent):
    name = "analytics_manager"

    def __init__(self, config, state_manager, history=None):
        super().__init__(config, state_manager)
        self.history = history
        self.analytics = YouTubeAnalyticsFetcher(
            YouTubeOAuthManager(config.youtube.client_secret_json, config.youtube.token_json))

    async def execute(self, **kwargs: Any) -> AgentResult:
        if not self.history:
            return AgentResult(success=True, data={"metrics": []})
        videos = [v for v in self.history.videos()
                  if v.get("youtube_id") and not str(v["youtube_id"]).startswith(("mock_", "dry_run_"))][-30:]
        ids = [v["youtube_id"] for v in videos]
        stats = self.analytics.get_many(ids) if ids else {}
        for v in self.history.data.get("videos", []):
            s = stats.get(v.get("youtube_id"))
            if s:
                v.update({"views": s["views"], "likes": s["likes"], "comments": s["comments"]})
        if stats:
            self.history._save()
        return AgentResult(success=True, data={"metrics": list(stats.values())})
