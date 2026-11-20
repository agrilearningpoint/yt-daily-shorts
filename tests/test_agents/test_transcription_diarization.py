"""Unit tests for TranscriptionDiarizationAgent."""

import json
from pathlib import Path
import pytest

from agents.transcription_diarization.agent import TranscriptionDiarizationAgent
from core.agent_contracts import SourceVideoManifest, TranscriptSegment
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def trans_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return TranscriptionDiarizationAgent(cfg, sm)


@pytest.mark.asyncio
async def test_transcription_from_fixture(trans_agent):
    fixture_path = Path("tests/fixtures/repurposing/multi_story_transcript.json")
    assert fixture_path.exists()
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    result = await trans_agent.execute(
        manifest=SourceVideoManifest(**data["manifest"]),
        segments=data["segments"],
    )
    assert result.success is True
    assert result.data["segment_count"] == 6
    assert result.data["speaker_count"] >= 2
    assert "सर्वोच्च न्यायालय" in result.data["full_text"]


@pytest.mark.asyncio
async def test_transcription_from_srt(trans_agent, tmp_path):
    srt_content = (
        "1\n"
        "00:00:01,000 --> 00:00:04,500\n"
        "आज की बड़ी खबर सुप्रीम कोर्ट से है।\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,200\n"
        "इसरो का गगनयान मिशन सफल हुआ।\n"
    )
    srt_file = tmp_path / "test.srt"
    srt_file.write_text(srt_content, encoding="utf-8")

    result = await trans_agent.execute(existing_captions_path=str(srt_file))
    assert result.success is True
    segments = result.data["segments"]
    assert len(segments) == 2
    assert isinstance(segments[0], TranscriptSegment)
    assert segments[0].start == 1.0
    assert segments[0].end == 4.5
    assert len(segments[0].words) > 0


@pytest.mark.asyncio
async def test_transcription_from_raw_text(trans_agent):
    text = "संसद में आज नया बजट पेश हुआ। सभी सांसदों ने इस पर चर्चा की।"
    result = await trans_agent.execute(raw_transcript=text)
    assert result.success is True
    assert result.data["segment_count"] >= 1
    assert len(result.data["speakers"]) >= 1
