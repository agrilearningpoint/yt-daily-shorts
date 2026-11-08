"""Quality Manager Agent — hard gate before rendering/publishing."""

from __future__ import annotations

import re
from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from core.duration import MIN_NEWS_STORIES, bounds, estimate_seconds

_BANNED = ("lorem", "placeholder", "TODO", "दृश्य 1 का", "हिंदी नरेशन")


class QualityManagerAgent(BaseAgent):
    name = "quality_manager"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = kwargs.get("script", {}) or {}
        verification = kwargs.get("verification", {}) or {}
        hook = script.get("hook", "")
        scenes = script.get("scenes", [])
        is_news = script.get("video_type") == "news"
        est = estimate_seconds(script)
        v = self.config.video
        targets = script.get("news_targets") if is_news else None
        lo, hi = bounds(v, "news" if is_news else "knowledge", targets)
        if is_news:
            t = targets or {"min_national": v.news_national_count - 6,
                            "min_international": min(5, v.news_international_count)}
            min_scenes = max(MIN_NEWS_STORIES, t["min_national"] + t["min_international"] - 3)
        else:
            min_scenes = 2
        max_scenes = 50 if is_news else 9
        if is_news and est > hi:
            # later stages (fact-check rewrite, hook agent) can add a few words: trim the longest national
            # stories in place instead of failing the whole day (run 42502796963 failed at 142s > 138s)
            while est > hi and len(scenes) > min_scenes:
                nat = [s for s in scenes if s.get("section") != "international"] or scenes
                scenes.remove(max(nat, key=lambda s: len((s.get("narration") or "").split())))
                est = estimate_seconds(script)
            for i, s in enumerate(scenes, 1):
                s["scene_number"] = i
            self.logger.info("trimmed news script to %d stories, ~%.0fs", len(scenes), est)
        text = hook + " ".join(s.get("narration", "") for s in scenes)

        checks = [
            {"name": "hook_length", "passed": 3 <= len(hook.split()) <= 22},
            {"name": "duration_bounds", "passed": lo <= est <= hi},
            {"name": "scene_count", "passed": min_scenes <= len(scenes) <= max_scenes},
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
            errors=[f"quality gate failed: {failed} (estimated {est:.0f}s, allowed {lo:.0f}-{hi:.0f}s)"] if failed else [],
        )
