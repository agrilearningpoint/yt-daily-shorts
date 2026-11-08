"""Word-synced Hindi captions (ASS karaoke-style highlight) + plain SRT export."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("video.subtitles")


def _format_timestamp(seconds: float) -> str:
    """SRT timestamp HH:MM:SS,mmm"""
    ms_total = int(round(max(seconds, 0) * 1000))
    h, rem = divmod(ms_total, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
    cs_total = int(round(max(seconds, 0) * 100))
    h, rem = divmod(cs_total, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_color: str, alpha: str = "00") -> str:
    v = hex_color.lstrip("#")
    r, g, b = v[0:2], v[2:4], v[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def group_words(words: Sequence[Dict[str, Any]], max_words: int = 3, max_chars: int = 20) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for w in words:
        candidate = " ".join(x["word"] for x in cur + [w])
        if cur and (len(cur) >= max_words or len(candidate) > max_chars):
            groups.append(cur)
            cur = []
        cur.append(w)
        if w["word"].endswith(("।", ".", "?", "!", ",")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


class SubtitleGenerator:
    """Creates subtitle files. Words are dicts: {word, start, end} in seconds (absolute)."""

    def generate_ass(self, words: Sequence[Dict[str, Any]], output_path: str,
                     highlight_color: str = "#FFD60A", font_name: str = "Mukta ExtraBold",
                     width: int = 1080, height: int = 1920, font_size: int = 104,
                     margin_v: int = 560) -> str:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,9,4,2,70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        hl = _ass_color(highlight_color)
        lines = []
        groups = group_words(list(words))
        for gi, grp in enumerate(groups):
            g_end = grp[-1]["end"]
            if gi + 1 < len(groups):
                g_end = max(g_end, min(groups[gi + 1][0]["start"], g_end + 0.6))
            for wi, w in enumerate(grp):
                start = w["start"]
                end = grp[wi + 1]["start"] if wi + 1 < len(grp) else g_end
                if end - start < 0.05:
                    continue
                parts = []
                for wj, x in enumerate(grp):
                    token = _escape(x["word"])
                    if wj == wi:
                        parts.append(f"{{\\c{hl}\\fscx108\\fscy108}}{token}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
                    else:
                        parts.append(token)
                pop = "{\\fad(60,0)}" if wi == 0 else ""
                lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
        out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Generated ASS captions (%d groups): %s", len(groups), out)
        return str(out)

    def generate_srt_from_words(self, words: Sequence[Dict[str, Any]], output_path: str) -> str:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        blocks = []
        for i, grp in enumerate(group_words(list(words), max_words=6, max_chars=40), 1):
            blocks.append(f"{i}\n{_format_timestamp(grp[0]['start'])} --> {_format_timestamp(grp[-1]['end'])}\n"
                          + " ".join(w["word"] for w in grp) + "\n")
        out.write_text("\n".join(blocks), encoding="utf-8")
        return str(out)

    # Back-compat: scene-level SRT with estimated timings ---------------------
    def generate_srt(self, scenes: List[Dict[str, Any]], output_path: str) -> str:
        words: List[Dict[str, Any]] = []
        t = 0.0
        for scene in scenes:
            narration = scene.get("narration", "").strip()
            duration = float(scene.get("duration", 15.0))
            toks = narration.split()
            if not toks:
                t += duration
                continue
            step = duration / len(toks)
            for tok in toks:
                words.append({"word": tok, "start": t, "end": t + step})
                t += step
        return self.generate_srt_from_words(words, output_path)
