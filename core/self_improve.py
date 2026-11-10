"""Self-improvement loop: every run teaches the next one something.

Three small pieces, no magic:

1. `record_run()`  - append one line of metrics per run (durations, failures,
   providers used, storage sizes) to `data/metrics.jsonl`.
2. `classify_error()` - bucket an error message into a known failure class so the
   same class can be counted instead of re-read.
3. `report()` - turn the log into `data/improvements.md`: the top failure classes,
   the slowest stage, and the concrete fix for each. The error-analyst agent feeds
   this into prompts so the writer/editor actually change behaviour next time.

The point is not a fancy ML loop; it is that a failure that happened twice must
never be diagnosed from scratch a third time.
"""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.self_improve")

DATA = Path("data")

# error class -> (matcher substrings, the fix that actually applies)
ERROR_CLASSES: Dict[str, Dict[str, Any]] = {
    "llm_quota":        {"match": ("429", "quota", "RESOURCE_EXHAUSTED", "rate limit"),
                         "fix": "shift the stage to another provider; keep the flagship tier for script/SEO only"},
    "llm_timeout":      {"match": ("timeout", "timed out", "ReadTimeout"),
                         "fix": "the key/model is parked for the run — check the llm-check report before blaming code"},
    "llm_unavailable":  {"match": ("503", "high demand", "overloaded"),
                         "fix": "model is congested upstream; the chain already falls through, no action"},
    "no_visual":        {"match": ("no visuals", "visual step", "no images"),
                         "fix": "add 2 more concrete visual_queries for that beat/chapter"},
    "media_download":   {"match": ("download", "HTTP 404", "HTTP 403"),
                         "fix": "source threw a dead link; the sourcer now retries the next candidate"},
    "render_ffmpeg":    {"match": ("ffmpeg failed", "Invalid argument", "filter"),
                         "fix": "keep image sizes uniform (the pipeline rescales, this means a corrupt file)"},
    "storage":          {"match": ("HF storage", "upload failed", "huggingface"),
                         "fix": "storage is optional by design — never blocks a run, just check the token"},
    "youtube_auth":     {"match": ("credentials", "invalid_grant", "401", "refresh"),
                         "fix": "OAuth refresh token expired — re-run the YouTube auth flow once"},
    "youtube_upload":   {"match": ("upload failed", "quotaExceeded", "video file missing"),
                         "fix": "YouTube rejected the file/size; the artifact is kept on HF for a manual retry"},
    "tts":              {"match": ("TTS", "edge-tts", "no audio"),
                         "fix": "edge-tts hiccup; retried automatically, fallback voice is hi-IN-SwaraNeural"},
    "unknown":          {"match": (),
                         "fix": "read the traceback — a new failure class deserves a new rule here"},
}


def classify_error(message: str) -> str:
    low = str(message).lower()
    for name, spec in ERROR_CLASSES.items():
        if any(m.lower() in low for m in spec["match"]):
            return name
    return "unknown"


def record_run(kind: str, duration_min: float, ok: bool, errors: Optional[List[str]] = None,
               extra: Optional[Dict[str, Any]] = None) -> None:
    DATA.mkdir(exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "minutes": round(duration_min, 2),
           "ok": bool(ok), "classes": sorted({classify_error(e) for e in (errors or [])})}
    if extra:
        row.update(extra)
    with open(DATA / "metrics.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_metrics(limit: int = 200) -> List[Dict[str, Any]]:
    path = DATA / "metrics.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def report() -> str:
    """Write data/improvements.md and return it (also used as a prompt fragment)."""
    rows = load_metrics()
    if not rows:
        return "no runs recorded yet"
    classes = Counter(c for r in rows for c in r.get("classes", []))
    fails = sum(1 for r in rows if not r.get("ok"))
    avg = sum(r.get("minutes", 0) for r in rows) / len(rows)
    lines = [f"# Self-improvement report",
             f"", f"- runs analysed: **{len(rows)}**", f"- failed runs: **{fails}**",
             f"- average duration: **{avg:.1f} min**", ""]
    if classes:
        lines.append("## Recurring failure classes")
        lines.append("")
        lines.append("| class | count | fix |")
        lines.append("|---|---|---|")
        for name, n in classes.most_common(6):
            lines.append(f"| `{name}` | {n} | {ERROR_CLASSES.get(name, {}).get('fix', '-')} |")
        lines.append("")
    by_kind = Counter(r.get("kind", "?") for r in rows)
    lines.append("## Runs by type\n")
    for k, n in by_kind.most_common():
        lines.append(f"- {k}: {n}")
    lines.append("")
    lines.append("## Next actions")
    for name, _ in classes.most_common(3):
        fix = ERROR_CLASSES.get(name, {}).get("fix")
        if fix:
            lines.append(f"- **{name}**: {fix}")
    text = "\n".join(lines)
    DATA.mkdir(exist_ok=True)
    (DATA / "improvements.md").write_text(text + "\n", encoding="utf-8")
    return text


def lessons_for_prompt(limit_chars: int = 700) -> str:
    """Short fragment the scriptwriter/reviewer can take as guidance."""
    rows = load_metrics(60)
    if not rows:
        return ""
    classes = Counter(c for r in rows for c in r.get("classes", []))
    if not classes:
        return ""
    top = ", ".join(f"{c} x{n}" for c, n in classes.most_common(3))
    return (f"Known pipeline failure history (avoid triggering these): {top}. "
            "Prefer conservative choices that keep the run cheap and reliable.")
