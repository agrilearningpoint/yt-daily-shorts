"""News collection, filtering, ranking and packaging for the morning Short."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from research.deduplication import deduplicate_articles, jaccard_similarity
from research.rss_reader import RSSReader, RawArticle
from research.source_registry import SourceRegistry

logger = logging.getLogger("research.collector")

# Stories that make poor 60-second explainers / are risky for a news channel.
_SKIP_KEYWORDS = (
    "live updates", "live:", "horoscope", "rashifal", "राशिफल", "photos:", "in pics",
    "quiz", "crossword", "obituary", "rape", "बलात्कार", "murder", "हत्या",
)


@dataclass
class ProcessedNewsItem:
    title: str
    summary: str
    source_url: str
    source_name: str
    published_at: str
    reliability_score: float
    importance_score: float


def _fallback_items(n: int = 3) -> List[ProcessedNewsItem]:
    now = datetime.now(timezone.utc).isoformat()
    base = [
        ProcessedNewsItem("भारत के डिजिटल इंफ्रास्ट्रक्चर और UPI का वैश्विक विस्तार",
                          "UPI को कई नए देशों में स्वीकृति मिली है।", "https://pib.gov.in", "PIB Hindi", now, 1.0, 0.95),
        ProcessedNewsItem("इसरो के नए उपग्रह मिशन की तैयारी",
                          "इसरो ने आगामी उपग्रह प्रक्षेपण के परीक्षण पूरे किए।", "https://www.isro.gov.in", "ISRO", now, 1.0, 0.92),
        ProcessedNewsItem("भारतीय निर्यात में वृद्धि",
                          "वाणिज्य मंत्रालय के आंकड़ों में निर्यात में तेजी।", "https://pib.gov.in", "PIB Hindi", now, 1.0, 0.88),
    ]
    out = list(base)
    i = 0
    while len(out) < n:
        b = base[i % len(base)]
        out.append(ProcessedNewsItem(f"{b.title} ({len(out) + 1})", b.summary, b.source_url + f"#s{len(out)}",
                                     b.source_name, now, b.reliability_score, b.importance_score - 0.01 * len(out)))
        i += 1
    return out


class NewsCollector:
    """Collects and curates daily news for the morning short."""

    def __init__(self, source_registry: Optional[SourceRegistry] = None, max_hours_old: int = 24,
                 allow_offline_fallback: bool = True):
        self.registry = source_registry or SourceRegistry()
        self.reader = RSSReader()
        self.max_hours_old = max_hours_old
        self.allow_offline_fallback = allow_offline_fallback

    def _fetch_all(self) -> List[RawArticle]:
        sources = self.registry.get_all_sources()
        articles: List[RawArticle] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for fetched in pool.map(lambda s: self.reader.fetch_feed(s.feed_url, s.name, s.language), sources):
                articles.extend(fetched)
        logger.info("Fetched %d raw articles from %d sources", len(articles), len(sources))
        return articles

    def collect_and_rank_news(self, target_count: int = 3,
                              exclude: Optional[Iterable[dict]] = None) -> List[ProcessedNewsItem]:
        all_articles = self._fetch_all()
        exclude = list(exclude or [])
        used_urls = {e.get("url") for e in exclude}
        used_titles = [e.get("title", "") for e in exclude]

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.max_hours_old)
        recent = [a for a in all_articles if a.published_at and a.published_at >= cutoff]
        if not recent and all_articles:
            logger.warning("No articles in past %dh; using latest available", self.max_hours_old)
            recent = all_articles

        filtered = []
        for a in recent:
            low = (a.title or "").lower()
            if any(k in low for k in _SKIP_KEYWORDS):
                continue
            if a.link in used_urls:
                continue
            if any(jaccard_similarity(a.title, t) >= 0.5 for t in used_titles if t):
                continue
            filtered.append(a)

        unique = deduplicate_articles(filtered)

        processed: List[ProcessedNewsItem] = []
        for a in unique:
            reliability = self.registry.get_reliability_weight(a.source_name)
            hours_old = (now - (a.published_at or now)).total_seconds() / 3600.0
            recency = max(0.4, 1.0 - hours_old / 36.0)
            substance = min(1.0, (len(a.title) + len(a.summary)) / 220.0)
            # Stories covered by several outlets are more important.
            coverage = sum(1 for b in recent if b.source_name != a.source_name
                           and jaccard_similarity(a.title, b.title) >= 0.25)
            coverage_score = min(1.0, coverage / 3.0)
            importance = reliability * 0.35 + recency * 0.25 + substance * 0.15 + coverage_score * 0.25
            processed.append(ProcessedNewsItem(
                title=a.title, summary=a.summary, source_url=a.link, source_name=a.source_name,
                published_at=a.published_at.isoformat() if a.published_at else "",
                reliability_score=reliability, importance_score=round(importance, 3)))

        processed.sort(key=lambda x: x.importance_score, reverse=True)

        if not processed:
            if not self.allow_offline_fallback:
                raise RuntimeError("No news could be collected from any feed (strict mode).")
            logger.warning("No feeds reachable — using OFFLINE sample news (dry-run only)")
            processed = _fallback_items(target_count)

        return processed[:target_count]
