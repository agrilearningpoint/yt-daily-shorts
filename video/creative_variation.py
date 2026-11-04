"""Creative variation engine to rotate themes, transitions, and audio moods."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class VisualTheme:
    name: str
    primary_color: str
    secondary_color: str
    background_color: str
    transition: str
    music_mood: str
    font_name: str


PRESET_THEMES: List[VisualTheme] = [
    VisualTheme(
        name="Vibrant India Modern",
        primary_color="#FF9933",
        secondary_color="#138808",
        background_color="#0F172A",
        transition="slide_left",
        music_mood="upbeat_inspirational",
        font_name="Mukta-Bold"
    ),
    VisualTheme(
        name="Deep Investigative Tech",
        primary_color="#00F0FF",
        secondary_color="#7000FF",
        background_color="#050505",
        transition="zoom_in",
        music_mood="cyber_investigative",
        font_name="Arial-Bold"
    ),
    VisualTheme(
        name="Heritage & Historic Gold",
        primary_color="#FFD700",
        secondary_color="#B8860B",
        background_color="#1A0F00",
        transition="fade",
        music_mood="traditional_cinematic",
        font_name="Times-Bold"
    ),
    VisualTheme(
        name="Breaking News Pulse",
        primary_color="#E63946",
        secondary_color="#F1FAEE",
        background_color="#1D3557",
        transition="slide_right",
        music_mood="driving_news_beat",
        font_name="Impact"
    )
]


class CreativeVariationEngine:
    """Selects varied themes preventing repetitive visual output."""

    def __init__(self, history: List[str] = None):
        self.history = history or []

    def get_next_theme(self, video_type: str = "news") -> VisualTheme:
        available = [t for t in PRESET_THEMES if t.name not in self.history[-2:]]
        if not available:
            available = PRESET_THEMES
        selected = random.choice(available)
        self.history.append(selected.name)
        return selected
