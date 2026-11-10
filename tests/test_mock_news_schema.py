"""Regression: the offline mock must satisfy the v2 news script validator.

CI went red because MockLLMProvider still emitted the pre-v2 3-scene payload
while ``ScriptManagerAgent.validate`` expects bucket-based stories
(``national``/``international``) with per-story ``category``.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.script_manager.agent import ScriptManagerAgent, bounds, parse_script
from core.duration import WORDS_PER_SEC
from core.configuration import load_config
from core.llm_client import MockLLMProvider
from core.state_manager import StateManager


NEWS_PROMPT = """
Return ONLY valid JSON:
{
 "hook": "...",
 "national": [
   1. "national": 16 DIFFERENT Indian stories (national politics, government, states, economy)
   2. "international": 4 DIFFERENT world stories (world leaders, wars/diplomacy)
 ],
 "national": [{"on_screen_text": "...", "src": 1, "parts": [...]}],
 "international": [{"on_screen_text": "...", "src": 7, "parts": [...]}]
}
Give the candidate number for "src".
"""


def _mock_payload(prompt: str) -> dict:
    return asyncio.run(MockLLMProvider().generate_json(prompt))


@pytest.fixture()
def agent(tmp_path):
    cfg = load_config()
    cfg.llm.allow_mock = True
    cfg.database.sqlite_path = str(tmp_path / "mock.db")
    return ScriptManagerAgent(cfg, StateManager(cfg.database.sqlite_path))


def test_mock_returns_bucket_schema():
    data = _mock_payload(NEWS_PROMPT)
    assert "national" in data and "international" in data
    assert len(data["national"]) >= 4
    assert all(story.get("parts") for story in data["national"])


def test_mock_script_passes_news_validation(agent):
    data = _mock_payload(NEWS_PROMPT)
    script = parse_script(data, "news", [], [])
    # same order as ScriptManagerAgent.execute(): trim, validate, and ignore "too ..."
    # length notes (execute() demotes those to the Quality Manager's duration rule).
    agent.targets = None
    budget = int(bounds(agent.config.video, "news", None)[1] * WORDS_PER_SEC["news"])
    agent.fit_news(script, budget)
    problems = agent.validate(script, 110, 135)
    hard = [p for p in problems if not p.startswith("too ")]
    assert hard == [], hard
    lo, hi = bounds(agent.config.video, "news", None)
    from core.duration import estimate_seconds
    est = estimate_seconds(agent._as_dict(script, "news"))
    assert lo <= est <= hi, f"{est:.0f}s outside {lo:.0f}-{hi:.0f}s"
    assert all(s.parts for s in script.scenes)
    assert all(s.category for s in script.scenes)   # Hindi section name filled in
    # each story should read like a news line (9..22 words)
    assert all(9 <= len(s.narration.split()) <= 22 for s in script.scenes)


def test_mock_hook_mentions_first_story():
    data = _mock_payload(NEWS_PROMPT)
    assert "डिजिटल इंडिया" in data["hook"]
    assert data["national"][0]["on_screen_text"] == "डिजिटल इंडिया"
