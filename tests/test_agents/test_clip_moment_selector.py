"""Unit tests for ClipMomentSelectorAgent."""

import pytest

from agents.clip_moment_selector.agent import ClipMomentSelectorAgent
from core.agent_contracts import ExtractedStory, SelectedClip, TranscriptSegment, VisualScene
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def clip_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return ClipMomentSelectorAgent(cfg, sm)


@pytest.mark.asyncio
async def test_clip_moment_selection(clip_agent):
    story = ExtractedStory(
        story_id="story_gaganyaan",
        title="गगनयान परीक्षण सफल",
        category="science",
        start_time=20.0,
        end_time=35.0,
        key_facts=["सफल क्रू एस्केप"],
        entities=["इसरो"],
    )
    segments = [
        TranscriptSegment(
            segment_id="s1",
            speaker_id="SPEAKER_ANCHOR",
            start=20.0,
            end=25.5,
            text="इसरो ने गगनयान के लिए क्रू एस्केप सिस्टम का सफल परीक्षण किया।",
        ),
        TranscriptSegment(
            segment_id="s2",
            speaker_id="SPEAKER_SCIENTIST",
            start=26.0,
            end=31.8,
            text="श्रीहरिकोटा से यह प्रक्षेपण पूरी तरह सामान्य रहा।",
        ),
    ]
    scenes = [
        VisualScene(
            scene_index=0,
            start=20.0,
            end=26.0,
            keyframe_path="",
            speaker_position="center",
        ),
        VisualScene(
            scene_index=1,
            start=26.0,
            end=33.0,
            keyframe_path="",
            speaker_position="left",
        ),
    ]

    result = await clip_agent.execute(story=story, segments=segments, scenes=scenes)
    assert result.success is True
    clips = result.data["selected_clips"]
    assert len(clips) >= 1
    assert isinstance(clips[0], SelectedClip)
    assert 2.0 <= clips[0].duration <= 8.5
    assert result.data["hook_clip"] is not None
