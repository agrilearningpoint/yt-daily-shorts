"""Tests for AudioSoundDesignAgent and multi-track audio mix pipeline."""

import pytest
import wave
from pathlib import Path

from core.configuration import AppConfig
from core.state_manager import StateManager
from core.agent_contracts import AudioMixPlan, SoundCueContract
from agents.audio_sound_design.agent import AudioSoundDesignAgent


def _create_synthetic_wav(path: Path, duration_sec: float = 2.0, freq: int = 440) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    import math
    import struct

    sample_rate = 44100
    n_samples = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = int(16000.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        w.writeframes(frames)
    return str(path)


@pytest.mark.asyncio
async def test_audio_sound_design_agent_schedule(tmp_path):
    cfg = AppConfig()
    sm = StateManager(":memory:")
    agent = AudioSoundDesignAgent(cfg, sm)

    res = await agent.execute(video_id="test_audio_001", duration=45.0, video_type="news")
    assert res.success
    assert "mix_plan" in res.data
    mix_plan: AudioMixPlan = res.data["mix_plan"]
    assert mix_plan.total_duration == 45.0
    assert mix_plan.target_loudness_lufs == -14.0
    assert mix_plan.true_peak_limit_db == -1.0


def test_render_mix_multi_track(tmp_path):
    cfg = AppConfig()
    sm = StateManager(":memory:")
    agent = AudioSoundDesignAgent(cfg, sm)

    voice_wav = tmp_path / "voice.wav"
    _create_synthetic_wav(voice_wav, duration_sec=3.0, freq=300)

    bed_wav = tmp_path / "bed.wav"
    _create_synthetic_wav(bed_wav, duration_sec=4.0, freq=150)

    cue_wav = tmp_path / "cue_whoosh.wav"
    _create_synthetic_wav(cue_wav, duration_sec=0.5, freq=600)

    out_mix = tmp_path / "final_mix.wav"

    plan = AudioMixPlan(
        mix_id="test_mix_render",
        total_duration=3.0,
        narration_audio_path=str(voice_wav),
        background_bed_path=str(bed_wav),
        bed_volume=0.10,
        ducked_volume=0.03,
        sound_cues=[
            SoundCueContract(
                cue_id="cue_1",
                scene_id="scene_000",
                sound_type="whoosh",
                sound_path=str(cue_wav),
                start_time=0.5,
                end_time=1.0,
                gain_db=-6.0,
                ducking_priority=1,
                trigger_type="transition",
                source_license="CC0",
            )
        ],
        target_loudness_lufs=-14.0,
        true_peak_limit_db=-1.0,
        output_master_audio_path=str(out_mix),
    )

    result_path = agent.render_mix(plan, str(out_mix))
    assert Path(result_path).exists()
    assert Path(result_path).stat().st_size > 1000
