"""CLI: python -m longform --topic "हिंदू धर्म" --minutes 22 --chapters 9 --upload"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from core.configuration import load_config
from core.logger import setup_logger


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="longform", description="Long-form documentary pipeline")
    p.add_argument("--topic", required=True, help="film topic (Hindi or English)")
    p.add_argument("--angle", default="", help="the specific promise of the film")
    p.add_argument("--minutes", type=int, default=22)
    p.add_argument("--chapters", type=int, default=9)
    p.add_argument("--upload", action="store_true", help="upload to YouTube")
    p.add_argument("--privacy", default="unlisted", choices=["unlisted", "private", "public"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rebuild-visuals", action="store_true",
                   help="re-fetch visuals and re-render chapters (keeps the script)")
    return p.parse_args()


async def main() -> int:
    args = parse()
    setup_logger("longform", level=logging.INFO)
    log = logging.getLogger("longform")
    cfg = load_config()
    if args.dry_run:
        cfg.set_dry_run(True)
    from longform.pipeline import LongFormPipeline

    pipe = LongFormPipeline(cfg)
    res = await pipe.run(topic=args.topic, angle=args.angle, minutes=args.minutes,
                         chapters=args.chapters, upload=args.upload, privacy=args.privacy,
                         rebuild_visuals=args.rebuild_visuals)
    log.info("=== DONE ===")
    print(f"\nfile      : {res['path']}")
    print(f"duration  : {res['duration_sec'] / 60:.1f} min")
    print(f"thumbnail : {res['thumbnail']}")
    if res.get("url"):
        print(f"url       : {res['url']}")
    if res.get("upload_error"):
        print(f"upload err: {res['upload_error']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
