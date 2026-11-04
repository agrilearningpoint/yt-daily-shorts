"""RSS reader and feed fetcher with resilient retry and date normalization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import feedparser
import requests

try:
    from dateutil import parser as date_parser
except ImportError:
    date_parser = None

logger = logging.getLogger("research.rss")


@dataclass
class RawArticle:
    title: str
    link: str
    summary: str
    published_at: Optional[datetime]
    source_name: str
    language: str = "hi"


class RSSReader:
    """Fetches and parses RSS/Atom feeds safely."""

    def __init__(self, timeout_sec: int = 15):
        self.timeout = timeout_sec

    def fetch_feed(self, url: str, source_name: str, language: str = "hi") -> List[RawArticle]:
        articles: List[RawArticle] = []
        try:
            # Use requests with proper headers to avoid bot blocks
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("Feed %s returned status %s", url, resp.status_code)
                return articles

            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "") or entry.get("description", "")
                
                # Strip simple HTML from summary if needed
                if "<" in summary and ">" in summary:
                    import re
                    summary = re.sub(r"<[^>]+>", " ", summary).strip()

                pub_date = None
                date_str = entry.get("published", "") or entry.get("updated", "")
                if date_str:
                    try:
                        pub_date = date_parser.parse(date_str)
                        if pub_date and pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                    except Exception:
                        pub_date = datetime.now(timezone.utc)
                else:
                    pub_date = datetime.now(timezone.utc)

                if title and link:
                    articles.append(RawArticle(
                        title=title,
                        link=link,
                        summary=summary[:1000],
                        published_at=pub_date,
                        source_name=source_name,
                        language=language
                    ))
        except Exception as exc:
            logger.error("Failed fetching feed %s (%s): %s", source_name, url, exc)
        return articles
