"""VFX Agent — designs broadcast color grading, camera motions, and transition visual effects."""

from __future__ import annotations

from typing import Any, Dict, List
from agents.base_agent import AgentResult, BaseAgent
from video.vfx_engine import VFXEngine, VFX_COLOR_GRADES


class VFXAgent(BaseAgent):
    """Orchestrates cinematic visual effects, color grading, camera motions, and SFX cues."""

    name = "vfx_agent"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        default_grade = getattr(self.config.video, "color_grade", "broadcast_crisp")
        self.engine = VFXEngine(color_grade=default_grade)

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        scenes = script.get("scenes", [])
        creative_brief = kwargs.get("creative_brief", {}) or {}
        
        color_grade = creative_brief.get("color_grade") or self.engine.color_grade
        if color_grade not in VFX_COLOR_GRADES:
            color_grade = "broadcast_crisp"
        self.engine.color_grade = color_grade

        vfx_plan: List[Dict[str, Any]] = []
        fx_sequence = ["flash", "whip", "punch", "glitch", "light_leak"]

        for idx, sc in enumerate(scenes):
            fx_type = fx_sequence[idx % len(fx_sequence)]
            vfx_plan.append({
                "scene_index": idx,
                "transition_effect": fx_type,
                "transition_filter": self.engine.get_transition_effect(fx_type),
                "motion_mode": idx % 3,  # 0: push-in, 1: pull-out, 2: pan
                "sfx": "whoosh_fast" if idx % 2 == 0 else "impact_hit",
            })

        self.logger.info("Generated VFX plan for %d scenes with color grade '%s'", len(scenes), color_grade)

        return AgentResult(
            success=True,
            data={
                "color_grade": color_grade,
                "color_filter": self.engine.get_color_filter(),
                "vfx_plan": vfx_plan,
                "total_scenes": len(scenes),
            },
            errors=[],
        )
