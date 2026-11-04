"""Source registry and reliability ranking for news and research.

Maintains trusted Indian and international publishers, official government feeds (PIB, DD News),
and academic/scientific portals with strict domain verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SourceDefinition:
    name: str
    feed_url: str
    home_url: str
    category: str  # "national", "international", "business", "science", "sports"
    reliability_score: float  # 0.0 to 1.0 (PIB is 1.0)
    is_government: bool = False
    language: str = "hi"  # "hi" or "en"


DEFAULT_TRUSTED_SOURCES: List[SourceDefinition] = [
    SourceDefinition(
        name="PIB Hindi",
        feed_url="https://pib.gov.in/RssMain.aspx?ModId=6&LangId=2",
        home_url="https://pib.gov.in",
        category="national",
        reliability_score=1.0,
        is_government=True,
        language="hi",
    ),
    SourceDefinition(
        name="DD News Hindi",
        feed_url="https://ddnews.gov.in/hi/feed/",
        home_url="https://ddnews.gov.in",
        category="national",
        reliability_score=0.98,
        is_government=True,
        language="hi",
    ),
    SourceDefinition(
        name="BBC Hindi",
        feed_url="https://feeds.bbci.co.uk/hindi/rss.xml",
        home_url="https://www.bbc.com/hindi",
        category="international",
        reliability_score=0.95,
        is_government=False,
        language="hi",
    ),
    SourceDefinition(
        name="The Hindu National",
        feed_url="https://www.thehindu.com/news/national/feeder/default.rss",
        home_url="https://www.thehindu.com",
        category="national",
        reliability_score=0.92,
        is_government=False,
        language="en",
    ),
    SourceDefinition(
        name="ISRO Updates",
        feed_url="https://www.isro.gov.in/rss.xml",
        home_url="https://www.isro.gov.in",
        category="science",
        reliability_score=1.0,
        is_government=True,
        language="en",
    ),
    SourceDefinition(
        name="Reuters India",
        feed_url="https://www.reutersagency.com/feed/?taxonomy=markets&post_type=best",
        home_url="https://www.reuters.com",
        category="business",
        reliability_score=0.94,
        is_government=False,
        language="en",
    ),
]


class SourceRegistry:
    """Manages active verified source providers."""

    def __init__(self, sources: Optional[List[SourceDefinition]] = None):
        self._sources: Dict[str, SourceDefinition] = {
            s.name: s for s in (sources or DEFAULT_TRUSTED_SOURCES)
        }

    def get_all_sources(self) -> List[SourceDefinition]:
        return list(self._sources.values())

    def get_sources_by_category(self, category: str) -> List[SourceDefinition]:
        return [s for s in self._sources.values() if s.category == category or category == "all"]

    def is_source_trusted(self, url: str) -> bool:
        """Verify if a URL belongs to a trusted domain."""
        trusted_domains = [
            "pib.gov.in", "ddnews.gov.in", "isro.gov.in", "bbc.com", "thehindu.com",
            "indianexpress.com", "reuters.com", "wikipedia.org", "nature.com"
        ]
        return any(domain in url.lower() for domain in trusted_domains)

    def get_reliability_weight(self, source_name: str) -> float:
        source = self._sources.get(source_name)
        return source.reliability_score if source else 0.7
