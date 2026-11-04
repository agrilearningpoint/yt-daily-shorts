"""Telegram report formatting (HTML)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import pytz

from telegram.bot import esc


def _now_ist() -> str:
    return datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")


class TelegramReportBuilder:
    @staticmethod
    def build_daily_summary(completed_videos: List[Dict[str, Any]], failed_count: int = 0,
                            dry_run: bool = False, failures: List[str] = None, insights: str = "") -> str:
        mode = "🧪 <b>DRY-RUN</b> (upload skipped)" if dry_run else "🚀 <b>LIVE</b>"
        out = [f"🎬 <b>YT Shorts Report</b>", f"📅 {_now_ist()}", f"⚙️ {mode}", "━━━━━━━━━━━━"]
        if not completed_videos and failed_count == 0:
            out.append("ℹ️ No video jobs executed.")
            return "\n".join(out)
        for i, v in enumerate(completed_videos, 1):
            out.append(f"<b>{i}. [{esc(str(v.get('video_type', '')).upper())}]</b> {esc(v.get('title', ''))}")
            out.append(f"⏱ {float(v.get('duration', 0) or 0):.1f}s | 📰 {v.get('items', 0)} items | 🖼 {v.get('images', 0)} photos")
            out.append(f"🧠 {esc(v.get('llm', ''))} | 🎙 {esc(v.get('voice', ''))}")
            if v.get("youtube_url"):
                out.append(f"🔗 {esc(v['youtube_url'])}")
            if v.get("sources"):
                out.append(f"📚 {len(v['sources'])} sources")
            out.append("")
        if failed_count:
            out.append(f"⚠️ <b>{failed_count} failed</b>")
            for f in (failures or [])[:5]:
                out.append(f"• {esc(f[:300])}")
        else:
            out.append("✅ All videos processed successfully.")
        if insights:
            out.append(f"\n📈 {esc(insights)}")
        return "\n".join(out).strip()

    @staticmethod
    def build_failure_alert(stage: str, video_id: str, error_msg: str) -> str:
        return (f"🚨 <b>PIPELINE FAILURE</b>\nStage: <code>{esc(stage)}</code>\nVideo: <code>{esc(video_id)}</code>\n"
                f"Error: <code>{esc(error_msg[:800])}</code>\n\nNothing was published for this video.")
