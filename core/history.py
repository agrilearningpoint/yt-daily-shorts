"""Persistent publishing history (survives GitHub Actions runs via actions/cache).

Tracks which knowledge topics and news URLs/titles were already used so the
channel never repeats itself, plus a log of published videos.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


class HistoryStore:
    def __init__(self, path: str = "data/history.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.data: Dict[str, Any] = {"topics": [], "news": [], "videos": []}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # Topics ---------------------------------------------------------------
    def used_topics(self) -> List[str]:
        return [t["topic"] for t in self.data.get("topics", [])]

    def mark_topic(self, topic: str, category: str = "") -> None:
        with self._lock:
            self.data.setdefault("topics", []).append({"topic": topic, "category": category, "at": self._now()})
            self._save()

    # News -----------------------------------------------------------------
    def recent_news(self, days: int = 4) -> List[Dict[str, str]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        out = []
        for n in self.data.get("news", []):
            try:
                if datetime.fromisoformat(n["at"]) >= cutoff:
                    out.append(n)
            except (KeyError, ValueError):
                continue
        return out

    def mark_news(self, items: List[Dict[str, Any]]) -> None:
        with self._lock:
            for it in items:
                self.data.setdefault("news", []).append(
                    {"url": it.get("source_url", ""), "title": it.get("title", ""), "at": self._now()})
            self.data["news"] = self.data["news"][-400:]
            self._save()

    # Videos ---------------------------------------------------------------
    def mark_video(self, record: Dict[str, Any]) -> None:
        with self._lock:
            record = dict(record)
            record.setdefault("at", self._now())
            self.data.setdefault("videos", []).append(record)
            self.data["videos"] = self.data["videos"][-1000:]
            self._save()

    def videos(self) -> List[Dict[str, Any]]:
        return list(self.data.get("videos", []))
