# 🎬 YT Daily Shorts — Autonomous Hindi YouTube Shorts

[![Tests](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/tests.yml/badge.svg)](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/tests.yml)
[![Daily Production](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/daily_shorts.yml/badge.svg)](https://github.com/agrilearningpoint/yt-daily-shorts/actions/workflows/daily_shorts.yml)

Researches, writes, fact-checks, voices, edits and publishes a **daily Hindi news Short** (channel
BHARAT KI SOCH) on GitHub Actions using free tiers only. The knowledge Short is built but **paused** until the
news Short is perfect.

| Video | Time (IST) | Cron (UTC) | Content |
|---|---|---|---|
| News | 05:30 | `0 0 * * *` | ~2-minute bulletin: up to 30 national + 6 international stories from the **last 24 h only** (dated, verified), every spoken line with a real photo of that same story |
| Knowledge | paused | `0 9 * * *` (commented out) | 7-day editorial calendar (105 curated topics + LLM-suggested fresh topics) |

### Reliability rules (2026-11-08)
* **Fresh news only**: undated, older-than-24h or future-dated items are rejected; fewer fresh stories = a
  shorter video (minimum 12), never old news.
* **Claim-level fact check**: each used story's article text is fetched; unsupported stories are dropped.
* **One duration rule** (`core/duration.py`) shared by script writer, quality gate and post-render check (15-179 s).
* **No duplicate uploads**: every video carries a tag `bks-<type>-<YYYYMMDD IST>`; the channel is checked before
  uploading and after any failed upload. `force_upload` workflow input overrides.
* **Auto-retry** once on failure; **permanent state** (history, editor memory, DB) on the `state` branch.
* **Editor Director**: daily look, Gemini review of a contact sheet, flagged pictures replaced and re-rendered.
* **Health workflow**: 08:00 IST daily check (upload live, token, LLM keys) + Sunday weekly report on Telegram.

## Pipeline

```
research ─► prompt ─► script (LLM, validated) ─► fact-check (LLM, auto-corrects) ─► QUALITY GATE
   ─► theme ─► human-like Hindi voice (Gemini TTS, edge-tts fallback) split per beat by real pauses
   ─► one photo per beat (Wikipedia entity image / Commons / Openverse / Pexels / Pixabay)
   ─► motion graphics: Ken Burns + white-flash cuts + sliding headline chip + counter + progress bar
   ─► synthesized whoosh/pop SFX + ducked music (no subtitles) ─► MP4 1080x1920
   ─► SEO (LLM) ─► YouTube upload ─► Telegram preview + daily report ─► history/analytics (cached)
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
