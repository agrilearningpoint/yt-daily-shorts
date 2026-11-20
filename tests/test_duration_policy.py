"""Unit and integration tests for YouTube Shorts centralized duration policy.

Enforces:
- SHORTS_HARD_LIMIT = 59.9s
- SHORTS_SAFE_MAX = 59.5s
- SHORTS_MIN_DURATION = 15.0s
- NEWS_TARGET_DURATION = 56.0s
"""

import pytest
from types import SimpleNamespace

from core.duration import (
    SHORTS_HARD_LIMIT,
    SHORTS_SAFE_MAX,
    SHORTS_MIN_DURATION,
    NEWS_TARGET_DURATION,
    is_duration_valid,
    bounds,
    news_targets,
)
from agents.publisher.agent import PublisherAgent
from video.qa_inspector import VideoQAInspector


def test_duration_constants():
    assert SHORTS_HARD_LIMIT == 59.9
    assert SHORTS_SAFE_MAX == 59.5
    assert SHORTS_MIN_DURATION == 15.0
    assert NEWS_TARGET_DURATION == 56.0


@pytest.mark.parametrize(
    "duration, expected",
    [
        (14.9, False),
        (15.0, True),
        (25.0, True),
        (55.0, True),
        (56.0, True),
        (58.0, True),
        (59.5, True),
        (59.9, True),
        (60.0, False),
        (65.0, False),
        (130.0, False),
        (150.0, False),
        (179.0, False),
    ],
)
def test_is_duration_valid(duration, expected):
    assert is_duration_valid(duration) == expected


def test_bounds_news_never_exceeds_safe_max():
    cfg = SimpleNamespace(
        news_max_duration=150.0,
        min_duration=10.0,
        max_duration=180.0,
    )
    lo, hi = bounds(cfg, "news")
    assert lo >= SHORTS_MIN_DURATION
    assert hi <= SHORTS_SAFE_MAX

    lo_k, hi_k = bounds(cfg, "knowledge")
    assert lo_k >= SHORTS_MIN_DURATION
    assert hi_k <= SHORTS_SAFE_MAX


def test_news_targets_capped_at_safe_max():
    cfg = SimpleNamespace(
        news_national_count=20,
        news_international_count=10,
        news_target_duration=120.0,
    )
    items = [{"region": "national"}] * 30 + [{"region": "international"}] * 10
    targets = news_targets(cfg, items)
    assert targets["seconds"] <= SHORTS_SAFE_MAX
    assert targets["seconds"] >= SHORTS_MIN_DURATION


def test_video_qa_inspector_duration_bounds():
    inspector = VideoQAInspector()
    assert inspector.max_duration == SHORTS_HARD_LIMIT
    assert inspector.min_duration == SHORTS_MIN_DURATION


@pytest.mark.asyncio
async def test_publisher_rejects_out_of_bounds_duration(tmp_path, monkeypatch):
    from core.configuration import AppConfig
    from core.state_manager import StateManager

    cfg = AppConfig()
    cfg.general.dry_run = True
    sm = StateManager(":memory:")
    agent = PublisherAgent(cfg, sm)

    # Create dummy dummy file
    dummy_video = tmp_path / "test_out_of_bounds.mp4"
    dummy_video.write_bytes(b"dummy video content")

    # Mock probe_duration to 62.0s
    monkeypatch.setattr("agents.publisher.agent.probe_duration", lambda p: 62.0)

    result = await agent.execute(video_path=str(dummy_video))
    assert not result.success
    assert any("outside Shorts limits" in err for err in result.errors)

    # Mock probe_duration to 10.0s (under 15s)
    monkeypatch.setattr("agents.publisher.agent.probe_duration", lambda p: 10.0)

    result_short = await agent.execute(video_path=str(dummy_video))
    assert not result_short.success
    assert any("outside Shorts limits" in err for err in result_short.errors)
