"""AI image (and optional clip) generation — three free-first backends.

Order of attack (cheapest / most likely to work first):

1. ``hf-inference`` credits route  — ``InferenceClient`` with an explicit model
   ladder. Only works when the HF account has pre-paid credits or PRO, so it is
   tried but never relied upon (HTTP 402 flips a latch for the rest of the run).
2. **HF Space (free)** — the official ``black-forest-labs/FLUX.1-schnell``
   Gradio Space through ``gradio_client``. Real FLUX weights on HF hardware,
   no credits needed, authenticated with the same HF token. ~6 s per image.
3. **Pollinations (free, keyless)** — last-resort HTTP backend, no account at
   all. Keeps the pipeline alive even if HF itself is down.

Storage never depends on any of this — see ``core.hf_storage`` (free, unlimited
for public repos).

Model ladders are configurable via ``config.media.hf_image_models``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("video.ai_image")

# Ranked: best quality first. HF recommended text-to-image models (Nov 2026).
# NOTE hf-inference now serves exactly ONE t2i model (SD3-medium); everything
# else 410s as "deprecated" on that provider — the Space route covers the rest.
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

# Free Gradio Spaces serving real diffusion models (no inference credits).
DEFAULT_SPACES: List[str] = [
    "black-forest-labs/FLUX.1-schnell",
    "black-forest-labs/FLUX.1-dev",
]

_PROMPT_SUFFIX = ", vertical 9:16 composition, photorealistic, no text, no letters, no watermark, no logos"

_SPACE_API = "/infer"


class AIImageGenerator:
    """Generates images (or short clips) for free: credits → Space → Pollinations."""

    def __init__(self, hf_token: str = "", model_id: Optional[str] = None,
                 models: Optional[List[str]] = None, provider: str = "auto",
                 timeout: float = 120.0, use_space: bool = True,
                 use_pollinations: bool = True,
                 spaces: Optional[List[str]] = None) -> None:
        self.hf_token = hf_token
        self.models = list(models or ([model_id] if model_id else DEFAULT_IMAGE_MODELS))
        self.provider = provider
        self.timeout = timeout
        self.use_space = use_space
        self.use_pollinations = use_pollinations
        self.spaces = list(spaces or DEFAULT_SPACES)
        self.dead = False              # credits route exhausted
        self.space_dead = False        # every Space failed
        self.pollinations_dead = False
        self.last_error = ""
        self._client = None
        self._space_clients: dict = {}

    # ------------------------------------------------------------------ client
    def _get_client(self):
        if self._client is None:
            from huggingface_hub import InferenceClient   # optional dependency

            self._client = InferenceClient(provider=self.provider, api_key=self.hf_token,
                                           timeout=self.timeout)
        return self._client

    def _get_space(self, space_id: str):
        if space_id not in self._space_clients:
            from gradio_client import Client                # optional dependency

            logger.info("connecting to Space %s", space_id)
            self._space_clients[space_id] = Client(space_id, token=self.hf_token or None,
                                                  verbose=False)
        return self._space_clients[space_id]

    # ------------------------------------------------------------------ images
    def generate(self, prompt: str, output_path: str) -> Optional[str]:
        """Render one vertical image. Returns the saved path or ``None``."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        text = (prompt or "") + _PROMPT_SUFFIX

        for backend in (self._via_credits, self._via_space, self._via_pollinations):
            if self.dead and backend is self._via_credits:
                continue
            try:
                if backend(text, out_file):
                    logger.info("AI image generated via %s: %s", backend.__name__, out_file)
                    return str(out_file)
            except Exception as exc:  # noqa: BLE001 — a backend must never break a run
                self.last_error = f"{backend.__name__}: {type(exc).__name__}: {str(exc)[:160]}"
                logger.warning("AI image backend %s crashed: %s", backend.__name__, exc)
        logger.warning("all AI image backends failed (%s)", self.last_error)
        return None

    # -- backend 1: HF Inference Providers (needs credits)
    def _via_credits(self, text: str, out_file: Path) -> bool:
        if not self.hf_token or self.dead:
            return False
        for model in self.models:
            try:
                image = self._get_client().text_to_image(text, model=model)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{model}: {type(exc).__name__}: {str(exc)[:160]}"
                msg = str(exc)
                if "402" in msg or "Payment Required" in msg:
                    # no inference credits on this account — stop trying this run
                    self.dead = True
                    logger.info("HF inference needs credits (%s) — trying free Space instead", model)
                    return False
                if "410" in msg or "deprecated" in msg:
                    continue      # model retired on this provider, next candidate
                logger.warning("HF image failed via %s: %s", model, self.last_error)
                continue
            try:
                image.save(str(out_file))
                return True
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)[:200]
        return False

    # -- backend 2: free Gradio Space (real FLUX, no credits)
    def _via_space(self, text: str, out_file: Path) -> bool:
        if not self.use_space or self.space_dead:
            return False
        for space_id in self.spaces:
            try:
                client = self._get_space(space_id)
                result = client.predict(
                    prompt=text,
                    seed=0,
                    randomize_seed=True,
                    width=768,
                    height=1344,
                    num_inference_steps=4,
                    api_name=_SPACE_API,
                )
                produced = result[0] if isinstance(result, (list, tuple)) else result
                if not produced or not os.path.exists(str(produced)):
                    raise RuntimeError(f"space returned no file: {result!r}"[:200])
                self._normalise_image(str(produced), out_file)
                return True
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"space:{space_id}: {type(exc).__name__}: {str(exc)[:160]}"
                logger.warning("Space %s failed: %s", space_id, exc)
                self._space_clients.pop(space_id, None)
        self.space_dead = True         # every Space failed; don't hammer in this run
        return False

    # -- backend 3: Pollinations (free, keyless)
    def _via_pollinations(self, text: str, out_file: Path) -> bool:
        if not self.use_pollinations or self.pollinations_dead:
            return False
        try:
            import requests
            from urllib.parse import quote

            url = "https://image.pollinations.ai/prompt/" + quote(text[:900], safe="")
            resp = requests.get(url, params={"width": 768, "height": 1344, "model": "flux",
                                             "nologo": "true", "enhance": "false"},
                                timeout=self.timeout)
            if resp.status_code != 200 or len(resp.content) < 20_000:
                raise RuntimeError(f"HTTP {resp.status_code}, {len(resp.content)} bytes")
            tmp = Path(tempfile.mkdtemp()) / "pollinations.img"
            tmp.write_bytes(resp.content)
            self._normalise_image(str(tmp), out_file)
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"pollinations: {type(exc).__name__}: {str(exc)[:160]}"
            logger.warning("Pollinations failed: %s", exc)
            self.pollinations_dead = True
            return False

    # ------------------------------------------------------------------ video
    def generate_clip(self, prompt: str, output_path: str, model: Optional[str] = None) -> Optional[str]:
        """Render a short clip (long-form milestone). Needs inference credits."""
        if not self.hf_token or self.dead:
            return None
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        for candidate in ([model] if model else DEFAULT_VIDEO_MODELS):
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
                data = payload if isinstance(payload, (bytes, bytearray)) else payload.read()
                if data:
                    out_file.write_bytes(bytes(data))
                    return str(out_file)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HF clip save failed: %s", exc)
        return None

    # ------------------------------------------------------------------ helper
    @staticmethod
    def _normalise_image(src: str, dest: Path) -> None:
        """Convert whatever the backend produced (webp/png/jpeg) to the .jpg path."""
        try:
            from PIL import Image
            with Image.open(src) as im:
                im.convert("RGB").save(dest, "JPEG", quality=92)
        except Exception:  # noqa: BLE001 — PIL missing or odd format: copy bytes as-is
            dest.write_bytes(Path(src).read_bytes())
