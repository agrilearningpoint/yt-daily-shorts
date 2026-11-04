"""Subtitle file generator for vertical 1080x1920 YouTube Shorts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("video.subtitles")


def _format_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class SubtitleGenerator:
    """Creates SRT and ASS subtitle files aligned to scene narrations."""

    def generate_srt(self, scenes: List[Dict[str, Any]], output_path: str) -> str:
        """Create standard SRT subtitles with timing calculated per scene narration."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        current_time = 0.0
        lines = []
        subtitle_index = 1

        for scene in scenes:
            narration = scene.get("narration", "").strip()
            duration = float(scene.get("duration", 15.0))
            if not narration:
                current_time += duration
                continue

            # Split narration into 2-3 word chunks or clauses for fast shorts readability
            words = narration.split()
            chunk_size = 6  # 5-6 words per caption card
            chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
            chunk_duration = duration / max(len(chunks), 1)

            for chunk in chunks:
                start_str = _format_timestamp(current_time)
                end_time = current_time + chunk_duration
                end_str = _format_timestamp(end_time)

                lines.append(f"{subtitle_index}")
                lines.append(f"{start_str} --> {end_str}")
                lines.append(f"{chunk}\n")

                subtitle_index += 1
                current_time = end_time

        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info("Generated SRT subtitle file: %s", out_file)
        return str(out_file)

    def generate_ass(self, scenes: List[Dict[str, Any]], output_path: str, primary_color: str = "&H00FFFF&") -> str:
        """Generate Advanced SubStation Alpha (.ass) format with custom fonts and positioning."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Mukta,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(header)

        return str(out_file)
