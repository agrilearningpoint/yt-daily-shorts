"""Data access repositories with async SQLite support.

Each repository provides CRUD operations for its table(s).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _BaseRepository:
    """Shared connection helper."""

    def __init__(self, db_path: str = "data/yt_shorts.db") -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn


class VideoRepository(_BaseRepository):
    """CRUD for the ``videos`` table."""

    def insert(self, video_id: str, video_type: str, topic_category: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO videos (id, video_type, topic_category, created_at) "
            "VALUES (?, ?, ?, ?)",
            (video_id, video_type, topic_category, _now()),
        )
        conn.commit()
        conn.close()

    def update_status(self, video_id: str, status: str) -> None:
        conn = self._conn()
        conn.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))
        conn.commit()
        conn.close()

    def get(self, video_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_by_status(self, status: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM videos WHERE status = ?", (status,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_today(self) -> List[Dict[str, Any]]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM videos WHERE created_at LIKE ?", (f"{today}%",)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class ResearchRepository(_BaseRepository):
    """CRUD for the ``research`` table."""

    def insert(
        self,
        video_id: str,
        source_url: str,
        title: str = "",
        summary: str = "",
        source_name: str = "",
    ) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO research (video_id, source_url, title, content_summary, "
            "collected_at, source_name) VALUES (?, ?, ?, ?, ?, ?)",
            (video_id, source_url, title, summary, _now(), source_name),
        )
        conn.commit()
        conn.close()

    def get_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM research WHERE video_id = ?", (video_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class AnalyticsRepository(_BaseRepository):
    """CRUD for the ``analytics`` table."""

    def insert(
        self, video_id: str, views: int = 0, likes: int = 0, comments: int = 0
    ) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO analytics (video_id, views, likes, comments, collected_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (video_id, views, likes, comments, _now()),
        )
        conn.commit()
        conn.close()

    def get_latest(self, video_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM analytics WHERE video_id = ? ORDER BY collected_at DESC LIMIT 1",
            (video_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
