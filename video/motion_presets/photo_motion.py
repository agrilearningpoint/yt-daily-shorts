"""Photo Motion Presets (Presets 17 to 24) for BHARAT KI SOCH.

Broadcast Ken Burns curves, parallax depth camera motion, and photographic animations.
"""

from __future__ import annotations

from typing import List

from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)

PHOTO_MOTION_PRESETS: List[MotionPresetSpec] = [
    MotionPresetSpec(
        preset_id="photo_slow_push_in",
        name="Slow Dramatic Push-In",
        category=PresetCategory.PHOTO_MOTION,
        description="Steady, high-precision center push zoom (1.00 -> 1.14) emphasizing subject intensity.",
        duration_min=1.5,
        duration_default=3.5,
        duration_max=8.0,
        ffmpeg_filter_template="zoompan=z='min(1.0+0.0012*on,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=1.0, scale_y=1.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(
                time_offset=3.5, scale_x=1.14, scale_y=1.14, easing=EasingType.LINEAR
            ),
        ],
        parameters={"start_scale": 1.0, "end_scale": 1.14, "anchor": "center"},
        tags=["ken_burns", "push_in", "dramatic", "photo"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="photo_smooth_pull_out",
        name="Smooth Context Pull-Out",
        category=PresetCategory.PHOTO_MOTION,
        description="Starts on tight detail and gently zooms out (1.15 -> 1.00) revealing wider environmental context.",
        duration_min=1.5,
        duration_default=3.5,
        duration_max=8.0,
        ffmpeg_filter_template="zoompan=z='max(1.15-0.0012*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=1.15, scale_y=1.15, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(time_offset=3.5, scale_x=1.0, scale_y=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"start_scale": 1.15, "end_scale": 1.0, "anchor": "center"},
        tags=["ken_burns", "pull_out", "context", "reveal"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="photo_diagonal_pan",
        name="Diagonal Narrative Pan",
        category=PresetCategory.PHOTO_MOTION,
        description="Simultaneous slow zoom and diagonal pan across document, terrain, or crowded scene.",
        duration_min=2.0,
        duration_default=4.0,
        duration_max=9.0,
        ffmpeg_filter_template="zoompan=z='1.12':x='(iw-iw/zoom)*(on/{frames})':y='(ih-ih/zoom)*(1-on/{frames})':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0,
                scale_x=1.12,
                scale_y=1.12,
                pos_x=-50.0,
                pos_y=50.0,
                easing=EasingType.EASE_IN_OUT,
            ),
            KeyframeAnimation(
                time_offset=4.0,
                scale_x=1.12,
                scale_y=1.12,
                pos_x=50.0,
                pos_y=-50.0,
                easing=EasingType.LINEAR,
            ),
        ],
        parameters={"fixed_scale": 1.12, "pan_direction": "bottom_left_to_top_right"},
        tags=["diagonal", "pan", "document", "crowd"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="photo_horizontal_parallax",
        name="Horizontal Parallax Glide",
        category=PresetCategory.PHOTO_MOTION,
        description="Left-to-right steady tracking shot simulating camera movement on a motorized slider.",
        duration_min=1.8,
        duration_default=3.5,
        duration_max=7.5,
        ffmpeg_filter_template="zoompan=z='1.10':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_x=-80.0, scale_x=1.1, scale_y=1.1, easing=EasingType.LINEAR
            ),
            KeyframeAnimation(
                time_offset=3.5, pos_x=80.0, scale_x=1.1, scale_y=1.1, easing=EasingType.LINEAR
            ),
        ],
        parameters={"fixed_scale": 1.10, "glide_axis": "X"},
        tags=["parallax", "slider", "glide", "horizontal"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="photo_vertical_parallax",
        name="Vertical Skyscraper Parallax",
        category=PresetCategory.PHOTO_MOTION,
        description="Vertical tilt pedestal upward from foundation to peak of building, monument or tall figure.",
        duration_min=1.8,
        duration_default=3.5,
        duration_max=7.5,
        ffmpeg_filter_template="zoompan=z='1.12':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{frames})':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_y=120.0, scale_x=1.12, scale_y=1.12, easing=EasingType.LINEAR
            ),
            KeyframeAnimation(
                time_offset=3.5, pos_y=-120.0, scale_x=1.12, scale_y=1.12, easing=EasingType.LINEAR
            ),
        ],
        parameters={"fixed_scale": 1.12, "glide_axis": "Y"},
        tags=["vertical", "pedestal", "monument", "tilt"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="photo_focus_crop",
        name="Rule of Thirds Face Crop",
        category=PresetCategory.PHOTO_MOTION,
        description="Dynamic re-centering towards upper 1/3 eye line of speaker or subject with subtle drift.",
        duration_min=1.5,
        duration_default=3.0,
        duration_max=6.5,
        ffmpeg_filter_template="zoompan=z='min(1.05+0.0008*on,1.15)':x='iw/2-(iw/zoom/2)':y='ih*0.25-(ih/zoom*0.25)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_y=-40.0, scale_x=1.05, scale_y=1.05, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(
                time_offset=3.0, pos_y=-60.0, scale_x=1.15, scale_y=1.15, easing=EasingType.LINEAR
            ),
        ],
        parameters={"face_y_target": 0.28, "drift_scale": 1.15},
        tags=["face", "portrait", "portrait_crop", "interview"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="photo_depth_zoom",
        name="3D Depth Map Simulated Zoom",
        category=PresetCategory.PHOTO_MOTION,
        description="Depth-layer motion where foreground subject pushes forward faster than background.",
        duration_min=2.0,
        duration_default=3.5,
        duration_max=6.0,
        ffmpeg_filter_template="zoompan=z='min(1.02+0.0014*on,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=1.0, scale_y=1.0, easing=EasingType.EASE_IN_OUT
            ),
            KeyframeAnimation(
                time_offset=3.5, scale_x=1.18, scale_y=1.18, easing=EasingType.EASE_IN_OUT
            ),
        ],
        parameters={"depth_layers": 3, "foreground_boost": 1.3},
        tags=["depth", "3d", "parallax", "cinematic"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="photo_detail_to_wide",
        name="Detail to Wide Context Snap",
        category=PresetCategory.PHOTO_MOTION,
        description="Focuses for 1.2s on critical detail (signature, weapon, currency) then snaps wide to reveal whole setting.",
        duration_min=2.0,
        duration_default=3.5,
        duration_max=7.0,
        ffmpeg_filter_template="zoompan=z='if(lte(on,36),1.28,max(1.28-(on-36)*0.008,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=1.28, scale_y=1.28, easing=EasingType.LINEAR
            ),
            KeyframeAnimation(
                time_offset=1.2, scale_x=1.28, scale_y=1.28, easing=EasingType.EASE_IN_OUT
            ),
            KeyframeAnimation(
                time_offset=3.0, scale_x=1.0, scale_y=1.0, easing=EasingType.EASE_OUT
            ),
        ],
        parameters={"hold_time": 1.2, "initial_zoom": 1.28, "snap_speed": 0.8},
        tags=["detail", "macro", "snap_wide", "investigative"],
        render_type="ffmpeg",
    ),
]
