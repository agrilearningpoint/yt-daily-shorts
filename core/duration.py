"""One source of truth for spoken-length estimates and news story targets.

Script Manager, Quality Manager and the post-render check all use these, so a
script the writer accepts can never be rejected later for length.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Base speed measured on the Hindi neural voices, at tts.rate = +0%.
_BASE_WORDS_PER_SEC = {"news": 2.3, "knowledge": 2.4}
# The channel owner's voice setting (2026-11-11): 1.2x. edge-tts "+20%", Gemini style "brisk".
VOICE_SPEED = 1.2
# Everything that estimates length must use these, or a script the writer accepts gets rejected later.
WORDS_PER_SEC = {k: round(v * VOICE_SPEED, 3) for k, v in _BASE_WORDS_PER_SEC.items()}
SHORTS_HARD_LIMIT = 179.0                         # YouTube Shorts max is 180 s
MIN_NEWS_STORIES = 12                             # below this we skip the day instead of padding with old news


def words_of(script: Dict[str, Any]) -> int:
    n = len((script.get("hook") or "").split()) + len((script.get("outro") or "").split())
    for s in script.get("scenes", []) or []:
        n += len((s.get("narration") or "").split())
    return n


def estimate_seconds(script: Dict[str, Any]) -> float:
    vt = script.get("video_type", "knowledge")
    return words_of(script) / WORDS_PER_SEC.get(vt, 2.4)


def news_targets(cfg_video, items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Story counts for today, scaled down when fewer FRESH stories exist (never padded with old news)."""
    nat_avail = sum(1 for i in items if i.get("region") != "international")
    intl_avail = sum(1 for i in items if i.get("region") == "international")
    nat = min(cfg_video.news_national_count, max(nat_avail - 2, 0))
    intl = min(cfg_video.news_international_count, max(intl_avail - 1, 0))
    full = cfg_video.news_national_count + cfg_video.news_international_count
    seconds = round(cfg_video.news_target_duration * max(nat + intl, 1) / full)
    seconds = max(55, min(seconds, cfg_video.news_target_duration))
    return {"national": nat, "international": intl, "total": nat + intl, "seconds": seconds,
            "min_national": max(1, nat - 6) if nat > 8 else nat,
            "min_international": min(intl, 5)}


def bounds(cfg_video, video_type: str, targets: Dict[str, int] | None = None) -> Tuple[float, float]:
    """Allowed spoken duration (seconds) for a script, before TTS."""
    if video_type == "news":
        hi = cfg_video.news_max_duration
        if targets and targets.get("seconds"):
            hi = min(hi, targets["seconds"] * 1.15)
        return max(30.0, cfg_video.min_duration), min(float(hi), SHORTS_HARD_LIMIT)
    return float(cfg_video.min_duration), float(cfg_video.max_duration) * 1.25
