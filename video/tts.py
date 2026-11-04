"""Hindi voiceover with edge-tts, per-segment, with word-level timings.

Each segment (hook + every scene) is synthesised separately so the video
knows the exact length of every scene and captions can be word-synced.
In strict mode a TTS failure raises — a silent video is never produced.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("video.tts")

HINDI_VOICES = {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"}


class TTSError(RuntimeError):
    pass


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class Segment:
    text: str
    audio_path: str
    duration: float
    words: List[WordTiming] = field(default_factory=list)


def probe_duration(path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip() or 0)
    except Exception:
        return 0.0


def distribute_words(text: str, duration: float, offset: float = 0.0) -> List[WordTiming]:
    """Estimate per-word timings proportional to word length (fallback)."""
    words = text.split()
    if not words or duration <= 0:
        return []
    weights = [max(len(w), 2) for w in words]
    total = sum(weights)
    t = offset
    out = []
    for w, wt in zip(words, weights):
        d = duration * wt / total
        out.append(WordTiming(w, round(t, 3), round(t + d, 3)))
        t += d
    return out


class TTSEngine:
    def __init__(self, voice: str = "hi-IN-MadhurNeural", rate: str = "+8%", pitch: str = "+0Hz",
                 fallback_voice: str = "hi-IN-SwaraNeural", strict: bool = False):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.fallback_voice = fallback_voice
        self.strict = strict

    async def _synth(self, text: str, out_file: Path, voice: str) -> List[WordTiming]:
        import edge_tts
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=self.rate, pitch=self.pitch,
                                               boundary="WordBoundary")
        except TypeError:  # older edge-tts without `boundary`
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=self.rate, pitch=self.pitch)
        words: List[WordTiming] = []
        with open(out_file, "wb") as fh:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append(WordTiming(chunk["text"], start, start + chunk["duration"] / 1e7))
        if out_file.stat().st_size < 2000:
            raise TTSError("edge-tts returned no audio")
        return words

    async def synthesize_segment(self, text: str, output_path: str) -> Segment:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Optional[Exception] = None
        for attempt, voice in enumerate([self.voice, self.voice, self.fallback_voice]):
            try:
                words = await self._synth(text, out_file, voice)
                duration = probe_duration(str(out_file)) or (words[-1].end + 0.3 if words else 0.0)
                if not words:
                    words = distribute_words(text, duration)
                return Segment(text=text, audio_path=str(out_file), duration=duration, words=words)
            except Exception as exc:
                last_exc = exc
                logger.warning("edge-tts attempt %d (%s) failed: %s", attempt + 1, voice, exc)
                await asyncio.sleep(2 * (attempt + 1))
        if self.strict:
            raise TTSError(f"TTS failed after retries: {last_exc}")
        # Dry-run only: approximate-length silence so the rest of the pipeline can be tested.
        duration = max(2.0, len(text.split()) / 2.5)
        self._silence(str(out_file), duration)
        logger.warning("Using SILENT placeholder audio (dry-run only) for: %s", text[:40])
        return Segment(text=text, audio_path=str(out_file), duration=duration,
                       words=distribute_words(text, duration))

    async def synthesize_segments(self, texts: List[str], out_dir: str) -> List[Segment]:
        segs = []
        for i, t in enumerate(texts):
            segs.append(await self.synthesize_segment(t, str(Path(out_dir) / f"voice_{i:02d}.mp3")))
        return segs

    @staticmethod
    def concat_audio(segments: List[Segment], output_path: str) -> str:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise TTSError("ffmpeg not found")
        inputs = []
        for s in segments:
            inputs += ["-i", s.audio_path]
        n = len(segments)
        filt = "".join(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];" for i in range(n))
        filt += "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        cmd = [ffmpeg, "-y", *inputs, "-filter_complex", filt, "-map", "[out]", "-c:a", "aac", "-b:a", "160k", output_path]
        res = subprocess.run(cmd, capture_output=True, timeout=120)
        if res.returncode != 0:
            raise TTSError(res.stderr.decode(errors="ignore")[-400:])
        return output_path

    @staticmethod
    def _silence(output_path: str, duration: float) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{duration:.2f}",
                        "-acodec", "libmp3lame", output_path], capture_output=True, timeout=60)

    # Back-compat single-shot API -------------------------------------------
    async def generate_audio(self, text: str, output_path: str) -> str:
        seg = await self.synthesize_segment(text, output_path)
        return seg.audio_path

    @staticmethod
    def dump_timings(segments: List[Segment], path: str) -> None:
        Path(path).write_text(json.dumps([
            {"text": s.text, "duration": s.duration, "words": [vars(w) for w in s.words]} for s in segments
        ], ensure_ascii=False, indent=1), encoding="utf-8")
