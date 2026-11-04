"""Media collector for stock footage and images with graceful procedural fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional
import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("video.media")


class MediaCollector:
    """Collects visuals from Pexels/Pixabay APIs or renders stylized procedural cards."""

    def __init__(self, pexels_key: str = "", pixabay_key: str = "", cache_dir: str = "data/media_cache"):
        self.pexels_key = pexels_key
        self.pixabay_key = pixabay_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_scene_visual(self, scene_number: int, query: str, output_path: str, video_type: str = "news") -> str:
        """Fetch stock image/video or generate stylized card."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. Try Pexels if key exists
        if self.pexels_key:
            res = self._fetch_pexels(query, str(out_file))
            if res:
                return res

        # 2. Try Pixabay if key exists
        if self.pixabay_key:
            res = self._fetch_pixabay(query, str(out_file))
            if res:
                return res

        # 3. Fallback: Generate high quality 1080x1920 graphic card with Pillow
        return self._generate_procedural_card(scene_number, query, str(out_file), video_type)

    def _fetch_pexels(self, query: str, dest: str) -> Optional[str]:
        try:
            url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
            headers = {"Authorization": self.pexels_key}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                photos = data.get("photos", [])
                if photos:
                    img_url = photos[0]["src"]["large2x"]
                    img_data = requests.get(img_url, timeout=15).content
                    with open(dest, "wb") as f:
                        f.write(img_data)
                    return dest
        except Exception as exc:
            logger.warning("Pexels fetch error: %s", exc)
        return None

    def _fetch_pixabay(self, query: str, dest: str) -> Optional[str]:
        try:
            url = f"https://pixabay.com/api/?key={self.pixabay_key}&q={query}&image_type=photo&orientation=vertical"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", [])
                if hits:
                    img_url = hits[0]["largeImageURL"]
                    img_data = requests.get(img_url, timeout=15).content
                    with open(dest, "wb") as f:
                        f.write(img_data)
                    return dest
        except Exception as exc:
            logger.warning("Pixabay fetch error: %s", exc)
        return None

    def _generate_procedural_card(self, scene_number: int, text: str, dest: str, video_type: str) -> str:
        """Render a vertical 1080x1920 poster with gradient and typography."""
        width, height = 1080, 1920
        # Color palettes based on scene
        color_themes = [
            ((15, 23, 42), (30, 58, 138)),   # Deep Navy to Blue
            ((30, 27, 75), (88, 28, 135)),   # Deep Indigo to Purple
            ((20, 20, 20), (55, 65, 81)),    # Dark Slate
            ((19, 78, 74), (13, 148, 136)),  # Deep Teal
        ]
        top_color, bottom_color = color_themes[scene_number % len(color_themes)]

        img = Image.new("RGB", (width, height), top_color)
        draw = ImageDraw.Draw(img)

        # Draw vertical gradient
        for y in range(height):
            ratio = y / height
            r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
            g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
            b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Accent decorative shapes
        draw.rectangle([60, 100, 1020, 120], fill=(255, 153, 51)) # Saffron banner accent
        draw.rectangle([60, 1800, 1020, 1820], fill=(19, 136, 8)) # Green accent

        # Clean text
        badge_text = f"DAILY {video_type.upper()} SHORTS"
        draw.text((80, 150), badge_text, fill=(255, 255, 255))
        
        # Draw central subject query
        words = text.split()
        lines = []
        curr = []
        for w in words:
            curr.append(w)
            if len(" ".join(curr)) > 28:
                lines.append(" ".join(curr))
                curr = []
        if curr:
            lines.append(" ".join(curr))

        start_y = 750
        for line in lines[:6]:
            draw.text((100, start_y), line, fill=(240, 240, 240))
            start_y += 60

        img.save(dest, "JPEG", quality=90)
        logger.info("Generated procedural visual card: %s", dest)
        return dest
