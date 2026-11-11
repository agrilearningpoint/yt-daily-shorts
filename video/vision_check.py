"""Does this photo really show the line being spoken? Vision judge + a free word-check.

Two layers, because the channel's biggest complaint is "image और voice match नहीं करते":

1. ``make_vision_check`` — a VLM (Gemini, best model first) looks at the candidate and
   answers YES/NO. Fails *open* (returns None = "no opinion") when every model is out of
   quota, so a dead key can never blank the whole video — the caller then falls back to
   the word-check instead of showing nothing.
2. ``keyword_match`` — free, no API: the spoken line's content words vs the picture's
   own words (alt text, title, Wikipedia entity, search query). Catches the classic
   "voice कह रही है मंदिर, स्क्रीन पर गिरजाघर" case without spending a single call.

The caller (``MediaCollector``) uses 2 → 1 → best-available, so every beat gets a picture
that at least names the same thing as the narration.
"""
from __future__ import annotations

import base64
import io
import logging
import re
import threading
from typing import Callable, Iterable, List, Optional

import requests
from PIL import Image

logger = logging.getLogger("video.vision")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Words that carry no visual meaning: matching on them proves nothing.
_STOP = set("""
के की का में से को और पर ने है हैं था थी थे होगा हुई हुआ लिए एक यह वह ये वो भी तो ही नहीं बहुत कुछ
the a an of in on at to for from with by is are was were be been being this that these those it its
and or but not no very much more most some any all as if then than so such also into over under
""".split())


def content_words(text: str, min_len: int = 3) -> List[str]:
    """Meaningful words in a Hindi/English line (Devanagari + latin), stops removed."""
    words = re.findall(r"[\u0900-\u097F]{2,}|[A-Za-z]{3,}", (text or "").lower())
    return [w for w in words if w not in _STOP and len(w) >= min_len]


def keyword_match(spoken: str, picture_words: Iterable[str]) -> float:
    """0.0–1.0: share of the spoken line's content words that the picture's own text carries."""
    spoken_words = content_words(spoken)
    if not spoken_words:
        return 0.0
    hay = " ".join(w for w in (str(x or "").lower() for x in picture_words))
    if not hay.strip():
        return 0.0
    hits = sum(1 for w in spoken_words if w in hay or w[:max(3, len(w) - 2)] in hay)
    return hits / len(spoken_words)


def make_vision_check(api_key: str, models: Optional[List[str]] = None,
                      max_calls: int = 150) -> Optional[Callable[[str, str], Optional[bool]]]:
    """Returns check(path, description) -> True / False / None (None = no opinion, key dead).

    None is the important change: the old version returned False when Gemini was out of
    quota, which made MediaCollector throw away every real photo and fall back to a
    generic AI card — the "photo doesn't match the voice" bug.
    """
    if not api_key:
        return None
    models = models or ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
    state = {"calls": 0, "dead": set()}
    lock = threading.Lock()

    def check(path: str, description: str) -> Optional[bool]:
        with lock:
            if state["calls"] >= max_calls:
                return None          # budget spent: no opinion, caller uses the word-check
            state["calls"] += 1
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            return False
        img.thumbnail((512, 512))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        prompt = (f"A Hindi news video shows this photo while the narrator says: \"{description}\".\n"
                  "Does the photo clearly show that scene, its people, place or object (not a random/unrelated "
                  "stock photo, not a different country's scene, not a logo or text slide, not a social-media post "
                  "or profile screenshot, not a TV/website screenshot with on-screen text)? Answer only YES or NO.")
        body = {"contents": [{"parts": [{"text": prompt},
                                        {"inline_data": {"mime_type": "image/jpeg",
                                                         "data": base64.b64encode(buf.getvalue()).decode()}}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 5}}
        tried = 0
        for m in models:
            if m in state["dead"]:
                continue
            tried += 1
            try:
                r = requests.post(URL.format(model=m), params={"key": api_key}, json=body, timeout=30)
                if r.status_code in (404, 400):
                    state["dead"].add(m)      # model name not available on this key
                    continue
                if r.status_code == 429:
                    logger.warning("vision quota exhausted on %s — deferring to the word check", m)
                    return None
                if r.status_code != 200:
                    continue
                txt = "".join(p.get("text", "") for p in
                              r.json()["candidates"][0]["content"]["parts"]).strip().upper()
                return not txt.startswith("NO")
            except Exception as exc:
                logger.debug("vision %s failed: %s", m, exc)
        if tried == 0:
            return None
        return None   # every model failed: no opinion, not a rejection

    return check
