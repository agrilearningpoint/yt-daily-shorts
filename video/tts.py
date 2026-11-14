"""Production-grade TTS engine with beat-locked audio/video sync and multi-key rotation."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import edge_tts
import requests

logger = logging.getLogger(__name__)

HINDI_VOICES = {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
ROTATE_ERRORS = ("429", "401", "403", "503", "RESOURCE_EXHAUSTED", "quota", "timeout")


class TTSError(RuntimeError):
    """Raised when all TTS providers fail in strict mode."""


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
    audio_path: str
    durations: List[float]
    provider: str
    segments: List[Segment] = field(default_factory=list)


def probe_duration(path: str) -> float:
    """Measure exact audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return max(0.1, float(res.stdout.strip()))


def distribute_words(text: str, duration: float, offset: float = 0.0) -> List[WordTiming]:
    """Fallback even word distribution when WordBoundary events are unavailable."""
    words = [w for w in text.strip().split() if w]
    if not words:
        return []
    step = duration / len(words)
    return [
        WordTiming(word=w, start=round(offset + i * step, 3), end=round(offset + (i + 1) * step, 3))
        for i, w in enumerate(words)
    ]


def _find_audio_b64(obj: Any) -> Optional[str]:
    if isinstance(obj, dict):
        if "data" in obj and isinstance(obj["data"], str) and len(obj["data"]) > 200:
            return obj["data"]
        for v in obj.values():
            found = _find_audio_b64(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_audio_b64(item)
            if found:
                return found
    return None


def _parse_key_pool(api_key: str | List[str]) -> List[str]:
    if isinstance(api_key, list):
        raw = api_key
    else:
        raw = [api_key]
    extra = os.getenv("YT_GEMINI_API_KEYS_EXTRA", "")
    for sep in (",", ";", "\n"):
        extra = extra.replace(sep, ",")
    raw.extend(k.strip() for k in extra.split(",") if k.strip())
    seen, pool = set(), []
    for k in raw:
        if k and k not in seen:
            seen.add(k)
            pool.append(k)
    return pool


class GeminiTTS:
    """Gemini TTS with automatic multi-key rotation on quota/429 errors."""

    def __init__(
        self,
        api_key: str | List[str],
        models: List[str],
        voice: str = "auto",
        fallback_voice: str = "Charon",
        timeout: int = 180,
    ):
        self.keys = _parse_key_pool(api_key)
        self.models = models or ["gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"]
        self.voice = voice
        self.fallback_voice = fallback_voice
        self.timeout = timeout
        self._ki = 0
        self._lock = threading.Lock()

    def resolve_voice(self) -> str:
        return self.fallback_voice if self.voice == "auto" else self.voice

    def _next_key(self) -> str:
        with self._lock:
            if not self.keys:
                raise TTSError("No Gemini API keys configured for GeminiTTS.")
            key = self.keys[self._ki % len(self.keys)]
            self._ki = (self._ki + 1) % len(self.keys)
            return key

    def _generate_content(self, key: str, model: str, text: str, style: str, voice: str) -> bytes:
        url = f"{GEMINI_BASE}/models/{model}:generateContent?key={key}"
        prompt = f"Speak in this style: {style}\n\nText: {text}" if style else text
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
                },
            },
        }
        resp = requests.post(url, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise TTSError(f"GeminiTTS HTTP {resp.status_code}: {resp.text[:200]}")
        b64 = _find_audio_b64(resp.json())
        if not b64:
            raise TTSError(f"GeminiTTS returned no audio payload for model {model}")
        return base64.b64decode(b64)

    def synthesize(self, text: str, style: str, out_wav: str) -> str:
        if not self.keys:
            raise TTSError("GeminiTTS has no API keys.")
        voice = self.resolve_voice()
        last_err: Optional[Exception] = None
        for model in self.models:
            for _ in range(len(self.keys)):
                key = self._next_key()
                try:
                    audio_bytes = self._generate_content(key, model, text, style, voice)
                    Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
                    Path(out_wav).write_bytes(audio_bytes)
                    return model
                except Exception as exc:
                    last_err = exc
                    msg = str(exc)
                    if any(tok in msg for tok in ROTATE_ERRORS):
                        logger.warning("GeminiTTS rotating key on %s: %s", model, msg[:120])
                        continue
                    break
        raise TTSError(f"GeminiTTS failed across all keys/models: {last_err}")


class TTSEngine:
    """Beat-locked TTS Engine: synthesizes each beat separately to eliminate image-sound drift."""

    def __init__(
        self,
        voice: str = "hi-IN-MadhurNeural",
        rate: str = "+16%",
        pitch: str = "+0Hz",
        fallback_voice: str = "hi-IN-SwaraNeural",
        strict: bool = True,
        provider_order: Optional[List[str]] = None,
        gemini: Optional[GeminiTTS] = None,
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.fallback_voice = fallback_voice
        self.strict = strict
        self.provider_order = provider_order or ["gemini", "edge"]
        self.gemini = gemini

    @staticmethod
    def _normalise(src: str, dst: str) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-af", "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(dst),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @staticmethod
    def concat_audio(segments: List[Segment], output_path: str) -> str:
        list_file = Path(output_path).with_suffix(".concat.txt")
        lines = [f"file '{Path(s.audio_path).resolve()}'" for s in segments]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c:a", "pcm_s16le", str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        list_file.unlink(missing_ok=True)
        return str(output_path)

    async def _synth(self, text: str, out_file: Path, voice: str) -> List[WordTiming]:
        comm = edge_tts.Communicate(text, voice, rate=self.rate, pitch=self.pitch)
        words: List[WordTiming] = []
        audio_chunks: List[bytes] = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000.0
                dur = chunk["duration"] / 10_000_000.0
                words.append(WordTiming(word=chunk["text"], start=round(start, 3), end=round(start + dur, 3)))
        out_file.write_bytes(b"".join(audio_chunks))
        return words

    async def synthesize_segment(self, text: str, output_path: str) -> Segment:
        raw_mp3 = Path(output_path).with_suffix(".mp3")
        raw_mp3.parent.mkdir(parents=True, exist_ok=True)
        words: List[WordTiming] = []
        try:
            words = await self._synth(text, raw_mp3, self.voice)
        except Exception:
            words = await self._synth(text, raw_mp3, self.fallback_voice)
        self._normalise(str(raw_mp3), output_path)
        raw_mp3.unlink(missing_ok=True)
        dur = probe_duration(output_path)
        if not words:
            words = distribute_words(text, dur)
        return Segment(text=text, audio_path=output_path, duration=dur, words=words)

    async def synthesize_segments(self, texts: List[str], out_dir: str) -> List[Segment]:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        tasks = [
            self.synthesize_segment(t, str(out_path / f"beat_{i:02d}.wav"))
            for i, t in enumerate(texts)
        ]
        return await asyncio.gather(*tasks)

    async def _voice_beats_gemini(self, texts: List[str], out_dir: Path, style: str) -> VoiceResult:
        if not self.gemini:
            raise TTSError("GeminiTTS not initialized.")
        segments: List[Segment] = []
        used_model = ""
        for i, beat_text in enumerate(texts):
            raw_wav = out_dir / f"gemini_raw_{i:02d}.wav"
            norm_wav = out_dir / f"beat_{i:02d}.wav"
            used_model = await asyncio.to_thread(self.gemini.synthesize, beat_text, style, str(raw_wav))
            await asyncio.to_thread(self._normalise, str(raw_wav), str(norm_wav))
            raw_wav.unlink(missing_ok=True)
            dur = probe_duration(str(norm_wav))
            words = distribute_words(beat_text, dur)
            segments.append(Segment(text=beat_text, audio_path=str(norm_wav), duration=dur, words=words))

        final_wav = str(out_dir / "voice_full.wav")
        self.concat_audio(segments, final_wav)
        return VoiceResult(
            audio_path=final_wav,
            durations=[s.duration for s in segments],
            provider=f"gemini:{used_model}",
            segments=segments,
        )

    async def voice_beats(self, texts: List[str], out_dir: str, style: str = "") -> VoiceResult:
        """Synthesize every beat individually so visual durations match 1:1 with voice."""
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        errors: List[str] = []

        for provider in self.provider_order:
            try:
                if provider == "gemini" and self.gemini:
                    return await self._voice_beats_gemini(texts, out_path, style)
                if provider == "edge":
                    segs = await self.synthesize_segments(texts, out_dir)
                    final_wav = str(out_path / "voice_full.wav")
                    self.concat_audio(segs, final_wav)
                    return VoiceResult(
                        audio_path=final_wav,
                        durations=[s.duration for s in segs],
                        provider="edge-tts",
                        segments=segs,
                    )
            except Exception as exc:
                logger.warning("TTS provider %s failed: %s", provider, exc)
                errors.append(f"{provider}: {exc}")

        if not self.strict:
            final_wav = str(out_path / "voice_full.wav")
            durs = [max(1.5, len(t.split()) / 2.6) for t in texts]
            total = sum(durs) or 2.0
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{total:.2f}", "-c:a", "pcm_s16le", final_wav], capture_output=True)
            return VoiceResult(audio_path=final_wav, durations=durs, provider="silence")
        raise TTSError(f"All TTS providers failed (silent fallback disabled in production): {'; '.join(errors)}")

def detect_silences(path: str, noise_db: int = -32, min_d: float = 0.12) -> List[Tuple[float, float]]:
    import re
    cmd = ["ffmpeg", "-i", str(path), "-af", f"silencedetect=noise={noise_db}dB:d={min_d}", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", res.stderr)]
    return list(zip(starts, ends))


def split_by_pauses(texts: List[str], total: float, silences: List[Tuple[float, float]]) -> List[float]:
    if not texts:
        return []
    if len(texts) == 1:
        return [round(total, 3)]
    weights = [max(1, len(t.split())) for t in texts]
    w_sum = sum(weights)
    mids = [(s + e) / 2.0 for s, e in silences]
    cuts, acc = [0.0], 0
    for w in weights[:-1]:
        acc += w
        target = total * (acc / w_sum)
        best = min(mids, key=lambda m: abs(m - target)) if mids else target
        snap = best if abs(best - target) <= 1.2 and best > cuts[-1] + 0.2 else target
        cuts.append(snap)
    cuts.append(total)
    return [round(cuts[i + 1] - cuts[i], 3) for i in range(len(texts))]
