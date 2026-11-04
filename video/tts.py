"""Text-to-speech engine using edge-tts (free neural Hindi voices) with fallback."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("video.tts")

# Popular free high quality Indian neural voices in edge-tts
HINDI_VOICES = {
    "female": "hi-IN-SwaraNeural",
    "male": "hi-IN-MadhurNeural"
}


class TTSEngine:
    """Generates Hindi voiceover audio using edge-tts or offline fallback."""

    def __init__(self, voice: str = "hi-IN-SwaraNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def generate_audio(self, text: str, output_path: str) -> str:
        """Synthesize Hindi speech into an MP3 file."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            import edge_tts
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )
            await communicate.save(str(out_file))
            logger.info("edge-tts audio generated successfully: %s", out_file)
            return str(out_file)
        except Exception as exc:
            logger.warning("edge-tts failed or not available (%s), creating fallback tone/silent audio", exc)
            return self._generate_fallback_audio(str(out_file), duration_sec=50.0)

    def _generate_fallback_audio(self, output_path: str, duration_sec: float = 50.0) -> str:
        """Generate silent or dummy audio with ffmpeg if edge-tts fails."""
        import subprocess
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration_sec),
            "-acodec", "libmp3lame",
            output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            logger.info("Generated fallback silence audio: %s", output_path)
            return output_path
        except Exception as e:
            logger.warning("ffmpeg silence generation failed: %s. Creating dummy file.", e)
            with open(output_path, "wb") as f:
                f.write(b"MOCK_MP3_DATA" * 100)
            return output_path
