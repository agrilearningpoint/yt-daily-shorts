"""Clip Moment Selector Agent.

Isolates high-impact soundbites and visual moments from a source video for YouTube Shorts.
Ensures boundary alignment on natural speech pauses, determines 9:16 vertical crop focus,
evaluates audio quality, and selects optimal hook and core evidence clips.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import (
    ExtractedStory,
    SelectedClip,
    TranscriptSegment,
    VisualScene,
)
from core.configuration import AppConfig
from core.state_manager import StateManager


class ClipMomentSelectorAgent(BaseAgent):
    """Selects punchy 3-8s soundbites and visual moments from video segments."""

    name: str = "ClipMomentSelectorAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify story or selected_clips are provided."""
        return bool(kwargs.get("story") or kwargs.get("selected_clips") or kwargs.get("segments"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Execute clip moment selection from story transcript and scene metadata."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=["No story, segments, or clips provided to ClipMomentSelectorAgent."],
            )

        video_id = kwargs.get("video_id", "lv_clip_unk")
        story: Optional[ExtractedStory] = kwargs.get("story")
        segments: List[TranscriptSegment] = kwargs.get("segments", [])
        scenes: List[VisualScene] = kwargs.get("scenes", [])
        selected_clips: List[SelectedClip] = []

        # 1. Injected clips (test fixture or manual override)
        if kwargs.get("selected_clips"):
            for idx, c in enumerate(kwargs["selected_clips"]):
                if isinstance(c, SelectedClip):
                    selected_clips.append(c)
                elif isinstance(c, dict):
                    selected_clips.append(
                        SelectedClip(
                            clip_id=c.get("clip_id", f"clip_{idx+1:03d}"),
                            story_id=c.get("story_id", story.story_id if story else "story_001"),
                            start_time=float(c.get("start_time", 0.0)),
                            end_time=float(c.get("end_time", 5.0)),
                            duration=float(c.get("duration", 5.0)),
                            quote_text=c.get("quote_text", ""),
                            speaker_id=c.get("speaker_id", "SPEAKER_01"),
                            audio_quality=c.get("audio_quality", "clean"),
                            visual_quality=c.get("visual_quality", "high"),
                            crop_focus=c.get("crop_focus", "center"),
                            is_hook_candidate=bool(c.get("is_hook_candidate", False)),
                            purpose=c.get("purpose", "soundbite"),
                        )
                    )

        # 2. Select from segments within story time bounds
        elif story:
            selected_clips = self._select_moments_for_story(story, segments, scenes)

        hook_clip = next((c for c in selected_clips if c.is_hook_candidate), None)
        if not hook_clip and selected_clips:
            hook_clip = selected_clips[0]
            hook_clip.is_hook_candidate = True

        result_data = {
            "selected_clips": selected_clips,
            "hook_clip": hook_clip,
            "clip_count": len(selected_clips),
            "story_id": story.story_id if story else "",
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={"video_id": video_id, "clip_count": len(selected_clips)},
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _select_moments_for_story(
        self,
        story: ExtractedStory,
        segments: List[TranscriptSegment],
        scenes: List[VisualScene],
    ) -> List[SelectedClip]:
        """Isolate meaningful 3-8s soundbite moments snapped to natural speech pauses."""
        story_segs = [
            s for s in segments
            if (s.start >= story.start_time - 1.0 and s.end <= story.end_time + 1.0)
        ]
        if not story_segs:
            story_segs = segments[:3] if segments else []

        clips: List[SelectedClip] = []

        # Find soundbite candidates with strong sentiment, quote, or revelation
        for idx, seg in enumerate(story_segs):
            dur = seg.end - seg.start
            # Target 2.5 to 8.5 seconds
            if 2.5 <= dur <= 8.5:
                crop_focus = "center"
                matching_scene = next((sc for sc in scenes if sc.start <= seg.start <= sc.end), None)
                if matching_scene:
                    crop_focus = matching_scene.speaker_position

                is_hook = idx == 0 or any(k in seg.text for k in ["बड़ा फैसला", "खुलासा", "ऐतिहासिक", "महत्वपूर्ण", "स्पष्ट कहा"])
                purpose = "hook" if is_hook else "soundbite"

                # Check audio quality based on confidence and speaker tags
                audio_quality = "clean" if seg.confidence >= 0.90 else "background_noise"

                clips.append(
                    SelectedClip(
                        clip_id=f"{story.story_id}_clip_{len(clips)+1:02d}",
                        story_id=story.story_id,
                        start_time=round(seg.start, 2),
                        end_time=round(seg.end, 2),
                        duration=round(dur, 2),
                        quote_text=seg.text,
                        speaker_id=seg.speaker_id,
                        audio_quality=audio_quality,
                        visual_quality="high",
                        crop_focus=crop_focus,
                        is_hook_candidate=is_hook,
                        purpose=purpose,
                    )
                )

            if len(clips) >= 3:
                break

        # Fallback to contiguous concatenation if segments are too short
        if not clips and story_segs:
            combined_text = []
            c_start = story_segs[0].start
            c_end = story_segs[0].end
            spk = story_segs[0].speaker_id
            for s in story_segs:
                combined_text.append(s.text)
                c_end = s.end
                if (c_end - c_start) >= 3.0:
                    break
            c_dur = round(c_end - c_start, 2)
            clips.append(
                SelectedClip(
                    clip_id=f"{story.story_id}_clip_01",
                    story_id=story.story_id,
                    start_time=round(c_start, 2),
                    end_time=round(c_end, 2),
                    duration=c_dur,
                    quote_text=" ".join(combined_text),
                    speaker_id=spk,
                    audio_quality="clean",
                    visual_quality="high",
                    crop_focus="center",
                    is_hook_candidate=True,
                    purpose="hook",
                )
            )

        return clips
