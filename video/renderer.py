"""FFmpeg renderer v3 — fast-cut news style with motion graphics.

Each beat = Ken Burns photo + white flash cut + static frame overlay +
headline chip that slides in. Beats are concatenated losslessly, then the
voice, optional ducked music and synthesized whoosh/pop SFX are mixed in.
Word-synced Hindi captions (ASS) are burned in during the final pass.
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
    fx: str = "flash"            # cut effect chosen by the Editor Director
    ticker: bool = False         # show the scrolling headline ticker on this clip
    video: str = ""              # real-motion clip used instead of the still background
    depth: bool = False          # real photo: play it with 3D depth motion (video/parallax.py)


def _run(cmd: List[str], timeout: int = 600) -> None:
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if res.returncode != 0:
        err = res.stderr.decode(errors="ignore")
        lines = [ln for ln in err.replace("\r", "\n").splitlines()
                 if ln.strip() and not ln.lstrip().startswith(("frame=", "size=")) and "time=" not in ln]
        raise RenderError("\n".join(lines[-25:])[-2000:])


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
        self.recipe: dict = {}
        self.ticker: Optional[str] = None
        self.ticker_y = 1726
        self._t0 = 0.0
        self.depth_motion = True
        self._depth_clips: dict = {}

    def _prepare_depth(self, clips: List[SceneClip], durs: List[float], work: Path) -> None:
        """Turn each real-photo beat into a short 3D-motion clip (parallel, cached across re-renders)."""
        self._depth_clips = {}
        if not self.depth_motion:
            return
        try:
            from video.parallax import make_clip
        except Exception as exc:
            logger.warning("3D photo motion unavailable: %s", exc)
            return
        jobs = []
        for i, c in enumerate(clips):
            if c.depth and not c.video and Path(c.background).exists():
                st = Path(c.background).stat()
                key = f"{Path(c.background).stem}_{int(st.st_mtime)}_{st.st_size}_{durs[i]:.2f}_{i % 6}"
                jobs.append((i, c.background, str(work / f"depth_{key}.mp4"), durs[i]))
        if not jobs:
            return
        import time
        from concurrent.futures import ThreadPoolExecutor
        t0 = time.time()

        def one(job):
            i, bg, out, d = job
            if Path(out).exists() and Path(out).stat().st_size > 1000:
                return i, out
            return i, make_clip(bg, out, d + 0.1, self.width, self.height, self.fps, style=i % 6)
        with ThreadPoolExecutor(max_workers=3) as ex:
            for i, out in ex.map(one, jobs):
                if out:
                    self._depth_clips[i] = out
        logger.info("3D photo motion: %d/%d real photos in %.0fs", len(self._depth_clips), len(jobs), time.time() - t0)

    def _motion(self, idx: int, frames: int) -> tuple:
        zmax = float(self.recipe.get("zoom", 1.12))
        inc = (zmax - 1.0) / frames
        style = self.recipe.get("motion", "kenburns_mix")
        if style == "kenburns_in":
            mode = 0
        elif style == "slow_push":
            mode, inc = 0, inc * 0.6
        elif style == "parallax_pan":
            mode = 2 + idx % 2
        else:
            mode = idx % 4
        if mode == 0:
            return f"min(1+{inc:.6f}*on,{zmax})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        if mode == 1:
            return f"max({zmax}-{inc:.6f}*on,1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        if mode == 2:
            return f"{zmax:.2f}", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
        return f"{zmax:.2f}", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{frames})"

    def _fx(self, fx: str) -> str:
        col = self.recipe.get("flash_color", "white")
        col = col.replace("#", "0x")
        return {
            "flash": f",fade=t=in:st=0:d=0.14:color={col}",
            "dip": ",fade=t=in:st=0:d=0.2:color=black",
            "glitch": ",rgbashift=rh=-26:bh=26:gv=8:enable='lt(t,0.2)',fade=t=in:st=0:d=0.06:color=white",
            "whip": ",gblur=sigma=45:steps=2:enable='lt(t,0.13)'",
            "light": ",eq=brightness=0.28:saturation=1.3:enable='lt(t,0.16)'",
            "punch": f",fade=t=in:st=0:d=0.08:color={col}",
            "cut": "",
        }.get(fx, ",fade=t=in:st=0:d=0.12:color=white")

    def _beat_clip(self, clip: SceneClip, length: float, idx: int, out: str) -> str:
        frames = max(int(round(length * self.fps)), 2)
        z, x, y = self._motion(idx, frames)
        if clip.fx == "punch":  # quick zoom-punch into the new picture
            z = f"({z})+0.22*max(0,1-on/7)"
        grade = ""
        try:
            from video.editor_director import GRADES
            g = GRADES.get(self.recipe.get("grade", ""), "")
            grade = f",{g}" if g else ""
        except Exception:
            pass
        vig = ",vignette=PI/5" if self.recipe.get("vignette") else ""
        depth_clip = self._depth_clips.get(idx)
        if depth_clip and not clip.video:
            inputs = ["-i", depth_clip, "-i", clip.overlay]
            fc = f"[0:v]fps={self.fps},setsar=1{grade}{vig}{self._fx(clip.fx)}[bg]"
        elif clip.video and Path(clip.video).exists():
            W, H = self.width, self.height
            inputs = ["-stream_loop", "-1", "-ss", "0.5", "-i", clip.video, "-i", clip.overlay]
            fc = (f"[0:v]fps={self.fps},split[va][vb];"
                  f"[va]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2[vbg];"
                  f"[vb]scale={W}:{H}:force_original_aspect_ratio=decrease[vfg];"
                  f"[vbg][vfg]overlay=(W-w)/2:(H-h)/2,setsar=1{grade}{vig}{self._fx(clip.fx)}[bg]")
        else:
            inputs = ["-i", clip.background, "-i", clip.overlay]
            fc = (f"[0:v]scale={int(self.width * 1.5)}:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
                  f"s={self.width}x{self.height}:fps={self.fps},setsar=1{grade}{vig}{self._fx(clip.fx)}[bg]")
        last = "[bg]"
        n = 2
        if clip.ticker and self.ticker and Path(self.ticker).exists():
            inputs += ["-loop", "1", "-i", self.ticker]
            speed = 170
            fc += (f";{last}drawbox=x=0:y={self.ticker_y}:w=iw:h=84:color=0x0C0C12@0.88:t=fill[tb]")
            last = "[tb]"
            fc += (f";[{n}:v]format=rgba[tk];{last}[tk]overlay="
                   f"x='W-mod((t+{self._t0:.3f})*{speed},w+W)':y={self.ticker_y}:shortest=1[t1]")
            last, n = "[t1]", n + 1
        fc += f";{last}[1:v]overlay=0:0[f]"
        last = "[f]"
        if clip.chip and Path(clip.chip).exists():
            inputs += ["-loop", "1", "-i", clip.chip]
            fc += (f";[{n}:v]format=rgba[chip];{last}[chip]overlay="
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
               music_volume: float = 0.10, tempo: float = 1.0, sfx: bool = True,
               captions: Optional[str] = None, **_ignored) -> str:
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
        self._prepare_depth(clips, durs, work)
        paths = []
        self._t0 = 0.0
        for i, c in enumerate(clips):
            paths.append(self._beat_clip(c, durs[i], i, str(work / f"clip_{i:03d}.mp4")))
            self._t0 += durs[i]
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
                    fc.append(f"[w{k}]adelay={wd}|{wd},volume=0.32[wd{k}]")
                    fc.append(f"[p{k}]adelay={pd}|{pd},volume=0.22[pd{k}]")
                fc.append("".join(f"[wd{k}][pd{k}]" for k in range(n))
                          + f"amix=inputs={2 * n}:normalize=0:duration=longest[fxcuts]")
                mix.append("[fxcuts]")
            fc.append(f"[{h_i}:a]volume=0.8[hit]")
            mix.append("[hit]")
        if len(mix) == 1:
            fc.append(f"[voice]loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,afade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6[aout]")
        else:
            fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,"
                      f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,afade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6[aout]")

        vmap, vcodec = ["-map", "0:v"], ["-c:v", "copy"]
        if captions and Path(captions).exists():
            fonts = (ROOT / "assets" / "fonts").as_posix()
            cap = Path(captions).resolve().as_posix().replace(":", "\\:")
            fc.append(f"[0:v]ass='{cap}':fontsdir='{fonts}'[vcap]")
            vmap = ["-map", "[vcap]"]
            vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
        cmd = [self._ffmpeg, "-y", *inputs, "-filter_complex", ";".join(fc), *vmap, "-map", "[aout]",
               "-t", f"{total:.3f}", *vcodec, "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
               "-movflags", "+faststart", str(out)]
        logger.info("Rendering final video (%d beats, %.1fs)…", len(clips), total)
        _run(cmd, timeout=900)
        shutil.rmtree(work, ignore_errors=True)
        return str(out)
