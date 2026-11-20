"""Rights and Attribution Agent.

Assesses copyright risks, license statuses, and fair use/dealing considerations.
Evaluates provenance without assuming short clip duration or government ownership
automatically grants legal clearance. Flags review-required statuses and formats
mandatory attribution disclaimers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import (
    AdaptedShortScript,
    MediaRightsRecord,
    SelectedClip,
    SourceVideoManifest,
)
from core.configuration import AppConfig
from core.state_manager import StateManager


class RightsAttributionAgent(BaseAgent):
    """Enforces copyright safety, license assessment, and attribution standards."""

    name: str = "RightsAttributionAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)

    def validate_input(self, **kwargs: Any) -> bool:
        """Ensure manifest or rights_record is provided."""
        return bool(kwargs.get("manifest") or kwargs.get("rights_record") or kwargs.get("source_uri"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute copyright and fair use risk evaluation."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=["No manifest or source URI provided to RightsAttributionAgent."],
            )

        video_id = kwargs.get("video_id", "lv_rights_unk")

        # 1. Injected record
        if kwargs.get("rights_record"):
            raw_rec = kwargs["rights_record"]
            if isinstance(raw_rec, MediaRightsRecord):
                rights_record = raw_rec
            else:
                rights_record = MediaRightsRecord(**raw_rec)
        # 2. Evaluate from manifest and clips
        else:
            manifest: Optional[SourceVideoManifest] = kwargs.get("manifest")
            clips: List[SelectedClip] = kwargs.get("selected_clips", [])
            script: Optional[AdaptedShortScript] = kwargs.get("adapted_script")
            rights_record = self._evaluate_rights(manifest, clips, script)

        review_required = rights_record.risk_level in ("medium", "high") or rights_record.replacement_recommended

        result_data = {
            "rights_record": rights_record,
            "risk_level": rights_record.risk_level,
            "fair_use_score": rights_record.fair_use_score,
            "license_status": rights_record.license_type,
            "review_required": review_required,
            "on_screen_credit": rights_record.mandatory_on_screen_credit,
            "description_attribution": rights_record.description_attribution_text,
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={
                "video_id": video_id,
                "risk_level": rights_record.risk_level,
                "review_required": review_required,
            },
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _evaluate_rights(
        self,
        manifest: Optional[SourceVideoManifest],
        clips: List[SelectedClip],
        script: Optional[AdaptedShortScript],
    ) -> MediaRightsRecord:
        """Assess copyright licensing, fair dealing factors, and required disclaimers.

        NOTE: Neither short duration (e.g. <= 8s), nor government identity, nor disclaimers
        constitute automated legal immunity. All third-party broadcast footage requires
        explicit licensing review.
        """
        source_uri = manifest.source_uri if manifest else "unknown"
        author = (manifest.author if manifest else "") or (manifest.title if manifest else "Unknown Broadcaster")
        declared_license = (manifest.license if manifest else "unknown") or "unknown"
        warnings: List[str] = []

        max_clip_dur = max((c.duration for c in clips), default=0.0)
        if script:
            for sc in script.scenes:
                if sc.scene_type == "source_clip" and sc.duration > max_clip_dur:
                    max_clip_dur = sc.duration

        # Determine license status honestly
        if declared_license.lower() in ("cc0", "cc-by", "cc-by-sa", "public_domain"):
            license_type = declared_license.lower()
            fair_use_score = 0.90
            risk_level = "low"
            replacement_recommended = False
        else:
            license_type = "proprietary_broadcast_unlicensed"
            # Even under commentary / transformative news reporting, risk is not zero
            if max_clip_dur > 8.0:
                risk_level = "high"
                fair_use_score = 0.40
                replacement_recommended = True
                warnings.append(
                    f"Direct broadcast clip duration ({max_clip_dur:.1f}s) exceeds conservative news fair dealing threshold (8s). "
                    "Recommend replacing with licensed stock, Wikimedia Commons photos, or motion graphics."
                )
            elif max_clip_dur > 4.0:
                risk_level = "medium"
                fair_use_score = 0.70
                replacement_recommended = False
                warnings.append("Clip duration 4-8s; requires prominent transformative commentary and visible source attribution.")
            else:
                risk_level = "medium"  # Never 'low' for proprietary third-party commercial news
                fair_use_score = 0.75
                replacement_recommended = False

        source_label = author if author else "News Broadcast"
        on_screen_credit = f"Credit / Source: {source_label}"

        disclaimer = (
            "==========================================================\n"
            "COPYRIGHT & FAIR DEALING NOTICE:\n"
            "This video contains transformative commentary, news reporting, and educational critique.\n"
            "Reference is made to Section 52 of the Indian Copyright Act 1957 and Section 107 of the US Copyright Act.\n"
            "No copyright ownership is claimed over third-party broadcast footage or quoted material.\n\n"
            f"Source / Credit: {source_label}\n"
            f"Source Reference: {source_uri}\n"
            f"License Status: {license_type}\n"
            "All copyrights remain with their respective legal rights holders.\n"
            "=========================================================="
        )

        return MediaRightsRecord(
            source_uri=source_uri,
            source_owner=source_label,
            license_type=license_type,
            risk_level=risk_level,
            fair_use_score=fair_use_score,
            max_clip_duration_seconds=8.0,
            mandatory_on_screen_credit=on_screen_credit,
            description_attribution_text=disclaimer,
            warnings=warnings,
            replacement_recommended=replacement_recommended,
        )
