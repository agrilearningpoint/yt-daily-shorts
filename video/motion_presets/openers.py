"""Opener Motion Presets (Presets 1 to 8) for BHARAT KI SOCH.

Broadcast TV news hooks, urgent breaking flashes, and high-impact openers.
"""

from __future__ import annotations

from typing import List

from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)

OPENER_PRESETS: List[MotionPresetSpec] = [
    MotionPresetSpec(
        preset_id="opener_breaking_red_flash",
        name="Breaking Red Flash",
        category=PresetCategory.OPENER,
        description="High-urgency red/crimson strobe flash with instant zoom punch to seize attention in first 0.5s.",
        duration_min=0.8,
        duration_default=1.5,
        duration_max=3.0,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.15:color=0xCC0000,eq=brightness=0.15:saturation=1.4:enable='lt(t,0.35)'",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0,
                scale_x=1.25,
                scale_y=1.25,
                opacity=0.0,
                easing=EasingType.EXPONENTIAL_OUT,
            ),
            KeyframeAnimation(
                time_offset=0.2, scale_x=1.05, scale_y=1.05, opacity=1.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(
                time_offset=1.5, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.LINEAR
            ),
        ],
        parameters={"flash_color": "0xCC0000", "pulse_speed": 1.8, "urgency": "breaking"},
        tags=["breaking", "red", "flash", "hook", "urgent"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_headline_slam",
        name="Headline Slam",
        category=PresetCategory.OPENER,
        description="Text and visual asset slams from oversized perspective into resting frame with simulated camera shake.",
        duration_min=0.6,
        duration_default=1.2,
        duration_max=2.5,
        ffmpeg_filter_template="zoompan=z='if(lte(on,8),1.3-(on*0.0375),1.0)':d=1:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0,
                scale_x=1.4,
                scale_y=1.4,
                opacity=0.2,
                pos_y=-50.0,
                easing=EasingType.EXPONENTIAL_OUT,
            ),
            KeyframeAnimation(
                time_offset=0.3,
                scale_x=1.0,
                scale_y=1.0,
                opacity=1.0,
                pos_y=0.0,
                easing=EasingType.SPRING,
            ),
            KeyframeAnimation(
                time_offset=1.2,
                scale_x=1.0,
                scale_y=1.0,
                opacity=1.0,
                pos_y=0.0,
                easing=EasingType.LINEAR,
            ),
        ],
        parameters={"slam_speed": 0.25, "impact_intensity": 1.2, "shake_frames": 4},
        tags=["slam", "impact", "headline", "dynamic"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_date_flip",
        name="Date & Panchang Flip",
        category=PresetCategory.OPENER,
        description="Calendar date, Tithi and day of week flip down card animation for daily morning news bulletin.",
        duration_min=1.0,
        duration_default=2.0,
        duration_max=3.5,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.25:color=white",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0,
                scale_x=1.0,
                scale_y=0.1,
                opacity=0.0,
                rotation=-90.0,
                easing=EasingType.EASE_OUT,
            ),
            KeyframeAnimation(
                time_offset=0.4,
                scale_x=1.0,
                scale_y=1.0,
                opacity=1.0,
                rotation=0.0,
                easing=EasingType.EASE_OUT,
            ),
            KeyframeAnimation(
                time_offset=2.0,
                scale_x=1.0,
                scale_y=1.0,
                opacity=1.0,
                rotation=0.0,
                easing=EasingType.LINEAR,
            ),
        ],
        parameters={"flip_axis": "X", "flip_duration": 0.35, "shadow_depth": 12},
        tags=["daily", "calendar", "date", "panchang", "bulletin"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_light_sweep",
        name="Broadcast Light Sweep",
        category=PresetCategory.OPENER,
        description="Diagonal specular light beam sweep across dark newsroom glass backdrop with metallic gleam.",
        duration_min=0.8,
        duration_default=1.8,
        duration_max=3.0,
        ffmpeg_filter_template="eq=brightness='0.22*exp(-pow(t-0.5,2)/0.04)':saturation=1.2",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, pos_x=-500.0, opacity=0.0, easing=EasingType.LINEAR),
            KeyframeAnimation(
                time_offset=0.5, pos_x=0.0, opacity=0.8, easing=EasingType.EASE_IN_OUT
            ),
            KeyframeAnimation(time_offset=1.2, pos_x=500.0, opacity=0.0, easing=EasingType.LINEAR),
        ],
        parameters={"sweep_angle": 45, "beam_width": 250, "intensity": 0.75},
        tags=["light_sweep", "shine", "broadcast", "premium"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_radar_pulse",
        name="Radar Geo Pulse",
        category=PresetCategory.OPENER,
        description="Concentric radar rings pulsing outward from a geographic locus on an India or world map.",
        duration_min=1.0,
        duration_default=2.2,
        duration_max=4.0,
        ffmpeg_filter_template="boxblur=2:enable='between(t,0,0.3)',fade=t=in:st=0:d=0.2",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=0.2, scale_y=0.2, opacity=1.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(
                time_offset=1.0, scale_x=2.5, scale_y=2.5, opacity=0.0, easing=EasingType.EASE_OUT
            ),
        ],
        parameters={"pulse_count": 3, "center_norm": [0.5, 0.45], "ring_color": "0xFF9933"},
        tags=["radar", "geo", "map", "national", "defence"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_split_screen",
        name="Dynamic Split Screen Opener",
        category=PresetCategory.OPENER,
        description="Top and bottom vertical split reveals comparison or multiple breaking angles simultaneously.",
        duration_min=1.2,
        duration_default=2.5,
        duration_max=4.5,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.2",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_x=-200.0, opacity=0.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(time_offset=0.4, pos_x=0.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"split_ratio": 0.5, "border_width": 4, "border_color": "0xFFD700"},
        tags=["split_screen", "comparison", "dual_feed", "news"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_zoom_punch",
        name="Kinetic Zoom Punch",
        category=PresetCategory.OPENER,
        description="Rapid in-out zoom pulse synchronized with an impact bass drum beat or news sting.",
        duration_min=0.5,
        duration_default=1.0,
        duration_max=2.0,
        ffmpeg_filter_template="zoompan=z='if(lte(on,6),1.0+(on*0.04),if(lte(on,15),1.24-((on-6)*0.026),1.0))':d=1:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=1.0, scale_y=1.0, easing=EasingType.EXPONENTIAL_OUT
            ),
            KeyframeAnimation(
                time_offset=0.2, scale_x=1.22, scale_y=1.22, easing=EasingType.EXPONENTIAL_OUT
            ),
            KeyframeAnimation(
                time_offset=0.5, scale_x=1.0, scale_y=1.0, easing=EasingType.EASE_OUT
            ),
        ],
        parameters={"punch_scale": 1.22, "return_decay": 0.8},
        tags=["zoom_punch", "kinetic", "punch", "sting_sync"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="opener_cinematic_opener",
        name="Cinematic Knowledge Opener",
        category=PresetCategory.OPENER,
        description="Slow elegant wide push with subtle anamorphic vignette and warm amber lighting for deep knowledge shorts.",
        duration_min=1.5,
        duration_default=2.5,
        duration_max=5.0,
        ffmpeg_filter_template="vignette=PI/4,eq=saturation=1.15:contrast=1.08,fade=t=in:st=0:d=0.4",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0,
                scale_x=1.0,
                scale_y=1.0,
                opacity=0.0,
                easing=EasingType.EASE_IN_OUT,
            ),
            KeyframeAnimation(
                time_offset=0.5,
                scale_x=1.03,
                scale_y=1.03,
                opacity=1.0,
                easing=EasingType.EASE_IN_OUT,
            ),
            KeyframeAnimation(
                time_offset=2.5, scale_x=1.12, scale_y=1.12, opacity=1.0, easing=EasingType.LINEAR
            ),
        ],
        parameters={"warmth": 0.12, "vignette_depth": 0.65, "drift_rate": 0.04},
        tags=["cinematic", "knowledge", "documentary", "elegant"],
        render_type="hybrid",
    ),
]
