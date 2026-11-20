"""Tests for AudioSoundDesignAgent."""

import pytest
from pathlib import Path
from agents.audio_sound_design.agent import AudioSoundDesignAgent
from core.agent_contracts import AudioMixPlan
from core.configuration import AppConfig
from core.state_manager import StateManager


class MockTimelineSegment:
    def __init__(self, scene_id: str, audio_start: float, audio_end: float):
        self.scene_id = scene_id
        self.audio_start = audio_start
        self.audio_end = audio_end


@pytest.fixture
def agent(tmp_path):
    config = AppConfig()
    sm = StateManager(str(tmp_path / "test.db"))
    return AudioSoundDesignAgent(config, sm)


def test_validate_input(agent):
    assert not agent.validate_input()
    assert agent.validate_input(duration=30.0)
    assert agent.validate_input(timeline=[MockTimelineSegment("s1", 0.0, 5.0)])
    assert agent.validate_input(script="Test script")


@pytest.mark.asyncio
async def test_audio_sound_design_execution(agent, tmp_path):
    segments = [
        MockTimelineSegment("scene_001", 0.0, 5.0),
        MockTimelineSegment("scene_002", 5.0, 12.0),
        MockTimelineSegment("scene_003", 12.0, 20.0),
    ]

    res = await agent.execute(
        video_id="test_audio_001",
        duration=20.0,
        timeline_segments=segments,
        video_type="news",
    )

    assert res.success is True
    plan = res.data["mix_plan"]
    assert isinstance(plan, AudioMixPlan)
    assert plan.total_duration == 20.0
    assert plan.target_loudness_lufs == -14.0

    # Verify scheduled cues
    cues = plan.sound_cues
    assert len(cues) >= 2
    # Should have intro sting
    assert any(c.sound_type == "sting" and c.start_time == 0.0 for c in cues)
    # Should have outro sting
    assert any(c.sound_type == "sting" and c.trigger_type == "outro" for c in cues)


def test_render_mix_fallback(agent, tmp_path):
    out_file = tmp_path / "mixed.wav"
    plan = AudioMixPlan(
        mix_id="test_mix",
        total_duration=2.0,
        narration_audio_path="",
        background_bed_path="",
        sound_cues=[],
        output_master_audio_path=str(out_file),
    )
    result_path = agent.render_mix(plan, str(out_file))
    assert Path(result_path).exists()
    assert Path(result_path).stat().st_size > 0
