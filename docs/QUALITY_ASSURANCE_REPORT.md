# Multi-Pillar Quality Assurance Report

## Overview
Quality assurance in **BHARAT KI SOCH** automation operates across three distinct tiers: Pre-Render Editorial Gates, Synchronization Gates, and Independent Post-Render Video Inspection (`video/qa_inspector.py`). Videos that fail critical broadcast thresholds are blocked from publication or automatically repaired.

---

## 1. Quality Assurance Pipeline

```mermaid
flowchart TD
    subgraph Tier1 ["Tier 1: Pre-Render Editorial Gates"]
        A[Fact Verifier Agent] -->|Verification Score >= 80%| B[Quality Manager Agent]
        B -->|Readability & Density Pass| C[Hook Director Agent]
        C -->|Hook Quality Score >= 75| D[Approved Narrative]
    end

    subgraph Tier2 ["Tier 2: Timeline Synchronization Gates"]
        D --> E[Synchronization Engine]
        E -->|Drift < 0.05s & 100% Visuals Bound| F[Approved Master Timeline]
    end

    subgraph Tier3 ["Tier 3: Independent Post-Render Inspection"]
        F --> G[Video QA Inspector]
        G --> H{Pass All 5 Pillars?}
        H -->|Yes (Verdict: PASS / WARN)| I[Publisher Agent]
        H -->|Duration Overflow| J[Auto-Repair Trimming]
        J --> G
        H -->|Critical Failure| K[Halt Run & Send Telegram Alert]
    end
```

---

## 2. Five Pillars of Post-Render Inspection

Every rendered MP4 file is inspected by `VideoQAInspector` before publishing:

| Pillar | Inspection Method | Passing Standard | Tolerance / Auto-Repair |
| :--- | :--- | :--- | :--- |
| **1. Technical** | `ffprobe -show_streams` | $1080 \times 1920$ resolution, H.264 codec, $30 \pm 1$ FPS, file size $> 200\text{ KB}$. | Strict failure if resolution or codec invalid. |
| **2. Audio** | Stream probe & silence check | AAC audio, 44.1 kHz or 48 kHz, stereo/mono, no extended unvoiced gaps. | Non-standard codec flagged as warning. |
| **3. Duration** | `format=duration` ffprobe | $45.0\text{s} \le \text{Duration} \le 59.9\text{s}$ for Shorts format. | If $60.0\text{s} < \text{Duration} \le 63.0\text{s}$, auto-trimmed to $59.5\text{s}$. |
| **4. Synchronization** | Audio duration vs Video duration | $|Duration_{video} - Duration_{audio}| \le 0.10\text{s}$. | Drift $> 0.10\text{s}$ flagged as warning. |
| **5. Visual Defect** | FFmpeg `blackdetect` filter | Zero black screen stretches $\ge 0.8\text{s}$. | Black frames penalize visual score by 15 pts each. |

---

## 3. Sample QA Verification Output

```json
{
  "verdict": "PASS",
  "overall_score": 96.0,
  "pillar_scores": {
    "technical": 100.0,
    "visual": 95.0,
    "audio": 100.0,
    "sync": 95.0,
    "duration": 100.0
  },
  "critical_failures": [],
  "warnings": [
    "Container audio/video stream duration difference 0.042s within tolerance 0.10s"
  ],
  "auto_repair_attempted": false,
  "auto_repair_succeeded": false
}
```

---

## 4. Pre-Render Editorial Verification Matrix

1. **Fact Checking (`FactVerifierAgent`)**:
   - Cross-references every scene against verified news sources.
   - Rejects or auto-corrects fabricated dates, numbers, or names.
   - Requires $\ge 80\%$ fact grounding score.

2. **Hook Verification (`HookDirectorAgent`)**:
   - Evaluates 6 viral archetypes with 6 weighted scoring dimensions.
   - Requires $\ge 75/100$ quality score.
   - Enforces visual pairing contract binding the opening visual to the lead entity.

3. **Duration Calibration (`core/duration.py`)**:
   - Uses unified rate of 2.4 words per second.
   - Calibrates 20+ news headlines at 5–8 words per story to guarantee completion within 50–58 seconds.
