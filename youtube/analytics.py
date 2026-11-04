"""Video statistics via YouTube Data API v3."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from youtube.oauth import YouTubeOAuthManager

logger = logging.getLogger("youtube.analytics")


class YouTubeAnalyticsFetcher:
    def __init__(self, oauth_manager: YouTubeOAuthManager):
        self.oauth_manager = oauth_manager

    def get_many(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        creds = self.oauth_manager.get_credentials()
        if not creds or not video_ids:
            return {}
        try:
            from googleapiclient.discovery import build
            yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
            out = {}
            for i in range(0, len(video_ids), 50):
                resp = yt.videos().list(part="statistics", id=",".join(video_ids[i:i + 50])).execute()
                for it in resp.get("items", []):
                    st = it.get("statistics", {})
                    out[it["id"]] = {"video_id": it["id"], "views": int(st.get("viewCount", 0)),
                                     "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0))}
            return out
        except Exception as exc:
            logger.warning("Stats fetch failed: %s", exc)
            return {}

    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        if video_id.startswith(("mock_", "dry_run_")):
            return {"video_id": video_id, "views": 0, "likes": 0, "comments": 0, "status": "mock_data"}
        return self.get_many([video_id]).get(video_id, {"video_id": video_id, "views": 0, "likes": 0, "comments": 0})
