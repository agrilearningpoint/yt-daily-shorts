"""Unit tests for ContextEvidenceResearchAgent."""

import pytest

from agents.context_evidence_research.agent import ContextEvidenceResearchAgent
from core.agent_contracts import ExtractedStory
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def evidence_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return ContextEvidenceResearchAgent(cfg, sm)


@pytest.mark.asyncio
async def test_evidence_verification_valid_story(evidence_agent):
    story = ExtractedStory(
        story_id="story_isro_01",
        title="इसरो गगनयान क्रू एस्केप सिस्टम सफल",
        category="science",
        start_time=20.0,
        end_time=34.0,
        key_facts=["इसरो ने श्रीहरिकोटा से सफल परीक्षण किया", "सभी पैरामीटर सामान्य रहे"],
        entities=["इसरो", "गगनयान"],
        transcript_excerpt="इसरो ने गगनयान मिशन के लिए क्रू एस्केप का सफल परीक्षण किया।",
        completeness_score=1.0,
    )

    result = await evidence_agent.execute(stories=[story])
    assert result.success is True
    dossiers = result.data["evidence_dossiers"]
    assert "story_isro_01" in dossiers
    claims = dossiers["story_isro_01"]
    assert len(claims) >= 1
    assert claims[0].status == "verified"
    assert len(claims[0].sources) > 0


@pytest.mark.asyncio
async def test_evidence_verification_injected_dossier(evidence_agent):
    injected = {
        "story_custom": [
            {
                "claim_id": "c1",
                "claim_text": "सुप्रीम कोर्ट ने नया फैसला दिया",
                "status": "verified",
                "confidence": 0.98,
                "sources": [
                    {
                        "name": "PIB",
                        "url": "https://pib.gov.in",
                        "reliability_score": 1.0,
                        "is_government": True,
                    }
                ],
            }
        ]
    }
    result = await evidence_agent.execute(evidence_dossiers=injected)
    assert result.success is True
    assert result.data["verified_count"] == 1
    assert result.data["flagged_count"] == 0
