"""Unit tests for DailyOpeningDirectorAgent."""

import pytest

from agents.daily_opening_director.agent import DailyOpeningDirectorAgent
from core.agent_contracts import DailyOpeningBrief
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def opening_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return DailyOpeningDirectorAgent(cfg, sm)


@pytest.mark.asyncio
async def test_daily_opening_normal(opening_agent):
    result = await opening_agent.execute()
    assert result.success is True
    brief = result.data["opening_brief"]
    assert isinstance(brief, DailyOpeningBrief)
    assert len(brief.date_hi) > 0
    assert len(brief.weekday_hi) > 0
    assert len(brief.opening_hook_candidates) >= 3
    assert len(brief.visual_beats) == 3
    assert len(brief.motion_preset_ids) == 3
    assert len(brief.sound_cue_ids) == 3


@pytest.mark.asyncio
async def test_daily_opening_special_day_independence_day(opening_agent):
    result = await opening_agent.execute(date_override="2026-08-15")
    assert result.success is True
    brief = result.data["opening_brief"]
    assert "स्वतंत्रता दिवस" in brief.selected_special_day
    assert "15 अगस्त 2026" in brief.date_hi
    assert "स्वतंत्रता दिवस" in brief.spoken_script


@pytest.mark.asyncio
async def test_daily_opening_children_day(opening_agent):
    result = await opening_agent.execute(date_override="2026-11-20")
    assert result.success is True
    brief = result.data["opening_brief"]
    assert "विश्व बाल दिवस" in brief.selected_special_day
    assert "20 नवंबर 2026" in brief.date_hi
