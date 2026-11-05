"""Fact Verifier Agent — LLM cross-check of every claim against the research."""

from __future__ import annotations

import copy
from typing import Any

from agents.base_agent import AgentResult, BaseAgent
from prompts import render_prompt


class FactVerifierAgent(BaseAgent):
    name = "fact_verifier"

    def __init__(self, config, state_manager, llm=None):
        super().__init__(config, state_manager)
        self.llm = llm

    async def execute(self, **kwargs: Any) -> AgentResult:
        script = copy.deepcopy(kwargs.get("script", {}) or {})
        research = kwargs.get("research_data", {}) or {}
        items = research.get("items", [])
        used = set(script.get("sources", []))
        if len(items) > 10 and used:  # news: check only the stories actually used (keeps the prompt small)
            picked = [i for i in items if i.get("source_url") in used]
            # stories that cite by number may not list URLs: never check against a truncated list
            items = picked if len(picked) >= max(5, len(script.get("scenes", [])) // 2) else items[:70]

        if not script.get("sources"):
            return AgentResult(success=False, data={"verdict": "fail", "script": script},
                               errors=["script has no sources"])
        if self.llm is None:
            return AgentResult(success=False, errors=["No LLM configured for fact check"])

        prompt = render_prompt("verification/fact_check.j2", {"script": script, "research_items": items})
        try:
            result = await self.llm.generate_json(prompt)
        except Exception as exc:
            if self.config.general.strict_mode:
                return AgentResult(success=False, errors=[f"fact check unavailable: {exc}"])
            self.logger.warning("Fact check skipped (dry run): %s", exc)
            return AgentResult(success=True, data={"verdict": "skipped", "script": script})

        verdict = str(result.get("verdict", "fail")).lower()
        issues = result.get("issues") or []
        fixes = {int(c.get("scene_number", -1)): c.get("narration", "")
                 for c in (result.get("corrected_scenes") or []) if isinstance(c, dict)}
        for sc in script.get("scenes", []):
            new = (fixes.get(int(sc.get("scene_number", 0))) or "").strip()
            if new and new != sc.get("narration"):
                sc["narration"] = new
                from agents.script_manager.agent import resplit_parts
                sc["parts"] = resplit_parts(sc.get("parts") or [], new)
        if (result.get("corrected_hook") or "").strip():
            script["hook"] = result["corrected_hook"].strip()

        ok = verdict in ("pass", "fixed")
        self.logger.info("Fact check verdict=%s issues=%d", verdict, len(issues))
        return AgentResult(
            success=ok,
            data={"verdict": verdict, "confidence": result.get("confidence", 0), "issues": issues,
                  "all_verified": ok, "script": script, "verified_sources": script.get("sources", [])},
            errors=[] if ok else [f"fact check failed: {issues[:3]}"],
        )
