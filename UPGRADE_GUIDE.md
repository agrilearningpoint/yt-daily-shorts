# yt-daily-shorts Production Upgrade Bundle

## What Was Fixed
1. **Image & Sound Sync (`video/tts.py`)**:
   - Replaced whole-script `silencedetect` splitting in `GeminiTTS` with **per-beat synthesis** (`_voice_beats_gemini`), locking every visual beat 1:1 to its exact audio duration.
   - Added `_parse_key_pool` multi-key rotation to `GeminiTTS` so `YT_GEMINI_API_KEYS_EXTRA` keys rotate automatically on `429`/`RESOURCE_EXHAUSTED`.
   - Disabled silent audio fallback in production (`strict=True`).
2. **Full Key Utilization & Auto-Free Models (`config/settings.yaml`, `core/model_auto_discovery.py`)**:
   - Raised `max_keys_per_provider` from `2` to `10`.
   - Added `"auto-free"` and `"openrouter/free"` to provider model lists and live `https://openrouter.ai/api/v1/models` zero-cost discovery with 6-hour caching.
3. **High-Retention Pacing & Hooks (`config/settings.yaml`, `prompts/scripting/hook_critic_prompt.txt`)**:
   - Tightened News Shorts from 20 headlines (120s) to 5 crisp headlines (50s) and Knowledge Shorts to 46s.
   - Added 3-variant Hindi Hook Critic prompt.
4. **Trending & Self-Improving Agents (`research/yt_trend_scout.py`, `agents/self_learning/retention_optimizer.py`)**:
   - Uses `videos.list(chart="mostPopular", regionCode="IN")` (only 1 YouTube quota unit per call).
   - Reads `averageViewPercentage` from YouTube Analytics API and auto-tunes `editor_memory.json`.

## How to Apply in Your Local Repo
1. Extract this zip into your `yt-daily-shorts` root folder (overwrite matching files).
2. In `core/llm_client.py`, import `get_cached_free_models` from `core.model_auto_discovery` when `"auto-free"` is encountered.
3. Verify locally before pushing:
   ```bash
   python main.py --llm-check
   python main.py --video-type knowledge --dry-run
   pytest
   ```
4. Commit and push to `origin main`.
