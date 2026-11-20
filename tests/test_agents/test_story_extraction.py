"""Unit tests for StoryExtractionAgent."""

import json
from pathlib import Path
import pytest

from agents.story_extraction.agent import StoryExtractionAgent
from core.agent_contracts import ExtractedStory, TranscriptSegment
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def story_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return StoryExtractionAgent(cfg, sm)


@pytest.mark.asyncio
async def test_story_extraction_from_segments(story_agent):
    fixture_path = Path("tests/fixtures/repurposing/multi_story_transcript.json")
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    segments = [
        TranscriptSegment(
            segment_id=s["segment_id"],
            speaker_id=s["speaker_id"],
            start=s["start"],
            end=s["end"],
            text=s["text"],
            confidence=s["confidence"],
        )
        for s in data["segments"]
    ]

    result = await story_agent.execute(segments=segments)
    assert result.success is True
    stories = result.data["stories"]
    assert len(stories) >= 1
    assert isinstance(stories[0], ExtractedStory)
    assert stories[0].story_id.startswith("story_")
    assert stories[0].completeness_score > 0.0


@pytest.mark.asyncio
async def test_story_extraction_injected_stories(story_agent):
    injected = [
        {
            "story_id": "story_sc_01",
            "title": "सर्वोच्च न्यायालय का बड़ा फैसला",
            "category": "national",
            "start_time": 0.0,
            "end_time": 18.0,
            "key_facts": ["नागरिकों को पारदर्शी मतदान का अधिकार"],
            "entities": ["सर्वोच्च न्यायालय"],
            "completeness_score": 1.0,
        }
    ]
    result = await story_agent.execute(stories=injected)
    assert result.success is True
    assert result.data["story_count"] == 1
    assert result.data["stories"][0].story_id == "story_sc_01"
