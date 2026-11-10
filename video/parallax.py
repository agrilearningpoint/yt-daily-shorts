"""2.5D "3D photo" motion for a still news photo (free, CPU only).

Depth Anything V2 (small, ONNX, Apache-2.0) estimates which parts of the photo are near
and which are far; each frame then moves the near parts a little more than the background,
so the line's own real photo plays like a slow camera move instead of a flat zoom.

Any failure (no onnxruntime/opencv, model download blocked, odd image) returns None and the
renderer falls back to the normal Ken Burns zoom, so this can never break a run.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("video.parallax")

MODEL_URLS = [
    "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx",
    "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_quantized.onnx",
]
MODEL_DIR = Path(os.getenv("DEPTH_MODEL_DIR", str(Path.home() / ".cache" / "bks-depth")))
_lock = threading.Lock()
_session = None
_failed = False


def _get_session():
    global _session, _failed
    if _session is not None or _failed:
        return _session
    with _lock:
        if _session is not None or _failed:
            return _session
        try:
            import onnxruntime as ort
            import requests
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            path = None
            for url in MODEL_URLS:
                p = MODEL_DIR / url.rsplit("/", 1)[-1]
                if not p.exists() or p.stat().st_size < 1_000_000:
                    try:
                        r = requests.get(url, timeout=120, stream=True)
                        r.raise_for_status()
                        tmp = p.with_suffix(".part")
                        with open(tmp, "wb") as fh:
                            for chunk in r.iter_content(1 << 20):
                                fh.write(chunk)
                        tmp.rename(p)
                    except Exception as exc:
                        logger.warning("depth model download failed (%s): %s", url, exc)
                        continue
                path = p
                break
            if not path:
                raise RuntimeError("no depth model")
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, (os.cpu_count() or 2))
            _session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
            logger.info("Depth model ready: %s", path.name)
        except Exception as exc:
            _failed = True
            logger.warning("3D photo motion disabled: %s", exc)
    return _session


def depth_map(img):
    """Relative depth in 0..1 (1 = nearest), same HxW as img (BGR uint8)."""
    import cv2
    import numpy as np
    sess = _get_session()
    if sess is None:
        return None
    h, w = img.shape[:2]
    # model works on multiples of 14; keep the photo's shape, ~518 on the short side
    s = 518 / min(h, w)
    ih, iw = max(14, int(round(h * s / 14)) * 14), max(14, int(round(w * s / 14)) * 14)
    x = cv2.resize(img, (iw, ih), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    x = x.transpose(2, 0, 1)[None]
    name = sess.get_inputs()[0].name
    d = sess.run(None, {name: x})[0]
    d = np.squeeze(d).astype(np.float32)
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    d = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    d = cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)
    # grow near objects a bit and soften edges, so the move never tears an outline
    d = cv2.dilate(d, np.ones((15, 15), np.uint8))
    d = cv2.GaussianBlur(d, (0, 0), 9)
    return np.clip(d, 0, 1)


def _photo_box(image_path: str, sw: int, sh: int):
    """The sharp photo's rectangle inside the composed background (sidecar written by SceneComposer)."""
    try:
        x, y, w, h = (int(v) for v in Path(image_path + ".box").read_text().split(","))
    except Exception:
        return None
    x, y = max(0, x), max(0, y)
    w, h = min(w, sw - x), min(h, sh - y)
    return (x, y, w, h) if w > 64 and h > 64 else None


def _ease(t):
    return t * t * (3 - 2 * t)


def make_clip(image_path: str, out_path: str, seconds: float, width: int = 1080, height: int = 1920,
              fps: int = 30, style: int = 0, strength: float = 1.0) -> Optional[str]:
    """Render a W x H mp4 of the photo with depth parallax. image_path is the composed (oversized) bg."""
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        logger.debug("parallax deps missing: %s", exc)
        return None
    ffmpeg = shutil.which("ffmpeg")
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if ffmpeg is None or img is None:
        return None
    sh, sw = img.shape[:2]
    if sw < width or sh < height:
        img = cv2.resize(img, (max(sw, width), max(sh, height)))
        sh, sw = img.shape[:2]
    depth = None
    box = _photo_box(image_path, sw, sh)
    if box:
        x, y, w, h = box
        sub = depth_map(img[y:y + h, x:x + w])
        if sub is not None:
            depth = np.zeros((sh, sw), np.float32)    # blurred fill stays flat, far away
            depth[y:y + h, x:x + w] = 0.25 + 0.75 * sub
            depth = cv2.GaussianBlur(depth, (0, 0), 6)
    else:
        depth = depth_map(img)
    if depth is None:
        return None
    frames = max(int(round(seconds * fps)), 2)
    gx, gy = np.meshgrid(np.arange(width, dtype=np.float32) - width / 2,
                         np.arange(height, dtype=np.float32) - height / 2)
    cx, cy = sw / 2, sh / 2
    pad = min((sw - width) / 2, (sh - height) / 2)
    amp = max(18.0, min(pad * 0.75, 70.0)) * strength      # near-object travel in px
    dirs = [(0, 0, 1), (1, 0, 0), (-1, 0, 0), (0, -1, 1), (1, -1, 0), (-1, 1, 1)]
    dx, dy, dolly = dirs[style % len(dirs)]
    proc = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
         "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(frames):
            t = _ease(i / (frames - 1))
            zoom = 1.0 + 0.045 * t                           # gentle overall push
            bx, by = cx + gx / zoom, cy + gy / zoom
            d = cv2.remap(depth, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            k = d - 0.5                                       # near moves one way, far the other
            near_zoom = 1.0 + (0.07 * t * d if dolly else 0.0)
            ox = dx * amp * (t - 0.5) * k * 2
            oy = dy * amp * (t - 0.5) * k * 2
            mx = cx + gx / (zoom * near_zoom) - ox
            my = cy + gy / (zoom * near_zoom) - oy
            frame = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        rc = proc.wait(timeout=180)
    except Exception as exc:
        proc.kill()
        logger.warning("parallax render failed: %s", exc)
        return None
    if rc != 0 or not Path(out_path).exists():
        logger.warning("parallax encode failed: %s", (proc.stderr.read() or b"")[-300:])
        return None
    return out_path
