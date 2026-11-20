"""Unit tests for VisualAudioMatchQAAgent."""

import pytest
from agents.visual_audio_match_qa.agent import VisualAudioMatchQAAgent
from core.agent_contracts import (
    MasterEditingTimeline,
    TimelineSegmentContract,
    VisualAudioMatchResult,
)
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def qa_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return VisualAudioMatchQAAgent(cfg, sm)


def test_validate_input(qa_agent):
    assert not qa_agent.validate_input()
    assert qa_agent.validate_input(timeline="tl")
    assert qa_agent.validate_input(video_path="v.mp4")
    assert qa_agent.validate_input(script={"scenes": []})


@pytest.mark.asyncio
async def test_qa_pre_render_valid(qa_agent, tmp_path):
    # Create dummy images
    img1 = tmp_path / "img1.jpg"
    img1.write_bytes(b"\xff\xd8\xff" + b"\x00" * 200)

    seg = TimelineSegmentContract(
        scene_id="scene_001",
        segment_id="seg_001",
        text="भारत ने इतिहास रचा",
        audio_path="",
        audio_start=0.0,
        audio_end=3.0,
        measured_duration=3.0,
        visual_id="v1",
        visual_path=str(img1),
        visual_start=0.0,
        visual_end=3.0,
        visual_source="test",
        transition_effect="flash",
        camera_motion="push_in",
    )

    tl = MasterEditingTimeline(
        video_id="qa_test_01",
        total_duration=3.0,
        segments=[seg],
    )

    res = await qa_agent.execute(video_id="qa_test_01", timeline=tl)
    assert res.success is True
    verdict = res.data["qa_result"]
    assert isinstance(verdict, VisualAudioMatchResult)
    assert verdict.approved is True
    assert verdict.pre_render_passed is True
    assert verdict.overall_match_score >= 80.0


@pytest.mark.asyncio
async def test_qa_catches_missing_asset(qa_agent):
    seg = TimelineSegmentContract(
        scene_id="scene_001",
        segment_id="seg_001",
        text="भारत ने इतिहास रचा",
        audio_path="",
        audio_start=0.0,
        audio_end=3.0,
        measured_duration=3.0,
        visual_id="v1",
        visual_path="non_existent_image_xyz_123.jpg",
        visual_start=0.0,
        visual_end=3.0,
        visual_source="test",
        transition_effect="flash",
        camera_motion="push_in",
    )

    tl = MasterEditingTimeline(
        video_id="qa_test_02",
        total_duration=3.0,
        segments=[seg],
    )

    res = await qa_agent.execute(video_id="qa_test_02", timeline=tl)
    assert res.success is False
    verdict = res.data["qa_result"]
    assert verdict.approved is False
    assert len(verdict.errors) >= 1
    assert "Visual asset missing" in verdict.errors[0]
