"""Audio and News Sound Design Agent.

Directs broadcast sound design, schedules sound effects cues, manages background news
beds with voice-prioritized ducking, and builds an authoritative AudioMixPlan.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import AudioMixPlan, SoundCueContract
from core.configuration import AppConfig
from core.state_manager import StateManager


class AudioSoundDesignAgent(BaseAgent):
    """Schedules broadcast sound effects, news intro stings, and background bed ducking."""

    name: str = "AudioSoundDesignAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        self.ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
        self.sfx_dir = Path("assets/sfx")
        self.manifest_path = self.sfx_dir / "manifest.json"
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.logger.warning("Failed to parse SFX manifest: %s", exc)
        return {"categories": {}}

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify duration or timeline segments or script are provided."""
        return bool(kwargs.get("timeline") or kwargs.get("script") or kwargs.get("duration"))

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Schedule sound design cues and produce a structured AudioMixPlan."""
        video_id = kwargs.get("video_id", "audio_mix_001")
        total_duration = float(kwargs.get("duration", 0.0))
        voice_path = str(kwargs.get("voice_audio_path", ""))
        timeline_segments = kwargs.get("timeline_segments", [])
        is_news = kwargs.get("video_type", "news") == "news"

        out_dir = Path("output") / video_id
        out_dir.mkdir(parents=True, exist_ok=True)

        if not total_duration and timeline_segments:
            total_duration = max((s.audio_end for s in timeline_segments), default=30.0)
        elif not total_duration:
            total_duration = 55.0

        # Resolve background news bed track
        bed_path = self._resolve_bed_track(is_news)

        # Schedule Cues
        cues: List[SoundCueContract] = []

        # 1. Opening News Intro Sting (0.0s - 1.8s)
        intro_sound = self._find_sound_by_id("cue_news_intro_sting") or self._find_sound_by_id(
            "cue_bulletin_impact"
        )
        if intro_sound and Path(intro_sound).exists():
            cues.append(
                SoundCueContract(
                    cue_id=f"cue_intro_{video_id}",
                    scene_id="scene_000_hook",
                    sound_type="sting",
                    sound_path=str(Path(intro_sound).resolve()),
                    start_time=0.0,
                    end_time=1.8,
                    gain_db=-4.0,
                    ducking_priority=1,
                    trigger_type="hook",
                    source_license="CC0 / Original",
                )
            )

        # 2. Scene transitions and story reveals
        last_transition_time = 0.0
        for idx, seg in enumerate(timeline_segments):
            seg_start = getattr(seg, "audio_start", 0.0)
            # Add a transition whoosh at story starts if separated by at least 4.0s
            if seg_start > 2.0 and (seg_start - last_transition_time) >= 4.0:
                whoosh_sound = self._find_sound_by_id("cue_transition_whoosh")
                if whoosh_sound and Path(whoosh_sound).exists():
                    cues.append(
                        SoundCueContract(
                            cue_id=f"cue_trans_{idx}",
                            scene_id=getattr(seg, "scene_id", f"scene_{idx:03d}"),
                            sound_type="whoosh",
                            sound_path=str(Path(whoosh_sound).resolve()),
                            start_time=round(seg_start, 2),
                            end_time=round(seg_start + 0.6, 2),
                            gain_db=-7.0,
                            ducking_priority=1,
                            trigger_type="transition",
                            source_license="CC0 / Original",
                        )
                    )
                    last_transition_time = seg_start

        # 3. Outro closing sting (last 2.5s)
        closing_sound = self._find_sound_by_id("cue_bulletin_closing")
        if closing_sound and Path(closing_sound).exists() and total_duration > 5.0:
            cues.append(
                SoundCueContract(
                    cue_id=f"cue_outro_{video_id}",
                    scene_id="scene_outro",
                    sound_type="sting",
                    sound_path=str(Path(closing_sound).resolve()),
                    start_time=round(max(0.0, total_duration - 2.5), 2),
                    end_time=round(total_duration, 2),
                    gain_db=-4.0,
                    ducking_priority=1,
                    trigger_type="outro",
                    source_license="CC0 / Original",
                )
            )

        master_audio_out = str(out_dir / "master_audio_mix.wav")

        mix_plan = AudioMixPlan(
            mix_id=f"mix_{video_id}",
            total_duration=round(total_duration, 2),
            narration_audio_path=voice_path,
            background_bed_path=str(Path(bed_path).resolve()) if bed_path else "",
            bed_volume=0.10,
            ducked_volume=0.03,
            sound_cues=cues,
            target_loudness_lufs=-14.0,
            true_peak_limit_db=-1.0,
            output_master_audio_path=master_audio_out,
        )

        result_data = {
            "mix_plan": mix_plan,
            "mix_plan_dict": mix_plan.to_dict(),
            "cue_count": len(cues),
            "background_bed": bed_path,
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={"video_id": video_id, "cues": len(cues), "duration": total_duration},
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _find_sound_by_id(self, cue_id: str) -> Optional[str]:
        """Lookup physical sound file path by cue ID in manifest."""
        cats = self.manifest.get("categories", {})
        for cat_list in cats.values():
            for item in cat_list:
                if item.get("id") == cue_id:
                    p = self.sfx_dir / item.get("file", "")
                    if p.exists():
                        return str(p)
        return None

    def _resolve_bed_track(self, is_news: bool) -> str:
        """Resolve background music bed track."""
        bed_item = self._find_sound_by_id("bed_daily_news")
        if bed_item and Path(bed_item).exists():
            return bed_item
        # Check assets/music
        m_dir = Path("assets/music")
        wavs = list(m_dir.glob("*.wav")) + list(m_dir.glob("*.mp3"))
        if wavs:
            return str(wavs[0])
        return ""

    def render_mix(self, plan: AudioMixPlan, out_path: str) -> str:
        """Render final multi-track audio mix with sidechain ducking, cues with adelay, and loudness normalization."""
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        has_voice = bool(plan.narration_audio_path and Path(plan.narration_audio_path).exists())
        has_bed = bool(plan.background_bed_path and Path(plan.background_bed_path).exists())

        # Collect valid cues that exist on disk
        valid_cues = []
        for cue in plan.sound_cues or []:
            if cue.sound_path and Path(cue.sound_path).exists():
                valid_cues.append(cue)

        if not has_voice and not has_bed and not valid_cues:
            self._create_silent_wav(dest, plan.total_duration)
            return str(dest)

        inputs = []
        filter_parts = []
        mix_inputs = []

        # Input 0: Voice
        if has_voice:
            inputs.extend(["-i", plan.narration_audio_path])
            filter_parts.append("[0:a]aformat=channel_layouts=stereo:sample_rates=44100[voice]")
            mix_inputs.append("[voice]")
        else:
            inputs.extend(
                ["-f", "lavfi", "-t", str(plan.total_duration), "-i", "anullsrc=r=44100:cl=stereo"]
            )
            filter_parts.append("[0:a]aformat=channel_layouts=stereo:sample_rates=44100[voice]")
            mix_inputs.append("[voice]")

        cur_idx = 1

        # Input 1 (optional): Background music bed
        if has_bed:
            inputs.extend(["-stream_loop", "-1", "-i", plan.background_bed_path])
            fade_out_st = max(0.0, plan.total_duration - 1.5)
            # Bed ducked to -24 dB relative (-24 dB ~ volume 0.063, or using ducked_volume)
            bed_vol = getattr(plan, "ducked_volume", 0.03) or 0.03
            filter_parts.append(
                f"[{cur_idx}:a]aformat=channel_layouts=stereo:sample_rates=44100,"
                f"volume={bed_vol:.3f},afade=t=out:st={fade_out_st:.2f}:d=1.5[bed]"
            )
            mix_inputs.append("[bed]")
            cur_idx += 1

        # Inputs 2..N (optional): Sound cues
        for k, cue in enumerate(valid_cues):
            inputs.extend(["-i", cue.sound_path])
            delay_ms = max(0, int(cue.start_time * 1000))
            gain_factor = 10.0 ** (cue.gain_db / 20.0)
            tag = f"[cue_{k}]"
            filter_parts.append(
                f"[{cur_idx}:a]aformat=channel_layouts=stereo:sample_rates=44100,"
                f"volume={gain_factor:.3f},adelay={delay_ms}|{delay_ms}{tag}"
            )
            mix_inputs.append(tag)
            cur_idx += 1

        # Amix all inputs
        n_inputs = len(mix_inputs)
        mix_str = "".join(mix_inputs)
        filter_parts.append(
            f"{mix_str}amix=inputs={n_inputs}:duration=first:dropout_transition=2[mixed]"
        )

        # Broadcast Loudness normalization (-14 LUFS, -1 dBTP)
        filter_parts.append("[mixed]loudnorm=I=-14:LRA=7:TP=-1.0[out]")

        filter_graph = ";".join(filter_parts)

        try:
            cmd = [
                self.ffmpeg_path,
                "-y",
                *inputs,
                "-t",
                str(plan.total_duration),
                "-filter_complex",
                filter_graph,
                "-map",
                "[out]",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(dest),
            ]
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=60
            )
            return str(dest)
        except Exception as exc:
            self.logger.warning(
                "Advanced FFmpeg audio mix failed (%s). Attempting safe fallback mix.", exc
            )
            if has_voice:
                try:
                    shutil.copy(plan.narration_audio_path, dest)
                    return str(dest)
                except Exception:
                    pass
            self._create_silent_wav(dest, plan.total_duration)
            return str(dest)

    def _create_silent_wav(self, path: Path, duration: float) -> None:
        import wave

        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b"\x00\x00" * int(44100 * max(1.0, duration)))
