"""SQLite schema definitions and migration support.

Usage::

    from database.schema import init_database
    init_database("data/yt_shorts.db")
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL = """
-- ============================================================
-- YT Daily Shorts — Database Schema v1
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS videos (
    id              TEXT PRIMARY KEY,
    video_type      TEXT NOT NULL,          -- "news" | "knowledge"
    topic_category  TEXT DEFAULT '',
    title           TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    published_at    TEXT DEFAULT '',
    youtube_id      TEXT DEFAULT '',
    youtube_url     TEXT DEFAULT '',
    thumbnail_url   TEXT DEFAULT '',
    file_path       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scripts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT NOT NULL REFERENCES videos(id),
    hook            TEXT DEFAULT '',
    body_json       TEXT DEFAULT '[]',      -- JSON array of scenes
    duration_estimate REAL DEFAULT 0.0,
    language        TEXT DEFAULT 'hi',
    approved        INTEGER DEFAULT 0,
    quality_score   REAL DEFAULT 0.0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT NOT NULL REFERENCES videos(id),
    source_url      TEXT NOT NULL,
    title           TEXT DEFAULT '',
    content_summary TEXT DEFAULT '',
    collected_at    TEXT NOT NULL,
    verified        INTEGER DEFAULT 0,
    source_name     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    source_type     TEXT NOT NULL,          -- "rss" | "api" | "web"
    reliability_score REAL DEFAULT 0.8,
    last_accessed   TEXT DEFAULT '',
    active          INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS analytics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT NOT NULL REFERENCES videos(id),
    views           INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    watch_time_sec  REAL DEFAULT 0.0,
    collected_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS creative_variations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT NOT NULL REFERENCES videos(id),
    theme           TEXT DEFAULT '',
    transitions     TEXT DEFAULT '',        -- JSON array
    music_mood      TEXT DEFAULT '',
    color_palette   TEXT DEFAULT '',        -- JSON array
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT NOT NULL REFERENCES videos(id),
    asset_type      TEXT NOT NULL,          -- "image" | "video" | "audio"
    source_url      TEXT DEFAULT '',
    local_path      TEXT DEFAULT '',
    license_type    TEXT DEFAULT 'unknown',
    attribution     TEXT DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at);
CREATE INDEX IF NOT EXISTS idx_scripts_video ON scripts(video_id);
CREATE INDEX IF NOT EXISTS idx_research_video ON research(video_id);
CREATE INDEX IF NOT EXISTS idx_analytics_video ON analytics(video_id);
"""


def init_database(db_path: str = "data/yt_shorts.db") -> None:
    """Initialise the database, creating tables if they don't exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.executescript(DDL)

    # Record schema version
    cur = conn.execute("SELECT version FROM schema_version")
    row = cur.fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
    conn.commit()
    conn.close()
