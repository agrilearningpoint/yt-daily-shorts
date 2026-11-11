"""SEO for a finished documentary: title, description, tags — and a memory of what worked.

The shorts pipeline always had a SEO agent; the long-form one shipped a hardcoded
description and a fixed tag list. This module makes the same "learn from the last
runs" loop available to documentaries:

  * ``build_metadata``  asks the best model for title/description/tags against the
    real script, the real chapter timestamps and the real runtime.
  * ``lessons_for_prompt`` from ``core.self_improve`` feeds past failures in, so a
    run that lost its upload never repeats the mistake silently.
  * ``record_film`` writes one line to ``data/metrics.jsonl``; the error analyst
    and ``data/improvements.md`` are generated from that same file.

Everything degrades to the deterministic default when the LLM is unavailable, so a
quota error can never block a finished film from being published.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.self_improve import lessons_for_prompt, record_run

logger = logging.getLogger("longform.seo")

DEFAULT_TAGS = ["हिंदू धर्म", "hindu dharma", "history of hinduism in hindi", "सिंधु घाटी सभ्यता",
                "वैदिक काल", "उपनिषद", "भक्ति आंदोलन", "भारतीय इतिहास", "sanatan dharma explained",
                "indian history documentary hindi", "hinduism explained", "hindu temple history"]

PROMPT = """You are the SEO editor of a Hindi documentary channel. Return JSON only.

FILM TITLE: {title}
RUNTIME: {minutes:.0f} minutes, {chapters} chapters
CHAPTERS (title + what they cover):
{outline}

WHAT HAS FAILED BEFORE (do not repeat):
{lessons}

Write metadata a serious documentary channel would use:
  "titles": 5 candidates, 45-75 characters, Hindi Devanagari, no clickbait, no ALL CAPS,
            at most one number, the main keyword inside the first 40 characters.
  "description": 700-1100 characters. Line 1 is a single hook sentence. Then 4-6 short
            paragraphs. Then explicitly say the film is educational and that dates follow
            mainstream scholarship where historians disagree.
  "tags": 12-15 strings, Devanagari + roman keywords a Hindi viewer would actually type.
Return keys: titles, description, tags."""


def _outline(chapters: List[Dict[str, Any]], limit: int = 10) -> str:
    lines = []
    for i, ch in enumerate(chapters[:limit]):
        point = str(ch.get("point") or "")[:140]
        lines.append(f"{i + 1}. {ch.get('title', '')}" + (f" — {point}" if point else ""))
    return "\n".join(lines) or "(none)"


def _fallback(title: str, chapters: List[Dict[str, Any]], stamps: List[str], duration: float) -> Dict[str, Any]:
    desc = (
        f"{title}\n\n"
        "इस वीडियो में हम हिंदू धर्म की यात्रा को उसकी शुरुआत से आज तक समझेंगे — सिंधु घाटी से "
        "वैदिक काल, उपनिषदों के दर्शन, महाकाव्यों, पुराणों और मंदिर परंपरा से लेकर भक्ति आंदोलन "
        "और आधुनिक भारत तक।\n\n"
        "⏱ अध्याय\n" + "\n".join(stamps) + "\n\n"
        "यह वीडियो शैक्षिक उद्देश्य से बनाया गया है। तिथियाँ और तथ्य मानक इतिहास-ग्रंथों पर आधारित "
        "हैं; जहाँ इतिहासकारों में मतभेद है, वहाँ स्पष्ट रूप से बताया गया है।\n\n"
        f"#हिंदूधर्म #इतिहास #भारत #सनातन #documentary"
    )
    return {"title": title[:95], "description": desc[:4900], "tags": list(DEFAULT_TAGS),
            "duration_sec": round(duration, 1), "chapter_stamps": stamps, "seo": "fallback"}


async def build_metadata(llm, title: str, chapters: List[Dict[str, Any]], stamps: List[str],
                         duration: float) -> Dict[str, Any]:
    base = _fallback(title, chapters, stamps, duration)
    if llm is None:
        return base
    try:
        meta = await llm.generate_json(PROMPT.format(
            title=title, minutes=duration / 60.0, chapters=len(chapters),
            outline=_outline(chapters), lessons=lessons_for_prompt(600) or "(none yet)"),
            tier="quality")
    except Exception as exc:
        logger.warning("SEO generation failed (%s) — shipping the deterministic metadata", exc)
        return base

    titles = [str(t).strip() for t in (meta.get("titles") or meta.get("title") or []) if str(t).strip()]
    if isinstance(meta.get("title"), str) and meta["title"].strip():
        titles.append(meta["title"].strip())
    best = ""
    try:
        from youtube.seo import pick_best_title
        best = pick_best_title(titles) or ""
    except Exception:
        best = titles[0] if titles else ""
    desc = str(meta.get("description") or "").strip()
    tags = [str(t).strip() for t in (meta.get("tags") or []) if str(t).strip()]

    out = dict(base)
    if best:
        out["title"] = best[:95]
    if len(desc) >= 200:
        out["description"] = (desc + "\n\n⏱ अध्याय\n" + "\n".join(stamps))[:4900]
    if tags:
        merged = tags[:15]
        for t in DEFAULT_TAGS:
            if len(merged) >= 15:
                break
            if t not in merged:
                merged.append(t)
        out["tags"] = merged[:15]
    out["seo"] = "llm"
    logger.info("SEO: title=%r tags=%d desc=%d chars", out["title"], len(out["tags"]),
                len(out["description"]))
    return out


def record_film(kind: str, minutes: float, ok: bool, errors: List[str] | None = None,
                **extra: Any) -> None:
    """One metrics line per film so the error analyst can see long-form runs."""
    try:
        record_run(kind, minutes, ok, errors or [], extra=extra or None)
    except Exception as exc:  # never let telemetry break a render
        logger.debug("metrics write skipped: %s", exc)
