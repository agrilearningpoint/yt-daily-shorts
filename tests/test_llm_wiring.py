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
    # one candidate per (provider, model); each carries a key RING that rotates
    # on quota errors, so a dead key no longer removes the provider from the chain
    rings = {c.name: c.keys for c in chain.candidates}
    assert rings == {"gemini": ["g1", "g2"], "groq": ["groq1", "groq2"], "agnes": ["ag1"]}
    assert [c.name for c in chain.candidates][-1] == "agnes"
    assert chain.candidates[0].api_key == "g1"


def test_max_keys_per_provider_caps_chain(monkeypatch):
    monkeypatch.setattr("core.llm_client.discover_models", lambda *a, **k: [])
    cfg = LLMConfig(gemini_api_key="g1")
    cfg.provider_order = ["gemini"]
    cfg.models = {"gemini": ["m1", "m2"]}
    cfg.extra_keys = {"gemini": ["g2", "g3", "g4"]}
    cfg.max_keys_per_provider = 3
    chain = build_llm(cfg)
    # 2 models, and the ring is capped at 3 keys (g1..g3) — g4 is ignored
    assert len(chain.candidates) == 2
    assert all(c.keys == ["g1", "g2", "g3"] for c in chain.candidates)


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


def test_env_extra_comma_list_feeds_pool(monkeypatch, tmp_path):
    # isolate from the developer's real .env / ambient secrets
    monkeypatch.setattr("core.configuration.load_dotenv", lambda *a, **k: False)
    for i in range(2, 10):
        monkeypatch.delenv(f"YT_GEMINI_API_KEY_{i}", raising=False)
    monkeypatch.setenv("YT_GEMINI_API_KEY", "g1")
    monkeypatch.setenv("YT_GEMINI_API_KEYS_EXTRA", "g2, g3")
    cfg = load_config()
    assert cfg.llm.key_pool()["gemini"] == ["g1", "g2", "g3"]
    # and the runtime chain really builds a rotating ring from it
    llm = cfg.llm
    llm.provider_order = ["gemini"]
    llm.models = {"gemini": ["m1"]}
    llm.max_keys_per_provider = 3
    monkeypatch.setattr("core.llm_client.discover_models", lambda *a, **k: [])
    ring = build_llm(llm).candidates[0].keys
    assert ring == ["g1", "g2", "g3"]


def test_provider_order_drops_ollama_and_keeps_mistral():
    from core.configuration import LLMConfig

    order = LLMConfig().provider_order
    assert "ollama" not in order          # free tier is HTTP 402 — pure latency
    assert "mistral" in order             # 2 RPM / 40K TPM free tier works
    assert order.index("agnes") < order.index("openrouter")   # uncapped before the 50/day tier


def test_settings_models_are_the_probed_ones():
    import yaml
    from pathlib import Path

    cfg = yaml.safe_load(Path("config/settings.yaml").read_text())["llm"]
    models = cfg["models"]
    # latest free flagship first, flash-lite (500 RPD) as the volume workhorse
    assert models["gemini"][0] == "gemini-3.8-flash"
    assert models["gemini"][1] == "gemini-3.5-flash-lite"
    assert "gemini-3.1-flash-lite" in models["gemini"]
    # mistral-small/medium are capped at 0 req/min on the free tier
    assert not any("small" in m or "medium" in m for m in models["mistral"])
    assert models["mistral"][0] == "ministral-14b-latest"
    # inkling is 403 (agentic-harness only); every listed id was probed 200
    assert not any("inkling" in m for m in models["openrouter"])
    assert all(m.endswith(":free") for m in models["openrouter"])
    assert models["ollama"] == []
    # nvidia deepseek-v4.1-flash hung in CI (ReadTimeout) — one model is enough
    assert all("deepseek" not in m for m in models["nvidia"])


def test_transport_timeout_rotates_to_the_next_key():
    """A hung key must be rotated, not retried with the same key twice."""
    from core.llm_client import GeminiProvider, LLMError

    prov = GeminiProvider(["k1", "k2", "k3"], "gemini-3.8-flash")
    calls = []

    def fake_call(*a, **k):
        calls.append(prov._key())
        if prov._key() != "k3":
            raise LLMError("gemini/gemini-3.8-flash timeout: ReadTimeout")
        return "OK"

    assert prov._rotating(fake_call) == "OK"
    assert calls == ["k1", "k2", "k3"]


def test_a_model_that_keeps_503ing_is_dropped_for_the_run():
    import asyncio
    from core.llm_client import FallbackLLM, LLMError

    class Always503:
        name, model_name = "gemini", "gemini-3.8-flash"

        def __init__(self):
            self.hits = 0

        async def generate_text(self, prompt, system_prompt=None, json_mode=False):
            self.hits += 1
            raise LLMError("gemini/gemini-3.8-flash HTTP 503: high demand")

    class Healthy:
        name, model_name = "groq", "gpt-oss-120b"

        def __init__(self):
            self.hits = 0

        async def generate_text(self, prompt, system_prompt=None, json_mode=False):
            self.hits += 1
            return "fine"

    bad, good = Always503(), Healthy()
    chain = FallbackLLM([bad, good])

    async def run():
        for _ in range(6):
            assert await chain.generate_text("x") == "fine"

    asyncio.run(run())
    assert "gemini/gemini-3.8-flash" in chain.dead
    assert bad.hits == 2          # hit twice, then skipped for the rest of the run
    assert good.hits == 6


def test_a_stalling_key_is_parked_for_the_rest_of_the_run():
    from core.llm_client import GeminiProvider, LLMError

    prov = GeminiProvider(["slow", "fast1", "fast2"], "gemini-3.8-flash")

    def first_call(*a, **k):
        if prov._key() == "slow":
            raise LLMError("gemini/gemini-3.8-flash timeout: ReadTimeout")
        return "OK"

    assert prov._rotating(first_call) == "OK"
    assert prov._bad == {"slow"}
    # the next call must not touch the stalling key at all
    seen = []

    def later(*a, **k):
        seen.append(prov._key())
        return "OK"

    assert prov._rotating(later) == "OK"
    assert "slow" not in seen and len(seen) == 1   # ring advances, but never onto the parked key


# --------------------------------------------------------------------------- #
# Stage routing: the flagship's tiny quota goes to the stages that show
# --------------------------------------------------------------------------- #
def test_quality_tier_puts_the_flagship_first(monkeypatch):
    from core.llm_client import build_llm

    monkeypatch.setattr("core.llm_client.discover_models", lambda *a, **k: [])
    cfg = LLMConfig(gemini_api_key="g1")
    cfg.provider_order = ["gemini"]
    cfg.models = {"gemini": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]}
    cfg.tiers = {"quality": {"gemini": ["gemini-3.8-flash", "gemini-3.5-flash-lite"]}}

    chain = build_llm(cfg)
    labels = [f"{c.name}/{c.model_name}" for c in chain.candidates]
    assert labels[0] == "gemini/gemini-3.5-flash-lite"          # default chain untouched
    q = [f"{c.name}/{c.model_name}" for c in chain.order_for("quality")]
    assert q[:2] == ["gemini/gemini-3.8-flash", "gemini/gemini-3.5-flash-lite"]
    # a tier only reorders — nothing may be dropped from the fallback path
    assert set(labels) <= set(q)
    assert chain.order_for("") == chain.candidates


def test_quality_tier_still_falls_back_when_the_flagship_dies(monkeypatch):
    import asyncio
    from core.llm_client import build_llm, LLMError

    monkeypatch.setattr("core.llm_client.discover_models", lambda *a, **k: [])
    cfg = LLMConfig(gemini_api_key="g1", groq_api_key="q1")
    cfg.provider_order = ["gemini", "groq"]
    cfg.models = {"gemini": ["gemini-3.5-flash-lite"], "groq": ["openai/gpt-oss-120b"]}
    cfg.tiers = {"quality": {"gemini": ["gemini-3.8-flash"]}}

    chain = build_llm(cfg)
    # the flagship is congested; the lite tier must still answer (no real calls)
    for cand in chain.candidates:
        if cand.model_name == "gemini-3.8-flash":
            async def boom(*a, **k):
                raise LLMError("gemini/gemini-3.8-flash HTTP 503: high demand")
            cand.generate_json = boom
        else:
            async def fine(*a, **k):
                return {"ok": True}
            cand.generate_json = fine

    used = []

    async def run():
        for cand in chain.order_for("quality"):
            used.append(f"{cand.name}/{cand.model_name}")
        return await chain.generate_json('{"ok": true}', tier="quality")

    result = asyncio.run(run())
    assert used[0] == "gemini/gemini-3.8-flash"
    assert result["ok"] is True
    assert chain.last_used != "gemini/gemini-3.8-flash"


def test_script_and_seo_ask_for_the_quality_tier():
    from pathlib import Path

    script = Path("agents/script_manager/agent.py").read_text()
    seo = Path("agents/seo_manager/agent.py").read_text()
    assert 'tier="quality"' in script          # narration the viewer hears
    assert 'tier="quality"' in seo             # title/tags that decide the click
    # cheap stages stay on the default chain so they never eat the quota
    assert 'tier="quality"' not in Path("agents/research_manager/agent.py").read_text()
    assert 'tier="quality"' not in Path("agents/fact_verifier/agent.py").read_text()


def test_a_hung_model_is_retired_after_one_timeout():
    import asyncio
    from core.llm_client import FallbackLLM, LLMError

    class Hung:
        name, model_name = "gemini", "gemini-3.8-flash"

        def __init__(self):
            self.hits = 0

        async def generate_text(self, prompt, system_prompt=None, json_mode=False):
            self.hits += 1
            raise LLMError("gemini/gemini-3.8-flash timeout: ReadTimeout")

    class Fine:
        name, model_name = "gemini", "gemini-3.5-flash-lite"

        def __init__(self):
            self.hits = 0

        async def generate_text(self, prompt, system_prompt=None, json_mode=False):
            self.hits += 1
            return "ok"

    hung, fine = Hung(), Fine()
    chain = FallbackLLM([hung, fine])

    async def run():
        for _ in range(4):
            assert await chain.generate_text("x") == "ok"

    asyncio.run(run())
    assert hung.hits == 1                      # one timeout, never a second
    assert "gemini/gemini-3.8-flash" in chain.dead


def test_a_spent_daily_quota_parks_the_model_for_the_run():
    import asyncio
    from core.llm_client import FallbackLLM, LLMError

    class NoQuota:
        name, model_name = "gemini", "gemini-3.8-flash"

        def __init__(self):
            self.hits = 0

        async def generate_text(self, prompt, system_prompt=None, json_mode=False):
            self.hits += 1
            raise LLMError('gemini/gemini-3.8-flash HTTP 429: {"message": '
                           '"You exceeded your current quota, please check your plan"}')

    class Lite:
        name, model_name = "gemini", "gemini-3.5-flash-lite"

        def __init__(self):
            self.hits = 0

        async def generate_text(self, prompt, system_prompt=None, json_mode=False):
            self.hits += 1
            return "ok"

    spent, lite = NoQuota(), Lite()
    chain = FallbackLLM([spent, lite])

    async def run():
        for _ in range(5):
            assert await chain.generate_text("x") == "ok"

    asyncio.run(run())
    assert spent.hits == 1                    # quota won't refill mid-run
    assert lite.hits == 5
