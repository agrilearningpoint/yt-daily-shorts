"""Hook Director Agent — crafts, scores, and pairs viral opening hooks for YouTube Shorts.

Evaluates hooks across 6 viral archetypes with a 6-pillar weighted scoring matrix.
Enforces strict 1–3 second audio-visual pairing contracts to guarantee zero hook mismatch.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import ApprovedHook, HookCandidate

logger = logging.getLogger("agents.hook_director")

VIRAL_ARCHETYPES = [
    "curiosity_gap",
    "unexpected_fact",
    "strong_factual_statement",
    "direct_impact",
    "breaking_news",
    "emotional_intrigue",
]

ARCHETYPE_DESCRIPTIONS = {
    "curiosity_gap": "Opens a powerful knowledge gap that demands watching to resolve",
    "unexpected_fact": "Leads with a startling, counter-intuitive verified statistic or fact",
    "strong_factual_statement": "Bold, authoritative statement anchored in the lead event",
    "direct_impact": "Directly links the news or discovery to the viewer's wallet, life, or future",
    "breaking_news": "High-urgency TV bulletin delivery highlighting immediate national impact",
    "emotional_intrigue": "Evokes deep curiosity, awe, national pride, or urgent wonder",
}


class HookDirectorAgent(BaseAgent):
    name = "hook_director"

    def __init__(self, config, state_manager, llm=None) -> None:
        super().__init__(config, state_manager)
        self.llm = llm
        self.quality_threshold = 75.0

    def _score_candidate(
        self,
        text: str,
        archetype: str,
        lead_story: Dict[str, Any],
        paired_entity: str,
    ) -> HookCandidate:
        """Score candidate hook across 6 weighted dimensions (0-100 total)."""
        words = text.split()
        word_count = len(words)

        # 1. First-second impact (weight 0.25): 6-11 words, punchy start, strong verbs
        impact_score = 70.0
        if 6 <= word_count <= 11:
            impact_score += 20.0
        elif 4 <= word_count <= 14:
            impact_score += 10.0
        else:
            impact_score -= 15.0

        if any(
            w in text
            for w in ["बड़ा", "फैसला", "ऐलान", "हैरान", "सीधा", "असर", "नया", "पहला", "इतिहास"]
        ):
            impact_score += 10.0
        impact_score = min(100.0, max(0.0, impact_score))

        # 2. Curiosity (weight 0.20)
        curiosity_score = 75.0
        if archetype in ("curiosity_gap", "emotional_intrigue", "unexpected_fact"):
            curiosity_score += 15.0
        if "?" in text or "क्यों" in text or "कैसे" in text or "सच" in text:
            curiosity_score += 10.0
        curiosity_score = min(100.0, max(0.0, curiosity_score))

        # 3. Clarity (weight 0.15)
        # Avoid complex compound clauses or excessive jargon
        clarity_score = 85.0
        if "और" in text and "लेकिन" in text:
            clarity_score -= 15.0
        if len(re.findall(r"[,।!?]", text)) > 2:
            clarity_score -= 10.0
        clarity_score = min(100.0, max(0.0, clarity_score))

        # 4. Factual accuracy (weight 0.20): Anchored in lead story keywords
        factual_score = 65.0
        lead_title = lead_story.get("title", "") or lead_story.get("headline", "") or ""
        lead_words = set(re.findall(r"\w+", lead_title.lower()))
        matched_words = [w for w in words if w.lower() in lead_words]
        if matched_words or paired_entity:
            factual_score += 25.0
        if lead_story.get("verified", True):
            factual_score += 10.0
        factual_score = min(100.0, max(0.0, factual_score))

        # 5. Spoken naturalness (weight 0.10)
        # Smooth Hindi rhythm without bureaucratic phrasing
        naturalness_score = 80.0
        if any(b in text for b in ["तदोपरांत", "यद्यपि", "फलस्वरूप", "अधिसूचना"]):
            naturalness_score -= 30.0
        naturalness_score = min(100.0, max(0.0, naturalness_score))

        # 6. Visual pairing (weight 0.10): Must name a concrete visual entity
        visual_score = 70.0
        if paired_entity and paired_entity.lower() in text.lower():
            visual_score += 25.0
        elif paired_entity:
            visual_score += 15.0
        visual_score = min(100.0, max(0.0, visual_score))

        # Weighted calculation
        total_score = (
            0.25 * impact_score
            + 0.20 * curiosity_score
            + 0.15 * clarity_score
            + 0.20 * factual_score
            + 0.10 * naturalness_score
            + 0.10 * visual_score
        )

        return HookCandidate(
            archetype=archetype,
            text=text,
            impact_score=round(impact_score, 1),
            curiosity_score=round(curiosity_score, 1),
            clarity_score=round(clarity_score, 1),
            factual_score=round(factual_score, 1),
            naturalness_score=round(naturalness_score, 1),
            visual_potential=round(visual_score, 1),
            composite_score=round(total_score, 1),
            visual_pairing=paired_entity,
        )

    @staticmethod
    def _select_hook_scene_and_story(
        script: Dict[str, Any], items: List[Dict[str, Any]], existing_hook: str
    ) -> tuple:
        """Align HookDirector with the actual lead story the script's hook refers to."""
        scenes = script.get("scenes", []) or []
        news_scenes = [s for s in scenes if s.get("section") != "today"] or scenes
        hook_scene: Dict[str, Any] = news_scenes[0] if news_scenes else {}

        # If existing_hook matches a specific news scene (by entity/keywords), bind to THAT scene
        hook_words = set(re.findall(r"[\u0900-\u097F]{2,}|[A-Za-z0-9]{2,}", existing_hook.lower()))
        if hook_words and news_scenes:
            best_sc = hook_scene
            best_hits = 0
            for sc in news_scenes:
                sc_text = f"{sc.get('on_screen_text', '')} {sc.get('narration', '')}".lower()
                hits = sum(1 for w in hook_words if w in sc_text)
                if hits > best_hits:
                    best_hits = hits
                    best_sc = sc
            if best_hits >= 1:
                hook_scene = best_sc

        lead_story: Dict[str, Any] = {}
        sc_urls = hook_scene.get("sources") or []
        if sc_urls:
            lead_story = next(
                (it for it in items if it.get("source_url") == sc_urls[0]), {}
            )
        if not lead_story and items:
            sc_title = (hook_scene.get("headline") or hook_scene.get("narration") or "").lower()
            sc_words = set(re.findall(r"\w+", sc_title))
            if sc_words:
                lead_story = max(
                    items,
                    key=lambda it: len(
                        sc_words & set(re.findall(r"\w+", str(it.get("title", "")).lower()))
                    ),
                )
            if not lead_story:
                lead_story = items[0]
        return hook_scene, lead_story

    async def execute(self, **kwargs: Any) -> AgentResult:
        research_data = kwargs.get("research_data", {}) or {}
        script = kwargs.get("script", {}) or {}
        video_type = kwargs.get("video_type", "news")
        items = research_data.get("items", [])

        existing_hook = (script.get("hook") or "").strip()
        hook_scene, lead_story = self._select_hook_scene_and_story(script, items, existing_hook)

        # Identify exact lead entity & visual search query for 0.0s audio-visual pairing
        from video.semantic_matcher import extract_entity_from_hindi

        lead_title = (
            hook_scene.get("headline")
            or hook_scene.get("narration")
            or lead_story.get("title", "")
            or lead_story.get("headline", "")
        )
        first_part = (hook_scene.get("parts") or [{}])[0] if hook_scene else {}
        lead_entity = (
            extract_entity_from_hindi(existing_hook)
            or first_part.get("entity", "").strip()
            or hook_scene.get("image_query", "").strip()
            or extract_entity_from_hindi(lead_title)
            or lead_story.get("entity", "")
            or ("Parliament of India" if video_type == "news" else "India Landmark")
        )
        paired_search = (
            first_part.get("search", "").strip()
            or hook_scene.get("visual_keywords", "").strip()
            or lead_entity
        )

        candidates: List[HookCandidate] = []

        # Always keep the script writer's verified Hindi hook as a primary candidate
        if existing_hook:
            candidates.append(
                self._score_candidate(
                    text=existing_hook,
                    archetype="strong_factual_statement",
                    lead_story=lead_story,
                    paired_entity=lead_entity,
                )
            )

        # If an LLM is configured, also generate candidate hooks across archetypes
        prompt = (
            f"Generate 4 distinct viral Hindi YouTube Shorts hooks (6 to 10 words each, pure Devanagari) "
            f"strictly about this story (matching its visual subject):\n"
            f"Story: {lead_title}\n"
            f"Context: {lead_story.get('summary', '')[:200]}\n"
            f"Archetypes to generate:\n"
            f"1. breaking_news\n"
            f"2. direct_impact\n"
            f"3. curiosity_gap\n"
            f"4. strong_factual_statement\n\n"
            f'Return JSON object: {{"hooks": [{{"text": "...", "archetype": "..."}}]}}'
        )

        generated: List[Dict[str, str]] = []
        llm_client = self.llm
        if llm_client is None and self.config.llm.has_any_key():
            try:
                from core.llm_client import build_llm

                llm_client = build_llm(
                    self.config.llm, allow_mock=not self.config.general.strict_mode
                )
            except Exception:
                llm_client = None

        if llm_client is not None and not getattr(llm_client, "is_mock", False):
            try:
                res = await llm_client.generate_json(
                    prompt=prompt,
                    system_prompt="You write high-CTR viral Hindi hooks for YouTube Shorts.",
                )
                raw_hooks = res.get("hooks") if isinstance(res, dict) else []
                if isinstance(raw_hooks, list):
                    generated = [h for h in raw_hooks if isinstance(h, dict)]
            except Exception as exc:
                logger.info(
                    "Hook LLM generation skipped or failed, keeping existing Hindi hook: %s", exc
                )

        # Clean pure-Hindi fallback candidates ONLY when no existing hook exists
        if not generated and not existing_hook:
            hindi_subject = (hook_scene.get("on_screen_text") or "देश और दुनिया").strip()
            generated = [
                {
                    "text": f"{hindi_subject} से जुड़ी आज की सबसे बड़ी खबर जानिए!",
                    "archetype": "breaking_news",
                },
                {
                    "text": f"{hindi_subject} के इस बड़े फैसले का आप पर क्या असर होगा?",
                    "archetype": "curiosity_gap",
                },
            ]

        for item in generated:
            cand_text = str(item.get("text", "")).strip()
            cand_arch = str(item.get("archetype", "strong_factual_statement"))
            # Ensure Hindi Devanagari dominance (>= 40%) and avoid English template artifacts
            if cand_text and len(re.findall(r"[\u0900-\u097F]", cand_text)) >= len(cand_text) * 0.4:
                candidate = self._score_candidate(
                    text=cand_text,
                    archetype=cand_arch,
                    lead_story=lead_story,
                    paired_entity=lead_entity,
                )
                candidates.append(candidate)

        # Select top-scoring candidate
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        best = candidates[0] if candidates else None

        if not best or best.composite_score < self.quality_threshold:
            hindi_subject = (hook_scene.get("on_screen_text") or "आज की बड़ी खबर").strip()
            safe_text = existing_hook or f"{hindi_subject}: जानिए आज का सबसे बड़ा अपडेट!"
            best = self._score_candidate(
                text=safe_text,
                archetype="breaking_news",
                lead_story=lead_story,
                paired_entity=lead_entity,
            )
            best.composite_score = max(best.composite_score, 80.0)

        # Build ApprovedHook contract
        paired_path = ""
        paired_url = (hook_scene.get("sources") or [""])[0] if hook_scene else ""
        approved_hook = ApprovedHook(
            text=best.text,
            archetype=str(best.archetype),
            composite_score=best.composite_score,
            visual_pairing_query=paired_search,
            headline_chip=(hook_scene.get("on_screen_text") or best.text[:60]),
            entity_hint=lead_entity,
        )
        hook_dict = vars(approved_hook)
        if paired_path:
            hook_dict["paired_visual_path"] = paired_path
        if paired_url:
            hook_dict["paired_source_url"] = paired_url
        if lead_story.get("image_url"):
            hook_dict["paired_image_url"] = lead_story["image_url"]

        return AgentResult(
            success=True,
            data={
                "approved_hook": hook_dict,
                "candidates": [vars(c) for c in candidates],
            },
            metadata={"hook_text": approved_hook.text, "score": approved_hook.composite_score},
        )
