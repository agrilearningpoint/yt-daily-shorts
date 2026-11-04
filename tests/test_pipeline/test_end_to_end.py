"""End-to-end dry-run of the whole pipeline (offline: LLM mocked, TTS -> silence, no image downloads)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.configuration import load_config
from core.history import HistoryStore
from core.orchestrator import DailyOrchestrator, VideoTask
from core.state_manager import PipelineState, StateManager
from research.news_collector import NewsCollector
from video.media_collector import MediaCollector
from video.tts import TTSEngine


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")
async def test_full_pipeline_dry_run(tmp_path, monkeypatch):
    for k in ("GEMINI", "GROQ", "MISTRAL", "OPENROUTER", "NVIDIA", "OLLAMA"):
        monkeypatch.delenv(f"YT_{k}_API_KEY", raising=False)
    monkeypatch.delenv("YT_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(NewsCollector, "_fetch_all", lambda self: [])
    monkeypatch.setattr(MediaCollector, "find_image", lambda self, *a, **k: None)

    async def no_tts(self, text, out_file, voice):
        raise RuntimeError("offline")
    monkeypatch.setattr(TTSEngine, "_synth", no_tts)
    monkeypatch.setattr("asyncio.sleep", _instant)

    cfg = load_config()
    cfg.set_dry_run(True)
    cfg.general.strict_mode = False
    cfg.llm.allow_mock = True
    cfg.video.background_music = False
    cfg.database.sqlite_path = str(tmp_path / "e2e.db")
    state = StateManager(cfg.database.sqlite_path)
    orch = DailyOrchestrator(cfg, state, HistoryStore(str(tmp_path / "h.json")))

    vs = await orch.run_pipeline(VideoTask("news", "Test Roundup", "05:30", 1, "monday"))
    assert vs.state == PipelineState.COMPLETED, vs.error_message
    assert vs.youtube_id.startswith("mock_")
    prod = state.load_checkpoint(vs.video_id, "video_production")
    assert Path(prod["video_path"]).stat().st_size > 200_000
    assert prod["duration"] >= 10
    shutil.rmtree(Path("output") / vs.video_id, ignore_errors=True)


async def _instant(*_a, **_k):
    return None
