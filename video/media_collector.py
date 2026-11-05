"""Visual sourcing: Pexels/Pixabay (if keys) -> Wikipedia lead image -> Wikimedia
Commons -> Openverse (all free/CC). Returns a local image path + attribution.
If nothing usable is found the scene composer draws a designed text card.
"""

from __future__ import annotations

import hashlib
import os
import re
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image

logger = logging.getLogger("video.media")
_UA = {"User-Agent": "YTDailyShortsBot/2.0 (https://github.com/agrilearningpoint/yt-daily-shorts)"}


@dataclass
class MediaAsset:
    path: str
    source: str
    credit: str = ""
    page_url: str = ""


class MediaCollector:
    def __init__(self, pexels_key: str = "", pixabay_key: str = "", cache_dir: str = "data/media_cache",
                 use_wikimedia: bool = True, use_openverse: bool = True, timeout: int = 15,
                 agnes_key: str = "", agnes_model: str = "agnes-image-2.5-flash",
                 use_publisher_images: bool = False, use_news_photos: bool = True,
                 cf_token: str = "", cf_account: str = "", vision=None):
        self.pexels_key = pexels_key
        self.pixabay_key = pixabay_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_wikimedia = use_wikimedia
        self.use_openverse = use_openverse
        self.timeout = timeout
        self._used: set = set()
        self.agnes_key = agnes_key
        self.agnes_model = agnes_model
        self.use_publisher_images = use_publisher_images
        self.use_news_photos = use_news_photos
        self.cf_token, self.cf_account = cf_token, cf_account
        self.vision = vision  # callable(image_path, description) -> bool, or None

    # ------------------------------------------------------------------
    def _download(self, url: str, dest: Path) -> Optional[str]:
        if not url or url in self._used:
            return None
        try:
            r = requests.get(url, headers=_UA, timeout=self.timeout)
            if r.status_code != 200:
                return None
            img = Image.open(io.BytesIO(r.content))
            img.load()
            if min(img.size) < 400:
                return None
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(bg, img)
            img = img.convert("RGB")
            if self._looks_blank(img):
                logger.info("rejecting blank/logo-like image %s", url)
                return None
            img.save(dest, "JPEG", quality=92)
            self._used.add(url)
            return str(dest)
        except Exception as exc:
            logger.debug("download failed %s: %s", url, exc)
            return None

    @staticmethod
    def _looks_blank(img: "Image.Image") -> bool:
        """Flat images (transparent logos, white documents, solid fills) look empty on screen."""
        g = img.convert("L").resize((64, 64))
        px = list(g.getdata())
        mean = sum(px) / len(px)
        std = (sum((v - mean) ** 2 for v in px) / len(px)) ** 0.5
        flat = sum(1 for v in px if v > 235 or v < 20) / len(px)
        return std < 18 or flat > 0.7

    _STOP = {"with", "from", "the", "and", "for", "india", "indian", "photo", "image", "people", "during"}

    def _relevant(self, query: str, text: str, share: float = 2 / 3) -> bool:
        """The photo's own alt text/tags must mention the query's key words (stops random stock photos)."""
        want = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3 and w not in self._STOP]
        if not want:
            return True
        low = text.lower()
        hits = sum(1 for w in want if w in low or w.rstrip("s") in low)
        import math
        return hits >= max(1, math.ceil(share * len(want)))

    def _pexels(self, query: str, dest: Path) -> Optional[MediaAsset]:
        try:
            r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": self.pexels_key},
                             params={"query": query, "per_page": 10, "orientation": "portrait"}, timeout=self.timeout)
            for p in r.json().get("photos", []):
                if not self._relevant(query, p.get("alt", "") + " " + p.get("url", "").replace("-", " ")):
                    continue
                if self._download(p["src"]["large2x"], dest):
                    return MediaAsset(str(dest), "pexels", f"Photo: {p.get('photographer', '')} (Pexels)", p.get("url", ""))
        except Exception as exc:
            logger.warning("Pexels error: %s", exc)
        return None

    def _unsplash(self, query: str, dest: Path) -> Optional[MediaAsset]:
        key = os.getenv("YT_UNSPLASH_ACCESS_KEY", "")
        if not key or not query:
            return None
        try:
            h = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}
            r = requests.get("https://api.unsplash.com/search/photos", headers=h, timeout=self.timeout,
                             params={"query": query, "per_page": 10, "orientation": "portrait", "content_filter": "high"})
            for p in r.json().get("results", []) if r.ok else []:
                text = " ".join(filter(None, [p.get("alt_description"), p.get("description"),
                                              (p.get("links") or {}).get("html", "").replace("-", " ")]))
                if not self._relevant(query, text):
                    continue
                if self._download(p["urls"]["regular"], dest):
                    try:  # API guideline: register the download
                        requests.get(p["links"]["download_location"], headers=h, timeout=8)
                    except Exception:
                        pass
                    return MediaAsset(str(dest), "unsplash", f"Photo: {p['user'].get('name', '')} (Unsplash)",
                                      p["links"].get("html", ""))
        except Exception as exc:
            logger.warning("Unsplash error: %s", exc)
        return None

    def _pixabay(self, query: str, dest: Path) -> Optional[MediaAsset]:
        try:
            r = requests.get("https://pixabay.com/api/", params={
                "key": self.pixabay_key, "q": query, "image_type": "photo", "orientation": "vertical",
                "per_page": 10, "safesearch": "true"}, timeout=self.timeout)
            for h in r.json().get("hits", []):
                if not self._relevant(query, h.get("tags", "")):
                    continue
                if self._download(h["largeImageURL"], dest):
                    return MediaAsset(str(dest), "pixabay", f"Image: {h.get('user', '')} (Pixabay)", h.get("pageURL", ""))
        except Exception as exc:
            logger.warning("Pixabay error: %s", exc)
        return None

    def _commons(self, query: str, dest: Path) -> Optional[MediaAsset]:
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", headers=_UA, timeout=self.timeout, params={
                "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 8, "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600})
            pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
            for p in pages:
                info = (p.get("imageinfo") or [{}])[0]
                if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                    continue
                desc = str(info.get("extmetadata", {}).get("ImageDescription", {}).get("value", ""))
                if not self._relevant(query, p.get("title", "") + " " + re.sub(r"<[^>]+>", " ", desc)):
                    continue
                if self._download(info.get("thumburl") or info.get("url"), dest):
                    meta = info.get("extmetadata", {})
                    lic = meta.get("LicenseShortName", {}).get("value", "CC")
                    return MediaAsset(str(dest), "wikimedia", f"{p.get('title', '').replace('File:', '')} ({lic}, Wikimedia Commons)",
                                      info.get("descriptionurl", ""))
        except Exception as exc:
            logger.warning("Commons error: %s", exc)
        return None

    def _openverse(self, query: str, dest: Path) -> Optional[MediaAsset]:
        try:
            r = requests.get("https://api.openverse.org/v1/images/", headers=_UA, timeout=self.timeout, params={
                "q": query, "license_type": "commercial", "page_size": 8, "mature": "false"})
            for res in r.json().get("results", []):
                if (res.get("width") or 0) < 600:
                    continue
                if self._download(res.get("url"), dest):
                    credit = f"\"{res.get('title', '')}\" by {res.get('creator', 'unknown')} ({str(res.get('license', '')).upper()} {res.get('license_version', '')}, Openverse)"
                    return MediaAsset(str(dest), "openverse", credit, res.get("foreign_landing_url", ""))
        except Exception as exc:
            logger.warning("Openverse error: %s", exc)
        return None

    def _wikipedia_entity(self, entity: str, dest: Path) -> Optional[MediaAsset]:
        """Lead image of the entity's English Wikipedia article (free-licensed, very relevant)."""
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php", headers=_UA, timeout=self.timeout, params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": entity, "gsrlimit": 1,
                "prop": "pageimages|info", "piprop": "original", "inprop": "url", "redirects": 1})
            for page in r.json().get("query", {}).get("pages", {}).values():
                src = (page.get("original") or {}).get("source", "")
                if src.lower().endswith((".svg", ".gif")):
                    continue
                if src and self._download(src, dest):
                    return MediaAsset(str(dest), "wikipedia", f"{page.get('title', entity)} — Wikipedia/Wikimedia Commons",
                                      page.get("fullurl", ""))
        except Exception as exc:
            logger.debug("Wikipedia entity image failed for %s: %s", entity, exc)
        return None

    # Government sources whose photos are free to reuse with credit (GODL-India / public domain).
    # Private publishers' photos (agency/Getty/PTI) are NOT used: they cause copyright claims.
    SAFE_ARTICLE_DOMAINS = ("pib.gov.in", "ddnews.gov.in", "isro.gov.in", "mygov.in", "pmindia.gov.in",
                            "mea.gov.in", "india.gov.in", "nasa.gov")

    def article_image(self, article_url: str, dest: Path) -> Optional[MediaAsset]:
        """The story's own photo (og:image), only from copyright-safe government sources."""
        try:
            host = re.sub(r"^https?://", "", article_url or "").split("/")[0].lower()
            if not any(host == d or host.endswith("." + d) for d in self.SAFE_ARTICLE_DOMAINS):
                return None
            r = requests.get(article_url, headers=_UA, timeout=self.timeout)
            m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text, re.I)
                 or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', r.text, re.I))
            url = m.group(1) if m else ""
            if not url:  # PIB pages: first large content image
                m2 = re.search(r'<img[^>]+src=["\']([^"\']+(?:\.jpe?g|\.png))["\']', r.text, re.I)
                url = m2.group(1) if m2 else ""
            if url and not url.startswith("http"):
                url = "https://" + host + "/" + url.lstrip("/")
            if url and self._download(url, dest):
                return MediaAsset(str(dest), "article", f"Image: {host}", article_url)
        except Exception as exc:
            logger.debug("article image failed %s: %s", article_url, exc)
        return None

    # ------------------------------------------------------------------
    def find_image(self, keywords: str, dest_path: str, preferred_url: str = "",
                   entity: str = "", article_url: str = "") -> Optional[MediaAsset]:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        query = " ".join((keywords or "india").split()[:5])
        if preferred_url and self._download(preferred_url, dest):
            return MediaAsset(str(dest), "wikipedia", "Image: Wikipedia / Wikimedia Commons", preferred_url)
        if article_url:
            asset = self.article_image(article_url, dest)
            if asset:
                logger.info("Scene image from the story's own page %s", article_url)
                return asset
        if entity and self.use_wikimedia:
            asset = self._wikipedia_entity(entity, dest)
            if asset:
                logger.info("Scene image via wikipedia entity '%s'", entity)
                return asset
        providers = []
        if self.pexels_key:
            providers.append(self._pexels)
        if self.pixabay_key:
            providers.append(self._pixabay)
        if self.use_wikimedia:
            providers.append(self._commons)
        if self.use_openverse:
            providers.append(self._openverse)
        for provider in providers:
            asset = provider(query, dest)
            if asset:
                logger.info("Scene image via %s for '%s'", asset.source, query)
                return asset
        # retry with a shorter query
        short = " ".join(query.split()[:2])
        if short != query:
            for provider in providers:
                asset = provider(short, dest)
                if asset:
                    return asset
        logger.info("No image found for '%s' — designed card will be used", query)
        return None

    # ------------------------------------------------------------------
    def _wikipedia_exact(self, entity: str, dest: Path) -> Optional[MediaAsset]:
        """Lead image of the EXACT Wikipedia article (no fuzzy search drift -> no off-topic photos)."""
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php", headers=_UA, timeout=self.timeout, params={
                "action": "query", "format": "json", "titles": entity, "redirects": 1,
                "prop": "pageimages|info", "piprop": "original", "inprop": "url"})
            pages = list(r.json().get("query", {}).get("pages", {}).values())
            if not pages or "missing" in pages[0]:
                # search, but only accept a title that really names the same thing
                r = requests.get("https://en.wikipedia.org/w/api.php", headers=_UA, timeout=self.timeout, params={
                    "action": "query", "format": "json", "generator": "search", "gsrsearch": entity,
                    "gsrlimit": 1, "prop": "pageimages|info", "piprop": "original", "inprop": "url"})
                pages = list(r.json().get("query", {}).get("pages", {}).values())
                want = {w for w in re.findall(r"[a-z0-9]+", entity.lower()) if len(w) > 2}
                got = set(re.findall(r"[a-z0-9]+", (pages[0].get("title", "") if pages else "").lower()))
                if not pages or not want or len(want & got) / len(want) < 0.6:
                    return None
            page = pages[0]
            src = (page.get("original") or {}).get("source", "")
            if not src or src.lower().endswith((".svg", ".gif")) or re.search(
                    r"logo|emblem|seal_of|coat_of_arms|insignia|wordmark", src, re.I):
                return None
            if self._download(src, dest):
                return MediaAsset(str(dest), "wikipedia", f"{page.get('title', entity)} — Wikipedia/Wikimedia Commons",
                                  page.get("fullurl", ""))
        except Exception as exc:
            logger.debug("Wikipedia exact image failed for %s: %s", entity, exc)
        return None

    def _agnes(self, visual: str, dest: Path, mode: str = "news") -> Optional[MediaAsset]:
        """AI picture written from the scene description (Agnes AI, OpenAI-compatible images API)."""
        if not self.agnes_key or not visual or getattr(self, "_agnes_dead", False):
            return None
        import threading, time
        if not hasattr(MediaCollector, "_agnes_gate"):
            MediaCollector._agnes_gate = threading.Semaphore(2)  # free tier rate-limits bursts
        style = ("photorealistic editorial news photograph, natural light, realistic Indian setting"
                 if mode == "news" else
                 "cinematic, historically accurate, richly detailed, documentary illustration, dramatic light")
        prompt = (f"{visual}. {style}. Vertical 9:16 composition, subject centred. No text, no letters, "
                  f"no captions, no watermark, no logos, no recognisable real politician faces.")
        for attempt in range(3):
            try:
                with MediaCollector._agnes_gate:
                    r = requests.post("https://apihub.agnes-ai.com/v1/images/generations", timeout=120,
                                      headers={"Authorization": f"Bearer {self.agnes_key}", "Content-Type": "application/json"},
                                      json={"model": self.agnes_model, "prompt": prompt, "size": "1K", "ratio": "9:16"})
                if r.status_code == 429:
                    if attempt == 2:
                        self._agnes_dead = True  # stop hammering for the rest of this run
                        logger.warning("Agnes AI rate limit reached; no more AI images this run")
                        return None
                    time.sleep(20 * (attempt + 1))
                    continue
                url = ((r.json().get("data") or [{}])[0] or {}).get("url", "")
                if url and self._download(url, dest):
                    return MediaAsset(str(dest), "ai", "AI-generated illustration (Agnes AI)", "")
                logger.warning("Agnes AI image failed: HTTP %s %s", r.status_code, r.text[:160])
                return None
            except Exception as exc:
                logger.warning("Agnes AI error: %s", exc)
                return None
        return None

    _BAD_IMG = re.compile(r"logo|default|placeholder|favicon|sprite|icon|avatar|banner-ad|1x1", re.I)

    def _news_photo(self, query: str, dest: Path) -> Optional[MediaAsset]:
        """Photo of the SAME event: latest news articles about it (Bing News RSS) -> each article's og:image."""
        if not self.use_news_photos or not query:
            return None
        import urllib.parse, html
        try:
            r = requests.get("https://www.bing.com/news/search", headers=_UA, timeout=self.timeout,
                             params={"q": query[:120], "format": "rss", "setlang": "en-IN", "cc": "IN"})
            items = re.findall(r"<item>(.*?)</item>", r.text, re.S)[:8]
        except Exception as exc:
            logger.debug("bing news failed: %s", exc)
            return None
        for it in items:
            title = html.unescape((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1])
            link = html.unescape((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1])
            real = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [link])[0]
            if not real.startswith("http") or not self._news_match(query, title):
                continue
            try:
                page = requests.get(real, headers=_UA, timeout=self.timeout).text
            except Exception:
                continue
            m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page, re.I)
                 or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', page, re.I)
                 or re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', page, re.I))
            img = html.unescape(m.group(1)) if m else ""
            if not img or self._BAD_IMG.search(img.split("?")[0]):
                continue
            if self._download(img, dest):
                host = re.sub(r"^https?://(www\.)?", "", real).split("/")[0]
                return MediaAsset(str(dest), "news", f"Photo: {host}", real)
        return None

    def _news_match(self, query: str, title: str) -> bool:
        """Another outlet's headline about the same event: enough shared names/words (works for Hindi too)."""
        stop = {"के", "की", "का", "में", "से", "को", "और", "पर", "ने", "है", "हैं", "लिए", "एक", "यह", "बड़ी"}
        q = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2 and w not in stop and w not in self._STOP]
        if not q:
            return True
        t = title.lower()
        hits = sum(1 for w in q if w in t)
        return hits >= max(2, round(0.4 * len(q))) if len(q) >= 3 else hits >= 1

    def _cloudflare(self, visual: str, dest: Path, mode: str = "news") -> Optional[MediaAsset]:
        """Free AI picture from Cloudflare Workers AI (FLUX.1 schnell, ~10k free neurons/day)."""
        if not (self.cf_token and self.cf_account and visual):
            return None
        import base64
        style = ("photorealistic editorial news photograph, natural light, realistic Indian setting"
                 if mode == "news" else "cinematic, historically accurate, documentary illustration")
        prompt = f"{visual}. {style}. Vertical composition, subject centred. No text, no letters, no watermark, no logos."
        try:
            r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account}/ai/run/"
                              "@cf/black-forest-labs/flux-1-schnell", timeout=90,
                              headers={"Authorization": f"Bearer {self.cf_token}"},
                              json={"prompt": prompt[:2000], "steps": 8})
            b64 = (r.json().get("result") or {}).get("image", "") if r.ok else ""
            if not b64:
                logger.warning("Cloudflare AI image failed: HTTP %s %s", r.status_code, r.text[:160])
                return None
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            img.save(dest, "JPEG", quality=92)
            return MediaAsset(str(dest), "ai", "AI-generated illustration (Cloudflare Workers AI, FLUX)", "")
        except Exception as exc:
            logger.warning("Cloudflare AI error: %s", exc)
            return None

    def _checked(self, fn, description: str):
        """Wrap a stock/commons step: Gemini vision must agree the photo shows the described scene."""
        def run():
            a = fn()
            if a and self.vision:
                try:
                    if not self.vision(a.path, description):
                        logger.info("vision check rejected %s for '%s'", a.source, description[:60])
                        return None
                except Exception as exc:
                    logger.debug("vision check error: %s", exc)
            return a
        return run

    def find_visual(self, spec: dict, dest_path: str, mode: str = "news") -> Optional[MediaAsset]:
        """One picture for one small beat. spec: visual, entity, search, source, article, preferred, publisher."""
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        entity, search, visual = spec.get("entity", ""), spec.get("search", ""), spec.get("visual", "")
        hint = (spec.get("source") or "").lower()
        steps = []
        if spec.get("preferred"):
            steps.append(("preferred", lambda: self._download(spec["preferred"], dest) and
                          MediaAsset(str(dest), "wikipedia", "Image: Wikipedia / Wikimedia Commons", spec["preferred"])))
        if spec.get("article"):
            steps.append(("article", lambda: self.article_image(spec["article"], dest)))
        if spec.get("publisher") and self.use_publisher_images:
            steps.append(("publisher", lambda: self._download(spec["publisher"], dest) and
                          MediaAsset(str(dest), "publisher", f"Image: {spec.get('publisher_name', 'news source')}",
                                     spec.get("article_page", ""))))
        desc = visual or search or entity
        if mode == "news" and spec.get("news_query"):
            steps.append(("news", lambda: self._news_photo(spec["news_query"], dest)))
        ent = [("entity", lambda: entity and self._wikipedia_exact(entity, dest))]
        stock = []
        if self.pexels_key:
            stock.append(("pexels", self._checked(lambda: search and self._pexels(search, dest), desc)))
        if os.getenv("YT_UNSPLASH_ACCESS_KEY"):
            stock.append(("unsplash", self._checked(lambda: search and self._unsplash(search, dest), desc)))
        if self.pixabay_key:
            stock.append(("pixabay", self._checked(lambda: search and self._pixabay(search, dest), desc)))
        ai = [("ai", lambda: self._agnes(visual or search, dest, mode)),
              ("ai-cf", lambda: self._cloudflare(visual or search, dest, mode))]
        if hint == "stock":
            order = ent + stock + ai
        else:  # real photo of the person/thing first, else an AI picture made for this exact line
            order = ent + ai + stock
        tail = []
        if self.use_wikimedia:
            tail.append(("commons", self._checked(
                lambda: search and self._commons(" ".join(search.split()[:3]), dest), desc)))
        for name, fn in steps + order + tail:
            try:
                asset = fn()
            except Exception as exc:
                logger.debug("visual step %s failed: %s", name, exc)
                asset = None
            if asset:
                logger.info("Beat visual via %s (%s)", name, (visual or search or entity)[:60])
                return asset
        return None

    def find_visuals(self, specs: List[dict], mode: str = "news", workers: int = 6) -> List[Optional[MediaAsset]]:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(self.find_visual, s, s["dest"], mode) for s in specs]
            return [f.result() for f in futs]

    def find_many(self, requests_: List[dict], workers: int = 6) -> List[Optional[MediaAsset]]:
        """Parallel find_image for many beats. Each dict: keywords, dest, preferred, entity."""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(self.find_image, r.get("keywords", ""), r["dest"], r.get("preferred", ""),
                                r.get("entity", ""), r.get("article", "")) for r in requests_]
            return [f.result() for f in futs]

    # Back-compat ------------------------------------------------------------
    def get_scene_visual(self, scene_number: int, query: str, output_path: str, video_type: str = "news") -> str:
        from video.scene_composer import SceneComposer
        asset = self.find_image(query, output_path + ".src.jpg")
        comp = SceneComposer()
        return comp.compose_background(asset.path if asset else None, output_path, seed=scene_number)

    @staticmethod
    def cache_key(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
