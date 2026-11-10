"""Source registry and reliability ranking for news and research.

Maintains trusted Indian and international publishers, official government feeds (PIB, DD News),
and academic/scientific portals with strict domain verification.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    SourceDefinition("PIB Hindi", "https://pib.gov.in/RssMain.aspx?ModId=6&LangId=2", "https://pib.gov.in", "national", 1.0, True, "hi"),
    SourceDefinition("PIB English", "https://pib.gov.in/RssMain.aspx?ModId=6&LangId=1", "https://pib.gov.in", "national", 1.0, True, "en"),
    SourceDefinition("DD News Hindi", "https://ddnews.gov.in/hi/feed/", "https://ddnews.gov.in", "national", 0.97, True, "hi"),
    SourceDefinition("BBC Hindi", "https://feeds.bbci.co.uk/hindi/rss.xml", "https://www.bbc.com/hindi", "international", 0.95, False, "hi"),
    SourceDefinition("BBC India", "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml", "https://www.bbc.com/news/world/asia/india", "international", 0.94, False, "en"),
    SourceDefinition("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss", "https://www.thehindu.com", "national", 0.93, False, "en"),
    SourceDefinition("The Hindu Science", "https://www.thehindu.com/sci-tech/science/feeder/default.rss", "https://www.thehindu.com", "science", 0.92, False, "en"),
    SourceDefinition("Indian Express India", "https://indianexpress.com/section/india/feed/", "https://indianexpress.com", "national", 0.92, False, "en"),
    SourceDefinition("Hindustan Times India", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "https://www.hindustantimes.com", "national", 0.9, False, "en"),
    SourceDefinition("Times of India India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "https://timesofindia.indiatimes.com", "national", 0.88, False, "en"),
    SourceDefinition("Amar Ujala India", "https://www.amarujala.com/rss/india-news.xml", "https://www.amarujala.com", "national", 0.87, False, "hi"),
    SourceDefinition("ABP Live India", "https://www.abplive.com/news/india/feed", "https://www.abplive.com", "national", 0.85, False, "hi"),
    SourceDefinition("Dainik Bhaskar", "https://www.bhaskar.com/rss-v1--category-1061.xml", "https://www.bhaskar.com", "national", 0.86, False, "hi"),
    SourceDefinition("TV9 Hindi", "https://www.tv9hindi.com/feed", "https://www.tv9hindi.com", "national", 0.82, False, "hi"),
    SourceDefinition("NDTV India News", "https://feeds.feedburner.com/ndtvnews-india-news", "https://www.ndtv.com", "national", 0.88, False, "en"),
    SourceDefinition("The Hindu Business", "https://www.thehindu.com/business/feeder/default.rss", "https://www.thehindu.com", "economy", 0.92, False, "en"),
    SourceDefinition("The Hindu Sport", "https://www.thehindu.com/sport/feeder/default.rss", "https://www.thehindu.com", "sports", 0.92, False, "en"),
    SourceDefinition("The Hindu International", "https://www.thehindu.com/news/international/feeder/default.rss", "https://www.thehindu.com", "international", 0.92, False, "en"),
    SourceDefinition("LiveMint", "https://www.livemint.com/rss/news", "https://www.livemint.com", "economy", 0.9, False, "en"),
    SourceDefinition("NDTV India", "https://feeds.feedburner.com/ndtvkhabar-latest", "https://ndtv.in", "national", 0.88, False, "hi"),
    SourceDefinition("Amar Ujala", "https://www.amarujala.com/rss/breaking-news.xml", "https://www.amarujala.com", "national", 0.86, False, "hi"),
    # Google News = the stories every big media house is running in the last hours (trending, multi-outlet)
    SourceDefinition("Google News Top Hindi", "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi", "https://news.google.com", "national", 0.9, False, "hi"),
    SourceDefinition("Google News India Hindi", "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi", "https://news.google.com", "national", 0.9, False, "hi"),
    SourceDefinition("Google News India", "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en", "https://news.google.com", "national", 0.88, False, "en"),
    SourceDefinition("Google News World Hindi", "https://news.google.com/rss/headlines/section/topic/WORLD?hl=hi&gl=IN&ceid=IN:hi", "https://news.google.com", "international", 0.9, False, "hi"),
    SourceDefinition("Google News World", "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en", "https://news.google.com", "international", 0.88, False, "en"),
    SourceDefinition("Google News Business", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=hi&gl=IN&ceid=IN:hi", "https://news.google.com", "economy", 0.86, False, "hi"),
    SourceDefinition("Google News Sports", "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=hi&gl=IN&ceid=IN:hi", "https://news.google.com", "sports", 0.86, False, "hi"),
    SourceDefinition("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "https://www.bbc.com/news/world", "international", 0.95, False, "en"),
    SourceDefinition("DW Hindi", "https://rss.dw.com/xml/rss-hi-all", "https://www.dw.com/hi", "international", 0.92, False, "hi"),
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
            "pib.gov.in", "ddnews.gov.in", "isro.gov.in", "bbc.com", "bbc.co.uk", "thehindu.com",
            "indianexpress.com", "reuters.com", "wikipedia.org", "nature.com", "ndtv.in",
            "ndtv.com", "amarujala.com", "hindustantimes.com", "timesofindia.indiatimes.com", "abplive.com",
            "bhaskar.com", "tv9hindi.com", "livemint.com"
        ]
        return any(domain in url.lower() for domain in trusted_domains)

    def get_reliability_weight(self, source_name: str) -> float:
        source = self._sources.get(source_name)
        return source.reliability_score if source else 0.7
