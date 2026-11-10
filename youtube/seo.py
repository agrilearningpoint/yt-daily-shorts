"""YouTube SEO: title lint, search-first description, tags.

Rules (Satyam, 2026-11-10): no source links, no image credits in the description. The description is
written for search: the first two lines carry the words people type, then today's headlines as plain
text, then a natural keyword paragraph, then a few relevant hashtags.

Title lint rules adapted from youtube-agent-skill/title.py (MIT, (c) 2026 Jake Schincariol).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

DESKTOP, MOBILE, HARD = 60, 40, 100
VAGUE = {"amazing", "incredible", "insane", "crazy", "huge", "massive", "ultimate", "best", "secret",
         "shocking", "epic", "viral", "जबरदस्त", "धमाकेदार", "चौंकाने", "हैरान", "सनसनीखेज"}
STOP = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "are", "का", "की", "के", "में",
        "है", "हैं", "और", "से", "को", "पर", "ने", "यह", "वह", "क्या"}


@dataclass
class FormattedSEO:
    title: str
    description: str
    tags: List[str]
    category_id: str = "27"


def _words(t: str) -> List[str]:
    return [w for w in re.findall(r"[\w']+", t.lower()) if w]


def lint_title(title: str) -> Dict[str, object]:
    """Score a title 0-100 for search/feed packaging. Higher is better."""
    t = " ".join(title.split())
    n = len(t)
    issues, good = [], []
    if n > HARD:
        issues.append("over 100 chars")
    elif n > DESKTOP:
        issues.append(f"{n} chars, desktop search cuts near {DESKTOP}")
    else:
        good.append("fits desktop")
    if n > MOBILE + 15:
        issues.append("mobile feed may cut the subject")
    caps = [w for w in t.split() if len(w) > 2 and w.isascii() and w.isupper()]
    if len(caps) > 2:
        issues.append("too many ALL-CAPS words")
    if any(w in VAGUE for w in _words(t)):
        issues.append("vague hype word; use a name, number or date")
    if re.search(r"\d", t):
        good.append("has a number/date")
    front = [w for w in _words(t)[:3] if w not in STOP]
    if not front:
        issues.append("subject not in first words")
    else:
        good.append("subject up front")
    if "#" in t.replace("#shorts", "").replace("#Shorts", ""):
        issues.append("hashtag inside title")
    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "score": score, "issues": issues}


def pick_best_title(candidates: List[str]) -> str:
    cands = [" ".join(c.split()) for c in candidates if c and c.strip()]
    if not cands:
        return ""
    return max(cands, key=lambda c: lint_title(c)["score"])


def query_coverage(queries: List[str], title: str, first_lines: str) -> float:
    """Share of meaningful query words that appear in the title or the first two description lines."""
    hay = set(_words(title + " " + first_lines))
    need = [w for q in queries for w in _words(q) if w not in STOP and len(w) > 1]
    if not need:
        return 1.0
    return sum(1 for w in need if w in hay) / len(need)


def build_tags(tags: List[str], limit_chars: int = 480, max_tags: int = 30) -> List[str]:
    seen, out, size = set(), [], 0
    for t in tags:
        t = " ".join(str(t).replace("#", "").replace(",", " ").replace("<", "").replace(">", "").split()).strip()
        k = t.lower()
        if not t or k in seen or len(t) > 60:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1   # YouTube counts quotes around multi-word tags
        if size + cost > limit_chars or len(out) >= max_tags:
            break
        seen.add(k)
        out.append(t)
        size += cost
    return out


def build_hashtags(raw: List[str], base: List[str], max_n: int = 5) -> List[str]:
    out: List[str] = []
    for h in list(base) + list(raw):
        h = "#" + re.sub(r"[^\w]", "", str(h).lstrip("#"))
        if len(h) > 2 and h.lower() not in {x.lower() for x in out}:
            out.append(h)
        if len(out) >= max_n:
            break
    return out


class YouTubeSEOFormatter:
    @staticmethod
    def format_title(raw_title: str, max_length: int = 100) -> str:
        clean = " ".join(raw_title.replace("<", "").replace(">", "").split())
        if "#shorts" not in clean.lower():
            clean = f"{clean} #shorts"
        if len(clean) > max_length:
            clean = clean[: max_length - 11].rstrip() + "… #shorts"
        return clean

    @staticmethod
    def format_description(summary_hook: str, source_urls: Optional[List[str]] = None,
                           hashtags: Optional[List[str]] = None,
                           channel_name: str = "BHARAT KI SOCH",
                           media_credits: Optional[List[str]] = None, max_length: int = 5000,
                           story_lines: Optional[List[str]] = None, sources_title: str = "",
                           keywords_paragraph: str = "", headlines_title: str = "आज की बड़ी खबरें") -> str:
        """No source links and no image credits (Satyam, 2026-11-10). source_urls is ignored."""
        parts = [summary_hook.strip()]
        if story_lines:
            heads = "".join(f"{i}. {line}\n" for i, line in enumerate(story_lines, 1))
            parts.append(f"📰 {headlines_title}:\n{heads}".rstrip())
        if keywords_paragraph:
            parts.append(keywords_paragraph.strip())
        parts.append(f"🔔 रोज़ की ताज़ा खबरों के लिए {channel_name} को सब्सक्राइब करें!")
        ai_note = "ℹ️ यह वीडियो AI की मदद से (स्क्रिप्ट व आवाज़) बनाया गया है।"
        if media_credits and any("AI" in c for c in media_credits):
            ai_note += " कुछ सांकेतिक दृश्य भी AI से बने हैं।"
        parts.append(ai_note)
        if hashtags:
            parts.append(" ".join(h if h.startswith("#") else f"#{h}" for h in hashtags))
        desc = "\n\n".join(p for p in parts if p)
        desc = re.sub(r"https?://\S+", "", desc).replace("<", "").replace(">", "")
        return desc[:max_length].strip()
