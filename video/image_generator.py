"""AI Image generation using Hugging Face free-tier models with fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger("video.ai_image")


class AIImageGenerator:
    """Generates images via Hugging Face Inference API or defers to fallback."""

    def __init__(self, hf_token: str = "", model_id: str = "black-forest-labs/FLUX.1-schnell"):
        self.hf_token = hf_token
        self.model_id = model_id

    def generate(self, prompt: str, output_path: str) -> Optional[str]:
        if not self.hf_token:
            logger.info("HF_TOKEN not set, skipping AI image generation")
            return None

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        url = f"https://api-inference.huggingface.co/models/{self.model_id}"
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {"inputs": f"{prompt}, 9:16 vertical ratio, highly detailed, photorealistic, 4k"}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=40)
            if resp.status_code == 200:
                with open(out_file, "wb") as f:
                    f.write(resp.content)
                logger.info("Generated AI image: %s", out_file)
                return str(out_file)
            else:
                logger.warning("HF API returned %s: %s", resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.warning("AI image generation error: %s", exc)

        return None
