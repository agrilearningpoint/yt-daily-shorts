"""Quality Manager Agent — hard gate before rendering/publishing."""

from __future__ import annotations

import re
from typing import Any

from agents.base_agent import AgentResult, BaseAgent

_BANNED = ("lorem", "placeholder", "TODO", "दृश्य 1 का", "हिंदी नरेशन")


class QualityManagerAgent(BaseAgent):
    name = "quality_manager"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        verification = kwargs.get("verification", {}) or {}
        hook = script.get("hook", "")
        scenes = script.get("scenes", [])
        words = len(hook.split()) + sum(len(s.get("narration", "").split()) for s in scenes)
        est = words / 2.5
        v = self.config.video
        text = hook + " ".join(s.get("narration", "") for s in scenes)

        checks = [
            {"name": "hook_length", "passed": 4 <= len(hook.split()) <= 22},
            {"name": "duration_bounds", "passed": v.min_duration <= est <= v.max_duration + 6},
            {"name": "scene_count", "passed": 2 <= len(scenes) <= 6},
            {"name": "hindi_script", "passed": len(re.findall(r"[\u0900-\u097F]", text)) > len(text) * 0.4},
            {"name": "no_placeholders", "passed": not any(b.lower() in text.lower() for b in _BANNED)},
            {"name": "has_sources", "passed": bool(script.get("sources"))},
            {"name": "fact_check", "passed": verification.get("verdict") in ("pass", "fixed", "skipped")},
        ]
        failed = [c["name"] for c in checks if not c["passed"]]
        approved = not failed
        return AgentResult(
            success=approved,
            data={"approved": approved, "estimated_duration": round(est, 1), "checks": checks,
                  "overall_score": round(1 - len(failed) / len(checks), 2)},
            errors=[f"quality gate failed: {failed}"] if failed else [],
        )
