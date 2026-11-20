# BHARAT KI SOCH — Phase 2 Current State Audit

**Document Version:** 2.0.0  
**Phase:** Phase 2 Complete Newsroom & Master Video Editing System  
**Commit Inspected:** `08d7275f296a78d94326d5d353401c65ce5a2481`  
**Date:** November 20, 2026

---

## 1. Executive Summary

A comprehensive, line-by-line inspection of the repository was conducted following the completion of Phase 1. While Phase 1 established independent specialist agents for long-video repurposing and basic contracts, the codebase currently suffers from severe integration gaps, duplicate creative decision-making, false-success degradation paths, and disconnected outputs that never reach the final rendering pipeline.

The goal of Phase 2 is to transform BHARAT KI SOCH into a unified, professional AI-powered Hindi News Studio. This requires:
1. Two robust production modes: **Daily Newsroom Bulletin** and **Long Video to News Shorts Repurposing** (plus preservation of **Knowledge Shorts**).
2. Elimination of all fake-success fallbacks in Phase 1 agents.
3. Creation of priority agents: `DailyOpeningDirectorAgent`, `NewsVisualSourcingAgent`, `AudioSoundDesignAgent`, `MasterEditingDirectorAgent`, and `VisualAudioMatchQAAgent`.
4. Construction of a **56-preset motion graphics library** (`video/motion_presets/`).
5. A single unified authoritative timeline (`MasterEditingTimeline`) that binds voiceover, media assets, motion graphics, VFX, and audio cues into a single rendering path.

---

## 2. Agent Inventory & Execution Status Matrix

| Agent | File Path | Actual Execution Status | Findings & Flaws |
|---|---|---|---|
| `ResearchManagerAgent` | `agents/research_manager/agent.py` | Partially Functional | Gathers RSS/Google News well. Lacks verified date/special-day deep research. |
| `PromptEngineerAgent` | `agents/prompt_engineer/agent.py` | Functional | Template rendering works. |
| `ScriptManagerAgent` | `agents/script_manager/agent.py` | Functional | Enforces word counts and beat structures. Needs integration with `DailyOpeningBrief`. |
| `HookDirectorAgent` | `agents/hook_director/agent.py` | Functional | Generates 6 archetypes. Needs integration with daily opening and adapted scripts. |
| `FactVerifierAgent` | `agents/fact_verifier/agent.py` | Functional | Cross-checks script against research items. |
| `QualityManagerAgent` | `agents/quality_manager/agent.py` | Functional | Pre-render script and source count validation. |
| `CreativeDirectorAgent` | `agents/creative_director/agent.py` | Partially Functional | Rotates themes, but decisions are often re-decided or bypassed in `VideoProducerAgent`. |
| `MotionGraphicsAgent` | `agents/motion_graphics/agent.py` | **Misleading Success** | Generates PNG overlays to `output/{vid}`, but `VideoProducerAgent` **ignores `motion_data`** and re-creates overlays independently! |
| `VFXAgent` | `agents/vfx_agent/agent.py` | Partially Functional | Output `vfx_data` is only partially read (only `transition_effect` is sampled; camera motion and color grade are overridden). |
| `VideoProducerAgent` | `agents/video_producer/agent.py` | **Architectural Bottleneck** | Instantiates internal `EditorDirector`, re-planning creative recipe and ignoring upstream agent plans. |
| `LongVideoIntakeAgent` | `agents/long_video_intake/agent.py` | **Misleading Success** | Returns fake `duration=600.0s` for inaccessible remote streams and partial 16MB hash instead of verified media access. |
| `TranscriptionDiarizationAgent` | `agents/transcription_diarization/agent.py` | **Misleading Success** | When audio is missing, generates synthetic fake Hindi narration and claims successful transcription. |
| `SceneUnderstandingAgent` | `agents/scene_understanding/agent.py` | **Misleading Success** | Generates synthetic scenes with dummy keyframes when physical video is absent, masking errors. |
| `StoryExtractionAgent` | `agents/story_extraction/agent.py` | Partially Functional | Truncates transcript to 6,000 characters, dropping later news stories in 30-minute videos. |
| `ContextEvidenceResearchAgent` | `agents/context_evidence_research/agent.py` | **Misleading Success** | Fallback marks claims as "verified" without retrieving real evidence when LLM is unavailable. |
| `ShortsOpportunityRankerAgent` | `agents/shorts_opportunity_ranker/agent.py` | Partially Functional | Overly optimistic base scores (75+), insufficient rejection threshold for low-quality content. |
| `ClipMomentSelectorAgent` | `agents/clip_moment_selector/agent.py` | Partially Functional | Relies on single segments; falls back to arbitrary first segment instead of finding semantic soundbites. |
| `ShortsAdaptationAgent` | `agents/shorts_adaptation/agent.py` | Functional | Generates Devanagari Hindi scenes, but needs verified facts and real clip bounds. |
| `RightsAttributionAgent` | `agents/rights_attribution/agent.py` | **Flawed Logic** | Assumes $\le 8$s is automatically safe and government sources grant blanket clearance. |

---

## 3. Disconnected Outputs & Duplicate Creative Systems

1. **The `MotionGraphicsAgent` Disconnect:**
   - In `core/orchestrator.py` (lines 178-180), `MotionGraphicsAgent.execute()` runs and saves overlays.
   - It returns `motion` dictionary containing `{"overlays": [...]}`.
   - In `core/orchestrator.py` (line 184), `motion` is passed to `VideoProducerAgent.execute(motion_data=motion)`.
   - **FLAW:** `VideoProducerAgent` does not use `motion_data["overlays"]`. Instead, at line 428 and 461, it calls `self.motion_engine.compose_broadcast_overlay()` or `compose_frame()` from scratch. The upstream agent's output is completely abandoned.

2. **The `EditorDirector` Duplication:**
   - In `core/orchestrator.py`, `CreativeDirectorAgent` plans a creative brief, and `VFXAgent` plans visual effects.
   - In `agents/video_producer/agent.py` (line 387), `editor = EditorDirector(...)` is instantiated inside `VideoProducerAgent`.
   - `EditorDirector` independently executes `recipe = editor.plan(...)` and overrides the color grade, ticker, and transition styling.
   - This creates competing creative decisions and destroys predictability.

3. **Missing Audio Sound Design:**
   - The final render in `VideoProducerAgent` calls `self.renderer.render(..., music=vcfg.background_music, sfx=vcfg.sound_effects)`.
   - The renderer uses a generic hardcoded sound effect or random whoosh sound.
   - There is no structured sound design agent, no `SoundCueContract`, no sidechain music ducking, and no original BHARAT KI SOCH sound identity.

4. **Audio & Voice Limitations:**
   - Voice was configured to `hi-IN-MadhurNeural` (male voice).
   - Project requirement: **Consistent professional female Hindi news anchor voice (`hi-IN-SwaraNeural`)** for news bulletins and news shorts, with distinct voices for knowledge storytelling and original interview soundbites.

---

## 4. Phase 1 False-Success Degradation Paths (Must Be Repaired)

1. **`LongVideoIntakeAgent`:**
   - Must fail honestly with `source_access_status="inaccessible"` when a remote URL cannot be probed or downloaded.
   - Must never return a dummy `600.0s` duration.
   - Must compute an honest media stream hash or verified local fingerprint.
2. **`TranscriptionDiarizationAgent`:**
   - Must never generate synthetic Hindi text as a "transcript" when audio is missing. It must report `transcription_status="unavailable"`.
   - Must support full chunking across long recordings without global timestamp drift.
3. **`SceneUnderstandingAgent`:**
   - Must not return synthetic mock keyframes as true video analysis.
   - Must report `scene_analysis_status="unavailable"` when frames cannot be extracted.
4. **`StoryExtractionAgent`:**
   - Must eliminate the 6,000-character prompt truncation. Long transcripts must be processed in overlapping narrative windows so stories in minutes 15–40 are never lost.
5. **`ContextEvidenceResearchAgent`:**
   - Must never label a claim as `VERIFIED` without actual retrieved evidence sources and URLs. If evidence is lacking, it must be marked `UNVERIFIED` or `DISPUTED`.
6. **`ClipMomentSelectorAgent`:**
   - Must select coherent speaker soundbites based on full story context and speech boundaries, not merely fallback to the first segment.
7. **`RightsAttributionAgent`:**
   - Must completely discard the assumption that $\le 8$ seconds is legally safe or that government footage is automatically public domain. It must output legal risk levels, license requirements, and `review_required` statuses.

---

## 5. Architectural Blueprint for Phase 2

```
                                [ PRODUCTION MODES ]
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        ▼                                                                 ▼
[ MODE 1: Daily Newsroom ]                                 [ MODE 2: Long Video Repurposing ]
  - DailyOpeningDirectorAgent                                - LongVideoIntakeAgent (Repaired)
  - ResearchManagerAgent                                     - TranscriptionDiarizationAgent (Repaired)
  - Source Registry & Evidence                               - SceneUnderstandingAgent (Repaired)
  - ScriptManagerAgent                                       - StoryExtractionAgent (Chunked)
  - HookDirectorAgent                                        - ContextEvidenceResearchAgent (Repaired)
                                                             - ShortsOpportunityRankerAgent (Repaired)
                                                             - ClipMomentSelectorAgent (Repaired)
                                                             - ShortsAdaptationAgent
                                                             - HookDirectorAgent
                                                             - RightsAttributionAgent (Repaired)
        │                                                                 │
        └────────────────────────────────┬────────────────────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │    NewsVisualSourcingAgent      │
                        │ (Event Photos, B-Roll, Licenses)│
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │      CreativeDirectorAgent      │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │      MotionGraphicsAgent        │
                        │    (56 Motion Presets)          │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │           VFXAgent              │
                        │ (Content-Aware, Motion Presets) │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │     AudioSoundDesignAgent       │
                        │ (Female Anchor, SFX, Ducking)   │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │   MasterEditingDirectorAgent    │
                        │   (MasterEditingTimeline)       │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │     SynchronizationEngine       │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │     VideoProducerAgent /        │
                        │     VideoRenderer               │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │    VisualAudioMatchQAAgent      │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │      VideoQAInspector           │
                        └────────────────┬────────────────┘
                                         ▼
                        ┌─────────────────────────────────┐
                        │    SEO, Thumbnail, Publishing   │
                        └─────────────────────────────────┘
```

---

## 6. Action Plan & Implementation Sequence

1. **Step 2:** Repair all 9 Phase 1 agents to eradicate false-success paths and enforce strict truthfulness.
2. **Step 3:** Implement `DailyOpeningDirectorAgent` with Panchang, festivals, special days, and verified date research.
3. **Step 4:** Build `NewsVisualSourcingAgent` with license provenance and event-specific asset priority.
4. **Step 5:** Build `AudioSoundDesignAgent` with `hi-IN-SwaraNeural` voice profile, SFX library, sound cue contracts, and ducking.
5. **Step 6:** Build the **56 Motion Preset Library** (`video/motion_presets/`) across 7 distinct families.
6. **Step 7:** Upgrade `MotionGraphicsAgent` and `VFXAgent` to directly integrate with the Motion Preset Library and story contexts.
7. **Step 8:** Build `MasterEditingDirectorAgent` to unite all specialist plans into one authoritative `MasterEditingTimeline`.
8. **Step 9:** Wire everything into `core/newsroom_orchestrator.py` and `core/repurposing_orchestrator.py`.
9. **Step 10:** Upgrade `video/renderer.py` and `agents/video_producer/agent.py` to render strictly from `MasterEditingTimeline`.
10. **Step 11:** Implement `VisualAudioMatchQAAgent` and integrate post-render quality gates.
11. **Step 12:** Produce verified test renders, contact sheets, and preset gallery.
12. **Step 13:** Execute full regression test suite.
13. **Step 14:** Complete all 10 required documentation deliverables and commit to GitHub.
