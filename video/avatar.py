"""AI Avatar and Presenter abstraction with cloud/CPU fallback."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("video.avatar")


class AvatarEngine:
    """Manages AI avatar generation or falls back to motion-graphics narration."""

    def __init__(self, enable_avatar: bool = False, model_name: str = "LongCat"):
        self.enable_avatar = enable_avatar
        self.model_name = model_name

    def can_run_gpu_avatar(self) -> bool:
        """Check if GPU and avatar models are available."""
        # On standard GitHub Actions runners, GPU is not present
        return False

    def generate_presenter_clip(self, audio_path: str, output_path: str) -> Optional[str]:
        if not self.enable_avatar or not self.can_run_gpu_avatar():
            logger.info("Avatar mode disabled or CPU environment detected. Using stock/motion graphics fallback.")
            return None

        # GPU placeholder
        return None
