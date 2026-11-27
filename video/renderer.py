"""FFmpeg renderer v3 — fast-cut news style with motion graphics.

Each beat = Ken Burns photo + white flash cut + static frame overlay +
headline chip that slides in. Beats are concatenated losslessly, then the
voice, optional ducked music and synthesized whoosh/pop SFX are mixed in.
Word-synced Hindi captions (ASS) are burned in during the final pass.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.agent_contracts import WordCutPlan

logger = logging.getLogger("video.renderer")

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "assets" / "music"
SFX_DIR = ROOT / "data" / "sfx"
TAIL = 0.5


class RenderError(RuntimeError):
    pass


def quantize_durations(raw_durs: List[float], fps: int = 30, tail: float = 0.0) -> List[float]:
    """Quantize beat durations to exact integer frames with zero cumulative drift."""
    if not raw_durs:
        return []
    adjusted = list(raw_durs)
    adjusted[-1] = max(0.2, adjusted[-1] + tail)
    out: List[float] = []
    cum_target = 0.0
    cur_frame = 0
    for d in adjusted:
        cum_target += max(d, 2.0 / fps)
        end_frame = max(cur_frame + 2, int(round(cum_target * fps)))
        n_frames = end_frame - cur_frame
        out.append(n_frames / fps)
        cur_frame = end_frame
    return out


@dataclass
class SceneClip:
    background: str
    overlay: str  # full-frame static PNG
    duration: float  # seconds of voice for this beat
    chip: Optional[str] = None  # sliding headline chip PNG
    chip_y: int = 1230
    story_start: bool = (
        True  # whoosh/pop only when a new story/scene begins (not on every small cut)
    )
    fx: str = "flash"  # cut effect chosen by the Editor Director
    ticker: bool = False  # show the scrolling headline ticker on this clip
    video: str = ""  # real-motion clip used instead of the still background
    depth: bool = False  # real photo: play it with 3D depth motion (video/parallax.py)
    motion_preset_id: Optional[str] = None
    camera_motion: Optional[str] = None
    transition_effect: Optional[str] = None
    video_trim_start: float = 0.0
    video_trim_end: float = 0.0
    sfx_cue: Optional[str] = None


def _run(cmd: List[str], timeout: int = 600) -> None:
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if res.returncode != 0:
        err = res.stderr.decode(errors="ignore")
        lines = [
            ln
            for ln in err.replace("\r", "\n").splitlines()
            if ln.strip() and not ln.lstrip().startswith(("frame=", "size=")) and "time=" not in ln
        ]
        raise RenderError("\n".join(lines[-25:])[-2000:])


def ensure_sfx() -> dict:
    """Provide broadcast sound effects (bundled assets first, ffmpeg lavfi synthesis fallback)."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    bundled_sfx = ROOT / "assets" / "sfx"
    specs = {
        "whoosh": (
            "anoisesrc=d=0.42:c=pink:a=0.9,highpass=f=500,lowpass=f=7000,"
            "afade=t=in:d=0.16:curve=exp,afade=t=out:st=0.16:d=0.26:curve=log,volume=0.55"
        ),
        "pop": "sine=f=880:d=0.09,afade=t=out:st=0:d=0.09:curve=exp,volume=0.35",
        "hit": ("sine=f=70:d=0.35,afade=t=out:st=0:d=0.35:curve=exp,volume=0.9"),
        "click": "sine=f=1350:d=0.035,afade=t=out:st=0:d=0.035:curve=exp,volume=0.28",
    }
    bundled_map = {
        "whoosh": bundled_sfx / "transition_whoosh.wav",
        "pop": bundled_sfx / "headline_reveal.wav",
        "hit": bundled_sfx / "sting_news_intro.wav",
        "click": bundled_sfx / "ticker_blip.wav",
    }
    out = {}
    for name, flt in specs.items():
        b_path = bundled_map.get(name)
        if b_path and b_path.exists() and b_path.stat().st_size > 500:
            out[name] = str(b_path)
            continue
        path = SFX_DIR / f"{name}.wav"
        if not path.exists():
            _run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", flt, "-ar", "44100", "-ac", "2", str(path)], 60
            )
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
        self.ticker_y = 1605
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
        logger.info(
            "3D photo motion: %d/%d real photos in %.0fs",
            len(self._depth_clips),
            len(jobs),
            time.time() - t0,
        )

    def _motion(self, idx: int, frames: int, camera_motion: Optional[str] = None) -> tuple:
        zmax = float(self.recipe.get("zoom", 1.14))
        inc = (zmax - 1.0) / max(frames, 1)
        if camera_motion == "push_in":
            mode = 0
        elif camera_motion == "pull_out":
            mode = 1
        elif camera_motion == "pan":
            mode = 2 + (idx % 3)
        else:
            style = self.recipe.get("motion", "kenburns_mix")
            if style == "kenburns_in":
                mode = 0 if idx % 3 != 2 else 4
            elif style == "slow_push":
                mode, inc = 0, inc * 0.65
            elif style == "parallax_pan":
                mode = 2 + (idx % 3)
            else:
                mode = idx % 5
        if mode == 0:  # smooth center push-in
            return f"min(1+{inc:.6f}*on,{zmax})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        if mode == 1:  # smooth pull-out
            return f"max({zmax}-{inc:.6f}*on,1)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        if mode == 2:  # horizontal sweep L -> R
            return f"{zmax:.2f}", f"(iw-iw/zoom)*on/{max(frames, 1)}", "ih/2-(ih/zoom/2)"
        if mode == 3:  # horizontal sweep R -> L
            return f"{zmax:.2f}", f"(iw-iw/zoom)*(1-on/{max(frames, 1)})", "ih/2-(ih/zoom/2)"
        # diagonal top-left -> center sweep with zoom
        return (
            f"min(1+{inc:.6f}*on,{zmax})",
            f"(iw-iw/zoom)*on/{max(frames, 1)}",
            f"(ih-ih/zoom)*(1-on/{max(frames, 1)})",
        )

    def _fx(self, fx: str) -> str:
        col = self.recipe.get("flash_color", "white")
        col = col.replace("#", "0x")
        return {
            "flash": (
                f",fade=t=in:st=0:d=0.11:color={col},"
                f"eq=brightness='0.18*max(0,1-t/0.18)':saturation=1.18:enable='lt(t,0.18)'"
            ),
            "dip": ",fade=t=in:st=0:d=0.18:color=black",
            "glitch": ",rgbashift=rh=-26:bh=26:gv=8:enable='lt(t,0.18)',fade=t=in:st=0:d=0.06:color=white",
            "whip": ",gblur=sigma=42:steps=2:enable='lt(t,0.14)',eq=brightness=0.12:enable='lt(t,0.12)'",
            "wipe": ",gblur=sigma=24:steps=1:enable='lt(t,0.11)',eq=contrast=1.15:saturation=1.24:enable='lt(t,0.14)'",
            "light": ",eq=brightness='0.28*exp(-pow(t-0.12,2)/0.008)':saturation=1.32:enable='lt(t,0.28)'",
            "light_leak": ",eq=brightness='0.28*exp(-pow(t-0.12,2)/0.008)':saturation=1.32:enable='lt(t,0.28)'",
            "punch": (
                f",fade=t=in:st=0:d=0.08:color={col},"
                f"eq=brightness='0.22*max(0,1-t/0.16)':saturation=1.26:enable='lt(t,0.16)'"
            ),
            "fade": ",fade=t=in:st=0:d=0.14:color=black",
            "cut": "",
        }.get(fx, f",fade=t=in:st=0:d=0.10:color={col}")

    def _beat_clip(
        self, clip: SceneClip, length: float, idx: int, out: str, t0: float = 0.0
    ) -> str:
        import re as _re

        frames = max(int(round(length * self.fps)), 2)
        z, x, y = self._motion(idx, frames, camera_motion=getattr(clip, "camera_motion", None))
        cut_fx = clip.transition_effect or clip.fx
        if cut_fx == "punch":  # quick zoom-punch into the new picture
            z = f"({z})+0.22*max(0,1-on/7)"
        grade = ""
        try:
            from video.editor_director import GRADES

            raw_grade = str(self.recipe.get("grade", "") or "broadcast_crisp").strip()
            g = GRADES.get(raw_grade) or (
                raw_grade
                if ("=" in raw_grade and ("eq" in raw_grade or "colorbalance" in raw_grade))
                else GRADES.get("broadcast_crisp", "")
            )
            grade = f",{g}" if g else ""
        except Exception:
            pass
        vig = ",vignette=PI/5" if self.recipe.get("vignette", True) else ""
        preset_filter: Optional[str] = None
        if clip.motion_preset_id:
            try:
                from video.motion_presets.catalog import get_preset

                spec = get_preset(clip.motion_preset_id)
                if spec and spec.ffmpeg_filter_template:
                    preset_filter = spec.ffmpeg_filter_template.format(
                        frames=frames,
                        duration=length,
                        fps=self.fps,
                        width=self.width,
                        height=self.height,
                    )
                    # Guard against hardcoded d=1 single-frame stall or hardcoded dimensions
                    preset_filter = _re.sub(r":d=1(?=:|$)", f":d={frames}", preset_filter)
                    preset_filter = preset_filter.replace(
                        "1080x1920", f"{self.width}x{self.height}"
                    ).replace("1080:1920", f"{self.width}:{self.height}")
            except Exception as exc:
                logger.debug(
                    "Preset application skipped for %s: %s", clip.motion_preset_id, exc
                )

        depth_clip = self._depth_clips.get(idx)
        if depth_clip and not clip.video:
            inputs = ["-i", depth_clip, "-i", clip.overlay]
            extra_fx = ""
            if preset_filter and not preset_filter.startswith(("zoompan=", "overlay=", "split", "scale=")):
                extra_fx = f",{preset_filter}"
            fc = f"[0:v]fps={self.fps},setsar=1{grade}{vig}{extra_fx}{self._fx(cut_fx)}[bg]"
        elif clip.video and Path(clip.video).exists():
            W, H = self.width, self.height
            trim_ss = clip.video_trim_start if clip.video_trim_start > 0 else 0.5
            inputs = [
                "-stream_loop",
                "-1",
                "-ss",
                f"{trim_ss:.2f}",
                "-i",
                clip.video,
                "-i",
                clip.overlay,
            ]
            fc = (
                f"[0:v]fps={self.fps},split[va][vb];"
                f"[va]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2[vbg];"
                f"[vb]scale={W}:{H}:force_original_aspect_ratio=decrease[vfg];"
                f"[vbg][vfg]overlay=(W-w)/2:(H-h)/2,setsar=1{grade}{vig}{self._fx(cut_fx)}[bg]"
            )
        else:
            inputs = ["-i", clip.background, "-i", clip.overlay]
            if preset_filter:
                if preset_filter.startswith("overlay="):
                    fc = (
                        f"[0:v]scale={int(self.width * 1.5)}:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
                        f"s={self.width}x{self.height}:fps={self.fps},setsar=1{grade}{vig}{self._fx(cut_fx)}[bg]"
                    )
                elif preset_filter.startswith("zoompan="):
                    # Combine zoompan with smooth upscale headroom so output isn't blocky
                    fc = (
                        f"[0:v]scale={int(self.width * 1.5)}:-2,{preset_filter},"
                        f"setsar=1{grade}{vig}{self._fx(cut_fx)}[bg]"
                    )
                else:
                    fc = (
                        f"[0:v]scale={int(self.width * 1.5)}:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
                        f"s={self.width}x{self.height}:fps={self.fps},{preset_filter},setsar=1{grade}{vig}{self._fx(cut_fx)}[bg]"
                    )
            else:
                fc = (
                    f"[0:v]scale={int(self.width * 1.5)}:-2,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:"
                    f"s={self.width}x{self.height}:fps={self.fps},setsar=1{grade}{vig}{self._fx(cut_fx)}[bg]"
                )
        last = "[bg]"
        n = 2
        if clip.ticker and self.ticker and Path(self.ticker).exists():
            inputs += ["-loop", "1", "-i", self.ticker]
            speed = 170
            fc += f";{last}drawbox=x=0:y={self.ticker_y}:w=iw:h=84:color=0x0C0C12@0.88:t=fill[tb]"
            last = "[tb]"
            fc += (
                f";[{n}:v]format=rgba[tk];{last}[tk]overlay="
                f"x='W-mod((t+{t0:.3f})*{speed},w+W)':y={self.ticker_y}:shortest=1[t1]"
            )
            last, n = "[t1]", n + 1
        if preset_filter and preset_filter.startswith("overlay="):
            fc += f";{last}[1:v]{preset_filter}[f]"
        else:
            fc += f";{last}[1:v]overlay=0:0[f]"
        last = "[f]"
        if clip.chip and Path(clip.chip).exists():
            inputs += ["-loop", "1", "-i", clip.chip]
            fc += (
                f";[{n}:v]format=rgba[chip];{last}[chip]overlay="
                f"x='if(lt(t,0.28),-w+(w+60)*(t/0.28),60)':y={clip.chip_y}:shortest=1[c]"
            )
            last = "[c]"
        fc += f";{last}format=yuv420p[v]"
        _run(
            [
                self._ffmpeg,
                "-y",
                *inputs,
                "-filter_complex",
                fc,
                "-map",
                "[v]",
                "-t",
                f"{length:.3f}",
                "-r",
                str(self.fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-an",
                out,
            ]
        )
        return out

    def _pick_music(self) -> Optional[str]:
        if MUSIC_DIR.exists():
            tracks = [
                p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")
            ]
            if tracks:
                return str(random.choice(tracks))
        sfx_bed = ROOT / "assets" / "sfx" / "news_bed_loop.wav"
        return str(sfx_bed) if sfx_bed.exists() else None

    def render(
        self,
        clips: List[SceneClip],
        voice_audio: str,
        output_path: str,
        music: bool = True,
        music_volume: float = 0.10,
        tempo: float = 1.0,
        sfx: bool = True,
        captions: Optional[str] = None,
        **_ignored,
    ) -> str:
        if not self._ffmpeg:
            raise RenderError("ffmpeg not installed")
        if not clips:
            raise RenderError("no scenes to render")
        out = Path(output_path)
        work = out.parent / "_clips"
        work.mkdir(parents=True, exist_ok=True)
        tempo = max(0.5, min(float(tempo or 1.0), 2.0))
        durs = quantize_durations([c.duration / tempo for c in clips], fps=self.fps, tail=TAIL)
        # frame-accurate lengths so cuts stay in sync with the voice
        self._prepare_depth(clips, durs, work)
        paths = [None] * len(clips)
        t0_offsets = []
        cur_t0 = 0.0
        for d in durs:
            t0_offsets.append(cur_t0)
            cur_t0 += d

        def _render_one(idx: int) -> tuple:
            out_clip = str(work / f"clip_{idx:03d}.mp4")
            self._beat_clip(clips[idx], durs[idx], idx, out_clip, t0=t0_offsets[idx])
            return idx, out_clip

        max_workers = min(2, os.cpu_count() or 2)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for idx, p in pool.map(_render_one, range(len(clips))):
                paths[idx] = p
        concat_list = work / "list.txt"
        concat_list.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in paths))
        video_only = work / "video.mp4"
        _run(
            [
                self._ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(video_only),
            ]
        )
        total = sum(durs)

        inputs = ["-i", str(video_only), "-i", voice_audio]
        fc = []
        atempo = f",atempo={tempo:.4f}" if abs(tempo - 1.0) > 0.005 else ""
        # Broadcast anchor vocal presence chain: clean sub-85Hz rumble, warm body, crisp diction
        vocal_eq = (
            "highpass=f=85,equalizer=f=220:t=q:w=1.2:g=2.0,"
            "equalizer=f=3200:t=q:w=1.4:g=2.5,acompressor=threshold=-18dB:ratio=2.8:attack=5:release=60"
        )
        fc.append(f"[1:a]aresample=44100{atempo},{vocal_eq},apad=pad_dur={TAIL}[voice]")
        mix = ["[voice]"]
        idx = 2
        music_path = self._pick_music() if music else None
        if music_path:
            inputs += ["-stream_loop", "-1", "-i", music_path]
            fc.append(
                f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={music_volume},"
                f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[bgm]"
            )
            fc.append("[voice]asplit=2[vsc][vmix]")
            fc.append(
                "[bgm][vsc]sidechaincompress=threshold=0.02:ratio=5:attack=15:release=320[duck]"
            )
            mix = ["[vmix]", "[duck]"]
            idx += 1
        if sfx:
            fx = ensure_sfx()
            inputs += ["-i", fx["whoosh"], "-i", fx["pop"], "-i", fx["hit"], "-i", fx["click"]]
            w_i, p_i, h_i, c_i = idx, idx + 1, idx + 2, idx + 3
            cut_times, sub_cut_times, t = [], [], 0.0
            for k, d in enumerate(durs[:-1]):
                t += d
                if clips[k + 1].story_start:
                    cut_times.append(t)
                else:
                    sub_cut_times.append(t)
            n = len(cut_times)
            if n == 1:
                ct = cut_times[0]
                wd = max(int((ct - 0.16) * 1000), 0)
                pd = int((ct + 0.18) * 1000)
                fc.append(f"[{w_i}:a]adelay={wd}|{wd},volume=0.22[wd0]")
                fc.append(f"[{p_i}:a]adelay={pd}|{pd},volume=0.16[pd0]")
                fc.append("[wd0][pd0]amix=inputs=2:normalize=0:duration=longest[fxcuts]")
                mix.append("[fxcuts]")
            elif n > 1:
                fc.append(f"[{w_i}:a]asplit={n}" + "".join(f"[w{k}]" for k in range(n)))
                fc.append(f"[{p_i}:a]asplit={n}" + "".join(f"[p{k}]" for k in range(n)))
                for k, ct in enumerate(cut_times):
                    wd = max(int((ct - 0.16) * 1000), 0)
                    pd = int((ct + 0.18) * 1000)
                    fc.append(f"[w{k}]adelay={wd}|{wd},volume=0.22[wd{k}]")
                    fc.append(f"[p{k}]adelay={pd}|{pd},volume=0.16[pd{k}]")
                fc.append(
                    "".join(f"[wd{k}][pd{k}]" for k in range(n))
                    + f"amix=inputs={2 * n}:normalize=0:duration=longest[fxcuts]"
                )
                mix.append("[fxcuts]")
            m_sub = len(sub_cut_times)
            if m_sub == 1:
                cd = max(int(sub_cut_times[0] * 1000), 0)
                fc.append(f"[{c_i}:a]adelay={cd}|{cd},volume=0.12[fxsub]")
                mix.append("[fxsub]")
            elif m_sub > 1:
                fc.append(f"[{c_i}:a]asplit={m_sub}" + "".join(f"[ck{k}]" for k in range(m_sub)))
                for k, ct in enumerate(sub_cut_times):
                    cd = max(int(ct * 1000), 0)
                    fc.append(f"[ck{k}]adelay={cd}|{cd},volume=0.12[ckd{k}]")
                fc.append(
                    "".join(f"[ckd{k}]" for k in range(m_sub))
                    + f"amix=inputs={m_sub}:normalize=0:duration=longest[fxsub]"
                )
                mix.append("[fxsub]")
            fc.append(f"[{h_i}:a]volume=0.25,afade=t=out:st=1.0:d=0.8[hit]")
            mix.append("[hit]")
        if len(mix) == 1:
            fc.append(
                f"[voice]loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,afade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6[aout]"
            )
        else:
            fc.append(
                "".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,afade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6[aout]"
            )

        vmap, vcodec = ["-map", "0:v"], ["-c:v", "copy"]
        if captions and Path(captions).exists():
            fonts = (ROOT / "assets" / "fonts").resolve().as_posix().replace(":", "\\:")
            cap = Path(captions).resolve().as_posix().replace(":", "\\:")
            fc.append(f"[0:v]ass='{cap}':fontsdir='{fonts}'[vcap]")
            vmap = ["-map", "[vcap]"]
            vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
        cmd = [
            self._ffmpeg,
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(fc),
            *vmap,
            "-map",
            "[aout]",
            "-t",
            f"{total:.3f}",
            *vcodec,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-movflags",
            "+faststart",
            str(out),
        ]
        logger.info("Rendering final video (%d beats, %.1fs)…", len(clips), total)
        _run(cmd, timeout=900)
        shutil.rmtree(work, ignore_errors=True)
        return str(out)

    def render_word_cuts(
        self,
        plan: WordCutPlan,
        out_path: str,
        captions_ass_path: Optional[str] = None,
    ) -> str:
        return render_word_cuts(
            plan=plan,
            out_path=out_path,
            captions_ass_path=captions_ass_path,
            width=self.width,
            height=self.height,
        )


def render_word_cuts(
    plan: WordCutPlan,
    out_path: str,
    captions_ass_path: Optional[str] = None,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Render smart word-level visual cuts with continuous master audio.

    - Visual timeline cuts at word/group boundaries (contiguous: cut[i].end == cut[i+1].start).
    - Audio is never sliced: voiceover plays continuously from a single master track.
    - Captions are generated per word with current word highlighted.
    """
    if not plan.cuts:
        raise RenderError("WordCutPlan has no cuts to render.")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"_wcuts_{plan.video_id or 'run'}"
    work.mkdir(parents=True, exist_ok=True)
    cache_dir = ROOT / "output" / "_wcut_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    fps = plan.fps or 30
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cuts = plan.cuts

    # 1. Enforce contiguous boundaries
    cuts[0].start = 0.0
    for i in range(1, len(cuts)):
        cuts[i].start = cuts[i - 1].end
        if cuts[i].end <= cuts[i].start:
            cuts[i].end = round(cuts[i].start + (2.0 / fps), 3)

    if plan.duration > 0 and cuts[-1].end < plan.duration:
        cuts[-1].end = round(plan.duration, 3)

    # 2. Render individual video-only segments (cached by parameters hash)
    def _render_segment(idx: int) -> tuple[int, str]:
        c = cuts[idx]
        dur = max(c.end - c.start, 2.0 / fps)
        frames = max(int(round(dur * fps)), 2)

        cache_key = (
            f"{c.visual_asset}:{dur:.3f}:{c.motion_preset_id}:"
            f"{c.transition_effect}:{c.vfx_cue}:{width}x{height}@{fps}"
        )
        h = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        seg_cache = cache_dir / f"wcut_{h}.mp4"

        if seg_cache.exists() and seg_cache.stat().st_size > 1000:
            return idx, str(seg_cache)

        # Asset input setup
        inputs: List[str] = []
        filter_parts: List[str] = []
        asset_path = Path(c.visual_asset) if c.visual_asset else None

        if asset_path and asset_path.exists():
            ext = asset_path.suffix.lower()
            if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
                inputs = ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(asset_path)]
                filter_parts.append(
                    f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},setsar=1"
                )
            else:
                inputs = ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(asset_path)]
                filter_parts.append(
                    f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},setsar=1,fps={fps}"
                )
        else:
            # Fallback high-contrast solid background
            inputs = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"color=c=0x141A24:s={width}x{height}:r={fps}"]
            filter_parts.append(f"[0:v]fps={fps},setsar=1")

        # Apply motion preset if available
        preset_filter = None
        if c.motion_preset_id:
            try:
                from video.motion_presets.catalog import get_preset

                spec = get_preset(c.motion_preset_id)
                if spec and spec.ffmpeg_filter_template:
                    preset_filter = spec.ffmpeg_filter_template.format(
                        frames=frames,
                        duration=dur,
                        fps=fps,
                        width=width,
                        height=height,
                    )
            except Exception:
                pass

        if preset_filter and not preset_filter.startswith("overlay="):
            filter_parts.append(preset_filter)

        # Apply transition / cut effect
        fx = c.transition_effect or "cut"
        if fx == "flash":
            filter_parts.append("fade=t=in:st=0:d=0.08:color=white")
        elif fx == "dip":
            filter_parts.append("fade=t=in:st=0:d=0.10:color=black")
        elif fx == "glitch":
            filter_parts.append("rgbashift=rh=-20:bh=20:gv=6:enable='lt(t,0.1)'")

        vf = ",".join(filter_parts).replace("[0:v]", "")
        cmd = [
            ffmpeg,
            "-y",
            *inputs,
            "-vf",
            vf,
            "-t",
            f"{dur:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(seg_cache),
        ]
        _run(cmd, timeout=120)
        return idx, str(seg_cache)

    seg_paths = [None] * len(cuts)
    with ThreadPoolExecutor(max_workers=min(2, os.cpu_count() or 2)) as pool:
        for idx, sp in pool.map(lambda i: _render_segment(i), range(len(cuts))):
            seg_paths[idx] = sp

    # 3. Concatenate video-only segments
    concat_list = work / "concat_list.txt"
    concat_list.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in seg_paths))
    video_only = work / "video_only.mp4"
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(video_only),
        ]
    )

    # 4. Handle ASS Captions
    final_cap_path = captions_ass_path
    if not final_cap_path and plan.captions:
        from video.subtitle_generator import SubtitleGenerator

        sub_gen = SubtitleGenerator()
        final_cap_path = str(work / "word_captions.ass")
        sub_gen.generate_ass(plan.captions, final_cap_path, width=width, height=height)

    # 5. Mux master audio track ONCE
    audio_input = ["-i", plan.audio_path] if plan.audio_path and Path(plan.audio_path).exists() else []

    if audio_input:
        if final_cap_path and Path(final_cap_path).exists():
            fonts = (ROOT / "assets" / "fonts").resolve().as_posix().replace(":", "\\:")
            cap = Path(final_cap_path).resolve().as_posix().replace(":", "\\:")
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(video_only),
                *audio_input,
                "-vf",
                f"ass='{cap}':fontsdir='{fonts}'",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out),
            ]
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(video_only),
                *audio_input,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out),
            ]
    else:
        # Video only output
        cmd = [ffmpeg, "-y", "-i", str(video_only), "-c:v", "copy", str(out)]

    _run(cmd, timeout=300)
    shutil.rmtree(work, ignore_errors=True)
    return str(out)

