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

HINDI_VOICES = {
    "female": "hi-IN-SwaraNeural",
    "male": "hi-IN-MadhurNeural",
    "female_fallback": "hi-IN-KavyaNeural",
}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class TTSError(RuntimeError):
    pass


@dataclass
class WordTiming:
    word: str
    start: float
    end: float
    confidence: float = 1.0
    source: str = "edge-tts"

    @property
    def text(self) -> str:
        return self.word


@dataclass
class Segment:
    text: str
    audio_path: str
    duration: float
    words: List[WordTiming] = field(default_factory=list)


@dataclass
class VoiceResult:
    audio_path: str  # full voiceover
    durations: List[float]  # one per beat, sums to total
    provider: str
    beat_words: List[List[WordTiming]] = field(default_factory=list)


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
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.stdout.strip():
            return float(out.stdout.strip())
    except Exception:
        pass
    try:  # ffprobe missing or broken (imageio-ffmpeg ships ffmpeg only)
        ff = shutil.which("ffmpeg") or "ffmpeg"
        out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True, timeout=30)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out.stderr or "")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def distribute_words(
    text: str, duration: float, offset: float = 0.0, source: str = "proportional", confidence: float = 0.5
) -> List[WordTiming]:
    words = text.split()
    if not words or duration <= 0:
        return []
    weights = [max(len(w), 2) for w in words]
    total = sum(weights)
    t, out = offset, []
    for w, wt in zip(words, weights):
        d = duration * wt / total
        out.append(WordTiming(w, round(t, 3), round(t + d, 3), confidence=confidence, source=source))
        t += d
    return out


def align_with_whisper(
    audio_path: str, expected_text: str, language: str = "hi"
) -> Optional[List[WordTiming]]:
    """Align Gemini or external audio with faster-whisper word-level timestamps if available."""
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, language=language, word_timestamps=True)
        results: List[WordTiming] = []
        for segment in segments:
            for w in getattr(segment, "words", []):
                clean_word = (getattr(w, "word", "") or "").strip()
                if clean_word:
                    results.append(
                        WordTiming(
                            word=clean_word,
                            start=round(float(getattr(w, "start", 0.0)), 3),
                            end=round(float(getattr(w, "end", 0.0)), 3),
                            confidence=round(float(getattr(w, "probability", 0.9)), 2),
                            source="whisper",
                        )
                    )
        return results if results else None
    except Exception as exc:
        logger.debug("faster-whisper alignment unavailable or failed: %s", exc)
        return None


def detect_silences(
    path: str, noise_db: int = -32, min_d: float = 0.12
) -> List[Tuple[float, float]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    res = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            path,
            "-af",
            f"silencedetect=noise={noise_db}dB:d={min_d}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", res.stderr)]
    return list(zip(starts, ends))


def _spoken_weight(text: str) -> float:
    """Estimate relative spoken duration (Hindi + English syllables + punctuation pauses)."""
    clean = re.sub(r"<[^>]+>", " ", text or "").strip()
    chars = len(re.sub(r"[\s।,.?!;:'\"()\-]+", "", clean))
    pauses = len(re.findall(r"[।,.?!;:]", clean))
    digits = len(re.findall(r"\d+", clean))
    return max(float(chars) + 2.8 * pauses + 1.5 * digits, 1.0)


def split_by_pauses(
    texts: List[str], total: float, silences: List[Tuple[float, float]]
) -> List[float]:
    """Durations per text: proportional estimate snapped to the nearest real pause."""
    if not texts:
        return []
    if len(texts) == 1 or total <= 0:
        return [round(max(total, 0.0), 3)] * len(texts)
    weights = [_spoken_weight(t) for t in texts]
    wsum = float(sum(weights))
    mids = sorted((a + b) / 2 for a, b in silences if b - a >= 0.08)
    n = len(texts)
    min_step = min(0.45, total / max(n * 1.5, 1.0))
    bounds: List[float] = []
    acc = 0.0
    prev = 0.0
    for i, w in enumerate(weights[:-1]):
        acc += w
        expected = total * acc / wsum
        remaining_min = (n - 1 - i) * min_step
        max_b = max(prev + min_step, total - remaining_min)
        avg = total / n
        window = max(0.45, avg * 0.45)
        cands = [m for m in mids if abs(m - expected) <= window and prev + min_step <= m <= max_b]
        b = (
            min(cands, key=lambda m: abs(m - expected))
            if cands
            else min(max(expected, prev + min_step), max_b)
        )
        bounds.append(b)
        prev = b
    edges = [0.0] + bounds + [total]
    durs = [round(max(edges[i + 1] - edges[i], min_step), 3) for i in range(n)]
    diff = round(total - sum(durs), 3)
    if durs:
        durs[-1] = round(max(0.2, durs[-1] + diff), 3)
    return durs


def _find_audio_with_mime(obj: Any) -> Tuple[Optional[str], str]:
    """Find (base64 audio, mime_type) inside an Interactions/generateContent response."""
    found: List[Tuple[str, str]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if o.get("type") == "audio" and isinstance(o.get("data"), str):
                found.append((o["data"], str(o.get("mime_type", o.get("mimeType", "")))))
            inline = o.get("inlineData") or o.get("inline_data")
            if isinstance(inline, dict):
                mime = str(inline.get("mimeType", inline.get("mime_type", "")))
                if mime.startswith("audio") and isinstance(inline.get("data"), str):
                    found.append((inline["data"], mime))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return found[-1] if found else (None, "")


def _find_audio_b64(obj: Any) -> Optional[str]:
    """Find base64 audio inside an Interactions/generateContent response."""
    data, _ = _find_audio_with_mime(obj)
    return data


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
    def __init__(
        self,
        api_key: str,
        models: List[str],
        voice: str = "auto",
        fallback_voice: str = "Charon",
        timeout: int = 180,
    ):
        self.api_key = api_key
        self.keys: List[str] = [k.strip() for k in (api_key or "").split(",") if k.strip()]
        self._ki: int = 0
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
                for params in (
                    {
                        "language_code": "hi-IN",
                        "context": "News",
                        "type": "prebuilt",
                        "gender": "male",
                    },
                    {"language_code": "hi-IN", "type": "prebuilt"},
                ):
                    r = requests.get(
                        f"{GEMINI_BASE}/voices", headers=self._headers(), params=params, timeout=20
                    )
                    if r.status_code == 200:
                        voices = r.json().get("voices") or []
                        if voices:
                            voice = (
                                voices[0].get("id")
                                or voices[0].get("name", "").split("/")[-1]
                                or voice
                            )
                            break
            except Exception as exc:
                logger.info("Voice library lookup failed (%s); using %s", exc, voice)
        self._resolved_voice = voice
        logger.info("Gemini TTS voice: %s", voice)
        return voice

    def _interactions(self, model: str, text: str, style: str, voice: str) -> bytes:
        body = {
            "model": model,
            "input": [
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [{"type": "speech_metadata", "style": style}],
                        }
                    ],
                }
            ],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]},
        }
        r = requests.post(
            f"{GEMINI_BASE}/interactions", headers=self._headers(), json=body, timeout=self.timeout
        )
        if r.status_code != 200:
            raise TTSError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
        data, mime = _find_audio_with_mime(r.json())
        if not data:
            raise TTSError(f"{model}: no audio in response")
        return base64.b64decode(data), mime

    def _generate_content(self, model: str, text: str, style: str, voice: str) -> Tuple[bytes, str]:
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": f"Read this Hindi text aloud in the style of a {style}:\n{text}"}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
            },
        }
        r = requests.post(
            f"{GEMINI_BASE}/models/{model}:generateContent",
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise TTSError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
        data, mime = _find_audio_with_mime(r.json())
        if not data:
            raise TTSError(f"{model}: no audio in response")
        return base64.b64decode(data), mime

    @staticmethod
    def _save_audio(audio: bytes, mime: str, out_wav: str) -> None:
        m = (mime or "").lower()
        encoded = (
            audio[:4] in (b"RIFF", b"OggS", b"fLaC")
            or audio[:3] == b"ID3"
            or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
            or any(ext in m for ext in ("mp3", "mpeg", "ogg", "opus", "aac", "flac", "mp4", "wav"))
        )
        if audio[:4] == b"RIFF":
            Path(out_wav).write_bytes(audio)
        elif encoded:
            raw_enc = Path(out_wav).with_suffix(".encoded")
            raw_enc.write_bytes(audio)
            ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
            try:
                res = subprocess.run(
                    [ffmpeg, "-y", "-i", str(raw_enc), "-ac", "1", "-ar", "24000", out_wav],
                    capture_output=True,
                    timeout=120,
                )
                if res.returncode != 0:
                    _write_pcm_wav(audio, out_wav)
            finally:
                raw_enc.unlink(missing_ok=True)
        else:
            _write_pcm_wav(audio, out_wav)

    def synthesize(self, text: str, style: str, out_wav: str) -> str:
        voice = self.resolve_voice()
        errors = []
        for model in self.models:
            for v in dict.fromkeys([voice, self.fallback_voice]):
                try:
                    if not model.startswith(("gemini-2.", "gemini-1.")):
                        audio, mime = self._interactions(model, text, style, v)
                    else:
                        audio, mime = self._generate_content(
                            model, re.sub(r"<[^>]+>", "...", text), style, v
                        )
                    self._save_audio(audio, mime, out_wav)
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
    def __init__(
        self,
        voice: str = "hi-IN-MadhurNeural",
        rate: str = "+5%",
        pitch: str = "+0Hz",
        fallback_voice: str = "hi-IN-SwaraNeural",
        strict: bool = False,
        provider_order: Optional[List[str]] = None,
        gemini: Optional[GeminiTTS] = None,
    ):
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
            communicate = edge_tts.Communicate(
                text=text, voice=voice, rate=self.rate, pitch=self.pitch, boundary="WordBoundary"
            )
        except TypeError:
            communicate = edge_tts.Communicate(
                text=text, voice=voice, rate=self.rate, pitch=self.pitch
            )
        words: List[WordTiming] = []
        with open(out_file, "wb") as fh:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append(
                        WordTiming(
                            word=chunk["text"],
                            start=round(start, 3),
                            end=round(start + chunk["duration"] / 1e7, 3),
                            confidence=1.0,
                            source="edge-tts",
                        )
                    )
        if not out_file.exists() or out_file.stat().st_size < 1000:
            raise TTSError("edge-tts returned no audio")
        return words

    @staticmethod
    def _trim_segment_silence(path: Path) -> Tuple[float, float]:
        """Trim long encoder silence padding at start/end to a crisp 0.08s breath pause.

        Returns (orig_duration, new_duration) so callers can rescale WordBoundary timings.
        """
        orig_dur = probe_duration(str(path))
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        tmp = path.with_suffix(".tmp.mp3")
        af = (
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-40dB,"
            "areverse,silenceremove=start_periods=1:start_duration=0.02:start_threshold=-40dB,areverse,"
            "apad=pad_dur=0.08"
        )
        res = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(path),
                "-af",
                af,
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(tmp),
            ],
            capture_output=True,
            timeout=60,
        )
        if res.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1000:
            tmp.replace(path)
            new_dur = probe_duration(str(path)) or orig_dur
            return orig_dur, new_dur
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return orig_dur, orig_dur

    @staticmethod
    def _rescale_trimmed_words(
        words: List[WordTiming], orig_dur: float, new_dur: float
    ) -> List[WordTiming]:
        """Shift/align captured WordBoundary timings cleanly after edge silence trim."""
        if not words or new_dur <= 0:
            return []
        lead = words[0].start
        # If leading silence (~lead) was trimmed down to near 0, shift left by ~lead
        trimmed_head = max(0.0, orig_dur - max(0.0, new_dur - 0.08))
        shift = min(lead, trimmed_head * 0.6) if orig_dur > new_dur else 0.0
        span = max((words[-1].end - words[0].start), 0.1)
        avail = max(new_dur - 0.08 - max(0.0, lead - shift), 0.1)
        ratio = min(1.15, avail / span) if span > avail else 1.0
        out: List[WordTiming] = []
        base = words[0].start
        start_anchor = max(0.0, base - shift)
        for w in words:
            st = round(start_anchor + (w.start - base) * ratio, 3)
            en = round(min(new_dur, max(st + 0.03, start_anchor + (w.end - base) * ratio)), 3)
            out.append(WordTiming(w.word, st, en, confidence=w.confidence, source=w.source))
        return out

    async def synthesize_segment(self, text: str, output_path: str) -> Segment:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        clean = re.sub(r"<[^>]+>", " ", text)
        last_exc: Optional[Exception] = None
        for attempt, voice in enumerate([self.voice, self.voice, self.fallback_voice]):
            try:
                words = await self._synth(clean, out_file, voice)
                orig_dur, duration = self._trim_segment_silence(out_file)
                duration = duration or (words[-1].end + 0.1 if words else 0.0)
                aligned_words = (
                    self._rescale_trimmed_words(words, orig_dur, duration)
                    if words
                    else distribute_words(clean, duration)
                )
                return Segment(
                    text=clean,
                    audio_path=str(out_file),
                    duration=duration,
                    words=aligned_words,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning("edge-tts attempt %d (%s) failed: %s", attempt + 1, voice, exc)
                await asyncio.sleep(2 * (attempt + 1))
        if self.gemini:
            try:
                raw_wav = str(out_file.with_suffix(".wav"))
                await asyncio.to_thread(
                    self.gemini.synthesize, clean, "clear Hindi TV news anchor", raw_wav
                )
                if Path(raw_wav).exists():
                    self._trim_segment_silence(Path(raw_wav))
                    duration = probe_duration(raw_wav)
                    return Segment(
                        text=clean,
                        audio_path=raw_wav,
                        duration=duration,
                        words=distribute_words(clean, duration),
                    )
            except Exception as g_exc:
                logger.warning("Segment Gemini fallback failed: %s", g_exc)
        if self.strict:
            raise TTSError(f"TTS failed after retries: {last_exc}")
        duration = max(0.85, len(clean.split()) / 2.65)
        self._silence(str(out_file), duration)
        logger.warning("Using SILENT placeholder audio (dry-run only) for: %s", clean[:40])
        return Segment(
            text=clean,
            audio_path=str(out_file),
            duration=duration,
            words=distribute_words(clean, duration),
        )

    async def synthesize_segments(self, texts: List[str], out_dir: str) -> List[Segment]:
        segments = []
        for i, t in enumerate(texts):
            seg = await self.synthesize_segment(t, str(Path(out_dir) / f"voice_{i:02d}.mp3"))
            segments.append(seg)
            if i < len(texts) - 1:
                await asyncio.sleep(0.12)
        return segments

    @staticmethod
    def _join_continuous_beats(texts: List[str], owner_ids: Optional[List[Any]] = None) -> str:
        """Join beats cleanly: space within a sentence/story, newline across distinct beats."""
        out: List[str] = []
        for idx, raw in enumerate(texts):
            s = re.sub(r"<[^>]+>", " ", (raw or "")).strip()
            if not s:
                s = "।"
            same_owner_next = (
                owner_ids is not None
                and idx + 1 < len(texts)
                and owner_ids[idx] == owner_ids[idx + 1]
            )
            if not same_owner_next and s[-1] not in "।.?!":
                s += "।"
            out.append(s)
            if idx + 1 < len(texts):
                out.append(" " if same_owner_next else "\n")
        return "".join(out)

    @staticmethod
    def _align_continuous_boundaries(
        texts: List[str], boundary_words: List[WordTiming], total_duration: float
    ) -> Tuple[List[float], List[List[WordTiming]]]:
        """Map single-pass WordBoundary events to each beat and extract exact segment spans."""
        if not texts:
            return [], []

        def _norm(tok: str) -> str:
            return re.sub(r"[^\w\u0900-\u097F]", "", (tok or "").lower())

        # Expand multi-word boundary tokens (e.g. '27 नवंबर 2026') so cursor matches word-by-word
        expanded: List[WordTiming] = []
        for bw in boundary_words:
            parts = (bw.word or "").split()
            if len(parts) <= 1:
                if bw.word.strip():
                    expanded.append(bw)
            else:
                weights = [max(len(p), 1) for p in parts]
                wsum = float(sum(weights))
                cur_t = bw.start
                span = max(0.04, bw.end - bw.start)
                for p, wt in zip(parts, weights):
                    pd = span * wt / wsum
                    expanded.append(
                        WordTiming(
                            word=p,
                            start=round(cur_t, 3),
                            end=round(cur_t + pd, 3),
                            confidence=bw.confidence,
                            source=bw.source,
                        )
                    )
                    cur_t += pd

        if not expanded:
            durs = split_by_pauses(texts, total_duration, [])
            bwords, cur = [], 0.0
            for t, d in zip(texts, durs):
                bwords.append(distribute_words(re.sub(r"<[^>]+>", " ", t).strip(), d, offset=cur))
                cur += d
            return durs, bwords

        exp_norms = [_norm(w.word) for w in expanded]
        cursor = 0
        seg_ranges: List[Tuple[int, int]] = []
        total_exp = len(expanded)

        for idx, t in enumerate(texts):
            clean_t = re.sub(r"<[^>]+>", " ", (t or "")).strip()
            toks = [_norm(x) for x in clean_t.split() if _norm(x)]
            if not toks:
                seg_ranges.append((min(cursor, total_exp - 1), min(cursor, total_exp - 1)))
                continue

            # Snap start if small token drift occurred on numbers/symbols
            if cursor < total_exp and exp_norms[cursor] != toks[0]:
                for look in range(cursor, min(total_exp, cursor + 5)):
                    if exp_norms[look] == toks[0]:
                        cursor = look
                        break

            start_i = cursor
            # Consume expected number of tokens, bounded cleanly by next beat's anchor word
            next_anchor = ""
            if idx + 1 < len(texts):
                next_toks = [
                    _norm(x) for x in re.sub(r"<[^>]+>", " ", texts[idx + 1]).split() if _norm(x)
                ]
                next_anchor = next_toks[0] if next_toks else ""

            matched = 0
            while cursor < total_exp and matched < len(toks):
                # Look ahead briefly if normalized word doesn't match directly (e.g. expanded digit)
                target_tok = toks[matched]
                if exp_norms[cursor] == target_tok:
                    cursor += 1
                    matched += 1
                    continue
                if next_anchor and matched > 0 and exp_norms[cursor] == next_anchor and (len(toks) - matched) <= 2:
                    break
                cursor += 1
                matched += 1

            end_i = max(start_i + 1, cursor) if start_i < total_exp else total_exp
            seg_ranges.append((min(start_i, total_exp - 1), min(end_i, total_exp)))

        # Convert aligned word indices into contiguous segment start/end times
        seg_starts: List[float] = [0.0]
        for idx in range(1, len(texts)):
            s_i, e_i = seg_ranges[idx]
            prev_s, prev_e = seg_ranges[idx - 1]
            if s_i < total_exp and expanded[s_i].start > seg_starts[-1] + 0.05:
                st = expanded[s_i].start
            elif prev_e < total_exp:
                st = max(seg_starts[-1] + 0.15, expanded[prev_e - 1].end)
            else:
                st = seg_starts[-1] + 0.2
            seg_starts.append(min(st, max(0.0, total_duration - 0.15 * (len(texts) - idx))))

        durs: List[float] = []
        beat_words: List[List[WordTiming]] = []
        for idx, (s_i, e_i) in enumerate(seg_ranges):
            st = seg_starts[idx]
            en = seg_starts[idx + 1] if idx + 1 < len(seg_starts) else total_duration
            d = round(max(0.15, en - st), 3)
            durs.append(d)
            bw_slice = [
                WordTiming(
                    w.word,
                    round(max(st, min(en, w.start)), 3),
                    round(max(st + 0.03, min(en, w.end)), 3),
                    confidence=w.confidence,
                    source=w.source,
                )
                for w in expanded[s_i:e_i]
            ]
            if not bw_slice:
                clean_t = re.sub(r"<[^>]+>", " ", (texts[idx] or "")).strip()
                bw_slice = distribute_words(clean_t, d, offset=st, source="edge-tts", confidence=0.8)
            beat_words.append(bw_slice)

        if durs and total_duration > 0:
            diff = round(total_duration - sum(durs), 3)
            durs[-1] = round(max(0.15, durs[-1] + diff), 3)
        return durs, beat_words

    # -- main API ------------------------------------------------------------
    async def voice_beats(
        self,
        texts: List[str],
        out_dir: str,
        style: str = "",
        owner_ids: Optional[List[Any]] = None,
    ) -> VoiceResult:
        """Voice all beats; returns the full track and per-beat durations."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        final = str(out / "voiceover.m4a")
        for provider in self.provider_order:
            if provider == "gemini" and self.gemini:
                try:
                    joined = self._join_continuous_beats(texts, owner_ids=owner_ids)
                    raw = str(out / "voice_gemini.wav")
                    model = await asyncio.to_thread(self.gemini.synthesize, joined, style, raw)
                    self._normalise(raw, final)
                    total = probe_duration(final)
                    if total <= 0:
                        raise TTSError("gemini normalised audio has zero duration")
                    durs = split_by_pauses(texts, total, detect_silences(final))
                    whisper_words = await asyncio.to_thread(align_with_whisper, final, joined)
                    beat_words: List[List[WordTiming]] = []
                    cursor = 0.0
                    for t, d in zip(texts, durs):
                        clean_t = re.sub(r"<[^>]+>", " ", t).strip()
                        if whisper_words:
                            matching = [w for w in whisper_words if cursor - 0.1 <= w.start <= cursor + d + 0.1]
                            if matching:
                                beat_words.append(matching)
                            else:
                                beat_words.append(
                                    distribute_words(clean_t, d, offset=cursor, source="proportional", confidence=0.5)
                                )
                        else:
                            beat_words.append(
                                distribute_words(clean_t, d, offset=cursor, source="proportional", confidence=0.5)
                            )
                        cursor += d
                    return VoiceResult(final, durs, f"gemini:{model}", beat_words=beat_words)
                except Exception as exc:
                    logger.warning("Gemini TTS unavailable, falling back: %s", str(exc)[:200])
            elif provider == "edge":
                # Prefer coherent single-pass synthesis so anchor prosody flows naturally
                # across sentences instead of restarting pitch every 3-5 words.
                joined = self._join_continuous_beats(texts, owner_ids=owner_ids)
                raw_mp3 = out / "voice_full.mp3"
                words_full: Optional[List[WordTiming]] = None
                for attempt, voice in enumerate([self.voice, self.voice, self.fallback_voice]):
                    try:
                        words_full = await self._synth(joined, raw_mp3, voice)
                        break
                    except Exception as exc:
                        logger.warning(
                            "continuous edge-tts attempt %d (%s) failed: %s",
                            attempt + 1,
                            voice,
                            exc,
                        )
                        if attempt < 2:
                            await asyncio.sleep(2 * (attempt + 1))

                if raw_mp3.exists() and raw_mp3.stat().st_size > 1000:
                    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
                    res = subprocess.run(
                        [
                            ffmpeg,
                            "-y",
                            "-i",
                            str(raw_mp3),
                            "-af",
                            "aresample=44100,aformat=channel_layouts=stereo",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "192k",
                            final,
                        ],
                        capture_output=True,
                        timeout=120,
                    )
                    if res.returncode == 0 and Path(final).exists():
                        actual_total = probe_duration(final)
                        if actual_total > 0 and words_full:
                            durs, beat_words = self._align_continuous_boundaries(
                                texts, words_full, actual_total
                            )
                            return VoiceResult(final, durs, "edge-tts", beat_words=beat_words)
                        if actual_total > 0:
                            durs = split_by_pauses(texts, actual_total, detect_silences(final))
                            beat_words, cursor = [], 0.0
                            for t, d in zip(texts, durs):
                                beat_words.append(distribute_words(t, d, offset=cursor))
                                cursor += d
                            return VoiceResult(final, durs, "edge-tts", beat_words=beat_words)

                # Safe fallback: per-segment synthesis (also covers offline dry-run silence path)
                segs = await self.synthesize_segments(texts, out_dir)
                self.concat_audio(segs, final)
                raw_durs = [max(s.duration, 0.2) for s in segs]
                actual_total = probe_duration(final)
                raw_sum = sum(raw_durs)
                if actual_total > 0 and raw_sum > 0:
                    scale = actual_total / raw_sum
                    durs = [round(d * scale, 3) for d in raw_durs]
                    if durs:
                        durs[-1] = round(max(0.2, durs[-1] + (actual_total - sum(durs))), 3)
                else:
                    scale = 1.0
                    durs = [round(d, 3) for d in raw_durs]
                beat_words = []
                cursor = 0.0
                for s, d in zip(segs, durs):
                    s_words = []
                    if s.words and s.duration > 0:
                        wscale = d / s.duration
                        for w in s.words:
                            st = round(cursor + w.start * wscale, 3)
                            en = round(min(cursor + d, max(st + 0.04, cursor + w.end * wscale)), 3)
                            s_words.append(WordTiming(w.word, st, en))
                    else:
                        s_words = distribute_words(s.text, d, offset=cursor)
                    beat_words.append(s_words)
                    cursor += d
                return VoiceResult(final, durs, "edge-tts", beat_words=beat_words)
        raise TTSError("No TTS provider produced audio")

    @staticmethod
    def _normalise(src: str, dst: str) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        # trim leading/trailing silence, keep natural pauses inside
        af = (
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
            "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
            "aresample=44100,aformat=channel_layouts=stereo"
        )
        res = subprocess.run(
            [ffmpeg, "-y", "-i", src, "-af", af, "-c:a", "aac", "-b:a", "192k", dst],
            capture_output=True,
            timeout=120,
        )
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
        filt = "".join(
            f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];" for i in range(n)
        )
        filt += "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        res = subprocess.run(
            [
                ffmpeg,
                "-y",
                *inputs,
                "-filter_complex",
                filt,
                "-map",
                "[out]",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                output_path,
            ],
            capture_output=True,
            timeout=180,
        )
        if res.returncode != 0:
            raise TTSError(res.stderr.decode(errors="ignore")[-400:])
        return output_path

    @staticmethod
    def _silence(output_path: str, duration: float) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                f"{duration:.2f}",
                "-acodec",
                "libmp3lame",
                output_path,
            ],
            capture_output=True,
            timeout=60,
        )

    async def generate_audio(self, text: str, output_path: str) -> str:
        return (await self.synthesize_segment(text, output_path)).audio_path

    @staticmethod
    def dump_timings(texts: List[str], durations: List[float], provider: str, path: str) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "provider": provider,
                    "beats": [{"text": t, "duration": d} for t, d in zip(texts, durations)],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
