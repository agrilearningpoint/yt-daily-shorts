# BHARAT KI SOCH — Long Video Intelligence & Shorts Repurposing Architecture

**Document Version:** 1.0.0  
**Phase:** Phase 1 Architectural Design  
**Target Platform:** YouTube Shorts (9:16 Vertical, 1080×1920, 30 FPS, Devanagari Hindi)  
**System Classification:** Autonomous Multi-Agent Content Intelligence & Repurposing Pipeline  
**Date:** November 2026

---

## 1. System Vision & Objective

The **Long Video Intelligence & Shorts Repurposing Agent System** transforms long-format Hindi audiovisual broadcasts (such as 30–60 minute news bulletins, parliamentary proceedings, press conferences, one-on-one interviews, and policy addresses) into a fleet of independent, high-retention, contextually verified YouTube Shorts.

Unlike simplistic clipping tools that merely cut video at fixed time intervals, this system operates as an editorial newsroom and creative studio of 9 specialist AI agents. It understands the full narrative, separates disparate stories, independently verifies facts against authoritative government and journalistic records, scores virality potential using a 9-factor weighted matrix, isolates the most potent soundbites, writes culturally resonant Devanagari Hindi scripts, and guarantees copyright safety through fair use assessment and attribution formatting.

---

## 2. Architectural Blueprint & Information Flow

```
                                [ Long Video Source ]
                             (Local MP4/MKV or Web URL)
                                         │
                                         ▼
                            ┌─────────────────────────┐
                            │  LongVideoIntakeAgent   │
                            └────────────┬────────────┘
                                         │
                                         ▼
                               [ SourceVideoManifest ]
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
   ┌───────────────────────────┐                   ┌───────────────────────────┐
   │TranscriptionDiarization   │                   │ SceneUnderstandingAgent   │
   │Agent (STT, Word Timings,  │                   │ (Shot Boundaries, OCR,    │
   │Speaker Diarization)       │                   │ Keyframes, 9:16 Crop)     │
   └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
                            ┌─────────────────────────┐
                            │  StoryExtractionAgent   │
                            │ (Topic Shifts, Stories) │
                            └────────────┬────────────┘
                                         │
                                         ▼
                               [ Extracted Stories ]
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
   ┌───────────────────────────┐                   ┌───────────────────────────┐
   │ContextEvidenceResearch    │                   │ShortsOpportunityRanker    │
   │Agent (PIB, DD News,       │                   │Agent (9-Factor Virality   │
   │Fact Verification Dossier) │                   │Matrix, Duration 30/45/60s)│
   └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
                            ┌─────────────────────────┐
                            │ ClipMomentSelectorAgent │
                            │ (3-8s Soundbites, Cuts) │
                            └────────────┬────────────┘
                                         │
                                         ▼
                            ┌─────────────────────────┐
                            │  ShortsAdaptationAgent  │
                            │ (Hook, 6-Scene Script)  │
                            └────────────┬────────────┘
                                         │
                                         ▼
                            ┌─────────────────────────┐
                            │ RightsAttributionAgent  │
                            │ (Fair Use Risk, Credit) │
                            └────────────┬────────────┘
                                         │
                                         ▼
                         [ Validated Repurposing Package ]
                         (Ready for Production Rendering)
```

---

## 3. The 9 Specialist Agents

### 3.1 LongVideoIntakeAgent (`agents/long_video_intake/agent.py`)
- **Role:** Media ingestion gatekeeper and technical stream profiler.
- **Responsibilities:**
  - Validates remote URL schemes (`http`, `https`, YouTube, Vimeo) or local file existence.
  - Executes non-destructive `ffprobe` stream inspection to extract container format, duration, resolution, frame rate, video/audio codecs, audio channels, and sampling rates.
  - Computes SHA-256 media fingerprint on the leading 16MB of data to ensure instant deduplication and idempotent restarts.
  - Initializes isolated working directories under `output/repurposing/{video_id}/`.
- **Contract Produced:** `SourceVideoManifest`.

### 3.2 TranscriptionDiarizationAgent (`agents/transcription_diarization/agent.py`)
- **Role:** Speech intelligence, precise word alignment, and multi-speaker tracking.
- **Responsibilities:**
  - Leverages existing captions/subtitles (SRT/WebVTT) whenever present to minimize compute footprint.
  - Extracts 16kHz mono audio tracks via FFmpeg when transcription is required.
  - Whisper STT adapter with multi-provider fallbacks (local `faster-whisper`, `whisper.cpp`, or deterministic sentence distributors for mock testing).
  - Produces word-level timestamps (`WordTiming`) essential for rhythmic subtitles and zero-drift timeline synchronization.
  - Attributes speech to distinct speakers (`SPEAKER_ANCHOR`, `SPEAKER_REPORTER`, `SPEAKER_EXPERT`) and maintains speaking duration statistics.
- **Contract Produced:** `List[TranscriptSegment]`, `List[SpeakerProfile]`.

### 3.3 SceneUnderstandingAgent (`agents/scene_understanding/agent.py`)
- **Role:** Visual layout parser, keyframe extractor, and vertical framing auditor.
- **Responsibilities:**
  - Detects visual scene boundaries using FFmpeg scene filter heuristics.
  - Extracts JPEG keyframe thumbnails to `output/repurposing/{video_id}/keyframes/`.
  - Classifies visual taxonomy: `studio_anchor`, `split_interview`, `field_reporting`, `graphic_infographic`, `broll_footage`.
  - Evaluates on-screen text chyrons and banner headlines.
  - Assesses 9:16 vertical crop compatibility (evaluating speaker position: `center`, `left`, `right` to prevent faces being cropped during vertical reframing).
- **Contract Produced:** `List[VisualScene]`.

### 3.4 StoryExtractionAgent (`agents/story_extraction/agent.py`)
- **Role:** Broadcast narrative analyst and semantic topic segmenter.
- **Responsibilities:**
  - Analyzes full transcript narrative flow and identifies topic shift indicators (e.g. *"अगली बड़ी खबर"*, *"अब बात करते हैं"*, *"संसद में आज"*, *"दूसरी तरफ"*).
  - Segments one long video into discrete, independent stories.
  - Discards introductory channel branding, commercial sponsor breaks, and sign-offs.
  - Formulates for each story: title headline, start/end timestamps, core facts, mentioned entities, category, and completeness score (0.0 to 1.0).
- **Contract Produced:** `List[ExtractedStory]`.

### 3.5 ContextEvidenceResearchAgent (`agents/context_evidence_research/agent.py`)
- **Role:** Investigative fact-checker and contextual knowledge verifier.
- **Responsibilities:**
  - Extracts concrete factual claims from each candidate story.
  - Cross-references claims against trusted sources (PIB Hindi/English, DD News, The Hindu, BBC Hindi, Google News) using `SourceRegistry`.
  - Classifies verification status: `VERIFIED`, `UNVERIFIED`, `DISPUTED`, `CONTEXT_REQUIRED`.
  - Surfaces latest updates or government gazette notifications that emerged since the original broadcast.
  - Attaches source citation URLs and reliability weightings.
- **Contract Produced:** `Dict[str, List[EvidenceClaim]]`.

### 3.6 ShortsOpportunityRankerAgent (`agents/shorts_opportunity_ranker/agent.py`)
- **Role:** Algorithmic editorial director and viral potential evaluator.
- **Responsibilities:**
  - Evaluates every extracted story across a 9-factor weighted virality matrix:
    1. **Public Importance (20%):** National policy, legal precedents, safety, systemic significance.
    2. **Emotional / High-Impact Quotient (15%):** Historic announcements, revelations, warnings.
    3. **Information Freshness (15%):** Breaking updates and recency indicators.
    4. **Factual Clarity & Evidence Strength (15%):** High percentage of verified claims.
    5. **Standalone Comprehensibility (10%):** Story completeness without needing external context.
    6. **Curiosity / Hook Potential (10%):** Strong intrigue or mystery gap.
    7. **Visual Appeal / Footage Usability (5%):** High-action footage or recognizable figures.
    8. **Narrative Closure (5%):** Clear resolution or forward-looking takeaway.
    9. **Novelty / Uniqueness (5%):** Counter-intuitive facts or unprecedented events.
  - Assigns priority flags: `top_pick` ($\ge 82$), `viable` ($\ge 68$), `backlog` ($\ge 50$), `rejected` ($< 50$).
  - Recommends optimal target duration: 30s (punchy statements), 45s (standard news), 60s (deep knowledge).
- **Contract Produced:** `List[StoryRanking]`.

### 3.7 ClipMomentSelectorAgent (`agents/clip_moment_selector/agent.py`)
- **Role:** Film editor and soundbite hunter.
- **Responsibilities:**
  - Isolates 3.0 to 8.0-second video snippets that contain decisive quotes, emotional reactions, or critical declarations.
  - Snaps clip boundaries to natural speech pauses to ensure no speaker is cut off mid-word.
  - Identifies the opening visual hook clip and supporting soundbite clips.
  - Directs vertical crop focus (`center`, `left`, `right`) based on speaker coordinates.
  - Audits audio quality (`clean`, `background_noise`, `overlap`).
- **Contract Produced:** `List[SelectedClip]`.

### 3.8 ShortsAdaptationAgent (`agents/shorts_adaptation/agent.py`)
- **Role:** Hindi scriptwriter and storytelling director.
- **Responsibilities:**
  - Integrates 6 viral Hook Archetypes (`curiosity_gap`, `unexpected_fact`, `strong_statement`, `direct_impact`, `breaking_news`, `emotional_intrigue`).
  - Writes fluent, natural Devanagari Hindi narration paced strictly at ~2.5 to 2.8 words/second.
  - Constructs multi-modal 5-to-6 scene scripts:
    - **Scene 0 (Viral Hook, 0–3s):** Arresting hook voiceover + dynamic headline chip.
    - **Scene 1 (Source Soundbite, 3–8s):** Direct trimmed video clip from the source video with speaker overlay.
    - **Scene 2 (Core Revelation, 8–25s):** Authoritative explanation voiceover + high-resolution context image.
    - **Scene 3 (Evidence & Verification, 25–45s):** Corroborated facts + official document or infographic.
    - **Scene 4 (Impact & Takeaway, 45–54s):** Big-picture perspective.
    - **Scene 5 (Outro / CTA, 54–58s):** Subscriber retention prompt.
  - Specifies camera motion (`push_in`, `subtle_drift`, `pan_left`) and transition cues.
- **Contract Produced:** `AdaptedShortScript`.

### 3.9 RightsAttributionAgent (`agents/rights_attribution/agent.py`)
- **Role:** Copyright compliance officer and legal rights auditor.
- **Responsibilities:**
  - Categorizes footage provenance: Public Domain / Government (Sansad TV, Lok Sabha, PIB, DD News, ISRO) vs Private Commercial Broadcaster.
  - Assesses Fair Use / Fair Dealing risk level (`low`, `medium`, `high`) based on clip duration, transformativeness, and commentary ratio.
  - Enforces the strict $\le 8.0$ second direct clip threshold. Automatically flags recommendations to substitute prolonged third-party clips with Wikimedia Commons photos or motion graphics cards.
  - Generates mandatory on-screen watermark attribution (e.g. *"Credit / Source: Sansad TV"*).
  - Formats YouTube description copyright notice citing Section 107 of the US Copyright Act and Section 52 of the Indian Copyright Act 1957.
- **Contract Produced:** `MediaRightsRecord`.

---

## 4. Shared Data Contracts (`core/agent_contracts.py`)

All 9 agents communicate exclusively via typed dataclass structures defined in `core/agent_contracts.py`. This ensures zero coupling to internal database engines, clean serialization via `_safe_json_dumps`, and complete unit-testability without external dependencies.

```python
# Key Repurposing Contracts
SourceVideoManifest        # Media metadata, stream codecs, SHA-256 fingerprint
WordTiming                 # Millisecond word-level timing
SpeakerProfile             # Speaker role, display name, speaking duration
TranscriptSegment          # Timed speech segment with word timings
VisualScene                # Scene cuts, keyframe path, 9:16 crop position
ExtractedStory             # Independent story with facts, entities, timestamps
EvidenceSource             # Trusted news or government source citation
EvidenceClaim              # Verified or disputed claim with confidence score
StoryRanking               # 9-factor virality score, duration target, priority
SelectedClip               # 3-8s soundbite moment with crop coordinates
AdaptedShortScene          # Multi-modal scene (source clip vs photo context)
AdaptedShortScript         # Complete production-ready Hindi Shorts script
MediaRightsRecord          # Fair use assessment, on-screen credit, disclaimer
RepurposingJobResult       # End-to-end aggregate output
```

---

## 5. Zero-Budget Operational Strategy

The system is architected to operate entirely without mandatory paid subscription APIs:

1. **Transcription:** Local Whisper adapter (`faster-whisper` / `whisper.cpp`) running locally on CPU/GPU, with automatic fallback to existing embedded captions/subtitles when available.
2. **Video Stream Probing & Editing:** Local `ffprobe` and `ffmpeg` binaries for keyframe extraction, audio demuxing, scene detection, and subclip slicing.
3. **LLM Orchestration:** Multi-provider fallback chain supporting Google Gemini Free Tier, Groq (Llama 3 / Mixtral), Mistral Free, OpenRouter Free, and local Ollama, with graceful degradation to deterministic editorial heuristics.
4. **Research & Fact Verification:** RSS feeds and scraping of authoritative public sources (PIB, DD News, The Hindu) and Wikipedia API.
5. **Visual Context:** Wikimedia Commons API, DuckDuckGo Images, and PIL-based high-resolution motion graphics cards.

---

## 6. Phase 2 Production Roadmap

In Phase 2, the repurposed outputs will be wired into the automated rendering and publishing pipeline:
1. **Dynamic Video Subclip Splicing:** Upgrade `video/renderer.py` to support inserting trimmed 9:16 vertical video clips with smooth crossfades and audio normalization.
2. **Audio Ducking:** Automatically duck background music during original soundbite playback.
3. **Orchestrator Integration:** Add a `--repurpose <URL/file>` CLI trigger and GitHub Actions workflow for on-demand processing.
4. **Multi-Short Output:** Produce 3 to 8 independent Shorts from a single long broadcast in one execution.
