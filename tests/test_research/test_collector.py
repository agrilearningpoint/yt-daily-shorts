"""Unit tests for research, news collection, and source validation."""

from __future__ import annotations

from research.news_collector import NewsCollector
from research.source_registry import SourceRegistry
from research.trend_discovery import TrendDiscovery


def test_source_registry():
    reg = SourceRegistry()
    sources = reg.get_all_sources()
    assert len(sources) >= 4
    assert reg.is_source_trusted("https://pib.gov.in/PressRelease.aspx")
    assert reg.is_source_trusted("https://ddnews.gov.in")
    assert not reg.is_source_trusted("https://random-unverified-blog.xyz")


def test_news_collector_fallback():
    collector = NewsCollector()
    ranked = collector.collect_and_rank_news(target_count=3)
    assert len(ranked) >= 1
    assert ranked[0].source_url != ""
    assert ranked[0].reliability_score > 0.0


def test_trend_discovery():
    discovery = TrendDiscovery()
    topic = discovery.discover_calendar_topic("monday")
    assert topic.title != ""
    assert topic.source_url != ""
