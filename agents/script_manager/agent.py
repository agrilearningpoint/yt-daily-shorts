"""Script Manager Agent — generates structured Hindi scripts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent
from core.llm_client import get_llm_client


@dataclass
class Scene:
    scene_number: int = 0
    narration: str = ""
    visual_instructions: str = ""
    duration: float = 0.0
    sources: List[str] = field(default_factory=list)
    transition: str = "slide_left"


@dataclass
class Script:
    title: str = ""
    hook: str = ""
    scenes: List[Scene] = field(default_factory=list)
    total_duration: float = 0.0
    language: str = "hi"
    video_type: str = ""
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "hook": self.hook,
            "scenes": [vars(s) for s in self.scenes],
            "total_duration": self.total_duration,
            "language": self.language,
            "video_type": self.video_type,
            "sources": self.sources,
        }


class ScriptManagerAgent(BaseAgent):
    """Core agent converting verified research into engaging Hindi video scripts."""

    name = "script_manager"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.llm = get_llm_client(
            provider=self.config.llm.provider,
            api_key=self.config.llm.gemini_api_key or self.config.llm.groq_api_key,
            model_name=self.config.llm.model_name,
            temperature=self.config.llm.temperature
        )

    async def execute(self, **kwargs: Any) -> AgentResult:
        research_data = kwargs.get("research_data", {})
        prompt = kwargs.get("prompt_instructions", "")
        video_type = kwargs.get("video_type", "news")

        self.logger.info("Generating Hindi script for %s", video_type)

        try:
            data = await self.llm.generate_json(prompt)
            title = data.get("title", f"Daily {video_type.title()} Short")
            hook = data.get("hook", "")
            raw_scenes = data.get("scenes", [])
            sources = data.get("sources", research_data.get("sources", []))

            scenes = []
            for idx, sc in enumerate(raw_scenes, 1):
                scenes.append(Scene(
                    scene_number=sc.get("scene_number", idx),
                    narration=sc.get("narration", ""),
                    visual_instructions=sc.get("visual_instructions", ""),
                    duration=float(sc.get("duration", 18.0)),
                    sources=sc.get("sources", sources),
                    transition=sc.get("transition", "slide_left")
                ))

            script = Script(
                title=title,
                hook=hook,
                scenes=scenes,
                total_duration=sum(s.duration for s in scenes),
                language="hi",
                video_type=video_type,
                sources=sources
            )
            estimated_duration = self.estimate_duration(script)
            script.total_duration = estimated_duration or script.total_duration

            return AgentResult(
                success=bool(script.scenes),
                data={"script": script.to_dict(), "estimated_duration": script.total_duration},
                metadata={"video_type": video_type}
            )
        except Exception as exc:
            self.logger.error("Script generation failed: %s", exc)
            return AgentResult(success=False, errors=[str(exc)])

    def estimate_duration(self, script: Script) -> float:
        """Estimate Hindi spoken duration (~2.5 words per sec)."""
        words = len(script.hook.split())
        for s in script.scenes:
            words += len(s.narration.split())
        return round(words / 2.5, 1) if words else 54.0
