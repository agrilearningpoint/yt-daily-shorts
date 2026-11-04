"""Unit tests for SQLite state persistence and checkpointing."""

from __future__ import annotations

import tempfile
from pathlib import Path
from core.state_manager import PipelineState, StateManager


def test_state_creation_and_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        mgr = StateManager(db_path)

        vs = mgr.create_video_state(video_type="news", topic_category="Roundup")
        assert vs.video_id != ""
        assert vs.state == PipelineState.PENDING

        mgr.update_state(vs.video_id, state=PipelineState.RESEARCHING, title="Test Video Title")
        fetched = mgr.get_video_state(vs.video_id)
        assert fetched is not None
        assert fetched.state == PipelineState.RESEARCHING
        assert fetched.title == "Test Video Title"


def test_checkpointing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        mgr = StateManager(db_path)

        vs = mgr.create_video_state(video_type="knowledge")
        checkpoint_payload = {"script_hook": "नमस्ते दोस्तों", "word_count": 140}
        mgr.save_checkpoint(vs.video_id, "script_generation", checkpoint_payload)

        loaded = mgr.load_checkpoint(vs.video_id, "script_generation")
        assert loaded == checkpoint_payload

        # Overwrite test
        new_payload = {"script_hook": "Updated hook", "word_count": 150}
        mgr.save_checkpoint(vs.video_id, "script_generation", new_payload)
        assert mgr.load_checkpoint(vs.video_id, "script_generation") == new_payload
