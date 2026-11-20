# Broadcast Audio & News Sound Design — Technical Documentation

## 1. Overview & Mission

`AudioSoundDesignAgent` directs broadcast-grade sound design and multi-track audio engineering for **BHARAT KI SOCH**. It schedules broadcast sound effects, manages voice-prioritized music ducking, and builds an authoritative `AudioMixPlan`.

Location: `agents/audio_sound_design/agent.py`  
Asset Directory: `assets/sfx/`  
Manifest: `assets/sfx/manifest.json`  
Contracts: `AudioMixPlan`, `SoundCueContract` in `core/agent_contracts.py`  
Unit Tests: `tests/test_agents/test_audio_sound_design.py`

---

## 2. Broadcast Sound Effects Library (`assets/sfx/`)

All SFX are synthesized locally or released under CC0/Original licensing, requiring zero external paid downloads:

| Cue ID | File | Category | Type | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `cue_news_intro_sting` | `sting_news_intro.wav` | news_stings | sting | High-urgency brass/synth news opener |
| `cue_transition_whoosh` | `transition_whoosh.wav` | transitions | whoosh | Fast camera wipe between news beats |
| `cue_bulletin_impact` | `impact_bulletin.wav` | news_stings | impact | Sub-bass impact for breaking facts |
| `cue_headline_reveal` | `headline_reveal.wav` | transitions | reveal | Graphic lower-third strap unmasking |
| `cue_ticker_blip` | `ticker_blip.wav` | ui_sound | blip | Subtle periodic news ticker notification |
| `bed_daily_news` | `news_bed_loop.wav` | news_beds | bed | Low-profile rhythmic news background bed |
| `cue_bulletin_closing`| `ending_sting.wav` | news_stings | sting | Authoritative channel sign-off sting |

---

## 3. Sidechain Ducking & Voice Prioritization

Using FFmpeg audio filters (`amix`, `volume`, `afade`), voice narration is prioritized:
- Default music bed volume: `0.10` (-20 dB).
- Ducked volume during speech: `0.03` (-24 dB to -30 dB).
- Target broadcast loudness: `-14.0 LUFS`.
- True-peak limiter: `-1.0 dBFS`.
- Smooth fade-out in final 1.5 seconds.
