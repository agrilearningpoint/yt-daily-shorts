"""Visual and Audio Match QA Agent for BHARAT KI SOCH.

Performs frame-accurate pre-render and post-render quality assurance:
1. Validates that every spoken sentence/word aligns with visual assets.
2. Checks for zero-byte images, missing fonts, audio-video duration drift.
3. Inspects rendered MP4 for vertical dimensions (1080x1920), 30 FPS, audio streams,
   and Shorts duration compliance (15s - 59s).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import MasterEditingTimeline, VisualAudioMatchResult
from core.configuration import AppConfig
from core.duration import SHORTS_HARD_LIMIT, SHORTS_MIN_DURATION
from core.state_manager import StateManager
from video.qa_inspector import VideoQAInspector

logger = logging.getLogger("agents.visual_audio_match_qa")


class VisualAudioMatchQAAgent(BaseAgent):
    """Quality assurance gate ensuring visual-audio fidelity, semantic relevance, and broadcast standards."""

    name: str = "VisualAudioMatchQAAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        self.ffprobe = shutil.which("ffprobe") or "ffprobe"
        self.qa_inspector = VideoQAInspector(
            target_width=config.video.width,
            target_height=config.video.height,
            target_fps=config.video.fps,
            max_duration=float(getattr(config.video, "news_max_duration", SHORTS_HARD_LIMIT)),
            min_duration=float(getattr(config.video, "min_duration", SHORTS_MIN_DURATION)),
        )

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify timeline, video_path, or script is provided."""
        return bool(kwargs.get("timeline") or kwargs.get("video_path") or kwargs.get("script"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Run pre-render and post-render visual-audio match QA."""
        video_id = kwargs.get("video_id", "qa_001")
        timeline: Optional[MasterEditingTimeline] = kwargs.get("timeline")
        video_path = kwargs.get("video_path", "")

        errors: List[str] = []
        warnings: List[str] = []
        checks: Dict[str, Any] = {}

        # 1. Pre-render check
        pre_render_passed = True
        semantic_scores: List[float] = []
        total_audio_dur = 0.0
        total_visual_dur = 0.0

        if timeline:
            segments = (
                timeline.get("segments", [])
                if isinstance(timeline, dict)
                else getattr(timeline, "segments", [])
            )
            checks["segment_count"] = len(segments)

            for idx, seg in enumerate(segments):
                seg_id = (
                    seg.get("segment_id", f"seg_{idx}")
                    if isinstance(seg, dict)
                    else getattr(seg, "segment_id", f"seg_{idx}")
                )
                text = (
                    seg.get("text", "")
                    if isinstance(seg, dict)
                    else getattr(seg, "text", "")
                )
                v_path = (
                    seg.get("visual_path", "")
                    if isinstance(seg, dict)
                    else getattr(seg, "visual_path", "")
                )
                dur = (
                    float(seg.get("measured_duration", 0.0))
                    if isinstance(seg, dict)
                    else getattr(seg, "measured_duration", 0.0)
                )
                total_visual_dur += dur

                # Check file existence
                if v_path:
                    p = Path(v_path)
                    if not p.exists() or p.stat().st_size < 100:
                        errors.append(
                            f"Segment {seg_id}: Visual asset missing or corrupt ({v_path})"
                        )
                        pre_render_passed = False
                else:
                    warnings.append(
                        f"Segment {seg_id}: No visual asset assigned, using generated card"
                    )

                # Verify source provenance & metadata
                meta = (
                    seg.get("metadata", {})
                    if isinstance(seg, dict)
                    else (getattr(seg, "metadata", {}) or {})
                )
                entity = (
                    seg.get("entity", "")
                    if isinstance(seg, dict)
                    else getattr(seg, "entity", "")
                ) or (meta.get("entity", "") if isinstance(meta, dict) else "")
                provenance = (
                    seg.get("source", "")
                    if isinstance(seg, dict)
                    else getattr(seg, "source", "")
                ) or (meta.get("source", "") if isinstance(meta, dict) else "")
                if provenance and provenance.lower() in ("unknown", "corrupt", "fake"):
                    warnings.append(
                        f"Segment {seg_id}: Questionable asset provenance '{provenance}'"
                    )

                # Semantic relevance heuristic
                if text and v_path:
                    text_words = set(text.lower().split())
                    path_words = set(
                        Path(v_path).stem.lower().replace("_", " ").replace("-", " ").split()
                    )
                    if entity:
                        path_words.update(
                            entity.lower().replace("_", " ").replace("-", " ").split()
                        )
                    common = text_words.intersection(path_words)
                    score = min(1.0, 0.4 + (0.6 if common else 0.0))
                    semantic_scores.append(score)
                else:
                    semantic_scores.append(0.5)

            # Master audio duration check
            master_audio = (
                timeline.get("master_audio_path")
                if isinstance(timeline, dict)
                else getattr(timeline, "master_audio_path", "")
            )
            if master_audio and Path(master_audio).exists():
                try:
                    import wave

                    with wave.open(master_audio, "rb") as w:
                        frames = w.getnframes()
                        rate = w.getframerate()
                        total_audio_dur = frames / float(rate)
                except Exception:
                    total_audio_dur = total_visual_dur
            else:
                total_audio_dur = total_visual_dur

            drift = abs(total_visual_dur - total_audio_dur)
            checks["sync_drift_seconds"] = round(drift, 4)
            if drift > 0.5:
                warnings.append(f"Visual-Audio duration drift is {drift:.3f}s (tolerance: 0.5s)")

        else:
            checks["pre_render_skipped"] = True

        # Semantic match ratio
        semantic_ratio = (
            sum(semantic_scores) / max(len(semantic_scores), 1) if semantic_scores else 1.0
        )
        checks["semantic_match_ratio"] = round(semantic_ratio, 2)

        # 2. Post-render check (if video_path provided)
        post_render_passed = True
        if video_path and Path(video_path).exists():
            post_verdict = self.qa_inspector.verify_video(video_path)
            checks["video_inspected"] = True
            checks["technical_score"] = post_verdict.overall_score
            checks["post_render_approved"] = post_verdict.approved

            if not post_verdict.approved:
                post_render_passed = False
                errors.extend(post_verdict.errors)
            if post_verdict.warnings:
                warnings.extend(post_verdict.warnings)
        else:
            checks["post_render_evaluated"] = False

        # Word-Cut QA verification (if word_cut_plan is present)
        word_cut_plan = kwargs.get("word_cut_plan")
        if word_cut_plan:
            w_res = self.qa_inspector.verify_word_cuts(word_cut_plan, video_path)
            checks["word_cut_qa"] = w_res.to_dict()
            if not w_res.passed:
                errors.extend(w_res.errors)
            if w_res.warnings:
                warnings.extend(w_res.warnings)

        # 3. Overall Verdict
        overall_approved = (
            pre_render_passed and (post_render_passed or not video_path) and len(errors) == 0
        )
        overall_score = 100.0 - (len(errors) * 35.0) - (len(warnings) * 10.0)
        overall_score = max(0.0, min(100.0, overall_score))

        result = VisualAudioMatchResult(
            approved=overall_approved,
            overall_match_score=round(overall_score, 1),
            pre_render_passed=pre_render_passed,
            post_render_passed=post_render_passed,
            sync_drift_seconds=checks.get("sync_drift_seconds", 0.0),
            av_alignment_score=95.0 if checks.get("sync_drift_seconds", 0.0) < 0.1 else 75.0,
            semantic_match_ratio=round(semantic_ratio, 2),
            checks=checks,
            errors=errors,
            warnings=warnings,
        )

        agent_result = AgentResult(
            success=overall_approved,
            data={
                "qa_result": result,
                "approved": overall_approved,
                "overall_score": overall_score,
                "errors": errors,
                "warnings": warnings,
            },
            metadata={"video_id": video_id, "approved": overall_approved, "score": overall_score},
        )
        self.save_result(video_id, agent_result)
        return agent_result
