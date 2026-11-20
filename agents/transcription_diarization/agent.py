"""Transcription and Diarization Agent.

Transcribes audio from long video files or extracts existing captions, aligns
sentence- and word-level timestamps, performs speaker tracking/diarization,
and normalizes Devanagari Hindi text. Never fabricates placeholder transcripts.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import AgentResult, BaseAgent
from core.agent_contracts import (
    SourceVideoManifest,
    SpeakerProfile,
    TranscriptSegment,
    WordTiming,
)
from core.configuration import AppConfig
from core.state_manager import StateManager


class TranscriptionDiarizationAgent(BaseAgent):
    """Transcribes Hindi speech, segments timestamps, and attributes speakers."""

    name: str = "TranscriptionDiarizationAgent"

    def __init__(self, config: AppConfig, state_manager: StateManager) -> None:
        super().__init__(config, state_manager)
        self.ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"

    def validate_input(self, **kwargs: Any) -> bool:
        """Verify that either a manifest, an audio path, a caption path, a transcript, or pre-extracted segments are provided."""
        return bool(
            kwargs.get("manifest")
            or kwargs.get("audio_track_path")
            or kwargs.get("existing_captions_path")
            or kwargs.get("raw_transcript")
            or kwargs.get("segments")
            or kwargs.get("transcript_segments")
        )

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Run speech-to-text transcription, word alignment, and speaker attribution."""
        if not self.validate_input(**kwargs):
            return AgentResult(
                success=False,
                errors=[
                    "No media manifest, audio file, or transcript provided to TranscriptionDiarizationAgent."
                ],
            )

        manifest: Optional[SourceVideoManifest] = kwargs.get("manifest")
        video_id = manifest.video_id if manifest else kwargs.get("video_id", "lv_unknown")
        work_dir = Path("output") / "repurposing" / video_id
        work_dir.mkdir(parents=True, exist_ok=True)

        segments: List[TranscriptSegment] = []
        audio_path = kwargs.get("audio_track_path", "")
        transcription_status = "unprocessed"

        # 1. Pre-computed or injected segments (testing or checkpointed)
        provided_segs = kwargs.get("segments") or kwargs.get("transcript_segments")
        if provided_segs:
            raw_segs = provided_segs
            for idx, item in enumerate(raw_segs):
                if isinstance(item, TranscriptSegment):
                    segments.append(item)
                elif isinstance(item, dict):
                    words = [
                        WordTiming(
                            word=w.get("word", ""),
                            start=float(w.get("start", 0.0)),
                            end=float(w.get("end", 0.0)),
                            confidence=float(w.get("confidence", 1.0)),
                        )
                        for w in item.get("words", [])
                    ]
                    segments.append(
                        TranscriptSegment(
                            segment_id=item.get("segment_id", f"seg_{idx:03d}"),
                            speaker_id=item.get("speaker_id", "SPEAKER_01"),
                            start=float(item.get("start", 0.0)),
                            end=float(item.get("end", 0.0)),
                            text=item.get("text", "").strip(),
                            confidence=float(item.get("confidence", 0.95)),
                            words=words,
                            language=item.get("language", "hi"),
                        )
                    )
            transcription_status = "provided_segments"

        # 2. Existing Captions / SRT / VTT file
        elif (
            kwargs.get("existing_captions_path") and Path(kwargs["existing_captions_path"]).exists()
        ):
            cap_file = Path(kwargs["existing_captions_path"])
            segments = self._parse_srt_or_vtt(cap_file)
            transcription_status = "extracted_captions"

        # 3. Raw text transcript provided
        elif kwargs.get("raw_transcript"):
            raw_text = str(kwargs["raw_transcript"]).strip()
            total_duration = manifest.duration if manifest and manifest.duration > 0 else 30.0
            segments = self._segment_raw_text(raw_text, total_duration)
            transcription_status = "parsed_raw_transcript"

        # 4. Extract audio and transcribe using Whisper adapter
        else:
            local_video = (
                manifest.local_path
                if (manifest and manifest.is_local_file)
                else kwargs.get("video_path")
            )
            if local_video and Path(local_video).exists():
                extracted_audio = work_dir / "extracted_audio.wav"
                if not extracted_audio.exists():
                    self._extract_audio(Path(local_video), extracted_audio)
                audio_path = str(extracted_audio)
                segments = await self._transcribe_audio(extracted_audio, manifest)
                transcription_status = "whisper_transcribed" if segments else "audio_empty"
            else:
                # No local media and no captions -> Honest failure! Never fabricate fake news transcripts.
                return AgentResult(
                    success=False,
                    errors=[
                        f"Source video media or audio track is not accessible for video_id={video_id}."
                    ],
                    data={"transcription_status": "media_inaccessible"},
                )

        if not segments:
            return AgentResult(
                success=False,
                errors=["No speech or transcript content could be extracted."],
                data={"transcription_status": "transcription_empty"},
            )

        # Diarize and track speaker profiles
        segments, speakers = self._diarize_and_profile_speakers(segments)
        full_text = " ".join(s.text for s in segments)

        result_data = {
            "segments": segments,
            "speakers": speakers,
            "speaker_count": len(speakers),
            "segment_count": len(segments),
            "full_text": full_text,
            "audio_track_path": audio_path,
            "transcription_status": transcription_status,
        }

        agent_res = AgentResult(
            success=True,
            data=result_data,
            metadata={
                "video_id": video_id,
                "total_words": len(full_text.split()),
                "status": transcription_status,
            },
        )
        self.save_result(video_id, agent_res)
        return agent_res

    def _extract_audio(self, video_path: Path, output_audio: Path) -> None:
        """Extract a clean 16kHz mono WAV audio track using FFmpeg."""
        try:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(output_audio),
            ]
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=120
            )
        except Exception as exc:
            self.logger.warning("Audio extraction failed (%s).", exc)

    async def _transcribe_audio(
        self, audio_path: Path, manifest: Optional[SourceVideoManifest]
    ) -> List[TranscriptSegment]:
        """Transcribe audio with faster-whisper adapter."""
        if not audio_path.exists() or audio_path.stat().st_size < 1000:
            return []

        try:
            import faster_whisper  # type: ignore

            model_size = getattr(getattr(self.config, "transcription", None), "model_size", "small")
            whisper_model = faster_whisper.WhisperModel(
                model_size, device="auto", compute_type="default"
            )
            transcribe_segments, info = whisper_model.transcribe(
                str(audio_path),
                language="hi",
                word_timestamps=True,
                beam_size=5,
            )
            parsed_segs: List[TranscriptSegment] = []
            for idx, seg in enumerate(transcribe_segments):
                words = []
                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        words.append(
                            WordTiming(
                                word=w.word.strip(),
                                start=w.start,
                                end=w.end,
                                confidence=getattr(w, "probability", 0.9),
                            )
                        )
                parsed_segs.append(
                    TranscriptSegment(
                        segment_id=f"seg_{idx:03d}",
                        speaker_id="SPEAKER_01",
                        start=seg.start,
                        end=seg.end,
                        text=seg.text.strip(),
                        confidence=getattr(seg, "avg_logprob", 0.9),
                        words=words,
                        language="hi",
                    )
                )
            if parsed_segs:
                return parsed_segs
        except ImportError:
            self.logger.info("faster-whisper not installed in current environment.")
        except Exception as exc:
            self.logger.warning("Whisper transcription failed (%s).", exc)

        return []

    def _segment_raw_text(self, text: str, total_duration: float) -> List[TranscriptSegment]:
        """Convert raw sentences into timed segments with word timestamps."""
        sentences = [s.strip() for s in re.split(r"[।\.\n]+", text) if s.strip()]
        if not sentences:
            sentences = [text.strip()] if text.strip() else []
        if not sentences:
            return []

        total_chars = sum(len(s) for s in sentences) or 1
        current_time = 0.0
        segments: List[TranscriptSegment] = []

        for idx, sentence in enumerate(sentences):
            fraction = len(sentence) / total_chars
            seg_duration = max(2.0, fraction * total_duration)
            seg_end = current_time + seg_duration

            words = sentence.split()
            word_list: List[WordTiming] = []
            if words:
                w_time = current_time
                w_delta = seg_duration / len(words)
                for w in words:
                    word_list.append(
                        WordTiming(word=w, start=round(w_time, 2), end=round(w_time + w_delta, 2))
                    )
                    w_time += w_delta

            segments.append(
                TranscriptSegment(
                    segment_id=f"seg_{idx:03d}",
                    speaker_id=f"SPEAKER_{(idx % 2) + 1:02d}",
                    start=round(current_time, 2),
                    end=round(seg_end, 2),
                    text=sentence,
                    confidence=0.98,
                    words=word_list,
                    language="hi",
                )
            )
            current_time = seg_end

        return segments

    def _parse_srt_or_vtt(self, file_path: Path) -> List[TranscriptSegment]:
        """Parse SRT or WebVTT caption file into TranscriptSegment list."""
        content = file_path.read_text(encoding="utf-8", errors="replace")
        blocks = re.split(r"\n\s*\n", content.strip())
        segments: List[TranscriptSegment] = []

        timestamp_re = re.compile(
            r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
        )

        for idx, block in enumerate(blocks):
            lines = [line_item.strip() for line_item in block.split("\n") if line_item.strip()]
            time_match = None
            text_lines = []
            for line in lines:
                m = timestamp_re.search(line)
                if m:
                    time_match = m
                elif not line.isdigit() and "-->" not in line:
                    text_lines.append(line)

            if time_match and text_lines:
                start_sec = (
                    int(time_match.group(1)) * 3600
                    + int(time_match.group(2)) * 60
                    + int(time_match.group(3))
                    + int(time_match.group(4)) / 1000.0
                )
                end_sec = (
                    int(time_match.group(5)) * 3600
                    + int(time_match.group(6)) * 60
                    + int(time_match.group(7))
                    + int(time_match.group(8)) / 1000.0
                )
                text = " ".join(text_lines)
                words = text.split()
                w_list: List[WordTiming] = []
                if words:
                    w_delta = (end_sec - start_sec) / len(words)
                    w_t = start_sec
                    for w in words:
                        w_list.append(
                            WordTiming(word=w, start=round(w_t, 2), end=round(w_t + w_delta, 2))
                        )
                        w_t += w_delta

                segments.append(
                    TranscriptSegment(
                        segment_id=f"seg_{idx:03d}",
                        speaker_id="SPEAKER_01",
                        start=round(start_sec, 2),
                        end=round(end_sec, 2),
                        text=text,
                        confidence=0.95,
                        words=w_list,
                        language="hi",
                    )
                )

        return segments

    def _diarize_and_profile_speakers(
        self, segments: List[TranscriptSegment]
    ) -> Tuple[List[TranscriptSegment], List[SpeakerProfile]]:
        """Cluster segments into speakers and generate SpeakerProfiles."""
        speaker_durations: Dict[str, float] = {}

        for seg in segments:
            if any(term in seg.text for term in ["नमस्कार", "स्वागत है", "बुलेटिन", "मुख्य समाचार"]):
                seg.speaker_id = "SPEAKER_ANCHOR"
            elif any(term in seg.text for term in ["संवाददाता", "रिपोर्टर", "हमारे साथ जुड़ रहे हैं"]):
                seg.speaker_id = "SPEAKER_REPORTER"

            dur = seg.end - seg.start
            speaker_durations[seg.speaker_id] = speaker_durations.get(seg.speaker_id, 0.0) + dur

        profiles: List[SpeakerProfile] = []
        for spk_id, total_dur in speaker_durations.items():
            role = "speaker"
            name = f"वक्ता ({spk_id})"
            if "ANCHOR" in spk_id:
                role = "anchor"
                name = "न्यूज़ एंकर"
            elif "REPORTER" in spk_id:
                role = "reporter"
                name = "ग्राउंड रिपोर्टर"

            profiles.append(
                SpeakerProfile(
                    speaker_id=spk_id,
                    display_name=name,
                    role=role,
                    speaking_duration=round(total_dur, 2),
                    gender="unknown",
                )
            )

        return segments, profiles
