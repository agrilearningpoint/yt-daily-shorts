"""Fetch the body text of a news article so facts are checked against the real story, not just the RSS line."""
from __future__ import annotations

import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable

import requests

logger = logging.getLogger("research.article")
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
_SKIP_HOSTS = ("news.google.", "bing.com")


def article_text(url: str, limit: int = 1400, timeout: int = 12) -> str:
    if not url or any(h in url for h in _SKIP_HOSTS):
        return ""
    try:
        r = requests.get(url, headers=_UA, timeout=timeout)
        if not r.ok:
            return ""
        page = re.sub(r"(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", r.text)
        paras = [html.unescape(re.sub(r"<[^>]+>", " ", p)) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", page)]
        paras = [re.sub(r"\s+", " ", p).strip() for p in paras]
        paras = [p for p in paras if len(p) > 60 and "cookie" not in p.lower() and "subscribe" not in p.lower()]
        return " ".join(paras)[:limit]
    except Exception as exc:
        logger.debug("article text failed %s: %s", url, exc)
        return ""


def fetch_many(urls: Iterable[str], workers: int = 8) -> Dict[str, str]:
    urls = [u for u in dict.fromkeys(urls) if u]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        texts = list(pool.map(article_text, urls))
    out = {u: t for u, t in zip(urls, texts) if t}
    logger.info("Evidence: article text for %d/%d stories", len(out), len(urls))
    return out
