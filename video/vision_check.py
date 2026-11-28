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
from collections.abc import Callable, Iterable

import requests
from PIL import Image

logger = logging.getLogger("video.vision")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Words that carry no visual meaning: matching on them proves nothing.
_STOP = {
    "के",
    "की",
    "का",
    "में",
    "से",
    "को",
    "और",
    "पर",
    "ने",
    "है",
    "हैं",
    "था",
    "थी",
    "थे",
    "होगा",
    "हुई",
    "हुआ",
    "लिए",
    "एक",
    "यह",
    "वह",
    "ये",
    "वो",
    "भी",
    "तो",
    "ही",
    "नहीं",
    "बहुत",
    "कुछ",
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "from",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "and",
    "or",
    "but",
    "not",
    "no",
    "very",
    "much",
    "more",
    "most",
    "some",
    "any",
    "all",
    "as",
    "if",
    "then",
    "than",
    "so",
    "such",
    "also",
    "into",
    "over",
    "under",
}


def content_words(text: str, min_len: int = 3) -> list[str]:
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
    hits = sum(1 for w in spoken_words if w in hay or w[: max(3, len(w) - 2)] in hay)
    return hits / len(spoken_words)


def make_vision_check(
    api_key: str | Iterable[str],
    models: list[str] | None = None,
    max_calls: int = 150,
) -> Callable[[str, str], bool | None] | None:
    """Returns check(path, description) -> True / False / None (None = no opinion, key dead).

    None is the important change: the old version returned False when Gemini was out of
    quota, which made MediaCollector throw away every real photo and fall back to a
    generic AI card — the "photo doesn't match the voice" bug.
    """
    # Accept a key RING. The channel configures three Gemini keys; the old signature took a
    # single string, so one exhausted key silently disabled every vision check in the run while
    # two perfectly good keys sat unused.
    keys = [k for k in ([api_key] if isinstance(api_key, str) else list(api_key)) if k]
    if not keys:
        return None
    models = models or [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    ]
    state = {"calls": 0, "dead": set(), "key": 0}
    lock = threading.Lock()

    def check(path: str, description: str) -> bool | None:
        with lock:
            if state["calls"] >= max_calls:
                return None  # budget spent: no opinion, caller uses the word-check
            if len(state["dead"]) >= len(models) * len(keys):
                return None  # every model on every key is exhausted
            state["calls"] += 1
        try:
            with Image.open(path) as raw_im:
                img = raw_im.convert("RGB")
        except Exception:  # noqa: BLE001 - an unreadable image cannot be judged
            return False
        img.thumbnail((512, 512))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        prompt = (
            f'A Hindi news video shows this image while the headline says: "{description}".\n'
            "Is this image reasonably related to or suitable for this news story, person, organisation, place, or topic? "
            "Answer YES if it is relevant (portraits of mentioned people, buildings, events, press photos, or relevant news context are all acceptable). "
            "Only answer NO if it is totally unrelated, completely blank, or severely corrupt. "
            "Answer strictly YES or NO."
        )
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(buf.getvalue()).decode(),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 10},
        }
        for _slot in range(len(keys)):
            with lock:
                slot = state["key"] % len(keys)
                current_key = keys[slot]
            for m in models:
                with lock:
                    if (m, slot) in state["dead"]:
                        continue
                try:
                    r = requests.post(
                        URL.format(model=m), params={"key": current_key}, json=body, timeout=30
                    )
                    if r.status_code in (404, 400, 403):
                        with lock:
                            state["dead"].add((m, slot))
                        continue
                    if r.status_code == 429:
                        with lock:
                            state["dead"].add((m, slot))
                            state["key"] += 1  # rotate to the next key in the pool
                        logger.warning(
                            "vision quota exhausted on %s (key %d/%d) — rotating",
                            m,
                            state["key"],
                            len(keys),
                        )
                        break  # next key: restart the model list
                    if r.status_code != 200:
                        continue
                    cands = r.json().get("candidates") or []
                    parts = (cands[0].get("content") or {}).get("parts") or [] if cands else []
                    txt = "".join(p.get("text", "") for p in parts).strip().upper()
                    if not txt:
                        continue
                    toks = re.findall(r"[A-Z]+", txt)
                    if toks and toks[0] == "NO":
                        return False
                    return not ("NO" in toks and "YES" not in toks)
                except Exception as exc:  # noqa: BLE001 - one model failing is not the end
                    logger.debug("vision %s failed: %s", m, exc)
        return None  # every model on every key failed: no opinion, not a rejection

    return check
