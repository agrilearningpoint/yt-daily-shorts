"""Research tests (offline: network calls are stubbed)."""

from __future__ import annotations

from research.news_collector import NewsCollector
from research.source_registry import SourceRegistry
from research.trend_discovery import EDITORIAL_SEEDS, TrendDiscovery, normalize_day


def test_source_registry():
    reg = SourceRegistry()
    assert len(reg.get_all_sources()) >= 6
    assert reg.is_source_trusted("https://pib.gov.in/PressRelease.aspx")
    assert not reg.is_source_trusted("https://random-unverified-blog.xyz")


def test_news_collector_offline_fallback(monkeypatch):
    monkeypatch.setattr(NewsCollector, "_fetch_all", lambda self: [])
    ranked = NewsCollector().collect_and_rank_news(target_count=3)
    assert len(ranked) == 3 and ranked[0].source_url


def test_news_collector_strict_raises(monkeypatch):
    monkeypatch.setattr(NewsCollector, "_fetch_all", lambda self: [])
    try:
        NewsCollector(allow_offline_fallback=False).collect_and_rank_news()
        assert False, "should raise"
    except RuntimeError:
        pass


def test_normalize_day_handles_category_strings():
    assert normalize_day("Monday") == "monday"
    assert normalize_day("Indian Politics") == ""


def test_topic_rotation_skips_used():
    td = TrendDiscovery()
    first = EDITORIAL_SEEDS["friday"][0]
    assert td.pick_seed("friday", []) == first
    assert td.pick_seed("friday", [first]) == EDITORIAL_SEEDS["friday"][1]
    assert td.pick_seed("friday", EDITORIAL_SEEDS["friday"]) is None
