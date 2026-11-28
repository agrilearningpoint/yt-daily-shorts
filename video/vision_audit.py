"""Post-render vision audit: does the finished video actually show what the voice says?

The pipeline already had a VLM judge, but it only looked at *candidate* assets while they were
being downloaded, and only for sources it did not trust. Nothing ever looked at the finished MP4.
That is how a "2026 WORLD PRESS PHOTO" poster ended up on screen under the sentence
"आज 28 नवंबर 2026, शनिवार का दिन है" while every QA number said the video was fine: the numbers
measured duration, black frames and silence — never content.

This module samples real frames from the rendered video, pairs each with the line spoken at that
moment (from the master timeline), and asks a vision model whether the picture fits the words.
It returns a structured report the publish gate can block on:

    {"approved": bool, "checked": n, "rejected": [{"time": .., "text": .., "reason": ..}]}

Three deliberate rules, learned from the failure above:

* **Sampling is per beat, not per second** — one frame from the middle of each beat, so the audit
  covers every story instead of spending the budget on long beats.
* **Fail-open on quota, fail-closed on rejection.** A dead key returns ``checked: 0`` and is
  reported as "not measured" (the gate can decide), but a model that actually says NO is a
  blocking reason — that is a picture the model looked at.
* **The frames are saved.** ``output/<id>/vision_frames/`` keeps the exact JPEG that was judged, so
  a human can verify the verdict without re-rendering.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("video.vision_audit")

# the VLM prompt for a finished frame: stricter than the asset-sourcing one, because here the
# question is not "could this be related" but "does this illustrate THIS sentence"
FRAME_PROMPT = (
    'A Hindi news Short is on screen. The anchor is saying: "{text}"\n'
    "Look at the picture behind the text.\n"
    "Would a viewer accept this picture as illustrating that sentence? A portrait of the person "
    "named, the place named, the object named, a clearly relevant news photo, or a news-style "
    "title card naming the same subject all count as YES. A poster, logo, advertisement, calendar "
    "page, unrelated product, or a picture of a different subject counts as NO.\n"
    "Answer strictly YES or NO."
)


class VisionAuditor:
    """Samples frames from a rendered video and judges picture-vs-words."""

    def __init__(
        self,
        judge: Callable[[str, str], bool | None] | None = None,
        ffmpeg: str | None = None,
        max_frames: int = 12,
    ) -> None:
        self.judge = judge
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")
        self.max_frames = max_frames

    # -- frames -------------------------------------------------------
    def extract_frame(self, video_path: str, at_seconds: float, dest: Path) -> bool:
        """One JPEG at ``at_seconds``. Returns True when the file really exists and has bytes."""
        if not self.ffmpeg or not Path(video_path).is_file():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            res = subprocess.run(
                [
                    self.ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{max(0.0, at_seconds):.3f}",
                    "-i",
                    video_path,
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(dest),
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001 - a frame we cannot grab is reported, not raised
            logger.debug("frame extraction failed at %.2fs: %s", at_seconds, exc)
            return False
        return res.returncode == 0 and dest.is_file() and dest.stat().st_size > 1024

    # -- the audit ----------------------------------------------------
    def audit(
        self,
        video_path: str,
        timeline: dict[str, Any] | None = None,
        out_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Judge one frame per beat. Returns the report described in the module docstring."""
        report: dict[str, Any] = {
            "approved": True,
            "checked": 0,
            "rejected": [],
            "skipped": [],
            "frames_dir": str(out_dir or ""),
            "reason": "",
        }
        beats = _beats(timeline)
        if not beats:
            report["reason"] = "no timeline segments to audit"
            return report
        if self.judge is None:
            report["reason"] = "no vision model configured"
            return report
        if not self.ffmpeg or not Path(video_path).is_file():
            report["reason"] = "no video file to audit"
            return report

        frames_dir = Path(out_dir or "vision_frames")
        step = max(1, len(beats) // max(1, self.max_frames))
        sampled = beats[::step][: self.max_frames]

        for i, beat in enumerate(sampled):
            if not beat.get("visual_path"):
                # A beat with no photograph is a DESIGNED CARD (big headline over a gradient).
                # There is no picture to be wrong; judging it only produces false alarms.
                report["skipped"].append({"time": beat.get("start", 0), "why": "designed card"})
                continue
            mid = (float(beat.get("start", 0.0)) + float(beat.get("end", 0.0))) / 2.0
            dest = frames_dir / f"frame_{i:02d}_{mid:.1f}s.jpg"
            if not self.extract_frame(video_path, mid, dest):
                report["skipped"].append({"time": round(mid, 2), "why": "frame extraction failed"})
                continue
            text = str(beat.get("text") or "").strip()
            try:
                verdict = self.judge(str(dest), FRAME_PROMPT.format(text=text[:400]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("judge failed: %s", exc)
                verdict = None
            if verdict is None:
                report["skipped"].append({"time": round(mid, 2), "why": "no vision opinion"})
                continue
            report["checked"] += 1
            if verdict is False:
                report["rejected"].append(
                    {
                        "time": round(mid, 2),
                        "text": text[:120],
                        "frame": dest.name,
                    }
                )

        report["approved"] = not report["rejected"]
        if not report["checked"]:
            report["reason"] = "no frame could be judged (quota or tooling), nothing was proved"
        logger.info(
            "Vision audit: %d judged, %d rejected, %d skipped",
            report["checked"],
            len(report["rejected"]),
            len(report["skipped"]),
        )
        return report

    def audit_saved_frames(
        self, timeline: dict[str, Any] | None, frames_dir: Path
    ) -> dict[str, Any]:
        """Judge assets directly (used when a render is not available yet)."""
        report: dict[str, Any] = {"approved": True, "checked": 0, "rejected": [], "skipped": []}
        beats = _beats(timeline)
        for i, beat in enumerate(beats[: self.max_frames]):
            path = beat.get("visual_path")
            if not path or not Path(str(path)).is_file():
                report["skipped"].append({"beat": i, "why": "no visual"})
                continue
            verdict = (
                self.judge(str(path), FRAME_PROMPT.format(text=str(beat.get("text", ""))[:400]))
                if self.judge
                else None
            )
            if verdict is None:
                report["skipped"].append({"beat": i, "why": "no vision opinion"})
                continue
            report["checked"] += 1
            if verdict is False:
                report["rejected"].append({"beat": i, "text": str(beat.get("text", ""))[:120]})
        report["approved"] = not report["rejected"]
        return report


def _beats(timeline: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Segments from a MasterEditingTimeline dataclass, its dict form, or a production payload."""
    if not timeline:
        return []
    if isinstance(timeline, dict) and "segments" not in timeline:
        # someone passed the production payload: dig out the timeline inside it
        inner = timeline.get("master_timeline") or timeline.get("timeline")
        if inner:
            timeline = inner
    segs = (
        timeline.get("segments")
        if isinstance(timeline, dict)
        else getattr(timeline, "segments", None)
    )
    out: list[dict[str, Any]] = []
    for seg in segs or []:
        data = seg if isinstance(seg, dict) else vars(seg)
        out.append(
            {
                "text": data.get("text") or data.get("narration") or "",
                "start": data.get("audio_start", data.get("start", 0.0)),
                "end": data.get("audio_end", data.get("end", 0.0)),
                "visual_path": data.get("visual_path", ""),
            }
        )
    return [b for b in out if b["text"]]
