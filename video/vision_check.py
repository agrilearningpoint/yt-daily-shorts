"""Gemini looks at a candidate photo and says whether it really shows the line being spoken.

Idea from KoroLiu/auto-news-shorts (imagecheck): "better no picture than an unrelated picture".
Fails open (returns True) when Gemini is unavailable, so a quota error never blanks a video.
"""
from __future__ import annotations

import base64
import io
import logging
import threading
from typing import Callable, List, Optional

import requests
from PIL import Image

logger = logging.getLogger("video.vision")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def make_vision_check(api_key: str, models: Optional[List[str]] = None,
                      max_calls: int = 60) -> Optional[Callable[[str, str], bool]]:
    if not api_key:
        return None
    models = models or ["gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
    state = {"calls": 0, "dead": set()}
    lock = threading.Lock()

    def check(path: str, description: str) -> bool:
        with lock:
            if state["calls"] >= max_calls:
                return True
            state["calls"] += 1
        img = Image.open(path).convert("RGB")
        img.thumbnail((512, 512))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        prompt = (f"A Hindi news video shows this photo while the narrator says: \"{description}\".\n"
                  "Does the photo clearly show that scene, its people, place or object (not a random/unrelated "
                  "stock photo, not a different country's scene, not a logo or text slide, not a social-media post or "
                  "profile screenshot, not a TV/website screenshot with on-screen text)? Answer only YES or NO.")
        body = {"contents": [{"parts": [{"text": prompt},
                                        {"inline_data": {"mime_type": "image/jpeg",
                                                         "data": base64.b64encode(buf.getvalue()).decode()}}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 5}}
        for m in models:
            if m in state["dead"]:
                continue
            try:
                r = requests.post(URL.format(model=m), params={"key": api_key}, json=body, timeout=30)
                if r.status_code in (404, 400):
                    state["dead"].add(m)
                    continue
                if r.status_code != 200:
                    continue
                txt = "".join(p.get("text", "") for p in
                              r.json()["candidates"][0]["content"]["parts"]).strip().upper()
                return not txt.startswith("NO")
            except Exception as exc:
                logger.debug("vision %s failed: %s", m, exc)
        return True

    return check
