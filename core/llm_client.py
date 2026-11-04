"""Multi-provider LLM layer with automatic fallback.

Providers: Gemini (native REST), and OpenAI-compatible Groq, Mistral,
OpenRouter, NVIDIA NIM and Ollama Cloud. They are tried in the configured
order; a provider/model that errors, rate-limits or returns invalid JSON
falls through to the next one. The mock provider is used ONLY when
``allow_mock`` is set (tests / offline dev) — never in a live run.
"""

from __future__ import annotations

import asyncio
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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini via the v1beta REST API (no deprecated SDK)."""

    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model_name: str, temperature: float = 0.7,
                 max_tokens: int = 4096, timeout: int = 90):
        self.api_key = api_key
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
        resp = requests.post(
            self.URL.format(model=self.model_name),
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json=body, timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise LLMError(f"gemini/{self.model_name} HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"gemini/{self.model_name} empty candidates: {str(data)[:300]}") from exc
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    async def generate_text(self, prompt, system_prompt=None, json_mode=False) -> str:
        return await asyncio.to_thread(self._call, prompt, system_prompt, json_mode)


class OpenAICompatProvider(BaseLLMProvider):
    """Any OpenAI-compatible /chat/completions endpoint."""

    BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "nvidia": "https://integrate.api.nvidia.com/v1",
        "ollama": "https://ollama.com/v1",
    }

    def __init__(self, provider: str, api_key: str, model_name: str, temperature: float = 0.7,
                 max_tokens: int = 4096, timeout: int = 90):
        self.name = provider
        self.base_url = self.BASE_URLS[provider]
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.name == "openrouter":
            h["HTTP-Referer"] = "https://github.com/agrilearningpoint/yt-daily-shorts"
            h["X-Title"] = "yt-daily-shorts"
        return h

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
        if json_mode and self.name in ("groq", "mistral", "openrouter"):
            payload["response_format"] = {"type": "json_object"}
        resp = requests.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                             json=payload, timeout=self.timeout)
        if resp.status_code == 400 and "response_format" in payload:
            payload.pop("response_format")
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                                 json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise LLMError(f"{self.name}/{self.model_name} HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"{self.name}/{self.model_name} bad response: {str(data)[:300]}") from exc
        return content

    async def generate_text(self, prompt, system_prompt=None, json_mode=False) -> str:
        return await asyncio.to_thread(self._call, prompt, system_prompt, json_mode)


class MockLLMProvider(BaseLLMProvider):
    """Deterministic offline provider — tests and local dev only."""

    name = "mock"

    async def generate_text(self, prompt, system_prompt=None, json_mode=False) -> str:
        if json_mode:
            return json.dumps(await self.generate_json(prompt))
        return "यह एक परीक्षण उत्तर है।"

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if "FACT_CHECK" in prompt:
            return {"verdict": "pass", "confidence": 0.9, "issues": [], "corrected_scenes": []}
        if "SEO_METADATA" in prompt:
            return {"title": "भारत की बड़ी उपलब्धि | 60 सेकंड में", "tags": ["india", "hindi news"],
                    "description_hook": "जानिए आज की सबसे अहम बात।"}
        return {
            "title": "आज की बड़ी खबरें - 60 सेकंड में",
            "hook": "क्या आप जानते हैं आज देश में कौन सा बड़ा फैसला हुआ?",
            "scenes": [
                {"scene_number": 1, "on_screen_text": "बड़ा फैसला",
                 "narration": "भारत सरकार ने आज डिजिटल इंफ्रास्ट्रक्चर को लेकर एक बड़ा और अहम निर्णय लिया है जिसका असर करोड़ों लोगों पर होगा।",
                 "visual_keywords": "india digital infrastructure", "sources": ["https://pib.gov.in"]},
                {"scene_number": 2, "on_screen_text": "युवाओं को फायदा",
                 "narration": "इस परियोजना से लाखों युवाओं को रोजगार मिलेगा और गांवों तक तेज इंटरनेट पहुंचेगा, जिससे पढ़ाई और कारोबार दोनों आसान होंगे।",
                 "visual_keywords": "indian youth technology", "sources": ["https://pib.gov.in"]},
                {"scene_number": 3, "on_screen_text": "आपकी राय?",
                 "narration": "विशेषज्ञ मानते हैं कि यह कदम अर्थव्यवस्था को नई रफ्तार देगा। आपको क्या लगता है? कमेंट में बताइए और चैनल को सब्सक्राइब कीजिए।",
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


class FallbackLLM(BaseLLMProvider):
    """Tries each (provider, model) in order until one succeeds."""

    name = "fallback"

    def __init__(self, candidates: List[BaseLLMProvider], allow_mock: bool = False):
        self.candidates = candidates
        self.allow_mock = allow_mock
        self.last_used: str = ""
        self.errors: List[str] = []

    @property
    def is_mock(self) -> bool:
        return not self.candidates and self.allow_mock

    async def _run(self, method: str, prompt: str, system_prompt: Optional[str]) -> Any:
        self.errors = []
        for cand in self.candidates:
            label = f"{cand.name}/{getattr(cand, 'model_name', '')}"
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
                    transient = any(c in msg for c in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504", "timed out", "invalid JSON"))
                    if transient and attempt == 0:
                        await asyncio.sleep(4)
                        continue
                    break
        if self.allow_mock:
            logger.warning("All LLM providers failed/unavailable — using MOCK provider (dry-run only).")
            self.last_used = "mock"
            return await getattr(MockLLMProvider(), method)(prompt, system_prompt)
        raise LLMError("All LLM providers failed: " + " | ".join(self.errors[-6:]))

    async def generate_text(self, prompt, system_prompt=None, json_mode=False) -> str:
        return await self._run("generate_text", prompt, system_prompt)

    async def generate_json(self, prompt, system_prompt=None) -> Dict[str, Any]:
        return await self._run("generate_json", prompt, system_prompt)


def build_llm(llm_cfg, allow_mock: bool = False) -> FallbackLLM:
    """Build the provider chain from an ``LLMConfig``."""
    keys = llm_cfg.keys()
    candidates: List[BaseLLMProvider] = []
    for provider in llm_cfg.provider_order:
        key = keys.get(provider, "")
        if not key:
            continue
        models = list((llm_cfg.models or {}).get(provider) or [])
        if provider == "openrouter" and (not models or "auto-free" in models):
            models = [m for m in models if m != "auto-free"] + _openrouter_free_models(key)
        if not models:
            continue
        for model in models:
            kwargs = dict(temperature=llm_cfg.temperature, max_tokens=llm_cfg.max_tokens,
                          timeout=llm_cfg.timeout_sec)
            if provider == "gemini":
                candidates.append(GeminiProvider(key, model, **kwargs))
            else:
                candidates.append(OpenAICompatProvider(provider, key, model, **kwargs))
    return FallbackLLM(candidates, allow_mock=allow_mock or llm_cfg.allow_mock)


async def health_check(llm_cfg) -> List[Tuple[str, bool, str]]:
    """Ping every configured provider/model once. Used by ``main.py --llm-check``."""
    chain = build_llm(llm_cfg)
    results = []
    for cand in chain.candidates:
        label = f"{cand.name}/{getattr(cand, 'model_name', '')}"
        try:
            data = await cand.generate_json('Return {"ok": true, "lang": "hi"} as JSON.')
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
