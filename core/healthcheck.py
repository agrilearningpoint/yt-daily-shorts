"""Ops healthcheck: the alarm for the run that never happened.

A daily Telegram report is sent *by* the run. If the scheduler never fires, or
the workflow is disabled, or every retry failed, that report never arrives and the
channel silently goes dark. This check is the opposite: it looks for the absence
of success and speaks up.

Exit code 0 = healthy, 1 = degraded (so a workflow step can fail loudly).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("core.healthcheck")

MAX_AGE_HOURS = 30.0       # a daily channel must have produced something in this window


def _last_success(state_db: Path) -> Optional[datetime]:
    try:
        import sqlite3
        con = sqlite3.connect(str(state_db))
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        stamps: List[str] = []
        for t in tables:
            try:
                cur.execute(f"SELECT * FROM {t} LIMIT 0")
                cols = [d[0] for d in cur.description]
            except Exception:
                continue
            for col in ("updated_at", "created_at", "completed_at", "timestamp"):
                if col in cols:
                    try:
                        cur.execute(f"SELECT {col} FROM {t} WHERE {col} IS NOT NULL ORDER BY {col} DESC LIMIT 1")
                        row = cur.fetchone()
                        if row and row[0]:
                            stamps.append(str(row[0]))
                    except Exception:
                        continue
        con.close()
        parsed = []
        for s in stamps:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed.append(datetime.strptime(s[:19], fmt))
                    break
                except ValueError:
                    continue
        return max(parsed) if parsed else None
    except Exception as exc:
        logger.debug("could not read state db: %s", exc)
        return None


def _metrics_age_hours() -> Optional[float]:
    p = Path("data/metrics.jsonl")
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def check(state_db: str = "data/yt_shorts.db") -> Tuple[bool, List[str]]:
    """Return (healthy, findings). Findings are human-readable lines for Telegram."""
    findings: List[str] = []
    healthy = True

    last = _last_success(Path(state_db))
    if last is None:
        findings.append("⚠️ state DB me koi successful run record nahi mila")
    else:
        age = (datetime.now() - last).total_seconds() / 3600.0
        if age > MAX_AGE_HOURS:
            healthy = False
            findings.append(f"🚨 pichla successful run {age:.0f} घंटे पहले tha (limit {MAX_AGE_HOURS:.0f}h)")

    m_age = _metrics_age_hours()
    if m_age is not None and m_age > MAX_AGE_HOURS:
        findings.append(f"⚠️ metrics.jsonl {m_age:.0f}h se update nahi hua")

    try:                          # disk safety for a runner that also caches models
        usage = __import__("shutil").disk_usage(".")
        free_gb = usage.free / 1e9
        if free_gb < 3:
            healthy = False
            findings.append(f"🚨 disk free {free_gb:.1f} GB — render fail hoga")
    except Exception:
        pass

    # LLM quota snapshot: how much of the free pool is left today
    try:
        from core.self_improve import load_metrics
        rows = load_metrics(20)
        quota_hits = sum(1 for r in rows if "llm_quota" in (r.get("classes") or []))
        if quota_hits:
            findings.append(f"ℹ️ last {len(rows)} runs me {quota_hits} baar LLM quota hit hua")
    except Exception:
        pass

    if not findings:
        findings.append("✅ sab theek — last run window ke andar hai")
    return healthy, findings


def notify(findings: List[str]) -> None:
    try:
        from core.configuration import load_config
        from telegram.notifier import TelegramNotifier
        cfg = load_config()
        TelegramNotifier(cfg.telegram).send_message("🩺 <b>Healthcheck</b>\n" + "\n".join(findings))
    except Exception as exc:
        logger.warning("healthcheck notify skipped: %s", exc)


if __name__ == "__main__":
    import sys
    ok, f = check()
    print("\n".join(f))
    if "--notify" in sys.argv:
        notify(f)
    sys.exit(0 if ok else 1)
