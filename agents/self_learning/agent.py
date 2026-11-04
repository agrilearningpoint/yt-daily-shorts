"""Self-Learning Agent — turns past performance into style guidance for new scripts."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.base_agent import AgentResult, BaseAgent


class SelfLearningAgent(BaseAgent):
    name = "self_learning"

    def __init__(self, config, state_manager, history=None):
        super().__init__(config, state_manager)
        self.history = history

    async def execute(self, **kwargs: Any) -> AgentResult:
        video_type = kwargs.get("video_type", "news")
        vids: List[Dict[str, Any]] = [v for v in (self.history.videos() if self.history else [])
                                      if v.get("video_type") == video_type and v.get("views") is not None]
        if len(vids) < 5:
            return AgentResult(success=True, data={"style_notes": "", "insights": "Not enough data yet."})
        ranked = sorted(vids, key=lambda v: v.get("views", 0), reverse=True)
        top = ranked[:3]
        bottom = ranked[-3:]
        notes = ("PAST PERFORMANCE (learn from it, do not copy): best-performing titles/hooks on this channel: "
                 + " | ".join(f"\"{v.get('title', '')}\" ({v.get('views', 0)} views)" for v in top)
                 + ". Weakest: " + " | ".join(f"\"{v.get('title', '')}\"" for v in bottom)
                 + ". Write a hook and title in the style of the best performers.")
        avg = sum(v.get("views", 0) for v in vids) / len(vids)
        return AgentResult(success=True, data={"style_notes": notes,
                                               "insights": f"Avg views ({video_type}, {len(vids)} videos): {avg:.0f}. Top: {top[0].get('title', '')}"})
