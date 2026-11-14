"""Quota-efficient YouTube Trending Scout using videos.list(chart=mostPopular) = 1 unit/call."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def fetch_trending_india(
    youtube_service: Any,
    category_id: str = "25",
    region_code: str = "IN",
    max_results: int = 15,
) -> List[Dict[str, Any]]:
    """
    Fetch currently trending videos in India using YouTube Data API v3.
    Uses videos.list(chart='mostPopular') which costs only 1 quota unit (vs 100 for search.list).
    """
    req = youtube_service.videos().list(
        part="snippet,statistics,contentDetails",
        chart="mostPopular",
        regionCode=region_code,
        videoCategoryId=category_id,
        maxResults=max_results,
    )
    resp = req.execute()
    results: List[Dict[str, Any]] = []
    for item in resp.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        results.append(
            {
                "video_id": item.get("id"),
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "tags": snippet.get("tags", [])[:10],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "published_at": snippet.get("publishedAt", ""),
            }
        )
    results.sort(key=lambda x: x["views"], reverse=True)
    return results


def build_trend_prompt_context(trending_items: List[Dict[str, Any]], top_n: int = 5) -> str:
    """Summarize top trending titles and hook structures for the script generator."""
    if not trending_items:
        return "No live trending context available."
    lines = ["Top Currently Trending Indian Videos (Learn hook style & curiosity triggers):"]
    for i, item in enumerate(trending_items[:top_n], 1):
        lines.append(f"{i}. {item['title']} ({item['views']:,} views)")
    return "\n".join(lines)
