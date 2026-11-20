"""VFX Agent — designs broadcast color grading, camera motions, and transition visual effects.

Uses semantic tone mapping (urgency, category, pace) linked to the 56 Motion Presets library.
Produces strongly validated VFXPlanItem records that feed directly into the Master Editing Timeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import VFXPlanItem
from video.motion_presets import MotionPresetCatalog
from video.vfx_engine import VFX_COLOR_GRADES, VFXEngine

logger = logging.getLogger("agents.vfx_agent")

CATEGORY_TONE_MAP = {
    # High urgency / politics / breaking news
    "breaking": {
        "fx": "punch",
        "motion": "push_in",
        "sfx": "impact_hit",
        "speed": "fast",
        "motion_preset_id": "opener_breaking_red_flash",
        "transition_preset_id": "transition_impact_flash",
    },
    "national": {
        "fx": "flash",
        "motion": "push_in",
        "sfx": "whoosh_fast",
        "speed": "fast",
        "motion_preset_id": "photo_slow_push_in",
        "transition_preset_id": "transition_light_sweep",
    },
    "politics": {
        "fx": "punch",
        "motion": "pan",
        "sfx": "impact_hit",
        "speed": "medium",
        "motion_preset_id": "photo_diagonal_pan",
        "transition_preset_id": "transition_fast_whip",
    },
    "defence": {
        "fx": "punch",
        "motion": "push_in",
        "sfx": "impact_hit",
        "speed": "fast",
        "motion_preset_id": "photo_focus_crop",
        "transition_preset_id": "transition_impact_flash",
    },
    # Finance / economics / markets
    "finance": {
        "fx": "whip",
        "motion": "pan",
        "sfx": "whoosh_fast",
        "speed": "medium",
        "motion_preset_id": "data_statistics_bar",
        "transition_preset_id": "transition_fast_whip",
    },
    "market": {
        "fx": "whip",
        "motion": "pan",
        "sfx": "whoosh_fast",
        "speed": "medium",
        "motion_preset_id": "data_number_count_up",
        "transition_preset_id": "transition_diagonal_wipe",
    },
    "economy": {
        "fx": "whip",
        "motion": "pan",
        "sfx": "whoosh_fast",
        "speed": "medium",
        "motion_preset_id": "data_statistics_bar",
        "transition_preset_id": "transition_fast_whip",
    },
    # Science / technology / space
    "science": {
        "fx": "light_leak",
        "motion": "push_in",
        "sfx": "whoosh_fast",
        "speed": "medium",
        "motion_preset_id": "photo_depth_zoom",
        "transition_preset_id": "transition_light_sweep",
    },
    "technology": {
        "fx": "glitch",
        "motion": "push_in",
        "sfx": "impact_hit",
        "speed": "fast",
        "motion_preset_id": "transition_rgb_glitch",
        "transition_preset_id": "transition_rgb_glitch",
    },
    "space": {
        "fx": "light_leak",
        "motion": "pull_out",
        "sfx": "whoosh_fast",
        "speed": "slow",
        "motion_preset_id": "photo_smooth_pull_out",
        "transition_preset_id": "transition_luma_dissolve",
    },
    # Heritage / culture / facts
    "heritage": {
        "fx": "fade",
        "motion": "pull_out",
        "sfx": "whoosh_fast",
        "speed": "slow",
        "motion_preset_id": "photo_smooth_pull_out",
        "transition_preset_id": "transition_luma_dissolve",
    },
    "history": {
        "fx": "fade",
        "motion": "pull_out",
        "sfx": "whoosh_fast",
        "speed": "slow",
        "motion_preset_id": "photo_vertical_parallax",
        "transition_preset_id": "transition_luma_dissolve",
    },
    "personality": {
        "fx": "punch",
        "motion": "push_in",
        "sfx": "whoosh_fast",
        "speed": "medium",
        "motion_preset_id": "photo_focus_crop",
        "transition_preset_id": "transition_fast_whip",
    },
    "facts": {
        "fx": "glitch",
        "motion": "push_in",
        "sfx": "impact_hit",
        "speed": "fast",
        "motion_preset_id": "photo_slow_push_in",
        "transition_preset_id": "transition_rgb_glitch",
    },
}


class VFXAgent(BaseAgent):
    """Orchestrates cinematic visual effects, color grading, camera motions, and SFX cues."""

    name = "vfx_agent"

    def __init__(self, config, state_manager) -> None:
        super().__init__(config, state_manager)
        default_grade = getattr(self.config.video, "color_grade", "broadcast_crisp")
        self.engine = VFXEngine(color_grade=default_grade)
        self.preset_catalog = MotionPresetCatalog.get_instance()

    def _determine_scene_vfx(
        self,
        scene_idx: int,
        category: str,
        section: str,
        text: str,
        is_hook: bool = False,
    ) -> Dict[str, Any]:
        """Determine transition effect, motion mode, SFX, and motion preset ID based on semantic tone."""
        if is_hook:
            return {
                "fx": "punch",
                "motion": "push_in",
                "sfx": "impact_hit",
                "speed": "fast",
                "motion_preset_id": "opener_breaking_red_flash",
            }

        cat_key = (category or section or "").lower()
        matched = None
        for k, tone in CATEGORY_TONE_MAP.items():
            if k in cat_key:
                matched = tone
                break

        if not matched:
            # Analyze keywords in text
            if any(w in text for w in ["रुपये", "करोड़", "शेयर", "बाजार", "सेंसेक्स", "सोना", "RBI"]):
                matched = CATEGORY_TONE_MAP["finance"]
            elif any(w in text for w in ["इसरो", "सैटेलाइट", "मिसाइल", "आर्मी", "सेना"]):
                matched = CATEGORY_TONE_MAP["defence"]
            elif any(w in text for w in ["मंदिर", "इतिहास", "विरासत", "प्राचीन"]):
                matched = CATEGORY_TONE_MAP["heritage"]
            else:
                matched = {
                    "fx": "flash" if scene_idx % 2 == 0 else "whip",
                    "motion": "push_in" if scene_idx % 2 == 0 else "pan",
                    "sfx": "whoosh_fast",
                    "speed": "medium",
                    "motion_preset_id": "photo_slow_push_in"
                    if scene_idx % 2 == 0
                    else "photo_diagonal_pan",
                }

        return matched

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        scenes = script.get("scenes", [])
        hook = script.get("hook", "")
        creative_brief = kwargs.get("creative_brief", {}) or {}

        color_grade = creative_brief.get("color_grade") or self.engine.color_grade
        if color_grade not in VFX_COLOR_GRADES:
            color_grade = "broadcast_crisp"
        self.engine.color_grade = color_grade

        vfx_plan: List[VFXPlanItem] = []

        # 1. Opening hook VFX
        if hook:
            hook_fx = self._determine_scene_vfx(0, "बड़ी खबर", "national", hook, is_hook=True)
            vfx_plan.append(
                VFXPlanItem(
                    scene_id="scene_000_hook",
                    transition_effect=hook_fx["fx"],
                    camera_motion=hook_fx["motion"],
                    color_grade=color_grade,
                    intensity=0.85,
                    sfx_type=hook_fx["sfx"],
                    motion_preset_id=hook_fx.get("motion_preset_id", "opener_breaking_red_flash"),
                )
            )

        # 2. Scene by scene VFX plan
        for idx, sc in enumerate(scenes, 1):
            scene_id = f"scene_{idx:03d}"
            cat = sc.get("category", "")
            sec = sc.get("section", "national")
            narr = sc.get("narration", "")

            fx_spec = self._determine_scene_vfx(idx, cat, sec, narr, is_hook=False)
            vfx_plan.append(
                VFXPlanItem(
                    scene_id=scene_id,
                    transition_effect=fx_spec["fx"],
                    camera_motion=fx_spec["motion"],
                    color_grade=color_grade,
                    intensity=0.65 if fx_spec["fx"] in ("flash", "punch") else 0.0,
                    sfx_type=fx_spec["sfx"],
                    motion_preset_id=fx_spec.get("motion_preset_id", "photo_slow_push_in"),
                )
            )

        self.logger.info(
            "Generated context-aware VFX plan for %d items with grade '%s'",
            len(vfx_plan),
            color_grade,
        )

        return AgentResult(
            success=True,
            data={
                "color_grade": color_grade,
                "color_filter": self.engine.get_color_filter(),
                "vfx_plan": [vars(item) for item in vfx_plan],
                "total_items": len(vfx_plan),
            },
            errors=[],
        )
