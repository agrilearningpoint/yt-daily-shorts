"""Configuration tests."""

from __future__ import annotations

from core.configuration import AppConfig, EditorialCalendar, load_config, validate_config
from core.llm_client import FallbackLLM, build_llm, extract_json


def test_default_config_loading():
    cfg = load_config()
    assert cfg.general.project_name == "yt-daily-shorts"
    assert (cfg.video.width, cfg.video.height) == (1080, 1920)
    assert "gemini" in cfg.llm.provider_order


def test_editorial_calendar_categories():
    cal = EditorialCalendar()
    assert "Politics" in cal.get_today_category("Monday")
    assert "Economy" in cal.get_today_category("Sunday")


def test_live_mode_forces_strict(monkeypatch):
    monkeypatch.setenv("YT_DRY_RUN", "false")
    monkeypatch.setenv("YT_TIMEZONE", "UTC")
    cfg = load_config()
    assert cfg.general.dry_run is False and cfg.youtube.dry_run is False
    assert cfg.general.strict_mode is True and cfg.general.timezone == "UTC"


def test_llm_chain_skips_missing_keys(monkeypatch):
    for k in ("GEMINI", "GROQ", "MISTRAL", "OPENROUTER", "NVIDIA", "OLLAMA"):
        monkeypatch.delenv(f"YT_{k}_API_KEY", raising=False)
    cfg = AppConfig()
    cfg.llm.groq_api_key = "gsk_test"
    cfg.llm.models = {"groq": ["m1", "m2"]}
    chain = build_llm(cfg.llm)
    assert isinstance(chain, FallbackLLM)
    assert [c.name for c in chain.candidates] == ["groq", "groq"]


def test_extract_json_tolerant():
    assert extract_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json('Sure! {"b": [1, 2]} hope it helps') == {"b": [1, 2]}


def test_config_validation():
    assert isinstance(validate_config(AppConfig()), list)
