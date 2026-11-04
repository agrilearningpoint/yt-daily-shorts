"""Pipeline state management with SQLite persistence and checkpoint support.

Allows the orchestrator to track each video through the pipeline,
save intermediate results, and resume from the last successful stage
after a failure.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PipelineState(str, Enum):
    """Stages a video moves through."""
    PENDING = "pending"
    RESEARCHING = "researching"
    SCRIPTING = "scripting"
    VERIFYING = "verifying"
    PRODUCING = "producing"
    RENDERING = "rendering"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VideoState:
    """Runtime representation of a video's pipeline state."""
    video_id: str
    video_type: str  # "news" | "knowledge"
    state: PipelineState = PipelineState.PENDING
    topic_category: str = ""
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    youtube_id: str = ""
    youtube_url: str = ""


class StateManager:
    """Thread-safe SQLite-backed state manager.

    Args:
        db_path: Path to the SQLite database file.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS video_states (
        video_id       TEXT PRIMARY KEY,
        video_type     TEXT NOT NULL,
        state          TEXT NOT NULL DEFAULT 'pending',
        topic_category TEXT DEFAULT '',
        title          TEXT DEFAULT '',
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL,
        checkpoint_data TEXT DEFAULT '{}',
        error_message  TEXT DEFAULT '',
        youtube_id     TEXT DEFAULT '',
        youtube_url    TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS checkpoints (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id   TEXT NOT NULL,
        stage      TEXT NOT NULL,
        data_json  TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(video_id, stage)
    );
    CREATE TABLE IF NOT EXISTS agent_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name  TEXT NOT NULL,
        video_id    TEXT DEFAULT '',
        action      TEXT NOT NULL,
        result_json TEXT DEFAULT '{}',
        error       TEXT DEFAULT '',
        timestamp   TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str = "data/yt_shorts.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._conn()
            conn.executescript(self._DDL)
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Video state CRUD
    # ------------------------------------------------------------------

    def create_video_state(
        self,
        video_type: str,
        topic_category: str = "",
        video_id: Optional[str] = None,
    ) -> VideoState:
        """Insert a new video state and return it."""
        vid = video_id or uuid.uuid4().hex[:12]
        now = self._now()
        vs = VideoState(
            video_id=vid,
            video_type=video_type,
            topic_category=topic_category,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            conn = self._conn()
            conn.execute(
                """INSERT INTO video_states
                   (video_id, video_type, state, topic_category, title,
                    created_at, updated_at, checkpoint_data, error_message,
                    youtube_id, youtube_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    vs.video_id, vs.video_type, vs.state.value,
                    vs.topic_category, vs.title,
                    vs.created_at, vs.updated_at,
                    json.dumps(vs.checkpoint_data), vs.error_message,
                    vs.youtube_id, vs.youtube_url,
                ),
            )
            conn.commit()
            conn.close()
        return vs

    def update_state(
        self,
        video_id: str,
        *,
        state: Optional[PipelineState] = None,
        title: Optional[str] = None,
        error_message: Optional[str] = None,
        youtube_id: Optional[str] = None,
        youtube_url: Optional[str] = None,
        agent_name: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update one or more fields on a video state row."""
        sets: list[str] = []
        vals: list[Any] = []
        if state is not None:
            sets.append("state = ?")
            vals.append(state.value)
        if title is not None:
            sets.append("title = ?")
            vals.append(title)
        if error_message is not None:
            sets.append("error_message = ?")
            vals.append(error_message)
        if youtube_id is not None:
            sets.append("youtube_id = ?")
            vals.append(youtube_id)
        if youtube_url is not None:
            sets.append("youtube_url = ?")
            vals.append(youtube_url)
        if not sets:
            return
        sets.append("updated_at = ?")
        vals.append(self._now())
        vals.append(video_id)

        with self._lock:
            conn = self._conn()
            conn.execute(
                f"UPDATE video_states SET {', '.join(sets)} WHERE video_id = ?",
                vals,
            )
            conn.commit()
            conn.close()

    def get_video_state(self, video_id: str) -> Optional[VideoState]:
        """Fetch a single video state by ID."""
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM video_states WHERE video_id = ?", (video_id,)
            ).fetchone()
            conn.close()
        if row is None:
            return None
        return self._row_to_state(row)

    def get_pending_videos(self) -> List[VideoState]:
        """Return all videos still in PENDING state."""
        return self._query_by_state(PipelineState.PENDING)

    def get_failed_videos(self) -> List[VideoState]:
        """Return all videos in FAILED state."""
        return self._query_by_state(PipelineState.FAILED)

    def get_today_videos(self) -> List[VideoState]:
        """Return all videos created today (UTC)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            conn = self._conn()
            rows = conn.execute(
                "SELECT * FROM video_states WHERE created_at LIKE ?",
                (f"{today}%",),
            ).fetchall()
            conn.close()
        return [self._row_to_state(r) for r in rows]

    def _query_by_state(self, state: PipelineState) -> List[VideoState]:
        with self._lock:
            conn = self._conn()
            rows = conn.execute(
                "SELECT * FROM video_states WHERE state = ?", (state.value,)
            ).fetchall()
            conn.close()
        return [self._row_to_state(r) for r in rows]

    @staticmethod
    def _row_to_state(row: sqlite3.Row) -> VideoState:
        return VideoState(
            video_id=row["video_id"],
            video_type=row["video_type"],
            state=PipelineState(row["state"]),
            topic_category=row["topic_category"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            checkpoint_data=json.loads(row["checkpoint_data"] or "{}"),
            error_message=row["error_message"],
            youtube_id=row["youtube_id"],
            youtube_url=row["youtube_url"],
        )

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def save_checkpoint(
        self, video_id: str, stage: str, data: Dict[str, Any]
    ) -> None:
        """Save or update a checkpoint for a pipeline stage."""
        now = self._now()
        with self._lock:
            conn = self._conn()
            conn.execute(
                """INSERT INTO checkpoints (video_id, stage, data_json, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(video_id, stage) DO UPDATE SET
                       data_json = excluded.data_json,
                       created_at = excluded.created_at""",
                (video_id, stage, json.dumps(data, ensure_ascii=False), now),
            )
            conn.commit()
            conn.close()

    def load_checkpoint(
        self, video_id: str, stage: str
    ) -> Optional[Dict[str, Any]]:
        """Load checkpoint data for a given stage, or ``None``."""
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                "SELECT data_json FROM checkpoints WHERE video_id = ? AND stage = ?",
                (video_id, stage),
            ).fetchone()
            conn.close()
        if row is None:
            return None
        return json.loads(row["data_json"])

    # ------------------------------------------------------------------
    # Agent logs
    # ------------------------------------------------------------------

    def log_agent(
        self,
        agent_name: str,
        action: str,
        video_id: str = "",
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
    ) -> None:
        """Record an agent execution event."""
        now = self._now()
        with self._lock:
            conn = self._conn()
            conn.execute(
                """INSERT INTO agent_logs
                   (agent_name, video_id, action, result_json, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    agent_name, video_id, action,
                    json.dumps(result or {}, ensure_ascii=False),
                    error, now,
                ),
            )
            conn.commit()
            conn.close()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_old_states(self, days: int = 30) -> int:
        """Delete video states older than *days*. Returns count deleted."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            conn = self._conn()
            cur = conn.execute(
                "DELETE FROM video_states WHERE created_at < ?", (cutoff,)
            )
            deleted = cur.rowcount
            conn.execute(
                "DELETE FROM checkpoints WHERE video_id NOT IN "
                "(SELECT video_id FROM video_states)"
            )
            conn.commit()
            conn.close()
        return deleted
