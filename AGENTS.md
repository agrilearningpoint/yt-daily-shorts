# AGENTS.md — Developer & AI Agent Operations Manual

## 1. Project Overview
**BHARAT KI SOCH (`yt-daily-shorts`)** is an autonomous Hindi AI production studio generating 2 daily YouTube Shorts:
1. Morning: National, International & Geopolitical News Bulletin (Target: 56s, Safe Max: 59.5s).
2. Evening: Deeply researched Knowledge, Heritage, or Science topic.

The production system runs on GitHub Actions and local workstations using zero-cost free-tier APIs (Gemini, Groq, Mistral, edge-tts, Wikipedia, Wikimedia, Pexels, Pixabay, FFmpeg).

---

## 2. Standard Commands
```bash
# Linting & Formatting
python -m ruff check .
python -m ruff check . --fix

# Automated Test Suite
python -m pytest -q
python -m pytest tests/test_word_timeline.py
python -m pytest tests/test_word_cut_renderer.py
python -m pytest tests/test_word_cut_qa.py

# CLI Word-Level Cuts
python tools/word_cut_cli.py plan --script "मेरा नाम सिंह है" --audio data/voice.wav --out plan.json
python tools/word_cut_cli.py render --plan plan.json --out output/short.mp4
python tools/word_cut_cli.py qa --plan plan.json --video output/short.mp4 --report qa.json

# Autonomous Agentic Editing Loop
python scripts/agent_edit.py --script script.txt --audio voice.wav
```

---

## 3. Architecture Map
- `video/word_timeline.py`: Devanagari & Latin tokenization, CUT/GLUE classification, and frame-accurate word grouping.
- `video/word_cut_qa.py`: Coverage, drift, monotonicity, duration, and audio continuity validation.
- `video/renderer.py`: Contiguous visual segment rendering, ASS word-level caption burning, and single-pass master audio muxing.
- `video/tts.py`: Speech synthesis (`edge-tts` with WordBoundary chunks, Gemini TTS with Whisper alignment fallback).
- `video/subtitle_generator.py`: ASS karaoke-style highlighted subtitles with Mukta Devanagari font.
- `agents/video_producer/agent.py`: High-level producer orchestrating tiles, voiceover, and word cuts behind `video.word_level_cuts` feature flag.
- `agents/visual_audio_match_qa/agent.py`: Multi-pillar QA gate enforcing broadcast standards and blocking defective renders.
- `core/agent_contracts.py`: Dataclass contracts (`WordCut`, `WordCutPlan`, `MasterEditingTimeline`, `VisualAudioMatchResult`).
- `config/settings.yaml`: Runtime settings, duration limits, and feature flags.

---

## 4. Smart Word-Level Cuts Spec
- **Rule 1 (Audio Continuity)**: Master voiceover audio is NEVER cut or spliced per word. It plays continuously as one unified track.
- **Rule 2 (Visual Timeline)**: Visual cuts occur at word/group boundaries (`cut[i].start == cut[i-1].end`).
- **Rule 3 (Function Words Glue)**: Prepositions, postpositions, and auxiliaries are glued to adjacent content words.
  - "my name is singh" -> 3 cuts: `[my]`, `[name]`, `[is singh]`.
  - "मेरा नाम सिंह है" -> 3 cuts: `[मेरा]`, `[नाम]`, `[सिंह है]`.
- **Rule 4 (No Gaps or Flashes)**: Minimum duration is 2 frames (66ms @ 30fps). Gaps between words hold the preceding visual.
- **Rule 5 (Feature Flag)**: Controlled via `video.word_level_cuts: false` (default) in `config/settings.yaml`. When disabled, the existing beat-level renderer runs unchanged.

---

## 5. Coding Standards & Guardrails
- **Language**: Python 3.11+.
- **Formatting**: Zero Ruff errors (`python -m ruff check .` must return 0).
- **Test Integrity**: All existing tests must pass (197+ tests).
- **Safe Commits**: Make atomic, descriptive git commits per phase.
- **No Paid APIs**: Maintain zero-budget architecture using free tiers and local FFmpeg.
- **No Fabricated Data**: Always base facts on verified sources; attribution for CC media.
