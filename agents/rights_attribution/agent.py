"""Rights and Attribution Agent.

Assesses copyright risks, determines fair use and fair dealing compliance,
enforces maximum clip duration thresholds, generates mandatory on-screen credits,
and formats YouTube description legal notices.
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

# Known public domain or government broadcast entities in India
PUBLIC_TRUST_BROADCASTERS = [
    "sansad tv", "rajya sabha", "lok sabha", "dd news", "pib", "doordarshan",
    "isro", "drdo", "nasa", "pmo india", "press information bureau",
]


class RightsAttributionAgent(BaseAgent):
    """Enforces copyright safety, clip length limits, and attribution standards."""

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

        is_safe = rights_record.risk_level in ("low", "medium") and not rights_record.replacement_recommended

        result_data = {
            "rights_record": rights_record,
            "risk_level": rights_record.risk_level,
            "fair_use_score": rights_record.fair_use_score,
            "is_safe": is_safe,
            "on_screen_credit": rights_record.mandatory_on_screen_credit,
            "description_attribution": rights_record.description_attribution_text,
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={"video_id": video_id, "risk_level": rights_record.risk_level, "safe": is_safe},
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _evaluate_rights(
        self,
        manifest: Optional[SourceVideoManifest],
        clips: List[SelectedClip],
        script: Optional[AdaptedShortScript],
    ) -> MediaRightsRecord:
        """Assess copyright licensing, clip duration limits, and required disclaimers."""
        source_uri = manifest.source_uri if manifest else "unknown"
        author = (manifest.author if manifest else "") or (manifest.title if manifest else "")
        author_lower = author.lower()
        warnings: List[str] = []

        is_gov_or_public = any(pb in author_lower for pb in PUBLIC_TRUST_BROADCASTERS) or any(
            pb in source_uri.lower() for pb in PUBLIC_TRUST_BROADCASTERS
        )

        max_clip_dur = max((c.duration for c in clips), default=0.0)
        # Check if any scene in script exceeds 8.0s for source_clip
        if script:
            for sc in script.scenes:
                if sc.scene_type == "source_clip" and sc.duration > 8.0:
                    max_clip_dur = max(max_clip_dur, sc.duration)

        # Enforce threshold
        replacement_recommended = False
        if is_gov_or_public:
            risk_level = "low"
            fair_use_score = 0.95
            max_allowed = 12.0
            source_label = author if author else "Official Broadcast / Sansad TV / DD News"
        else:
            max_allowed = 8.0
            if max_clip_dur > 8.0:
                risk_level = "high"
                fair_use_score = 0.50
                replacement_recommended = True
                warnings.append(
                    f"Direct broadcast clip duration ({max_clip_dur:.1f}s) exceeds the safe 8.0s threshold. "
                    "Recommend replacing with Wikimedia Commons photos and animated infographics."
                )
            elif max_clip_dur > 5.0:
                risk_level = "medium"
                fair_use_score = 0.75
                warnings.append("Clip duration between 5s and 8s; maintain clear commentary and visible attribution.")
            else:
                risk_level = "low"
                fair_use_score = 0.88
            source_label = author if author else "Third-Party Media / News Broadcast"

        on_screen_credit = f"Credit / Source: {source_label}"

        disclaimer = (
            "==========================================================\n"
            "COPYRIGHT & FAIR USE DISCLAIMER:\n"
            "This video contains transformative commentary, news reporting, and educational critique.\n"
            "Under Section 107 of the US Copyright Act and Section 52 of the Indian Copyright Act 1957,\n"
            "allowance is made for 'fair use' / 'fair dealing' for purposes such as criticism, comment,\n"
            f"news reporting, teaching, scholarship, and research.\n\n"
            f"Original Footage / Source Material: {source_label}\n"
            f"Source Reference: {source_uri}\n"
            "All copyrights belong to their respective legal owners.\n"
            "=========================================================="
        )

        return MediaRightsRecord(
            source_uri=source_uri,
            source_owner=source_label,
            license_type="public_domain" if is_gov_or_public else "fair_use_commentary",
            risk_level=risk_level,
            fair_use_score=fair_use_score,
            max_clip_duration_seconds=max_allowed,
            mandatory_on_screen_credit=on_screen_credit,
            description_attribution_text=disclaimer,
            warnings=warnings,
            replacement_recommended=replacement_recommended,
        )
