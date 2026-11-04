"""Structured logging with sensitive-value masking.

Usage::

    from core.logger import setup_logger, get_logger

    setup_logger("yt_shorts", level=logging.INFO)
    logger = get_logger("yt_shorts.main")
    logger.info("Pipeline started")
"""

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Sensitive-value masking
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(AIza[0-9A-Za-z_-]{35})", re.ASCII),          # Google API key
    re.compile(r"(sk-[A-Za-z0-9]{20,})", re.ASCII),            # OpenAI-style key
    re.compile(r"(gsk_[A-Za-z0-9]{20,})", re.ASCII),           # Groq key
    re.compile(r"(hf_[A-Za-z0-9]{20,})", re.ASCII),            # HuggingFace token
    re.compile(r"(ghp_[A-Za-z0-9]{36})", re.ASCII),            # GitHub PAT
    re.compile(r"(bot\d{8,}:[A-Za-z0-9_-]{35})", re.ASCII),    # Telegram bot token
]

_ENV_SENSITIVE_KEYS = {
    "YT_GEMINI_API_KEY", "YT_GROQ_API_KEY", "YT_TELEGRAM_BOT_TOKEN",
    "YT_PEXELS_API_KEY", "YT_PIXABAY_API_KEY", "YT_HF_TOKEN",
    "YT_MONGODB_URI", "YT_CLOUDFLARE_R2_ACCESS_KEY",
    "YT_CLOUDFLARE_R2_SECRET_KEY", "YT_YOUTUBE_CLIENT_SECRET_JSON",
    "YT_YOUTUBE_TOKEN_JSON", "YT_MISTRAL_API_KEY", "YT_OPENROUTER_API_KEY",
    "YT_NVIDIA_API_KEY", "YT_OLLAMA_API_KEY", "YT_TELEGRAM_CHAT_ID",
}


def _mask(text: str) -> str:
    """Replace known secret patterns with ``***``."""
    for pat in _SENSITIVE_PATTERNS:
        text = pat.sub("***REDACTED***", text)
    for key in _ENV_SENSITIVE_KEYS:
        val = os.environ.get(key, "")
        if len(val) >= 8 and val in text:
            text = text.replace(val, "***REDACTED***")
    return text


class _MaskingFormatter(logging.Formatter):
    """Formatter that scrubs secrets from every log record."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        original = super().format(record)
        return _mask(original)


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------

_LOG_DIR = Path("data/logs")


def setup_logger(
    name: str = "yt_shorts",
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
) -> logging.Logger:
    """Configure the root application logger.

    * Console handler with colours (via :mod:`rich` if available).
    * Rotating file handler under *data/logs/*.
    * Sensitive-value masking on every handler.

    Args:
        name:    Logger name.
        level:   Minimum log level.
        log_dir: Override the default log directory.

    Returns:
        Configured :class:`logging.Logger`.
    """
    log_path = log_dir or _LOG_DIR
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Configure the ROOT logger so every module logger (agents.*, video.*, core.*) is visible.
    root = logging.getLogger()
    root.setLevel(level)
    for noisy in ("urllib3", "googleapiclient", "PIL", "asyncio", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if root.handlers and any(getattr(h, "_yt", False) for h in root.handlers):
        return logger  # already initialised

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Console ---------------------------------------------------------------
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_MaskingFormatter(fmt, datefmt=datefmt))
    console._yt = True
    root.addHandler(console)

    # File ------------------------------------------------------------------
    file_handler = RotatingFileHandler(
        log_path / f"{name}.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_MaskingFormatter(fmt, datefmt=datefmt))
    file_handler._yt = True
    root.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger. Call :func:`setup_logger` first."""
    return logging.getLogger(name)
