"""Publisher Agent — uploads to YouTube (strict in live mode)."""

from __future__ import annotations

from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from youtube.oauth import YouTubeOAuthManager
import os

from youtube.uploader import YouTubeUploader, publish_key


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
                publishing_key=publish_key(kwargs.get("video_type", "")),
                force=os.getenv("YT_FORCE_UPLOAD", "").lower() in ("1", "true", "yes"),
                captions_path=kwargs.get("captions_path"),
                playlist_title="आज की बड़ी खबरें | BHARAT KI SOCH" if kwargs.get("video_type") == "news" else "",
                comment=("आज की कौन-सी खबर आपको सबसे बड़ी लगी? कमेंट में बताइए 👇"
                         if kwargs.get("video_type") == "news" else ""),
            )
        except Exception as exc:
            return AgentResult(success=False, errors=[str(exc)])
        return AgentResult(success=bool(res and res.get("id")),
                           data={"youtube_id": res.get("id", ""), "youtube_url": res.get("url", ""),
                                 "upload_details": res})
