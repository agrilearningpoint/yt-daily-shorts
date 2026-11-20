# Changelog

All notable changes to the **YT Daily Shorts** platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - Production Hardening, Duration Policy & Architecture Integration

### Added
- **Centralized Shorts Duration Policy**:
  - Defined authoritative constants in `core/duration.py`: `SHORTS_HARD_LIMIT = 59.9`, `SHORTS_SAFE_MAX = 59.5`, `SHORTS_MIN_DURATION = 15.0`, `NEWS_TARGET_DURATION = 56.0`.
  - Added `is_duration_valid()` predicate and unified validation across all orchestrators and agents.
  - Synchronized `config/settings.yaml`, `core/configuration.py`, `prompts/scripting/news_script.j2`, and `agents/prompt_engineer/agent.py` to target 56s (8 news stories: 6 national, 2 international).
  - Hard duration check in `PublisherAgent`: probe-based rejection before YouTube upload if duration $> 59.9$s or $< 15.0$s.
- **Strict Blocking QA Gates**:
  - `visual_audio_match_qa` stage in `core/orchestrator.py` and `core/newsroom_orchestrator.py` now enforces `require_success=True` and `approved=True`. Rejections immediately abort with `StageError` and mark pipeline `FAILED`.
  - Added semantic and provenance integrity checks in `agents/visual_audio_match_qa/agent.py` preventing corrupt, fake, or mismatched assets.
  - Post-render `VideoQAInspector` checks video streams, vertical dimensions (1080x1920), duration bounds, and audio stream presence.
- **Master Editing Director & Motion Presets Integration**:
  - Connected `MasterEditingDirectorAgent` timeline segments directly to `VideoRenderer._beat_clip()` in `video/renderer.py`.
  - Implemented dynamic rendering of all 56 motion presets via FFmpeg filtergraph construction supporting zoom, pan, drift, punch, blur, shake, rotate, and overlay animations.
- **Multi-Track Audio Sound Design**:
  - Overhauled `AudioSoundDesignAgent.render_mix()` to construct multi-track FFmpeg filtergraphs mixing narration voice, ducked background news bed (-24 dB during speech), and timed sound effects cues.
  - Applied EBU R128 / ATSC A/85 broadcast loudness normalization (`loudnorm=I=-14:LRA=7:TP=-1.0`).
- **Female Hindi News Voice Lock**:
  - Standardized Hindi news voice strictly to `hi-IN-SwaraNeural` (primary) and `hi-IN-KavyaNeural` (female fallback) in `video/tts.py`, `agents/video_producer/agent.py`, and `config/settings.yaml`.
- **Long-Video-to-Shorts Repurposing Pipeline Completion**:
  - Standardized agent input/output contracts across all 9 repurposing agents (`LongVideoIntakeAgent`, `TranscriptionDiarizationAgent`, `SceneUnderstandingAgent`, `StoryExtractionAgent`, `ContextEvidenceResearchAgent`, `ShortsOpportunityRankerAgent`, `ClipMomentSelectorAgent`, `ShortsAdaptationAgent`, `RightsAttributionAgent`).
  - Added `AdaptedShortScript.to_script_dict()` bridge for seamless downstream rendering.
  - Fixed chunked story extraction and duration capping in `ShortsAdaptationAgent`.
- **State Manager In-Memory Database Fix**:
  - Added persistent connection caching for `":memory:"` SQLite databases in `core/state_manager.py` to prevent table loss during testing.

### Changed
- Refactored `NewsroomOrchestrator.produce_daily_bulletin()` to delegate directly to `DailyOrchestrator` for unified execution.
- Standardized `NewsVisualSourcingAgent` and `MediaCollector` signatures and Fair Dealing license provenance tracking.
- Resolved all Ruff linting and formatting violations across 190 Python files.

## [0.1.0] - Initial Production Implementation

### Added
- **Multi-Agent Core Engine**:
  - `BaseAgent` abstract class with standardized execution, validation, and persistence.
  - 12 production-ready agents: `ResearchManager`, `PromptEngineer`, `ScriptManager`, `FactVerifier`, `QualityManager`, `CreativeDirector`, `VideoProducer`, `SEOManager`, `ThumbnailDesigner`, `Publisher`, `AnalyticsManager`, and `SelfLearning`.
  - `DailyOrchestrator` coordinating sequential multi-agent execution with stage checkpointing.
- **Research & Verification Engine**:
  - `SourceRegistry` supporting trusted Indian and global sources (PIB, DD News, ISRO, BBC Hindi, The Hindu, Reuters India).
  - `RSSReader` with dynamic feed fetching and resilient date parsing.
  - `deduplicate_articles` using word-level Jaccard similarity.
  - `TrendDiscovery` with 7-day editorial calendar seeds and Wikipedia REST API enrichment.
- **Prompt & Scripting Engine**:
  - Jinja2 prompt templates for news and knowledge scripts, creative brief, and SEO metadata.
  - Unified `BaseLLMProvider` supporting Google Gemini API (`gemini-2.0-flash`), Groq (`llama-3.3-70b-versatile`), and offline `MockLLMProvider`.
  - Duration estimation tuned for Hindi speech rate (~2.5 words/sec).
- **Video Production & Subtitles**:
  - `TTSEngine` using `edge-tts` with high-quality Hindi neural voices (`hi-IN-SwaraNeural`, `hi-IN-MadhurNeural`) and silence audio fallback.
  - `MediaCollector` supporting Pexels and Pixabay APIs with fallback procedural 1080x1920 graphic cards.
  - `AIImageGenerator` for Hugging Face inference.
  - `SubtitleGenerator` generating mobile-optimized vertical `.srt` and `.ass` subtitles.
  - `CreativeVariationEngine` rotating themes, colors, and audio moods.
  - `VideoRenderer` compiling 1080x1920 9:16 vertical MP4 video via FFmpeg.
- **YouTube Publishing & SEO**:
  - `YouTubeOAuthManager` handling secure Google OAuth 2.0 with automatic token refresh.
  - `YouTubeSEOFormatter` generating high-CTR titles, numbered source citations, and hashtags.
  - `YouTubeUploader` with official Data API v3 and safe `DRY_RUN` simulation.
  - `YouTubeAnalyticsFetcher` tracking view counts, likes, and comments.
- **Telegram Management & Reporting**:
  - `TelegramNotifier` sending Markdown status summaries and real-time failure alerts.
  - `CommandDispatcher` providing remote bot management (`/status`, `/news`, `/topics`, `/retry`).
- **Cloud Automation & CI/CD**:
  - GitHub Actions `daily_shorts.yml` scheduled at 00:00 UTC (5:30 AM IST) and 09:00 UTC (2:30 PM IST).
  - GitHub Actions `tests.yml` automated test suite with pytest.
  - Artifacts uploading for rendered videos, logs, and database.
- **State Management & Persistence**:
  - SQLite database schema with WAL mode and checkpoints table for failure resumption.
  - Sensitive-value scrubbing in logger across all handlers.
