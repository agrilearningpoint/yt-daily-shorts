"""Unit tests for ShortsOpportunityRankerAgent."""

import pytest

from agents.shorts_opportunity_ranker.agent import FACTOR_WEIGHTS, ShortsOpportunityRankerAgent
from core.agent_contracts import ExtractedStory
from core.configuration import load_config
from core.state_manager import StateManager


@pytest.fixture
def ranker_agent(tmp_path):
    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.database.sqlite_path = str(tmp_path / "test.db")
    sm = StateManager(cfg.database.sqlite_path)
    return ShortsOpportunityRankerAgent(cfg, sm)


def test_factor_weights_sum_to_one():
    total_weight = sum(FACTOR_WEIGHTS.values())
    assert abs(total_weight - 1.0) < 0.001


@pytest.mark.asyncio
async def test_ranker_multi_story_ranking(ranker_agent):
    s1 = ExtractedStory(
        story_id="story_national_sc",
        title="सर्वोच्च न्यायालय का ऐतिहासिक फैसला",
        category="national",
        start_time=4.0,
        end_time=18.0,
        key_facts=["पारदर्शी चुनाव प्रक्रिया पर बड़ा निर्णय"],
        entities=["सर्वोच्च न्यायालय", "भारत"],
        transcript_excerpt="नागरिकों को पारदर्शी मतदान का अधिकार है।",
        completeness_score=1.0,
    )
    s2 = ExtractedStory(
        story_id="story_sports_local",
        title="स्थानीय मैच का परिणाम",
        category="sports",
        start_time=200.0,
        end_time=220.0,
        key_facts=["मैच टाई रहा"],
        entities=["टीम"],
        transcript_excerpt="स्थानीय मैच बराबरी पर खत्म हुआ।",
        completeness_score=0.6,
    )

    result = await ranker_agent.execute(stories=[s1, s2])
    assert result.success is True
    rankings = result.data["rankings"]
    assert len(rankings) == 2
    # s1 (national/historical decision) should rank higher than local sports
    assert rankings[0].story_id == "story_national_sc"
    assert rankings[0].composite_score > rankings[1].composite_score
    assert rankings[0].priority_flag in ("top_pick", "viable")
    assert rankings[0].recommended_duration in (30, 45, 60)
