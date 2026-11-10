# LLM Key Verification & Capacity Report

**Repo:** `agrilearningpoint/yt-daily-shorts`
**Probed:** 2026-11-10 (live API calls, not docs-only)
**Keys in pool:** 14 LLM keys across 7 providers (0 duplicates)

---

## 1. Verdict per provider

| Provider | Keys | Status | Free allowance (measured) | Notes |
|---|---|---|---|---|
| **Gemini** | 6 | ⚠️ flagship congested | 5 RPM · 250K TPM · **20 RPD/project** (3.8-flash)<br>15 RPM · **500 RPD** (3.5-flash-lite) | **3.8-flash is the latest free flagship and stays first in the chain**, but on 2026-11-10 it answered 429 (quota spent) / 503 (high demand) / timeout across the 6 keys. 3.5-flash-lite: **6/6 keys 200, avg 2.4 s** — the real volume tier |
| **Mistral** | 1 | ✅ works | **2 RPM · 40,000 TPM** | `mistral-small`/`medium` → 429 with `limit_req_minute: 0`; `ministral-14b-latest` + `open-mistral-nemo` → 200. `mistral-large` → 403 tier |
| **Groq** | 2 | ✅ works | 30 RPM · 8K TPM · 1,000 RPD · 200K TPD | limits are **per organization** — both keys share one quota |
| **Agnes** | 1 | ✅ works | 30 RPM · **no hard usage cap** | best free fallback; used for both text and images |
| **NVIDIA** | 1 | ✅ works | 40 RPM · 10,000 RPD + 1,000 signup credits | free-evaluation endpoints |
| **OpenRouter** | 2 | ✅ works | 20 RPM · **50 RPD** (`is_free_tier: true`) | 1,000 RPD after a one-time $10 top-up. `inkling:free` → 403 (agentic harness only), `gemma:free` → 429 |
| **Ollama** | 1 | ❌ 402 | 0 | paid credits/subscription required — **removed from the chain**, key kept |

**Live proof through the repo code (6/6):**
```
✅ gemini     -> gemini/gemini-3.6-flash
✅ mistral    -> mistral/ministral-14b-latest
✅ groq       -> groq/openai/gpt-oss-120b
✅ agnes      -> agnes/agnes-2.5-flash
✅ nvidia     -> nvidia/nvidia/nemotron-3-ultra-550b-a55b
✅ openrouter -> openrouter/nvidia/nemotron-3-ultra-550b-a55b:free
```

### Gemini ladder, measured (health_check now walks every model)

| Model | key#1 | key#2 | verdict |
|---|---|---|---|
| gemini-3.8-flash | 429 quota spent | 503 high demand | ⚠️ bursty, tiny 20 RPD |
| gemini-3.5-flash-lite | ✅ | ✅ | ✅ **the workhorse** |
| gemini-3.1-flash-lite | 503 | ✅ | usable |

### Stall handling (this is what protects a run)

| | before | after |
|---|---|---|
| First LLM call with 3.8-flash congested | 63.7 s | **5.6 s** |
| Five calls | 77 s | **21.6 s** |
| Hung key | retried twice on every call | parked for the run after one timeout |
| Model answering 503 twice | re-tried on every call | dropped for the run |

CI (`llm_check`, run 42814911002): 7/7 non-Gemini keys OK; 3.8-flash failed all
3 probed keys (429 / timeout / 503) exactly as predicted, and the chain still
served every call through 3.5-flash-lite.

---

## 2. Chain after the retune

```
provider_order: gemini → mistral → groq → agnes → nvidia → openrouter
timeout_sec: 60   # a hung key is parked after one timeout
models:
  gemini     gemini-3.8-flash, gemini-3.5-flash-lite, gemini-3.1-flash-lite
  mistral    ministral-14b-latest, open-mistral-nemo
  groq       openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b
  agnes      agnes-2.5-flash
  nvidia     nvidia/nemotron-3-ultra-550b-a55b, deepseek-ai/deepseek-v4.1-flash
  openrouter nvidia/nemotron-3-ultra-550b-a55b:free, nvidia/nemotron-3.5-lightning:free,
             dots-studio/dots-3-note-preview:free, liquid/lfm-3-1.7b:free,
             recursive/flint-v1.0:free
  ollama     []   # 402 — re-enable with ["auto"] after subscribing
```

16 candidates total. Keys rotate inside each provider on 429/413/503.

---

## 3. Capacity — how many shorts per day?

One short ≈ 8–10 LLM calls ≈ 30–40K tokens (research, fact-check, script ×2, SEO).

| Provider | Binding limit | Videos/day |
|---|---|---|
| Agnes | uncapped | **unlimited** |
| Mistral (40K TPM) | tokens/min | ~30+ |
| Groq (200K TPD) | tokens/day | ~5 |
| Gemini (1 project, flash) | 20 RPD | ~2 |
| Gemini (6 separate projects) | 120 RPD | ~12 |
| NVIDIA | 10K RPD | credit-bound |
| OpenRouter | 50 RPD | ~5 |
| Ollama | — | 0 |

**Realistic capacity: 10–20 shorts/day.** The plan needs 1–2/day.

### Important caveat
Gemini and Groq count quota **per project / per organization**, not per key.
Six Gemini keys inside one Google Cloud project still share 20 RPD. To turn the
6 keys into 6× quota, each key must live in its **own** Google Cloud project.

---

## 4. Recommended routing

| Task | Best free option | Why |
|---|---|---|
| Long script / research | Agnes 2.5-flash | uncapped, 30 RPM |
| Structured JSON | Groq gpt-oss-120b | fast + reliable schema |
| Final quality pass | Gemini 3.6-flash | best quality, but only 20 RPD |
| Bulk / high volume | Mistral ministral-14b | 40K TPM ceiling |
| Safety net | NVIDIA / OpenRouter | 10K RPD / 50 RPD |

---

## 5. Other credentials in the pool

| Secret | Status |
|---|---|
| `GNEWS_API_KEY` | ✅ 100 req/day, 10 Hindi articles verified |
| `PEXELS_API_KEY` / `PIXABAY_API_KEY` | ✅ stock media |
| `HF_TOKEN` | ✅ token valid; inference needs credits (402) but **storage + free FLUX Spaces work** |
| `TELEGRAM_BOT_TOKEN` / `CHAT_ID` | ✅ group `-1003886311757` |
| `YOUTUBE_CLIENT_SECRET_JSON` / `YOUTUBE_TOKEN_JSON` | ✅ publishing (OAuth) |

## 6. Storage

Private HF dataset `Rajaagri/yt-daily-shorts-artifacts` — verified in CI:
`videos/<date>/<video_id>/{final_short.mp4, captions.srt, thumbnail.jpg, manifest.json}`
plus `state/{yt_shorts.db, history.json}`. Last live upload: 59.62 MB mp4 + 8.05 MB db.
