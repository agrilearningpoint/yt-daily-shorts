"""Tests for word-cut rendering in video.renderer."""

import shutil
import subprocess
import wave
from pathlib import Path

from core.agent_contracts import WordCut, WordCutPlan
from video.renderer import render_word_cuts
from video.subtitle_generator import SubtitleGenerator
from video.tts import probe_duration
from video.word_timeline import TokenType, WordToken


def _make_synthetic_wav(path: Path, duration: float = 1.5, rate: int = 24000) -> str:
    """Generate simple silent/sine synthetic audio for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        n_samples = int(duration * rate)
        # Write 0.1s beep then silence
        samples = bytearray(n_samples * 2)
        wf.writeframes(samples)
    return str(path)


def _make_dummy_image(path: Path, color: str = "red") -> str:
    """Generate a small solid PNG image using ffmpeg or PIL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=100x100:d=1",
            "-vframes",
            "1",
            str(path),
        ],
        capture_output=True,
    )
    return str(path)


def test_three_word_synthetic_word_cuts(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import pytest

        pytest.skip("ffmpeg not available")

    # 1. Create synthetic 1.2s audio
    audio_path = _make_synthetic_wav(tmp_path / "master_audio.wav", duration=1.2)

    # 2. Create dummy visual assets for 3 cuts
    img1 = _make_dummy_image(tmp_path / "img1.png", color="blue")
    img2 = _make_dummy_image(tmp_path / "img2.png", color="green")
    img3 = _make_dummy_image(tmp_path / "img3.png", color="red")

    # 3. Build WordCutPlan for "my name is singh"
    cuts = [
        WordCut(
            group_id="wg_000",
            start=0.0,
            end=0.3,
            text="my",
            words=[
                WordToken("my", "my", 0.0, 0.3, TokenType.CUT, 1.0, "test", 0, 2)
            ],
            visual_asset=img1,
            motion_preset_id="ken_burns_zoom_in",
            transition_effect="flash",
        ),
        WordCut(
            group_id="wg_001",
            start=0.3,
            end=0.6,
            text="name",
            words=[
                WordToken("name", "name", 0.3, 0.6, TokenType.CUT, 1.0, "test", 3, 7)
            ],
            visual_asset=img2,
            motion_preset_id="slow_push",
            transition_effect="cut",
        ),
        WordCut(
            group_id="wg_002",
            start=0.6,
            end=1.2,
            text="is singh",
            words=[
                WordToken("is", "is", 0.6, 0.8, TokenType.GLUE, 1.0, "test", 8, 10),
                WordToken(
                    "singh", "singh", 0.8, 1.2, TokenType.CUT, 1.0, "test", 11, 16
                ),
            ],
            visual_asset=img3,
            motion_preset_id="ken_burns_zoom_in",
            transition_effect="cut",
        ),
    ]

    captions = [
        {"word": "my", "start": 0.0, "end": 0.3},
        {"word": "name", "start": 0.3, "end": 0.6},
        {"word": "is", "start": 0.6, "end": 0.8},
        {"word": "singh", "start": 0.8, "end": 1.2},
    ]

    plan = WordCutPlan(
        video_id="test_short",
        fps=30,
        audio_path=audio_path,
        duration=1.2,
        cuts=cuts,
        captions=captions,
    )

    out_mp4 = tmp_path / "final_word_cuts.mp4"
    res = render_word_cuts(
        plan, str(out_mp4), width=360, height=640
    )  # small resolution for fast test

    assert Path(res).exists()
    assert Path(res).stat().st_size > 5000

    # Verify duration
    dur = probe_duration(res)
    assert dur > 1.0


def test_ass_captions_events(tmp_path: Path):
    sub_gen = SubtitleGenerator()
    words = [
        {"word": "मेरा", "start": 0.0, "end": 0.3},
        {"word": "नाम", "start": 0.3, "end": 0.6},
        {"word": "सिंह", "start": 0.6, "end": 0.9},
        {"word": "है", "start": 0.9, "end": 1.2},
    ]
    out_ass = tmp_path / "test.ass"
    sub_gen.generate_ass(words, str(out_ass))

    assert out_ass.exists()
    content = out_ass.read_text(encoding="utf-8")
    assert "Dialogue:" in content
    assert "मेरा" in content
    assert "नाम" in content
    assert "सिंह" in content
