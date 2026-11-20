"""Brand and Outro Motion Presets (Presets 49 to 56) for BHARAT KI SOCH.

Broadcast department bumpers, attribution cards, channel identity logos, and loop endings.
"""

from __future__ import annotations

from typing import List

from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)

BRAND_OUTRO_PRESETS: List[MotionPresetSpec] = [
    MotionPresetSpec(
        preset_id="brand_national_bumper",
        name="National News Segment Bumper",
        category=PresetCategory.BRAND_OUTRO,
        description="Saffron and navy graphic card transition announcing the start of national domestic coverage.",
        duration_min=0.8,
        duration_default=1.5,
        duration_max=3.0,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.2",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.8, scale_y=0.8, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.3, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"primary_color": "0xFF9933", "segment_label": "देश की बात"},
        tags=["bumper", "national", "segment", "brand"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="brand_international_bumper",
        name="Global Affairs Segment Bumper",
        category=PresetCategory.BRAND_OUTRO,
        description="Deep cobalt blue globe rotation bumper introducing international and geopolitical developments.",
        duration_min=0.8,
        duration_default=1.5,
        duration_max=3.0,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.2",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.8, scale_y=0.8, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.3, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"primary_color": "0x3B82F6", "segment_label": "दुनिया जहान"},
        tags=["bumper", "international", "globe", "geopolitics"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="brand_economy_bumper",
        name="Business & Markets Bumper",
        category=PresetCategory.BRAND_OUTRO,
        description="Emerald green financial ticker card introducing market indices, budget, and business stories.",
        duration_min=0.8,
        duration_default=1.5,
        duration_max=3.0,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.2",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.8, scale_y=0.8, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.3, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"primary_color": "0x10B981", "segment_label": "कारोबार & बाजार"},
        tags=["bumper", "economy", "markets", "business"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="brand_calendar_reveal",
        name="Editorial Calendar Observance Card",
        category=PresetCategory.BRAND_OUTRO,
        description="Elegant animated card highlighting UN Days, National Observances, or historical milestones.",
        duration_min=1.2,
        duration_default=2.5,
        duration_max=5.0,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.25",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.9, scale_y=0.9, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.4, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"card_style": "parchment_gold", "icon": "calendar"},
        tags=["calendar", "observance", "anniversary", "history"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="brand_ticker_transition",
        name="Breaking News Ticker Slide-In",
        category=PresetCategory.BRAND_OUTRO,
        description="Continuous bottom ticker banner sliding up with glowing 'LIVE / ताज़ा अपडेट' tag.",
        duration_min=0.5,
        duration_default=1.0,
        duration_max=3.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, pos_y=100.0, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.3, pos_y=0.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"ticker_y": 1726, "live_tag_color": "0xE11D48"},
        tags=["ticker", "live", "crawler", "breaking"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="brand_attribution_card",
        name="Legal & Journalistic Attribution Bug",
        category=PresetCategory.BRAND_OUTRO,
        description="Clean semi-transparent source watermark card complying with Press Trust of India / Wikimedia / Fair Use.",
        duration_min=1.0,
        duration_default=2.5,
        duration_max=6.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=0.0, easing=EasingType.LINEAR),
            KeyframeAnimation(time_offset=0.25, opacity=0.85, easing=EasingType.LINEAR),
        ],
        parameters={"attribution_pos": [72, 1660], "alpha": 0.85},
        tags=["attribution", "source", "journalism", "provenance"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="brand_outro_subscribe",
        name="Channel Identity & Follow Callout",
        category=PresetCategory.BRAND_OUTRO,
        description="BHARAT KI SOCH logo with animated like/subscribe bell notification icon and tagline.",
        duration_min=1.5,
        duration_default=2.5,
        duration_max=4.5,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.25:color=black",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.85, scale_y=0.85, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.35, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.SPRING),
        ],
        parameters={"channel_title": "भारत की सोच", "cta_text": "सब्सक्राइब करें और जुड़े रहें"},
        tags=["outro", "subscribe", "brand", "channel_id"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="brand_short_loop_ending",
        name="Seamless Shorts Loop Matcher",
        category=PresetCategory.BRAND_OUTRO,
        description="Color grade and visual alignment in final 0.4s matching the exact starting frame for endless loop playback.",
        duration_min=0.3,
        duration_default=0.8,
        duration_max=1.5,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=1.0, easing=EasingType.LINEAR),
            KeyframeAnimation(time_offset=0.8, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"loop_target": "first_frame", "crossfade_seconds": 0.15},
        tags=["loop", "shorts_loop", "seamless", "retention"],
        render_type="hybrid",
    ),
]
