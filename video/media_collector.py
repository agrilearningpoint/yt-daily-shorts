"""Visual sourcing: Pexels/Pixabay (if keys) -> Wikipedia lead image -> Wikimedia
Commons -> Openverse (all free/CC). Returns a local image path + attribution.
If nothing usable is found the scene composer draws a designed text card.
"""

from __future__ import annotations

import hashlib
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
                 use_publisher_images: bool = False):
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

    def _relevant(self, query: str, text: str) -> bool:
        """The photo's own alt text/tags must mention the query's key words (stops random stock photos)."""
        want = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3 and w not in self._STOP]
        if not want:
            return True
        low = text.lower()
        hits = sum(1 for w in want if w in low or w.rstrip("s") in low)
        return hits >= max(1, -(-2 * len(want) // 3))

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
            if not src or src.lower().endswith((".svg", ".gif")):
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
        ent = [("entity", lambda: entity and self._wikipedia_exact(entity, dest))]
        stock = []
        if self.pexels_key:
            stock.append(("pexels", lambda: search and self._pexels(search, dest)))
        if self.pixabay_key:
            stock.append(("pixabay", lambda: search and self._pixabay(search, dest)))
        ai = [("ai", lambda: self._agnes(visual or search, dest, mode))]
        if hint == "ai":
            order = ai + ent + stock
        elif hint == "stock":
            order = stock + ai + ent
        else:  # entity first, then the AI illustration (more specific than generic stock)
            order = ent + (ai + stock if mode == "knowledge" else stock + ai)
        tail = []
        if self.use_wikimedia:
            tail.append(("commons", lambda: search and self._commons(" ".join(search.split()[:3]), dest)))
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
