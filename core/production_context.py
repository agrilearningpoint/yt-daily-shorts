"""Centralized Production Context for the Multi-Agent YouTube Shorts Pipeline.

Maintains a single verified source of truth across all agent stages, with
dependency tracking and safe downstream cache invalidation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.agent_contracts import (
    ApprovedHook,
    ApprovedScript,
    CreativeBrief,
    FactVerificationReport,
    MasterEditingTimeline,
    MotionGraphicsPlanItem,
    ProductionArtifacts,
    QualityVerificationVerdict,
    ResearchContext,
    VFXPlanItem,
)

logger = logging.getLogger("core.production_context")

STAGE_DEPENDENCY_GRAPH: Dict[str, List[str]] = {
    "research": [
        "prompt_engineering", "script_generation", "fact_verification",
        "quality_check", "creative_direction", "vfx_direction",
        "motion_graphics", "video_production", "seo_optimization",
        "thumbnail_design", "publishing"
    ],
    "prompt_engineering": [
        "script_generation", "fact_verification", "quality_check",
        "creative_direction", "vfx_direction", "motion_graphics",
        "video_production", "seo_optimization", "thumbnail_design", "publishing"
    ],
    "script_generation": [
        "fact_verification", "quality_check", "creative_direction",
        "vfx_direction", "motion_graphics", "video_production",
        "seo_optimization", "thumbnail_design", "publishing"
    ],
    "fact_verification": [
        "quality_check", "creative_direction", "vfx_direction",
        "motion_graphics", "video_production", "seo_optimization",
        "thumbnail_design", "publishing"
    ],
    "quality_check": [
        "creative_direction", "vfx_direction", "motion_graphics",
        "video_production", "seo_optimization", "thumbnail_design", "publishing"
    ],
    "creative_direction": [
        "vfx_direction", "motion_graphics", "video_production",
        "thumbnail_design"
    ],
    "vfx_direction": ["video_production"],
    "motion_graphics": ["video_production"],
    "video_production": [
        "seo_optimization", "thumbnail_design", "publishing"
    ],
    "seo_optimization": ["publishing"],
    "thumbnail_design": ["publishing"],
    "publishing": [],
}


@dataclass
class ProductionContext:
    video_id: str
    run_id: str
    video_type: str = "news"
    topic_category: str = "Daily News Roundup"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Production Stages
    research: Optional[ResearchContext] = None
    fact_report: Optional[FactVerificationReport] = None
    creative_brief: Optional[CreativeBrief] = None
    approved_hook: Optional[ApprovedHook] = None
    approved_script: Optional[ApprovedScript] = None
    vfx_plan: List[VFXPlanItem] = field(default_factory=list)
    motion_plan: List[MotionGraphicsPlanItem] = field(default_factory=list)
    editing_timeline: Optional[MasterEditingTimeline] = None
    quality_report: Optional[QualityVerificationVerdict] = None
    artifacts: Optional[ProductionArtifacts] = None

    # Stage results dictionary for generic checkpoint persistence
    stage_data: Dict[str, Any] = field(default_factory=dict)

    def set_stage_data(self, stage: str, data: Any) -> None:
        """Record stage output and touch timestamp."""
        self.stage_data[stage] = data
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_stage_data(self, stage: str) -> Optional[Any]:
        return self.stage_data.get(stage)

    def invalidate_downstream(self, stage_name: str, state_manager=None) -> List[str]:
        """Invalidate all stages that depend on `stage_name`.

        Prevents stale audio, visuals, or VFX plans from being reused when upstream
        scripts or facts are altered or corrected.
        """
        downstream = STAGE_DEPENDENCY_GRAPH.get(stage_name, [])
        invalidated = []
        for dep in downstream:
            if dep in self.stage_data:
                del self.stage_data[dep]
                invalidated.append(dep)

            # Invalidate typed fields
            if dep in ("script_generation", "fact_verification"):
                self.approved_script = None
                self.approved_hook = None
            elif dep == "creative_direction":
                self.creative_brief = None
            elif dep == "vfx_direction":
                self.vfx_plan.clear()
            elif dep == "motion_graphics":
                self.motion_plan.clear()
            elif dep == "video_production":
                self.editing_timeline = None
                self.artifacts = None
            elif dep == "quality_check":
                self.quality_report = None

        if state_manager and invalidated:
            try:
                state_manager.invalidate_checkpoints(self.video_id, invalidated)
            except Exception as e:
                logger.debug("State manager cache invalidation error: %s", e)

        if invalidated:
            logger.info("Context [%s]: Invalidated %d downstream stages from '%s': %s",
                        self.video_id, len(invalidated), stage_name, invalidated)
        return invalidated
