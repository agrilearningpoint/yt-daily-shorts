"""FFmpeg renderer v3 — fast-cut news style with motion graphics.

Each beat = Ken Burns photo + white flash cut + static frame overlay +
headline chip that slides in. Beats are concatenated losslessly, then the
voice, optional ducked music and synthesized whoosh/pop SFX are mixed in.
No subtitles are burned in.
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

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"
SFX_DIR = ROOT / "data" / "sfx"
TAIL = 0.5


class RenderError(RuntimeError):
    pass


@dataclass
class SceneClip:
    background: str
    overlay: str                 # full-frame static PNG
    duration: float              # seconds of voice for this beat
    chip: Optional[str] = None   # sliding headline chip PNG
    chip_y: int = 1230
    story_start: bool = True     # whoosh/pop only when a new story/scene begins (not on every small cut)


def _run(cmd: List[str], timeout: int = 600) -> None:
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if res.returncode != 0:
        raise RenderError(res.stderr.decode(errors="ignore")[-1500:])


def ensure_sfx() -> dict:
    """Synthesize small CC0-style sound effects with ffmpeg (no downloads)."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    specs = {
        "whoosh": ("anoisesrc=d=0.42:c=pink:a=0.9,highpass=f=500,lowpass=f=7000,"
                   "afade=t=in:d=0.16:curve=exp,afade=t=out:st=0.16:d=0.26:curve=log,volume=0.55"),
        "pop": "sine=f=880:d=0.09,afade=t=out:st=0:d=0.09:curve=exp,volume=0.35",
        "hit": ("sine=f=70:d=0.35,afade=t=out:st=0:d=0.35:curve=exp,volume=0.9"),
    }
    out = {}
    for name, flt in specs.items():
        path = SFX_DIR / f"{name}.wav"
        if not path.exists():
            _run([ffmpeg, "-y", "-f", "lavfi", "-i", flt, "-ar", "44100", "-ac", "2", str(path)], 60)
        out[name] = str(path)
    return out


class VideoRenderer:
    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self._ffmpeg = shutil.which("ffmpeg")

    def _beat_clip(self, clip: SceneClip, length: float, idx: int, out: str) -> str:
        frames = max(int(round(length * self.fps)), 2)
        zmax = 1.12
        inc = (zmax - 1.0) / frames
        mode = idx % 4
        if mode == 0:
            z, x, y = f"min(1+{inc:.6f}*on,{zmax})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif mode == 1:
            z, x, y = f"max({zmax}-{inc:.6f}*on,1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif mode == 2:
            z, x, y = "1.10", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
        else:
            z, x, y = "1.10", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{frames})"
        inputs = ["-i", clip.background, "-i", clip.overlay]
        fc = (f"[0:v]scale={int(self.width * 1.5)}:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
              f"s={self.width}x{self.height}:fps={self.fps},setsar=1,"
              f"fade=t=in:st=0:d=0.12:color=white[bg];[bg][1:v]overlay=0:0[f]")
        last = "[f]"
        if clip.chip and Path(clip.chip).exists():
            inputs += ["-loop", "1", "-i", clip.chip]
            fc += (f";[2:v]format=rgba[chip];{last}[chip]overlay="
                   f"x='if(lt(t,0.28),-w+(w+60)*(t/0.28),60)':y={clip.chip_y}:shortest=1[c]")
            last = "[c]"
        fc += f";{last}format=yuv420p[v]"
        _run([self._ffmpeg, "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-t", f"{length:.3f}",
              "-r", str(self.fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", "-an", out])
        return out

    def _pick_music(self) -> Optional[str]:
        if not MUSIC_DIR.exists():
            return None
        tracks = [p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")]
        return str(random.choice(tracks)) if tracks else None

    def render(self, clips: List[SceneClip], voice_audio: str, output_path: str, music: bool = True,
               music_volume: float = 0.10, tempo: float = 1.0, sfx: bool = True, **_ignored) -> str:
        if not self._ffmpeg:
            raise RenderError("ffmpeg not installed")
        if not clips:
            raise RenderError("no scenes to render")
        out = Path(output_path)
        work = out.parent / "_clips"
        work.mkdir(parents=True, exist_ok=True)
        durs = [c.duration / tempo for c in clips]
        durs[-1] += TAIL
        # frame-accurate lengths so cuts stay in sync with the voice
        paths = [self._beat_clip(c, durs[i], i, str(work / f"clip_{i:03d}.mp4")) for i, c in enumerate(clips)]
        concat_list = work / "list.txt"
        concat_list.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in paths))
        video_only = work / "video.mp4"
        _run([self._ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(video_only)])
        total = sum(durs)

        inputs = ["-i", str(video_only), "-i", voice_audio]
        fc = []
        atempo = f",atempo={tempo:.4f}" if abs(tempo - 1.0) > 0.005 else ""
        fc.append(f"[1:a]aresample=44100{atempo},apad=pad_dur={TAIL}[voice]")
        mix = ["[voice]"]
        idx = 2
        music_path = self._pick_music() if music else None
        if music_path:
            inputs += ["-stream_loop", "-1", "-i", music_path]
            fc.append(f"[{idx}:a]aresample=44100,volume={music_volume},"
                      f"afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[bgm]")
            fc.append("[voice]asplit=2[vsc][vmix]")
            fc.append("[bgm][vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]")
            mix = ["[vmix]", "[duck]"]
            idx += 1
        if sfx:
            fx = ensure_sfx()
            inputs += ["-i", fx["whoosh"], "-i", fx["pop"], "-i", fx["hit"]]
            w_i, p_i, h_i = idx, idx + 1, idx + 2
            cut_times, t = [], 0.0
            for k, d in enumerate(durs[:-1]):
                t += d
                if clips[k + 1].story_start:
                    cut_times.append(t)
            n = len(cut_times)
            if n:
                fc.append(f"[{w_i}:a]asplit={n}" + "".join(f"[w{k}]" for k in range(n)))
                fc.append(f"[{p_i}:a]asplit={n}" + "".join(f"[p{k}]" for k in range(n)))
                for k, ct in enumerate(cut_times):
                    wd = max(int((ct - 0.18) * 1000), 0)
                    pd = int((ct + 0.22) * 1000)
                    fc.append(f"[w{k}]adelay={wd}|{wd},volume=0.55[wd{k}]")
                    fc.append(f"[p{k}]adelay={pd}|{pd},volume=0.45[pd{k}]")
                fc.append("".join(f"[wd{k}][pd{k}]" for k in range(n))
                          + f"amix=inputs={2 * n}:normalize=0:duration=longest[fxcuts]")
                mix.append("[fxcuts]")
            fc.append(f"[{h_i}:a]volume=0.8[hit]")
            mix.append("[hit]")
        if len(mix) == 1:
            fc.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
        else:
            fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,"
                      "loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

        cmd = [self._ffmpeg, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[aout]",
               "-t", f"{total:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
               "-movflags", "+faststart", str(out)]
        logger.info("Rendering final video (%d beats, %.1fs)…", len(clips), total)
        _run(cmd, timeout=900)
        shutil.rmtree(work, ignore_errors=True)
        return str(out)
