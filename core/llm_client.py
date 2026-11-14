"""Multi-provider LLM layer with automatic fallback.

Providers: Gemini (native REST), and OpenAI-compatible Groq, Mistral,
OpenRouter, NVIDIA NIM and Ollama Cloud. They are tried in the configured
order; a provider/model that errors, rate-limits or returns invalid JSON
falls through to the next one. The mock provider is used ONLY when
``allow_mock`` is set (tests / offline dev) — never in a live run.
"""

from __future__ import annotations

import asyncio
import os
import threading
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("core.llm")


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

ROTATE_ON = ("HTTP 429", "HTTP 413", "HTTP 401", "HTTP 403", "HTTP 503", "quota",
             "RESOURCE_EXHAUSTED", "timeout", "timed out")


def split_keys(value: str) -> List[str]:
    """'k1,k2' -> ['k1', 'k2'] (spaces/quotes/newlines ignored, duplicates dropped)."""
    out = []
    for k in str(value or "").replace("\n", ",").replace(";", ",").split(","):
        k = k.strip().strip('"').strip("'").strip()
        if k and k not in out:
            out.append(k)
    return out


class _KeyRing:
    """Several API keys for one provider: on quota/limit/overload errors the next key is tried."""

    def _init_keys(self, api_key) -> None:
        self.keys = api_key if isinstance(api_key, list) else split_keys(api_key)
        self.api_key = self.keys[0] if self.keys else ""
        self._ki = 0
        self._tl = threading.local()

    def _key(self) -> str:
        return getattr(self._tl, "key", None) or self.api_key

    def _rotating(self, fn, *args):
        """Try the keys in ring order; a hung key is retired for the whole run.

        A 429/503 is per-request and worth retrying later, but a timeout means
        the key's endpoint is stalling — retrying it on every model would add
        minutes to a run, so it is parked in ``_bad``.
        """
        usable = [k for k in self.keys if k not in getattr(self, "_bad", ())] or list(self.keys)
        if len(usable) <= 1:
            self._tl.key = usable[0]
            return fn(*args)
        last = None
        for step in range(len(usable)):
            key = usable[(self._ki + step) % len(usable)]
            self._tl.key = key
            try:
                out = fn(*args)
                self._ki = (self._ki + step) % len(usable)
                return out
            except LLMError as exc:
                last = exc
                msg = str(exc)
                if "timeout" in msg or "timed out" in msg:
                    if not hasattr(self, "_bad"):
                        self._bad = set()
                    self._bad.add(key)
                    logger.warning("%s key %s…%s is stalling — parked for this run",
                                   self.name, key[:6], key[-4:])
                if not any(c in msg for c in ROTATE_ON):
                    raise
                logger.info("%s key #%d hit a limit, trying the next key", self.name,
                            (self._ki + step) % len(usable) + 1)
        raise last


def extract_json(text: str) -> Dict[str, Any]:
    """Parse the first JSON object in *text* (tolerates fences / chatter)."""
    if not text:
        raise LLMError("empty LLM response")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("no JSON object in LLM response")
    snippet = cleaned[start:end + 1]
    snippet = re.sub(r",\s*([}\]])", r"\1", snippet)  # trailing commas
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise LLMError(f"invalid JSON from LLM: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("LLM JSON is not an object")
    return data


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class BaseLLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None,
                            json_mode: bool = False) -> str:
        ...

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        instr = ("\n\nReturn ONLY one valid JSON object. No markdown fences, no commentary.")
        text = await self.generate_text(prompt + instr, system_prompt, json_mode=True)
        return extract_json(text)


class GeminiProvider(_KeyRing, BaseLLMProvider):
    """Google Gemini via the v1beta REST API (no deprecated SDK)."""

    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model_name: str, temperature: float = 0.7,
                 max_tokens: int = 4096, timeout: int = 90):
        self._init_keys(api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _call(self, prompt: str, system_prompt: Optional[str], json_mode: bool) -> str:
        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        try:
            resp = requests.post(
                self.URL.format(model=self.model_name),
                headers={"x-goog-api-key": self._key(), "Content-Type": "application/json"},
                json=body, timeout=self.timeout,
            )
        except requests.RequestException as exc:   # hang / reset: rotate to the next key
            raise LLMError(f"gemini/{self.model_name} timeout: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LLMError(f"gemini/{self.model_name} HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"gemini/{self.model_name} empty candidates: {str(data)[:300]}") from exc
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    async def generate_text(self, prompt, system_prompt=None, json_mode=False) -> str:
        return await asyncio.to_thread(self._rotating, self._call, prompt, system_prompt, json_mode)


class OpenAICompatProvider(_KeyRing, BaseLLMProvider):
    """Any OpenAI-compatible /chat/completions endpoint."""

    BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "nvidia": "https://integrate.api.nvidia.com/v1",
        "ollama": "https://ollama.com/v1",
        "agnes": "https://apihub.agnes-ai.com/v1",   # free tier, text + images
    }

    def __init__(self, provider: str, api_key: str, model_name: str, temperature: float = 0.7,
                 max_tokens: int = 4096, timeout: int = 90):
        self.name = provider
        self.base_url = self.BASE_URLS[provider]
        self._init_keys(api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}
        if self.name == "openrouter":
            h["HTTP-Referer"] = "https://github.com/agrilearningpoint/yt-daily-shorts"
            h["X-Title"] = "yt-daily-shorts"
        return h

    def _post(self, payload: Dict[str, Any]):
        """POST with transport errors converted into rotatable LLMErrors."""
        try:
            return requests.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                                 json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"{self.name}/{self.model_name} timeout: {type(exc).__name__}") from exc

    def _call(self, prompt: str, system_prompt: Optional[str], json_mode: bool) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode and self.name in ("groq", "mistral", "openrouter", "agnes"):
            payload["response_format"] = {"type": "json_object"}
        resp = self._post(payload)
        if resp.status_code == 400 and "response_format" in payload:
            payload.pop("response_format")
            resp = self._post(payload)
        if resp.status_code != 200:
            raise LLMError(f"{self.name}/{self.model_name} HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"{self.name}/{self.model_name} bad response: {str(data)[:300]}") from exc
        return content

    async def generate_text(self, prompt, system_prompt=None, json_mode=False) -> str:
        return await asyncio.to_thread(self._rotating, self._call, prompt, system_prompt, json_mode)


class MockLLMProvider(BaseLLMProvider):
    """Deterministic offline provider — tests and local dev only."""

    name = "mock"

    async def generate_text(self, prompt, system_prompt=None, json_mode=False, tier="") -> str:
        if json_mode:
            return json.dumps(await self.generate_json(prompt))
        return "यह एक परीक्षण उत्तर है।"

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None,
                            tier: str = "") -> Dict[str, Any]:
        if "FACT_CHECK" in prompt:
            return {"verdict": "pass", "confidence": 0.9, "issues": [], "corrected_scenes": []}
        # v2 news schema: the prompt asks for "national"/"international" story buckets.
        if '"national"' in prompt and '"international"' in prompt:
            def _count(pattern: str, default: int) -> int:
                hit = re.search(pattern, prompt)
                return int(hit.group(1)) if hit else default

            n_nat = _count(r"(\d+)\s+DIFFERENT Indian stories", 16)
            n_int = _count(r"(\d+)\s+DIFFERENT world stories", 4)
            topics = ["डिजिटल इंडिया", "इसरो मिशन", "किसान योजना", "रेलवे विस्तार",
                      "निर्यात वृद्धि", "शिक्षा नीति"]

            def story(i: int, _section: str) -> Dict[str, Any]:
                topic = topics[i % len(topics)]
                return {
                    "on_screen_text": topic,
                    "src": (i % 6) + 1,
                    "parts": [
                        {"say": f"सरकार ने {topic} पर बड़ा फैसला लिया है",
                         "visual": "Indian parliament building", "entity": "Parliament House (India)",
                         "search": "india parliament", "source": "entity"},
                        {"say": "इससे लाखों लोगों को सीधा फायदा मिलेगा",
                         "visual": "happy indian families", "entity": "",
                         "search": "indian family", "source": "stock"},
                    ],
                }

            return {
                "title": "आज की बड़ी खबरें",
                "hook": f"आज की सबसे बड़ी खबर: {topics[0]} पर सरकार का बड़ा फैसला",
                "national": [story(i, "national") for i in range(max(n_nat, 4))],
                "international": [story(i, "international") for i in range(max(n_int, 2))],
                "sources": ["https://pib.gov.in", "https://ddnews.gov.in"],
            }
        if "SEO_METADATA" in prompt:
            return {"title": "भारत की बड़ी उपलब्धि | 60 सेकंड में", "tags": ["india", "hindi news"],
                    "description_hook": "जानिए आज की सबसे अहम बात।"}
        return {
            "title": "आज की बड़ी खबरें - 60 सेकंड में",
            "hook": "क्या आप जानते हैं आज देश में कौन सा बड़ा फैसला हुआ?",
            "scenes": [
                {"scene_number": 1, "on_screen_text": "बड़ा फैसला",
                 "parts": [{"say": "भारत सरकार ने आज डिजिटल इंफ्रास्ट्रक्चर को लेकर", "visual": "india digital infrastructure", "entity": "", "search": "india digital infrastructure", "source": "stock"}, {"say": "एक बड़ा और अहम निर्णय लिया है जिसका", "visual": "india digital infrastructure", "entity": "", "search": "india digital infrastructure", "source": "stock"}, {"say": "असर करोड़ों लोगों पर होगा।", "visual": "india digital infrastructure", "entity": "", "search": "india digital infrastructure", "source": "stock"}],
                 "visual_keywords": "india digital infrastructure", "sources": ["https://pib.gov.in"]},
                {"scene_number": 2, "on_screen_text": "युवाओं को फायदा",
                 "parts": [{"say": "इस परियोजना से लाखों युवाओं को रोजगार मिलेगा", "visual": "indian youth technology", "entity": "", "search": "indian youth technology", "source": "stock"}, {"say": "और गांवों तक तेज इंटरनेट पहुंचेगा, जिससे पढ़ाई", "visual": "indian youth technology", "entity": "", "search": "indian youth technology", "source": "stock"}, {"say": "और कारोबार दोनों आसान होंगे।", "visual": "indian youth technology", "entity": "", "search": "indian youth technology", "source": "stock"}],
                 "visual_keywords": "indian youth technology", "sources": ["https://pib.gov.in"]},
                {"scene_number": 3, "on_screen_text": "आपकी राय?",
                 "parts": [{"say": "विशेषज्ञ मानते हैं कि यह कदम अर्थव्यवस्था को", "visual": "india economy growth", "entity": "", "search": "india economy growth", "source": "stock"}, {"say": "नई रफ्तार देगा। आपको क्या लगता है? कमेंट", "visual": "india economy growth", "entity": "", "search": "india economy growth", "source": "stock"}, {"say": "में बताइए और चैनल को सब्सक्राइब कीजिए।", "visual": "india economy growth", "entity": "", "search": "india economy growth", "source": "stock"}],
                 "visual_keywords": "india economy growth", "sources": ["https://pib.gov.in"]},
            ],
            "sources": ["https://pib.gov.in"],
        }


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

def _openrouter_free_models(api_key: str, limit: int = 4) -> List[str]:
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models",
                            headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
        models = [m["id"] for m in resp.json().get("data", []) if str(m.get("id", "")).endswith(":free")]
        preferred = [m for m in models if any(k in m for k in ("gemini", "llama", "qwen", "gpt-oss", "deepseek", "mistral"))]
        return (preferred or models)[:limit]
    except Exception as exc:  # pragma: no cover - network
        logger.warning("OpenRouter model discovery failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Auto model discovery: asks each provider which models exist RIGHT NOW, so a
# retired model never breaks the pipeline. Preferred ids from settings come
# first (if still listed), then the best discovered ones.
# ---------------------------------------------------------------------------

_EXCLUDE = ("tts", "audio", "image", "embed", "whisper", "guard", "safety", "transcribe", "live",
            "robotics", "vision", "ocr", "rerank", "parse", "moderation", "translate", "orpheus",
            "omni", "lyria", "veo", "imagen", "computer-use", "deep-research", "antigravity", "argon",
            "nano-banana", "calibration", "reward", "nemoguard", "-pro")
_PREFER = {
    "gemini": ("flash",),
    "groq": ("gpt-oss-120b", "qwen", "gpt-oss-20b", "llama"),
    "mistral": ("mistral-medium-latest", "mistral-small-latest", "mistral-large-latest", "ministral-14b-latest"),
    "nvidia": ("nemotron-3-ultra", "nemotron-3.5-super", "deepseek-v4", "gpt-oss", "mistral-large", "nemotron"),
    "ollama": ("gpt-oss", "qwen", "deepseek"),
}


def _version_key(model_id: str) -> tuple:
    nums = re.findall(r"(\d+(?:\.\d+)?)", model_id)
    ver = float(nums[0]) if nums else 0.0
    lite = 1 if "lite" in model_id else 0
    preview = 1 if ("preview" in model_id or "exp" in model_id) else 0
    return (-ver, lite, preview, model_id)


def discover_models(provider: str, api_key: str, limit: int = 4, timeout: int = 20) -> List[str]:
    """Return currently-available chat model ids for *provider* (best first)."""
    try:
        if provider == "gemini":
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             headers={"x-goog-api-key": api_key}, params={"pageSize": 200}, timeout=timeout)
            ids = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                   if "generateContent" in m.get("supportedGenerationMethods", [])]
            ids = [i for i in ids if ("flash" in i or "gemma" in i) and not any(x in i for x in _EXCLUDE)]
            flash = sorted([i for i in ids if "flash" in i and "latest" not in i], key=_version_key)
            return (flash + [i for i in ids if "gemma" in i])[:limit]
        if provider == "openrouter":
            return _openrouter_free_models(api_key, limit)
        base = OpenAICompatProvider.BASE_URLS[provider]
        r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        ids = [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        ids = [i for i in ids if not any(x in i.lower() for x in _EXCLUDE)]
        ranked: List[str] = []
        for pat in _PREFER.get(provider, ()):
            ranked += sorted([i for i in ids if pat in i and i not in ranked], key=_version_key)
        return ranked[:limit]
    except Exception as exc:  # pragma: no cover - network
        logger.warning("Model discovery failed for %s: %s", provider, exc)
        return []


class FallbackLLM(BaseLLMProvider):
    """Tries each (provider, model) in order until one succeeds."""

    name = "fallback"

    def __init__(self, candidates: List[BaseLLMProvider], allow_mock: bool = False,
                 tiers: Optional[Dict[str, List[BaseLLMProvider]]] = None):
        self.candidates = candidates
        # Stage routing: {"quality": [preferred candidates..., rest of the chain]}
        self.tiers: Dict[str, List[BaseLLMProvider]] = tiers or {}
        self.allow_mock = allow_mock
        self.last_used: str = ""
        self.errors: List[str] = []
        self.dead: set = set()
        self.strikes: Dict[str, int] = {}

    @property
    def is_mock(self) -> bool:
        return not self.candidates and self.allow_mock

    def order_for(self, tier: str = "") -> List[BaseLLMProvider]:
        """Candidates for one call — a tier reorders the chain, never shrinks it."""
        return self.tiers.get(tier) or self.candidates

    async def _run(self, method: str, prompt: str, system_prompt: Optional[str],
                   tier: str = "") -> Any:
        self.errors = []
        for cand in self.order_for(tier):
            label = f"{cand.name}/{getattr(cand, 'model_name', '')}"
            if label in self.dead:
                continue
            for attempt in range(2):
                try:
                    result = await getattr(cand, method)(prompt, system_prompt)
                    if method == "generate_text" and not str(result).strip():
                        raise LLMError("empty text")
                    self.last_used = label
                    logger.info("LLM success via %s", label)
                    return result
                except Exception as exc:
                    msg = str(exc)
                    self.errors.append(f"{label}: {msg[:200]}")
                    logger.warning("LLM %s failed (attempt %d): %s", label, attempt + 1, msg[:200])
                    if any(c in msg for c in ("HTTP 404", "HTTP 410", "HTTP 402", "HTTP 401", "HTTP 403")):
                        self.dead.add(label)  # model retired / no access: skip for the rest of the run
                    if "exceeded your current quota" in msg or "billing" in msg:
                        # daily quota spent (gemini free tier is 20 RPD) — it will
                        # not come back inside this run, so stop paying for it
                        self.dead.add(label)
                        logger.warning("LLM %s is out of daily quota — parked for the rest of the run", label)
                    elif "timeout" in msg or "timed out" in msg:
                        # a hung model already cost one full timeout — never again
                        self.dead.add(label)
                        logger.warning("LLM %s hung (timeout) — parked for the rest of the run", label)
                    elif any(c in msg for c in ("HTTP 503", "high demand", "overloaded")):
                        self.strikes[label] = self.strikes.get(label, 0) + 1
                        if self.strikes[label] >= 2:      # twice is enough — don't stall every call
                            self.dead.add(label)
                    transient = any(c in msg for c in ("HTTP 500", "HTTP 502", "HTTP 504", "invalid JSON"))
                    if transient and attempt == 0:
                        await asyncio.sleep(4)
                        continue
                    break
        if self.allow_mock:
            logger.warning("All LLM providers failed/unavailable — using MOCK provider (dry-run only).")
            self.last_used = "mock"
            return await getattr(MockLLMProvider(), method)(prompt, system_prompt)
        raise LLMError("All LLM providers failed: " + " | ".join(self.errors[-6:]))

    async def generate_text(self, prompt, system_prompt=None, json_mode=False, tier="") -> str:
        return await self._run("generate_text", prompt, system_prompt, tier=tier)

    async def generate_json(self, prompt, system_prompt=None, tier="") -> Dict[str, Any]:
        return await self._run("generate_json", prompt, system_prompt, tier=tier)


def provider_keys(provider: str, main_key: str = "") -> List[str]:
    """Main secret + YT_<PROVIDER>_API_KEYS_EXTRA (comma list), de-duplicated."""
    extra = os.getenv(f"YT_{provider.upper()}_API_KEYS_EXTRA", "")
    return split_keys(f"{main_key},{extra}")


def _make_candidate(provider: str, ring: List[str], model: str, llm_cfg) -> BaseLLMProvider:
    kwargs = dict(temperature=llm_cfg.temperature, max_tokens=llm_cfg.max_tokens,
                  timeout=llm_cfg.timeout_sec)
    if provider == "gemini":
        return GeminiProvider(list(ring), model, **kwargs)
    return OpenAICompatProvider(provider, ring, model, **kwargs)


def build_llm(llm_cfg, allow_mock: bool = False) -> FallbackLLM:
    """Build the provider chain from an ``LLMConfig``."""
    keys = llm_cfg.keys()
    cap = max(1, int(getattr(llm_cfg, "max_keys_per_provider", 2) or 1))
    candidates: List[BaseLLMProvider] = []
    rings: Dict[str, List[str]] = {}
    for provider in llm_cfg.provider_order:
        # config-driven pool first (it already merges YT_<P>_API_KEY_<n> and
        # YT_<P>_API_KEYS_EXTRA); fall back to the env-only reader
        pool = []
        if hasattr(llm_cfg, "key_pool"):
            pool = [k for k in (llm_cfg.key_pool().get(provider) or []) if k]
        ring = pool or provider_keys(provider, keys.get(provider, ""))
        ring = ring[:max(1, int(getattr(llm_cfg, "max_keys_per_provider", 2) or 1))]
        if not ring:
            continue
        rings[provider] = ring
        key = ring[0]
        configured = list((llm_cfg.models or {}).get(provider) or ["auto"])
        preferred = [m for m in configured if m not in ("auto", "auto-free", "auto:free")]
        models = list(preferred)
        if any(m in ("auto", "auto-free", "auto:free") for m in configured):
            discovered = []
            for k in ring:   # a dead/limited key must not hide the provider's models
                discovered = discover_models(provider, k)
                if discovered:
                    break
            if discovered and preferred and provider != "openrouter":
                # keep preferred ids only if the provider still lists them
                still = [m for m in preferred if m in discovered]
                models = still + [m for m in discovered if m not in still]
            else:
                models = preferred + [m for m in discovered if m not in preferred]
        models = list(dict.fromkeys(models))[:5]
        if not models:
            continue
        logger.info("LLM %s models: %s", provider, models)
        for model in models:
            candidates.append(_make_candidate(provider, ring, model, llm_cfg))

    # ---- stage routing -----------------------------------------------------
    # Categories such as "quality" get the small-quota flagship first, then the
    # normal chain as fallback. A tier only REORDERS the chain, so a stage can
    # never end up with fewer options than the default path.
    tiers: Dict[str, List[BaseLLMProvider]] = {}
    for tier, per_provider in (getattr(llm_cfg, "tiers", None) or {}).items():
        if not isinstance(per_provider, dict):
            continue
        preferred_c: List[BaseLLMProvider] = []
        for provider, models in per_provider.items():
            ring = rings.get(provider) or provider_keys(provider, keys.get(provider, ""))
            ring = ring[:cap]
            if not ring:
                logger.warning("LLM tier %s wants %s but there is no key for it", tier, provider)
                continue
            for model in (models or []):
                preferred_c.append(_make_candidate(provider, ring, model, llm_cfg))
        if preferred_c:
            taken = {f"{c.name}/{c.model_name}" for c in preferred_c}
            tiers[tier] = preferred_c + [
                c for c in candidates if f"{c.name}/{c.model_name}" not in taken]
            logger.info("LLM tier %s prefers: %s", tier,
                        [f"{c.name}/{c.model_name}" for c in preferred_c])
    return FallbackLLM(candidates, allow_mock=allow_mock or llm_cfg.allow_mock, tiers=tiers)


async def health_check(llm_cfg) -> List[Tuple[str, bool, str]]:
    """Ping every key of every provider once (best model), then the model chain. ``main.py --llm-check``."""
    chain = build_llm(llm_cfg)
    results = []
    # Walk the configured model ladder, not just the first entry: when the
    # flagship is congested (gemini-3.8-flash 503s in bursts) the report must
    # still say whether the fallback tier the pipeline will actually use works.
    done = set()
    for cand in chain.candidates:
        label_model = (cand.name, cand.model_name)
        if label_model in done:
            continue
        done.add(label_model)
        for i, k in enumerate(getattr(cand, "keys", []) or [], 1):
            one = type(cand)(k, cand.model_name, timeout=60) if cand.name == "gemini" else \
                OpenAICompatProvider(cand.name, k, cand.model_name, timeout=60)
            label = f"{cand.name} key#{i} (...{k[-4:]}) {cand.model_name}"
            try:
                data = await one.generate_json('Return {"ok": true, "lang": "hi"} as JSON.')
                results.append((label, bool(data.get("ok")), "ok"))
            except Exception as exc:
                results.append((label, False, str(exc)[:160]))
    return results


# Backwards-compatible factory used by older code/tests
def get_llm_client(provider: str = "", api_key: str = "", model_name: Optional[str] = None,
                   temperature: float = 0.7) -> BaseLLMProvider:
    p = (provider or "").lower()
    if p == "gemini" and api_key:
        return GeminiProvider(api_key, model_name or "gemini-3.8-flash", temperature)
    if p in OpenAICompatProvider.BASE_URLS and api_key:
        return OpenAICompatProvider(p, api_key, model_name or "openai/gpt-oss-120b", temperature)
    return MockLLMProvider()
