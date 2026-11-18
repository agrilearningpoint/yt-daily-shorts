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
        if Path(video_path).stat().st_size > 50 * 1024 * 1024:
            logger.info("Video too large for Telegram bot upload; skipped.")
            return False
        files = {}
        try:
            files["video"] = open(video_path, "rb")
            if thumb_path and Path(thumb_path).exists():
                files["thumbnail"] = open(thumb_path, "rb")
            data = {"chat_id": self.chat_id, "caption": caption[:1000], "parse_mode": "HTML",
                    "supports_streaming": "true", "width": 1080, "height": 1920}
            resp = requests.post(self._api("sendVideo"), data=data, files=files, timeout=180)
            if resp.status_code != 200:
                logger.warning("Telegram sendVideo %s: %s", resp.status_code, resp.text[:200])
                # Fallback to sendDocument
                for f in files.values():
                    f.seek(0)
                doc_files = {"document": files["video"]}
                if "thumbnail" in files:
                    doc_files["thumbnail"] = files["thumbnail"]
                resp = requests.post(self._api("sendDocument"), data={"chat_id": self.chat_id, "caption": caption[:1000]}, files=doc_files, timeout=180)
                if resp.status_code != 200:
                    logger.warning("Telegram sendDocument fallback %s: %s", resp.status_code, resp.text[:200])
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Telegram sendVideo failed: %s", exc)
            return False
        finally:
            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass


if __name__ == "__main__":
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description="Send video or message to Telegram")
    parser.add_argument("--video", type=str, help="Path to video file")
    parser.add_argument("--caption", type=str, default="", help="Video caption")
    parser.add_argument("--thumb", type=str, default=None, help="Path to thumbnail")
    parser.add_argument("--message", type=str, default="", help="Text message to send")
    parser.add_argument("--token", type=str, default="", help="Bot token (or env YT_TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--chat-id", type=str, default="", help="Chat ID (or env YT_TELEGRAM_CHAT_ID)")
    args = parser.parse_args()

    token = args.token or os.environ.get("YT_TELEGRAM_BOT_TOKEN", "")
    chat_id = args.chat_id or os.environ.get("YT_TELEGRAM_CHAT_ID", "-1003886311757")
    notifier = TelegramNotifier(token, chat_id)
    if not notifier.enabled:
        print("Error: bot_token or chat_id is missing.")
        sys.exit(1)
    if args.video:
        ok = notifier.send_video(args.video, caption=args.caption, thumb_path=args.thumb)
        print("Video sent successfully" if ok else "Failed to send video")
        sys.exit(0 if ok else 1)
    elif args.message:
        ok = notifier.send_message(args.message)
        print("Message sent successfully" if ok else "Failed to send message")
        sys.exit(0 if ok else 1)
