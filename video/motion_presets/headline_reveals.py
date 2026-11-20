"""Headline Reveal Motion Presets (Presets 9 to 16) for BHARAT KI SOCH.

Broadcast TV chyrons, dynamic lower-thirds, headline straps, and text animations.
"""

from __future__ import annotations

from typing import List

from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)

HEADLINE_REVEAL_PRESETS: List[MotionPresetSpec] = [
    MotionPresetSpec(
        preset_id="headline_bottom_up",
        name="Bottom-Up Lower Third",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Smooth slide-up from bottom screen margin into reading position with slight overshoot.",
        duration_min=0.4,
        duration_default=0.8,
        duration_max=2.0,
        ffmpeg_filter_template="overlay=x=0:y='if(lte(t,0.4),H-(H-1230)*(t/0.4),1230)':eval=frame",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_y=180.0, opacity=0.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(
                time_offset=0.35, pos_y=-10.0, opacity=1.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(time_offset=0.5, pos_y=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"resting_y": 1230, "overshoot_px": 10, "slide_time": 0.35},
        tags=["headline", "lower_third", "slide_up", "chyron"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_left_right_strap",
        name="Left-to-Right Strap Wipe",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Broadcast colored anchor bar extends from screen left followed by Devanagari headline text unmask.",
        duration_min=0.5,
        duration_default=0.9,
        duration_max=2.0,
        ffmpeg_filter_template="overlay=x='if(lte(t,0.3),-W+W*(t/0.3),0)':y=1230:eval=frame",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_x=-1080.0, opacity=0.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(time_offset=0.3, pos_x=0.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"accent_bar_width": 16, "bar_color": "0xFF9933"},
        tags=["strap", "left_to_right", "bar", "newsroom"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_kinetic_word_pop",
        name="Kinetic Word Pop",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Devanagari headline words pop in succession matching spoken voiceover cadence.",
        duration_min=0.6,
        duration_default=1.4,
        duration_max=3.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=0.8, scale_y=0.8, opacity=0.0, easing=EasingType.SPRING
            ),
            KeyframeAnimation(
                time_offset=0.15, scale_x=1.1, scale_y=1.1, opacity=1.0, easing=EasingType.SPRING
            ),
            KeyframeAnimation(
                time_offset=0.25, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.LINEAR
            ),
        ],
        parameters={"word_stagger": 0.12, "pop_scale": 1.15},
        tags=["kinetic", "typography", "words", "speech_sync"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_masked_wipe",
        name="Masked Geometric Wipe",
        category=PresetCategory.HEADLINE_REVEAL,
        description="45-degree angled chevron wipe reveals headline plate from right to left.",
        duration_min=0.4,
        duration_default=0.7,
        duration_max=1.8,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_x=400.0, opacity=0.0, easing=EasingType.EASE_IN_OUT
            ),
            KeyframeAnimation(
                time_offset=0.4, pos_x=0.0, opacity=1.0, easing=EasingType.EASE_IN_OUT
            ),
        ],
        parameters={"angle_deg": 45, "chevron_width": 80},
        tags=["masked", "wipe", "geometric", "chyron"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_double_chyron",
        name="Double-Tier Broadcast Chyron",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Two-layer lower third: top strap contains topic/location, bottom wider strap holds main headline.",
        duration_min=0.6,
        duration_default=1.0,
        duration_max=2.2,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, pos_y=120.0, opacity=0.0, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(time_offset=0.3, pos_y=0.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"tier1_height": 50, "tier2_height": 130, "resting_y": 1200},
        tags=["chyron", "double_tier", "broadcast", "tv_style"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_typewriter",
        name="Devanagari Typewriter Unfold",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Characters appear sequentially with blinking amber cursor for investigative or urgent alert stories.",
        duration_min=0.8,
        duration_default=1.6,
        duration_max=3.5,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"char_interval": 0.04, "cursor_color": "0xFFCC00", "cursor_blink_rate": 0.3},
        tags=["typewriter", "terminal", "investigative", "alert"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_category_badge",
        name="Category Badge Flip-In",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Category pill badge (राष्ट्रीय, अंतरराष्ट्रीय, अर्थव्यवस्था) scales up with 3D flip-in.",
        duration_min=0.3,
        duration_default=0.6,
        duration_max=1.5,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0,
                scale_x=0.0,
                scale_y=0.0,
                rotation=-45.0,
                opacity=0.0,
                easing=EasingType.SPRING,
            ),
            KeyframeAnimation(
                time_offset=0.25,
                scale_x=1.1,
                scale_y=1.1,
                rotation=5.0,
                opacity=1.0,
                easing=EasingType.SPRING,
            ),
            KeyframeAnimation(
                time_offset=0.35,
                scale_x=1.0,
                scale_y=1.0,
                rotation=0.0,
                opacity=1.0,
                easing=EasingType.LINEAR,
            ),
        ],
        parameters={"badge_height": 48, "corner_radius": 24, "resting_pos": [72, 280]},
        tags=["category", "badge", "pill", "tag"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="headline_story_counter",
        name="Story Index Counter Tick",
        category=PresetCategory.HEADLINE_REVEAL,
        description="Numbered story counter (01/20, 02/20) with digital flip and glowing background border pulse.",
        duration_min=0.3,
        duration_default=0.5,
        duration_max=1.2,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(
                time_offset=0.0, scale_x=1.3, scale_y=1.3, opacity=0.5, easing=EasingType.EASE_OUT
            ),
            KeyframeAnimation(
                time_offset=0.2, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.LINEAR
            ),
        ],
        parameters={"counter_format": "{current:02d} / {total:02d}", "resting_pos": [920, 280]},
        tags=["counter", "index", "story_number", "bulletin"],
        render_type="pil_overlay",
    ),
]
