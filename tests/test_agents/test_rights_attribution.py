"""Unit tests for RightsAttributionAgent."""

import pytest

from agents.rights_attribution.agent import RightsAttributionAgent
from core.agent_contracts import (
    MediaRightsRecord,
    SelectedClip,
    SourceVideoManifest,
)
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def rights_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return RightsAttributionAgent(cfg, sm)


@pytest.mark.asyncio
async def test_rights_public_domain_low_risk(rights_agent):
    manifest = SourceVideoManifest(
        video_id="lv_sansad",
        source_uri="https://sansadtv.nic.in/bulletin",
        is_local_file=False,
        local_path="",
        sha256="abc123",
        duration=300.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        audio_channels=2,
        audio_sample_rate=44100,
        has_audio=True,
        author="Sansad TV Official",
        license="public_domain",
    )
    clip = SelectedClip(
        clip_id="c1",
        story_id="s1",
        start_time=10.0,
        end_time=15.0,
        duration=5.0,
        quote_text="संसद की कार्यवाही",
        speaker_id="SPEAKER_01",
    )

    result = await rights_agent.execute(manifest=manifest, selected_clips=[clip])
    assert result.success is True
    rec = result.data["rights_record"]
    assert isinstance(rec, MediaRightsRecord)
    assert rec.risk_level == "low"
    assert rec.fair_use_score >= 0.90
    assert "Sansad TV" in rec.mandatory_on_screen_credit
    assert (
        "Section 107" in rec.description_attribution_text
        or "Section 52" in rec.description_attribution_text
    )


@pytest.mark.asyncio
async def test_rights_commercial_excessive_duration_flags_high_risk(rights_agent):
    manifest = SourceVideoManifest(
        video_id="lv_commercial",
        source_uri="https://commercialnews.com/video123",
        is_local_file=False,
        local_path="",
        sha256="xyz789",
        duration=300.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        audio_channels=2,
        audio_sample_rate=44100,
        has_audio=True,
        author="Commercial News Network",
    )
    # Clip exceeding 8.0s threshold
    clip = SelectedClip(
        clip_id="c1",
        story_id="s1",
        start_time=10.0,
        end_time=21.0,
        duration=11.0,
        quote_text="लंबा भाषण",
        speaker_id="SPEAKER_01",
    )

    result = await rights_agent.execute(manifest=manifest, selected_clips=[clip])
    assert result.success is True
    rec = result.data["rights_record"]
    assert rec.risk_level == "high"
    assert rec.replacement_recommended is True
    assert len(rec.warnings) > 0
