"""Broadcast Visual Effects (VFX) & Sound Design Engine.

Coordinates:
- Cinematic FFmpeg video filters (whip pan, punch-in, white flash, film vignette)
- Professional TV News color grading curves
- Synchronized Sound Design (whooshes on cuts, camera shutter on photos, impact hits)
- Dynamic camera motion algorithms
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger("video.vfx")

ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = ROOT / "data" / "sfx"

VFX_COLOR_GRADES = {
    "broadcast_crisp": "eq=contrast=1.12:saturation=1.20:brightness=0.02,unsharp=5:5:0.8:5:5:0.4",
    "vivid_news": "eq=contrast=1.15:saturation=1.25,unsharp=5:5:0.9",
    "cinematic_warm": "colorbalance=rs=0.06:gs=0.02:bs=-0.04,eq=contrast=1.08:saturation=1.10",
    "punchy_hdr": "eq=contrast=1.18:saturation=1.22:brightness=0.01,unsharp=7:7:1.0",
}


class VFXEngine:
    """Orchestrates cinematic visual effects, motion curves, and sound design."""

    def __init__(self, color_grade: str = "broadcast_crisp"):
        self.color_grade = color_grade
        self._ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self._ensure_sound_effects()

    def _ensure_sound_effects(self) -> Dict[str, str]:
        """Synthesize zero-dependency broadcast SFX using ffmpeg lavfi."""
        SFX_DIR.mkdir(parents=True, exist_ok=True)
        specs = {
            "whoosh_fast": "anoisesrc=d=0.35:c=pink:a=0.9,highpass=f=600,lowpass=f=8000,afade=t=in:d=0.12:curve=exp,afade=t=out:st=0.12:d=0.23:curve=log,volume=0.65",
            "shutter_click": "sine=f=1200:d=0.05,afade=t=out:st=0:d=0.05:curve=exp,volume=0.4",
            "impact_hit": "sine=f=65:d=0.45,afade=t=out:st=0:d=0.45:curve=exp,volume=1.0",
            "news_beep": "sine=f=800:d=0.08,afade=t=out:st=0:d=0.08:curve=exp,volume=0.3",
        }
        paths = {}
        for name, flt in specs.items():
            path = SFX_DIR / f"{name}.wav"
            if not path.exists():
                try:
                    subprocess.run(
                        [
                            self._ffmpeg,
                            "-y",
                            "-f",
                            "lavfi",
                            "-i",
                            flt,
                            "-ar",
                            "44100",
                            "-ac",
                            "2",
                            str(path),
                        ],
                        capture_output=True,
                        timeout=30,
                    )
                except Exception as e:
                    logger.debug("SFX synthesis skipped: %s", e)
            paths[name] = str(path)
        return paths

    def get_color_filter(self) -> str:
        """Return the FFmpeg video filter for the selected color grade."""
        grade = VFX_COLOR_GRADES.get(self.color_grade, VFX_COLOR_GRADES["broadcast_crisp"])
        vignette = "vignette=PI/5"
        return f"{grade},{vignette}"

    def get_transition_effect(self, fx_type: str = "whip") -> str:
        """Return transition filter string."""
        effects = {
            "whip": ",gblur=sigma=40:steps=2:enable='lt(t,0.14)'",
            "flash": ",fade=t=in:st=0:d=0.10:color=white",
            "punch": ",fade=t=in:st=0:d=0.08:color=white",
            "glitch": ",rgbashift=rh=-24:bh=24:gv=8:enable='lt(t,0.18)',fade=t=in:st=0:d=0.06:color=white",
            "light_leak": ",eq=brightness=0.30:saturation=1.35:enable='lt(t,0.16)'",
        }
        return effects.get(fx_type, effects["flash"])

    def get_camera_motion(
        self, idx: int, total_frames: int, zmax: float = 1.15
    ) -> Tuple[str, str, str]:
        """Compute smooth Ken Burns camera motion expressions."""
        inc = (zmax - 1.0) / max(total_frames, 1)
        mode = idx % 3
        if mode == 0:  # Smooth Push-in
            return f"min(1+{inc:.6f}*on,{zmax})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif mode == 1:  # Smooth Pull-out
            return f"max({zmax}-{inc:.6f}*on,1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        else:  # Subtle Pan
            return f"{zmax:.2f}", f"(iw-iw/zoom)*on/{total_frames}", "ih/2-(ih/zoom/2)"
