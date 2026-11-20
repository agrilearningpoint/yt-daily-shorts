"""End-to-end pipeline flow test for Phase 1 Long Video Repurposing Agents.

Validates the complete chain of 9 specialist agents working in sequence:
Intake -> Transcribe/Diarize -> Scene Understand -> Story Extract -> Evidence Research
-> Opportunity Ranker -> Moment Selector -> Shorts Adaptation -> Rights Attribution.
"""

import json
from pathlib import Path
import pytest

from agents.clip_moment_selector.agent import ClipMomentSelectorAgent
from agents.context_evidence_research.agent import ContextEvidenceResearchAgent
from agents.long_video_intake.agent import LongVideoIntakeAgent
from agents.rights_attribution.agent import RightsAttributionAgent
from agents.scene_understanding.agent import SceneUnderstandingAgent
from agents.shorts_adaptation.agent import ShortsAdaptationAgent
from agents.shorts_opportunity_ranker.agent import ShortsOpportunityRankerAgent
from agents.story_extraction.agent import StoryExtractionAgent
from agents.transcription_diarization.agent import TranscriptionDiarizationAgent
from core.agent_contracts import (
    AdaptedShortScript,
    MediaRightsRecord,
    SourceVideoManifest,
)
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.mark.asyncio
async def test_full_repurposing_chain_phase1(tmp_path):
    # 1. Setup shared infrastructure
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "repurposing_test.db")
    sm = StateManager(cfg.database.sqlite_path)

    # 2. Agent 1: LongVideoIntakeAgent
    intake = LongVideoIntakeAgent(cfg, sm)
    intake_res = await intake.execute(
        source_url="https://www.youtube.com/watch?v=sample_sansad_news",
        title="विशेष समाचार बुलेटिन: सर्वोच्च न्यायालय व गगनयान",
        author="Sansad TV Official",
        license="public_domain",
    )
    assert intake_res.success is True
    manifest = intake_res.data["manifest"]
    assert isinstance(manifest, SourceVideoManifest)

    # 3. Agent 2: TranscriptionDiarizationAgent
    fixture_path = Path("tests/fixtures/repurposing/multi_story_transcript.json")
    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))

    transcriber = TranscriptionDiarizationAgent(cfg, sm)
    trans_res = await transcriber.execute(
        manifest=manifest,
        segments=fixture_data["segments"],
    )
    assert trans_res.success is True
    segments = trans_res.data["segments"]
    assert len(segments) == 6
    assert trans_res.data["speaker_count"] >= 2

    # 4. Agent 3: SceneUnderstandingAgent
    scene_agent = SceneUnderstandingAgent(cfg, sm)
    scene_fixture = json.loads(Path("tests/fixtures/repurposing/sample_scenes.json").read_text(encoding="utf-8"))
    scene_res = await scene_agent.execute(manifest=manifest, scenes=scene_fixture, duration=60.0)
    assert scene_res.success is True
    scenes = scene_res.data["scenes"]
    assert len(scenes) == 5

    # 5. Agent 4: StoryExtractionAgent
    extractor = StoryExtractionAgent(cfg, sm)
    story_res = await extractor.execute(manifest=manifest, segments=segments, scenes=scenes)
    assert story_res.success is True
    stories = story_res.data["stories"]
    assert len(stories) >= 1

    # 6. Agent 5: ContextEvidenceResearchAgent
    researcher = ContextEvidenceResearchAgent(cfg, sm)
    evidence_res = await researcher.execute(stories=stories)
    assert evidence_res.success is True
    dossiers = evidence_res.data["evidence_dossiers"]
    assert len(dossiers) >= 1

    # 7. Agent 6: ShortsOpportunityRankerAgent
    ranker = ShortsOpportunityRankerAgent(cfg, sm)
    rank_res = await ranker.execute(stories=stories, evidence_dossiers=dossiers)
    assert rank_res.success is True
    rankings = rank_res.data["rankings"]
    assert len(rankings) >= 1
    top_story = rank_res.data["top_stories"][0] if rank_res.data["top_stories"] else stories[0]
    top_ranking = rankings[0]
    assert top_ranking.composite_score > 0.0

    # 8. Agent 7: ClipMomentSelectorAgent
    clip_selector = ClipMomentSelectorAgent(cfg, sm)
    clip_res = await clip_selector.execute(story=top_story, segments=segments, scenes=scenes)
    assert clip_res.success is True
    selected_clips = clip_res.data["selected_clips"]
    assert len(selected_clips) >= 1

    # 9. Agent 8: ShortsAdaptationAgent
    adapter = ShortsAdaptationAgent(cfg, sm)
    evidence_claims = dossiers.get(top_story.story_id, [])
    adapt_res = await adapter.execute(
        story=top_story,
        ranking=top_ranking,
        selected_clips=selected_clips,
        evidence_claims=evidence_claims,
        target_duration=top_ranking.recommended_duration,
    )
    assert adapt_res.success is True
    adapted_script = adapt_res.data["adapted_script"]
    assert isinstance(adapted_script, AdaptedShortScript)
    assert len(adapted_script.scenes) >= 3

    # 10. Agent 9: RightsAttributionAgent
    rights_agent = RightsAttributionAgent(cfg, sm)
    rights_res = await rights_agent.execute(
        manifest=manifest,
        selected_clips=selected_clips,
        adapted_script=adapted_script,
    )
    assert rights_res.success is True
    rights_record = rights_res.data["rights_record"]
    assert isinstance(rights_record, MediaRightsRecord)
    assert rights_record.risk_level in ("low", "medium")
    assert "Sansad TV" in rights_record.mandatory_on_screen_credit
    assert "Section" in rights_record.description_attribution_text
