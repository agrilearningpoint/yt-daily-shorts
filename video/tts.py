"""Human-like Hindi voiceover.

Order (configurable): Gemini TTS (gemini-3.8-flash-tts etc., free tier,
expressive, Hindi) -> Microsoft edge-tts (fallback).

The whole script is voiced in ONE request (keeps free-tier rate limits happy
and gives a natural, continuous delivery). It is then split back into the
individual beats (hook, each news item / scene, outro) by snapping the
expected boundaries to real pauses found with ffmpeg ``silencedetect``.
In strict mode a failure raises — a silent video is never produced.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("video.tts")

HINDI_VOICES = {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


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


@dataclass
class VoiceResult:
    audio_path: str             # full voiceover
    durations: List[float]      # one per beat, sums to total
    provider: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def probe_duration(path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # ffmpeg-only environments (e.g. the imageio-ffmpeg binary): read the banner
        try:
            ff = shutil.which("ffmpeg") or "ffmpeg"
            out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True, timeout=30)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out.stderr or "")
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        return 0.0
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=30)
        if out.stdout.strip():
            return float(out.stdout.strip())
    except Exception:
        pass
    try:      # ffprobe missing or broken (imageio-ffmpeg ships ffmpeg only)
        ff = shutil.which("ffmpeg") or "ffmpeg"
        out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True, timeout=30)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out.stderr or "")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def distribute_words(text: str, duration: float, offset: float = 0.0) -> List[WordTiming]:
    words = text.split()
    if not words or duration <= 0:
        return []
    weights = [max(len(w), 2) for w in words]
    total = sum(weights)
    t, out = offset, []
    for w, wt in zip(words, weights):
        d = duration * wt / total
        out.append(WordTiming(w, round(t, 3), round(t + d, 3)))
        t += d
    return out


def detect_silences(path: str, noise_db: int = -32, min_d: float = 0.12) -> List[Tuple[float, float]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    res = subprocess.run([ffmpeg, "-hide_banner", "-i", path, "-af", f"silencedetect=noise={noise_db}dB:d={min_d}",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", res.stderr)]
    return list(zip(starts, ends))


def split_by_pauses(texts: List[str], total: float, silences: List[Tuple[float, float]]) -> List[float]:
    """Durations per text: proportional estimate snapped to the nearest real pause."""
    weights = [max(len(re.sub(r"<[^>]+>", "", t).replace(" ", "")), 1) for t in texts]
    wsum = float(sum(weights))
    mids = [(a + b) / 2 for a, b in silences if b - a >= 0.08]
    bounds: List[float] = []
    acc = 0.0
    prev = 0.0
    for i, w in enumerate(weights[:-1]):
        acc += w
        expected = total * acc / wsum
        avg = total / len(texts)
        window = max(0.5, avg * 0.45)
        cands = [m for m in mids if abs(m - expected) <= window and m > prev + 0.6]
        b = min(cands, key=lambda m: abs(m - expected)) if cands else max(expected, prev + 0.6)
        bounds.append(b)
        prev = b
    edges = [0.0] + bounds + [total]
    durs = [max(edges[i + 1] - edges[i], 0.4) for i in range(len(texts))]
    scale = total / sum(durs)
    return [round(d * scale, 3) for d in durs]


def _find_audio_b64(obj: Any) -> Optional[str]:
    """Find base64 audio inside an Interactions/generateContent response."""
    found: List[str] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if o.get("type") == "audio" and isinstance(o.get("data"), str):
                found.append(o["data"])
            inline = o.get("inlineData") or o.get("inline_data")
            if isinstance(inline, dict) and str(inline.get("mimeType", inline.get("mime_type", ""))).startswith("audio"):
                found.append(inline.get("data", ""))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return found[-1] if found else None


def _write_pcm_wav(pcm: bytes, path: str, rate: int = 24000) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


# ---------------------------------------------------------------------------
# Gemini TTS
# ---------------------------------------------------------------------------

class GeminiTTS:
    def __init__(self, api_key: str, models: List[str], voice: str = "auto", fallback_voice: str = "Charon",
                 timeout: int = 180):
        self.api_key = api_key
        self.models = models
        self.voice = voice
        self.fallback_voice = fallback_voice
        self.timeout = timeout
        self._resolved_voice: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        if getattr(self, "keys", None):
            key = self.keys[self._ki % len(self.keys)]
            self._ki = (self._ki + 1) % len(self.keys)
            return {"x-goog-api-key": key, "Content-Type": "application/json"}
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def resolve_voice(self) -> str:
        if self._resolved_voice:
            return self._resolved_voice
        voice = self.voice
        if not voice or voice == "auto":
            voice = self.fallback_voice
            try:
                for params in ({"language_code": "hi-IN", "context": "News", "type": "prebuilt", "gender": "male"},
                               {"language_code": "hi-IN", "type": "prebuilt"}):
                    r = requests.get(f"{GEMINI_BASE}/voices", headers=self._headers(), params=params, timeout=20)
                    if r.status_code == 200:
                        voices = r.json().get("voices") or []
                        if voices:
                            voice = voices[0].get("id") or voices[0].get("name", "").split("/")[-1] or voice
                            break
            except Exception as exc:
                logger.info("Voice library lookup failed (%s); using %s", exc, voice)
        self._resolved_voice = voice
        logger.info("Gemini TTS voice: %s", voice)
        return voice

    def _interactions(self, model: str, text: str, style: str, voice: str) -> bytes:
        body = {
            "model": model,
            "input": [{"type": "user_input", "content": [{
                "type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]},
        }
        r = requests.post(f"{GEMINI_BASE}/interactions", headers=self._headers(), json=body, timeout=self.timeout)
        if r.status_code != 200:
            raise TTSError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
        data = _find_audio_b64(r.json())
        if not data:
            raise TTSError(f"{model}: no audio in response")
        return base64.b64decode(data)

    def _generate_content(self, model: str, text: str, style: str, voice: str) -> bytes:
        body = {
            "contents": [{"parts": [{"text": f"Read this Hindi text aloud in the style of a {style}:\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
        }
        r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers=self._headers(), json=body,
                          timeout=self.timeout)
        if r.status_code != 200:
            raise TTSError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
        data = _find_audio_b64(r.json())
        if not data:
            raise TTSError(f"{model}: no audio in response")
        return base64.b64decode(data)

    def synthesize(self, text: str, style: str, out_wav: str) -> str:
        voice = self.resolve_voice()
        errors = []
        for model in self.models:
            for v in dict.fromkeys([voice, self.fallback_voice]):
                try:
                    if not model.startswith(("gemini-2.", "gemini-1.")):
                        audio = self._interactions(model, text, style, v)
                    else:
                        audio = self._generate_content(model, re.sub(r"<[^>]+>", "...", text), style, v)
                    if audio[:4] == b"RIFF":
                        Path(out_wav).write_bytes(audio)
                    else:
                        _write_pcm_wav(audio, out_wav)
                    if probe_duration(out_wav) < 1.0:
                        raise TTSError(f"{model}: audio too short")
                    logger.info("Voice generated with Gemini %s (%s)", model, v)
                    return model
                except Exception as exc:
                    errors.append(str(exc)[:160])
                    logger.warning("Gemini TTS %s/%s failed: %s", model, v, str(exc)[:160])
                    if "HTTP 400" not in str(exc):
                        break  # voice is not the problem; try next model
        raise TTSError("Gemini TTS failed: " + " | ".join(errors[-4:]))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class TTSEngine:
    def __init__(self, voice: str = "hi-IN-MadhurNeural", rate: str = "+8%", pitch: str = "+0Hz",
                 fallback_voice: str = "hi-IN-SwaraNeural", strict: bool = False,
                 provider_order: Optional[List[str]] = None, gemini: Optional[GeminiTTS] = None):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.fallback_voice = fallback_voice
        self.strict = strict
        self.provider_order = provider_order or ["edge"]
        self.gemini = gemini

    # -- edge-tts ----------------------------------------------------------
    async def _synth(self, text: str, out_file: Path, voice: str) -> List[WordTiming]:
        import edge_tts
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=self.rate, pitch=self.pitch,
                                               boundary="WordBoundary")
        except TypeError:
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
        clean = re.sub(r"<[^>]+>", " ", text)
        last_exc: Optional[Exception] = None
        for attempt, voice in enumerate([self.voice, self.voice, self.fallback_voice]):
            try:
                words = await self._synth(clean, out_file, voice)
                duration = probe_duration(str(out_file)) or (words[-1].end + 0.3 if words else 0.0)
                return Segment(text=clean, audio_path=str(out_file), duration=duration,
                               words=words or distribute_words(clean, duration))
            except Exception as exc:
                last_exc = exc
                logger.warning("edge-tts attempt %d (%s) failed: %s", attempt + 1, voice, exc)
                await asyncio.sleep(2 * (attempt + 1))
        if self.strict:
            raise TTSError(f"TTS failed after retries: {last_exc}")
        duration = max(1.5, len(clean.split()) / 2.8)
        self._silence(str(out_file), duration)
        logger.warning("Using SILENT placeholder audio (dry-run only) for: %s", clean[:40])
        return Segment(text=clean, audio_path=str(out_file), duration=duration,
                       words=distribute_words(clean, duration))

    async def synthesize_segments(self, texts: List[str], out_dir: str) -> List[Segment]:
        return [await self.synthesize_segment(t, str(Path(out_dir) / f"voice_{i:02d}.mp3"))
                for i, t in enumerate(texts)]

    # -- main API ------------------------------------------------------------
    async def voice_beats(self, texts: List[str], out_dir: str, style: str = "") -> VoiceResult:
        """Voice all beats; returns the full track and per-beat durations."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        final = str(out / "voiceover.m4a")
        for provider in self.provider_order:
            if provider == "gemini" and self.gemini:
                try:
                    joined = " <short pause> ".join(t.strip().rstrip("।.") + "।" for t in texts)
                    raw = str(out / "voice_gemini.wav")
                    model = await asyncio.to_thread(self.gemini.synthesize, joined, style, raw)
                    self._normalise(raw, final)
                    total = probe_duration(final)
                    durs = split_by_pauses(texts, total, detect_silences(final))
                    return VoiceResult(final, durs, f"gemini:{model}")
                except Exception as exc:
                    logger.warning("Gemini TTS unavailable, falling back: %s", str(exc)[:200])
            elif provider == "edge":
                segs = await self.synthesize_segments(texts, out_dir)
                self.concat_audio(segs, final)
                return VoiceResult(final, [s.duration for s in segs], "edge-tts")
        raise TTSError("No TTS provider produced audio")

    @staticmethod
    def _normalise(src: str, dst: str) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        # trim leading/trailing silence, keep natural pauses inside
        af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
              "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
              "aresample=44100,aformat=channel_layouts=stereo")
        res = subprocess.run([ffmpeg, "-y", "-i", src, "-af", af, "-c:a", "aac", "-b:a", "192k", dst],
                             capture_output=True, timeout=120)
        if res.returncode != 0:
            raise TTSError(res.stderr.decode(errors="ignore")[-300:])

    @staticmethod
    def concat_audio(segments: List[Segment], output_path: str) -> str:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise TTSError("ffmpeg not found")
        inputs: List[str] = []
        for s in segments:
            inputs += ["-i", s.audio_path]
        n = len(segments)
        filt = "".join(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];" for i in range(n))
        filt += "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        res = subprocess.run([ffmpeg, "-y", *inputs, "-filter_complex", filt, "-map", "[out]", "-c:a", "aac",
                              "-b:a", "192k", output_path], capture_output=True, timeout=180)
        if res.returncode != 0:
            raise TTSError(res.stderr.decode(errors="ignore")[-400:])
        return output_path

    @staticmethod
    def _silence(output_path: str, duration: float) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{duration:.2f}",
                        "-acodec", "libmp3lame", output_path], capture_output=True, timeout=60)

    async def generate_audio(self, text: str, output_path: str) -> str:
        return (await self.synthesize_segment(text, output_path)).audio_path

    @staticmethod
    def dump_timings(texts: List[str], durations: List[float], provider: str, path: str) -> None:
        Path(path).write_text(json.dumps({"provider": provider, "beats": [
            {"text": t, "duration": d} for t, d in zip(texts, durations)]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
