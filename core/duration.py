"""Centralized duration policy and spoken-length estimates for YouTube Shorts.

Single source of truth across Script Manager, Hook Director, Video Producer,
QA Inspector, Master Editing Director, and Publisher.

YouTube Shorts Strict Duration Policy:
- SHORTS_HARD_LIMIT: 59.9 seconds (hard technical cap; YouTube rejects/reclassifies 60.0s+)
- SHORTS_SAFE_MAX:   59.5 seconds (safe rendering target leaving margin for container/muxing)
- SHORTS_MIN_DURATION: 15.0 seconds (minimum required for Shorts monetization/structure)
- NEWS_TARGET_DURATION: 56.0 seconds (target duration for daily news bulletins)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Centralized Shorts Duration Policy Constants
SHORTS_HARD_LIMIT = 59.9  # Strict technical ceiling (seconds)
SHORTS_SAFE_MAX = 59.5  # Safe target rendering ceiling (seconds)
SHORTS_MIN_DURATION = 15.0  # Strict minimum duration (seconds)
NEWS_TARGET_DURATION = 56.0  # Target duration for news bulletins (seconds)

# Base speaking speed measured on Hindi neural voices at tts.rate = +0%
_BASE_WORDS_PER_SEC = {"news": 2.3, "knowledge": 2.4, "repurposed_news": 2.3}

# Natural voice tempo (1.05x brisk broadcast delivery)
VOICE_SPEED = 1.05

# Words per second for length estimation
WORDS_PER_SEC = {k: round(v * VOICE_SPEED, 3) for k, v in _BASE_WORDS_PER_SEC.items()}

# Minimum stories for a rapid-fire news bulletin (5-8 stories for 56s Short)
MIN_NEWS_STORIES = 5


def words_of(script: Dict[str, Any]) -> int:
    """Calculate total word count in a script."""
    n = len((script.get("hook") or "").split()) + len((script.get("outro") or "").split())
    for s in script.get("scenes", []) or []:
        n += len((s.get("narration") or "").split())
    return n


def estimate_seconds(script: Dict[str, Any]) -> float:
    """Estimate spoken duration in seconds based on script word count and voice speed."""
    vt = script.get("video_type", "knowledge")
    wps = WORDS_PER_SEC.get(vt, 2.4)
    return words_of(script) / wps


def news_targets(cfg_video: Any, items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calculate news story counts scaled for a 56-second YouTube Short."""
    nat_avail = sum(1 for i in items if i.get("region") != "international")
    intl_avail = sum(1 for i in items if i.get("region") == "international")

    cfg_nat = getattr(cfg_video, "news_national_count", 6)
    cfg_intl = getattr(cfg_video, "news_international_count", 2)

    nat = min(cfg_nat, max(nat_avail, 1)) if nat_avail else 1
    intl = min(cfg_intl, max(intl_avail, 0))

    full = max(cfg_nat + cfg_intl, 1)
    target_sec = min(
        float(getattr(cfg_video, "news_target_duration", NEWS_TARGET_DURATION)), SHORTS_SAFE_MAX
    )

    seconds = round(target_sec * max(nat + intl, 1) / full)
    seconds = max(int(SHORTS_MIN_DURATION), min(int(seconds), int(SHORTS_SAFE_MAX)))

    return {
        "national": nat,
        "international": intl,
        "total": nat + intl,
        "seconds": seconds,
        "min_national": max(1, nat - 2),
        "min_international": min(intl, 2),
    }


def bounds(
    cfg_video: Any, video_type: str, targets: Optional[Dict[str, int]] = None
) -> Tuple[float, float]:
    """Allowed spoken duration (seconds) for a script before TTS generation."""
    min_d = max(
        float(SHORTS_MIN_DURATION), float(getattr(cfg_video, "min_duration", SHORTS_MIN_DURATION))
    )

    if video_type == "news":
        hi = min(float(getattr(cfg_video, "news_max_duration", SHORTS_SAFE_MAX)), SHORTS_SAFE_MAX)
        if targets and targets.get("seconds"):
            hi = min(hi, float(targets["seconds"]) * 1.08)
        return min_d, min(hi, SHORTS_SAFE_MAX)

    hi = min(float(getattr(cfg_video, "max_duration", 58.0)), SHORTS_SAFE_MAX)
    return min_d, min(hi, SHORTS_SAFE_MAX)


def is_duration_valid(duration_sec: float) -> bool:
    """Validate whether an actual rendered duration satisfies the Shorts policy."""
    return SHORTS_MIN_DURATION <= round(duration_sec, 2) <= SHORTS_HARD_LIMIT
