"""Motion Preset Catalog Registry for BHARAT KI SOCH.

Aggregates, indexes, and provides fast query access to all 56 distinct broadcast motion presets.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from video.motion_presets.brand_outros import BRAND_OUTRO_PRESETS
from video.motion_presets.data_graphics import DATA_GRAPHICS_PRESETS
from video.motion_presets.headline_reveals import HEADLINE_REVEAL_PRESETS
from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)
from video.motion_presets.openers import OPENER_PRESETS
from video.motion_presets.photo_motion import PHOTO_MOTION_PRESETS
from video.motion_presets.transitions import TRANSITION_PRESETS
from video.motion_presets.video_reframe import VIDEO_REFRAME_PRESETS


class MotionPresetCatalog:
    """Master registry and query engine for 56 broadcast motion presets."""

    _instance: Optional[MotionPresetCatalog] = None
    _registry: Dict[str, MotionPresetSpec] = {}

    def __init__(self) -> None:
        self._load_all()

    def _load_all(self) -> None:
        all_lists = [
            OPENER_PRESETS,
            HEADLINE_REVEAL_PRESETS,
            PHOTO_MOTION_PRESETS,
            VIDEO_REFRAME_PRESETS,
            DATA_GRAPHICS_PRESETS,
            TRANSITION_PRESETS,
            BRAND_OUTRO_PRESETS,
        ]
        self._registry.clear()
        for p_list in all_lists:
            for spec in p_list:
                if spec.preset_id in self._registry:
                    raise ValueError(f"Duplicate preset ID detected: {spec.preset_id}")
                self._registry[spec.preset_id] = spec

    @classmethod
    def get_instance(cls) -> MotionPresetCatalog:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def count(self) -> int:
        """Total count of registered motion presets."""
        return len(self._registry)

    def get(self, preset_id: str) -> Optional[MotionPresetSpec]:
        """Fetch preset specification by exact ID."""
        return self._registry.get(preset_id)

    def get_or_default(self, preset_id: str, default_id: str = "photo_slow_push_in") -> MotionPresetSpec:
        """Fetch preset specification, falling back to safe default if not found."""
        return self._registry.get(preset_id) or self._registry[default_id]

    def has(self, preset_id: str) -> bool:
        """Check if preset ID exists."""
        return preset_id in self._registry

    def list_presets(self, category: Optional[PresetCategory] = None) -> List[MotionPresetSpec]:
        """List all presets, optionally filtered by category."""
        if category is None:
            return list(self._registry.values())
        return [p for p in self._registry.values() if p.category == category]

    def find_by_tag(self, tag: str) -> List[MotionPresetSpec]:
        """Find presets containing a specific tag."""
        norm_tag = tag.lower().strip()
        return [p for p in self._registry.values() if norm_tag in [t.lower() for t in p.tags]]

    def all_presets(self) -> Dict[str, MotionPresetSpec]:
        """Return dict of all registered presets."""
        return dict(self._registry)

    def export_manifest(self) -> Dict[str, Any]:
        """Export serialized dictionary of all presets for tooling or preview."""
        return {
            "total_presets": len(self._registry),
            "categories": {
                cat.value: [p.to_dict() for p in self.list_presets(cat)]
                for cat in PresetCategory
            },
        }


# Module level singleton helpers
def get_preset(preset_id: str) -> Optional[MotionPresetSpec]:
    return MotionPresetCatalog.get_instance().get(preset_id)


def list_all_presets() -> List[MotionPresetSpec]:
    return MotionPresetCatalog.get_instance().list_presets()


def count_presets() -> int:
    return MotionPresetCatalog.get_instance().count()
