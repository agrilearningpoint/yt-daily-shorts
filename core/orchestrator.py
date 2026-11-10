"""Main pipeline orchestrator.

research -> prompt -> script -> fact-check (auto-corrects) -> quality gate ->
creative -> voice/visual/render -> SEO -> thumbnail -> publish -> notify.
Every stage is checkpointed; any failed gate stops the video so nothing
broken is ever published.
"""

from __future__ import annotations

from core.duration import SHORTS_HARD_LIMIT
import logging
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz

from agents.analytics_manager import AnalyticsManagerAgent
from agents.creative_director import CreativeDirectorAgent
from agents.fact_verifier import FactVerifierAgent
from agents.prompt_engineer import PromptEngineerAgent
from agents.publisher import PublisherAgent
from agents.quality_manager import QualityManagerAgent
from agents.research_manager import ResearchManagerAgent
from agents.script_manager import ScriptManagerAgent
from agents.self_learning import SelfLearningAgent
from agents.seo_manager import SEOManagerAgent
from agents.thumbnail_designer import ThumbnailDesignerAgent
from agents.video_producer import VideoProducerAgent
from core.configuration import AppConfig
from core.history import HistoryStore
from core.llm_client import build_llm
from core.state_manager import PipelineState, StateManager, VideoState
from telegram.bot import TelegramNotifier, esc
from telegram.reports import TelegramReportBuilder

logger = logging.getLogger("core.orchestrator")


class StageError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


@dataclass
class VideoTask:
    video_type: str          # "news" | "knowledge"
    topic_category: str
    scheduled_time: str      # HH:MM IST
    priority: int = 1
    day_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class DailyOrchestrator:
    def __init__(self, config: AppConfig, state_manager: Optional[StateManager] = None,
                 history: Optional[HistoryStore] = None) -> None:
        self.config = config
        self.state = state_manager or StateManager(config.database.sqlite_path)
        self.history = history or HistoryStore(config.database.history_path)
        self.notifier = TelegramNotifier(config.telegram.bot_token, config.telegram.chat_id)
        self.llm = build_llm(config.llm, allow_mock=not config.general.strict_mode)

        self.research_agent = ResearchManagerAgent(config, self.state, history=self.history, llm=self.llm)
        self.prompt_agent = PromptEngineerAgent(config, self.state)
        self.script_agent = ScriptManagerAgent(config, self.state, llm=self.llm)
        self.verifier_agent = FactVerifierAgent(config, self.state, llm=self.llm)
        self.quality_agent = QualityManagerAgent(config, self.state)
        self.creative_agent = CreativeDirectorAgent(config, self.state, history=self.history)
        self.producer_agent = VideoProducerAgent(config, self.state)
        self.seo_agent = SEOManagerAgent(config, self.state, llm=self.llm)
        self.thumbnail_agent = ThumbnailDesignerAgent(config, self.state)
        self.publisher_agent = PublisherAgent(config, self.state)
        self.analytics_agent = AnalyticsManagerAgent(config, self.state, history=self.history)
        self.learning_agent = SelfLearningAgent(config, self.state, history=self.history)
        self.failures: List[str] = []
        self._summary_cache: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    def _now(self) -> datetime:
        return datetime.now(pytz.timezone(self.config.general.timezone))

    def get_video_schedule(self) -> List[VideoTask]:
        day_name = self._now().strftime("%A").lower()
        category = self.config.editorial_calendar.get_today_category(day_name)
        tasks = [
            VideoTask("news", "Daily News Roundup", "05:30", 1, day_name),
            VideoTask("knowledge", category, "14:30", 2, day_name),
        ]
        if self.config.general.daily_video_count >= 3:
            tasks.append(VideoTask("knowledge", f"{category} - Spotlight", "18:00", 3, day_name))
        return tasks[: max(1, self.config.general.daily_video_count)]

    def _preflight(self) -> None:
        if self.config.general.strict_mode and not self.llm.candidates:
            raise StageError("preflight", "No LLM API key available — refusing to publish placeholder content.")

    async def _stage(self, video_id: str, stage: str, coro_factory, require_success: bool = True) -> Dict[str, Any]:
        cached = self.state.load_checkpoint(video_id, stage)
        if cached:
            return cached
        result = await coro_factory()
        self.state.log_agent(stage, "execute", video_id, result.data if isinstance(result.data, dict) else {},
                             "; ".join(result.errors))
        if require_success and not result.success:
            raise StageError(stage, "; ".join(result.errors) or f"{stage} failed")
        self.state.save_checkpoint(video_id, stage, result.data)
        return result.data

    # ------------------------------------------------------------------
    async def run_pipeline(self, task: VideoTask, video_id: Optional[str] = None) -> VideoState:
        if video_id and self.state.get_video_state(video_id):
            vs = self.state.get_video_state(video_id)
        else:
            vs = self.state.create_video_state(video_type=task.video_type, topic_category=task.topic_category)
        vid = vs.video_id
        logger.info("🎬 Pipeline %s [%s — %s]", vid, task.video_type, task.topic_category)
        try:
            self._preflight()

            self.state.update_state(vid, state=PipelineState.RESEARCHING)
            research = await self._stage(vid, "research", lambda: self.research_agent.execute(
                video_type=task.video_type, topic_category=task.topic_category, day_name=task.day_name))

            learning = await self.learning_agent.execute(video_type=task.video_type)
            prompt = await self._stage(vid, "prompt_engineering", lambda: self.prompt_agent.execute(
                video_type=task.video_type, research_data=research, topic_category=task.topic_category))
            prompt_text = prompt.get("prompt", "")
            if learning.data.get("style_notes"):
                prompt_text += "\n\n" + learning.data["style_notes"]

            self.state.update_state(vid, state=PipelineState.SCRIPTING)
            script_data = await self._stage(vid, "script_generation", lambda: self.script_agent.execute(
                video_type=task.video_type, research_data=research, prompt_instructions=prompt_text,
                min_words=prompt.get("min_words", 110), max_words=prompt.get("max_words", 135),
                targets=prompt.get("targets")))
            script = script_data.get("script", script_data)
            llm_used = script_data.get("llm", "")

            self.state.update_state(vid, state=PipelineState.VERIFYING, title=script.get("title", ""))
            verification = await self._stage(vid, "fact_verification", lambda: self.verifier_agent.execute(
                script=script, research_data=research))
            script = verification.get("script") or script

            quality = await self._stage(vid, "quality_check", lambda: self.quality_agent.execute(
                script=script, verification=verification))

            creative = await self._stage(vid, "creative_direction", lambda: self.creative_agent.execute(script=script))

            self.state.update_state(vid, state=PipelineState.RENDERING)
            production = await self._stage(vid, "video_production", lambda: self.producer_agent.execute(
                video_id=vid, script=script, creative_brief=creative, research_data=research))

            dur = float(production.get("duration") or 0)
            if dur > SHORTS_HARD_LIMIT or (0 < dur < 15):
                raise StageError("video_production", f"rendered video is {dur:.1f}s (Shorts must be 15-{SHORTS_HARD_LIMIT:.0f}s)")

            seo = await self._stage(vid, "seo_optimization", lambda: self.seo_agent.execute(
                script=script, production=production))
            thumb = await self._stage(vid, "thumbnail_design", lambda: self.thumbnail_agent.execute(
                video_id=vid, script=script, creative_brief=creative, production=production), require_success=False)
            self._upload_artifact_to_hf(vid, thumb.get("thumbnail_path"), "thumbnail.jpg")

            self.state.update_state(vid, state=PipelineState.PUBLISHING, title=seo.get("title", ""))
            pub = await self._stage(vid, "publishing", lambda: self.publisher_agent.execute(
                video_path=production.get("video_path", ""), seo_data=seo,
                thumbnail_path=thumb.get("thumbnail_path"), video_type=task.video_type,
                captions_path=production.get("captions_srt")))

            yt_id, yt_url = pub.get("youtube_id", ""), pub.get("youtube_url", "")
            self.state.update_state(vid, state=PipelineState.COMPLETED, youtube_id=yt_id, youtube_url=yt_url)

            # Remember what we used so it is never repeated (live runs only).
            if self.config.general.dry_run:
                pass
            elif task.video_type == "news":
                used_urls = set(script.get("sources", []))
                self.history.mark_news([i for i in research.get("items", []) if i.get("source_url") in used_urls]
                                       or research.get("items", [])[:3])
            else:
                item = (research.get("items") or [{}])[0]
                self.history.mark_topic(item.get("seed") or item.get("title", ""), task.topic_category)
            if not self.config.general.dry_run:
                self.history.mark_video({"video_id": vid, "video_type": task.video_type, "title": seo.get("title", ""),
                                         "youtube_id": yt_id, "theme": creative.get("theme_name", ""),
                                         "duration": production.get("duration", 0)})

            caption = (f"{'🧪 DRY-RUN' if self.config.general.dry_run else '✅ Published'}: "
                       f"<b>{esc(seo.get('title', ''))}</b>\n{esc(yt_url)}")
            if self.config.telegram.send_video:
                self.notifier.send_video(production.get("video_path", ""), caption, thumb.get("thumbnail_path"))
            self._summary_cache[vid] = {"duration": production.get("duration", 0), "sources": script.get("sources", []),
                                        "llm": llm_used, "quality": quality.get("overall_score"),
                                        "voice": production.get("voice_provider", ""),
                                        "items": len(script.get("scenes", [])),
                                        "images": production.get("images_found", 0)}
            logger.info("✅ %s done: %s", vid, yt_url)

        except Exception as exc:
            stage = getattr(exc, "stage", "pipeline")
            logger.exception("❌ %s failed at %s: %s", vid, stage, exc)
            self.failures.append(f"{task.video_type} @ {stage}: {exc}")
            self.state.update_state(vid, state=PipelineState.FAILED, error_message=f"[{stage}] {exc}")
            self.notifier.send_message(TelegramReportBuilder.build_failure_alert(stage, vid, str(exc)))

        return self.state.get_video_state(vid)

    async def resume_pipeline(self, video_id: str) -> Optional[VideoState]:
        vs = self.state.get_video_state(video_id)
        if not vs:
            logger.error("Unknown video_id %s", video_id)
            return None
        task = VideoTask(vs.video_type, vs.topic_category, "", day_name=self._now().strftime("%A").lower())
        return await self.run_pipeline(task, video_id=video_id)

    async def run_daily(self, video_type_filter: str = "all") -> List[VideoState]:
        logger.info("=== YT Daily Shorts run started (dry_run=%s, strict=%s, llm=%d candidates) ===",
                    self.config.general.dry_run, self.config.general.strict_mode, len(self.llm.candidates))
        self._summary_cache = {}
        try:
            await self.analytics_agent.execute()
        except Exception as exc:
            logger.warning("Analytics refresh skipped: %s", exc)

        tasks = self.get_video_schedule()
        if video_type_filter not in ("all", "", None):
            tasks = [t for t in tasks if t.video_type == video_type_filter][:1]

        results: List[VideoState] = []
        for t in tasks:
            vs = await self.run_pipeline(t)
            if vs:
                results.append(vs)

        completed = []
        for r in results:
            if r.state == PipelineState.COMPLETED:
                extra = self._summary_cache.get(r.video_id, {})
                completed.append({"video_type": r.video_type, "title": r.title, "youtube_url": r.youtube_url, **extra})
        insights = ""
        try:
            insights = (await self.learning_agent.execute(video_type="news")).data.get("insights", "")
        except Exception:
            pass
        self.notifier.send_message(TelegramReportBuilder.build_daily_summary(
            completed, failed_count=len(results) - len(completed), dry_run=self.config.general.dry_run,
            failures=self.failures, insights=insights))
        logger.info("=== Run completed: %d ok, %d failed ===", len(completed), len(results) - len(completed))
        self._backup_state_to_hf()
        return results

    def _upload_artifact_to_hf(self, video_id: str, local_path: Any, name: str) -> None:
        """Add one late artefact (thumbnail, SEO json, ...) to the video's HF folder."""
        if not local_path or not Path(str(local_path)).exists():
            return
        try:
            from core.hf_storage import store_from_config

            store = store_from_config(self.config)
            if not store.enabled:
                return
            url = store.upload_file(local_path, f"videos/{self._now():%Y-%m-%d}/{video_id}/{name}")
            if url:
                logger.info("HF storage: %s -> %s", name, url)
        except Exception as exc:  # noqa: BLE001 — storage must never break a run
            logger.warning("HF artefact upload skipped (%s): %s", name, exc)

    def _backup_state_to_hf(self) -> None:
        """Mirror SQLite DB + history to the free HF dataset repo (survives runner resets)."""
        try:
            from core.hf_storage import store_from_config

            store = store_from_config(self.config)
            if not store.enabled:
                return
            paths = [getattr(self.config.database, "sqlite_path", ""),
                     getattr(self.config.database, "history_path", "")]
            urls = store.backup_state([p for p in paths if p])
            if urls:
                logger.info("HF storage: state backup %s", ", ".join(urls))
        except Exception as exc:  # noqa: BLE001
            logger.warning("HF state backup skipped: %s", exc)
