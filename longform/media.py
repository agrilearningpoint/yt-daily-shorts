"""Visual sourcing for 16:9 documentary chapters.

Priority is deliberately different from the Shorts pipeline:

1. **Wikimedia Commons** — a documentary about a civilisation needs *specific*
   monuments, manuscripts and paintings, which is exactly what Commons has and
   stock libraries do not. Free, no key, no quota.
2. **Pexels / Pixabay** — for generic motion-friendly frames (crowds, ghats, fire,
   festivals) where a stock photo looks better than an archival scan.
3. **AI (Agnes / HF FLUX)** — only when nothing real exists for a query, and
   capped per chapter so a broken key can never stall the film.

Every image is remembered in `media.json` per chapter, so a re-render reuses the
same visuals instead of re-fetching (Commons is polite but not free to hammer).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import List, Optional

import requests

logger = logging.getLogger("longform.media")

UA = {"User-Agent": "yt-daily-shorts-longform/1.0 (documentary research; contact: repo owner)"}
MIN_W, MIN_H = 1000, 560          # anything smaller looks soft at 1080p
AI_CAP_PER_CHAPTER = 3


class VisualSourcer:
    def __init__(self, out_root: Path, pexels_key: str = "", pixabay_key: str = "",
                 hf_token: str = "", agnes_key: str = "", timeout: int = 45) -> None:
        self.out_root = out_root
        self.pexels_key = pexels_key
        self.pixabay_key = pixabay_key
        self.hf_token = hf_token
        self.agnes_key = agnes_key
        self.timeout = timeout
        self._seen: set = set()          # sha1 of bytes, across the whole film
        self._kept: set = set()          # paths already accepted (never delete these)
        self._ai_used = 0

    # ------------------------------------------------------------------ public
    def fetch_chapter(self, idx: int, queries: List[str], want: int) -> List[str]:
        """Fetch up to *want* landscape images for one chapter (cached in media.json)."""
        ch_dir = self.out_root / f"ch{idx + 1:02d}"
        ch_dir.mkdir(parents=True, exist_ok=True)
        manifest = ch_dir / "media.json"
        if manifest.exists():
            try:
                paths = json.loads(manifest.read_text(encoding="utf-8"))
                paths = [p for p in paths if Path(p).exists()]
                if len(paths) >= want * 0.6:
                    logger.info("ch%02d: media cache hit (%d images)", idx + 1, len(paths))
                    return paths
            except json.JSONDecodeError:
                pass

        got: List[str] = []
        per_query = max(1, (want // max(1, len(queries))) + 1)
        for q in queries:
            if len(got) >= want:
                break
            for path in self._commons_many(q, per_query, ch_dir):
                if path and self._accept(path):
                    got.append(path)
            time.sleep(0.25)
        # top up from stock, then AI
        for q in queries[:4]:
            if len(got) >= want:
                break
            for path in self._stock_many(q, 2, ch_dir):
                if path and self._accept(path):
                    got.append(path)
        if len(got) < want * 0.5:
            for q in queries[:AI_CAP_PER_CHAPTER]:
                if len(got) >= want:
                    break
                p = self._ai_one(q, ch_dir)
                if p:
                    got.append(p)
        got = [p for p in got if Path(p).exists()]
        # a chapter must never render with 2-3 pictures: repeat what we have
        if not got:
            raise RuntimeError(f"chapter {idx + 1}: no visuals found for {queries[:2]}")
        if len(got) < since_needed(want):
            logger.warning("ch%02d only %d visuals (wanted %d) — will hold each longer",
                           idx + 1, len(got), want)
        manifest.write_text(json.dumps(got, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("ch%02d: %d visuals", idx + 1, len(got))
        return got

    # ----------------------------------------------------------------- commons
    def _commons_many(self, query: str, k: int, dest_dir: Path) -> List[str]:
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=self.timeout,
                             params={"action": "query", "format": "json", "generator": "search",
                                     "gsrnamespace": 6, "gsrsearch": f"{query} filetype:bitmap",
                                     "gsrlimit": 12, "prop": "imageinfo",
                                     "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1920})
            pages = r.json().get("query", {}).get("pages", {}) or {}
        except Exception as exc:
            logger.debug("commons '%s' failed: %s", query, exc)
            return []
        out = []
        terms = {t for t in _tokens(query)}
        for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
            if len(out) >= k:
                break
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                continue
            w, h = info.get("width", 0), info.get("height", 0)
            if w < MIN_W or h < MIN_H:
                continue
            # Relevance gate. Commons search is fuzzy: "Pashupati seal" happily
            # returns a photo of someone rock climbing. Require the file title or
            # its description to share meaningful vocabulary with the query.
            meta = info.get("extmetadata") or {}
            blob = " ".join([
                str(page.get("title", "")),
                str(meta.get("ImageDescription", {}).get("value", "")),
                str(meta.get("Categories", {}).get("value", "")),
                str(meta.get("ObjectName", {}).get("value", "")),
            ])
            if terms and not (terms & set(_tokens(blob))):
                logger.debug("rejected off-topic: %s (query '%s')", page.get("title", "")[:50], query)
                continue
            url = info.get("thumburl") or info.get("url")
            if not url:
                continue
            name = hashlib.sha1(url.encode()).hexdigest()[:12]
            path = dest_dir / f"{name}.jpg"
            if str(path) in self._kept and path.exists():
                out.append(str(path))
                continue
            if not self._download(url, path):
                continue
            out.append(str(path))
        return out

    # ------------------------------------------------------------------- stock
    def _stock_many(self, query: str, k: int, dest_dir: Path) -> List[str]:
        out: List[str] = []
        if self.pexels_key:
            try:
                r = requests.get("https://api.pexels.com/v1/search", timeout=self.timeout,
                                 headers={"Authorization": self.pexels_key},
                                 params={"query": query, "per_page": k * 2, "orientation": "landscape",
                                         "size": "large"})
                for ph in (r.json().get("photos") or [])[:k]:
                    src = ph.get("src", {}).get("large2x") or ph.get("src", {}).get("large")
                    if not src:
                        continue
                    path = dest_dir / f"px_{ph['id']}.jpg"
                    if self._download(src, path):
                        out.append(str(path))
            except Exception as exc:
                logger.debug("pexels '%s' failed: %s", query, exc)
        if len(out) < k and self.pixabay_key:
            try:
                r = requests.get("https://pixabay.com/api/", timeout=self.timeout,
                                 params={"key": self.pixabay_key, "q": query, "image_type": "photo",
                                         "orientation": "horizontal", "per_page": max(3, k),
                                         "min_width": MIN_W, "safesearch": "true"})
                for hit in (r.json().get("hits") or [])[:k]:
                    src = hit.get("largeImageURL") or hit.get("webformatURL")
                    if not src:
                        continue
                    path = dest_dir / f"pb_{hit['id']}.jpg"
                    if self._download(src, path):
                        out.append(str(path))
            except Exception as exc:
                logger.debug("pixabay '%s' failed: %s", query, exc)
        return out

    # ---------------------------------------------------------------------- ai
    def _ai_one(self, query: str, dest_dir: Path) -> Optional[str]:
        path = dest_dir / f"ai_{hashlib.sha1(query.encode()).hexdigest()[:10]}.jpg"
        if path.exists():
            return str(path)
        prompt = (f"{query}. Cinematic documentary illustration, historically accurate, natural light, "
                  "wide 16:9 composition, muted colours, no text, no watermark, no logos, no real faces")
        # Agnes first (free, generous), then the free HF Space route
        if self.agnes_key:
            try:
                r = requests.post("https://apihub.agnes-ai.com/v1/images/generations",
                                  headers={"Authorization": f"Bearer {self.agnes_key}",
                                           "Content-Type": "application/json"},
                                  json={"model": "agnes-image-2.5-flash", "prompt": prompt,
                                        "size": "1024x576", "n": 1}, timeout=180)
                if r.status_code == 200:
                    data = r.json().get("data") or []
                    url = (data[0] or {}).get("url") if data else ""
                    if url and self._download(url, path):
                        logger.info("ch ai: %s via agnes", query[:40])
                        return str(path)
                else:
                    logger.debug("agnes image HTTP %s", r.status_code)
            except Exception as exc:
                logger.debug("agnes image failed: %s", exc)
        try:
            from video.image_generator import AIImageGenerator
            gen = AIImageGenerator(self.hf_token)
            out = gen.generate(prompt, str(path))
            if out:
                logger.info("ch ai: %s via %s", query[:40], "hf-space")
                return out
        except Exception as exc:
            logger.debug("hf image failed: %s", exc)
        return None

    # ------------------------------------------------------------------ helpers
    def _download(self, url: str, dest: Path) -> bool:
        try:
            r = requests.get(url, headers=UA, timeout=self.timeout, stream=True)
            if r.status_code != 200:
                return False
            data = r.raw.read(20_000_000) if hasattr(r.raw, "read") else r.content
            if len(data) < 12_000:
                return False
            dest.write_bytes(data)
            return True
        except Exception:
            return False

    def _accept(self, path: str) -> bool:
        """Reject duplicates across the whole film and unusable frames."""
        try:
            data = Path(path).read_bytes()
        except OSError:
            return False
        digest = hashlib.sha1(data).hexdigest()
        if digest in self._seen:
            # same picture reached us twice: drop the copy, but NEVER delete a file
            # that was already accepted (two queries can resolve to one filename)
            if path not in self._kept:
                Path(path).unlink(missing_ok=True)
            return False
        self._seen.add(digest)
        self._kept.add(path)
        try:
            from PIL import Image
            from video.media_collector import MediaCollector  # reuse the existing junk detector
            with Image.open(path) as im:
                w, h = im.size
            if w < MIN_W or h < MIN_H or w / h < 0.5:
                Path(path).unlink(missing_ok=True)
                return False
            if MediaCollector._is_blank_or_logo(Image.open(path)) if hasattr(
                    MediaCollector, "_is_blank_or_logo") else False:
                Path(path).unlink(missing_ok=True)
                return False
        except Exception:
            pass
        return True


_STOP = {"the", "a", "an", "of", "and", "in", "on", "at", "to", "for", "with", "photo", "image",
         "file", "jpg", "jpeg", "png", "commons", "wikimedia", "museum", "collection"}


def _tokens(text: str) -> List[str]:
    import re
    return [t for t in re.findall(r"[a-z]{3,}", str(text).lower()) if t not in _STOP]


def since_needed(want: int) -> int:
    """Below this many visuals a chapter starts looking like a slideshow of 3 photos."""
    return max(3, want // 3)
