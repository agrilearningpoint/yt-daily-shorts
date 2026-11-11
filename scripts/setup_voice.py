"""One knob for the channel voice: pick the voice, set the speed, prove it works.

    python scripts/setup_voice.py                 # dry run: list what would change
    python scripts/setup_voice.py --apply         # write config/settings.yaml
    python scripts/setup_voice.py --rate +15% --apply
    python scripts/setup_voice.py --test          # synthesise 2 s with the real API

Voice speed lives in exactly one place — ``tts.rate`` in config/settings.yaml.
Providers read it, nothing hardcodes it:
  * edge-tts  uses it as-is (e.g. "+15%")
  * Gemini TTS has no rate parameter, so the style string is rewritten to say it
    in words ("fast, brisk pace"), which is what actually made the anchor drag.
"""
from __future__ import annotations

import os

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
SETTINGS = ROOT / "config" / "settings.yaml"

PACE_WORDS = {
    "normal": "a steady, normal pace",
    "fast": "a brisk, fast pace — clearly quicker than normal but every word still clear",
    "slow": "a slow, deliberate pace with clear pauses",
}


def parse_percent(rate: str) -> int:
    m = re.match(r"\s*([+-]?\d+)\s*%?\s*$", rate or "")
    return int(m.group(1)) if m else 0


def pace_for(percent: int) -> str:
    if percent <= -4:
        return "slow"
    if percent >= 8:
        return "fast"
    return "normal"


def rewrite_style(style: str, percent: int) -> str:
    """Swap only the pace part of the prompt; keep every other quality hint intact."""
    wanted = PACE_WORDS[pace_for(percent)]
    pace_re = re.compile(r"(^|,\s*)(a\s+)?(steady|calm|normal|medium|slow|fast|brisk|quick|rapid)"
                         r"[, ]*(pace|tempo|speed|crisp delivery|deliberate)?[^,]*", re.I)
    parts = [p.strip() for p in style.split(",")]
    kept = [p for p in parts if p and not pace_re.match(p)]
    kept.append(wanted)
    return ", ".join(kept)


def plan(rate: str, voice: str | None, dry_run: bool) -> list[str]:
    from ruamel.yaml import YAML

    y = YAML()
    y.preserve_quotes = True
    data = y.load(SETTINGS.read_text(encoding="utf-8")) or {}
    tts = data.setdefault("tts", {})
    pct = parse_percent(rate)
    changes = []
    if voice and tts.get("voice") != voice:
        changes.append(f"tts.voice: {tts.get('voice')} -> {voice}")
        tts["voice"] = voice
    if str(tts.get("rate")) != rate:
        changes.append(f"tts.rate: {tts.get('rate')} -> {rate}")
        tts["rate"] = rate
    for key in ("news_style", "knowledge_style"):
        old = str(tts.get(key) or "")
        new = rewrite_style(old, pct)
        if old != new:
            changes.append(f"tts.{key}: rewritten for {pace_for(pct)}")
            tts[key] = new
    if changes and not dry_run:
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            y.dump(data, fh)
    return changes


def test_voice(rate: str) -> int:
    """Synthesise one short line with the configured voice and report the real speed."""
    from video.tts import TTSEngine, probe_duration

    text = ("नमस्कार दोस्तों, आज हम भारत के इतिहास की एक ऐसी कहानी सुनेंगे जो आपको हैरान कर देगी। "
            "यह कहानी शुरू होती है चार हज़ार साल पहले।")
    out = Path("/tmp/voice_test.mp3")
    tts = TTSEngine(voice="hi-IN-MadhurNeural", rate=rate)
    asyncio.run(tts.synthesize_segment(text, str(out)))
    dur = probe_duration(str(out)) or 0
    words = len(text.split())
    wpm = words / dur * 60 if dur else 0
    print(f"rate={rate}  audio={dur:.1f}s  words={words}  -> {wpm:.0f} words/min")
    return 0 if wpm > 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="setup_voice")
    ap.add_argument("--rate", default="+0%", help='edge-tts rate, e.g. "+0%%", "+15%%", "-5%%"')
    ap.add_argument("--voice", default="", help="e.g. hi-IN-MadhurNeural")
    ap.add_argument("--apply", action="store_true", help="write config/settings.yaml")
    ap.add_argument("--test", action="store_true", help="synthesise 2 s and print real words/min")
    a = ap.parse_args()
    changes = plan(a.rate, a.voice or None, dry_run=not a.apply)
    for c in changes:
        print(("written: " if a.apply else "would change: ") + c)
    if not changes:
        print(f"already set: rate={a.rate}" + (f" voice={a.voice}" if a.voice else ""))
    if a.test:
        return test_voice(a.rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
