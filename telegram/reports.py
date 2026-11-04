"""Telegram daily production reports and alert formatting."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


class TelegramReportBuilder:
    """Formats Markdown reports for Telegram broadcasts."""

    @staticmethod
    def build_daily_summary(
        completed_videos: List[Dict[str, Any]],
        failed_count: int = 0,
        dry_run: bool = False
    ) -> str:
        now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        mode_badge = "🧪 *DRY-RUN MODE*" if dry_run else "🚀 *PRODUCTION MODE*"

        report = f"""🎬 *YouTube Shorts Daily Report*
📅 {now_str}
⚙️ {mode_badge}

━━━━━━━━━━━━━━━━━━━━━
"""
        if not completed_videos and failed_count == 0:
            report += "ℹ️ No video jobs executed today."
            return report

        for idx, vid in enumerate(completed_videos, 1):
            v_type = vid.get("video_type", "Short").upper()
            title = vid.get("title", "Untitled")
            yt_url = vid.get("youtube_url", "")
            duration = vid.get("duration", 55)
            sources = vid.get("sources", [])

            report += f"*{idx}. [{v_type}]* {title}\n"
            report += f"⏱ Duration: {duration:.1f}s\n"
            if yt_url:
                report += f"🔗 Watch: {yt_url}\n"
            if sources:
                report += f"📚 Sources: {len(sources)} verified links\n"
            report += "\n"

        if failed_count > 0:
            report += f"⚠️ *Failures Encountered:* {failed_count} video(s) failed.\n"
        else:
            report += "✅ All daily shorts rendered and processed successfully!\n"

        return report.strip()

    @staticmethod
    def build_failure_alert(stage: str, video_id: str, error_msg: str) -> str:
        return f"""🚨 *PIPELINE FAILURE ALERT*
Stage: `{stage}`
Video ID: `{video_id}`
Error: `{error_msg}`

Please inspect GitHub Actions run logs.
"""
