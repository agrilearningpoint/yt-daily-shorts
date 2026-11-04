"""Visual theme rotation so consecutive videos never look identical."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


@dataclass
class VisualTheme:
    name: str
    primary_color: str      # accent bars / badges
    secondary_color: str    # gradient end
    background_color: str   # gradient start
    caption_highlight: str  # active-word caption colour
    transition: str
    music_mood: str
    font_name: str = "Mukta-ExtraBold"
    video_types: tuple = ("news", "knowledge")

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["theme_name"] = self.name
        d.pop("video_types", None)
        return d


PRESET_THEMES: List[VisualTheme] = [
    VisualTheme("Breaking News Pulse", "#E63946", "#1D3557", "#0B1320", "#FFD60A", "fade", "news", video_types=("news",)),
    VisualTheme("Saffron Bulletin", "#FF9933", "#132A13", "#0F172A", "#FFD60A", "slideleft", "news", video_types=("news",)),
    VisualTheme("Midnight Desk", "#00B4D8", "#03045E", "#020617", "#FFE66D", "fade", "news", video_types=("news",)),
    VisualTheme("Heritage Gold", "#FFD700", "#3D2200", "#140B00", "#FFD700", "fade", "cinematic", video_types=("knowledge",)),
    VisualTheme("Deep Tech", "#00F0FF", "#2A0A5E", "#050510", "#00F0FF", "slideleft", "tech", video_types=("knowledge",)),
    VisualTheme("Vibrant India", "#FF9933", "#0B6623", "#0F172A", "#FFD60A", "smoothleft", "inspiring", video_types=("knowledge",)),
    VisualTheme("Royal Story", "#C77DFF", "#240046", "#10002B", "#FFD60A", "fade", "cinematic", video_types=("knowledge",)),
]


class CreativeVariationEngine:
    def __init__(self, history: Optional[List[str]] = None):
        self.history = list(history or [])

    def get_next_theme(self, video_type: str = "news") -> VisualTheme:
        pool = [t for t in PRESET_THEMES if video_type in t.video_types] or PRESET_THEMES
        available = [t for t in pool if t.name not in self.history[-2:]] or pool
        selected = random.choice(available)
        self.history.append(selected.name)
        return selected


def hex_to_rgb(value: str) -> tuple:
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
