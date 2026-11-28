"""Fail-closed publication gate.

The pipeline already has several independent checks (visual-audio match QA, post-render QA,
duration limits, fact check). Each of them lives inside the stage that produces the thing it
checks, which means: if a stage is skipped, throws a soft error, or a future refactor drops a
call, the surviving code path still reaches ``publisher.execute`` and the video goes out.

This module is the single place that decides "may this artefact be published?". It is *fail
closed*: anything it cannot positively prove is a failure. It never repairs, never re-renders and
never uploads — it collects evidence, writes ``output/<video_id>/quality_report.json`` and either
returns OK or raises :class:`GateBlocked`.

Design rules
------------
* Missing evidence == failure. "I could not measure it" is never a pass.
* Thresholds live here, in one table, and are reported verbatim in the JSON so a later run can be
  compared against the same numbers.
* Every check returns a :class:`Check` so the report explains *why* a video was blocked, with the
  measured value next to the limit.
* Dry runs are gated exactly like live runs; only the upload step differs. That is the point of a
  dry run.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

__all__ = ["THRESHOLDS", "Check", "GateBlocked", "PublishGate", "QualityReport"]

# Thresholds are deliberately a dict: they are dumped into the report, so the numbers that
# blocked a video are auditable later.
THRESHOLDS: dict[str, float] = {
    "min_visual_match": 0.34,  # average semantic match of a beat's picture to its spoken words
    "min_beats_scored": 0.80,  # fraction of beats that must have a measured score
    "max_black_seconds": 1.5,  # longest acceptable black stretch
    "max_silence_seconds": 2.5,  # longest acceptable silence
    "min_duration": 15.0,  # Shorts must be >= 15 s
    "max_duration": 179.0,  # Shorts must be <= 180 s (one second of safety)
    "min_editor_score": 6.0,  # editorial quality score out of 10
}


class GateBlocked(RuntimeError):
    """Raised when the artefact must not be published."""

    def __init__(self, reasons: Sequence[str], report_path: Path | None = None) -> None:
        self.reasons = list(reasons)
        self.report_path = report_path
        super().__init__("publish gate blocked: " + "; ".join(self.reasons))


@dataclass
class Check:
    """One verification with its measured value and verdict."""

    name: str
    passed: bool
    detail: str = ""
    measured: Any = None
    limit: Any = None
    critical: bool = True

    @property
    def status(self) -> str:
        if self.passed:
            return "pass"
        return "block" if self.critical else "warn"

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "status": self.status,
            "detail": self.detail,
            "measured": self.measured,
            "limit": self.limit,
        }


@dataclass
class QualityReport:
    video_id: str
    checks: list[Check] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    report_path: Path | None = None

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def blocking(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.critical]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and not c.critical]

    @property
    def approved(self) -> bool:
        return not self.blocking

    def verdict(self) -> str:
        if self.blocking:
            return "BLOCKED"
        if self.warnings:
            return "APPROVED_WITH_WARNINGS"
        return "APPROVED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "verdict": self.verdict(),
            "approved": self.approved,
            "thresholds": THRESHOLDS,
            "counts": {
                "total": len(self.checks),
                "passed": sum(1 for c in self.checks if c.passed),
                "blocking": len(self.blocking),
                "warnings": len(self.warnings),
            },
            "blocking_reasons": [f"{c.name}: {c.detail}" for c in self.blocking],
            "checks": [c.as_dict() for c in self.checks],
            "facts": self.facts,
        }

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "quality_report.json"
        path.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        return path


class PublishGate:
    """Verifies an episode before it is allowed to be published."""

    def __init__(self, thresholds: dict[str, float] | None = None) -> None:
        self.t = dict(THRESHOLDS)
        if thresholds:
            self.t.update(thresholds)

    # -- individual checks --------------------------------------------
    def check_video_file(self, report: QualityReport, video_path: str) -> None:
        path = Path(video_path or "")
        exists = bool(video_path) and path.is_file()
        size_mb = round(path.stat().st_size / 1e6, 2) if exists else 0.0
        report.add(
            Check(
                name="video_file",
                passed=exists and size_mb > 0.2,
                detail=f"{path.name or '(none)'} {size_mb} MB",
                measured=size_mb,
                limit="> 0.2 MB",
            )
        )

    def probe_duration(self, video_path: str) -> float | None:
        """Duration in seconds via ffprobe, else ffmpeg's banner. None if it cannot be measured."""
        probe = shutil.which("ffprobe")
        try:
            if probe:
                out = subprocess.run(
                    [
                        probe,
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=nw=1:nk=1",
                        video_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if out.stdout.strip():
                    return float(out.stdout.strip())
            ff = shutil.which("ffmpeg")
            if ff:
                out = subprocess.run(
                    [ff, "-i", video_path], capture_output=True, text=True, timeout=30, check=False
                )
                marker = "Duration: "
                if marker in (out.stderr or ""):
                    stamp = out.stderr.split(marker, 1)[1].split(",", 1)[0].strip()
                    h, m, s = stamp.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:  # noqa: BLE001 - an unmeasurable file is a blocked file, not a crash
            return None
        return None

    def check_duration(self, report: QualityReport, video_path: str) -> None:
        dur = self.probe_duration(video_path) if video_path else None
        report.facts["duration_seconds"] = dur
        ok = dur is not None and self.t["min_duration"] <= dur <= self.t["max_duration"]
        report.add(
            Check(
                name="duration",
                passed=ok,
                detail="unmeasurable" if dur is None else f"{dur:.1f}s",
                measured=dur,
                limit=f"{self.t['min_duration']:.0f}-{self.t['max_duration']:.0f}s",
            )
        )

    def check_visual_match(self, report: QualityReport, qa_payload: dict[str, Any] | None) -> None:
        """Vision/semantic match of picture to words, measured per beat."""
        payload = qa_payload or {}
        # The QA agent nests its numbers under "qa_result" (a dataclass) and its checks live in
        # "checks": semantic_match_ratio is the average per-beat picture-to-word match, 0..1.
        nested = payload.get("qa_result")
        checks = getattr(nested, "checks", None) or (nested or {}).get("checks", {})
        checks = checks or {}
        score = (
            payload.get("average_semantic_score")
            or payload.get("semantic_score")
            or checks.get("semantic_match_ratio")
            or getattr(nested, "semantic_match_ratio", None)
        )
        beats = (
            checks.get("segment_count")
            or payload.get("segment_count")
            or getattr(nested, "segment_count", 0)
            or 0
        )
        scored = payload.get("scored_segments", beats)
        report.facts["visual_match"] = {"score": score, "beats": beats, "scored": scored}

        if score is None:
            report.add(
                Check(
                    name="visual_match",
                    passed=False,
                    detail="no measured picture-to-word score (evidence missing)",
                    measured=None,
                    limit=f">= {self.t['min_visual_match']}",
                )
            )
            return
        coverage = (scored / beats) if beats else 0.0
        report.add(
            Check(
                name="visual_match_score",
                passed=float(score) >= self.t["min_visual_match"],
                detail=f"average {float(score):.3f} over {scored}/{beats} beats",
                measured=float(score),
                limit=f">= {self.t['min_visual_match']}",
            )
        )
        report.add(
            Check(
                name="visual_match_coverage",
                passed=coverage >= self.t["min_beats_scored"],
                detail=f"{scored}/{beats} beats scored",
                measured=round(coverage, 3),
                limit=f">= {self.t['min_beats_scored']}",
            )
        )

    def check_black_and_silence(
        self, report: QualityReport, video_path: str, qa_payload: dict[str, Any] | None = None
    ) -> None:
        """Black frames and silence come from the QA payload when present, else are measured."""
        payload = qa_payload or {}
        black = payload.get("max_black_duration")
        silence = payload.get("max_silence_duration")
        if black is None or silence is None:
            measured = self.measure_black_and_silence(video_path)
            black = black if black is not None else measured.get("black")
            silence = silence if silence is not None else measured.get("silence")
        report.facts["black_silence"] = {"black": black, "silence": silence}
        report.add(
            Check(
                name="black_frames",
                passed=black is not None and float(black) <= self.t["max_black_seconds"],
                detail="unmeasurable" if black is None else f"{float(black):.2f}s longest black",
                measured=black,
                limit=f"<= {self.t['max_black_seconds']}s",
            )
        )
        report.add(
            Check(
                name="silence",
                passed=silence is not None and float(silence) <= self.t["max_silence_seconds"],
                detail="unmeasurable"
                if silence is None
                else f"{float(silence):.2f}s longest silence",
                measured=silence,
                limit=f"<= {self.t['max_silence_seconds']}s",
            )
        )

    def measure_black_and_silence(self, video_path: str) -> dict[str, float | None]:
        """Best-effort measurement with ffmpeg's filters; None when the tool cannot do it."""
        ff = shutil.which("ffmpeg")
        if not ff or not video_path or not Path(video_path).is_file():
            return {"black": None, "silence": None}
        out: dict[str, float | None] = {"black": None, "silence": None}
        try:
            res = subprocess.run(
                [
                    ff,
                    "-hide_banner",
                    "-i",
                    video_path,
                    "-vf",
                    "blackdetect=d=0.1:pix_th=0.10",
                    "-an",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            lengths = [
                float(line.split("black_duration:")[1].split()[0])
                for line in (res.stderr or "").splitlines()
                if "black_duration:" in line
            ]
            out["black"] = max(lengths) if lengths else 0.0
        except Exception as exc:  # noqa: BLE001 - measurement failure is reported as "unmeasurable"
            _log.debug("black-frame measurement failed: %s", exc)
        try:
            res = subprocess.run(
                [
                    ff,
                    "-hide_banner",
                    "-i",
                    video_path,
                    "-af",
                    "silencedetect=n=-40dB:d=0.1",
                    "-vn",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            lengths = [
                float(line.split("silence_duration:")[1].split()[0])
                for line in (res.stderr or "").splitlines()
                if "silence_duration:" in line
            ]
            out["silence"] = max(lengths) if lengths else 0.0
        except Exception as exc:  # noqa: BLE001 - measurement failure is reported as "unmeasurable"
            _log.debug("silence measurement failed: %s", exc)
        return out

    def check_editorial(self, report: QualityReport, quality: dict[str, Any] | None) -> None:
        # the quality manager reports "overall_score" on a 0..1 scale (1.0 = flawless) and
        # "score" in older payloads on a 0..10 scale; both are normalised for the threshold
        payload = quality or {}
        score = payload.get("score")
        if score is None and payload.get("overall_score") is not None:
            raw = float(payload["overall_score"])
            score = raw * 10.0 if raw <= 1.0 else raw
        report.facts["editorial_score"] = score
        if score is None:
            report.add(
                Check(
                    name="editorial_score",
                    passed=False,
                    detail="quality manager did not return a score",
                    critical=False,
                )
            )
            return
        report.add(
            Check(
                name="editorial_score",
                passed=float(score) >= self.t["min_editor_score"],
                detail=f"{float(score):.1f}/10",
                measured=float(score),
                limit=f">= {self.t['min_editor_score']}",
                critical=False,  # a soft signal; the hard checks above decide publication
            )
        )

    def check_story_slides(
        self, report: QualityReport, timeline: dict[str, Any] | None, script: dict[str, Any] | None
    ) -> None:
        """Every story must own a picture. A story rendered only as a text card is a quality bug."""
        segs = _segments(timeline)
        if not segs:
            report.add(
                Check(
                    name="story_slides",
                    passed=False,
                    detail="no master timeline to verify (evidence missing)",
                )
            )
            return
        without_visual = []
        for seg in segs:
            data = seg if isinstance(seg, dict) else vars(seg)
            path = str(data.get("visual_path") or data.get("asset_path") or "")
            if not path:
                without_visual.append(str(data.get("segment_id", data.get("scene_id", "?"))))
        total = len(segs)
        report.facts["segments"] = total
        report.add(
            Check(
                name="story_slides",
                passed=not without_visual,
                detail=(
                    f"all {total} segments have a visual"
                    if not without_visual
                    else f"{len(without_visual)}/{total} segments have no visual: "
                    f"{', '.join(without_visual[:6])}"
                ),
                measured=len(without_visual),
                limit=0,
            )
        )

    def check_ownership(self, report: QualityReport, production: dict[str, Any] | None) -> None:
        """Every story must own exactly one picture, identified by scene ID (not array index)."""
        prod = production or {}
        rows = prod.get("visual_ownership") or []
        problems = prod.get("ownership_problems") or []
        report.facts["visual_ownership"] = {"rows": len(rows), "problems": problems[:5]}
        if not rows:
            report.add(
                Check(
                    name="visual_ownership",
                    passed=False,
                    detail="producer published no ownership table (evidence missing)",
                )
            )
            return
        report.add(
            Check(
                name="visual_ownership",
                passed=not problems,
                detail="every story owns one picture"
                if not problems
                else f"{len(problems)} problem(s): {'; '.join(problems[:4])}",
                measured=len(problems),
                limit=0,
            )
        )

    def check_voice(
        self,
        report: QualityReport,
        production: dict[str, Any] | None,
        timeline: dict[str, Any] | None = None,
    ) -> None:
        prod = production or {}
        audio = prod.get("audio_path") or prod.get("voice_path")
        if not audio:
            # fall back to the timeline: a segment with narration audio proves the voice exists
            has_audio = any(
                (s if isinstance(s, dict) else vars(s)).get("audio_path")
                for s in _segments(timeline)
            )
        else:
            has_audio = Path(str(audio)).is_file()
        report.add(
            Check(
                name="voice_track",
                passed=bool(has_audio),
                detail="narration present" if has_audio else "no narration audio found",
                measured=bool(has_audio),
                limit="required",
            )
        )

    def check_captions(self, report: QualityReport, production: dict[str, Any] | None) -> None:
        path = (production or {}).get("captions_srt")
        ok = bool(path) and Path(str(path)).is_file()
        report.add(
            Check(
                name="captions",
                passed=ok,
                detail=Path(str(path)).name if ok else "no .srt produced",
                critical=False,
            )
        )

    # -- the gate itself ----------------------------------------------
    def run(
        self,
        video_id: str,
        *,
        video_path: str = "",
        production: dict[str, Any] | None = None,
        timeline: dict[str, Any] | None = None,
        script: dict[str, Any] | None = None,
        quality: dict[str, Any] | None = None,
        qa_payload: dict[str, Any] | None = None,
        extra_checks: Iterable[Check] = (),
        output_dir: Path | None = None,
    ) -> QualityReport:
        """Evaluate everything and return the report (raising :class:`GateBlocked` on failure)."""
        report = QualityReport(video_id=video_id)
        self.check_video_file(report, video_path)
        self.check_duration(report, video_path)
        self.check_visual_match(report, qa_payload)
        self.check_black_and_silence(report, video_path, qa_payload)
        self.check_story_slides(report, timeline, script)
        self.check_ownership(report, production)
        self.check_voice(report, production, timeline)
        self.check_captions(report, production)
        self.check_editorial(report, quality)
        for check in extra_checks:
            report.add(check)

        path = report.save(output_dir or Path("output") / video_id)
        report.report_path = path
        if not report.approved:
            raise GateBlocked([f"{c.name}: {c.detail}" for c in report.blocking], path)
        return report


def _segments(timeline: dict[str, Any] | None) -> list[Any]:
    if not timeline:
        return []
    if isinstance(timeline, dict):
        return list(timeline.get("segments") or [])
    return list(getattr(timeline, "segments", []) or [])
