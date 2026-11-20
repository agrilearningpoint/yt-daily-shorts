"""Video Reframe Motion Presets (Presets 25 to 32) for BHARAT KI SOCH.

Intelligent 16:9 to 9:16 vertical re-framing, dynamic blurred background pillars,
speaker centering, and multi-source video layouts.
"""

from __future__ import annotations

from typing import List

from video.motion_presets.models import (
    EasingType,
    KeyframeAnimation,
    MotionPresetSpec,
    PresetCategory,
)

VIDEO_REFRAME_PRESETS: List[MotionPresetSpec] = [
    MotionPresetSpec(
        preset_id="video_speaker_focus_reframe",
        name="Speaker Focus Center Reframe",
        category=PresetCategory.VIDEO_REFRAME,
        description="Scales 16:9 source to fit 1080w with upper-middle speaker placement and blurred ambient mirror backdrop.",
        duration_min=1.0,
        duration_default=3.5,
        duration_max=15.0,
        ffmpeg_filter_template="split[va][vb];[va]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[vbg];[vb]scale=1080:1920:force_original_aspect_ratio=decrease[vfg];[vbg][vfg]overlay=(W-w)/2:360",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=1.0, scale_y=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"blur_radius": 24, "fg_vertical_offset": 360},
        tags=["reframe", "speaker", "blurred_pillars", "16_to_9"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="video_face_follow_vertical_crop",
        name="Face-Follow Vertical Dynamic Crop",
        category=PresetCategory.VIDEO_REFRAME,
        description="Direct 9:16 vertical crop of 16:9 video actively tracked to human face coordinates.",
        duration_min=1.0,
        duration_default=4.0,
        duration_max=15.0,
        ffmpeg_filter_template="scale=-1:1920,crop=1080:1920:'max(0,min(in_w-1080,in_w*0.5-540))':0",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, pos_x=0.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"face_center_x": 0.5, "tracking_smoothing": 0.15},
        tags=["face_track", "crop", "9_16", "press_conference"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="video_reporter_split_screen",
        name="Anchor & Ground Reporter Split",
        category=PresetCategory.VIDEO_REFRAME,
        description="Dual feed vertical stack: studio anchor on upper half, ground reporter/correspondent on lower half.",
        duration_min=1.5,
        duration_default=4.5,
        duration_max=12.0,
        ffmpeg_filter_template="split[top][bot];[top]crop=iw:ih/2:0:0,scale=1080:950[vtop];[bot]crop=iw:ih/2:0:ih/2,scale=1080:950[vbot];[vtop][vbot]vstack",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"split_y": 960, "separator_thickness": 6, "separator_color": "0xFF9933"},
        tags=["split_screen", "reporter", "ground_report", "live"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="video_pip_headline",
        name="Picture-in-Picture News Box",
        category=PresetCategory.VIDEO_REFRAME,
        description="Floating rounded PiP video window positioned above lower thirds with drop shadow and border.",
        duration_min=1.0,
        duration_default=3.0,
        duration_max=10.0,
        ffmpeg_filter_template="scale=920:-1[pip];[0:v][pip]overlay=80:400",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=0.8, scale_y=0.8, opacity=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.3, scale_x=1.0, scale_y=1.0, opacity=1.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"pip_width": 920, "pip_x": 80, "pip_y": 400, "border_radius": 18},
        tags=["pip", "overlay", "boxed_video", "studio"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="video_two_source_comparison",
        name="Two-Source Claim Comparison",
        category=PresetCategory.VIDEO_REFRAME,
        description="Side-by-side or stacked split comparing contradictory statements or before-and-after footage.",
        duration_min=1.5,
        duration_default=4.0,
        duration_max=10.0,
        ffmpeg_filter_template="split[v1][v2];[v1]scale=1080:900[top];[v2]scale=1080:900[bot];[top][bot]vstack",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, opacity=1.0, easing=EasingType.LINEAR),
        ],
        parameters={"stack_orientation": "vertical", "label_left": "दावा", "label_right": "सच्चाई"},
        tags=["comparison", "fact_check", "claim_vs_reality", "split"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="video_dynamic_montage",
        name="Dynamic Fast-Cut B-Roll Montage",
        category=PresetCategory.VIDEO_REFRAME,
        description="Rapid 0.6s to 1.2s b-roll video rhythm with alternating direction zooms.",
        duration_min=1.2,
        duration_default=3.0,
        duration_max=6.0,
        ffmpeg_filter_template="eq=saturation=1.2:contrast=1.1,fade=t=in:st=0:d=0.1:color=white",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=1.05, scale_y=1.05, easing=EasingType.LINEAR),
            KeyframeAnimation(time_offset=3.0, scale_x=1.12, scale_y=1.12, easing=EasingType.LINEAR),
        ],
        parameters={"cut_interval": 0.8, "flash_on_cut": True},
        tags=["montage", "fast_cut", "broll", "rhythm"],
        render_type="ffmpeg",
    ),
    MotionPresetSpec(
        preset_id="video_to_headline_transition",
        name="Video Push to Headline Strap",
        category=PresetCategory.VIDEO_REFRAME,
        description="Live video shrinks upward to the top half while the bottom expands to deliver breaking facts.",
        duration_min=0.8,
        duration_default=2.0,
        duration_max=5.0,
        ffmpeg_filter_template="",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, scale_x=1.0, scale_y=1.0, pos_y=0.0, easing=EasingType.EASE_OUT),
            KeyframeAnimation(time_offset=0.5, scale_x=0.9, scale_y=0.9, pos_y=-240.0, easing=EasingType.EASE_OUT),
        ],
        parameters={"target_y": -240, "shrink_scale": 0.9},
        tags=["video_transition", "shrink", "facts", "explain"],
        render_type="hybrid",
    ),
    MotionPresetSpec(
        preset_id="video_vertical_subject_tracking",
        name="Vertical Moving Subject Tracking",
        category=PresetCategory.VIDEO_REFRAME,
        description="Linear interpolated pan window following mobile vehicles, sports figures, or walking delegates.",
        duration_min=1.5,
        duration_default=4.0,
        duration_max=12.0,
        ffmpeg_filter_template="scale=-1:1920,crop=1080:1920:'(in_w-1080)*(t/{duration})':0",
        keyframes=[
            KeyframeAnimation(time_offset=0.0, pos_x=0.0, easing=EasingType.LINEAR),
            KeyframeAnimation(time_offset=4.0, pos_x=400.0, easing=EasingType.LINEAR),
        ],
        parameters={"track_axis": "X", "track_velocity_px_s": 100},
        tags=["tracking", "movement", "pan_track", "action"],
        render_type="ffmpeg",
    ),
]
