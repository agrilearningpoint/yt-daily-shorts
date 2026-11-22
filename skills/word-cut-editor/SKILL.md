---
name: word-cut-editor
description: Autonomous editing skill for smart word-level visual cuts with continuous audio
---

# Word Cut Editor Skill

## Overview
This skill provides automated, high-retention video editing where every content word triggers a fresh visual cut while the master voiceover audio remains one continuous, uninterrupted stream. Helping and function words are naturally glued to adjacent content words.

## Core Rules & Non-Negotiables
1. **Continuous Audio Track**: Never slice, crossfade, or dice the audio per word. The master voiceover audio is recorded in one take and muxed continuously.
2. **100% Word Coverage**: Every script word must appear exactly once in the visual cut timeline.
3. **Contiguous Visual Cuts**: No visual gap between groups (`cut[i].start == cut[i-1].end`). If there is an audio pause, hold the previous visual.
4. **Frame Snapping**: All cut points snap to the 30 FPS frame grid (multiples of 33.3ms).
5. **Minimum Group Duration**: No visual group shorter than 2 frames (66ms).

## Step-by-Step Workflow

### Step 1: Planning
Generate the word-level cut plan using `WordTimelineBuilder` or CLI:
```bash
python tools/word_cut_cli.py plan --script "मेरा नाम सिंह है" --audio data/voice.wav --out word_plan.json
```

### Step 2: Rendering
Render the contiguous visual segments and mux the continuous audio:
```bash
python tools/word_cut_cli.py render --plan word_plan.json --out final_short.mp4
```

### Step 3: Verification & QA
Validate the output against broadcast standards:
```bash
python tools/word_cut_cli.py qa --plan word_plan.json --video final_short.mp4 --report qa_report.json
```

### Step 4: Iterative Loop (Agentic)
For autonomous optimization with deterministic repairs:
```bash
python scripts/agent_edit.py --script "मेरा नाम सिंह है" --audio data/voice.wav
```

## QA Checklist
- [ ] Every script word accounted for (0 missing, 0 duplicates).
- [ ] No visual gap > 1 frame.
- [ ] Word onset drift ≤ 50ms.
- [ ] Master audio duration matches video duration (±0.1s).
- [ ] ASS captions highlight active word without clipping.
- [ ] Total Shorts duration strictly within 15.0s – 59.5s.
