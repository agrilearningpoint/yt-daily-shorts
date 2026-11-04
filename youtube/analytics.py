"""Fetches video performance metrics via YouTube Data API v3."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from youtube.oauth import YouTubeOAuthManager

logger = logging.getLogger("youtube.analytics")


class YouTubeAnalyticsFetcher:
    """Retrieves view counts, likes, and comment counts."""

    def __init__(self, oauth_manager: YouTubeOAuthManager):
        self.oauth_manager = oauth_manager

    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Fetch statistics for a published video."""
        if video_id.startswith("mock_") or video_id.startswith("dry_run_"):
            return {
                "video_id": video_id,
                "views": 1500,
                "likes": 120,
                "comments": 15,
                "status": "mock_data"
            }

        creds = self.oauth_manager.get_credentials()
        if not creds:
            return {"video_id": video_id, "views": 0, "likes": 0, "comments": 0}

        try:
            from googleapiclient.discovery import build
            youtube = build("youtube", "v3", credentials=creds)

            resp = youtube.videos().list(part="statistics", id=video_id).execute()
            items = resp.get("items", [])
            if not items:
                return {"video_id": video_id, "views": 0, "likes": 0, "comments": 0}

            stats = items[0]["statistics"]
            return {
                "video_id": video_id,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            }
        except Exception as exc:
            logger.warning("Could not fetch YouTube statistics for %s: %s", video_id, exc)
            return {"video_id": video_id, "views": 0, "likes": 0, "comments": 0}
