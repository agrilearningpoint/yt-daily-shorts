# Changelog

All notable changes to the **YT Daily Shorts** platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
