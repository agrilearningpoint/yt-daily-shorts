"""FFmpeg renderer: Ken Burns scene clips -> xfade transitions -> burned word
captions -> voice + optional ducked background music -> 1080x1920 H.264 MP4.
"""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("video.renderer")

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
TRANSITION = 0.35
TAIL = 0.6


class RenderError(RuntimeError):
    pass


@dataclass
class SceneClip:
    background: str
    overlay: str
    duration: float  # audio duration of this segment


def _ff_escape(path: str) -> str:
    return Path(path).resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


class VideoRenderer:
    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self._ffmpeg = shutil.which("ffmpeg")

    def _run(self, cmd: List[str], timeout: int = 600) -> None:
        logger.debug("ffmpeg: %s", " ".join(cmd))
        res = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if res.returncode != 0:
            raise RenderError(res.stderr.decode(errors="ignore")[-1500:])

    # ------------------------------------------------------------------
    def _scene_clip(self, clip: SceneClip, length: float, idx: int, out: str) -> str:
        frames = max(int(round(length * self.fps)), 2)
        zmax = 1.10
        inc = (zmax - 1.0) / frames
        mode = idx % 4
        if mode == 0:      # zoom in, centre
            z, x, y = f"min(1+{inc:.6f}*on,{zmax})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif mode == 1:    # zoom out
            z, x, y = f"max({zmax}-{inc:.6f}*on,1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif mode == 2:    # slow pan right while zoomed
            z, x, y = "1.08", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
        else:              # slow pan up
            z, x, y = "1.08", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{frames})"
        vf = (f"[0:v]scale={int(self.width * 1.6)}:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
              f"s={self.width}x{self.height}:fps={self.fps},setsar=1[bg];"
              f"[bg][1:v]overlay=0:0:format=auto,format=yuv420p[v]")
        cmd = [self._ffmpeg, "-y", "-i", clip.background, "-i", clip.overlay, "-filter_complex", vf,
               "-map", "[v]", "-t", f"{length:.3f}", "-r", str(self.fps), "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out]
        self._run(cmd)
        return out

    def _pick_music(self) -> Optional[str]:
        if not MUSIC_DIR.exists():
            return None
        tracks = [p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")]
        return str(random.choice(tracks)) if tracks else None

    # ------------------------------------------------------------------
    def render(self, clips: List[SceneClip], voice_audio: str, captions_ass: Optional[str], output_path: str,
               transition: str = "fade", music: bool = True, music_volume: float = 0.10,
               tempo: float = 1.0) -> str:
        if not self._ffmpeg:
            raise RenderError("ffmpeg not installed")
        if not clips:
            raise RenderError("no scenes to render")
        out = Path(output_path)
        work = out.parent / "_clips"
        work.mkdir(parents=True, exist_ok=True)
        T = TRANSITION
        n = len(clips)
        durs = [c.duration / tempo for c in clips]

        lengths = []
        for i, d in enumerate(durs):
            if n == 1:
                lengths.append(d + TAIL)
            elif i == 0:
                lengths.append(d + T / 2)
            elif i == n - 1:
                lengths.append(d + T / 2 + TAIL)
            else:
                lengths.append(d + T)
        paths = [self._scene_clip(c, lengths[i], i, str(work / f"clip_{i:02d}.mp4")) for i, c in enumerate(clips)]
        total = sum(durs) + TAIL

        inputs: List[str] = []
        for p in paths:
            inputs += ["-i", p]
        inputs += ["-i", voice_audio]
        voice_idx = n
        music_path = self._pick_music() if music else None
        if music_path:
            inputs += ["-stream_loop", "-1", "-i", music_path]

        transitions = [transition, "slideleft", "fade", "smoothleft", "circleopen", "wipeleft"]
        fc = []
        last = "[0:v]"
        cum = 0.0
        for i in range(1, n):
            cum += durs[i - 1]
            offset = max(cum - T / 2, 0.01)
            tr = transitions[(i - 1) % len(transitions)] if i > 1 else transition
            label = f"[x{i}]"
            fc.append(f"{last}[{i}:v]xfade=transition={tr}:duration={T}:offset={offset:.3f}{label}")
            last = label
        vlabel = last
        if captions_ass and Path(captions_ass).exists():
            fc.append(f"{vlabel}subtitles='{_ff_escape(captions_ass)}':fontsdir='{_ff_escape(str(FONT_DIR))}'[vs]")
            vlabel = "[vs]"
        fc.append(f"{vlabel}format=yuv420p[vout]")

        atempo = f",atempo={tempo:.4f}" if abs(tempo - 1.0) > 0.005 else ""
        fc.append(f"[{voice_idx}:a]aresample=44100{atempo},apad=pad_dur={TAIL}[voice]")
        if music_path:
            fc.append(f"[{voice_idx + 1}:a]aresample=44100,volume={music_volume},afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[bgm]")
            fc.append("[voice]asplit=2[vsc][vmix]")
            fc.append("[bgm][vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]")
            fc.append("[duck][vmix]amix=inputs=2:duration=shortest:dropout_transition=0:normalize=0,"
                      "loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
        else:
            fc.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

        cmd = [self._ffmpeg, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
               "-t", f"{total:.3f}", "-r", str(self.fps), "-c:v", "libx264", "-preset", "medium", "-crf", "21",
               "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
               "-movflags", "+faststart", str(out)]
        logger.info("Rendering final video (%d scenes, %.1fs)…", n, total)
        self._run(cmd, timeout=900)
        shutil.rmtree(work, ignore_errors=True)
        return str(out)

    # Back-compat for old callers/tests -------------------------------------
    def render_vertical_short(self, scene_visuals: List[str], audio_path: str, output_path: str,
                              subtitle_path: Optional[str] = None, duration_per_scene: float = 18.0) -> str:
        from video.scene_composer import SceneComposer
        comp = SceneComposer()
        clips = []
        for i, v in enumerate(scene_visuals):
            ov = str(Path(output_path).parent / f"_ov_{i}.png")
            comp.compose_overlay(ov, "", "", i, len(scene_visuals))
            clips.append(SceneClip(v, ov, duration_per_scene))
        return self.render(clips, audio_path, None, output_path, music=False)
