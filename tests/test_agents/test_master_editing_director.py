"""Unit tests for MasterEditingDirectorAgent."""

import pytest
from pathlib import Path
from agents.master_editing_director.agent import MasterEditingDirectorAgent
from core.agent_contracts import (
    AudioMixPlan,
    DailyOpeningBrief,
    MasterEditingTimeline,
    NewsVisualAsset,
)
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def master_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return MasterEditingDirectorAgent(cfg, sm)


def test_validate_input(master_agent):
    assert not master_agent.validate_input()
    assert master_agent.validate_input(script={"scenes": []})
    assert master_agent.validate_input(scenes=[{"narration": "abc"}])
    assert master_agent.validate_input(timeline="timeline_001")


@pytest.mark.asyncio
async def test_master_editing_director_execute(master_agent, tmp_path):
    script = {
        "hook": "आज की सबसे बड़ी खबर, भारत ने अंतरिक्ष में रचा नया इतिहास!",
        "video_type": "news",
        "scenes": [
            {
                "narration": "इसरो ने अपना नया सैटेलाइट सफलतापूर्वक लॉन्च कर दिया है।",
                "headline": "इसरो का नया कीर्तिमान",
                "category": "विज्ञान",
            },
            {
                "narration": "प्रधानमंत्री ने वैज्ञानिकों को बधाई दी है।",
                "headline": "पीएम ने दी बधाई",
                "category": "राष्ट्रीय",
            },
        ],
    }

    opening_brief = DailyOpeningBrief(
        date_iso="2026-11-20",
        date_hi="20 नवंबर 2026",
        weekday_hi="शुक्रवार",
        panchang="कार्तिक शुक्ल पक्ष एकादशी",
        selected_special_day="विश्व बाल दिवस",
        opening_hook_candidates=["बड़ी खबर"],
        selected_hook="बड़ी खबर",
        visual_beats=["beat1", "beat2", "beat3"],
        motion_preset_ids=["opener_breaking_red_flash", "opener_headline_slam", "opener_date_flip"],
    )

    visual_assets = [
        NewsVisualAsset(
            asset_id="asset_001",
            story_id="story_001",
            asset_type="photo",
            local_path=str(tmp_path / "img1.jpg"),
            source_provider="wikipedia",
            license_name="CC BY-SA 4.0",
        ),
        NewsVisualAsset(
            asset_id="asset_002",
            story_id="story_002",
            asset_type="photo",
            local_path=str(tmp_path / "img2.jpg"),
            source_provider="wikimedia",
            license_name="Public Domain",
        ),
    ]

    vfx_data = {
        "color_grade": "broadcast_crisp",
        "vfx_plan": [
            {"scene_id": "scene_000_hook", "transition_effect": "punch", "motion_preset_id": "opener_breaking_red_flash"},
            {"scene_id": "scene_001", "transition_effect": "flash", "motion_preset_id": "photo_depth_zoom"},
        ],
    }

    motion_data = {
        "motion_plan": [
            {"scene_id": "scene_000_hook", "overlay_path": str(tmp_path / "ov_hook.png")},
            {"scene_id": "scene_001", "overlay_path": str(tmp_path / "ov_1.png")},
        ]
    }

    audio_mix_plan = AudioMixPlan(
        mix_id="mix_001",
        total_duration=15.0,
        narration_audio_path=str(tmp_path / "voice.wav"),
        background_bed_path=str(tmp_path / "bed.wav"),
        output_master_audio_path=str(tmp_path / "master_audio.wav"),
    )

    result = await master_agent.execute(
        video_id="test_edit_001",
        script=script,
        opening_brief=opening_brief,
        visual_assets=visual_assets,
        vfx_data=vfx_data,
        motion_data=motion_data,
        audio_mix_plan=audio_mix_plan,
        measured_durations=[3.0, 4.0, 3.5],
    )

    assert result.success is True
    timeline = result.data["master_timeline"]
    assert isinstance(timeline, MasterEditingTimeline)
    assert len(timeline.segments) == 3  # 1 hook + 2 scenes
    assert timeline.segments[0].scene_id == "scene_000_hook"
    assert timeline.segments[0].motion_preset_id == "opener_breaking_red_flash"
    assert timeline.segments[1].scene_id == "scene_001"
    assert timeline.total_duration > 0.0

    # Test conversion to renderer clips
    clips, durs = master_agent.build_renderer_clips(timeline, tmp_path)
    assert len(clips) == 3
    assert len(durs) == 3
    assert all(d > 0 for d in durs)
