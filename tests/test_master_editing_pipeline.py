"""Integration test for Master Editing Director timeline and renderer clips generation."""

import pytest
from pathlib import Path
from PIL import Image

from core.configuration import AppConfig
from core.state_manager import StateManager
from core.agent_contracts import (
    DailyOpeningBrief,
    NewsVisualAsset,
    MasterEditingTimeline,
)
from agents.master_editing_director.agent import MasterEditingDirectorAgent
from video.renderer import SceneClip


def _create_test_image(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1080, 1920), color=(30, 40, 50))
    img.save(str(path))
    return str(path)


@pytest.mark.asyncio
async def test_master_editing_director_pipeline(tmp_path):
    cfg = AppConfig()
    sm = StateManager(":memory:")
    agent = MasterEditingDirectorAgent(cfg, sm)

    test_img = _create_test_image(tmp_path / "asset_1.jpg")

    script = {
        "title": "आज का सुपरफास्ट बुलेटिन",
        "hook": "संसद में आज नया ऐतिहासिक विधेयक पेश हुआ!",
        "scenes": [
            {
                "narration": "संसद में आज डिजिटल पर्सनल डेटा प्रोटेक्शन बिल पेश हुआ।",
                "on_screen_text": "डिजिटल बिल पेश",
                "category": "राष्ट्रीय",
            },
            {
                "narration": "इसरो ने अगले चंद्र मिशन की आधिकारिक घोषणा कर दी है।",
                "on_screen_text": "इसरो चंद्र मिशन",
                "category": "विज्ञान",
            },
        ],
    }

    opening_brief = DailyOpeningBrief(
        date_iso="2026-11-20",
        date_hi="20 नवंबर 2026",
        weekday_hi="शुक्रवार",
        festivals=["मार्गशीर्ष एकादशी"],
        selected_hook=script["hook"],
        spoken_script=script["hook"],
        sound_cue_ids=["cue_news_intro_sting"],
    )

    visual_assets = {
        "scene_000": NewsVisualAsset(
            asset_id="vis_000",
            story_id="scene_000",
            asset_type="photo",
            local_path=test_img,
            source_provider="publisher_news",
            creator="PTI",
            license_name="News Editorial",
            actual_event_or_stock="actual_event",
        ),
        "scene_001": NewsVisualAsset(
            asset_id="vis_001",
            story_id="scene_001",
            asset_type="photo",
            local_path=test_img,
            source_provider="isro",
            creator="ISRO",
            license_name="Public Domain",
            actual_event_or_stock="actual_event",
        ),
    }

    result = await agent.execute(
        video_id="med_test_001",
        script=script,
        opening_brief=opening_brief,
        visual_assets=visual_assets,
    )

    assert result.success
    master_timeline: MasterEditingTimeline = result.data["master_timeline"]
    assert master_timeline is not None
    assert len(master_timeline.segments) >= 2

    # Verify build_renderer_clips
    clips, durs = agent.build_renderer_clips(master_timeline, tmp_path)
    assert len(clips) == len(master_timeline.segments)
    assert len(durs) == len(clips)
    for c in clips:
        assert isinstance(c, SceneClip)
        assert Path(c.background).exists()
        assert Path(c.overlay).exists()
        assert c.duration > 0
