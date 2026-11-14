"""Live free-model auto-discovery with 6-hour local cache for OpenRouter, Gemini, and Groq."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

import requests

CACHE_FILE = Path(".cache/free_models_cache.json")
CACHE_TTL_SEC = 6 * 3600

PREFERRED_PREFIXES = (
    "openrouter/free",
    "nvidia/nemotron",
    "google/gemma",
    "qwen/",
    "openai/gpt-oss",
    "meta-llama/",
    "dots-studio/",
)


def fetch_openrouter_free_models(limit: int = 8, timeout: int = 15) -> List[str]:
    """Fetch live zero-cost models from OpenRouter API (pricing.prompt == 0 and completion == 0)."""
    resp = requests.get("https://openrouter.ai/api/v1/models", timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    free_ids: List[str] = ["openrouter/free"]
    for item in data:
        mid = item.get("id", "")
        pricing = item.get("pricing") or {}
        is_zero = str(pricing.get("prompt", "1")) == "0" and str(pricing.get("completion", "1")) == "0"
        if is_zero and (mid.endswith(":free") or mid == "openrouter/free"):
            if any(x in mid for x in ("embed", "rerank", "tts", "whisper", "guard")):
                continue
            if mid not in free_ids:
                free_ids.append(mid)

    def _rank(m: str) -> Tuple[int, str]:
        for idx, p in enumerate(PREFERRED_PREFIXES):
            if m.startswith(p):
                return (idx, m)
        return (len(PREFERRED_PREFIXES), m)

    free_ids.sort(key=_rank)
    return free_ids[:limit]


def get_cached_free_models(provider: str = "openrouter", limit: int = 8) -> List[str]:
    """Return cached free models or refresh from live API if cache expired."""
    now = time.time()
    cache: Dict[str, Dict] = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    entry = cache.get(provider)
    if entry and (now - entry.get("ts", 0)) < CACHE_TTL_SEC and entry.get("models"):
        return entry["models"][:limit]

    if provider == "openrouter":
        models = fetch_openrouter_free_models(limit=limit)
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache[provider] = {"ts": now, "models": models}
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        return models
    return []
