"""Telegram notifications (HTML parse mode, safe escaping) + video preview upload."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("telegram.bot")


def esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _api(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            logger.info("Telegram not configured; skipped.")
            return False
        for chunk_start in range(0, len(text), 3900):
            payload = {"chat_id": self.chat_id, "text": text[chunk_start:chunk_start + 3900],
                       "parse_mode": parse_mode, "disable_web_page_preview": True}
            try:
                resp = requests.post(self._api("sendMessage"), json=payload, timeout=15)
                if resp.status_code != 200:
                    # retry without formatting so the alert always arrives
                    payload.pop("parse_mode", None)
                    resp = requests.post(self._api("sendMessage"), json=payload, timeout=15)
                if resp.status_code != 200:
                    logger.warning("Telegram error %s: %s", resp.status_code, resp.text[:200])
                    return False
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)
                return False
        return True

    def send_video(self, video_path: str, caption: str = "", thumb_path: Optional[str] = None) -> bool:
        if not self.enabled or not Path(video_path).exists():
            return False
        if Path(video_path).stat().st_size > 48 * 1024 * 1024:
            logger.info("Video too large for Telegram bot upload; skipped.")
            return False
        try:
            files = {"video": open(video_path, "rb")}
            if thumb_path and Path(thumb_path).exists():
                files["thumbnail"] = open(thumb_path, "rb")
            data = {"chat_id": self.chat_id, "caption": caption[:1000], "parse_mode": "HTML",
                    "supports_streaming": "true", "width": 1080, "height": 1920}
            resp = requests.post(self._api("sendVideo"), data=data, files=files, timeout=180)
            for f in files.values():
                f.close()
            if resp.status_code != 200:
                logger.warning("Telegram sendVideo %s: %s", resp.status_code, resp.text[:200])
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Telegram sendVideo failed: %s", exc)
            return False
