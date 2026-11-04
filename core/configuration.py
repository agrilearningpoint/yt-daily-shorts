"""Application configuration with environment-variable overrides.

The hierarchy (highest priority first):

1. Environment variables prefixed with ``YT_``.
2. ``config/settings.local.yaml`` (gitignored).
3. ``config/settings.yaml`` (committed defaults).

Usage::

    from core.configuration import load_config
    cfg = load_config()
    print(cfg.general.timezone)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GeneralConfig:
    project_name: str = "yt-daily-shorts"
    timezone: str = "Asia/Kolkata"
    daily_video_count: int = 2
    max_video_count: int = 3
    dry_run: bool = True
    debug: bool = False


@dataclass
class LLMConfig:
    provider: str = "gemini"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    model_name: str = "gemini-2.0-flash"
    temperature: float = 0.7
    max_tokens: int = 8192


@dataclass
class TTSConfig:
    provider: str = "edge-tts"
    voice: str = "hi-IN-SwaraNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"


@dataclass
class VideoConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    target_duration: int = 55
    max_duration: int = 60
    output_format: str = "mp4"
    quality: str = "high"


@dataclass
class YouTubeConfig:
    client_secret_json: str = ""
    token_json: str = ""
    default_privacy: str = "private"
    category_id: str = "22"
    dry_run: bool = True


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""
    authorized_user_ids: List[str] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    provider: str = "sqlite"
    sqlite_path: str = "data/yt_shorts.db"
    mongodb_uri: str = ""


@dataclass
class MediaConfig:
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    hf_token: str = ""
    cache_dir: str = "data/media_cache"


@dataclass
class SEOConfig:
    max_title_length: int = 100
    max_description_length: int = 5000
    default_hashtags: List[str] = field(default_factory=lambda: [
        "#shorts", "#hindi", "#news", "#facts",
        "#india", "#knowledge", "#dailynews",
    ])


@dataclass
class EditorialCalendar:
    monday: str = "Indian Politics and Political Leaders"
    tuesday: str = "Science and Technology"
    wednesday: str = "Medical Science and Scientific Research"
    thursday: str = "Great Personalities and Biographies"
    friday: str = "Indian History, Monuments, Temples and Heritage"
    saturday: str = "Interesting Facts, Inventions and Discoveries"
    sunday: str = "Economy, Society and World Affairs"

    def get_today_category(self, day_name: str) -> str:
        """Return the editorial category for a given day name."""
        return getattr(self, day_name.lower(), "General Knowledge")


@dataclass
class AppConfig:
    """Top-level application configuration container."""
    general: GeneralConfig = field(default_factory=GeneralConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    seo: SEOConfig = field(default_factory=SEOConfig)
    editorial_calendar: EditorialCalendar = field(default_factory=EditorialCalendar)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SETTINGS = _PROJECT_ROOT / "config" / "settings.yaml"
_LOCAL_SETTINGS = _PROJECT_ROOT / "config" / "settings.local.yaml"

_ENV_MAP: Dict[str, tuple[str, str]] = {
    # env var → (section, field)
    "YT_GEMINI_API_KEY":       ("llm", "gemini_api_key"),
    "YT_GROQ_API_KEY":         ("llm", "groq_api_key"),
    "YT_LLM_PROVIDER":        ("llm", "provider"),
    "YT_LLM_MODEL":           ("llm", "model_name"),
    "YT_TTS_PROVIDER":        ("tts", "provider"),
    "YT_TTS_VOICE":           ("tts", "voice"),
    "YT_TELEGRAM_BOT_TOKEN":  ("telegram", "bot_token"),
    "YT_TELEGRAM_CHAT_ID":    ("telegram", "chat_id"),
    "YT_YOUTUBE_CLIENT_SECRET_JSON": ("youtube", "client_secret_json"),
    "YT_YOUTUBE_TOKEN_JSON":  ("youtube", "token_json"),
    "YT_PEXELS_API_KEY":      ("media", "pexels_api_key"),
    "YT_PIXABAY_API_KEY":     ("media", "pixabay_api_key"),
    "YT_HF_TOKEN":            ("media", "hf_token"),
    "YT_MONGODB_URI":         ("database", "mongodb_uri"),
    "YT_CLOUDFLARE_R2_ACCESS_KEY": ("media", "r2_access_key"),
    "YT_CLOUDFLARE_R2_SECRET_KEY": ("media", "r2_secret_key"),
    "YT_DRY_RUN":             ("general", "dry_run"),
    "YT_DEBUG":                ("general", "debug"),
    "YT_TIMEZONE":             ("general", "timezone"),
    "YT_SQLITE_PATH":         ("database", "sqlite_path"),
}


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Read a YAML file; return empty dict if missing."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _apply_yaml(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Overlay *data* from a YAML file onto *cfg*."""
    section_map = {
        "general": cfg.general,
        "llm": cfg.llm,
        "tts": cfg.tts,
        "video": cfg.video,
        "youtube": cfg.youtube,
        "telegram": cfg.telegram,
        "database": cfg.database,
        "media": cfg.media,
        "seo": cfg.seo,
        "editorial_calendar": cfg.editorial_calendar,
    }
    for section_key, section_data in data.items():
        target = section_map.get(section_key)
        if target is None or not isinstance(section_data, dict):
            continue
        for field_key, value in section_data.items():
            if hasattr(target, field_key):
                current = getattr(target, field_key)
                # Coerce booleans from YAML string "true"/"false"
                if isinstance(current, bool) and isinstance(value, str):
                    value = value.lower() in ("true", "1", "yes")
                setattr(target, field_key, value)


def _apply_env(cfg: AppConfig) -> None:
    """Override config fields from environment variables."""
    section_map = {
        "general": cfg.general,
        "llm": cfg.llm,
        "tts": cfg.tts,
        "video": cfg.video,
        "youtube": cfg.youtube,
        "telegram": cfg.telegram,
        "database": cfg.database,
        "media": cfg.media,
        "seo": cfg.seo,
    }
    for env_key, (section, field_name) in _ENV_MAP.items():
        value = os.environ.get(env_key)
        if value is None:
            continue
        target = section_map.get(section)
        if target is None:
            continue
        if not hasattr(target, field_name):
            continue
        current = getattr(target, field_name)
        if isinstance(current, bool):
            setattr(target, field_name, value.lower() in ("true", "1", "yes"))
        elif isinstance(current, int):
            try:
                setattr(target, field_name, int(value))
            except ValueError:
                pass
        elif isinstance(current, float):
            try:
                setattr(target, field_name, float(value))
            except ValueError:
                pass
        else:
            setattr(target, field_name, value)


def validate_config(cfg: AppConfig) -> List[str]:
    """Return a list of configuration warnings (not errors for optional keys)."""
    warnings: List[str] = []
    if not cfg.llm.gemini_api_key and not cfg.llm.groq_api_key:
        warnings.append("No LLM API key configured (GEMINI or GROQ). LLM features will fail.")
    if not cfg.telegram.bot_token:
        warnings.append("Telegram bot token not set. Notifications disabled.")
    if cfg.video.width != 1080 or cfg.video.height != 1920:
        warnings.append(f"Non-standard resolution {cfg.video.width}x{cfg.video.height}.")
    return warnings


def load_config() -> AppConfig:
    """Build the application configuration.

    Loads defaults → settings.yaml → settings.local.yaml → env vars.
    """
    load_dotenv()  # load .env if present

    cfg = AppConfig()

    # Layer 1: committed defaults
    _apply_yaml(cfg, _load_yaml(_DEFAULT_SETTINGS))

    # Layer 2: local overrides (gitignored)
    _apply_yaml(cfg, _load_yaml(_LOCAL_SETTINGS))

    # Layer 3: environment variables (highest priority)
    _apply_env(cfg)

    return cfg
