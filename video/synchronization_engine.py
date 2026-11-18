"""Precision Audio-Video Synchronization Engine for YouTube Shorts.

Ensures frame-accurate alignment between spoken Hindi narration, on-screen visuals,
karaoke captions, and motion-graphics overlays. Eliminates narration-to-visual drift.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent_contracts import MasterEditingTimeline, TimelineSegmentContract

logger = logging.getLogger("video.synchronization_engine")


class SyncError(RuntimeError):
    """Raised when timeline validation or synchronization fails strict QA."""
    pass


@dataclass
class SyncValidationResult:
    is_valid: bool
    total_audio_duration: float
    total_visual_duration: float
    drift_seconds: float
    segment_count: int
    missing_visuals: List[str] = field(default_factory=list)
    boundary_mismatches: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SynchronizationEngine:
    """Manages segment-level audio-visual synchronization, drift prevention, and QA."""

    def __init__(self, fps: int = 30, max_drift_tolerance: float = 0.05) -> None:
        self.fps = fps
        self.max_drift_tolerance = max_drift_tolerance

    def build_timeline(
        self,
        beats: List[Dict[str, Any]],
        durations: List[float],
        seg_owner: List[Tuple[int, int]],
        assets: Dict[Tuple[int, int], Any],
        fps: Optional[int] = None,
        tail: float = 0.0,
    ) -> MasterEditingTimeline:
        """Construct a validated master editing timeline with stable IDs and exact boundaries.

        Args:
            beats: List of beat dictionaries (kind, text, parts, chip, etc.)
            durations: Measured audio duration per spoken segment (from TTS)
            seg_owner: Mapping from duration index to (beat_idx, part_idx)
            assets: Sourced visual assets mapped by (beat_idx, part_idx)
            fps: Frame rate (defaults to self.fps)
            tail: Padding tail added to the last segment (e.g. 0.3-0.5s for clean audio decay)
        """
        framerate = fps or self.fps
        if len(durations) != len(seg_owner):
            raise SyncError(
                f"Duration count ({len(durations)}) does not match segment owner count ({len(seg_owner)})"
            )

        # 1. Quantize durations to integer frame boundaries to prevent cumulative rounding drift
        raw_durations = list(durations)
        if raw_durations and tail > 0:
            raw_durations[-1] = max(0.2, raw_durations[-1] + tail)

        quantized_durs: List[float] = []
        cum_target = 0.0
        cur_frame = 0
        for d in raw_durations:
            cum_target += max(d, 2.0 / framerate)
            end_frame = max(cur_frame + 2, int(round(cum_target * framerate)))
            n_frames = end_frame - cur_frame
            quantized_durs.append(n_frames / framerate)
            cur_frame = end_frame

        # 2. Build TimelineSegmentContract for every spoken beat/part
        segments: List[TimelineSegmentContract] = []
        cur_time = 0.0

        for seg_idx, ((b_idx, p_idx), q_dur) in enumerate(zip(seg_owner, quantized_durs)):
            beat = beats[b_idx] if b_idx < len(beats) else {}
            parts = beat.get("parts") or []
            part = parts[p_idx] if p_idx < len(parts) else {}

            spoken_text = part.get("say", "") or beat.get("text", "")
            scene_id = f"scene_{b_idx:03d}"
            segment_id = f"{scene_id}_part_{p_idx:03d}"
            visual_id = f"vis_{b_idx:03d}_{p_idx:03d}"

            start_t = round(cur_time, 3)
            end_t = round(cur_time + q_dur, 3)

            asset = assets.get((b_idx, p_idx))
            visual_path = getattr(asset, "path", "") if asset else ""

            # Check if this is the start of a story/item
            story_start = (p_idx == 0)

            # Determine transition effect
            kind = beat.get("kind", "item")
            if kind in ("section", "outro"):
                fx = "dip"
            elif p_idx == 0:
                fx = "punch" if b_idx == 0 else "flash"
            else:
                fx = "cut"

            seg = TimelineSegmentContract(
                scene_id=scene_id,
                segment_id=segment_id,
                text=spoken_text,
                audio_path="",
                audio_start=start_t,
                audio_end=end_t,
                measured_duration=round(q_dur, 3),
                visual_id=visual_id,
                visual_path=visual_path,
                visual_start=start_t,
                visual_end=end_t,
                visual_source=getattr(asset, "source", "unknown") if asset else "none",
                transition_effect=fx,
                camera_motion="push_in" if p_idx == 0 else "pan",
            )
            segments.append(seg)
            cur_time += q_dur

        total_dur = round(cur_time, 3)
        timeline = MasterEditingTimeline(
            video_id="master_timeline",
            total_duration=total_dur,
            segments=segments,
            master_audio_path="",
        )
        return timeline

    def verify_sync(self, timeline: MasterEditingTimeline) -> SyncValidationResult:
        """Run strict multi-point synchronization QA on the timeline."""
        errors: List[str] = []
        warnings: List[str] = []
        missing_visuals: List[str] = []
        boundary_mismatches: List[str] = []

        if not timeline.segments:
            return SyncValidationResult(
                is_valid=False,
                total_audio_duration=0.0,
                total_visual_duration=0.0,
                drift_seconds=0.0,
                segment_count=0,
                errors=["Timeline has zero segments"],
            )

        total_audio = 0.0
        total_visual = 0.0
        prev_end = 0.0

        for i, seg in enumerate(timeline.segments):
            # Check visual path existence or placeholder
            if not seg.visual_path:
                missing_visuals.append(seg.segment_id)

            # Check boundary continuity
            if abs(seg.audio_start - prev_end) > 0.01:
                boundary_mismatches.append(
                    f"Gap/overlap at segment {seg.segment_id}: prev_end={prev_end}, start={seg.audio_start}"
                )

            # Check audio vs visual start/end match
            if abs(seg.audio_start - seg.visual_start) > 0.001:
                boundary_mismatches.append(
                    f"Audio/Visual start mismatch at {seg.segment_id}: audio={seg.audio_start}, vis={seg.visual_start}"
                )
            if abs(seg.audio_end - seg.visual_end) > 0.001:
                boundary_mismatches.append(
                    f"Audio/Visual end mismatch at {seg.segment_id}: audio={seg.audio_end}, vis={seg.visual_end}"
                )

            # Check caption boundary containment
            for c in seg.captions:
                if c.start < seg.audio_start - 0.05 or c.end > seg.audio_end + 0.05:
                    warnings.append(
                        f"Caption timing slightly extends beyond audio boundaries at {seg.segment_id}"
                    )

            seg_audio_dur = seg.audio_end - seg.audio_start
            seg_visual_dur = seg.visual_end - seg.visual_start
            total_audio += seg_audio_dur
            total_visual += seg_visual_dur
            prev_end = seg.audio_end

        drift = abs(total_audio - total_visual)
        if drift > self.max_drift_tolerance:
            errors.append(f"Cumulative timeline drift {drift:.4f}s exceeds limit {self.max_drift_tolerance}s")

        if missing_visuals:
            warnings.append(f"{len(missing_visuals)} segments lack dedicated visual path")

        if boundary_mismatches:
            errors.extend(boundary_mismatches)

        is_valid = len(errors) == 0

        return SyncValidationResult(
            is_valid=is_valid,
            total_audio_duration=round(total_audio, 3),
            total_visual_duration=round(total_visual, 3),
            drift_seconds=round(drift, 4),
            segment_count=len(timeline.segments),
            missing_visuals=missing_visuals,
            boundary_mismatches=boundary_mismatches,
            errors=errors,
            warnings=warnings,
        )

    def align_captions(
        self,
        timeline: MasterEditingTimeline,
        beat_words: List[List[Any]],
        tempo: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Align karaoke/subtitle word timings accurately within segment bounds."""
        aligned_words: List[Dict[str, Any]] = []

        for seg_idx, seg in enumerate(timeline.segments):
            words_for_seg = beat_words[seg_idx] if seg_idx < len(beat_words) else []
            seg_start = seg.audio_start
            seg_end = seg.audio_end
            seg_dur = seg_end - seg_start

            if words_for_seg:
                # Provider gave real word timings
                for w in words_for_seg:
                    w_text = getattr(w, "word", str(w))
                    raw_start = getattr(w, "start", 0.0) / tempo
                    raw_end = getattr(w, "end", 0.0) / tempo

                    # Constrain within segment boundary
                    bounded_start = round(max(seg_start, min(seg_end, raw_start)), 3)
                    bounded_end = round(max(bounded_start, min(seg_end, raw_end)), 3)

                    aligned_words.append({
                        "word": w_text,
                        "start": bounded_start,
                        "end": bounded_end,
                        "segment_id": seg.segment_id,
                    })
            else:
                # Fallback: distribute words across segment duration
                words = seg.text.split()
                if words and seg_dur > 0:
                    w_lens = [max(len(w), 2) for w in words]
                    total_len = sum(w_lens)
                    t_cur = seg_start
                    for w_txt, w_len in zip(words, w_lens):
                        w_dur = seg_dur * (w_len / total_len)
                        w_start = round(t_cur, 3)
                        w_end = round(t_cur + w_dur, 3)
                        aligned_words.append({
                            "word": w_txt,
                            "start": w_start,
                            "end": w_end,
                            "segment_id": seg.segment_id,
                        })
                        t_cur += w_dur

        return aligned_words
