"""Integration test for the 9-agent Long Video to Shorts Repurposing Pipeline."""

import pytest

from core.configuration import AppConfig
from core.state_manager import StateManager
from core.agent_contracts import (
    TranscriptSegment,
    VisualScene,
    ExtractedStory,
)
from agents.long_video_intake.agent import LongVideoIntakeAgent
from agents.transcription_diarization.agent import TranscriptionDiarizationAgent
from agents.scene_understanding.agent import SceneUnderstandingAgent
from agents.story_extraction.agent import StoryExtractionAgent
from agents.context_evidence_research.agent import ContextEvidenceResearchAgent
from agents.shorts_opportunity_ranker.agent import ShortsOpportunityRankerAgent
from agents.clip_moment_selector.agent import ClipMomentSelectorAgent
from agents.shorts_adaptation.agent import ShortsAdaptationAgent
from agents.rights_attribution.agent import RightsAttributionAgent


@pytest.mark.asyncio
async def test_full_repurposing_agent_chain(tmp_path):
    cfg = AppConfig()
    cfg.general.dry_run = True
    sm = StateManager(":memory:")

    dummy_video = tmp_path / "long_speech.mp4"
    dummy_video.write_bytes(b"dummy long video header bytes")

    # 1. Intake
    intake_agent = LongVideoIntakeAgent(cfg, sm)
    res_intake = await intake_agent.execute(source_type="local_file", source_path=str(dummy_video))
    assert res_intake.success
    manifest = res_intake.data.get("manifest")
    assert manifest is not None

    # 2. Transcription
    trans_agent = TranscriptionDiarizationAgent(cfg, sm)
    res_trans = await trans_agent.execute(
        manifest=manifest,
        transcript_segments=[
            TranscriptSegment(
                segment_id="seg_001",
                speaker_id="SPEAKER_01",
                start=0.0,
                end=15.0,
                text="भारत ने आज विज्ञान के क्षेत्र में एक नया और ऐतिहासिक मील का पत्थर स्थापित किया है।",
            ),
            TranscriptSegment(
                segment_id="seg_002",
                speaker_id="SPEAKER_01",
                start=15.0,
                end=35.0,
                text="हमारे वैज्ञानिकों ने पूर्णतः स्वदेशी तकनीक से नया क्रायोजेनिक इंजन तैयार किया है।",
            ),
        ],
    )
    assert res_trans.success
    res_trans.data.get("segments", [])

    # 3. Scene Understanding
    scene_agent = SceneUnderstandingAgent(cfg, sm)
    res_scene = await scene_agent.execute(
        manifest=manifest,
        scenes=[
            VisualScene(
                scene_index=0,
                start=0.0,
                end=15.0,
                keyframe_path=str(tmp_path / "kf1.jpg"),
                scene_type="speaker_medium",
                chyron_text="Speaker addressing audience from podium",
            ),
            VisualScene(
                scene_index=1,
                start=15.0,
                end=35.0,
                keyframe_path=str(tmp_path / "kf2.jpg"),
                scene_type="broll_science",
                chyron_text="Laboratory testing rocket engine firing",
            ),
        ],
    )
    assert res_scene.success
    res_scene.data.get("scenes", [])

    # 4. Story Extraction
    story_agent = StoryExtractionAgent(cfg, sm)
    res_story = await story_agent.execute(
        transcription=res_trans.data,
        scene_analysis=res_scene.data,
        extracted_stories=[
            ExtractedStory(
                story_id="story_isro_01",
                title="भारत का स्वदेशी क्रायोजेनिक इंजन सफल",
                category="विज्ञान",
                start_time=0.0,
                end_time=35.0,
                lead_speaker="वैज्ञानिक प्रमुख",
                key_facts=["स्वदेशी तकनीक", "सफल परीक्षण"],
                entities=["ISRO", "भारत"],
            )
        ],
    )
    assert res_story.success
    stories = res_story.data.get("stories", [])
    assert len(stories) == 1

    # 5. Context Evidence Research
    context_agent = ContextEvidenceResearchAgent(cfg, sm)
    res_context = await context_agent.execute(stories=stories)
    assert res_context.success

    # 6. Opportunity Ranker
    ranker_agent = ShortsOpportunityRankerAgent(cfg, sm)
    res_ranker = await ranker_agent.execute(stories=stories)
    assert res_ranker.success
    top_candidate = res_ranker.data.get("top_candidate") or stories[0]

    # 7. Clip Moment Selector
    moment_agent = ClipMomentSelectorAgent(cfg, sm)
    res_moment = await moment_agent.execute(
        story=top_candidate,
        transcription=res_trans.data,
        scene_analysis=res_scene.data,
        target_duration=55.0,
    )
    assert res_moment.success

    # 8. Shorts Adaptation
    adapt_agent = ShortsAdaptationAgent(cfg, sm)
    res_adapt = await adapt_agent.execute(
        story=top_candidate,
        selected_moments=res_moment.data,
        video_type="repurposed_news",
    )
    assert res_adapt.success
    script = res_adapt.data.get("script")
    assert script is not None
    assert script.get("hook")
    assert len(script.get("scenes", [])) > 0

    # 9. Rights Attribution
    rights_agent = RightsAttributionAgent(cfg, sm)
    res_rights = await rights_agent.execute(
        source_manifest=manifest,
        selected_moments=res_moment.data,
    )
    assert res_rights.success
    rights_record = res_rights.data.get("rights_record")
    assert rights_record is not None
