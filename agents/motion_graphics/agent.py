"""Motion Graphics Agent — designs broadcast-level graphics, overlays, and kinetic typography.

Produces structured MotionGraphicsPlanItem items and renders broadcast lower-thirds,
live breaking news chips, story progress counters, and ticker overlays integrated with
the 56 broadcast Motion Presets library.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import MotionGraphicsPlanItem
from video.motion_graphics import MotionGraphicsEngine
from video.motion_presets import MotionPresetCatalog

logger = logging.getLogger("agents.motion_graphics")


class MotionGraphicsAgent(BaseAgent):
    """Orchestrates broadcast news lower-thirds, live tickers, category badges, and story counters."""

    name = "motion_graphics"

    def __init__(self, config, state_manager) -> None:
        super().__init__(config, state_manager)
        channel = getattr(self.config.general, "channel_name", "BHARAT KI SOCH")
        self.engine = MotionGraphicsEngine(channel_name=channel)
        self.preset_catalog = MotionPresetCatalog.get_instance()

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        scenes = script.get("scenes", [])
        hook = script.get("hook", "")
        opening_brief = kwargs.get("opening_brief")
        out_dir = kwargs.get("out_dir", "output/temp")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        self.logger.info("Generating broadcast motion graphics overlays for %d scenes", len(scenes))

        motion_plan: List[MotionGraphicsPlanItem] = []
        overlays: List[str] = []
        total = len(scenes)

        # 1. Opening Hook overlay
        if hook:
            hook_overlay = f"{out_dir}/overlay_hook.png"
            self.engine.compose_broadcast_overlay(
                out_path=hook_overlay,
                headline=hook[:75],
                category="बड़ी खबर",
                story_index=0,
                total_stories=total,
                is_hook=True,
            )
            overlays.append(hook_overlay)

            # Choose opener preset (or from opening_brief if present)
            hook_preset = "opener_breaking_red_flash"
            if opening_brief and getattr(opening_brief, "motion_preset_ids", None):
                hook_preset = opening_brief.motion_preset_ids[0]

            motion_plan.append(
                MotionGraphicsPlanItem(
                    scene_id="scene_000_hook",
                    overlay_path=hook_overlay,
                    headline=hook[:75],
                    category_badge="बड़ी खबर",
                    story_counter=f"00/{total:02d}",
                    is_hook=True,
                    progress_percent=0.0,
                    motion_preset_id=hook_preset,
                )
            )

        # 2. Scene overlays
        headline_preset_cycle = [
            "headline_bottom_up",
            "headline_left_right_strap",
            "headline_double_chyron",
            "headline_masked_wipe",
        ]

        for idx, s in enumerate(scenes, 1):
            scene_id = f"scene_{idx:03d}"
            sc_overlay = f"{out_dir}/overlay_{scene_id}.png"
            headline = s.get("on_screen_text") or s.get("headline") or s.get("narration") or ""
            cat = s.get("category") or "राष्ट्रीय"

            self.engine.compose_broadcast_overlay(
                out_path=sc_overlay,
                headline=headline[:65],
                category=cat,
                story_index=idx,
                total_stories=total,
                is_hook=False,
            )
            overlays.append(sc_overlay)

            assigned_preset = headline_preset_cycle[(idx - 1) % len(headline_preset_cycle)]

            motion_plan.append(
                MotionGraphicsPlanItem(
                    scene_id=scene_id,
                    overlay_path=sc_overlay,
                    headline=headline[:65],
                    category_badge=cat,
                    story_counter=f"{idx:02d}/{total:02d}",
                    is_hook=False,
                    progress_percent=round(idx / max(total, 1), 2),
                    motion_preset_id=assigned_preset,
                )
            )

        return AgentResult(
            success=True,
            data={
                "motion_plan": [vars(item) for item in motion_plan],
                "overlays": overlays,
                "total_overlays": len(overlays),
                "ticker_preset_id": "brand_ticker_transition",
            },
            errors=[],
        )
