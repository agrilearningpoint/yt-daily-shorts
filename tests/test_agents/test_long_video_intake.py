"""Unit tests for LongVideoIntakeAgent."""

import pytest

from agents.long_video_intake.agent import LongVideoIntakeAgent
from core.agent_contracts import SourceVideoManifest
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def intake_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return LongVideoIntakeAgent(cfg, sm)


@pytest.mark.asyncio
async def test_intake_local_file(intake_agent, tmp_path):
    test_file = tmp_path / "sample_bulletin.mp4"
    test_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")

    result = await intake_agent.execute(file_path=str(test_file), title="Test News Video")
    assert result.success is True
    manifest = result.data["manifest"]
    assert isinstance(manifest, SourceVideoManifest)
    assert manifest.is_local_file is True
    assert manifest.local_path == str(test_file.resolve())
    assert len(manifest.sha256) == 64
    assert manifest.title == "Test News Video"
    assert manifest.detected_language == "hi"


@pytest.mark.asyncio
async def test_intake_remote_url(intake_agent):
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = await intake_agent.execute(source_url=url, author="Sansad TV")
    assert result.success is True
    manifest = result.data["manifest"]
    assert isinstance(manifest, SourceVideoManifest)
    assert manifest.is_local_file is False
    assert manifest.source_uri == url
    assert manifest.author == "Sansad TV"
    assert manifest.video_id.startswith("lv_")


@pytest.mark.asyncio
async def test_intake_missing_input_fails(intake_agent):
    result = await intake_agent.execute()
    assert result.success is False
    assert len(result.errors) > 0
    assert "Neither 'file_path' nor 'source_url'" in result.errors[0]
