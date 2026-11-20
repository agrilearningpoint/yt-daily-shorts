"""Data models for Motion Presets in BHARAT KI SOCH video pipeline.

Provides typed definitions for 56 distinct broadcast-grade motion presets, keyframe
animations, easing curves, and category registries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List


class EasingType(str, Enum):
    """Animation interpolation curves."""

    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    EXPONENTIAL_OUT = "exponential_out"
    SPRING = "spring"
    ELASTIC = "elastic"


class PresetCategory(str, Enum):
    """Broad categories for motion presets."""

    OPENER = "opener"
    HEADLINE_REVEAL = "headline_reveal"
    PHOTO_MOTION = "photo_motion"
    VIDEO_REFRAME = "video_reframe"
    DATA_GRAPHICS = "data_graphics"
    TRANSITION = "transition"
    BRAND_OUTRO = "brand_outro"


@dataclass
class KeyframeAnimation:
    """Individual keyframe state within a motion preset."""

    time_offset: float = 0.0  # Seconds from preset start
    scale_x: float = 1.0  # Horizontal scale factor (1.0 = 100%)
    scale_y: float = 1.0  # Vertical scale factor
    pos_x: float = 0.0  # X offset in pixels or normalized 0..1
    pos_y: float = 0.0  # Y offset in pixels or normalized 0..1
    opacity: float = 1.0  # Alpha (0.0 to 1.0)
    rotation: float = 0.0  # Rotation in degrees
    easing: EasingType = EasingType.EASE_OUT

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["easing"] = self.easing.value
        return d


@dataclass
class MotionPresetSpec:
    """Complete specification for a single motion preset."""

    preset_id: str
    name: str
    category: PresetCategory
    description: str
    duration_min: float
    duration_default: float
    duration_max: float
    ffmpeg_filter_template: str
    keyframes: List[KeyframeAnimation] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    render_type: str = "ffmpeg"  # "ffmpeg", "pil_overlay", or "hybrid"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "duration_min": self.duration_min,
            "duration_default": self.duration_default,
            "duration_max": self.duration_max,
            "ffmpeg_filter_template": self.ffmpeg_filter_template,
            "keyframes": [kf.to_dict() for kf in self.keyframes],
            "parameters": self.parameters,
            "tags": self.tags,
            "render_type": self.render_type,
        }
