"""Publisher Agent — uploads videos to YouTube via Data API v3 with DRY_RUN."""

from __future__ import annotations

from typing import Any
from agents.base_agent import AgentResult, BaseAgent
from youtube.oauth import YouTubeOAuthManager
from youtube.uploader import YouTubeUploader


class PublisherAgent(BaseAgent):
    """Uploads videos to YouTube using official Data API v3."""

    name = "publisher"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.oauth_manager = YouTubeOAuthManager(
            client_secret_json=self.config.youtube.client_secret_json,
            token_json=self.config.youtube.token_json
        )
        self.uploader = YouTubeUploader(
            oauth_manager=self.oauth_manager,
            dry_run=self.config.general.dry_run or self.config.youtube.dry_run
        )

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_path = kwargs.get("video_path", "")
        seo_data = kwargs.get("seo_data", {})

        title = seo_data.get("title", "Daily Short #shorts")
        description = seo_data.get("description", "")
        tags = seo_data.get("tags", [])
        category_id = seo_data.get("category_id", self.config.youtube.category_id)
        privacy = self.config.youtube.default_privacy

        res = self.uploader.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy_status=privacy
        )

        success = res is not None
        yt_id = res.get("id", "") if res else ""
        yt_url = res.get("url", "") if res else ""

        return AgentResult(
            success=success,
            data={"youtube_id": yt_id, "youtube_url": yt_url, "upload_details": res}
        )
