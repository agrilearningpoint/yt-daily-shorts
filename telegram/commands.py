"""Telegram Bot Command Router and Handlers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from telegram.reports import TelegramReportBuilder

logger = logging.getLogger("telegram.commands")


class CommandDispatcher:
    """Dispatches user bot commands for remote management."""

    def __init__(self, authorized_ids: List[str]):
        self.authorized_ids = authorized_ids

    def is_authorized(self, user_id: str) -> bool:
        if not self.authorized_ids:
            return True
        return str(user_id) in self.authorized_ids

    def handle_command(self, command: str, user_id: str, context_data: Dict[str, Any]) -> str:
        """Route command and return reply text."""
        if not self.is_authorized(user_id):
            return "⛔ Unauthorized. You do not have permission to manage this bot."

        cmd = command.strip().lower().split()[0]
        if cmd in ("/start", "/help"):
            return (
                "🤖 *YouTube Shorts Automation Bot*\n\n"
                "Available Commands:\n"
                "/status - Pipeline state and recent jobs\n"
                "/news - Recent collected news stories\n"
                "/scripts - Today's generated Hindi scripts\n"
                "/videos - Rendered video files\n"
                "/analytics - YouTube performance metrics\n"
                "/topics - 7-day editorial calendar\n"
                "/retry - Re-trigger failed video tasks"
            )
        elif cmd == "/status":
            videos = context_data.get("videos", [])
            return TelegramReportBuilder.build_daily_summary(videos)
        elif cmd == "/news":
            news = context_data.get("news", [])
            if not news:
                return "ℹ️ No recent news collected yet."
            msg = "📰 *Latest Verified Stories:*\n"
            for n in news[:5]:
                msg += f"• {n.get('title')} ({n.get('source_name')})\n"
            return msg
        elif cmd == "/topics":
            return (
                "📅 *7-Day Editorial Schedule:*\n"
                "• Mon: Indian Politics & Political Leaders\n"
                "• Tue: Science & Technology\n"
                "• Wed: Medical Science & Research\n"
                "• Thu: Great Personalities & Biographies\n"
                "• Fri: Indian History, Monuments & Heritage\n"
                "• Sat: Inventions & Discoveries\n"
                "• Sun: Economy, Society & World Affairs"
            )
        else:
            return f"Unknown command: {cmd}. Type /help for options."
