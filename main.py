"""YT Daily Shorts — AI-Powered YouTube Shorts Automation Platform.

Entry point for scheduled runs and manual triggers.

Usage::

    python main.py
    python main.py --video-type news
    python main.py --video-type knowledge --dry-run
    python main.py --status
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8 / emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.configuration import load_config, validate_config
from core.logger import get_logger, setup_logger
from core.orchestrator import DailyOrchestrator
from core.state_manager import StateManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YT Daily Shorts — AI-Powered Automated YouTube Shorts in Hindi"
    )
    parser.add_argument(
        "--video-type",
        choices=["all", "news", "knowledge"],
        default="all",
        help="Specify which video type to generate today (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Run without uploading to YouTube or making billable API calls",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display today's pipeline status and recent videos",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default="",
        help="Resume pipeline for a specific failed video_id from last checkpoint",
    )
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()

    # 1. Setup Logging
    setup_logger("yt_shorts", level=logging.INFO)
    logger = get_logger("yt_shorts.cli")
    logger.info("Initializing YT Daily Shorts Automation System...")

    # 2. Load Configuration
    config = load_config()
    if args.dry_run is not None:
        config.general.dry_run = args.dry_run
        config.youtube.dry_run = args.dry_run

    warnings = validate_config(config)
    for w in warnings:
        logger.warning("Config Notice: %s", w)

    # 3. Handle Status Query
    state_mgr = StateManager(config.database.sqlite_path)
    if args.status:
        today_videos = state_mgr.get_today_videos()
        print("\n" + "=" * 60)
        print("[STATUS] TODAY'S VIDEO PRODUCTION STATUS")
        print("=" * 60)
        if not today_videos:
            print("No video production runs recorded for today.")
        for v in today_videos:
            print(f"[{v.state.value.upper()}] ID: {v.video_id} | Type: {v.video_type} | Title: {v.title}")
            if v.youtube_url:
                print(f"   URL: {v.youtube_url}")
            if v.error_message:
                print(f"   Error: {v.error_message}")
        print("=" * 60 + "\n")
        return 0

    orchestrator = DailyOrchestrator(config, state_mgr)

    # 4. Handle Resume
    if args.resume:
        logger.info("Resuming video pipeline for ID: %s", args.resume)
        vs = await orchestrator.resume_pipeline(args.resume)
        return 0 if vs and vs.state.value == "completed" else 1

    # 5. Execute Daily Pipeline
    results = await orchestrator.run_daily(video_type_filter=args.video_type)
    any_failed = any(r.state.value == "failed" for r in results)

    return 1 if any_failed else 0


def main():
    try:
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
