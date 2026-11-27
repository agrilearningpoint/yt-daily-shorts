"""Master Editing Director Agent for BHARAT KI SOCH.

Unifies Creative Direction, Daily Opening, Visual Sourcing, Motion Graphics, VFX,
Audio Sound Design, and Synchronization into ONE authoritative MasterEditingTimeline.
Eliminates duplicate creative decisions and guarantees that all agent outputs reach
the final rendering pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import (
    AudioMixPlan,
    DailyOpeningBrief,
    MasterEditingTimeline,
    NewsVisualAsset,
    TimelineSegmentContract,
)
from core.configuration import AppConfig
from core.state_manager import StateManager
from video.editor_director import GRADES
from video.motion_presets import MotionPresetCatalog
from video.renderer import SceneClip
from video.synchronization_engine import SynchronizationEngine

logger = logging.getLogger("agents.master_editing_director")


class MasterEditingDirectorAgent(BaseAgent):
    """Authoritative editing director synthesizing all creative and technical decisions into a single timeline."""

    name: str = "MasterEditingDirectorAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        self.fps = getattr(config.video, "fps", 30)
        self.sync_engine = SynchronizationEngine(fps=self.fps)
        self.preset_catalog = MotionPresetCatalog.get_instance()

    def validate_input(self, **kwargs: Any) -> bool:
        """Ensure script, scenes, or timeline are provided."""
        return bool(kwargs.get("script") or kwargs.get("scenes") or kwargs.get("timeline"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Assemble and validate the master editing timeline."""
        video_id = kwargs.get("video_id", "master_edit_001")
        script = kwargs.get("script", {}) or {}
        scenes = script.get("scenes", [])
        hook_text = script.get("hook", "")
        video_type = script.get("video_type", "news")

        opening_brief: Optional[DailyOpeningBrief] = kwargs.get("opening_brief")
        visual_assets: List[NewsVisualAsset] = kwargs.get("visual_assets", [])
        vfx_data: Dict[str, Any] = kwargs.get("vfx_data", {}) or {}
        motion_data: Dict[str, Any] = kwargs.get("motion_data", {}) or {}
        audio_mix_plan: Optional[AudioMixPlan] = kwargs.get("audio_mix_plan")
        measured_durations: List[float] = kwargs.get("measured_durations", [])
        narration_path: str = kwargs.get("narration_audio_path", "")

        out_dir = Path("output") / video_id
        out_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("Directing master edit for video '%s' (type: %s)", video_id, video_type)

        # 1. Resolve VFX plan and color grade
        color_grade_name = vfx_data.get("color_grade", "broadcast_crisp")
        color_filter = GRADES.get(color_grade_name, GRADES.get("broadcast_crisp", ""))
        vfx_items = {
            item["scene_id"]: item
            for item in vfx_data.get("vfx_plan", [])
            if isinstance(item, dict) and "scene_id" in item
        }

        # 2. Resolve Motion Graphics overlays
        motion_items = {
            item["scene_id"]: item
            for item in motion_data.get("motion_plan", [])
            if isinstance(item, dict) and "scene_id" in item
        }

        # 3. Build structural scene beats
        beats: List[Dict[str, Any]] = []
        if hook_text:
            beats.append(
                {
                    "scene_id": "scene_000_hook",
                    "kind": "hook",
                    "text": hook_text,
                    "headline": hook_text[:75],
                    "category": "बड़ी खबर",
                    "is_hook": True,
                }
            )

        for idx, sc in enumerate(scenes, 1):
            scene_id = f"scene_{idx:03d}"
            narr = sc.get("narration") or sc.get("text") or ""
            headline = sc.get("on_screen_text") or sc.get("headline") or narr[:65]
            beats.append(
                {
                    "scene_id": scene_id,
                    "kind": "scene",
                    "text": narr,
                    "headline": headline,
                    "category": sc.get("category", "राष्ट्रीय"),
                    "is_hook": False,
                }
            )

        total_beats = len(beats)
        if not measured_durations:
            # Fallback estimation based on word count (approx 2.4 words per second in Hindi)
            measured_durations = [max(1.8, len(b["text"].split()) / 2.4) for b in beats]
        elif len(measured_durations) < total_beats:
            # Pad missing durations
            last_avg = sum(measured_durations) / max(len(measured_durations), 1)
            while len(measured_durations) < total_beats:
                measured_durations.append(last_avg)
        elif len(measured_durations) > total_beats:
            measured_durations = measured_durations[:total_beats]

        # 4. Quantize beat durations to exact frames to eliminate drift
        framerate = self.fps
        quantized_durs: List[float] = []
        cum_target = 0.0
        cur_frame = 0
        tail = 0.4  # clean audio decay tail
        raw_durs = list(measured_durations)
        if raw_durs:
            raw_durs[-1] = max(0.2, raw_durs[-1] + tail)

        for d in raw_durs:
            cum_target += max(d, 2.0 / framerate)
            end_frame = max(cur_frame + 2, int(round(cum_target * framerate)))
            quantized_durs.append((end_frame - cur_frame) / framerate)
            cur_frame = end_frame

        total_duration = sum(quantized_durs)

        # 5. Build Timeline Segments
        timeline_segments: List[TimelineSegmentContract] = []
        current_time = 0.0

        # Safe extraction for opening_brief
        opening_presets = []
        if opening_brief:
            if isinstance(opening_brief, dict):
                opening_presets = opening_brief.get("motion_preset_ids", [])
            else:
                opening_presets = getattr(opening_brief, "motion_preset_ids", []) or []

        # Safe extraction for audio_mix_plan
        master_audio = narration_path
        bg_bed = None
        bed_vol = 0.10
        if audio_mix_plan:
            if isinstance(audio_mix_plan, dict):
                master_audio = audio_mix_plan.get("output_master_audio_path") or narration_path
                bg_bed = audio_mix_plan.get("background_bed_path")
                bed_vol = audio_mix_plan.get("bed_volume", 0.10)
            else:
                master_audio = getattr(audio_mix_plan, "output_master_audio_path", narration_path)
                bg_bed = getattr(audio_mix_plan, "background_bed_path", None)
                bed_vol = getattr(audio_mix_plan, "bed_volume", 0.10)

        for idx, (beat, dur) in enumerate(zip(beats, quantized_durs)):
            scene_id = beat["scene_id"]
            start_t = round(current_time, 3)
            end_t = round(current_time + dur, 3)

            # Resolve visual asset
            asset_path = ""
            asset_source = "placeholder"
            asset_id = f"vis_{scene_id}"
            is_video = False

            va = None
            sc_idx = (idx - 1) if hook_text else idx
            if isinstance(visual_assets, list):
                if idx < len(visual_assets):
                    va = visual_assets[idx]
                elif 0 <= sc_idx < len(visual_assets):
                    va = visual_assets[sc_idx]
            elif isinstance(visual_assets, dict):
                if beat.get("is_hook"):
                    va = (
                        visual_assets.get("scene_000_hook")
                        or visual_assets.get("hook")
                        or visual_assets.get("scene_000")
                        or next(iter(visual_assets.values()), None)
                    )
                else:
                    va = (
                        visual_assets.get(f"scene_{sc_idx:03d}")
                        or visual_assets.get(scene_id)
                        or visual_assets.get(str(sc_idx))
                        or visual_assets.get(str(idx))
                    )

            if va:
                asset_path = getattr(va, "local_path", getattr(va, "path", ""))
                asset_source = getattr(
                    va, "source_provider", getattr(va, "source", "sourcing_agent")
                )
                asset_id = getattr(va, "asset_id", asset_id)
            elif beat.get("is_hook") and opening_brief:
                # Use opening hook visual if available
                asset_source = "daily_opening"

            # Check if video file
            if asset_path and Path(asset_path).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
                is_video = True

            # Resolve VFX settings
            vfx_item = vfx_items.get(scene_id, {})
            transition_fx = vfx_item.get("transition_effect", "flash" if idx % 2 == 0 else "whip")
            camera_motion = vfx_item.get("camera_motion", "push_in")
            vfx_preset = vfx_item.get("motion_preset_id")

            # Resolve Motion Graphics Overlay
            motion_item = motion_items.get(scene_id, {})
            overlay_p = motion_item.get("overlay_path")

            # Resolve Motion Preset ID
            if beat.get("is_hook"):
                preset_id = (
                    (opening_presets[0] if opening_presets else None)
                    or vfx_preset
                    or "opener_breaking_red_flash"
                )
            elif is_video:
                preset_id = "video_speaker_focus_reframe"
            else:
                preset_id = vfx_preset or (
                    "photo_slow_push_in" if idx % 2 == 0 else "photo_diagonal_pan"
                )

            segment = TimelineSegmentContract(
                scene_id=scene_id,
                segment_id=f"seg_{idx:03d}",
                text=beat["text"],
                audio_path=narration_path,
                audio_start=start_t,
                audio_end=end_t,
                measured_duration=round(dur, 3),
                visual_id=asset_id,
                visual_path=asset_path,
                visual_start=start_t,
                visual_end=end_t,
                visual_source=asset_source,
                transition_effect=transition_fx,
                camera_motion=camera_motion,
                overlay_path=overlay_p,
                chip_path=None,
                sfx_cue=vfx_item.get("sfx_type"),
                captions=[],
                motion_preset_id=preset_id,
                is_video_asset=is_video,
                video_trim_start=0.0,
                video_trim_end=dur if is_video else 0.0,
            )
            timeline_segments.append(segment)
            current_time = end_t

        master_timeline = MasterEditingTimeline(
            video_id=video_id,
            total_duration=round(total_duration, 2),
            segments=timeline_segments,
            master_audio_path=master_audio,
            captions_ass_path=str(out_dir / "captions.ass"),
            captions_srt_path=str(out_dir / "captions.srt"),
            music_track_path=bg_bed,
            music_volume=bed_vol,
            color_grade_filter=color_filter,
            audio_mix_plan=audio_mix_plan,
            opening_brief=opening_brief,
            visual_assets=visual_assets,
        )

        result_data = {
            "master_timeline": master_timeline,
            "segment_count": len(timeline_segments),
            "total_duration": master_timeline.total_duration,
            "color_grade": color_grade_name,
            "has_opening_brief": opening_brief is not None,
            "has_audio_mix_plan": audio_mix_plan is not None,
            "visual_assets_bound": len(visual_assets),
        }

        agent_result = AgentResult(
            success=True,
            data=result_data,
            metadata={
                "video_id": video_id,
                "segments": len(timeline_segments),
                "duration": total_duration,
            },
        )
        self.save_result(video_id, agent_result)
        return agent_result

    def build_renderer_clips(
        self, timeline: MasterEditingTimeline, work_dir: Path
    ) -> Tuple[List[SceneClip], List[float]]:
        """Translate authoritative timeline into renderer SceneClips and quantized durations."""
        clips: List[SceneClip] = []
        durs: List[float] = []

        for idx, seg in enumerate(timeline.segments):
            dur = seg.measured_duration
            durs.append(dur)

            # Ensure background image/video exists or generate fallback
            bg_path = seg.visual_path
            if not bg_path or not Path(bg_path).exists():
                bg_path = str(work_dir / f"fallback_bg_{idx:03d}.jpg")
                self._generate_solid_card(bg_path, seg.text[:40])

            # Ensure overlay exists or generate transparent placeholder
            ov_path = seg.overlay_path
            if not ov_path or not Path(ov_path).exists():
                ov_path = str(work_dir / f"empty_ov_{idx:03d}.png")
                self._generate_transparent_png(ov_path)

            clip = SceneClip(
                background=bg_path,
                overlay=ov_path,
                duration=dur,
                chip=None,
                chip_y=1390,
                story_start=(idx == 0 or seg.transition_effect in ("flash", "punch", "whip")),
                fx=seg.transition_effect or "flash",
                ticker=True,
                video=seg.visual_path if seg.is_video_asset else "",
                depth=(not seg.is_video_asset),
                motion_preset_id=seg.motion_preset_id,
                camera_motion=seg.camera_motion,
                transition_effect=seg.transition_effect,
                video_trim_start=seg.video_trim_start,
                video_trim_end=seg.video_trim_end,
                sfx_cue=seg.sfx_cue,
            )
            clips.append(clip)

        return clips, durs

    def _generate_solid_card(self, out_path: str, label: str) -> None:
        """Create fallback background frame if no image was provided."""
        from PIL import Image, ImageDraw

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (1080, 1920), color=(15, 23, 42))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 1080, 8], fill=(225, 29, 72))
        d.text((60, 900), label, fill=(240, 240, 240))
        im.save(str(p), quality=90)

    def _generate_transparent_png(self, out_path: str) -> None:
        """Create empty transparent 1080x1920 PNG."""
        from PIL import Image

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGBA", (1080, 1920), color=(0, 0, 0, 0))
        im.save(str(p))
