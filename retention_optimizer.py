"""Self-learning loop: reads YouTube Analytics retention & updates editor_memory.json."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List


def fetch_recent_shorts_retention(yt_analytics: Any, days: int = 14) -> List[Dict[str, Any]]:
    """Query YouTube Analytics API for views, avg view duration, and avg view percentage."""
    end_d = date.today().isoformat()
    start_d = (date.today() - timedelta(days=days)).isoformat()
    resp = (
        yt_analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start_d,
            endDate=end_d,
            metrics="views,averageViewDuration,averageViewPercentage,likes,subscribersGained",
            dimensions="video",
            sort="-views",
            maxResults=20,
        )
        .execute()
    )
    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    rows = resp.get("rows", [])
    return [dict(zip(headers, row)) for row in rows]


def update_editor_memory(
    memory_path: str | Path,
    analytics_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Adjust hook & pacing rules in editor_memory.json based on real retention performance."""
    p = Path(memory_path)
    mem: Dict[str, Any] = {}
    if p.exists():
        mem = json.loads(p.read_text(encoding="utf-8"))

    if not analytics_rows:
        return mem

    avg_pct = sum(float(r.get("averageViewPercentage", 0)) for r in analytics_rows) / len(analytics_rows)
    rules = mem.setdefault("auto_learned_rules", {})
    rules["last_avg_retention_pct"] = round(avg_pct, 2)

    if avg_pct < 65.0:
        rules["hook_max_words"] = 10
        rules["force_pattern_interrupt"] = True
        rules["recommended_target_duration_sec"] = 42
        rules["subtitle_font_size"] = 108
    elif avg_pct >= 85.0:
        rules["hook_max_words"] = 14
        rules["recommended_target_duration_sec"] = 50

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mem, indent=2, ensure_ascii=False), encoding="utf-8")
    return mem
