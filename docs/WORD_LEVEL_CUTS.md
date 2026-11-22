# Smart Word-Level Visual Cuts Specification

## 1. Overview
Smart Word-Level Visual Cuts is a high-retention video editing technique designed for viral YouTube Shorts and dynamic long-form videos.

Instead of holding one static frame or slowly panning for 3–5 seconds per sentence, the video cuts visually with the rhythm of natural speech. Crucially, **the audio track is never cut**—the human-sounding Hindi voiceover continues seamlessly from beginning to end.

---

## 2. Core Principles

### Principle 1: Continuous Audio Master
- Audio is synthesized in a single take or stitched cleanly once.
- Visuals cut at word boundaries, but the voiceover never stutters, crossfades, or cuts.
- Audio muxing is performed as a single lossless stream:
  ```bash
  ffmpeg -i video_only.mp4 -i voiceover.m4a -c:v copy -c:a aac -b:a 192k -shortest final.mp4
  ```

### Principle 2: Content Word Anchoring & Function Word Gluing
Flash frames (cuts shorter than 100ms) feel like visual glitches to the human eye. To keep edits looking natural and cinematic:
- **Content Words (Nouns, Main Verbs, Adjectives, Adverbs, Numbers)** act as **CUT Anchors**.
- **Function / Helping Words (Articles, Prepositions, Conjunctions, Auxiliaries)** are **GLUED** to an adjacent anchor.

#### Examples:
1. **English**:
   - Script: `"my name is singh"`
   - Classification: `my` (CUT), `name` (CUT), `is` (GLUE), `singh` (CUT)
   - Groups: `[my]`, `[name]`, `[is singh]` -> **3 cuts**

2. **Hindi**:
   - Script: `"मेरा नाम सिंह है"`
   - Classification: `मेरा` (CUT), `नाम` (CUT), `सिंह` (CUT), `है` (GLUE)
   - Groups: `[मेरा]`, `[नाम]`, `[सिंह है]` -> **3 cuts**

---

## 3. Configuration

In `config/settings.yaml`:
```yaml
video:
  word_level_cuts: false          # Feature flag (default: false for backward compatibility)
  word_cut_max_group_seconds: 1.2 # Maximum duration of a visual cut before splitting
  word_cut_max_words_per_group: 3 # Maximum words per visual cut group
  word_cut_min_group_ms: 66       # Minimum group duration (2 frames @ 30fps)
  word_cut_min_confidence: 0.5    # Minimum timestamp confidence threshold
  word_cut_glue_policy: "auto"    # auto | attach_next | attach_prev
  word_cut_longform_phrase_mode: true # For >60s videos, groups into phrases to limit clip count
```

---

## 4. Devanagari Typography & Captions
- Captions use the bundled **Mukta ExtraBold** (`assets/fonts/Mukta-Bold.ttf`) font.
- Hindi conjuncts (`क्ष`, `त्र`, `ज्ञ`, `श्र`, `न्ह`, `त्स`) and matras are preserved without letter-spacing artifacts.
- Highlight styling uses ASS karaoke tags (`\k`) or dialogue color overrides (`\c&H00FFFF&`).

---

## 5. Limitations & Edge Cases
1. **Extreme Fast Speech**: If speech rate exceeds 4 words per second, `word_cut_min_group_ms` (66ms) merges adjacent words automatically so clips never breach the 2-frame hardware limit.
2. **Long-Form Videos (>60s)**: A 10-minute video with pure word-level cuts would generate 2,500 clips. Enabling `word_cut_longform_phrase_mode: true` groups words into phrases (2–3 seconds), keeping total clips manageable and rendering fast.
