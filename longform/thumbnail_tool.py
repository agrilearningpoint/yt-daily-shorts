"""Re-cut a film's thumbnail and (optionally) set it on the published video.

    python -m longform.thumbnail_tool --video-id film-6910e004-20261111 \
        --title "सनातन की यात्रा" --yt-video-id 0b-ZijmybxQ --set

The hero is a frame out of the film itself, so the thumbnail can never be
off-topic — the failure mode that put a Gothic cathedral on a Hindu history film
when the hero came from a keyword image search.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from longform import render as R

logger = logging.getLogger("longform.thumbnail")


def _local_film(video_id: str) -> Optional[Path]:
    p = Path("output") / "long" / video_id / "film_1080p.mp4"
    return p if p.exists() else None


def _hf_film(video_id: str) -> Optional[Path]:
    try:
        from huggingface_hub import hf_hub_download

        from core.configuration import load_config

        cfg = load_config()
        token = getattr(getattr(cfg, "media", None), "hf_token", "") or ""
        repo = getattr(getattr(cfg, "media", None), "hf_repo_id", "") or ""
        if not (token and repo):
            return None
        logger.info("downloading long/%s/film_1080p.mp4 from %s", video_id, repo)
        local = hf_hub_download(repo_id=repo, repo_type="dataset", token=token,
                                filename=f"long/{video_id}/film_1080p.mp4")
        dest = Path("output") / "long" / video_id / "film_1080p.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(Path(local).read_bytes())
        return dest if dest.exists() else None
    except Exception as exc:
        logger.warning("HF download failed: %s", exc)
        return None


def candidate_frames(film: Path, n: int = 8, tmp: Optional[Path] = None) -> List[Path]:
    """Grab n frames spread over the film, cropped above the subtitle band."""
    dur = R.probe_duration(str(film)) or 600.0
    tmp = tmp or film.parent / "thumbs_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []
    for i in range(n):
        # skip the first minute (chapter card) and the last (outro)
        t = 60 + (dur - 120) * (i + 0.5) / n
        f = tmp / f"frame_{i:02d}.jpg"
        try:
            R.run([R.ff(), "-y", "-ss", f"{t:.2f}", "-i", str(film), "-frames:v", "1",
                   "-vf", "crop=iw:ih*0.78:0:0,scale=1920:-1", "-q:v", "2", str(f)])
            if f.exists() and f.stat().st_size > 20_000:
                out.append(f)
        except Exception as exc:
            logger.debug("frame at %.0fs failed: %s", t, exc)
    return out


def score(path: Path) -> Tuple[float, float]:
    """(variance, mean brightness) — we want detail and a mid-tone exposure."""
    from PIL import Image
    im = Image.open(path).convert("L").resize((96, 54))
    px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
    mean = sum(px) / max(1, len(px))
    var = sum((v - mean) ** 2 for v in px) / max(1, len(px))
    return var, mean


def grade(path: Path) -> Tuple[float, float, float]:
    """(variance, mean brightness, dark fraction) over a 96x54 luma sample."""
    from PIL import Image
    im = Image.open(path).convert("L").resize((96, 54))
    px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
    mean = sum(px) / max(1, len(px))
    var = sum((v - mean) ** 2 for v in px) / max(1, len(px))
    dark = sum(1 for v in px if v < 28) / max(1, len(px))
    return var, mean, dark


def pick_best(frames: List[Path]) -> Optional[Path]:
    """Prefer a detailed, mid-tone, not-mostly-black frame (netflix-style hero)."""
    best, best_score = None, -1.0
    for f in frames:
        try:
            var, mean, dark = grade(f)
        except Exception:
            continue
        if not (40 <= mean <= 215) or dark > 0.55:
            continue
        s = var * (1.0 - abs(mean - 132) / 300.0)
        if s > best_score:
            best, best_score = f, s
    if best:
        return best
    # nothing scored well: fall back to the least-black frame rather than frame 0
    ranked = []
    for f in frames:
        try:
            _, mean, dark = grade(f)
        except Exception:
            continue
        ranked.append((-(dark * 1000) + mean, f))
    return max(ranked)[1] if ranked else (frames[0] if frames else None)


def build(video_id: str, title: str, film: Optional[Path] = None) -> Optional[Path]:
    film = film or _local_film(video_id) or _hf_film(video_id)
    if not film:
        logger.error("no film found for %s", video_id)
        return None
    hero = pick_best(candidate_frames(film))
    if not hero:
        logger.error("no usable frame in %s", film)
        return None
    out = film.parent / "thumbnail.jpg"
    R.compose_thumbnail(str(hero), title, out, channel="BHARAT KI SOCH")
    logger.info("thumbnail rebuilt from %s -> %s", hero.name, out)
    return out


def set_on_youtube(video_id: str, thumb: Path) -> bool:
    from core.configuration import load_config
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from youtube.oauth import YouTubeOAuthManager
    cfg = load_config()
    yt = cfg.youtube
    oauth = YouTubeOAuthManager(getattr(yt, "client_secret_json", ""), getattr(yt, "token_json", ""))
    creds = oauth.get_credentials()
    if not creds:
        logger.error("no YouTube credentials: %s", oauth.last_error)
        return False
    api = build("youtube", "v3", credentials=creds, cache_discovery=False)
    api.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb))).execute()
    logger.info("thumbnail set on %s", video_id)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="thumbnail_tool")
    ap.add_argument("--video-id", required=True, help="film id, e.g. film-6910e004-20261111")
    ap.add_argument("--title", required=True)
    ap.add_argument("--yt-video-id", default="", help="published YouTube id to update")
    ap.add_argument("--set", action="store_true", help="push the new thumbnail to YouTube")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    thumb = build(a.video_id, a.title)
    if not thumb:
        return 1
    print(json.dumps({"thumbnail": str(thumb), "bytes": thumb.stat().st_size}))
    if a.set and a.yt_video_id:
        return 0 if set_on_youtube(a.yt_video_id, thumb) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
