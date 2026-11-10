"""Chapter rendering for the long-form pipeline (16:9, 1080p).

One ffmpeg pass per image slice, concatenated with the demuxer, then a single
muxing pass that adds narration, burned-in subtitles, chapter card and loudness
normalisation. Splitting the work this way means a 25-minute film renders in
minutes, and a single bad image can be replaced without touching the rest.

Editing language (all deliberate, all cheap):
  * slow Ken Burns push/pull, direction alternating so the frame never feels static
  * cuts land on sentence boundaries - never mid-sentence
  * a chapter card at the start ("अध्याय 3 / 9"), plus a lower-third over the first 6 s
  * sentence subtitles, 2 lines max, safe-area bottom margin (no karaoke shouting)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("longform.render")

W, H, FPS = 1920, 1080, 30
CRF, PRESET = "22", "veryfast"
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def ff() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def run(cmd: List[str], what: str = "") -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({what}): {(proc.stderr or '')[-1200:]}")
    if what:
        logger.debug("ok: %s", what)


def probe_duration(path: str) -> float:
    """Duration in seconds. Uses ffprobe when present, else parses ffmpeg's own banner."""
    probe = shutil.which("ffprobe")
    if probe:
        try:
            out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=nw=1:nk=1", str(path)],
                                 capture_output=True, text=True, timeout=30)
            if out.stdout.strip():
                return float(out.stdout.strip())
        except Exception:
            pass
    try:      # fallback: read "Duration: 00:00:12.34" off ffmpeg -i
        out = subprocess.run([ff(), "-i", str(path)], capture_output=True, text=True, timeout=30)
        import re as _re
        m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out.stderr or "")
        if m:
            h, mi, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mi * 60 + sec
    except Exception:
        pass
    return 0.0


# --------------------------------------------------------------------------- #
# cards
# --------------------------------------------------------------------------- #
def _wrap(d, text: str, font, max_w: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_card(title: str, subtitle: str, out_path: Path,
              accent: Tuple[int, int, int] = (212, 175, 55)) -> str:
    """Clean dark chapter card with Devanagari type (also used for thumbnails)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), (14, 14, 18))
    d = ImageDraw.Draw(img)
    for y in range(H):
        shade = int(12 + 26 * (y / H))
        d.line([(0, y), (W, y)], fill=(shade, max(0, shade - 2), min(255, shade + 5)))
    f_big = ImageFont.truetype(str(FONT_DIR / "Mukta-ExtraBold.ttf"), 92)
    f_mid = ImageFont.truetype(str(FONT_DIR / "Mukta-Medium.ttf"), 44)
    d.rectangle([140, 400, 260, 408], fill=accent)
    y = 460
    for line in _wrap(d, title, f_big, W - 300)[:3]:
        d.text((140, y), line, font=f_big, fill=(244, 244, 248))
        y += 106
    if subtitle:
        for line in _wrap(d, subtitle, f_mid, W - 300)[:2]:
            d.text((142, y + 14), line, font=f_mid, fill=(176, 176, 188))
            y += 56
    img.save(out_path, "JPEG", quality=92)
    return str(out_path)


def make_outro(out_path: Path, channel: str, line1: str, line2: str) -> str:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), (12, 12, 16))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(str(FONT_DIR / "Mukta-ExtraBold.ttf"), 84)
    f2 = ImageFont.truetype(str(FONT_DIR / "Mukta-Medium.ttf"), 46)
    f3 = ImageFont.truetype(str(FONT_DIR / "Mukta-Bold.ttf"), 44)
    d.rectangle([W // 2 - 70, 370, W // 2 + 70, 376], fill=(212, 175, 55))
    d.text((W // 2, 470), line1, font=f1, fill=(245, 245, 250), anchor="mm")
    d.text((W // 2, 576), line2, font=f2, fill=(180, 180, 195), anchor="mm")
    d.text((W // 2, 706), channel, font=f3, fill=(212, 175, 55), anchor="mm")
    img.save(out_path, "JPEG", quality=92)
    return str(out_path)


# --------------------------------------------------------------------------- #
# subtitles — rendered with PIL (HarfBuzz shaping), NOT libass
# --------------------------------------------------------------------------- #
# libass in this ffmpeg build renders Devanagari without shaping (matras come out
# as dotted circles). PIL has raqm, so the text is drawn as a transparent PNG and
# overlaid on top of the moving frame: correct conjuncts, and the text stays put
# while the picture Ken-Burns underneath it.
SUB_FONT = "Mukta-Bold.ttf"
SUB_SIZE = 58
SUB_MAX_W = W - 320
SUB_Y = H - 168


def subtitle_png(text: str, out_path: Path, size: int = SUB_SIZE) -> str:
    from PIL import Image, ImageDraw, ImageFont

    text = " ".join(str(text).split())
    font = ImageFont.truetype(str(FONT_DIR / SUB_FONT), size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # bottom scrim: subtitles must stay readable over a bright sky or a white monument
    scrim_h = 300
    for i in range(scrim_h):
        alpha = int(150 * (i / scrim_h) ** 1.6)
        d.line([(0, H - scrim_h + i), (W, H - scrim_h + i)], fill=(0, 0, 0, alpha))

    def wrap(t: str) -> List[str]:
        words, lines, cur = t.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=font) <= SUB_MAX_W:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines[:2]

    lines = wrap(text)
    line_h = size + 16
    y = SUB_Y - (len(lines) - 1) * line_h
    for line in lines:
        tw = d.textlength(line, font=font)
        x = (W - tw) / 2
        # soft drop shadow keeps the text legible over bright photographs
        d.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 200))
        d.text((x, y), line, font=font, fill=(246, 246, 250, 255))
        y += line_h
    img.save(out_path, "PNG")
    return str(out_path)


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def build_srt(cues: Sequence[Dict], out_path: Path, offset: float = 0.0) -> str:
    """Sidecar captions for YouTube (viewers can toggle; also helps search)."""
    lines = []
    for i, c in enumerate(cues, 1):
        if c["end"] <= c["start"]:
            continue
        lines.append(f"{i}\n{_ass_time(c['start'] + offset)} --> {_ass_time(c['end'] + offset)}\n"
                     f"{str(c['text']).strip()}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)


def sentence_cues(sentences: Sequence[str], words: Sequence[Dict], total: float) -> List[Dict]:
    """Map edge-tts word timings onto sentence boundaries.

    The TTS reads the sentences in order, so sentence i owns the next
    len(sentence_i) words. That keeps subtitle timing locked to the voice without
    needing a forced aligner.
    """
    from longform.script import split_sentences

    flat: List[str] = []
    for s in sentences:
        flat.extend(split_sentences(s))
    if not words:
        weight = [len(s) for s in flat] or [1]
        cues, t = [], 0.0
        for s, w in zip(flat, weight):
            dur = total * (w / sum(weight))
            cues.append({"text": s, "start": t, "end": t + dur})
            t += dur
        return cues
    cues, wi = [], 0
    for s in flat:
        n = max(1, len(s.split()))
        start = float(words[min(wi, len(words) - 1)]["start"])
        end_idx = min(wi + n - 1, len(words) - 1)
        end = float(words[end_idx]["end"])
        cues.append({"text": s, "start": start, "end": max(end, start + 0.6)})
        wi += n
    return cues


# --------------------------------------------------------------------------- #
# timeline planning
# --------------------------------------------------------------------------- #
def plan_slices(cues: List[Dict], n_images: int, start_at: float, end_at: float) -> List[Tuple[float, float]]:
    """Split [start_at, end_at] into n_images spans, each cut on a sentence boundary."""
    n_images = max(1, n_images)
    usable = [c for c in cues if c["end"] > start_at]
    if not usable:
        step = (end_at - start_at) / n_images
        return [(start_at + i * step, start_at + (i + 1) * step) for i in range(n_images)]
    target = (end_at - start_at) / n_images
    spans: List[Tuple[float, float]] = []
    cursor = start_at
    for i in range(n_images):
        if i == n_images - 1:
            spans.append((cursor, max(end_at, cursor + 1.5)))
            break
        want = cursor + target
        # nearest cue boundary after 'want', but always make progress
        candidates = [c["end"] for c in cues if c["end"] > cursor + 1.0]
        pick = min(candidates, key=lambda t: abs(t - want)) if candidates else want
        if pick <= cursor + 0.8:
            pick = want
        spans.append((cursor, pick))
        cursor = pick
    return spans


# --------------------------------------------------------------------------- #
# video pieces
# --------------------------------------------------------------------------- #
def render_still(img: str, dur: float, out_path: str, seed: int = 0, fps: int = FPS,
                 overlay: Optional[str] = None) -> str:
    """Slow Ken Burns clip from one still, alternating push / pull / pan."""
    frames = max(2, int(round(dur * fps)))
    kind = seed % 4
    if kind == 0:
        z = "min(zoom+0.00042,1.16)"; x = "iw/2-(iw/zoom/2)"; y = "ih/2-(ih/zoom/2)"
    elif kind == 1:
        z = "if(eq(on,1),1.16,max(zoom-0.00042,1.0))"; x = "iw/2-(iw/zoom/2)"; y = "ih/2-(ih/zoom/2)"
    elif kind == 2:
        z = "min(zoom+0.00030,1.12)"; x = "(iw-iw/zoom)*on/{d}".format(d=frames); y = "ih/2-(ih/zoom/2)"
    else:
        z = "min(zoom+0.00030,1.12)"; x = "(iw-iw/zoom)*(1-on/{d})".format(d=frames); y = "ih/2-(ih/zoom/2)"
    vf = (f"scale=2560:1440:force_original_aspect_ratio=increase,crop=2560:1440,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps},"
          f"format=yuv420p")
    cmd = [ff(), "-y", "-loop", "1", "-i", img]
    if overlay:
        cmd += ["-loop", "1", "-i", overlay,
                "-filter_complex", f"[0:v]{vf}[bg];[bg][1:v]overlay=0:0:format=auto,format=yuv420p[v]",
                "-map", "[v]"]
    else:
        cmd += ["-vf", vf]
    cmd += ["-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
            "-g", "60", "-pix_fmt", "yuv420p", "-an", out_path]
    run(cmd, f"still {Path(img).name}")
    return out_path


def concat(videos: List[str], out_path: str, work: Path, reencode: bool = False) -> str:
    """Join clips. Stream-copy is fine for identical pieces; a film-level join
    re-encodes because stream-copy silently loses seconds when the parts differ
    by a frame or two (measured: 19.0 min of chapters came out as 17.3 min)."""
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{Path(v).resolve()}'\n" for v in videos), encoding="utf-8")
    cmd = [ff(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if reencode:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"]
    else:
        cmd += ["-c", "copy"]
    cmd.append(out_path)
    run(cmd, "concat")
    return out_path


def mux_chapter(video: str, audio: str, _ass_unused: Optional[str], out_path: str,
                fade_in: float = 0.7, fade_out: float = 0.9, audio_delay_ms: int = 0) -> str:
    """Add narration + fades + loudness normalisation (subtitles are already burned).

    ``audio_delay_ms`` lets the chapter card play *over* the opening of the
    narration without shifting the subtitle timeline.
    """
    dur = probe_duration(video)
    vf = []
    vf.append(f"fade=t=in:st=0:d={fade_in}")
    if dur > fade_out + 1:
        vf.append(f"fade=t=out:st={max(0.0, dur - fade_out):.2f}:d={fade_out}")
    cmd = [ff(), "-y", "-i", video, "-i", audio,
           "-vf", ",".join(vf),
           "-af", (("adelay=%d|%d," % (audio_delay_ms, audio_delay_ms)) if audio_delay_ms else "")
                  + "loudnorm=I=-16:TP=-1.5:LRA=11",
           "-c:v", "libx264", "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-shortest", "-movflags", "+faststart", out_path]
    run(cmd, f"mux {Path(out_path).name}")
    return out_path
