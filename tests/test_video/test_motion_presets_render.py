"""Comprehensive execution test rendering all 56 motion presets with FFmpeg."""

import pytest
import shutil
from PIL import Image

from video.motion_presets import list_all_presets
from video.renderer import SceneClip, VideoRenderer


@pytest.fixture(scope="module")
def synthetic_assets(tmp_path_factory):
    """Generate low-res synthetic background and transparent overlay for fast rendering tests."""
    temp_dir = tmp_path_factory.mktemp("preset_render_assets")
    bg_path = temp_dir / "synthetic_bg.jpg"
    ov_path = temp_dir / "synthetic_ov.png"

    # 540x960 fast test canvas (maintains 9:16 aspect ratio)
    bg_img = Image.new("RGB", (540, 960), color=(30, 45, 60))
    bg_img.save(str(bg_path), quality=80)

    ov_img = Image.new("RGBA", (540, 960), color=(0, 0, 0, 0))
    ov_img.save(str(ov_path))

    return bg_path, ov_path, temp_dir


def test_ffmpeg_available():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None, "FFmpeg binary must be installed and on PATH."


def test_render_all_56_motion_presets(synthetic_assets):
    """Verify that every one of the 56 presets compiles and renders a valid video clip with FFmpeg."""
    bg_path, ov_path, temp_dir = synthetic_assets
    renderer = VideoRenderer(width=540, height=960, fps=30)

    presets = list_all_presets()
    assert len(presets) == 56

    failed_presets = []
    render_dir = temp_dir / "preset_outputs"
    render_dir.mkdir(parents=True, exist_ok=True)

    for idx, preset in enumerate(presets):
        out_clip_path = render_dir / f"clip_{preset.preset_id}.mp4"
        clip = SceneClip(
            background=str(bg_path),
            overlay=str(ov_path),
            duration=0.5,
            motion_preset_id=preset.preset_id,
            transition_effect=preset.preset_id if "transition" in preset.preset_id else "flash",
        )

        try:
            renderer._beat_clip(
                clip=clip,
                length=0.5,
                idx=idx,
                out=str(out_clip_path),
                t0=0.0,
            )
            if not out_clip_path.exists() or out_clip_path.stat().st_size < 1000:
                failed_presets.append((preset.preset_id, "File missing or under 1000 bytes"))
        except Exception as exc:
            failed_presets.append((preset.preset_id, str(exc)[:200]))

    assert not failed_presets, f"Failed presets ({len(failed_presets)}/56): {failed_presets}"
