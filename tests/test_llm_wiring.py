"""Wiring tests: key pools, Agnes provider, HF media source."""

from __future__ import annotations

import os

from core.configuration import LLMConfig, load_config
from core.llm_client import OpenAICompatProvider, build_llm


def test_extra_keys_form_a_pool():
    cfg = LLMConfig(gemini_api_key="primary")
    cfg.extra_keys = {"gemini": ["spare1", "spare2"]}
    pool = cfg.key_pool()
    assert pool["gemini"] == ["primary", "spare1", "spare2"]
    assert cfg.key_count() == 3


def test_pool_deduplicates_primary():
    cfg = LLMConfig(groq_api_key="k1")
    cfg.extra_keys = {"groq": ["k1", "k2"]}
    assert cfg.key_pool()["groq"] == ["k1", "k2"]


def test_agnes_is_a_text_provider():
    assert "agnes" in LLMConfig().keys()
    assert OpenAICompatProvider.BASE_URLS["agnes"] == "https://apihub.agnes-ai.com/v1"


def test_build_llm_uses_every_pooled_key(monkeypatch):
    monkeypatch.setattr("core.llm_client.discover_models", lambda *a, **k: [])
    cfg = LLMConfig(gemini_api_key="g1", groq_api_key="groq1", agnes_api_key="ag1")
    cfg.provider_order = ["gemini", "groq", "agnes"]
    cfg.models = {"gemini": ["gemini-3.8-flash"], "groq": ["openai/gpt-oss-120b"],
                  "agnes": ["agnes-2.5-flash"]}
    cfg.extra_keys = {"gemini": ["g2", "g3"], "groq": ["groq2"]}
    cfg.max_keys_per_provider = 2

    chain = build_llm(cfg)
    keys = [c.api_key for c in chain.candidates]
    # gemini: 1 model x 2 keys, groq: 1 model x 2 keys, agnes: 1 model x 1 key
    assert keys == ["g1", "g2", "groq1", "groq2", "ag1"]
    names = [c.name for c in chain.candidates]
    assert names[-1] == "agnes"


def test_max_keys_per_provider_caps_chain(monkeypatch):
    monkeypatch.setattr("core.llm_client.discover_models", lambda *a, **k: [])
    cfg = LLMConfig(gemini_api_key="g1")
    cfg.provider_order = ["gemini"]
    cfg.models = {"gemini": ["m1", "m2"]}
    cfg.extra_keys = {"gemini": ["g2", "g3", "g4"]}
    cfg.max_keys_per_provider = 3
    chain = build_llm(cfg)
    assert len(chain.candidates) == 6   # 2 models x 3 keys (not 4 keys)


def test_env_extras_are_picked_up(monkeypatch):
    monkeypatch.setenv("YT_GEMINI_API_KEY", "env-primary")
    monkeypatch.setenv("YT_GEMINI_API_KEY_2", "env-spare")
    monkeypatch.setenv("YT_AGNES_API_KEY", "env-agnes")
    monkeypatch.setenv("YT_MAX_KEYS_PER_PROVIDER", "3")
    cfg = load_config()
    assert cfg.llm.gemini_api_key == "env-primary"
    assert "env-spare" in cfg.llm.extra_keys.get("gemini", [])
    # Agnes key feeds both the image source and the text provider
    assert cfg.llm.agnes_api_key == "env-agnes"
    assert cfg.media.agnes_api_key == "env-agnes"
    assert cfg.llm.max_keys_per_provider == 3


def test_hf_source_is_wired_but_optional():
    from video.media_collector import MediaCollector

    assert hasattr(MediaCollector, "_huggingface")
    # no token -> no attempt, no crash
    mc = MediaCollector()
    assert mc._huggingface("test visual", __import__("pathlib").Path("/tmp/x.jpg")) is None
