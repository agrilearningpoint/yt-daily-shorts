"""Chaptered documentary scripting.

Two passes, so each LLM response stays small enough to never truncate:

1. **Outline** — one call: chapter titles + English visual-search queries.
2. **Narration** — one call *per chapter*, with a strict word budget and a
   "use only these facts" instruction, because a 25-minute Hindi script written
   in a single call gets cut off or starts inventing dates.

Everything is cached in `script.json` so a re-run never re-pays for LLM calls.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("longform.script")

OUTLINE_PROMPT = """You are the head writer of a Hindi documentary channel (DNA-quality, fact-checked).

TOPIC: {topic}
ANGLE: {angle}
TOTAL LENGTH: {minutes} minutes of narration across {n} chapters.

Build an outline of exactly {n} chapters that together cover the topic from its
earliest origin to the present day, in chronological order, with no chapter
overlapping another.

For every chapter return:
  - "title": a short Hindi chapter title (max 45 chars, no emoji)
  - "point": one English sentence saying what this chapter proves/explains
  - "visual_queries": 6 English Wikimedia-Commons/Pexels search queries for this
    chapter. Use concrete, photographable nouns (place names, monuments,
    manuscripts, art, festivals, objects). Never use abstract words like
    "spirituality" or "devotion" — they return nothing.

Rules:
  - Chapter 1 is the hook + "what this video covers", not a definition dump.
  - The last chapter must land the topic in the present day and close the loop.
  - Strictly factual: only well-established history. If a date is disputed, the
    outline must say so in "point".

Return ONLY JSON:
{{"title": "<Hindi video title, max 90 chars>",
  "chapters": [{{"title": "...", "point": "...", "visual_queries": ["...", "..."]}}]}}"""

CHAPTER_PROMPT = """You are writing ONE chapter of a Hindi documentary narration.

VIDEO: {video_title}
CHAPTER {idx}/{total}: {chapter_title}
WHAT THIS CHAPTER MUST PROVE: {point}
NEXT CHAPTER (do not spoil it): {next_title}
TARGET LENGTH: {words} words of spoken Hindi (roughly {secs} seconds of narration).

STYLE
  - Documentary Hindi (Sanskritised but spoken, like a well-researched YouTube documentary).
  - Short sentences. One idea per sentence. Written to be HEARD, not read.
  - Second person is banned ("आप" only in the final call-to-action of the last chapter).
  - No "नमस्कार दोस्तों", no channel name, no "आज हम जानेंगे" filler.
  - Every factual claim must be one that appears in standard history textbooks.
    If historians disagree, say so plainly ("इतिहासकारों में मतभेद है").
  - Never invent dates, names, verses, or numbers. If unsure, leave it out.
  - No emoji, no markdown, no headings, no bullet points — pure narration text.
  - Close the chapter with one sentence that pulls the viewer forward.

FACTS THAT MUST APPEAR IN THIS CHAPTER:
{facts}

Return ONLY JSON: {{"narration": "<the whole chapter narration>"}}"""

FACTS = {
    "default": "- Use only well-established history; no invented dates or quotes.",
}


def _facts_for(idx: int, topic_key: str = "") -> str:
    """Curated anchors per chapter — keeps dates/names from drifting."""
    return _FACT_SETS.get(idx + 1, _FACTS_FALLBACK)


_FACTS_FALLBACK = ("- Anchor the chapter in 2-3 concrete, checkable facts (a place, a text, a date range).\n"
                   "- No invented verses, no invented numbers.")

# Curated for the Hindu Dharma film; other topics fall back to the generic rule.
_FACT_SETS: Dict[int, str] = {
    1: ("- The word 'हिंदू' comes from the Sanskrit 'सिंधु' (Indus); Persian speakers called the land beyond "
        "the river 'Hindu', and the Greeks 'Indoi'. The term is geographic first, religious later.\n"
        "- 'हिंदू धर्म' is an umbrella for many traditions — Vaishnava, Shaiva, Shakta, Smarta — not one church.\n"
        "- Oldest living major tradition: the Vedas are dated roughly 1500-1200 BCE by mainstream scholarship."),
    2: ("- Indus Valley Civilisation: mature phase roughly 2600-1900 BCE, spread over ~1.3 million sq km.\n"
        "- Mohenjo-daro: Great Bath, grid streets, covered drainage. Harappa: granaries, standardised bricks.\n"
        "- The 'Pashupati seal' (a seated figure surrounded by animals) is often read as an early Shiva-like "
        "figure — but scholars caution this is an interpretation, not proof.\n"
        "- No surviving temple or scripture from this civilisation; its script is undeciphered."),
    3: ("- Rigveda: ~1028 hymns in 10 mandalas; four Vedas total (Rig, Sama, Yajur, Atharva).\n"
        "- Transmitted orally with extraordinary accuracy (śākhā lineages) long before writing.\n"
        "- Deities: Indra, Agni, Varuna, Usha, Surya. Fire sacrifice (yajna) is the central ritual.\n"
        "- The Purusha-sukta (Rigveda 10.90) is the hymn later used to justify varna — a much-debated verse.\n"
        "- Vedic period ends around 500 BCE with the rise of cities, iron, and the Upanishadic turn."),
    4: ("- Principal Upanishads: Brihadaranyaka, Chandogya, Katha, Isha, Mundaka and others, roughly 800-300 BCE.\n"
        "- Core vocabulary: Brahman (ultimate reality), Atman (self), karma, samsara, moksha.\n"
        "- Six classical darshanas: Nyaya, Vaisheshika, Samkhya, Yoga, Mimamsa, Vedanta.\n"
        "- Same centuries see the rise of Buddhism (Siddhartha Gautama, c. 5th century BCE) and Jainism "
        "(Mahavira) — both reject Vedic authority.\n"
        "- 'तत् त्वम् असि' (Chandogya) and 'अहं ब्रह्मास्मि' (Brihadaranyaka) are the most quoted mahavakyas."),
    5: ("- Ramayana: attributed to Valmiki, ~24,000 verses; seven kandas; Rama, Sita, Hanuman, Ravana.\n"
        "- Mahabharata: ~100,000 verses, the longest epic; core war narrative plus the Bhagavad Gita "
        "(18 chapters, Krishna's counsel to Arjuna).\n"
        "- Both grew orally for centuries; the written texts we have are later recensions with regional variants.\n"
        "- The Gita's questions — duty, action without attachment, the self beyond the body — shaped later "
        "Vedanta, Gandhi's reading, and modern Indian thought."),
    6: ("- The 18 Mahapuranas (c. 300-1000 CE) supply cosmology, genealogies and temple lore.\n"
        "- Trimurti: Brahma (creator), Vishnu (preserver), Shiva (dissolver) — a relatively late synthesis.\n"
        "- Dashavatara: ten avatars of Vishnu, from Matsya to Kalki.\n"
        "- Temple worship (puja, murti, pilgrimage) becomes the dominant popular form in this era, "
        "alongside the older fire ritual.\n"
        "- Puranic geography and genealogies vary widely between texts; they are narrative, not chronicle."),
    7: ("- South India: Alvars (Vaishnava) and Nayanars (Shaiva), 6th-9th century CE, poetry in Tamil.\n"
        "- North India: Kabir (15th c.), Mirabai (16th c.), Tulsidas' Ramcharitmanas (16th c., Awadhi), "
        "Surdas, Ravidas.\n"
        "- Bengal: Chaitanya Mahaprabhu (15th-16th c.) and sankirtan.\n"
        "- Guru Nanak (1469-1539) and the Sikh tradition emerged in this same devotional climate.\n"
        "- Bhakti and Sufi shrines shared audiences; several saints are claimed by both traditions.\n"
        "- Bhakti made devotion accessible in the people's own languages, bypassing Sanskrit ritual."),
    8: ("- Gupta period (4th-6th c. CE): classical temple form, Dashavatara temple at Deogarh.\n"
        "- South: Chola Bronzes (9th-13th c.), Brihadeeswarar temple at Thanjavur (completed ~1010 CE, "
        "UNESCO), Meenakshi temple at Madurai.\n"
        "- North/Central: Khajuraho (Chandela, 10th-11th c.), Konark Sun Temple (13th c., Odisha), "
        "Lingaraja at Bhubaneswar.\n"
        "- Cave art: Ajanta (Buddhist, 2nd c. BCE - 6th c. CE) and Ellora (Buddhist, Hindu, Jain, 6th-10th c.).\n"
        "- Temple = scale model of cosmos + economic centre + art archive."),
    9: ("- 19th century reform: Raja Ram Mohan Roy (Brahmo Samaj, 1828) and the 1829 ban on sati; "
        "Dayanand Saraswati (Arya Samaj, 1875).\n"
        "- Swami Vivekananda's 1893 Chicago address; Ramakrishna Mission (1897).\n"
        "- Gandhi's use of ahimsa and the Gita in the freedom movement; Ambedkar's critique of caste and the "
        "temple-entry movements.\n"
        "- 1950 Constitution abolishes untouchability (Article 17) and guarantees religious freedom.\n"
        "- Today: ~1.1 billion Hindus worldwide, the third-largest religion; diaspora communities in Nepal, "
        "Bangladesh, Indonesia (Bali), Mauritius, the Caribbean, the US, the UK and the Gulf.\n"
        "- Yoga and meditation are now global practices with Hindu roots, often detached from the tradition."),
}


class ChapterScript(dict):
    """dict with attribute access — keeps the pipeline readable."""


class ScriptWriter:
    def __init__(self, llm, words_per_chapter: int = 430) -> None:
        self.llm = llm
        self.words_per_chapter = words_per_chapter

    # ------------------------------------------------------------------ outline
    async def write_outline(self, topic: str, angle: str, minutes: int, chapters: int) -> Dict[str, Any]:
        prompt = OUTLINE_PROMPT.format(topic=topic, angle=angle, minutes=minutes, n=chapters)
        data = await self.llm.generate_json(prompt, tier="quality")
        chs = data.get("chapters") or []
        if len(chs) < 4:
            raise RuntimeError(f"outline returned only {len(chs)} chapters")
        for c in chs:
            c.setdefault("title", "अध्याय")
            c.setdefault("point", "")
            q = [str(x) for x in (c.get("visual_queries") or []) if str(x).strip()]
            if len(q) < 3:   # never let a chapter starve for visuals
                q = (q + ["Hindu temple India", "Indian manuscript painting",
                          "Indian festival crowd", "Indian monument architecture"])[:6]
            c["visual_queries"] = q[:6]
        logger.info("outline: %d chapters — %s", len(chs), data.get("title", "")[:60])
        return {"title": data.get("title") or topic, "chapters": chs[:chapters]}

    # ---------------------------------------------------------------- narration
    async def write_chapter(self, video_title: str, ch: Dict[str, Any], idx: int,
                            total: int, next_title: str) -> str:
        words = self.words_per_chapter
        prompt = CHAPTER_PROMPT.format(
            video_title=video_title, idx=idx + 1, total=total, chapter_title=ch["title"],
            point=ch.get("point", ""), next_title=next_title or "समापन",
            words=words, secs=int(words / 2.6), facts=_facts_for(idx),
        )
        data = await self.llm.generate_json(prompt, tier="quality")
        text = (data.get("narration") or "").strip()
        # A chapter that comes back at 60% of the budget is what turned a "22 minute"
        # film into a 16 minute one. Insist on the budget twice, keep the longest answer.
        for attempt in range(2):
            if len(text.split()) >= words * 0.92:
                break
            logger.warning("chapter %d short (%d/%d words) — extending (attempt %d)",
                           idx + 1, len(text.split()), words, attempt + 1)
            data = await self.llm.generate_json(
                prompt + f"\n\nYour previous answer was only {len(text.split())} words out of {words}. "
                         "Rewrite the SAME chapter at the full length: add concrete, checkable detail "
                         "(dates, places, names, numbers, cause and effect). Never pad with filler and "
                         "never repeat a sentence.", tier="quality")
            candidate = (data.get("narration") or "").strip()
            if len(candidate.split()) > len(text.split()):
                text = candidate
        text = _clean(text)
        logger.info("chapter %d/%d: %d words", idx + 1, total, len(text.split()))
        return text

    async def lengthen(self, video_title: str, ch: Dict[str, Any], idx: int, total: int,
                       target_words: int) -> str:
        """Rewrite a chapter longer, using the real measured audio gap as the brief."""
        have = ch.get("narration", "")
        prompt = CHAPTER_PROMPT.format(
            video_title=video_title, idx=idx + 1, total=total, chapter_title=ch["title"],
            point=ch.get("point", ""), next_title="समापन", words=target_words,
            secs=int(target_words / 2.6), facts=_facts_for(idx),
        )
        prompt += (f"\n\nThe narration below is only {len(have.split())} words and speaks for too short a "
                   f"time. Rewrite it at {target_words}+ words. Keep the same opening, the same closing "
                   "sentence and the same order of ideas; add concrete detail (dates, places, names, "
                   "numbers, consequences, comparisons). Do not repeat a sentence, do not pad.\n\n"
                   f"CURRENT NARRATION:\n{have}")
        data = await self.llm.generate_json(prompt, tier="quality")
        out = _clean((data.get("narration") or "").strip())
        logger.info("chapter %d lengthened: %d -> %d words", idx + 1, len(have.split()), len(out.split()))
        return out or have

    # -------------------------------------------------------------------- build
    async def build(self, topic: str, angle: str, minutes: int, chapters: int,
                    out_dir: Path) -> Dict[str, Any]:
        cache = out_dir / "script.json"
        if cache.exists():
            data = json.loads(cache.read_text(encoding="utf-8"))
            if len(data.get("chapters", [])) == chapters and all(c.get("narration") for c in data["chapters"]):
                logger.info("script.json cache hit (%d chapters)", len(data["chapters"]))
                return data
        out_dir.mkdir(parents=True, exist_ok=True)
        outline = await self.write_outline(topic, angle, minutes, chapters)
        chs = outline["chapters"]
        for i, ch in enumerate(chs):
            nxt = chs[i + 1]["title"] if i + 1 < len(chs) else ""
            ch["narration"] = await self.write_chapter(outline["title"], ch, i, len(chs), nxt)
            # save after every chapter — a crash never loses finished work
            cache.write_text(json.dumps({**outline, "chapters": chs}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        data = {**outline, "chapters": chs}
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        total_words = sum(len(c["narration"].split()) for c in chs)
        logger.info("script complete: %d chapters, %d words (~%.1f min)",
                    len(chs), total_words, total_words / 2.6 / 60)
        return data


def _clean(text: str) -> str:
    """Strip markdown/emoji noise that TTS would read out loud."""
    import re
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#>`]+", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def split_sentences(text: str) -> List[str]:
    """Hindi-aware splitter: '।', '?', '!' plus a hard cap for very long sentences."""
    import re
    parts = re.split(r"(?<=[।?!])\s+", text.strip())
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p.split()) > 38:      # keep subtitle lines readable
            words = p.split()
            for i in range(0, len(words), 30):
                out.append(" ".join(words[i:i + 30]))
        else:
            out.append(p)
    return out
