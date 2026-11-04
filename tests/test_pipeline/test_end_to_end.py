"""End-to-end integration test for the entire multi-agent pipeline."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from core.configuration import load_config
from core.orchestrator import DailyOrchestrator, VideoTask
from core.state_manager import PipelineState, StateManager


@pytest.mark.asyncio
async def test_full_pipeline_dry_run():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "e2e_test.db")
        cfg = load_config()
        cfg.general.dry_run = True
        cfg.youtube.dry_run = True
        cfg.database.sqlite_path = db_path
        # Use mock LLM
        cfg.llm.provider = "mock"

        state_mgr = StateManager(db_path)
        orchestrator = DailyOrchestrator(cfg, state_mgr)

        task = VideoTask(
            video_type="news",
            topic_category="Test Roundup",
            scheduled_time="06:00",
            priority=1
        )

        vs = await orchestrator.run_pipeline(task)
        assert vs is not None
        assert vs.state == PipelineState.COMPLETED
        assert vs.youtube_id != ""

        # Verify checkpoints were created
        research_cp = state_mgr.load_checkpoint(vs.video_id, "research")
        assert research_cp is not None
        script_cp = state_mgr.load_checkpoint(vs.video_id, "script_generation")
        assert script_cp is not None
        assert "scenes" in script_cp
