"""AI image (and optional clip) generation via Hugging Face Inference Providers.

Uses ``huggingface_hub.InferenceClient`` with ``provider="auto"`` so HF picks a
currently-serving backend (fal-ai / replicate / hf-inference / ...). Model ids
must be passed explicitly — HF has no reliable "default model" for a task — so
we walk a ranked candidate list and take the first one that actually renders.

Free HF *inference* needs credits; without them every call raises HTTP 402 and
we return ``None`` fast (the media chain then falls back to Agnes → Cloudflare →
stock/design). Storage is free — see ``core.hf_storage``.

Models are configurable through ``config.media.hf_image_models``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("video.ai_image")

# Ranked: best quality first. HF recommended text-to-image models (Nov 2026).
DEFAULT_IMAGE_MODELS: List[str] = [
    "black-forest-labs/FLUX.1-Krea-dev",
    "Qwen/Qwen-Image",
    "ByteDance/Hyper-SD",
    "stabilityai/stable-diffusion-3-medium-diffusers",
]

# Text-to-video models, kept for the long-form milestone (needs credits).
DEFAULT_VIDEO_MODELS: List[str] = [
    "Lightricks/LTX-Video-0.9.8-13B-distilled",   # fast
    "tencent/HunyuanVideo",                        # quality
    "Wan-AI/Wan2.2-TI2V-5B",
]

_PROMPT_SUFFIX = ", vertical 9:16 composition, photorealistic, no text, no letters, no watermark, no logos"


class AIImageGenerator:
    """Generates images (or short clips) via HF Inference Providers."""

    def __init__(self, hf_token: str = "", model_id: Optional[str] = None,
                 models: Optional[List[str]] = None, provider: str = "auto",
                 timeout: float = 120.0) -> None:
        self.hf_token = hf_token
        self.models = list(models or ([model_id] if model_id else DEFAULT_IMAGE_MODELS))
        self.provider = provider
        self.timeout = timeout
        self.dead = False
        self.last_error = ""
        self._client = None

    # ------------------------------------------------------------------ client
    def _get_client(self):
        if self._client is None:
            from huggingface_hub import InferenceClient   # optional dependency

            self._client = InferenceClient(provider=self.provider, api_key=self.hf_token,
                                           timeout=self.timeout)
        return self._client

    # ------------------------------------------------------------------ images
    def generate(self, prompt: str, output_path: str) -> Optional[str]:
        """Render one vertical image. Returns the saved path or ``None``."""
        if not self.hf_token or self.dead:
            return None
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        text = (prompt or "") + _PROMPT_SUFFIX

        for model in self.models:
            try:
                image = self._get_client().text_to_image(text, model=model)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{model}: {type(exc).__name__}: {str(exc)[:160]}"
                msg = str(exc)
                if "402" in msg or "Payment Required" in msg:
                    # no inference credits on this account — stop trying this run
                    self.dead = True
                    logger.info("HF inference needs credits (%s) — skipping HF images", model)
                    return None
                logger.warning("HF image failed via %s: %s", model, self.last_error)
                continue
            try:
                image.save(str(out_file))
                logger.info("HF image generated (%s): %s", model, out_file)
                return str(out_file)
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)[:200]
                logger.warning("HF image save failed: %s", exc)
        return None

    # ------------------------------------------------------------------ video
    def generate_clip(self, prompt: str, output_path: str, model: Optional[str] = None) -> Optional[str]:
        """Render a short clip (long-form milestone). Needs inference credits."""
        if not self.hf_token or self.dead:
            return None
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        for candidate in ([model] if model else self.models and DEFAULT_VIDEO_MODELS):
            try:
                payload = self._get_client().text_to_video(prompt, model=candidate)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{candidate}: {type(exc).__name__}: {str(exc)[:160]}"
                if "402" in str(exc) or "Payment Required" in str(exc):
                    self.dead = True
                    logger.info("HF video inference needs credits — skipping")
                    return None
                logger.warning("HF clip failed via %s: %s", candidate, self.last_error)
                continue
            try:
                data = payload if isinstance(payload, (bytes, bytearray)) else getattr(payload, "read", lambda: b"")()
                if data:
                    out_file.write_bytes(bytes(data))
                    return str(out_file)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HF clip save failed: %s", exc)
        return None
