"""Script Manager Agent — generates and validates structured Hindi scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
SYSTEM_PROMPT = (
    "You write accurate, engaging Hindi (Devanagari) scripts for YouTube Shorts. "
    "You never invent facts. You always answer with a single valid JSON object."
)


@dataclass
class Scene:
    scene_number: int = 0
    narration: str = ""
    on_screen_text: str = ""
    visual_keywords: str = ""
    sources: List[str] = field(default_factory=list)


@dataclass
class Script:
    title: str = ""
    hook: str = ""
    scenes: List[Scene] = field(default_factory=list)
    total_duration: float = 0.0
    language: str = "hi"
    video_type: str = ""
    sources: List[str] = field(default_factory=list)

    def word_count(self) -> int:
        return len(self.hook.split()) + sum(len(s.narration.split()) for s in self.scenes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title, "hook": self.hook, "scenes": [vars(s) for s in self.scenes],
            "total_duration": self.total_duration, "language": self.language,
            "video_type": self.video_type, "sources": self.sources, "word_count": self.word_count(),
        }


def parse_script(data: Dict[str, Any], video_type: str, fallback_sources: List[str]) -> Script:
    sources = [s for s in (data.get("sources") or fallback_sources) if isinstance(s, str) and s.startswith("http")]
    scenes = []
    for idx, sc in enumerate(data.get("scenes") or [], 1):
        if not isinstance(sc, dict):
            continue
        narration = str(sc.get("narration", "")).strip()
        if not narration:
            continue
        sc_sources = [s for s in (sc.get("sources") or sources) if isinstance(s, str) and s.startswith("http")]
        scenes.append(Scene(
            scene_number=idx,
            narration=narration,
            on_screen_text=str(sc.get("on_screen_text", "")).strip()[:40],
            visual_keywords=str(sc.get("visual_keywords") or sc.get("visual_instructions") or "").strip()[:80],
            sources=sc_sources,
        ))
    all_sources = list(dict.fromkeys(sources + [u for s in scenes for u in s.sources]))
    return Script(title=str(data.get("title", "")).strip(), hook=str(data.get("hook", "")).strip(),
                  scenes=scenes, video_type=video_type, sources=all_sources)


class ScriptManagerAgent(BaseAgent):
    name = "script_manager"

    def __init__(self, config, state_manager, llm=None):
        super().__init__(config, state_manager)
        self.llm = llm

    def validate(self, script: Script, min_w: int, max_w: int) -> List[str]:
        problems = []
        if not script.title:
            problems.append("missing title")
        if len(script.hook.split()) < 4:
            problems.append("hook too short")
        if len(script.scenes) < 2:
            problems.append("fewer than 2 scenes")
        text = script.hook + " ".join(s.narration for s in script.scenes)
        if len(_DEVANAGARI.findall(text)) < len(text) * 0.4:
            problems.append("narration is not in Hindi (Devanagari)")
        wc = script.word_count()
        if wc < min_w * 0.8:
            problems.append(f"too short: {wc} words, need {min_w}-{max_w}")
        if wc > max_w * 1.1:
            problems.append(f"too long: {wc} words, need {min_w}-{max_w}")
        if not script.sources:
            problems.append("no sources")
        return problems

    async def execute(self, **kwargs: Any) -> AgentResult:
        research_data = kwargs.get("research_data", {}) or {}
        prompt = kwargs.get("prompt_instructions", "")
        video_type = kwargs.get("video_type", "news")
        min_w = int(kwargs.get("min_words", 110))
        max_w = int(kwargs.get("max_words", 135))
        fallback_sources = research_data.get("sources", [])

        if self.llm is None:
            return AgentResult(success=False, errors=["No LLM configured"])

        attempt_prompt = prompt
        last_problems: List[str] = []
        script = None
        for attempt in range(3):
            try:
                data = await self.llm.generate_json(attempt_prompt, SYSTEM_PROMPT)
            except Exception as exc:
                self.logger.error("Script generation failed: %s", exc)
                return AgentResult(success=False, errors=[str(exc)])
            script = parse_script(data, video_type, fallback_sources)
            last_problems = self.validate(script, min_w, max_w)
            if not last_problems:
                break
            self.logger.warning("Script attempt %d rejected: %s", attempt + 1, last_problems)
            attempt_prompt = (prompt + "\n\nYOUR PREVIOUS ANSWER WAS REJECTED because: "
                              + "; ".join(last_problems) + ". Fix these and return the full JSON again.")

        if script is None or last_problems:
            hard = [p for p in last_problems if not p.startswith("too ")]
            if script is None or hard:
                return AgentResult(success=False, errors=last_problems or ["no script"])
            self.logger.warning("Accepting script with soft issues: %s", last_problems)

        script.total_duration = round(script.word_count() / 2.5, 1)
        return AgentResult(success=True,
                           data={"script": script.to_dict(), "llm": getattr(self.llm, "last_used", "")},
                           metadata={"video_type": video_type})
