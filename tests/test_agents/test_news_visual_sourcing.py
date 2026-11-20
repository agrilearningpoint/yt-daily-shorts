"""Unit tests for NewsVisualSourcingAgent."""

import pytest

from agents.news_visual_sourcing.agent import NewsVisualSourcingAgent
from core.agent_contracts import NewsVisualAsset
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def visual_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    cfg.media.cache_dir = str(tmp_path / "media_cache")
    sm = StateManager(cfg.database.sqlite_path)
    return NewsVisualSourcingAgent(cfg, sm)


@pytest.mark.asyncio
async def test_news_visual_sourcing_scenes(visual_agent):
    scenes = [
        {
            "narration": "आज संसद में बजट सत्र के दौरान महत्वपूर्ण घोषणा हुई।",
            "visual_keywords": "Parliament of India building New Delhi",
            "entity": "Parliament of India",
        },
        {
            "narration": "इसरो ने गगनयान परीक्षण सफलतापूर्वक पूरा किया।",
            "visual_keywords": "ISRO rocket launch Sriharikota",
            "entity": "ISRO",
        },
    ]

    result = await visual_agent.execute(scenes=scenes)
    assert result.success is True
    assets = result.data["visual_assets"]
    assert len(assets) == 2
    assert "scene_000" in assets
    asset_0 = assets["scene_000"]
    assert isinstance(asset_0, NewsVisualAsset)
    assert asset_0.asset_id == "vis_scene_000"
    assert len(asset_0.local_path) > 0
    assert asset_0.actual_event_or_stock in ("actual_event", "institutional_broll", "stock", "illustrative_graphic")
