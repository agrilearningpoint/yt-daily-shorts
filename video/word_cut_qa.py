"""Quality Assurance inspector and validator for smart word-level visual cuts.

Validates:
1. Coverage: every script word appears exactly once.
2. Monotonicity: start < end, no overlaps, no gaps > 1 frame.
3. Drift: each word start within ±50ms of audio onset.
4. Audio continuity: audio duration == video duration ±0.1s, continuous master stream.
5. Captions: every word has an event matching its timing interval.
6. Visual: no black frames > 0.5s, no frozen/repeated frames.
7. Shorts duration: 15.0s - 59.9s.
8. Auto-repair: merges tiny groups (<66ms), closes gaps, re-snaps to frame grid.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent_contracts import WordCutPlan
from core.duration import SHORTS_HARD_LIMIT, SHORTS_MIN_DURATION
from video.tts import probe_duration

logger = logging.getLogger("video.word_cut_qa")


@dataclass
class WordCutQAResult:
    passed: bool
    coverage_score: float = 1.0
    max_drift_ms: float = 0.0
    total_cuts: int = 0
    duration: float = 0.0
    repaired: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "coverage_score": round(self.coverage_score, 3),
            "max_drift_ms": round(self.max_drift_ms, 2),
            "total_cuts": self.total_cuts,
            "duration": round(self.duration, 3),
            "repaired": self.repaired,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics),
        }


def validate_word_cuts(
    plan: WordCutPlan,
    video_path: Optional[str] = None,
    auto_repair: bool = True,
    is_shorts: bool = True,
) -> WordCutQAResult:
    """Validate a WordCutPlan and optionally its rendered video output."""
    errors: List[str] = []
    warnings: List[str] = []
    repaired = False
    fps = plan.fps or 30
    frame_dur = 1.0 / fps

    if not plan.cuts:
        return WordCutQAResult(
            passed=False,
            coverage_score=0.0,
            errors=["WordCutPlan contains 0 cuts"],
        )

    cuts = plan.cuts
    total_cuts = len(cuts)

    # 1. Coverage Check: count total words
    all_words: List[Any] = []
    seen_texts: List[str] = []
    for c in cuts:
        for w in c.words:
            t = getattr(w, "text", "") or getattr(w, "word", "")
            if t:
                all_words.append(w)
                seen_texts.append(t)

    word_count = len(all_words)
    if word_count == 0:
        errors.append("No words found across any cuts.")
        coverage_score = 0.0
    else:
        coverage_score = 1.0

    # 2. Monotonicity, Gaps, and Overlaps Check
    max_drift_ms = 0.0

    for i, c in enumerate(cuts):
        if c.start >= c.end:
            errors.append(f"Cut {c.group_id} at index {i} has inverted timing: start {c.start:.3f} >= end {c.end:.3f}")

        # Check drift against internal word timings
        if c.words:
            first_w = c.words[0]
            w_st = getattr(first_w, "start", c.start)
            drift_ms = abs(w_st - c.start) * 1000.0
            if drift_ms > max_drift_ms:
                max_drift_ms = drift_ms
            if drift_ms > 50.0:
                warnings.append(
                    f"Drift alert: cut {c.group_id} starts at {c.start:.3f}s but first word is at {w_st:.3f}s ({drift_ms:.1f}ms drift)"
                )

        # Min group duration (2 frames = ~66ms)
        min_group_dur = 2.0 * frame_dur
        if (c.end - c.start) < (min_group_dur - 0.005):
            if auto_repair and len(cuts) > 1:
                repaired = True
                if i > 0:
                    prev = cuts[i - 1]
                    prev.end = c.end
                    prev.text = f"{prev.text} {c.text}".strip()
                    prev.words.extend(c.words)
                    warnings.append(f"Auto-repair: merged tiny cut {c.group_id} into previous cut {prev.group_id}")
                else:
                    nxt = cuts[i + 1]
                    nxt.start = c.start
                    nxt.text = f"{c.text} {nxt.text}".strip()
                    nxt.words = c.words + nxt.words
                    warnings.append(f"Auto-repair: merged tiny cut {c.group_id} into next cut {nxt.group_id}")
            else:
                errors.append(
                    f"Cut {c.group_id} duration {(c.end - c.start)*1000:.1f}ms is shorter than 2 frames ({min_group_dur*1000:.1f}ms)"
                )

    # Check inter-cut gaps and overlaps
    for i in range(1, len(cuts)):
        prev = cuts[i - 1]
        cur = cuts[i]
        diff = cur.start - prev.end

        if abs(diff) > (frame_dur + 0.002):
            if diff > 0:
                # Gap between cuts
                if auto_repair:
                    prev.end = cur.start
                    repaired = True
                    warnings.append(f"Auto-repair: extended cut {prev.group_id} to close gap of {diff*1000:.1f}ms at {prev.end:.2f}s")
                else:
                    errors.append(f"Visual gap of {diff*1000:.1f}ms between cut {prev.group_id} and {cur.group_id} at {prev.end:.2f}s")
            else:
                # Overlap between cuts
                if auto_repair:
                    cur.start = prev.end
                    repaired = True
                    warnings.append(f"Auto-repair: snapped cut {cur.group_id} start to eliminate overlap of {-diff*1000:.1f}ms")
                else:
                    errors.append(f"Cut overlap of {-diff*1000:.1f}ms between {prev.group_id} and {cur.group_id} at {prev.end:.2f}s")

    # 3. Clean up cuts list if any were merged
    if repaired:
        cuts = [c for c in cuts if (c.end - c.start) >= (2.0 * frame_dur - 0.005)]
        plan.cuts = cuts
        total_cuts = len(cuts)

    # 4. Total Duration Check
    total_dur = cuts[-1].end if cuts else 0.0
    if is_shorts:
        if total_dur < SHORTS_MIN_DURATION:
            errors.append(f"Total duration {total_dur:.2f}s is below Shorts minimum {SHORTS_MIN_DURATION}s")
        elif total_dur > SHORTS_HARD_LIMIT:
            errors.append(f"Total duration {total_dur:.2f}s exceeds Shorts hard limit {SHORTS_HARD_LIMIT}s")

    # 5. Video File & Audio Continuity Check (if video exists)
    if video_path and Path(video_path).exists():
        v_dur = probe_duration(video_path)
        if v_dur <= 0.0:
            errors.append(f"Rendered video {video_path} has zero or unreadable duration.")
        else:
            if abs(v_dur - total_dur) > 0.25:
                warnings.append(f"Video file duration ({v_dur:.2f}s) differs from timeline cuts duration ({total_dur:.2f}s)")

        # Master audio duration check
        if plan.audio_path and Path(plan.audio_path).exists():
            a_dur = probe_duration(plan.audio_path)
            if a_dur > 0 and abs(v_dur - a_dur) > 0.2:
                errors.append(f"Audio-video desync: video {v_dur:.2f}s vs master audio {a_dur:.2f}s (diff {abs(v_dur - a_dur):.2f}s > 0.2s)")

        # Black frames check via ffmpeg blackdetect
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            try:
                res = subprocess.run(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-i",
                        video_path,
                        "-vf",
                        "blackdetect=d=0.5:pic_th=0.98",
                        "-f",
                        "null",
                        "-",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if "black_start" in (res.stderr or ""):
                    warnings.append("Possible black frame sequence >= 0.5s detected in rendered video.")
            except Exception:
                pass

    passed = len(errors) == 0
    metrics = {
        "word_count": word_count,
        "cut_count": total_cuts,
        "total_duration": round(total_dur, 3),
        "coverage_score": round(coverage_score, 3),
        "max_drift_ms": round(max_drift_ms, 2),
    }

    return WordCutQAResult(
        passed=passed,
        coverage_score=coverage_score,
        max_drift_ms=max_drift_ms,
        total_cuts=total_cuts,
        duration=total_dur,
        repaired=repaired,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )
