"""Draws 1080x1920 scene layers with proper Devanagari shaping (Pillow + raqm).

* background layer (oversized for Ken Burns motion): photo with blurred fill,
  or a designed gradient card when no photo exists.
* overlay layer (transparent PNG): badge, headline, progress bar, watermark.
"""

from __future__ import annotations

import logging
import math
import random
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from video.creative_variation import hex_to_rgb

logger = logging.getLogger("video.composer")

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1080, 1920
ZOOM_PAD = 1.12  # background is rendered 12% larger for zoompan headroom


def font(size: int, weight: str = "ExtraBold") -> ImageFont.FreeTypeFont:
    path = FONT_DIR / f"Mukta-{weight}.ttf"
    kwargs = {}
    if features.check("raqm"):
        kwargs["layout_engine"] = ImageFont.Layout.RAQM
    try:
        return ImageFont.truetype(str(path), size, **kwargs)
    except OSError:
        logger.error("Font missing: %s", path)
        return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int, max_lines: int = 3) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=fnt) <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(",।") + "…"
    return lines


def _gradient(size: Tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        r = y / max(h - 1, 1)
        base.putpixel((0, y), tuple(int(top[i] * (1 - r) + bottom[i] * r) for i in range(3)))
    return base.resize((w, h))


class SceneComposer:
    def __init__(self, theme: Optional[dict] = None, channel_name: str = ""):
        theme = theme or {}
        self.primary = hex_to_rgb(theme.get("primary_color", "#FF9933"))
        self.secondary = hex_to_rgb(theme.get("secondary_color", "#1D3557"))
        self.bg = hex_to_rgb(theme.get("background_color", "#0F172A"))
        self.channel_name = channel_name

    # ------------------------------------------------------------------
    def compose_background(self, image_path: Optional[str], out_path: str, seed: int = 0,
                           card_text: str = "") -> str:
        bw, bh = int(W * ZOOM_PAD), int(H * ZOOM_PAD)
        if image_path and Path(image_path).exists():
            src = Image.open(image_path).convert("RGB")
            # blurred cover fill
            scale = max(bw / src.width, bh / src.height)
            fill = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1))
            fill = fill.crop(((fill.width - bw) // 2, (fill.height - bh) // 2,
                              (fill.width - bw) // 2 + bw, (fill.height - bh) // 2 + bh))
            fill = fill.filter(ImageFilter.GaussianBlur(28))
            fill = Image.blend(fill, Image.new("RGB", fill.size, (0, 0, 0)), 0.45)
            # sharp foreground: fill most of the frame if portrait-ish, else fit width
            ratio = src.width / src.height
            if ratio < 0.8:
                fs = max(bw / src.width, bh / src.height)
            else:
                fs = (bw * 1.0) / src.width
            fg = src.resize((max(1, int(src.width * fs)), max(1, int(src.height * fs))), Image.LANCZOS)
            if fg.height > bh:
                top = (fg.height - bh) // 2
                fg = fg.crop((0, top, fg.width, top + bh))
            if fg.width > bw:
                left = (fg.width - bw) // 2
                fg = fg.crop((left, 0, left + bw, fg.height))
            x = (bw - fg.width) // 2
            y = int(bh * 0.47) - fg.height // 2
            y = max(0, min(y, bh - fg.height))
            fill.paste(fg, (x, y))
            canvas = fill
        else:
            canvas = self._designed_card((bw, bh), seed, card_text)
        # vignette top/bottom for text legibility
        shade = Image.new("L", (1, bh))
        for yy in range(bh):
            r = yy / bh
            a = 0
            if r < 0.28:
                a = int(170 * (1 - r / 0.28))
            elif r > 0.58:
                a = int(200 * ((r - 0.58) / 0.42))
            shade.putpixel((0, yy), a)
        shade = shade.resize((bw, bh))
        canvas = Image.composite(Image.new("RGB", (bw, bh), (0, 0, 0)), canvas, shade)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, "JPEG", quality=92)
        return out_path

    def _designed_card(self, size, seed: int, text: str) -> Image.Image:
        bw, bh = size
        img = _gradient(size, self.bg, self.secondary)
        rnd = random.Random(seed)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for _ in range(7):
            r = rnd.randint(120, 420)
            cx, cy = rnd.randint(0, bw), rnd.randint(int(bh * 0.25), int(bh * 0.8))
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=self.primary + (60,), width=rnd.randint(3, 10))
        for i in range(0, bw, 90):
            d.line([(i, 0), (i - bh // 3, bh)], fill=(255, 255, 255, 10), width=2)
        img = Image.alpha_composite(img.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(2)))
        if text:
            d2 = ImageDraw.Draw(img)
            f = font(150)
            lines = wrap_text(d2, text, f, int(bw * 0.8), 3)
            y = int(bh * 0.45) - len(lines) * 85
            for ln in lines:
                tw = d2.textlength(ln, font=f)
                d2.text(((bw - tw) / 2, y), ln, font=f, fill=(255, 255, 255, 235),
                        stroke_width=4, stroke_fill=(0, 0, 0, 160))
                y += 175
        return img.convert("RGB")

    # ------------------------------------------------------------------
    def compose_overlay(self, out_path: str, headline: str, badge: str, index: int, total: int,
                        date_label: str = "") -> str:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # badge pill
        bf = font(46, "Bold")
        label = badge.strip()
        if label:
            tw = d.textlength(label, font=bf)
            d.rounded_rectangle([60, 150, 60 + tw + 60, 228], radius=39, fill=self.primary + (255,))
            d.text((90, 152), label, font=bf, fill=(10, 10, 10, 255))
        if date_label:
            df = font(40, "Medium")
            dw = d.textlength(date_label, font=df)
            d.text((W - 60 - dw, 163), date_label, font=df, fill=(255, 255, 255, 230),
                   stroke_width=2, stroke_fill=(0, 0, 0, 180))

        # headline
        if headline.strip():
            hf = font(104)
            lines = wrap_text(d, headline.strip(), hf, W - 140, 2)
            y = 268
            for ln in lines:
                tw = d.textlength(ln, font=hf)
                pad = 26
                d.rounded_rectangle([60 - 6, y + 18, 60 + tw + pad * 2, y + 140], radius=18, fill=(0, 0, 0, 150))
                d.text((60 + pad, y), ln, font=hf, fill=(255, 255, 255, 255))
                y += 138
            d.rectangle([60, y + 18, 220, y + 30], fill=self.primary + (255,))

        # progress bar
        if total > 1:
            seg_w = (W - 120 - (total - 1) * 12) / total
            for i in range(total):
                x0 = 60 + i * (seg_w + 12)
                col = self.primary + (255,) if i <= index else (255, 255, 255, 90)
                d.rounded_rectangle([x0, 92, x0 + seg_w, 102], radius=5, fill=col)

        # watermark
        if self.channel_name:
            wf = font(38, "Medium")
            ww = d.textlength(self.channel_name, font=wf)
            d.text(((W - ww) / 2, H - 230), self.channel_name, font=wf, fill=(255, 255, 255, 150))

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "PNG")
        return out_path

    # ------------------------------------------------------------------
    def compose_thumbnail(self, image_path: Optional[str], out_path: str, title: str) -> str:
        bg_path = str(Path(out_path).with_suffix(".bg.jpg"))
        self.compose_background(image_path, bg_path, seed=7)
        bg = Image.open(bg_path).convert("RGB")
        bw, bh = bg.size
        bg = bg.crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W, (bh - H) // 2 + H))
        d = ImageDraw.Draw(bg)
        f = font(132)
        lines = wrap_text(d, title.replace("#shorts", "").strip(), f, W - 140, 4)
        y = int(H * 0.60)
        for i, ln in enumerate(lines):
            tw = d.textlength(ln, font=f)
            fill = self.primary if i == 0 else (255, 255, 255)
            d.text(((W - tw) / 2, y), ln, font=f, fill=fill, stroke_width=8, stroke_fill=(0, 0, 0))
            y += 160
        bg.save(out_path, "JPEG", quality=92)
        Path(bg_path).unlink(missing_ok=True)
        return out_path
