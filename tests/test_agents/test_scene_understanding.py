"""Unit tests for SceneUnderstandingAgent."""

import json
from pathlib import Path
import pytest

from agents.scene_understanding.agent import SceneUnderstandingAgent
from core.agent_contracts import SourceVideoManifest, VisualScene
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def scene_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return SceneUnderstandingAgent(cfg, sm)


@pytest.mark.asyncio
async def test_scene_understanding_fixture(scene_agent):
    fixture_path = Path("tests/fixtures/repurposing/sample_scenes.json")
    scenes_data = json.loads(fixture_path.read_text(encoding="utf-8"))

    result = await scene_agent.execute(scenes=scenes_data, duration=35.0)
    assert result.success is True
    scenes = result.data["scenes"]
    assert len(scenes) == 5
    assert isinstance(scenes[0], VisualScene)
    assert scenes[0].scene_type == "studio_anchor"
    assert scenes[2].scene_type == "split_interview"
    assert scenes[2].speaker_position == "left"


@pytest.mark.asyncio
async def test_scene_understanding_synthetic_fallback(scene_agent, tmp_path):
    manifest = SourceVideoManifest(
        video_id="lv_test_mock",
        source_uri="mock.mp4",
        is_local_file=False,
        local_path="",
        sha256="000111222333444",
        duration=30.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        audio_channels=2,
        audio_sample_rate=44100,
        has_audio=True,
    )

    result = await scene_agent.execute(manifest=manifest, allow_synthetic=True)
    assert result.success is True
    assert result.data["total_scenes"] >= 3
    keyframe_dir = Path(result.data["keyframe_dir"])
    assert keyframe_dir.exists()
    keyframes = list(keyframe_dir.glob("*.jpg"))
    assert len(keyframes) >= 3


@pytest.mark.asyncio
async def test_scene_understanding_inaccessible_video_fails_honestly(scene_agent):
    manifest = SourceVideoManifest(
        video_id="lv_inaccessible",
        source_uri="missing.mp4",
        is_local_file=True,
        local_path="non_existent_file.mp4",
        sha256="123456",
        duration=30.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        audio_channels=2,
        audio_sample_rate=44100,
        has_audio=True,
    )
    result = await scene_agent.execute(manifest=manifest)
    assert result.success is False
    assert result.data.get("scene_analysis_status") == "video_inaccessible"
