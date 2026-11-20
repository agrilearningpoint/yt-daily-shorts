"""Unit tests for NewsroomOrchestrator."""

import pytest
from pathlib import Path
from core.configuration import load_config
from core.history import HistoryStore
from core.newsroom_orchestrator import NewsroomOrchestrator, ProductionRunSummary
from core.state_manager import StateManager


@pytest.fixture
def newsroom(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    cfg.database.history_path = str(tmp_path / "history.json")
    sm = StateManager(cfg.database.sqlite_path)
    hist = HistoryStore(cfg.database.history_path)
    return NewsroomOrchestrator(cfg, sm, hist)


def test_newsroom_initialization(newsroom):
    assert newsroom.daily_opening_agent is not None
    assert newsroom.research_agent is not None
    assert newsroom.visual_sourcing_agent is not None
    assert newsroom.audio_sound_agent is not None
    assert newsroom.master_editing_agent is not None
    assert newsroom.visual_audio_qa_agent is not None
    assert newsroom.intake_agent is not None
    assert newsroom.transcription_agent is not None
    assert newsroom.scene_agent is not None
    assert newsroom.story_agent is not None
    assert newsroom.context_agent is not None
    assert newsroom.ranker_agent is not None
    assert newsroom.moment_agent is not None
    assert newsroom.adaptation_agent is not None
    assert newsroom.rights_agent is not None


@pytest.mark.asyncio
async def test_newsroom_stage_error_handling(newsroom):
    # Test stage error handling
    with pytest.raises(Exception):
        await newsroom._run_stage(
            "test_vid", "failing_stage",
            lambda: (_ for _ in ()).throw(RuntimeError("Forced stage error")),
            required=True
        )

    # Test non-required failure returns None without raising
    res = await newsroom._run_stage(
        "test_vid", "optional_stage",
        lambda: (_ for _ in ()).throw(RuntimeError("Optional error")),
        required=False
    )
    assert res is None
