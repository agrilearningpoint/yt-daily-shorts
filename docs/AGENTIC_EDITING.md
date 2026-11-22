# Agentic Editing Workflow

## 1. Concept: Deterministic Autonomous Editing
Traditional AI video generation often relies on prompt-and-pray loops, where an LLM generates raw parameters and hopes the output renders correctly.

The **Agentic Editing Workflow** in BHARAT KI SOCH operates like **Claude Code / OpenCode**:
It couples an LLM orchestrator with **deterministic repository tools** (`tools/word_cut_cli.py`, `video/word_timeline.py`, `video/word_cut_qa.py`, FFmpeg).

```
[Script & Voiceover]
        │
        ▼
   [ 1. Plan ] ──────► Generates WordCutPlan (Frame-accurate tokens & cuts)
        │
        ▼
  [ 2. Render ] ─────► Video-only contiguous cuts + single-pass master audio mux
        │
        ▼
    [ 3. QA ] ───────► Independent verification (coverage, drift, gaps, duration)
        │
   Pass? │ No
  ───────┴────────► [ 4. Analyze & Repair ] (Auto-close gaps, merge sub-frames)
        │                     │
        ▼                     ▼
[ 5. Approve ] ◄────── [ Re-render ] (Max 3 iterations)
```

---

## 2. Deterministic Fix Rules (No Hallucinations)
When QA detects a defect, the agent applies strict mathematical fixes:
1. **Visual Gaps (`diff > 1 frame`)**: Extends previous cut end timestamp to current cut start.
2. **Visual Overlaps (`diff < -1 frame`)**: Snaps current cut start to previous cut end.
3. **Sub-Frame Cuts (`duration < 66ms`)**: Merges the tiny cut into its preceding neighbor.
4. **Duration Drift**: Clamps final cut to the exact audio duration.

---

## 3. Tool Reference

### Word Cut CLI (`tools/word_cut_cli.py`)
- `python tools/word_cut_cli.py plan --script ... --out plan.json`
- `python tools/word_cut_cli.py render --plan plan.json --out video.mp4`
- `python tools/word_cut_cli.py qa --plan plan.json --video video.mp4 --report qa.json`

### Agentic Loop Script (`scripts/agent_edit.py`)
Runs the full plan-render-QA-repair cycle automatically:
```bash
python scripts/agent_edit.py --script "मेरा नाम सिंह है" --audio data/voice.wav
```
Outputs `output/agent_edit/edit_report.json` with comprehensive audit trails.

### Model Context Protocol Server (`tools/mcp_server.py`)
Exposes tools over standard MCP protocol:
- `word_cut_plan`
- `word_cut_render`
- `word_cut_qa`
- `youtube_upload`
