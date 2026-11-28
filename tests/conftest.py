"""Test isolation.

Two rules, both learned the hard way:

1. Tests must never touch real provider keys. ``core.configuration.load_config()`` calls
   ``load_dotenv()``, which writes the developer's ``.env`` into ``os.environ`` for the whole
   process. Every later test then "sees" real Gemini/Groq keys, so assertions like "the chain
   only has groq" start failing depending on test order — and a careless test could make a real,
   billed API call.
2. ``LLMConfig()`` reads the environment directly (intentional in production), so isolation has to
   happen at the ``dotenv`` boundary, not just by deleting variables.
"""

from __future__ import annotations

import os

import pytest

_KEY_PREFIXES = (
    "YT_",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
    "OLLAMA_API_KEY",
    "AGNES_API_KEY",
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "GNEWS_API_KEY",
)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Run every test with an empty provider environment and a no-op .env loader."""
    for name in list(os.environ):
        if any(name == p or name.startswith(p) for p in _KEY_PREFIXES):
            monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr("core.configuration.load_dotenv", lambda *a, **k: False, raising=False)
    dotenv = pytest.importorskip("dotenv", reason="python-dotenv is optional here")
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False, raising=False)
    yield
