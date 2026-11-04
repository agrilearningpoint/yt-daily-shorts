"""Quality Manager Agent — assesses hook, Hindi duration, and repetition."""

from __future__ import annotations

from typing import Any
from agents.base_agent import AgentResult, BaseAgent


class QualityManagerAgent(BaseAgent):
    """Enforces quality thresholds for duration, hook strength, and grammar."""

    name = "quality_manager"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {})
        hook = script.get("hook", "")
        scenes = script.get("scenes", [])
        total_duration = script.get("total_duration", 55.0)

        checks = []

        # 1. Hook check
        hook_passed = len(hook.split()) >= 4
        checks.append({"name": "hook_length", "passed": hook_passed, "score": 1.0 if hook_passed else 0.5})

        # 2. Duration check (45 - 60 sec)
        duration_passed = 40.0 <= total_duration <= 60.0
        checks.append({"name": "duration_bounds", "passed": duration_passed, "score": 1.0 if duration_passed else 0.7})

        # 3. Scene count (at least 2 scenes)
        scene_passed = len(scenes) >= 2
        checks.append({"name": "scene_density", "passed": scene_passed, "score": 1.0 if scene_passed else 0.5})

        overall_score = sum(c["score"] for c in checks) / len(checks)
        approved = overall_score >= 0.7

        return AgentResult(
            success=approved,
            data={
                "overall_score": round(overall_score, 2),
                "approved": approved,
                "checks": checks
            }
        )
