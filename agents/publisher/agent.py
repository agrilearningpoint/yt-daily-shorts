"""Publisher Agent — uploads to YouTube (strict in live mode)."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from youtube.oauth import YouTubeOAuthManager
from youtube.uploader import YouTubeUploader


class PublisherAgent(BaseAgent):
    name = "publisher"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.oauth_manager = YouTubeOAuthManager(config.youtube.client_secret_json, config.youtube.token_json)
        self.uploader = YouTubeUploader(self.oauth_manager, dry_run=config.general.dry_run,
                                        strict=config.general.strict_mode)

    async def execute(self, **kwargs: Any) -> AgentResult:
        seo = kwargs.get("seo_data", {}) or {}
        try:
            res = self.uploader.upload_video(
                video_path=kwargs.get("video_path", ""),
                title=seo.get("title", "Daily Short #shorts"),
                description=seo.get("description", ""),
                tags=seo.get("tags", []),
                category_id=seo.get("category_id", self.config.youtube.knowledge_category_id),
                privacy_status=self.config.youtube.default_privacy,
                contains_synthetic_media=self.config.youtube.contains_synthetic_media,
                thumbnail_path=kwargs.get("thumbnail_path"),
            )
        except Exception as exc:
            return AgentResult(success=False, errors=[str(exc)])
        return AgentResult(success=bool(res and res.get("id")),
                           data={"youtube_id": res.get("id", ""), "youtube_url": res.get("url", ""),
                                 "upload_details": res})
