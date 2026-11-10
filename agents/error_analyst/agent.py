"""Error Analyst — reads what actually broke and turns it into a fix list.

Different from self-learning (which looks at *views*): this agent looks at
*failures*. It walks the run database and the metrics log, groups errors into the
classes defined in ``core.self_improve``, and writes:

  * ``data/improvements.md``      - the ranked "fix this next" report
  * ``data/lessons.json``         - one machine-readable line per class + the fix
  * a prompt fragment             - so the writer/editor change behaviour next run

Run it after every production run (the orchestrator already calls it) or by hand:
``python -m agents.error_analyst``.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent
from core.self_improve import ERROR_CLASSES, classify_error, load_metrics, report

logger = logging.getLogger("agent.error_analyst")

DATA = Path("data")


class ErrorAnalystAgent(BaseAgent):
    name = "error_analyst"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)

    # ------------------------------------------------------------------ inputs
    def _failed_runs(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            for v in self.state.get_failed_videos():
                if str(getattr(v, "state", "")).lower().endswith("failed") and getattr(v, "error_message", ""):
                    rows.append({"video_id": getattr(v, "video_id", ""),
                                 "error": str(v.error_message)[:400],
                                 "type": getattr(v, "video_type", "")})
        except Exception as exc:
            logger.debug("state query unavailable: %s", exc)
        # long-form runs never touch the state DB, so the metrics log is the other half
        for r in load_metrics(120):
            if not r.get("ok") and r.get("error"):
                rows.append({"video_id": r.get("kind", "?"), "error": str(r["error"])[:400],
                             "type": r.get("kind", "")})
        return rows

    # ----------------------------------------------------------------- execute
    async def execute(self, **kwargs: Any) -> AgentResult:
        failed = self._failed_runs()
        classes = Counter(classify_error(f["error"]) for f in failed)
        metrics = load_metrics(120)
        for r in metrics:
            for c in r.get("classes") or []:
                classes[c] += 1

        lessons: List[Dict[str, str]] = []
        for name, count in classes.most_common():
            fix = ERROR_CLASSES.get(name, {}).get("fix", "")
            example = next((f["error"] for f in failed if classify_error(f["error"]) == name), "")
            lessons.append({"class": name, "count": str(count), "fix": fix,
                            "example": example[:200]})
            logger.info("failure class %-16s x%-3d %s", name, count, fix[:60])

        DATA.mkdir(exist_ok=True)
        (DATA / "lessons.json").write_text(json.dumps(lessons, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        text = report()
        (DATA / "improvements.md").write_text(text + "\n", encoding="utf-8")

        fragment = ""
        if lessons:
            top = lessons[:3]
            fragment = ("AVOID REPEATING THESE PIPELINE FAILURES: "
                        + "; ".join(f"{l['class']} ({l['count']}x)" for l in top) + ".")
        return AgentResult(success=True, data={
            "failed_runs": len(failed),
            "classes": dict(classes),
            "lessons": lessons[:8],
            "prompt_fragment": fragment,
            "report_path": str(DATA / "improvements.md"),
        })


def main() -> int:      # convenience CLI
    import asyncio
    from core.configuration import load_config
    from core.state_manager import StateManager

    cfg = load_config()
    state = StateManager(cfg.database.sqlite_path)
    res = asyncio.run(ErrorAnalystAgent(cfg, state).execute())
    print(json.dumps(res.data, ensure_ascii=False, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
