"""Broadcast-grade Motion Graphics Engine for 1080x1920 Vertical Shorts & Videos.

Generates broadcast TV news layers:
- Breaking News Live Header with pulsing indicator
- News Story Index Counter (e.g., '01 / 20', '02 / 20')
- Color-coded Category Badges (National, World, Economy, Defence, Science)
- Dynamic Lower Third Headline Straps with Devanagari text wrapping
- Highlight Stat Chips for numbers, amounts, and records
- Continuous segmented progress bar
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont, features

logger = logging.getLogger("video.motion_graphics")

W, H = 1080, 1920
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Category color themes (Accent, Background)
CATEGORY_COLORS: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = {
    "राष्ट्रीय": ((255, 153, 51), (15, 23, 42)),  # Saffron + Dark Slate
    "अंतरराष्ट्रीय": ((59, 130, 246), (15, 23, 42)),  # Blue + Dark Slate
    "कारोबार": ((16, 185, 129), (6, 78, 59)),  # Emerald Green
    "रक्षा": ((239, 68, 68), (69, 10, 10)),  # Crimson Red
    "विज्ञान": ((139, 92, 246), (46, 16, 101)),  # Purple
    "खेल": ((245, 158, 11), (67, 20, 7)),  # Amber
    "आज": ((244, 63, 94), (19, 78, 74)),  # Rose Teal
    "default": ((225, 29, 72), (15, 23, 42)),  # Ruby
}


def _get_font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    path = FONT_DIR / f"Mukta-{weight}.ttf"
    kwargs = {}
    if features.check("raqm"):
        kwargs["layout_engine"] = ImageFont.Layout.RAQM
    try:
        return ImageFont.truetype(str(path), size, **kwargs)
    except OSError:
        return ImageFont.load_default()


def _wrap_headline(
    draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int, max_lines: int = 2
) -> List[str]:
    words = text.split()
    lines: List[str] = []
    curr = ""
    for w in words:
        test = f"{curr} {w}".strip()
        if draw.textlength(test, font=fnt) <= max_w or not curr:
            curr = test
        else:
            lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)
    return lines[:max_lines]


class MotionGraphicsEngine:
    """Generates broadcast TV quality transparent overlay cards."""

    def __init__(self, channel_name: str = "BHARAT KI SOCH"):
        self.channel_name = channel_name

    def compose_broadcast_overlay(
        self,
        out_path: str,
        headline: str,
        category: str,
        story_index: int,
        total_stories: int,
        date_str: str = "",
        is_hook: bool = False,
    ) -> str:
        """Compose a full 1080x1920 transparent PNG overlay with TV-style lower thirds and header."""
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # -------------------------------------------------------------
        # 1. TOP HEADER: Breaking News Banner + Live Indicator
        # -------------------------------------------------------------
        # Header background pill
        d.rounded_rectangle([40, 60, W - 40, 140], radius=20, fill=(10, 15, 30, 220))
        d.rounded_rectangle([40, 60, W - 40, 140], radius=20, outline=(255, 255, 255, 40), width=2)

        # Red Live indicator box
        d.rounded_rectangle([50, 70, 170, 130], radius=14, fill=(220, 38, 38, 255))
        d.ellipse([65, 92, 81, 108], fill=(255, 255, 255, 255))  # White dot
        fnt_live = _get_font(34, "ExtraBold")
        d.text((92, 79), "LIVE", font=fnt_live, fill=(255, 255, 255, 255))

        # Channel name / Bulletin title
        fnt_title = _get_font(38, "Bold")
        bulletin_title = "सुपरफास्ट 20+ बड़ी खबरें" if not is_hook else f"{self.channel_name} | BREAKING"
        d.text((195, 76), bulletin_title, font=fnt_title, fill=(255, 255, 255, 240))

        # Date & Time label (right aligned)
        if date_str:
            fnt_date = _get_font(30, "Medium")
            dw = d.textlength(date_str, font=fnt_date)
            d.text((W - 70 - dw, 82), date_str, font=fnt_date, fill=(203, 213, 225, 230))

        # -------------------------------------------------------------
        # 2. STORY COUNTER & CATEGORY BADGE
        # -------------------------------------------------------------
        if not is_hook and story_index > 0:
            # Story Counter Pill: 'खबर 01 / 20'
            counter_text = f"खबर {story_index:02d} / {total_stories:02d}"
            fnt_counter = _get_font(34, "Bold")
            cw = d.textlength(counter_text, font=fnt_counter)
            d.rounded_rectangle([40, 160, 40 + cw + 40, 224], radius=16, fill=(255, 214, 10, 255))
            d.text((60, 169), counter_text, font=fnt_counter, fill=(10, 10, 10, 255))

            # Category Badge
            cat_name = category.strip() or "राष्ट्रीय"
            cat_color, cat_bg = CATEGORY_COLORS.get(cat_name, CATEGORY_COLORS["default"])
            fnt_cat = _get_font(34, "Bold")
            cat_w = d.textlength(cat_name, font=fnt_cat)
            cat_x = 40 + cw + 55
            d.rounded_rectangle(
                [cat_x, 160, cat_x + cat_w + 40, 224], radius=16, fill=cat_color + (240,)
            )
            d.text((cat_x + 20, 169), cat_name, font=fnt_cat, fill=(255, 255, 255, 255))

        # -------------------------------------------------------------
        # 3. LOWER THIRD HEADLINE STRAP
        # -------------------------------------------------------------
        if headline.strip():
            fnt_head = _get_font(72, "ExtraBold") if is_hook else _get_font(60, "Bold")
            lines = _wrap_headline(
                d, headline.strip(), fnt_head, W - 140, max_lines=3 if is_hook else 2
            )

            box_h = len(lines) * 88 + 48
            box_y = 1380 - box_h  # positioned cleanly above YouTube UI controls

            # Translucent dark backdrop
            d.rounded_rectangle(
                [40, box_y, W - 40, box_y + box_h], radius=24, fill=(10, 15, 28, 230)
            )
            d.rounded_rectangle(
                [40, box_y, W - 40, box_y + box_h], radius=24, outline=(255, 255, 255, 30), width=2
            )

            # Left accent highlight bar
            accent_col = (255, 214, 10, 255) if is_hook else (225, 29, 72, 255)
            d.rounded_rectangle([42, box_y + 8, 54, box_y + box_h - 8], radius=6, fill=accent_col)

            # Headline text
            ty = box_y + 22
            for line in lines:
                d.text(
                    (70, ty),
                    line,
                    font=fnt_head,
                    fill=(255, 255, 255, 255),
                    stroke_width=2,
                    stroke_fill=(0, 0, 0, 180),
                )
                ty += 84

        # -------------------------------------------------------------
        # 4. SEGMENTED PROGRESS TIMELINE (At Bottom)
        # -------------------------------------------------------------
        if total_stories > 1 and not is_hook:
            bar_y = H - 60
            avail_w = W - 80
            gap = 6
            seg_w = max(4.0, (avail_w - (total_stories - 1) * gap) / total_stories)

            for idx in range(total_stories):
                x0 = 40 + idx * (seg_w + gap)
                x1 = x0 + seg_w
                fill_color = (255, 214, 10, 255) if idx < story_index else (255, 255, 255, 70)
                d.rounded_rectangle([x0, bar_y, x1, bar_y + 8], radius=4, fill=fill_color)

        img.save(str(out_file), "PNG")
        return str(out_file)
