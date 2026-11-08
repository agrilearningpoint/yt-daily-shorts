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
    image_url: str = ""
    region: str = "national"     # national (India) | international (world)
    coverage: int = 0            # other outlets reporting the same story (independent corroboration)


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
        cat = {s.name: s.category for s in sources}
        for a in articles:
            if not a.region:
                a.region = "international" if cat.get(a.source_name) == "international" else "national"
        try:
            from research.api_news import fetch_api_news
            articles.extend(fetch_api_news())
        except Exception as exc:
            logger.warning("news APIs skipped: %s", exc)
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
        # Freshness gate: only stories with a VERIFIED publish time inside the window.
        # Undated, old or future-dated items are dropped; never fall back to old news.
        recent = [a for a in all_articles
                  if a.published_at and cutoff <= a.published_at <= now + timedelta(hours=1)]
        undated = sum(1 for a in all_articles if not a.published_at)
        logger.info("Freshness: %d/%d articles within %dh (%d undated rejected, %d stale/future rejected)",
                    len(recent), len(all_articles), self.max_hours_old, undated,
                    len(all_articles) - len(recent) - undated)

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
            hours_old = (now - a.published_at).total_seconds() / 3600.0
            recency = max(0.4, 1.0 - hours_old / 36.0)
            substance = min(1.0, (len(a.title) + len(a.summary)) / 220.0)
            # Stories covered by several outlets are more important.
            coverage = sum(1 for b in recent if (b.publisher or b.source_name) != (a.publisher or a.source_name)
                           and jaccard_similarity(a.title, b.title) >= 0.25)
            coverage_score = min(1.0, coverage / 3.0)
            importance = reliability * 0.35 + recency * 0.25 + substance * 0.15 + coverage_score * 0.25
            processed.append(ProcessedNewsItem(
                title=a.title, summary=a.summary, source_url=a.link,
                source_name=a.publisher or a.source_name, region=a.region or "national",
                published_at=a.published_at.isoformat() if a.published_at else "",
                reliability_score=reliability, importance_score=round(importance, 3), image_url=a.image_url,
                coverage=coverage))

        processed.sort(key=lambda x: x.importance_score, reverse=True)

        if not processed:
            if not self.allow_offline_fallback:
                raise RuntimeError("No news could be collected from any feed (strict mode).")
            logger.warning("No feeds reachable — using OFFLINE sample news (dry-run only)")
            processed = _fallback_items(target_count)

        intl_n = max(8, target_count // 5)
        intl = [p for p in processed if p.region == "international"][:intl_n]
        nat = [p for p in processed if p.region != "international"][:max(target_count - len(intl), 0)]
        out = nat + intl
        out.sort(key=lambda x: x.importance_score, reverse=True)
        return out
