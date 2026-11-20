"""Data Graphics Motion Presets (Presets 33 to 40) for BHARAT KI SOCH.

Maps, geographic pins, route lines, animated count-ups, charts, and quote callouts.
"""

from __future__ import annotations

from typing import List

from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)

DATA_GRAPHICS_PRESETS: List[MotionPresetSpec] = [
    MotionPresetSpec(
        preset_id="data_map_zoom",
        name="Geographic Region Map Zoom",
        category=PresetCategory.DATA_GRAPHICS,
        description="Pushes in from all-India or subcontinent view down to specific state or border district.",
        duration_min=1.5,
        duration_default=3.0,
        duration_max=6.0,
        ffmpeg_filter_template="zoompan=z='min(1.0+0.0025*on,1.35)':x='iw*0.48-(iw/zoom*0.48)':y='ih*0.35-(ih/zoom*0.35)':d={frames}:s=1080x1920:fps=30",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=1.0, scale_y=1.0, easing=EasingType.EASE_IN_OUT),
            KeyframeAnimation(time_offset=2.5, scale_x=1.35, scale_y=1.35, easing=EasingType.EASE_OUT),
        ],
        parameters={"target_lat_norm": 0.35, "target_lon_norm": 0.48, "final_zoom": 1.35},
        tags=["map", "zoom", "geography", "state", "border"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="data_location_pin",
        name="Animated Location Pin Drop",
        category=PresetCategory.DATA_GRAPHICS,
        description="3D teardrop location marker drops with spring bounce onto map coordinate, triggering a ripple ring.",
        duration_min=0.6,
        duration_default=1.2,
        duration_max=2.5,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, pos_y=-150.0, opacity=0.0, easing=EasingType.EXPONENTIAL_OUT),
            KeyframeAnimation(time_offset=0.35, pos_y=0.0, opacity=1.0, easing=EasingType.SPRING),
            KeyframeAnimation(time_offset=0.5, pos_y=-15.0, opacity=1.0, easing=EasingType.SPRING),
            KeyframeAnimation(time_offset=0.65, pos_y=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"pin_color": "0xEF4444", "ripple_color": "0xFF9933", "bounce_decay": 0.6},
        tags=["pin", "location", "marker", "drop", "map"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="data_route_line_draw",
        name="Animated Transit Route Line",
        category=PresetCategory.DATA_GRAPHICS,
        description="Glowing animated path line draws across map between points of interest (e.g. Vande Bharat, highway corridor).",
        duration_min=1.2,
        duration_default=2.5,
        duration_max=5.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"line_width": 6, "glow_color": "0x00E5FF", "draw_duration": 2.0},
        tags=["route", "path", "corridor", "transit", "infrastructure"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="data_number_count_up",
        name="Economic Metric Count-Up",
        category=PresetCategory.DATA_GRAPHICS,
        description="Numbers rapidly tick up from zero to target value (e.g. ₹5 Trillion, 8.2% GDP) with glowing delimiter.",
        duration_min=0.8,
        duration_default=1.8,
        duration_max=3.5,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.9, scale_y=0.9, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.2, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"count_duration": 1.4, "suffix": " लाख करोड़", "prefix": "₹"},
        tags=["metric", "count_up", "economy", "gdp", "numbers"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="data_statistics_bar",
        name="Comparative Bar Graph Growth",
        category=PresetCategory.DATA_GRAPHICS,
        description="Horizontal comparison bars expand smoothly to illustrate fiscal, defense, or poll statistics.",
        duration_min=1.0,
        duration_default=2.0,
        duration_max=4.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.0, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.8, scale_x=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"bar_height": 38, "bar_spacing": 24, "accent_color": "0x10B981"},
        tags=["bar_chart", "statistics", "comparison", "growth"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="data_timeline_progress",
        name="Historical Milestones Timeline",
        category=PresetCategory.DATA_GRAPHICS,
        description="Step-by-step progress nodes illuminate sequentially along vertical or horizontal timeline axis.",
        duration_min=1.5,
        duration_default=3.0,
        duration_max=6.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=0.0, easing=EasingType.LINEAR),
            KeyframeAnimation(time_offset=0.3, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"node_count": 4, "step_interval": 0.6},
        tags=["timeline", "milestone", "history", "years"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="data_quote_highlight",
        name="Key Statement Quote Card",
        category=PresetCategory.DATA_GRAPHICS,
        description="Large typographic quotation card with animated quotation marks and highlighted keyword pulse.",
        duration_min=1.5,
        duration_default=3.5,
        duration_max=7.0,
        ffmpeg_filter_template="fade=t=in:st=0:d=0.3:color=black",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.92, scale_y=0.92, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.4, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"quote_mark_color": "0xF59E0B", "card_bg": "0x1E293B", "highlight_color": "0xFDE047"},
        tags=["quote", "statement", "attribution", "speaker"],
        render_type="pil_overlay",
    ),
    MotionPresetSpec(
        preset_id="data_chart_draw_on",
        name="Interactive Line Chart Unfold",
        category=PresetCategory.DATA_GRAPHICS,
        description="Stock market index, inflation, or trend curve draws dynamically from left to right with glowing data tip.",
        duration_min=1.2,
        duration_default=2.4,
        duration_max=5.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"curve_color": "0x3B82F6", "draw_time": 1.8, "point_count": 12},
        tags=["chart", "line_chart", "trend", "sensex", "inflation"],
        render_type="pil_overlay",
    ),
]
