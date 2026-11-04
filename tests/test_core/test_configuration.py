"""Unit tests for configuration loading and validation."""

from __future__ import annotations

import os
from core.configuration import AppConfig, EditorialCalendar, load_config, validate_config


def test_default_config_loading():
    cfg = load_config()
    assert cfg.general.project_name == "yt-daily-shorts"
    assert cfg.video.width == 1080
    assert cfg.video.height == 1920
    assert cfg.video.fps == 30
    assert cfg.editorial_calendar.monday != ""


def test_editorial_calendar_categories():
    cal = EditorialCalendar()
    assert "Politics" in cal.get_today_category("Monday")
    assert "Science" in cal.get_today_category("Tuesday")
    assert "Medical" in cal.get_today_category("Wednesday")
    assert "Personalities" in cal.get_today_category("Thursday")
    assert "History" in cal.get_today_category("Friday")
    assert "Facts" in cal.get_today_category("Saturday")
    assert "Economy" in cal.get_today_category("Sunday")


def test_env_override(monkeypatch):
    monkeypatch.setenv("YT_TIMEZONE", "UTC")
    monkeypatch.setenv("YT_DRY_RUN", "false")
    cfg = load_config()
    assert cfg.general.timezone == "UTC"
    assert cfg.general.dry_run is False


def test_config_validation():
    cfg = AppConfig()
    warnings = validate_config(cfg)
    assert isinstance(warnings, list)
