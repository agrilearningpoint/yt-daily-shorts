# BHARAT KI SOCH — Long Video Intelligence & Shorts Repurposing Architecture Audit

**Document Version:** 1.0.0  
**Phase:** Phase 1 — Long Video Intelligence & Specialist Agent Foundation  
**System Target:** Hindi News & Knowledge Shorts Repurposing Pipeline  
**Date:** November 2026

---

## 1. Executive Summary

BHARAT KI SOCH currently operates an automated Hindi YouTube Shorts generation engine that creates two daily videos (News Roundup and Deep Knowledge Topic). The engine includes:
- Multi-provider LLM fallback (Gemini, Groq, Mistral, OpenRouter, NVIDIA) with auto-discovery.
- Precise audio-video synchronization engine (`video/synchronization_engine.py`) with sub-millisecond drift control and frame quantization.
- 6 Hook Archetypes with strict visual-semantic pairing (`agents/hook_director/`).
- Automated VFX & Motion Graphics overlay generators (`agents/vfx_agent/`, `agents/motion_graphics/`).
- Post-render QA Inspector (`video/qa_inspector.py`) scoring duration, sync, and audiovisual alignment.
- Long-form documentary generator (`longform/`).

The objective of **Phase 1** is to build a professional, modular, production-grade **Long Video Intelligence & Shorts Repurposing Agent System**. This system ingests long-format Hindi video content (such as 35-minute news bulletins, interviews, press conferences, parliamentary debates, and speeches), transcribes and diarizes the audio, detects visual scene boundaries, segments the video into distinct independent stories, verifies facts with external evidence, ranks viral opportunities using a multi-factor matrix, selects exact clip moments, adapts the content into punchy 30s/45s/60s Hindi Shorts scripts, and assesses copyright/attribution risks.

This document presents a comprehensive audit of all existing agents, analyzes their reusability for long-video repurposing, identifies architectural gaps, and defines the specifications for 9 new specialist agents and extended data contracts.

---

## 2. Existing Agent Inventory & Evaluation

| Agent Name | Folder Path | Primary Responsibility | Execution Status | LLM Integration | Reusable for Repurposing? |
|---|---|---|---|---|---|
| `ResearchManagerAgent` | `agents/research_manager/` | Gathers news items from RSS/APIs, ranks top stories | Functional | Yes (clustering & ranking) | Partially (needs story-level research mode) |
| `FactVerifierAgent` | `agents/fact_verifier/` | Verifies claims against source articles, drops unverified scenes | Functional | Yes (strict verification) | Partially (needs cross-source evidence support) |
| `PromptEngineerAgent` | `agents/prompt_engineer/` | Formats system & user prompts for pipeline stages | Functional | No (template engine) | Yes (can provide repurposing prompt templates) |
| `ScriptManagerAgent` | `agents/script_manager/` | Generates 60s Hindi narration scripts with beats | Functional | Yes (generation & pacing) | Partially (needs adaptation from source excerpts) |
| `HookDirectorAgent` | `agents/hook_director/` | Generates & scores 6 viral hook archetypes with visual pairing | Functional | Yes (multi-candidate scoring) | Yes (direct reuse for adapted Shorts hooks) |
| `CreativeDirectorAgent` | `agents/creative_director/` | Defines visual theme, color palette, typography, music mood | Functional | Rule-based rotation | Yes (shared visual theme design) |
| `QualityManagerAgent` | `agents/quality_manager/` | Pre-render validation of script, duration, and beats | Functional | Rule-based & LLM | Yes (pre-render validation for repurposed Shorts) |
| `VFXAgent` | `agents/vfx_agent/` | Plans visual transitions, camera motions, color grades | Functional | Rule-based context mapping | Yes (applied to repurposed timeline segments) |
| `MotionGraphicsAgent` | `agents/motion_graphics/` | Generates PIL overlay banners, story counters, category chips | Functional | Pillow graphics rendering | Yes (overlays for repurposed clips/scenes) |
| `VideoProducerAgent` | `agents/video_producer/` | Coordinates TTS audio, media collection, video rendering | Functional | Orchestration | Yes (renderer can take repurposing timeline) |
| `SEOManagerAgent` | `agents/seo_manager/` | Generates viral Hindi titles, descriptions, hashtags, tags | Functional | Yes (metadata generation) | Yes (metadata for repurposed Shorts) |
| `ThumbnailDesignerAgent` | `agents/thumbnail_designer/` | Generates 1080x1920 cover image with dynamic text chips | Functional | Pillow graphics rendering | Yes (covers for repurposed Shorts) |
| `PublisherAgent` | `agents/publisher/` | Uploads to YouTube via OAuth2 and sends Telegram alerts | Functional | External API calls | Yes (Phase 2 publishing) |
| `AnalyticsManagerAgent` | `agents/analytics_manager/` | Fetches YouTube Analytics performance metrics | Functional | External API calls | Inactive in Phase 1 |
| `SelfLearningAgent` | `agents/self_learning/` | Optimizes retention patterns and hook weights | Functional | Statistical heuristics | Inactive in Phase 1 |
| `ErrorAnalystAgent` | `agents/error_analyst/` | Diagnoses failures and suggests corrective actions | Functional | LLM diagnosis | Yes (error handling) |

---

## 3. Detailed Per-Agent Technical Audit

### 3.1 ResearchManagerAgent (`agents/research_manager/agent.py`)
- **Current Responsibility:** Collects daily news items from RSS feeds (PIB, DD News, BBC Hindi, The Hindu) and news APIs. Clusters duplicate stories and selects top 20+ items.
- **Input Schema:** `video_type: str`, `day_name: str`, `target_count: int`.
- **Output Schema:** `ResearchContext` containing list of `ResearchItem` dataclass objects.
- **Dependencies:** `research.news_collector.NewsCollector`, `research.source_registry.SourceRegistry`, `core.llm_client`.
- **Gaps for Repurposing:** Designed purely for daily morning news feed aggregation. Cannot accept an extracted story from a long video and perform targeted contextual research on a specific topic.
- **Required Improvement:** Add story-level research mode (`research_story(topic, entities, claims)`) or pair with a dedicated `ContextEvidenceResearchAgent`.

### 3.2 FactVerifierAgent (`agents/fact_verifier/agent.py`)
- **Current Responsibility:** Checks generated script narration against the gathered `ResearchContext`. Identifies unverified claims and marks them for removal or correction.
- **Input Schema:** `script: ApprovedScript`, `research_context: ResearchContext`.
- **Output Schema:** `FactVerificationReport` with verdict (`pass`, `fixed`, `fail`), confidence score, and dropped/corrected scene indices.
- **Dependencies:** `core.llm_client`.
- **Gaps for Repurposing:** Validates scripts against pre-existing research items; does not verify statements made inside a raw video transcript against independent external journalism.
- **Required Improvement:** Extend to support verification of `ExtractedStory` claims against web/official evidence dossiers.

### 3.3 ScriptManagerAgent (`agents/script_manager/agent.py`)
- **Current Responsibility:** Crafts a 50–60 second Hindi news or knowledge script broken into hook, scene items (with visual beat specs), and outro.
- **Input Schema:** `research_context: ResearchContext`, `creative_brief: CreativeBrief`, `video_type: str`.
- **Output Schema:** `ApprovedScript` dataclass instance.
- **Dependencies:** `core.llm_client`, `core.duration.calculate_duration`.
- **Gaps for Repurposing:** Generates scripts from scratch based on daily bullet points. Does not know how to adapt an existing transcript excerpt and soundbite into a tight 30s/45s/60s Short that integrates both original source footage and supplementary narration.
- **Required Improvement:** Keep existing `ScriptManagerAgent` intact for daily shorts; build a dedicated `ShortsAdaptationAgent` for long-video repurposing.

### 3.4 HookDirectorAgent (`agents/hook_director/agent.py`)
- **Current Responsibility:** Implements 6 viral hook archetypes (`CURIOSITY_GAP`, `UNEXPECTED_FACT`, `STRONG_STATEMENT`, `DIRECT_IMPACT`, `BREAKING_NEWS`, `EMOTIONAL_INTRIGUE`). Scores 6 candidates across 6 criteria (impact, curiosity, clarity, factual, naturalness, visual potential) and enforces visual-semantic pairing.
- **Input Schema:** `research_items: List[ResearchItem]` or story summary, `video_type: str`.
- **Output Schema:** `ApprovedHook` dataclass instance with `headline_chip` and `visual_pairing_query`.
- **Dependencies:** `core.llm_client`.
- **Reusability:** Excellent. Can be directly reused or called by the new `ShortsAdaptationAgent` to generate high-retention opening hooks for repurposed Shorts.

### 3.5 VideoProducerAgent & Video Layer (`agents/video_producer/agent.py`, `video/`)
- **Current Responsibility:** Converts `ApprovedScript` into a final vertical MP4 using `SynchronizationEngine`, `TTSEngine`, `MediaCollector`, `SceneComposer`, and `Renderer`.
- **Input Schema:** `ApprovedScript`, `CreativeBrief`, `VFXPlanItem`, `MotionGraphicsPlanItem`.
- **Output Schema:** `ProductionArtifacts` (video path, thumbnail path, subtitle paths, measured duration).
- **Gaps for Repurposing:** `Renderer` currently expects image assets and Ken Burns motion for all scenes. It does not support cutting and inserting trimmed video subclips from a source video file alongside Ken Burns still photos.
- **Required Improvement in Phase 2:** Enhance `video/renderer.py` and `video/synchronization_engine.py` to support video clip inputs with audio ducking and 9:16 vertical smart cropping.

---

## 4. Architectural Analysis: Why Long-Video Repurposing Requires New Specialist Agents

Repurposing a long video (such as a 35-minute parliamentary discussion, an interview, or a multi-topic news broadcast) is fundamentally different from generating a daily synthetic news summary:

1. **Source Ingestion & Stream Integrity:**
   - Raw inputs can be local files (MP4, MKV, MOV) or remote streaming URLs (YouTube, Vimeo).
   - Needs container inspection, audio channel extraction, resolution/codec verification, and local caching without redownloading.
2. **Audio Transcription & Multi-Speaker Diarization:**
   - Daily pipeline does TTS synthesis from text. Repurposing does *STT* (Speech-to-Text) from audio.
   - Long recordings contain multiple speakers (Anchor, Reporter, Minister, Guest). Timings must be frame-accurate down to the word level.
3. **Computer Vision & Shot Boundary Detection:**
   - Long videos contain scene cuts, graphic lower-thirds, split-screens, and b-roll footage.
   - We must detect cuts, OCR on-screen headlines/chyrons, and classify frame layouts to know where clean soundbites and visual moments exist.
4. **Topic Segmentation & Story Extraction:**
   - A single long broadcast contains 5 to 15 completely distinct news topics.
   - We must delineate story start/end boundaries, extract key claims, and determine completeness so that each story can stand on its own.
5. **Contextual Verification & Fact Checking:**
   - Claims in video broadcasts can be outdated, opinionated, or incomplete. External verification against official records (PIB, Supreme Court, Gazette) ensures zero fabricated or false news.
6. **Virality & Retention Ranking:**
   - Not every segment of a 35-minute video makes a viral Short. A rigorous 9-factor multi-dimensional scoring matrix is required to identify the best candidates.
7. **Soundbite & Moment Selection:**
   - A human editor watches the video to find the single 4-second punchy statement where the speaker makes the core declaration. An agent must isolate these exact micro-windows.
8. **Shorts Script Adaptation:**
   - Direct transcript cuts sound disjointed. The story must be reimagined as a 30s/45s/60s vertical narrative: Hook -> Source Soundbite -> Context/Evidence -> Impact -> CTA.
9. **Rights & Fair Use Risk Assessment:**
   - Repurposing third-party broadcast footage carries copyright and Content ID risks. An agent must evaluate transformativeness, enforce short duration thresholds (<= 5–8s direct clips), generate visible source attributions, and recommend safe asset substitutions when risk is high.

---

## 5. Specification of 9 New Specialist Agents

### Agent 1: LongVideoIntakeAgent
- **Module:** `agents/long_video_intake/agent.py`
- **Class:** `LongVideoIntakeAgent(BaseAgent)`
- **Input:** `source_url: Optional[str]`, `file_path: Optional[str]`, `options: Optional[Dict[str, Any]]`
- **Output:** `AgentResult(data={"manifest": SourceVideoManifest})`
- **Key Responsibilities:**
  - Validates source URL format or checks local file existence.
  - Probes streams using `ffprobe` (or local file fallback) to extract duration, resolution, FPS, video/audio codecs, audio channels, and bitrate.
  - Computes unique SHA-256 hash of media file to prevent redundant processing.
  - Checks permissions and DRM flags.
  - Prepares isolated workspace directory under `output/repurposing/{video_hash}/`.

### Agent 2: TranscriptionDiarizationAgent
- **Module:** `agents/transcription_diarization/agent.py`
- **Class:** `TranscriptionDiarizationAgent(BaseAgent)`
- **Input:** `manifest: SourceVideoManifest`, `audio_track_path: Optional[str]`, `existing_captions_path: Optional[str]`
- **Output:** `AgentResult(data={"segments": List[TranscriptSegment], "speakers": List[SpeakerProfile], "full_text": str})`
- **Key Responsibilities:**
  - Checks for existing accurate captions/SRT first (zero compute cost).
  - Extracts 16kHz mono WAV audio track using FFmpeg if transcription is required.
  - Transcribes Hindi audio using Whisper adapter (faster-whisper, whisper.cpp, or mock/fallback for test/offline environments).
  - Implements overlapping window chunking with timestamp stitching.
  - Attributes speech to distinct speakers (`SPEAKER_01`, `SPEAKER_02`, Anchor, Interviewee).
  - Generates word-level timestamps with confidence scores and Devanagari text normalization.

### Agent 3: SceneUnderstandingAgent
- **Module:** `agents/scene_understanding/agent.py`
- **Class:** `SceneUnderstandingAgent(BaseAgent)`
- **Input:** `manifest: SourceVideoManifest`, `sample_interval: float = 1.0`
- **Output:** `AgentResult(data={"scenes": List[VisualScene], "total_cuts": int})`
- **Key Responsibilities:**
  - Detects shot boundaries and cuts using FFmpeg scene filter (`select='gt(scene,0.3)'`) or uniform sampling.
  - Extracts keyframe images for each scene segment.
  - Performs OCR heuristic / text extraction on on-screen chyrons and headline bands.
  - Classifies visual layout: `STUDIO_ANCHOR`, `SPLIT_INTERVIEW`, `FIELD_REPORTING`, `DOCUMENT_INFOGRAPHIC`, `BROLL_FOOTAGE`.
  - Assesses vertical 9:16 crop viability (speaker center framing vs graphic obstruction).

### Agent 4: StoryExtractionAgent
- **Module:** `agents/story_extraction/agent.py`
- **Class:** `StoryExtractionAgent(BaseAgent)`
- **Input:** `manifest: SourceVideoManifest`, `segments: List[TranscriptSegment]`, `scenes: Optional[List[VisualScene]]`
- **Output:** `AgentResult(data={"stories": List[ExtractedStory]})`
- **Key Responsibilities:**
  - Analyzes transcript narrative flow to detect topical shifts and anchor transitions.
  - Segments raw video into distinct, self-contained stories.
  - Extracts for each story: headline, start/end timestamp, key facts, mentioned entities, category, and completeness score.
  - Discards conversational filler, intro channel jingles, and commercial segments.

### Agent 5: ContextEvidenceResearchAgent
- **Module:** `agents/context_evidence_research/agent.py`
- **Class:** `ContextEvidenceResearchAgent(BaseAgent)`
- **Input:** `stories: List[ExtractedStory]`, `max_claims_per_story: int = 5`
- **Output:** `AgentResult(data={"evidence_dossiers": Dict[str, List[EvidenceClaim]]})`
- **Key Responsibilities:**
  - Extracts verifiable factual claims from each story.
  - Queries trusted news and government sources (`SourceRegistry`, DuckDuckGo/Wikipedia) for corroborating evidence.
  - Evaluates claim status: `VERIFIED`, `UNVERIFIED`, `DISPUTED`, `CONTEXT_REQUIRED`.
  - Identifies latest updates or policy developments since the video was recorded.
  - Produces source citation links and reliability weights.

### Agent 6: ShortsOpportunityRankerAgent
- **Module:** `agents/shorts_opportunity_ranker/agent.py`
- **Class:** `ShortsOpportunityRankerAgent(BaseAgent)`
- **Input:** `stories: List[ExtractedStory]`, `evidence_dossiers: Dict[str, List[EvidenceClaim]]`
- **Output:** `AgentResult(data={"rankings": List[StoryRanking], "top_stories": List[ExtractedStory]})`
- **Key Responsibilities:**
  - Applies 9-factor weighted virality scoring matrix:
    1. Public Importance (20%)
    2. Emotional / High-Impact Quotient (15%)
    3. Information Freshness (15%)
    4. Factual Clarity & Evidence Strength (15%)
    5. Standalone Comprehensibility (10%)
    6. Curiosity / Hook Potential (10%)
    7. Visual Appeal / Footage Usability (5%)
    8. Narrative Closure (5%)
    9. Novelty / Uniqueness (5%)
  - Recommends target duration (30s, 45s, 60s) for each candidate.
  - Provides editorial reasoning and priority flags (`TOP_PICK`, `VIABLE`, `BACKLOG`, `REJECTED`).

### Agent 7: ClipMomentSelectorAgent
- **Module:** `agents/clip_moment_selector/agent.py`
- **Class:** `ClipMomentSelectorAgent(BaseAgent)`
- **Input:** `story: ExtractedStory`, `segments: List[TranscriptSegment]`, `scenes: List[VisualScene]`
- **Output:** `AgentResult(data={"selected_clips": List[SelectedClip], "hook_clip": Optional[SelectedClip]})`
- **Key Responsibilities:**
  - Identifies high-energy soundbites (3 to 8 seconds) containing direct quotes, critical revelations, or decisive remarks.
  - Ensures clips start and end on natural speech pauses without truncating words.
  - Associates visual framing recommendation (center crop, pan to speaker, full graphic).
  - Assesses audio clarity (clean speech vs background crowd/music interference).

### Agent 8: ShortsAdaptationAgent
- **Module:** `agents/shorts_adaptation/agent.py`
- **Class:** `ShortsAdaptationAgent(BaseAgent)`
- **Input:** `story: ExtractedStory`, `ranking: StoryRanking`, `selected_clips: List[SelectedClip]`, `evidence: List[EvidenceClaim]`
- **Output:** `AgentResult(data={"adapted_script": AdaptedShortScript})`
- **Key Responsibilities:**
  - Crafts an opening hook using `HookDirectorAgent` archetypes and Hindi rhetorical techniques.
  - Builds an adapted 30s/45s/60s narrative in authentic Devanagari Hindi.
  - Coordinates multi-modal scene breakdown:
    - Phase A: Hook (0–3s, punchy voice + dynamic chip).
    - Phase B: Original Soundbite Clip (3–9s, source footage with speaker attribution).
    - Phase C: Core Revelation & Evidence (9–35s, narrator voiceover + high-res context visual).
    - Phase D: Broader Impact & Takeaway (35–52s, narrator voiceover + infographic/map).
    - Phase E: Outro & Engagement CTA (52–58s).
  - Generates on-screen text chips, category badges, and word-level pacing specs.

### Agent 9: RightsAttributionAgent
- **Module:** `agents/rights_attribution/agent.py`
- **Class:** `RightsAttributionAgent(BaseAgent)`
- **Input:** `manifest: SourceVideoManifest`, `selected_clips: List[SelectedClip]`, `adapted_script: AdaptedShortScript`
- **Output:** `AgentResult(data={"rights_record": MediaRightsRecord})`
- **Key Responsibilities:**
  - Analyzes video origin and channel ownership (official government/parliament vs private news broadcaster vs user upload).
  - Evaluates fair use risk level (`LOW`, `MEDIUM`, `HIGH`) based on clip duration and transformativeness.
  - Generates mandatory on-screen watermark/credit text (e.g., `"Source: Sansad TV"`, `"Footage: DD News"`).
  - Formats YouTube description attribution section and legal disclaimer.
  - Flags any clip exceeding 8 seconds for automatic trimming or image replacement to prevent Content ID claims.

---

## 6. Proposed Extended Data Contracts (`core/agent_contracts.py`)

The following dataclasses will be added to `core/agent_contracts.py` to establish typed communication between the new agents:

- `SourceVideoManifest`: Input file/URL, duration, resolution, codecs, audio info, sha256.
- `TranscriptSegment`: Speaker ID, start/end timestamps, text, confidence, word-level timings.
- `SpeakerProfile`: Speaker ID, display name, role (anchor, minister, guest, reporter), total speaking time.
- `VisualScene`: Scene index, start/end timestamps, keyframe path, scene type, chyron text.
- `ExtractedStory`: Story ID, title, start/end timestamps, category, key facts, entities, transcript excerpt, completeness score.
- `EvidenceSource`: Source name, URL, reliability score, is_government.
- `EvidenceClaim`: Claim text, status (`VERIFIED`, `UNVERIFIED`, `DISPUTED`), sources, confidence.
- `StoryRanking`: Story ID, composite score, factor breakdown, recommended duration, priority flag, rationale.
- `ClipCandidate` & `SelectedClip`: Clip ID, start/end timestamps, duration, quote text, speaker, audio quality, crop recommendation.
- `AdaptedShortScript`: Short ID, story ID, target duration, title, hook, scenes (with clip vs photo source types), outro, attribution.
- `MediaRightsRecord`: Source entity, fair use score, risk level, on_screen_credit, description_attribution, replacement_recommendations.
- `RepurposingJobResult`: Aggregate result encapsulating all generated Shorts candidates and manifests.

---

## 7. Dependency & Execution Design (Phase 1 vs Phase 2)

```
[Long Video File or URL]
          │
          ▼
 1. LongVideoIntakeAgent
          │
          ├──────────────────────────┐
          ▼                          ▼
 2. TranscriptionDiarization  3. SceneUnderstanding
          │                          │
          └───────────┬──────────────┘
                      ▼
            4. StoryExtraction
                      │
          ┌───────────┴──────────────┐
          ▼                          ▼
 5. ContextEvidenceResearch   6. ShortsOpportunityRanker
          │                          │
          └───────────┬──────────────┘
                      ▼
            7. ClipMomentSelector
                      │
                      ▼
            8. ShortsAdaptation
                      │
                      ▼
            9. RightsAttribution
                      │
                      ▼
   [Validated Repurposing Package]
   (Ready for Phase 2 Production Renderer)
```

**Phase 1 Guarantee:**
All 9 agents execute independently and composably. They accept standard inputs, interact with shared configuration and LLM infrastructure, and produce strongly-typed outputs. The existing daily Shorts pipeline and long-form documentary pipeline remain 100% stable and intact.
