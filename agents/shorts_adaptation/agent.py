"""Shorts Adaptation Agent.

Adapts an extracted story, source soundbite clips, and verified evidence into
a production-ready 30s/45s/60s Hindi YouTube Shorts script with multi-modal scenes,
word-paced narration, on-screen text chips, and camera motion instructions.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import (
    AdaptedShortScene,
    AdaptedShortScript,
    EvidenceClaim,
    ExtractedStory,
    HookArchetype,
    SelectedClip,
    StoryRanking,
)
from core.configuration import AppConfig
from core.llm_client import LLMClient
from core.state_manager import StateManager


class ShortsAdaptationAgent(BaseAgent):
    """Adapts repurposed story context into a production-grade Hindi Shorts script."""

    name: str = "ShortsAdaptationAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        self.llm = LLMClient(config.llm)

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify story or adapted_script is provided."""
        return bool(kwargs.get("story") or kwargs.get("adapted_script"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute script adaptation for the designated story and duration."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=["No story or adapted script provided to ShortsAdaptationAgent."],
            )

        video_id = kwargs.get("video_id", "lv_adapt_unk")

        # 1. Injected script (fixtures / testing)
        if kwargs.get("adapted_script"):
            script_data = kwargs["adapted_script"]
            if isinstance(script_data, AdaptedShortScript):
                adapted = script_data
            else:
                scenes = [
                    AdaptedShortScene(**s) if isinstance(s, dict) else s
                    for s in script_data.get("scenes", [])
                ]
                adapted = AdaptedShortScript(
                    short_id=script_data.get("short_id", "short_001"),
                    story_id=script_data.get("story_id", "story_001"),
                    title_hi=script_data.get("title_hi", ""),
                    hook_text_hi=script_data.get("hook_text_hi", ""),
                    hook_archetype=script_data.get("hook_archetype", "curiosity_gap"),
                    target_duration=int(script_data.get("target_duration", 60)),
                    estimated_duration=float(script_data.get("estimated_duration", 55.0)),
                    scenes=scenes,
                    outro_hi=script_data.get("outro_hi", ""),
                    source_attributions=script_data.get("source_attributions", []),
                    evidence_citations=script_data.get("evidence_citations", []),
                    category_badge=script_data.get("category_badge", "राष्ट्रीय"),
                )
        # 2. Adapt from story, ranking, clips, and evidence
        else:
            story: ExtractedStory = kwargs["story"]
            ranking: Optional[StoryRanking] = kwargs.get("ranking")
            moments_data = kwargs.get("selected_moments") or {}
            clips: List[SelectedClip] = kwargs.get("selected_clips") or (
                moments_data.get("selected_clips", []) if isinstance(moments_data, dict) else []
            )
            evidence: List[EvidenceClaim] = kwargs.get("evidence_claims", [])
            target_dur = int(
                kwargs.get("target_duration") or (ranking.recommended_duration if ranking else 56)
            )
            if target_dur > 60:
                target_dur = 56
            adapted = await self._adapt_story_to_script(story, ranking, clips, evidence, target_dur)

        script_dict = adapted.to_script_dict() if hasattr(adapted, "to_script_dict") else {}
        result_data = {
            "adapted_script": adapted,
            "script": script_dict,
            "estimated_duration": adapted.estimated_duration,
            "scene_count": len(adapted.scenes),
            "short_id": adapted.short_id,
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={
                "video_id": video_id,
                "short_id": adapted.short_id,
                "duration": adapted.estimated_duration,
            },
        )
        self.save_result(video_id, agent_res)
        return agent_res

    async def _adapt_story_to_script(
        self,
        story: ExtractedStory,
        ranking: Optional[StoryRanking],
        clips: List[SelectedClip],
        evidence: List[EvidenceClaim],
        target_dur: int,
    ) -> AdaptedShortScript:
        """Compose a structured Devanagari Hindi Shorts script using LLM or deterministic template."""
        short_id = f"{story.story_id}_short_{target_dur}s"
        primary_clip = clips[0] if clips else None
        evidence_text = " | ".join(c.claim_text for c in evidence[:3]) if evidence else story.title

        prompt = (
            "You are the Lead Creative Scriptwriter for BHARAT KI SOCH YouTube channel.\n"
            f"Write a {target_dur}-second Hindi YouTube Shorts script for this story:\n"
            f"Title: {story.title}\n"
            f"Category: {story.category}\n"
            f"Key Evidence: {evidence_text}\n"
            f"Source Soundbite Quote: {primary_clip.quote_text if primary_clip else 'None'}\n\n"
            "Script Structure:\n"
            "1. Hook (0-3s): High intrigue first second hook\n"
            "2. Scene 1: Source soundbite from the original video\n"
            "3. Scene 2: Voiceover explanation of core revelation\n"
            "4. Scene 3: Evidence facts and official perspective\n"
            "5. Scene 4: Big picture impact\n"
            "6. Outro (3s): Subscribe prompt\n\n"
            "Return JSON object with keys:\n"
            "- title_hi: Viral Hindi Title\n"
            "- hook_text_hi: 1-3 second opening hook text\n"
            "- hook_archetype: One of [curiosity_gap, unexpected_fact, strong_statement, direct_impact, breaking_news]\n"
            "- scenes: List of objects with [scene_index, scene_type (source_clip or photo_context), duration (float), narration_hi, visual_query, on_screen_text, headline_chip, camera_motion]\n"
            "- outro_hi: Outro call to action in Hindi\n"
            "- category_badge: Hindi badge word (e.g. राष्ट्रीय, विज्ञान, आर्थिक)\n"
            "Return ONLY JSON."
        )

        try:
            resp = await self.llm.generate(
                prompt=prompt,
                system_prompt="You are an expert Hindi Shorts creator. Output valid JSON.",
                temperature=0.3,
            )
            parsed = self._parse_json_object(resp.text)
            if parsed and "scenes" in parsed:
                scenes: List[AdaptedShortScene] = []
                for s in parsed["scenes"]:
                    scenes.append(
                        AdaptedShortScene(
                            scene_index=int(s.get("scene_index", len(scenes))),
                            scene_type=s.get("scene_type", "photo_context"),
                            duration=float(s.get("duration", 5.0)),
                            narration_hi=s.get("narration_hi", ""),
                            source_clip_id=primary_clip.clip_id
                            if s.get("scene_type") == "source_clip" and primary_clip
                            else None,
                            clip_start=primary_clip.start_time
                            if s.get("scene_type") == "source_clip" and primary_clip
                            else None,
                            clip_end=primary_clip.end_time
                            if s.get("scene_type") == "source_clip" and primary_clip
                            else None,
                            visual_query=s.get("visual_query", story.title),
                            on_screen_text=s.get("on_screen_text", ""),
                            headline_chip=s.get("headline_chip", ""),
                            camera_motion=s.get("camera_motion", "subtle_drift"),
                            transition=s.get("transition", "clean_cut"),
                        )
                    )
                total_dur = sum(sc.duration for sc in scenes)
                return AdaptedShortScript(
                    short_id=short_id,
                    story_id=story.story_id,
                    title_hi=parsed.get("title_hi", story.title),
                    hook_text_hi=parsed.get(
                        "hook_text_hi", scenes[0].narration_hi if scenes else ""
                    ),
                    hook_archetype=parsed.get("hook_archetype", HookArchetype.CURIOSITY_GAP.value),
                    target_duration=target_dur,
                    estimated_duration=round(total_dur, 2),
                    scenes=scenes,
                    outro_hi=parsed.get(
                        "outro_hi",
                        "देश और दुनिया की हर बड़ी खबर के लिए भारत की सोच को अभी सब्सक्राइब करें।",
                    ),
                    source_attributions=[f"Source: {story.lead_speaker or 'Broadcast'}"],
                    evidence_citations=[c.claim_text for c in evidence[:2]],
                    category_badge=parsed.get("category_badge", "खास खबर"),
                )
        except Exception as exc:
            self.logger.warning(
                "LLM adaptation script generation failed (%s); using deterministic template.", exc
            )

        # Deterministic script generation
        return self._build_template_script(story, primary_clip, evidence, target_dur)

    def _build_template_script(
        self,
        story: ExtractedStory,
        clip: Optional[SelectedClip],
        evidence: List[EvidenceClaim],
        target_dur: int,
    ) -> AdaptedShortScript:
        """Construct a high-quality deterministic Devanagari Hindi script."""
        scenes: List[AdaptedShortScene] = []
        entity_name = story.entities[0] if story.entities else "भारत"

        # Scene 0: Viral Hook (3.0s)
        scenes.append(
            AdaptedShortScene(
                scene_index=0,
                scene_type="photo_context",
                duration=3.0,
                narration_hi=f"क्या आप जानते हैं {entity_name} से जुड़ी यह बड़ी खबर?",
                visual_query=f"{entity_name} news breaking",
                on_screen_text=f"{entity_name} का बड़ा ऐलान",
                headline_chip="बड़ा फैसला",
                camera_motion="push_in",
                transition="whip_pan",
            )
        )

        # Scene 1: Source Soundbite or core revelation (4.5s)
        if clip:
            scenes.append(
                AdaptedShortScene(
                    scene_index=1,
                    scene_type="source_clip",
                    duration=clip.duration,
                    narration_hi=clip.quote_text,
                    source_clip_id=clip.clip_id,
                    clip_start=clip.start_time,
                    clip_end=clip.end_time,
                    visual_query="",
                    on_screen_text="सीधा बयान",
                    headline_chip="स्पेशल रिपोर्ट",
                    camera_motion="static",
                    transition="clean_cut",
                )
            )

        # Scene 2: Context / Revelation (7.0s)
        scenes.append(
            AdaptedShortScene(
                scene_index=len(scenes),
                scene_type="photo_context",
                duration=7.0,
                narration_hi=f"{story.title}। इस पूरे मामले ने अब नया मोड़ ले लिया है।",
                visual_query=f"{entity_name} official announcement",
                on_screen_text="विस्तृत विश्लेषण",
                headline_chip="सच्चाई क्या है?",
                camera_motion="subtle_drift",
                transition="clean_cut",
            )
        )

        # Scene 3: Evidence & Facts (8.0s)
        fact_text = (
            evidence[0].claim_text
            if evidence
            else story.key_facts[0]
            if story.key_facts
            else "आधिकारिक आंकड़े जारी किए गए हैं।"
        )
        scenes.append(
            AdaptedShortScene(
                scene_index=len(scenes),
                scene_type="photo_context",
                duration=8.0,
                narration_hi=f"पुख्ता जानकारी के अनुसार, {fact_text}",
                visual_query=f"{entity_name} official report documents",
                on_screen_text="सरकारी आंकड़े",
                headline_chip="पुख्ता सबूत",
                camera_motion="pan_left",
                transition="punch",
            )
        )

        # Scene 4: Conclusion & Outro (4.0s)
        scenes.append(
            AdaptedShortScene(
                scene_index=len(scenes),
                scene_type="photo_context",
                duration=4.0,
                narration_hi="आपकी इस पर क्या राय है? कमेंट में बताएं और सब्सक्राइब करें।",
                visual_query="India tricolor flag Bharat",
                on_screen_text="आपकी क्या राय है?",
                headline_chip="भारत की सोच",
                camera_motion="pull_out",
                transition="clean_cut",
            )
        )

        total_dur = sum(s.duration for s in scenes)
        return AdaptedShortScript(
            short_id=f"{story.story_id}_short_{target_dur}s",
            story_id=story.story_id,
            title_hi=story.title,
            hook_text_hi=scenes[0].narration_hi,
            hook_archetype=HookArchetype.CURIOSITY_GAP.value,
            target_duration=target_dur,
            estimated_duration=round(total_dur, 2),
            scenes=scenes,
            outro_hi="भारत की सोच को सब्सक्राइब करना न भूलें।",
            source_attributions=[f"Source: {story.lead_speaker or 'News Broadcast'}"],
            evidence_citations=[c.claim_text for c in evidence[:2]],
            category_badge="राष्ट्रीय",
        )

    def _parse_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        """Safely extract JSON object from text."""
        try:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return None
