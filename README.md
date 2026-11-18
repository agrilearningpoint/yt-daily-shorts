# 🎬 YT Daily Shorts — Autonomous Hindi YouTube Shorts

[![Tests](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/tests.yml/badge.svg)](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/tests.yml)
[![Daily Production](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/daily_shorts.yml/badge.svg)](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/daily_shorts.yml)

Researches, writes, fact-checks, voices, edits and publishes a **daily Hindi news Short** (channel
BHARAT KI SOCH) on GitHub Actions using free tiers only. The knowledge Short is built but **paused** until the
news Short is perfect.

| Video | Time (IST) | Cron (UTC) | Content |
|---|---|---|---|
| News | 05:30 | `0 0 * * *` | 50–58s superfast bulletin: 20+ national and international stories from the **last 24 h only** (dated, verified), every spoken line with a real photo of that same story |
| Knowledge | 14:30 | `0 9 * * *` | 50–58s researched explainer: 7-day editorial calendar (105 curated topics + LLM-suggested fresh topics) |

### Reliability rules
* **Fresh news only**: undated, older-than-24h or future-dated items are rejected; minimum 20 fresh stories for bulletin.
* **Claim-level fact check**: each used story's article text is fetched; unsupported stories are dropped.
* **One duration rule** (`core/duration.py`): Target 50–60s, Hard limit 59.9s for Shorts compliance.
* **Precision Audio-Video Synchronization** (`video/synchronization_engine.py`): Integer frame quantization with 0.000s cumulative drift.
* **Hook Director** (`agents/hook_director/`): Evaluates 6 viral archetypes and enforces opening 1–3s visual pairing contract.
* **Post-Render QA Inspector** (`video/qa_inspector.py`): 5-pillar validation (technical, audio, visual, sync, duration) with auto-repair.
* **No duplicate uploads**: every video carries a tag `bks-<type>-<YYYYMMDD IST>`; the channel is checked before uploading.
* **Auto-retry** once on failure; **permanent state** on the `state` branch and HF storage.

## Architecture & Documentation

- [Complete Architecture Audit](docs/COMPLETE_ARCHITECTURE_AUDIT.md)
- [New Multi-Agent Architecture](docs/NEW_AGENT_ARCHITECTURE.md)
- [Voice & Video Synchronization Design](docs/VOICE_VIDEO_SYNC_DESIGN.md)
- [Video Creative Direction Guide](docs/VIDEO_CREATIVE_DIRECTION.md)
- [Multi-Pillar Quality Assurance Report](docs/QUALITY_ASSURANCE_REPORT.md)
- [Implementation Changelog](docs/IMPLEMENTATION_CHANGELOG.md)

## Multi-Agent Pipeline

```
research ─► prompt ─► script ─► HOOK DIRECTOR ─► fact-check ─► QUALITY GATE
   ─► creative direction ─► VFX & MOTION GRAPHICS
   ─► SYNCHRONIZATION ENGINE (frame-accurate audio & visual bounds)
   ─► media collector (real photographs / Wikimedia / publisher)
   ─► FFmpeg video renderer (Ken Burns + transitions + burned captions)
   ─► POST-RENDER QA INSPECTOR (5 pillars + auto-repair)
   ─► SEO ─► YouTube upload ─► Telegram preview + daily report
```

* **Multi-LLM fallback + auto models**: Gemini → Groq → OpenRouter (free) → Mistral → NVIDIA NIM (→ Ollama).
  `"auto"` asks each provider's `/models` API at run time and picks the best current free model, so a retired
  model never breaks the pipeline; dead models (404/410/402) are skipped for the rest of the run.
* **Human-like voice**: Gemini 3.8 Flash TTS (free tier, Hindi, style-directed "TV news anchor"), voice picked
  automatically from Google's Hindi voice library; Microsoft edge-tts only as fallback.
* **Strict mode (automatic on live runs)**: no mock script, silent audio, offline news or fake MP4 can ever be
  published. Any failed gate stops that video and sends a Telegram alert.
* **Proper Devanagari**: bundled Mukta fonts (OFL) + Pillow/raqm shaping + libass captions.
* **Memory across runs**: `data/history.json` + SQLite are kept in the Actions cache, so topics and news never repeat
  and past performance (views) feeds back into hooks/titles.
* **Compliance**: every source URL + image credits in the description, AI disclosure text and
  `containsSyntheticMedia=true`, CC/stock images only.

## Setup (one time)

### 1. GitHub secrets (`Settings → Secrets and variables → Actions`)

| Secret | Needed | Notes |
|---|---|---|
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `MISTRAL_API_KEY` / `OPENROUTER_API_KEY` / `NVIDIA_API_KEY` / `OLLAMA_API_KEY` | at least one | more = more resilient |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | recommended | video previews, reports, alerts |
| `YOUTUBE_CLIENT_SECRET_JSON` | for upload | OAuth *Desktop app* client JSON |
| `YOUTUBE_TOKEN_JSON` | **for upload** | create with `scripts/get_youtube_token.py` (below) |
| `PEXELS_API_KEY`, `PIXABAY_API_KEY` | optional | better stock photos (free keys) |

Optional **variables**: `YT_YOUTUBE_PRIVACY` (`public` default, or `unlisted`/`private`), `YT_CHANNEL_NAME`.

### 2. Create `YOUTUBE_TOKEN_JSON` (on your own computer, once)

1. Google Cloud Console → enable **YouTube Data API v3**.
2. OAuth consent screen → External → add yourself as test user → **Publish app** (otherwise the token expires every 7 days).
3. Credentials → OAuth client ID → **Desktop app** → download as `client_secret.json`.
4. `pip install google-auth-oauthlib && python scripts/get_youtube_token.py client_secret.json`
5. Sign in with the account that owns the channel, copy the printed JSON into the `YOUTUBE_TOKEN_JSON` secret.

> Uploads from API projects that have not passed YouTube's API audit are locked to **private** by YouTube.
> Submit the audit form (YouTube API Services → Audit and Quota Extension) to publish publicly.

### 3. Test

* `Actions → Daily YouTube Shorts Production → Run workflow`
  * `llm_check = true` → pings every LLM provider/model.
  * `dry_run = true` → full video rendered, sent to Telegram + artifact, **no upload**.
* Scheduled runs are live (`dry_run=false`) automatically.

## Local development

```bash
pip install -r requirements.txt          # + ffmpeg on PATH
cp .env.example .env                     # add keys with YT_ prefix
python main.py --llm-check
python main.py --video-type news --dry-run
python main.py --status
python main.py --resume <video_id>
python -m pytest tests -q
```

## Customising

* `config/settings.yaml` — voice, rate, durations, models, provider order, hashtags, categories.
* `research/source_registry.py` — news feeds. `research/trend_discovery.py` — topic seeds per weekday.
* `prompts/` — script, fact-check and SEO prompts.
* `assets/music/` — drop royalty-free tracks for background music.

MIT licensed. Fonts: Mukta (SIL OFL, `assets/fonts/OFL.txt`).
