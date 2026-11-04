"""Research, news gathering, source verification, and trend discovery package."""

from research.news_collector import NewsCollector, ProcessedNewsItem
from research.rss_reader import RSSReader, RawArticle
from research.source_registry import SourceRegistry, SourceDefinition
from research.trend_discovery import TrendDiscovery, TopicDetails
from research.deduplication import deduplicate_articles

__all__ = [
    "NewsCollector",
    "ProcessedNewsItem",
    "RSSReader",
    "RawArticle",
    "SourceRegistry",
    "SourceDefinition",
    "TrendDiscovery",
    "TopicDetails",
    "deduplicate_articles",
]
