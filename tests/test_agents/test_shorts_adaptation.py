"""Unit tests for ShortsAdaptationAgent."""

import pytest

from agents.shorts_adaptation.agent import ShortsAdaptationAgent
from core.agent_contracts import (
    AdaptedShortScript,
    EvidenceClaim,
    ExtractedStory,
    SelectedClip,
    StoryRanking,
)
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def adapt_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return ShortsAdaptationAgent(cfg, sm)


@pytest.mark.asyncio
async def test_shorts_adaptation_template_generation(adapt_agent):
    story = ExtractedStory(
        story_id="story_isro_01",
        title="इसरो गगनयान क्रू एस्केप सिस्टम सफल",
        category="science",
        start_time=20.0,
        end_time=35.0,
        key_facts=["श्रीहरिकोटा से प्रक्षेपण सफल"],
        entities=["इसरो", "गगनयान"],
        transcript_excerpt="इसरो ने क्रू एस्केप सिस्टम का सफल परीक्षण किया।",
    )
    ranking = StoryRanking(
        story_id="story_isro_01",
        composite_score=88.5,
        factors={},
        recommended_duration=60,
        priority_flag="top_pick",
    )
    clip = SelectedClip(
        clip_id="clip_01",
        story_id="story_isro_01",
        start_time=22.0,
        end_time=26.5,
        duration=4.5,
        quote_text="गगनयान का क्रू एस्केप परीक्षण सफल रहा।",
        speaker_id="SPEAKER_SCIENTIST",
        is_hook_candidate=True,
    )
    claim = EvidenceClaim(
        claim_id="c1",
        story_id="story_isro_01",
        claim_text="इसरो का आधिकारिक परीक्षण सफल घोषित",
        status="verified",
    )

    result = await adapt_agent.execute(
        story=story,
        ranking=ranking,
        selected_clips=[clip],
        evidence_claims=[claim],
        target_duration=60,
    )
    assert result.success is True
    script = result.data["adapted_script"]
    assert isinstance(script, AdaptedShortScript)
    assert script.target_duration == 60
    assert len(script.scenes) >= 3
    # Verify source clip scene exists
    clip_scene = next((s for s in script.scenes if s.scene_type == "source_clip"), None)
    assert clip_scene is not None
    assert clip_scene.source_clip_id == "clip_01"
    # Verify hook text in Hindi
    assert len(script.hook_text_hi) > 0
