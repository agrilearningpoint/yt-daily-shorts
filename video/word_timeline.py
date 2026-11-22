"""Smart word-level visual cuts timeline builder with continuous audio.

Tokenizes script text (Devanagari, Latin, digits, emojis), classifies words into
content cuts vs function glues, and groups words into frame-accurate, contiguous visual cuts
while ensuring the master audio track remains one continuous, uninterrupted stream.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("video.word_timeline")


class TokenType(str, Enum):
    CUT = "cut"
    GLUE = "glue"
    PUNCT = "punct"
    NUMBER = "number"
    EMOJI = "emoji"


@dataclass
class WordToken:
    text: str
    normalized: str
    start: float = 0.0
    end: float = 0.0
    token_type: TokenType = TokenType.CUT
    confidence: float = 1.0
    source: str = "script"
    char_start: int = 0
    char_end: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "normalized": self.normalized,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "token_type": self.token_type.value,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass
class WordGroup:
    group_id: str
    words: List[WordToken]
    start: float
    end: float
    text: str
    anchor_word_index: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "words": [w.to_dict() for w in self.words],
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "text": self.text,
            "anchor_word_index": self.anchor_word_index,
        }


@dataclass
class WordTimeline:
    groups: List[WordGroup]
    words: List[WordToken]
    audio_duration: float
    fps: int = 30
    source: str = "edge-tts"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groups": [g.to_dict() for g in self.groups],
            "words": [w.to_dict() for w in self.words],
            "audio_duration": round(self.audio_duration, 3),
            "fps": self.fps,
            "source": self.source,
            "warnings": list(self.warnings),
        }


HINDI_GLUE_WORDS = {
    "है", "हैं", "था", "थी", "थे", "का", "की", "के", "को", "में", "से", "पर",
    "और", "या", "ने", "नहीं", "भी", "तो", "ही", "कि", "जो", "वो", "यह", "वह",
    "एक", "कर", "रहा", "रही", "रहे", "गया", "गई", "गए", "सकता", "सकती", "सकते",
    "चाहिए", "लिए", "बिना", "साथ", "तक", "बाद", "पहले"
}

ENGLISH_GLUE_WORDS = {
    "is", "am", "are", "was", "were", "be", "been", "being",
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "with",
    "and", "or", "but", "not", "do", "does", "did", "have", "has", "had",
    "will", "would", "can", "could", "should", "may", "might", "must",
    "this", "that", "these", "those"
}

# Hindi postpositions attach to previous content word
HINDI_POSTPOSITIONS = {"का", "की", "के", "को", "में", "से", "पर", "ने", "तक", "लिए", "साथ", "बिना"}
# Hindi sentence-final auxiliary/helping verbs attach to previous content word
HINDI_AUX_FINAL = {"है", "हैं", "था", "थी", "थे", "गया", "गई", "गए", "रहा", "रही", "रहे"}

# Emojis regex pattern
EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF"
    r"\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    r"\u2600-\u26FF\u2700-\u27BF]"
)

PUNCT_CHARS = set("।॥.,!?;:'\"()[]{}<>/-–—\\|`~*#@")


class WordTimelineBuilder:
    def __init__(self, fps: int = 30) -> None:
        self.fps = fps

    def tokenize(self, text: str) -> List[WordToken]:
        """Tokenize script text preserving Devanagari conjuncts, Latin, numbers, punctuation, emojis."""
        clean_text = text or ""
        tokens: List[WordToken] = []

        pattern = re.compile(
            r"https?://\S+|"
            r"[#@][\w_]+|"
            r"\d+(?:\.\d+)?|"
            r"[A-Za-z0-9\u0900-\u097F]+(?:'[A-Za-z0-9\u0900-\u097F]+)?(?:-[A-Za-z0-9\u0900-\u097F]+)*|"
            r"[\U0001F300-\U0001FAFF\u2600-\u27BF]|"
            r"[।॥.,!?;:'\"()\[\]{}\-–—/\\&]"
        )

        for match in pattern.finditer(clean_text):
            tok_text = match.group(0).strip()
            if not tok_text:
                continue
            char_start = match.start()
            char_end = match.end()

            # Normalized version strips enclosing quotes or punctuation for classification
            normalized = tok_text.strip("।॥.,!?;:'\"()[]{}<>/-–—\\").lower()
            if not normalized:
                normalized = tok_text

            tokens.append(
                WordToken(
                    text=tok_text,
                    normalized=normalized,
                    char_start=char_start,
                    char_end=char_end,
                )
            )

        return tokens

    def classify(self, tokens: List[WordToken]) -> List[WordToken]:
        """Classify each token into CUT, GLUE, PUNCT, NUMBER, or EMOJI."""
        for t in tokens:
            raw = t.text
            norm = t.normalized

            if all(ch in PUNCT_CHARS for ch in raw):
                t.token_type = TokenType.PUNCT
            elif EMOJI_PATTERN.search(raw):
                t.token_type = TokenType.EMOJI
            elif re.match(r"^\d+(?:\.\d+)?$", norm):
                t.token_type = TokenType.NUMBER
            elif norm in HINDI_GLUE_WORDS or norm in ENGLISH_GLUE_WORDS:
                t.token_type = TokenType.GLUE
            else:
                t.token_type = TokenType.CUT

            # Context overrides:
            # If English auxiliary 'is', 'was' etc. is at the very end of clause or sentence, keep GLUE
            # If word is pronoun possessive like 'my', 'our', 'his', 'her', 'मेरा', 'हमारा', default to CUT
            if norm in {"my", "our", "his", "her", "their", "मेरा", "मेरी", "मेरे", "हमारा", "उसका", "उनका"}:
                t.token_type = TokenType.CUT

        return tokens

    def group(self, tokens: List[WordToken], policy: Optional[Dict[str, Any]] = None) -> List[WordGroup]:
        """Group tokens around CUT anchors based on glue policy, min/max durations, and word limits."""
        cfg = policy or {}
        glue_policy = cfg.get("word_cut_glue_policy", "auto")
        max_words = int(cfg.get("word_cut_max_words_per_group", 3))
        min_group_ms = float(cfg.get("word_cut_min_group_ms", 66))
        max_group_seconds = float(cfg.get("word_cut_max_group_seconds", 1.2))

        # Filter out isolated whitespace, but keep all tokens
        words_only = [t for t in tokens if t.token_type != TokenType.PUNCT]
        if not words_only:
            # Only punctuation or empty
            return []

        # If no CUT token exists in the list, promote the longest word to CUT
        if not any(t.token_type in (TokenType.CUT, TokenType.NUMBER, TokenType.EMOJI) for t in words_only):
            longest = max(words_only, key=lambda w: len(w.text))
            longest.token_type = TokenType.CUT

        # Initial grouping by attaching GLUE to CUT anchors
        groups_raw: List[List[WordToken]] = []
        current_acc: List[WordToken] = []

        # We attach each token according to policy
        for i, tok in enumerate(tokens):
            if tok.token_type == TokenType.PUNCT:
                # Attach punctuation to preceding word or group
                if groups_raw:
                    groups_raw[-1].append(tok)
                elif current_acc:
                    current_acc.append(tok)
                continue

            if tok.token_type in (TokenType.CUT, TokenType.NUMBER, TokenType.EMOJI):
                if current_acc:
                    # Previous GLUE tokens that were looking ahead for a CUT anchor
                    current_acc.append(tok)
                    groups_raw.append(list(current_acc))
                    current_acc = []
                else:
                    groups_raw.append([tok])
            elif tok.token_type == TokenType.GLUE:
                # Decide whether to attach to previous group or accumulate for next group
                attach_prev = False
                if glue_policy == "attach_prev":
                    attach_prev = True
                elif glue_policy == "attach_next":
                    attach_prev = False
                else:  # auto
                    # Check Hindi postpositions or final auxiliaries
                    if tok.normalized in HINDI_POSTPOSITIONS or tok.normalized in HINDI_AUX_FINAL:
                        attach_prev = True
                    # If this is the last word in the entire stream, must attach to previous
                    elif i == len(tokens) - 1 or not any(
                        t.token_type in (TokenType.CUT, TokenType.NUMBER, TokenType.EMOJI) for t in tokens[i + 1:]
                    ):
                        attach_prev = True
                    # If previous group exists and current word is an auxiliary following a content word
                    elif groups_raw and not current_acc and tok.normalized in {"है", "हैं", "था", "थी", "थे"}:
                        attach_prev = True
                    else:
                        attach_prev = False

                if attach_prev and groups_raw:
                    groups_raw[-1].append(tok)
                else:
                    current_acc.append(tok)

        # Flush any trailing accumulated tokens into the last group
        if current_acc:
            if groups_raw:
                groups_raw[-1].extend(current_acc)
            else:
                groups_raw.append(current_acc)

        # Enforce max words per group
        split_groups: List[List[WordToken]] = []
        for g in groups_raw:
            # Exclude punctuation when counting words
            content_words = [w for w in g if w.token_type != TokenType.PUNCT]
            if len(content_words) <= max_words:
                split_groups.append(g)
            else:
                # Split into chunks of max_words
                cur_chunk: List[WordToken] = []
                for w in g:
                    cur_chunk.append(w)
                    if len([x for x in cur_chunk if x.token_type != TokenType.PUNCT]) >= max_words:
                        split_groups.append(list(cur_chunk))
                        cur_chunk = []
                if cur_chunk:
                    split_groups.append(cur_chunk)

        # Build WordGroup dataclasses
        word_groups: List[WordGroup] = []
        for idx, g in enumerate(split_groups):
            w_only = [w for w in g if w.token_type != TokenType.PUNCT]
            if not w_only:
                continue
            start_t = min(w.start for w in w_only)
            end_t = max(w.end for w in w_only)
            joined_text = " ".join(w.text for w in g)

            # Find anchor word index
            anchor_idx = 0
            for i_w, w in enumerate(w_only):
                if w.token_type in (TokenType.CUT, TokenType.NUMBER, TokenType.EMOJI):
                    anchor_idx = i_w
                    break

            word_groups.append(
                WordGroup(
                    group_id=f"wg_{idx:03d}",
                    words=g,
                    start=start_t,
                    end=end_t,
                    text=joined_text,
                    anchor_word_index=anchor_idx,
                )
            )

        # Merge groups shorter than min_group_ms (66ms) only if timings are set
        min_sec = min_group_ms / 1000.0
        merged: List[WordGroup] = []
        for g in word_groups:
            has_timings = any(w.end > w.start for w in g.words)
            if merged and has_timings and g.duration < min_sec:
                # Merge into previous group
                prev = merged[-1]
                prev.words.extend(g.words)
                prev.end = max(prev.end, g.end)
                prev.text = (prev.text + " " + g.text).strip()
            elif not merged and has_timings and g.duration < min_sec and len(word_groups) > 1:
                # Very first group is tiny; merge into next (accumulate)
                merged.append(g)
            else:
                merged.append(g)

        # If the first was tiny and still isolated, merge into second if exists
        if len(merged) > 1 and any(w.end > w.start for w in merged[0].words) and merged[0].duration < min_sec:
            first = merged.pop(0)
            merged[0].words = first.words + merged[0].words
            merged[0].start = first.start
            merged[0].text = (first.text + " " + merged[0].text).strip()

        # Split groups longer than max_group_seconds at word boundaries if multiple words
        final_groups: List[WordGroup] = []
        for g in merged:
            if g.duration > max_group_seconds and len(g.words) > 1:
                mid = len(g.words) // 2
                g1_words = g.words[:mid]
                g2_words = g.words[mid:]
                t1 = g1_words[-1].end if g1_words else g.start
                final_groups.append(
                    WordGroup(
                        group_id=g.group_id,
                        words=g1_words,
                        start=g.start,
                        end=t1,
                        text=" ".join(w.text for w in g1_words),
                        anchor_word_index=0,
                    )
                )
                final_groups.append(
                    WordGroup(
                        group_id=f"{g.group_id}_b",
                        words=g2_words,
                        start=t1,
                        end=g.end,
                        text=" ".join(w.text for w in g2_words),
                        anchor_word_index=0,
                    )
                )
            else:
                final_groups.append(g)

        # Re-number group_ids
        for idx, g in enumerate(final_groups):
            g.group_id = f"wg_{idx:03d}"

        return final_groups

    def build(
        self, script: str, voice_result: Any, config: Optional[Dict[str, Any]] = None
    ) -> WordTimeline:
        """Build a complete frame-accurate, contiguous WordTimeline from script & VoiceResult."""
        cfg = config or {}
        fps = int(cfg.get("fps", self.fps))
        audio_duration = 0.0
        warnings: List[str] = []

        # 1. Tokenize & Classify script
        tokens = self.tokenize(script)
        classified = self.classify(tokens)

        # 2. Extract raw word timings from VoiceResult
        raw_timings: List[Any] = []
        if hasattr(voice_result, "beat_words") and voice_result.beat_words:
            for b in voice_result.beat_words:
                raw_timings.extend(b)
        elif hasattr(voice_result, "words") and voice_result.words:
            raw_timings = list(voice_result.words)

        if hasattr(voice_result, "audio_path") and voice_result.audio_path:
            from video.tts import probe_duration
            audio_duration = probe_duration(voice_result.audio_path)
        if audio_duration <= 0.0 and hasattr(voice_result, "durations") and voice_result.durations:
            audio_duration = float(sum(voice_result.durations))

        # 3. Align WordTokens with raw timings
        content_tokens = [t for t in classified if t.token_type != TokenType.PUNCT]
        n_tokens = len(content_tokens)
        n_timings = len(raw_timings)

        if n_tokens > 0:
            if n_timings == n_tokens:
                # Direct 1:1 mapping
                for tok, rt in zip(content_tokens, raw_timings):
                    tok.start = getattr(rt, "start", 0.0)
                    tok.end = max(tok.start + 0.04, getattr(rt, "end", tok.start + 0.2))
                    tok.confidence = getattr(rt, "confidence", 1.0)
                    tok.source = getattr(rt, "source", "edge-tts")
            elif n_timings > 0:
                # Proportional mapping using available timing anchors
                warnings.append(
                    f"Word count mismatch: script has {n_tokens} words, TTS has {n_timings} word timings. Interpolating."
                )
                t_start = getattr(raw_timings[0], "start", 0.0)
                t_end = getattr(raw_timings[-1], "end", audio_duration)
                total_span = max(t_end - t_start, 0.5)
                step = total_span / n_tokens
                for i, tok in enumerate(content_tokens):
                    tok.start = round(t_start + i * step, 3)
                    tok.end = round(t_start + (i + 1) * step, 3)
                    tok.confidence = 0.7
                    tok.source = "interpolated"
            else:
                # No raw timings provided; distribute across audio duration
                warnings.append("No TTS word timings found; distributing words proportionally across audio.")
                step = (audio_duration or 10.0) / n_tokens
                for i, tok in enumerate(content_tokens):
                    tok.start = round(i * step, 3)
                    tok.end = round((i + 1) * step, 3)
                    tok.confidence = 0.5
                    tok.source = "proportional"

        # 4. Group tokens into cuts
        groups = self.group(classified, policy=cfg)

        # 5. Snap to frame grid and ensure contiguous coverage
        # Frame snap: round(t * fps) / fps
        if groups:
            # First group starts at 0.0
            groups[0].start = 0.0
            for i in range(len(groups)):
                g = groups[i]
                # Frame snap
                start_frame = round(g.start * fps)
                end_frame = round(g.end * fps)
                if end_frame <= start_frame:
                    end_frame = start_frame + 2  # min 2 frames

                g.start = start_frame / fps
                g.end = end_frame / fps

                # Ensure contiguous connection with previous group: no gaps!
                if i > 0:
                    prev = groups[i - 1]
                    if g.start < prev.end:
                        # Overlap: push g.start to prev.end
                        g.start = prev.end
                    elif g.start > prev.end:
                        # Gap: extend prev.end to g.start (hold previous visual)
                        prev.end = g.start

                    # Ensure group still has at least 2 frames
                    if g.end <= g.start:
                        g.end = round(g.start + (2.0 / fps), 3)

            # Ensure the last group covers until the end of audio duration
            if audio_duration > 0 and groups[-1].end < audio_duration:
                groups[-1].end = round(audio_duration, 3)

        source_name = getattr(voice_result, "provider", "tts")
        return WordTimeline(
            groups=groups,
            words=classified,
            audio_duration=audio_duration,
            fps=fps,
            source=source_name,
            warnings=warnings,
        )
