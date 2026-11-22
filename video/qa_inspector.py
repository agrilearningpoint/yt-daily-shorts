"""Independent Post-Render Video Quality Assurance Inspector.

Performs multi-pillar technical, visual, audio, and synchronization verification
on the final rendered MP4 file before publication.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent_contracts import QualityVerificationVerdict
from core.duration import SHORTS_HARD_LIMIT, SHORTS_MIN_DURATION

logger = logging.getLogger("video.qa_inspector")


@dataclass
class MediaStreamInfo:
    has_video: bool = False
    has_audio: bool = False
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    duration: float = 0.0
    video_duration: float = 0.0
    audio_duration: float = 0.0
    file_size_bytes: int = 0


class VideoQAInspector:
    """Rigorous independent inspector verifying rendered videos against broadcast standards."""

    def __init__(
        self,
        target_width: int = 1080,
        target_height: int = 1920,
        target_fps: int = 30,
        max_duration: float = SHORTS_HARD_LIMIT,
        min_duration: float = SHORTS_MIN_DURATION,
        max_drift_tolerance: float = 0.10,
    ) -> None:
        self.target_width = target_width
        self.target_height = target_height
        self.target_fps = target_fps
        self.max_duration = max_duration
        self.min_duration = min_duration
        self.max_drift_tolerance = max_drift_tolerance
        self._ffprobe = shutil.which("ffprobe")
        self._ffmpeg = shutil.which("ffmpeg")

    def inspect_streams(self, file_path: str) -> MediaStreamInfo:
        """Extract detailed stream information using ffprobe."""
        p = Path(file_path)
        if not p.exists() or p.stat().st_size == 0:
            return MediaStreamInfo()

        info = MediaStreamInfo(file_size_bytes=p.stat().st_size)

        if not self._ffprobe:
            return info

        cmd = [
            self._ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(res.stdout or "{}")

            fmt = data.get("format", {})
            info.duration = float(fmt.get("duration", 0.0))

            for st in data.get("streams", []):
                codec_type = st.get("codec_type")
                if codec_type == "video" and not info.has_video:
                    info.has_video = True
                    info.width = int(st.get("width", 0))
                    info.height = int(st.get("height", 0))
                    info.video_codec = st.get("codec_name", "")
                    info.video_duration = float(st.get("duration", info.duration))

                    # Parse FPS (e.g. "30/1" or "29.97")
                    r_frame_rate = st.get("r_frame_rate", "30/1")
                    if "/" in r_frame_rate:
                        num, den = r_frame_rate.split("/")
                        info.fps = float(num) / float(den) if float(den) > 0 else 30.0
                    else:
                        info.fps = float(r_frame_rate or 30.0)

                elif codec_type == "audio" and not info.has_audio:
                    info.has_audio = True
                    info.audio_codec = st.get("codec_name", "")
                    info.audio_duration = float(st.get("duration", info.duration))

        except Exception as exc:
            logger.warning("ffprobe stream inspection failed: %s", exc)

        return info

    def detect_black_frames(
        self, file_path: str, max_duration_sec: float = 1.0
    ) -> List[Tuple[float, float]]:
        """Detect any black frame stretches longer than max_duration_sec."""
        if not self._ffmpeg:
            return []

        cmd = [
            self._ffmpeg,
            "-hide_banner",
            "-i",
            str(file_path),
            "-vf",
            f"blackdetect=d={max_duration_sec}:pix_th=0.10",
            "-f",
            "null",
            "-",
        ]
        black_stretches: List[Tuple[float, float]] = []
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            starts = [float(x) for x in re.findall(r"black_start: ([0-9.]+)", res.stderr)]
            ends = [float(x) for x in re.findall(r"black_end: ([0-9.]+)", res.stderr)]
            black_stretches = list(zip(starts, ends))
        except Exception as exc:
            logger.warning("blackdetect failed: %s", exc)

        return black_stretches

    def verify_video(self, file_path: str) -> QualityVerificationVerdict:
        """Run comprehensive multi-pillar QA on the rendered video file."""
        failures: List[str] = []
        warnings: List[str] = []
        pillars: Dict[str, float] = {
            "technical": 100.0,
            "visual": 100.0,
            "audio": 100.0,
            "sync": 100.0,
            "duration": 100.0,
        }

        path = Path(file_path)
        if not path.exists():
            return QualityVerificationVerdict(
                approved=False,
                overall_score=0.0,
                script_passed=True,
                voice_passed=False,
                visuals_passed=False,
                sync_passed=False,
                technical_passed=False,
                measured_duration=0.0,
                errors=[f"File not found: {file_path}"],
            )

        if path.stat().st_size < 200_000:
            failures.append(f"File size too small ({path.stat().st_size} bytes, minimum 200KB)")
            pillars["technical"] -= 50.0

        streams = self.inspect_streams(file_path)

        # 1. Technical Pillar (Resolution, Codec, Framerate)
        if not streams.has_video:
            failures.append("No video stream found in file")
            pillars["technical"] = 0.0
        else:
            if streams.width != self.target_width or streams.height != self.target_height:
                failures.append(
                    f"Resolution mismatch: got {streams.width}x{streams.height}, expected {self.target_width}x{self.target_height}"
                )
                pillars["technical"] -= 40.0

            if round(streams.fps) not in (self.target_fps, self.target_fps - 1):
                warnings.append(f"FPS deviation: got {streams.fps:.2f}, expected {self.target_fps}")
                pillars["technical"] -= 10.0

            if streams.video_codec and streams.video_codec.lower() not in ("h264", "hevc", "av1"):
                warnings.append(f"Non-standard video codec: {streams.video_codec}")
                pillars["technical"] -= 15.0

        # 2. Audio Pillar
        if not streams.has_audio:
            failures.append("No audio stream found in file")
            pillars["audio"] = 0.0
        else:
            if streams.audio_codec and streams.audio_codec.lower() not in ("aac", "mp3", "opus"):
                warnings.append(f"Non-standard audio codec: {streams.audio_codec}")
                pillars["audio"] -= 10.0

        # 3. Duration Pillar
        effective_duration = streams.duration or streams.video_duration
        if effective_duration > self.max_duration:
            failures.append(
                f"Video duration {effective_duration:.2f}s exceeds Shorts limit {self.max_duration:.2f}s"
            )
            pillars["duration"] = 0.0
        elif effective_duration < self.min_duration:
            failures.append(
                f"Video duration {effective_duration:.2f}s is below minimum {self.min_duration:.2f}s"
            )
            pillars["duration"] = 20.0

        # 4. Synchronization Pillar (Audio vs Video duration drift)
        if (
            streams.has_video
            and streams.has_audio
            and streams.video_duration > 0
            and streams.audio_duration > 0
        ):
            av_drift = abs(streams.video_duration - streams.audio_duration)
            if av_drift > self.max_drift_tolerance:
                warnings.append(
                    f"Container audio/video stream duration difference {av_drift:.3f}s exceeds tolerance {self.max_drift_tolerance}s"
                )
                pillars["sync"] -= min(40.0, av_drift * 100)

        # 5. Visual Defect Pillar (Black frame check)
        black_stretches = self.detect_black_frames(file_path, max_duration_sec=0.8)
        if black_stretches:
            warnings.append(f"Detected {len(black_stretches)} black screen stretches >= 0.8s")
            pillars["visual"] -= min(35.0, len(black_stretches) * 15.0)

        # Calculate overall score
        total_score = sum(max(0.0, s) for s in pillars.values()) / len(pillars)

        approved = len(failures) == 0 and total_score >= 60.0

        report = QualityVerificationVerdict(
            approved=approved,
            overall_score=round(total_score, 1),
            script_passed=True,
            voice_passed=streams.has_audio,
            visuals_passed=streams.has_video and not bool(black_stretches),
            sync_passed=pillars["sync"] >= 70.0,
            technical_passed=pillars["technical"] >= 70.0,
            measured_duration=round(effective_duration, 2),
            errors=failures,
            warnings=warnings,
        )
        return report

    def auto_repair_video(self, file_path: str, max_duration: float = 59.5) -> Optional[str]:
        """Automatically repair duration overflow or container timestamps via ffmpeg copy/re-encode."""
        if not self._ffmpeg:
            return None

        p = Path(file_path)
        if not p.exists():
            return None

        streams = self.inspect_streams(file_path)
        if streams.duration <= max_duration:
            return file_path

        logger.info(
            "Auto-repairing video duration from %.2fs to %.2fs", streams.duration, max_duration
        )
        repaired_path = str(p.parent / f"repaired_{p.name}")

        cmd = [
            self._ffmpeg,
            "-y",
            "-ss",
            "0",
            "-t",
            str(max_duration),
            "-i",
            str(file_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            repaired_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=120)
            if res.returncode == 0 and Path(repaired_path).exists():
                shutil.move(repaired_path, file_path)
                logger.info("Auto-repair successfully normalized video to %.2fs", max_duration)
                return file_path
        except Exception as exc:
            logger.warning("Auto-repair failed: %s", exc)

        return None

    def verify_word_cuts(
        self, plan: Any, video_path: Optional[str] = None, auto_repair: bool = True
    ) -> Any:
        """Validate smart word-level visual cuts for coverage, monotonicity, and drift."""
        from video.word_cut_qa import validate_word_cuts

        return validate_word_cuts(plan, video_path, auto_repair=auto_repair)

