"""Shorts Opportunity Ranker Agent.

Evaluates extracted stories across a 9-factor weighted virality matrix:
1. Public Importance (20%)
2. Emotional / High-Impact Quotient (15%)
3. Information Freshness (15%)
4. Factual Clarity & Evidence Strength (15%)
5. Standalone Comprehensibility (10%)
6. Curiosity / Hook Potential (10%)
7. Visual Appeal / Footage Usability (5%)
8. Narrative Closure (5%)
9. Novelty / Uniqueness (5%)

Produces ranked opportunities, priority flags (top_pick, viable, backlog, rejected),
and recommended Shorts duration targets (30s, 45s, 60s).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import (
    EvidenceClaim,
    ExtractedStory,
    StoryRanking,
)
from core.configuration import AppConfig
from core.state_manager import StateManager

FACTOR_WEIGHTS: Dict[str, float] = {
    "public_importance": 0.20,
    "emotional_impact": 0.15,
    "information_freshness": 0.15,
    "evidence_strength": 0.15,
    "standalone_comprehensibility": 0.10,
    "curiosity_potential": 0.10,
    "visual_appeal": 0.05,
    "narrative_closure": 0.05,
    "novelty": 0.05,
}


class ShortsOpportunityRankerAgent(BaseAgent):
    """Ranks extracted stories for viral Shorts conversion using a 9-factor weighted matrix."""

    name: str = "ShortsOpportunityRankerAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify stories or pre-calculated rankings are provided."""
        return bool(kwargs.get("stories") or kwargs.get("rankings"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute scoring and ranking on all extracted stories."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=["No stories or rankings provided to ShortsOpportunityRankerAgent."],
            )

        video_id = kwargs.get("video_id", "lv_ranker_unk")
        stories: List[ExtractedStory] = kwargs.get("stories", [])
        evidence_dossiers: Dict[str, List[EvidenceClaim]] = kwargs.get("evidence_dossiers", {})
        rankings: List[StoryRanking] = []

        # 1. Injected rankings
        if kwargs.get("rankings"):
            for r in kwargs["rankings"]:
                if isinstance(r, StoryRanking):
                    rankings.append(r)
                elif isinstance(r, dict):
                    rankings.append(
                        StoryRanking(
                            story_id=r.get("story_id", "story_001"),
                            composite_score=float(r.get("composite_score", 85.0)),
                            factors=r.get("factors", {}),
                            recommended_duration=int(r.get("recommended_duration", 60)),
                            priority_flag=r.get("priority_flag", "top_pick"),
                            selection_rationale=r.get("selection_rationale", ""),
                            hook_angle=r.get("hook_angle", ""),
                        )
                    )

        # 2. Evaluate each story
        else:
            for story in stories:
                dossier = evidence_dossiers.get(story.story_id, [])
                ranking = self._evaluate_story(story, dossier)
                rankings.append(ranking)

        # Sort descending by composite score
        rankings.sort(key=lambda r: r.composite_score, reverse=True)

        story_map = {s.story_id: s for s in stories}
        top_stories = [story_map[r.story_id] for r in rankings if r.story_id in story_map and r.priority_flag in ("top_pick", "viable")]

        top_picks_count = sum(1 for r in rankings if r.priority_flag == "top_pick")
        viable_count = sum(1 for r in rankings if r.priority_flag == "viable")

        result_data = {
            "rankings": rankings,
            "top_stories": top_stories,
            "top_picks_count": top_picks_count,
            "viable_count": viable_count,
            "highest_score": rankings[0].composite_score if rankings else 0.0,
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={"video_id": video_id, "evaluated_count": len(rankings)},
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _evaluate_story(self, story: ExtractedStory, dossier: List[EvidenceClaim]) -> StoryRanking:
        """Apply the 9-factor scoring model to evaluate an extracted story."""
        factors: Dict[str, float] = {}

        # 1. Public Importance (20%): category weight + entities
        base_importance = 75.0
        if story.category in ("national", "science", "defense"):
            base_importance += 15.0
        elif story.category in ("economy", "politics"):
            base_importance += 10.0
        if len(story.entities) >= 3:
            base_importance += 5.0
        factors["public_importance"] = min(98.0, base_importance)

        # 2. Emotional / High-Impact Quotient (15%)
        impact = 70.0
        impact_keywords = ["फैसला", "ऐतिहासिक", "चेतावनी", "बड़ा", "खुलासा", "क्रांति", "नया रिकॉर्ड", "संकट"]
        matches = sum(1 for k in impact_keywords if k in story.title or k in story.transcript_excerpt)
        impact += min(25.0, matches * 8.0)
        factors["emotional_impact"] = min(96.0, impact)

        # 3. Information Freshness (15%)
        freshness = 85.0
        if "ताज़ा" in story.title or "आज" in story.title or "अभी" in story.transcript_excerpt:
            freshness += 10.0
        factors["information_freshness"] = min(95.0, freshness)

        # 4. Factual Clarity & Evidence Strength (15%)
        evidence_score = 75.0
        if dossier:
            verified_ratio = sum(1 for c in dossier if c.status == "verified") / len(dossier)
            evidence_score = 60.0 + (verified_ratio * 38.0)
        factors["evidence_strength"] = min(98.0, evidence_score)

        # 5. Standalone Comprehensibility (10%)
        factors["standalone_comprehensibility"] = min(95.0, 70.0 + (story.completeness_score * 25.0))

        # 6. Curiosity / Hook Potential (10%)
        curiosity = 75.0
        if any(q in story.title for q in ["क्यों", "कैसे", "क्या", "रहस्य", "सच्चाई"]):
            curiosity += 18.0
        factors["curiosity_potential"] = min(95.0, curiosity)

        # 7. Visual Appeal / Footage Usability (5%)
        visual = 80.0
        if story.category in ("science", "defense", "national"):
            visual += 12.0
        factors["visual_appeal"] = min(95.0, visual)

        # 8. Narrative Closure (5%)
        factors["narrative_closure"] = 85.0

        # 9. Novelty / Uniqueness (5%)
        factors["novelty"] = 82.0

        # Calculate composite score
        composite = sum(factors[k] * FACTOR_WEIGHTS[k] for k in FACTOR_WEIGHTS)
        composite = round(composite, 2)

        # Duration recommendation:
        # If duration in source is < 35s or story is punchy statement -> 30s
        # If story duration is 35-70s -> 45s
        # If rich multi-entity knowledge -> 60s
        source_dur = story.end_time - story.start_time
        if source_dur <= 35.0 or factors["emotional_impact"] > 88.0:
            rec_dur = 30
        elif source_dur <= 75.0 or story.category in ("national", "economy"):
            rec_dur = 45
        else:
            rec_dur = 60

        # Priority flag
        if composite >= 82.0:
            flag = "top_pick"
        elif composite >= 68.0:
            flag = "viable"
        elif composite >= 50.0:
            flag = "backlog"
        else:
            flag = "rejected"

        rationale = (
            f"उच्च स्कोर ({composite:.1f}/100) - जनहित महत्व: {factors['public_importance']:.0f}, "
            f"तथ्य प्रमाण: {factors['evidence_strength']:.0f}, प्रभाव: {factors['emotional_impact']:.0f}।"
        )

        hook_angle = f"क्या आप जानते हैं {story.entities[0] if story.entities else 'भारत'} का यह बड़ा कदम?"

        return StoryRanking(
            story_id=story.story_id,
            composite_score=composite,
            factors=factors,
            recommended_duration=rec_dur,
            priority_flag=flag,
            selection_rationale=rationale,
            hook_angle=hook_angle,
        )
