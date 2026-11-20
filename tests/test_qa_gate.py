"""Comprehensive tests verifying that QA failure strictly blocks publishing."""

import pytest

from core.configuration import AppConfig
from core.state_manager import StateManager
from core.agent_contracts import MasterEditingTimeline, TimelineSegmentContract
from agents.visual_audio_match_qa.agent import VisualAudioMatchQAAgent
from video.qa_inspector import VideoQAInspector


def test_video_qa_inspector_rejects_missing_file():
    inspector = VideoQAInspector()
    verdict = inspector.verify_video("non_existent_file.mp4")
    assert not verdict.approved
    assert any("File not found" in err for err in verdict.errors)


def test_video_qa_inspector_rejects_corrupted_small_file(tmp_path):
    small_file = tmp_path / "tiny.mp4"
    small_file.write_bytes(b"corrupt header only")
    inspector = VideoQAInspector()
    verdict = inspector.verify_video(str(small_file))
    assert not verdict.approved
    assert any("File size too small" in err for err in verdict.errors)


@pytest.mark.asyncio
async def test_visual_audio_qa_blocks_missing_visual_asset(tmp_path):
    cfg = AppConfig()
    sm = StateManager(":memory:")
    agent = VisualAudioMatchQAAgent(cfg, sm)

    timeline = MasterEditingTimeline(
        video_id="qa_test_001",
        total_duration=56.0,
        segments=[
            TimelineSegmentContract(
                scene_id="scene_000",
                segment_id="seg_0",
                text="संसद में आज नया विधेयक पेश हुआ",
                audio_path=str(tmp_path / "voice.wav"),
                audio_start=0.0,
                audio_end=5.0,
                measured_duration=5.0,
                visual_id="vis_000",
                visual_path=str(tmp_path / "missing_parliament.jpg"),
                visual_start=0.0,
                visual_end=5.0,
                visual_source="stock",
                transition_effect="flash",
                camera_motion="push_in",
            )
        ],
    )

    result = await agent.execute(video_id="qa_test_001", timeline=timeline)
    assert not result.success
    assert not result.data["approved"]
    assert any("missing or corrupt" in err for err in result.data["errors"])


@pytest.mark.asyncio
async def test_visual_audio_qa_passes_with_valid_assets(tmp_path):
    cfg = AppConfig()
    sm = StateManager(":memory:")
    agent = VisualAudioMatchQAAgent(cfg, sm)

    img_file = tmp_path / "parliament.jpg"
    img_file.write_bytes(b"A" * 1024)

    timeline = MasterEditingTimeline(
        video_id="qa_test_002",
        total_duration=56.0,
        segments=[
            TimelineSegmentContract(
                scene_id="scene_000",
                segment_id="seg_0",
                text="संसद में आज नया विधेयक पेश हुआ",
                audio_path=str(tmp_path / "voice.wav"),
                audio_start=0.0,
                audio_end=5.0,
                measured_duration=5.0,
                visual_id="vis_000",
                visual_path=str(img_file),
                visual_start=0.0,
                visual_end=5.0,
                visual_source="stock",
                transition_effect="flash",
                camera_motion="push_in",
            )
        ],
    )

    result = await agent.execute(video_id="qa_test_002", timeline=timeline)
    assert result.success
    assert result.data["approved"]
    assert len(result.data["errors"]) == 0
