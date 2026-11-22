# Agent Wiring Matrix — Complete Pipeline Integration Audit

## 1. Overview & Verification

This matrix documents all 25+ specialized agents across **BHARAT KI SOCH**, demonstrating how their inputs, outputs, and contracts connect into the master rendering pipeline.

**Verification Rule**: Every agent output must either feed the master rendering pipeline, the distribution metadata, or the self-learning memory loop. No agent output is orphaned.

---

## 2. Master Wiring Matrix

| Agent Name | Category | Primary Inputs | Primary Outputs / Contracts | Downstream Consumer(s) | Reaches Final MP4? |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `DailyOpeningDirectorAgent` | Mode 1 News | Calendar, Panchang DB | `DailyOpeningBrief` | `ScriptManager`, `MotionGraphics`, `MasterEditing` | **YES** |
| `ResearchManagerAgent` | Discovery | Feeds, Search Queries | `ResearchResult` | `PromptEngineer`, `ScriptManager`, `FactVerifier` | **YES** |
| `PromptEngineerAgent` | Generation | Research Data | Formatted Prompts | `ScriptManagerAgent` | **YES** |
| `ScriptManagerAgent` | Production | Research, Prompts | `ApprovedScript` | `HookDirector`, `FactVerifier`, `CreativeDirector` | **YES** |
| `HookDirectorAgent` | Editorial | Script, Research | `ApprovedHook` | `ScriptManager`, `MasterEditingDirector` | **YES** |
| `FactVerifierAgent` | QA Gate | Script, Sources | `VerificationReport` | `QualityManagerAgent` | **YES** |
| `QualityManagerAgent` | QA Gate | Script, Verification | `QualityVerificationVerdict` | `CreativeDirectorAgent` | **YES** |
| `CreativeDirectorAgent` | Styling | Script | Creative Brief, Tone | `NewsVisualSourcing`, `VFX`, `MasterEditing` | **YES** |
| `NewsVisualSourcingAgent` | Sourcing | Script, Research Items | `List[NewsVisualAsset]` | `MasterEditingDirector`, `VideoProducer` | **YES** |
| `MotionGraphicsAgent` | Motion | Script, Opening Brief | `List[MotionGraphicsPlanItem]` | `MasterEditingDirector`, `VideoProducer` | **YES** |
| `VFXAgent` | Visuals | Script, Creative Brief | `List[VFXPlanItem]`, Grade | `MasterEditingDirector`, `VideoProducer` | **YES** |
| `AudioSoundDesignAgent` | Audio | Script, Timeline Segs | `AudioMixPlan`, `SoundCues` | `MasterEditingDirector`, `VideoProducer` | **YES** |
| `MasterEditingDirectorAgent`| Master Edit | All Creative & Tech Plans| `MasterEditingTimeline` | `VideoProducerAgent`, `Renderer` | **YES** |
| `VideoProducerAgent` | Rendering | MasterEditingTimeline | Final MP4, Timings, SRT | `VisualAudioMatchQA`, `QAInspector`, `Publisher` | **YES** |
| `VisualAudioMatchQAAgent` | QA Gate | Timeline, Final MP4 | `VisualAudioMatchResult` | `DailyOrchestrator`, `NewsroomOrchestrator` | **YES** |
| `LongVideoIntakeAgent` | Mode 2 Long | File / Stream / URL | `MediaAssetManifest` | `TranscriptionDiarizationAgent` | **YES** |
| `TranscriptionDiarizationAgent`| Mode 2 Long | Audio / Media Manifest | `TranscriptionDiarizationResult`| `StoryExtractionAgent`, `MomentSelector` | **YES** |
| `SceneUnderstandingAgent` | Mode 2 Long | Media Manifest | `SceneAnalysisResult` | `StoryExtractionAgent`, `MomentSelector` | **YES** |
| `StoryExtractionAgent` | Mode 2 Long | Transcription, Scenes | `List[ExtractedStory]` | `ContextEvidence`, `OpportunityRanker` | **YES** |
| `ContextEvidenceResearchAgent` | Mode 2 Long | Extracted Stories | Evidence Verification | `OpportunityRankerAgent` | **YES** |
| `ShortsOpportunityRankerAgent` | Mode 2 Long | Stories, Evidence | Ranked Candidates | `ClipMomentSelectorAgent` | **YES** |
| `ClipMomentSelectorAgent` | Mode 2 Long | Candidate Story | `SelectedClipMoments` | `ShortsAdaptation`, `RightsAttribution` | **YES** |
| `ShortsAdaptationAgent` | Mode 2 Long | Selected Moments | Adapted Hindi Script | `HookDirector`, `CreativeDirector` | **YES** |
| `RightsAttributionAgent` | Legal | Manifest, Moments | `RightsAttributionReport` | `MasterEditingDirector`, `Publisher` | **YES** |
| `SEOManagerAgent` | Distribution | Script, Production | Title, Description, Tags | `PublisherAgent`, `TelegramNotifier` | **Metadata** |
| `ThumbnailDesignerAgent` | Distribution | Script, Assets, Frames | Thumbnail JPG (1080x1920) | `PublisherAgent`, `TelegramNotifier` | **Thumb** |
| `PublisherAgent` | Distribution | MP4, Metadata, Thumb | YouTube ID / HF URL | `TelegramNotifier`, `HistoryStore` | **Live** |
| `AnalyticsManagerAgent` | Feedback | YouTube API Data | Performance Metrics | `SelfLearningAgent` | **Loop** |
| `SelfLearningAgent` | Learning | History, Analytics | Style Notes & Memory | `PromptEngineer`, `CreativeDirector` | **Memory** |
| `WordTimelineBuilder` | Smart Cuts | Script, TTS WordTimings | `WordCutPlan` | `VideoProducerAgent`, `Renderer` | **YES** |
| `WordCutQA` | QA Gate | WordCutPlan, Rendered MP4 | `WordCutQAResult` | `VisualAudioMatchQAAgent`, `VideoQAInspector`| **YES** |
