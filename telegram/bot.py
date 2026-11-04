"""Telegram notification client using Telegram Bot API."""

from __future__ import annotations

import logging
from typing import Optional
import requests

logger = logging.getLogger("telegram.bot")


class TelegramNotifier:
    """Dispatches notifications and reports to authorized Telegram chat."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message via Telegram Bot API."""
        if not self.bot_token or not self.chat_id:
            logger.info("Telegram token or chat_id not configured. Notification skipped.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram notification sent successfully.")
                return True
            else:
                logger.warning("Telegram API error %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Failed to send Telegram notification: %s", exc)

        return False
