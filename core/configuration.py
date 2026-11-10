"""Application configuration with environment-variable overrides.

Priority (highest first):

1. Environment variables prefixed with ``YT_`` (GitHub Actions secrets).
2. ``config/settings.local.yaml`` (gitignored).
3. ``config/settings.yaml`` (committed defaults).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv


@dataclass
class GeneralConfig:
    project_name: str = "yt-daily-shorts"
    channel_name: str = "BHARAT KI SOCH"
    channel_name_spoken: str = "भारत की सोच"
    timezone: str = "Asia/Kolkata"
    daily_video_count: int = 2
    max_video_count: int = 3
    dry_run: bool = True
    # strict_mode: never publish placeholder content (mock LLM, silent audio,
    # fake MP4). Automatically ON for live (non dry-run) runs.
    strict_mode: bool = False
    debug: bool = False


@dataclass
class LLMConfig:
    # Providers are tried in this order; any provider without a key is skipped.
    provider_order: List[str] = field(default_factory=lambda: [
        "gemini", "groq", "nvidia", "mistral", "openrouter", "ollama",
    ])
    models: Dict[str, List[str]] = field(default_factory=dict)
    gemini_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""
    nvidia_api_key: str = ""
    ollama_api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_sec: int = 90
    allow_mock: bool = False  # only tests / offline dev

    def keys(self) -> Dict[str, str]:
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "mistral": self.mistral_api_key,
            "openrouter": self.openrouter_api_key,
            "nvidia": self.nvidia_api_key,
            "ollama": self.ollama_api_key,
        }

    def has_any_key(self) -> bool:
        return any(v for v in self.keys().values())


@dataclass
class TTSConfig:
    provider: str = "edge-tts"
    voice: str = "hi-IN-MadhurNeural"
    fallback_voice: str = "hi-IN-SwaraNeural"
    rate: str = "+8%"
    pitch: str = "+0Hz"
    provider_order: List[str] = field(default_factory=lambda: ["gemini", "edge"])
    gemini_models: List[str] = field(default_factory=lambda: [
        "gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-2.5-flash-preview-tts"])
    gemini_voice: str = "auto"
    gemini_fallback_voice: str = "Charon"
    news_style: str = "energetic, confident Hindi TV news anchor, fast crisp delivery"
    knowledge_style: str = "warm, curious Hindi storyteller, natural conversational pace"


@dataclass
class VideoConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    target_duration: int = 52
    min_duration: int = 25
    max_duration: int = 59
    news_max_duration: int = 140
    news_target_duration: int = 120
    news_national_count: int = 16
    news_international_count: int = 4
    output_format: str = "mp4"
    quality: str = "high"
    background_music: bool = True
    music_volume: float = 0.10
    news_headline_count: int = 20
    show_headline_chips: bool = True
    burn_captions: bool = True        # word-synced Hindi captions (audit 2026-11-08)
    depth_motion: bool = True         # real news photos play with 3D depth motion (2026-11-10)
    sound_effects: bool = True


@dataclass
class YouTubeConfig:
    client_secret_json: str = ""
    token_json: str = ""
    default_privacy: str = "public"
    category_id: str = "27"
    news_category_id: str = "25"
    knowledge_category_id: str = "27"
    contains_synthetic_media: bool = True
    dry_run: bool = True


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""
    send_video: bool = True
    authorized_user_ids: List[str] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    provider: str = "sqlite"
    sqlite_path: str = "data/yt_shorts.db"
    history_path: str = "data/history.json"
    mongodb_uri: str = ""


@dataclass
class MediaConfig:
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    hf_token: str = ""
    agnes_api_key: str = ""
    agnes_model: str = "agnes-image-2.5-flash"
    use_publisher_images: bool = True    # story's own RSS photo (owner chose real news photos, 2026-11-08)
    use_news_photos: bool = True         # real photo of the same event from the latest news articles (Bing News)
    cf_api_token: str = ""               # Cloudflare Workers AI (free FLUX images) - backup AI artist
    cf_account_id: str = ""
    vision_check: bool = True            # Gemini looks at stock/commons photos and rejects unrelated ones
    use_openverse: bool = True
    use_wikimedia: bool = True
    cache_dir: str = "data/media_cache"
    r2_access_key: str = ""
    r2_secret_key: str = ""


@dataclass
class SEOConfig:
    max_title_length: int = 100
    max_description_length: int = 5000
    default_hashtags: List[str] = field(default_factory=lambda: [
        "#shorts", "#hindi", "#facts", "#india", "#knowledge",
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
        return getattr(self, day_name.lower(), "General Knowledge")


@dataclass
class AppConfig:
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

    def set_dry_run(self, value: bool) -> None:
        self.general.dry_run = value
        self.youtube.dry_run = value
        if not value:
            self.general.strict_mode = True


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SETTINGS = _PROJECT_ROOT / "config" / "settings.yaml"
_LOCAL_SETTINGS = _PROJECT_ROOT / "config" / "settings.local.yaml"

_ENV_MAP: Dict[str, tuple] = {
    "YT_GEMINI_API_KEY": ("llm", "gemini_api_key"),
    "YT_GROQ_API_KEY": ("llm", "groq_api_key"),
    "YT_MISTRAL_API_KEY": ("llm", "mistral_api_key"),
    "YT_OPENROUTER_API_KEY": ("llm", "openrouter_api_key"),
    "YT_NVIDIA_API_KEY": ("llm", "nvidia_api_key"),
    "YT_OLLAMA_API_KEY": ("llm", "ollama_api_key"),
    "YT_TTS_VOICE": ("tts", "voice"),
    "YT_TELEGRAM_BOT_TOKEN": ("telegram", "bot_token"),
    "YT_TELEGRAM_CHAT_ID": ("telegram", "chat_id"),
    "YT_YOUTUBE_CLIENT_SECRET_JSON": ("youtube", "client_secret_json"),
    "YT_YOUTUBE_TOKEN_JSON": ("youtube", "token_json"),
    "YT_YOUTUBE_PRIVACY": ("youtube", "default_privacy"),
    "YT_PEXELS_API_KEY": ("media", "pexels_api_key"),
    "YT_PIXABAY_API_KEY": ("media", "pixabay_api_key"),
    "YT_AGNES_API_KEY": ("media", "agnes_api_key"),
    "YT_CF_API_TOKEN": ("media", "cf_api_token"),
    "YT_CF_ACCOUNT_ID": ("media", "cf_account_id"),
    "YT_HF_TOKEN": ("media", "hf_token"),
    "YT_MONGODB_URI": ("database", "mongodb_uri"),
    "YT_CLOUDFLARE_R2_ACCESS_KEY": ("media", "r2_access_key"),
    "YT_CLOUDFLARE_R2_SECRET_KEY": ("media", "r2_secret_key"),
    "YT_DRY_RUN": ("general", "dry_run"),
    "YT_STRICT_MODE": ("general", "strict_mode"),
    "YT_DEBUG": ("general", "debug"),
    "YT_TIMEZONE": ("general", "timezone"),
    "YT_CHANNEL_NAME": ("general", "channel_name"),
    "YT_DAILY_VIDEO_COUNT": ("general", "daily_video_count"),
    "YT_SQLITE_PATH": ("database", "sqlite_path"),
}


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _sections(cfg: AppConfig) -> Dict[str, Any]:
    return {
        "general": cfg.general, "llm": cfg.llm, "tts": cfg.tts, "video": cfg.video,
        "youtube": cfg.youtube, "telegram": cfg.telegram, "database": cfg.database,
        "media": cfg.media, "seo": cfg.seo, "editorial_calendar": cfg.editorial_calendar,
    }


def _coerce(current: Any, value: Any) -> Any:
    if isinstance(current, bool):
        return value if isinstance(value, bool) else str(value).strip().lower() in ("true", "1", "yes", "on")
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return current
    if isinstance(current, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return current
    return value


def _apply_yaml(cfg: AppConfig, data: Dict[str, Any]) -> None:
    sections = _sections(cfg)
    for section_key, section_data in data.items():
        target = sections.get(section_key)
        if target is None or not isinstance(section_data, dict):
            continue
        for key, value in section_data.items():
            if hasattr(target, key):
                setattr(target, key, _coerce(getattr(target, key), value))


def _apply_env(cfg: AppConfig) -> None:
    sections = _sections(cfg)
    for env_key, (section, name) in _ENV_MAP.items():
        value = os.environ.get(env_key)
        if value is None or value == "":
            continue
        target = sections[section]
        setattr(target, name, _coerce(getattr(target, name), value.strip()))
    # Keep the two dry-run flags in lock-step.
    cfg.youtube.dry_run = cfg.general.dry_run
    if not cfg.general.dry_run:
        cfg.general.strict_mode = True


def validate_config(cfg: AppConfig) -> List[str]:
    warnings: List[str] = []
    if not cfg.llm.has_any_key():
        warnings.append("No LLM API key configured. Live runs will fail (strict mode).")
    if not cfg.telegram.bot_token:
        warnings.append("Telegram bot token not set. Notifications disabled.")
    if not cfg.general.dry_run and not cfg.youtube.token_json:
        warnings.append("YOUTUBE_TOKEN_JSON missing: uploads cannot happen. Run scripts/get_youtube_token.py once.")
    if not cfg.media.pexels_api_key and not cfg.media.pixabay_api_key:
        warnings.append("No Pexels/Pixabay key: using Wikimedia/Openverse + designed cards for visuals.")
    return warnings


def load_config() -> AppConfig:
    load_dotenv()
    cfg = AppConfig()
    _apply_yaml(cfg, _load_yaml(_DEFAULT_SETTINGS))
    _apply_yaml(cfg, _load_yaml(_LOCAL_SETTINGS))
    _apply_env(cfg)
    return cfg
