"""Optional news APIs (free keys): GNews and NewsData.io. Used on top of RSS when keys are set."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List

import requests
from dateutil import parser as date_parser

from research.rss_reader import RawArticle

logger = logging.getLogger("research.api")


def _dt(s: str):
    try:
        d = date_parser.parse(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def gnews(key: str) -> List[RawArticle]:
    out: List[RawArticle] = []
    if not key:
        return out
    for cat, region, lang in (("nation", "national", "hi"), ("nation", "national", "en"),
                              ("world", "international", "hi"), ("world", "international", "en")):
        try:
            r = requests.get("https://gnews.io/api/v4/top-headlines", timeout=15, params={
                "category": cat, "lang": lang, "country": "in", "max": 10, "apikey": key})
            for a in (r.json().get("articles") or []) if r.ok else []:
                out.append(RawArticle(a.get("title", ""), a.get("url", ""), a.get("description", "") or "",
                                      _dt(a.get("publishedAt", "")), f"GNews {cat}", lang,
                                      a.get("image", "") or "", region, (a.get("source") or {}).get("name", "")))
            if not r.ok:
                logger.warning("GNews %s/%s HTTP %s", cat, lang, r.status_code)
        except Exception as exc:
            logger.warning("GNews failed: %s", exc)
    return out


def newsdata(key: str) -> List[RawArticle]:
    out: List[RawArticle] = []
    if not key:
        return out
    for params, region in (({"country": "in", "language": "hi"}, "national"),
                           ({"country": "in", "language": "en", "category": "top"}, "national"),
                           ({"category": "world", "language": "hi,en"}, "international")):
        try:
            r = requests.get("https://newsdata.io/api/1/latest", timeout=15, params={"apikey": key, **params})
            for a in (r.json().get("results") or []) if r.ok else []:
                if a.get("duplicate"):
                    continue
                out.append(RawArticle(a.get("title", "") or "", a.get("link", "") or "", a.get("description", "") or "",
                                      _dt(a.get("pubDate", "") + " UTC"), "NewsData", (a.get("language") or "hi")[:2],
                                      a.get("image_url", "") or "", region, a.get("source_name", "") or ""))
            if not r.ok:
                logger.warning("NewsData HTTP %s", r.status_code)
        except Exception as exc:
            logger.warning("NewsData failed: %s", exc)
    return out


def fetch_api_news() -> List[RawArticle]:
    arts = gnews(os.getenv("YT_GNEWS_API_KEY", "")) + newsdata(os.getenv("YT_NEWSDATA_API_KEY", ""))
    if arts:
        logger.info("News APIs added %d articles", len(arts))
    return arts
