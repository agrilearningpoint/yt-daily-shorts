"""Story Extraction Agent.

Analyzes full transcript and scene structures, detects topic transitions and narrative
boundaries, and segments a long video into distinct, self-contained Hindi news/knowledge stories.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import ExtractedStory, SourceVideoManifest, TranscriptSegment, VisualScene
from core.configuration import AppConfig
from core.llm_client import LLMClient
from core.state_manager import StateManager


class StoryExtractionAgent(BaseAgent):
    """Extracts independent news stories and topics from full transcript and scene context."""

    name: str = "StoryExtractionAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        self.llm = LLMClient(config.llm)

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify segments or stories are provided."""
        return bool(kwargs.get("segments") or kwargs.get("stories") or kwargs.get("transcript"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Extract stories from segments and metadata."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=["No transcript segments or text provided to StoryExtractionAgent."],
            )

        manifest: Optional[SourceVideoManifest] = kwargs.get("manifest")
        video_id = manifest.video_id if manifest else kwargs.get("video_id", "lv_story_unk")

        stories: List[ExtractedStory] = []

        # 1. Injected stories (e.g. fixtures or manual override)
        if kwargs.get("stories"):
            for idx, st in enumerate(kwargs["stories"]):
                if isinstance(st, ExtractedStory):
                    stories.append(st)
                elif isinstance(st, dict):
                    stories.append(
                        ExtractedStory(
                            story_id=st.get("story_id", f"story_{idx+1:03d}"),
                            title=st.get("title", f"Story {idx+1}"),
                            category=st.get("category", "national"),
                            start_time=float(st.get("start_time", 0.0)),
                            end_time=float(st.get("end_time", 60.0)),
                            key_facts=st.get("key_facts", []),
                            entities=st.get("entities", []),
                            transcript_excerpt=st.get("transcript_excerpt", ""),
                            completeness_score=float(st.get("completeness_score", 1.0)),
                            lead_speaker=st.get("lead_speaker", "Anchor"),
                            recommended_angle=st.get("recommended_angle", ""),
                        )
                    )

        # 2. Extract from segments
        elif kwargs.get("segments"):
            segments: List[TranscriptSegment] = kwargs["segments"]
            stories = await self._extract_stories_from_segments(segments, manifest)

        # 3. Extract from raw transcript string
        elif kwargs.get("transcript"):
            raw_text = str(kwargs["transcript"])
            stories = await self._extract_from_raw_text(raw_text, manifest)

        result_data = {
            "stories": stories,
            "story_count": len(stories),
            "categories": list({s.category for s in stories}),
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={"video_id": video_id, "story_count": len(stories)},
        )
        self.save_result(video_id, agent_res)
        return agent_res

    async def _extract_stories_from_segments(
        self, segments: List[TranscriptSegment], manifest: Optional[SourceVideoManifest]
    ) -> List[ExtractedStory]:
        """Use LLM or rule-based topic boundary detection on transcript segments."""
        if not segments:
            return []

        # Prepare condensed transcript with timestamps
        condensed_lines = []
        for s in segments:
            condensed_lines.append(f"[{s.start:.1f}s - {s.end:.1f}s] ({s.speaker_id}): {s.text}")
        full_transcript_text = "\n".join(condensed_lines)

        prompt = (
            "You are a Senior Executive News Editor analyzing a broadcast video transcript in Hindi.\n"
            "Identify each distinct, independent news story or topic.\n"
            "For each distinct story, output a JSON array of objects with keys:\n"
            "- title: Compelling Hindi headline\n"
            "- category: One of [national, international, politics, science, economy, sports, defense]\n"
            "- start_time: Start time in seconds (float)\n"
            "- end_time: End time in seconds (float)\n"
            "- key_facts: List of 2 to 4 key facts\n"
            "- entities: List of important named entities (people, organizations, places)\n"
            "- transcript_excerpt: Exact quote or summary from this portion\n"
            "- completeness_score: 0.0 to 1.0 indicating if this story can stand alone as a Short\n"
            "- lead_speaker: Primary speaker name or role\n"
            "- recommended_angle: Editorial angle for a 50-60 second Short\n\n"
            "Transcript:\n"
            f"{full_transcript_text[:6000]}\n\n"
            "Return ONLY a JSON array."
        )

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="You are a Hindi News Editorial Director. Output valid JSON only.",
                temperature=0.2,
            )
            parsed = self._parse_json_array(response.text)
            if parsed and isinstance(parsed, list):
                extracted = []
                for idx, item in enumerate(parsed):
                    extracted.append(
                        ExtractedStory(
                            story_id=f"story_{idx+1:03d}",
                            title=item.get("title", f"खबर {idx+1}"),
                            category=item.get("category", "national"),
                            start_time=float(item.get("start_time", segments[0].start)),
                            end_time=float(item.get("end_time", segments[-1].end)),
                            key_facts=item.get("key_facts", []),
                            entities=item.get("entities", []),
                            transcript_excerpt=item.get("transcript_excerpt", ""),
                            completeness_score=float(item.get("completeness_score", 0.9)),
                            lead_speaker=item.get("lead_speaker", "Anchor"),
                            recommended_angle=item.get("recommended_angle", ""),
                        )
                    )
                if extracted:
                    return extracted
        except Exception as exc:
            self.logger.warning("LLM story extraction failed or in mock mode (%s); using rule-based clusterer.", exc)

        # Fallback heuristic: cluster segments by duration and transition cues
        return self._heuristic_segment_clustering(segments, manifest)

    def _heuristic_segment_clustering(
        self, segments: List[TranscriptSegment], manifest: Optional[SourceVideoManifest]
    ) -> List[ExtractedStory]:
        """Heuristic rule-based segmentation clustering adjacent segments."""
        transition_patterns = [
            r"अगली\s+खबर", r"बड़ी\s+खबर", r"अब\s+बात\s+करते\s+हैं", r"संसद\s+में",
            r"दूसरी\s+तरफ", r"वैज्ञानिकों", r"अंतरराष्ट्रीय", r"अर्थव्यवस्था",
        ]

        clusters: List[List[TranscriptSegment]] = []
        current_cluster: List[TranscriptSegment] = []

        for seg in segments:
            is_transition = any(re.search(pat, seg.text) for pat in transition_patterns)
            cluster_dur = (current_cluster[-1].end - current_cluster[0].start) if current_cluster else 0.0

            if current_cluster and (is_transition or cluster_dur >= 45.0):
                clusters.append(current_cluster)
                current_cluster = [seg]
            else:
                current_cluster.append(seg)

        if current_cluster:
            clusters.append(current_cluster)

        stories: List[ExtractedStory] = []
        for idx, cl in enumerate(clusters):
            c_text = " ".join(s.text for s in cl)
            start_t = cl[0].start
            end_t = cl[-1].end
            words = c_text.split()
            title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")

            # Infer category
            cat = "national"
            if any(k in c_text for k in ["इसरो", "नासा", "वैज्ञानिक", "उपग्रह", "तकनीक"]):
                cat = "science"
            elif any(k in c_text for k in ["रुपया", "शेयर", "आरबीआई", "बजट", "जीडीपी"]):
                cat = "economy"
            elif any(k in c_text for k in ["विदेश", "अमेरिका", "रूस", "चीन", "वैश्विक"]):
                cat = "international"
            elif any(k in c_text for k in ["संसद", "विपक्ष", "चुनाव", "लोकसभा", "सरकार"]):
                cat = "politics"

            stories.append(
                ExtractedStory(
                    story_id=f"story_{idx+1:03d}",
                    title=title,
                    category=cat,
                    start_time=round(start_t, 2),
                    end_time=round(end_t, 2),
                    key_facts=[c_text[:120]],
                    entities=[w for w in ["भारत", "सरकार", "संसद", "इसरो"] if w in c_text] or ["भारत"],
                    transcript_excerpt=c_text[:200],
                    completeness_score=0.9,
                    lead_speaker=cl[0].speaker_id,
                    recommended_angle="ताज़ा घटनाक्रम और इसका प्रभाव",
                )
            )

        return stories

    async def _extract_from_raw_text(self, text: str, manifest: Optional[SourceVideoManifest]) -> List[ExtractedStory]:
        """Extract stories from raw unsegmented text string."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        stories = []
        t_per_para = 30.0
        cur_t = 0.0
        for idx, para in enumerate(paragraphs):
            words = para.split()
            title = " ".join(words[:6])
            stories.append(
                ExtractedStory(
                    story_id=f"story_{idx+1:03d}",
                    title=title,
                    category="national",
                    start_time=cur_t,
                    end_time=cur_t + t_per_para,
                    key_facts=[para[:100]],
                    entities=["भारत"],
                    transcript_excerpt=para[:200],
                    completeness_score=0.9,
                    lead_speaker="Anchor",
                )
            )
            cur_t += t_per_para
        return stories

    def _parse_json_array(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Safely extract and parse JSON array from LLM response."""
        try:
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return None
