"""Visual sourcing: Pexels/Pixabay (if keys) -> Wikipedia lead image -> Wikimedia
Commons -> Openverse (all free/CC). Returns a local image path + attribution.
If nothing usable is found the scene composer draws a designed text card.
"""

from __future__ import annotations

import hashlib
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
                 use_wikimedia: bool = True, use_openverse: bool = True, timeout: int = 15):
        self.pexels_key = pexels_key
        self.pixabay_key = pixabay_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_wikimedia = use_wikimedia
        self.use_openverse = use_openverse
        self.timeout = timeout
        self._used: set = set()

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
            img.convert("RGB").save(dest, "JPEG", quality=92)
            self._used.add(url)
            return str(dest)
        except Exception as exc:
            logger.debug("download failed %s: %s", url, exc)
            return None

    def _pexels(self, query: str, dest: Path) -> Optional[MediaAsset]:
        try:
            r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": self.pexels_key},
                             params={"query": query, "per_page": 5, "orientation": "portrait"}, timeout=self.timeout)
            for p in r.json().get("photos", []):
                if self._download(p["src"]["large2x"], dest):
                    return MediaAsset(str(dest), "pexels", f"Photo: {p.get('photographer', '')} (Pexels)", p.get("url", ""))
        except Exception as exc:
            logger.warning("Pexels error: %s", exc)
        return None

    def _pixabay(self, query: str, dest: Path) -> Optional[MediaAsset]:
        try:
            r = requests.get("https://pixabay.com/api/", params={
                "key": self.pixabay_key, "q": query, "image_type": "photo", "orientation": "vertical",
                "per_page": 5, "safesearch": "true"}, timeout=self.timeout)
            for h in r.json().get("hits", []):
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

    # ------------------------------------------------------------------
    def find_image(self, keywords: str, dest_path: str, preferred_url: str = "") -> Optional[MediaAsset]:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        query = " ".join((keywords or "india").split()[:5])
        if preferred_url and self._download(preferred_url, dest):
            return MediaAsset(str(dest), "wikipedia", "Image: Wikipedia / Wikimedia Commons", preferred_url)
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

    # Back-compat ------------------------------------------------------------
    def get_scene_visual(self, scene_number: int, query: str, output_path: str, video_type: str = "news") -> str:
        from video.scene_composer import SceneComposer
        asset = self.find_image(query, output_path + ".src.jpg")
        comp = SceneComposer()
        return comp.compose_background(asset.path if asset else None, output_path, seed=scene_number)

    @staticmethod
    def cache_key(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
