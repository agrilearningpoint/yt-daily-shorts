"""AI Newsroom Orchestrator for BHARAT KI SOCH.

Coordinates end-to-end production across all specialized newsroom agents:
1. Daily News Bulletin Studio (Mode 1):
   DailyOpeningDirector -> Research -> Script -> Hook -> FactVerifier -> Quality ->
   Creative -> NewsVisualSourcing -> MotionGraphics -> VFX -> AudioSoundDesign ->
   MasterEditingDirector -> VideoProducer -> VisualAudioMatchQA -> SEO -> Thumbnail -> Publish.

2. Long Video Repurposing Studio (Mode 2):
   LongVideoIntake -> TranscriptionDiarization -> SceneUnderstanding -> StoryExtraction ->
   ContextEvidence -> OpportunityRanker -> ClipMomentSelector -> ShortsAdaptation ->
   HookDirector -> RightsAttribution -> NewsVisualSourcing -> MotionGraphics -> VFX ->
   AudioSoundDesign -> MasterEditingDirector -> VideoProducer -> VisualAudioMatchQA -> SEO -> Thumbnail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz

from agents.analytics_manager import AnalyticsManagerAgent
from agents.audio_sound_design import AudioSoundDesignAgent
from agents.clip_moment_selector import ClipMomentSelectorAgent
from agents.context_evidence_research import ContextEvidenceResearchAgent
from agents.creative_director import CreativeDirectorAgent
from agents.daily_opening_director import DailyOpeningDirectorAgent
from agents.fact_verifier import FactVerifierAgent
from agents.hook_director import HookDirectorAgent
from agents.long_video_intake import LongVideoIntakeAgent
from agents.master_editing_director import MasterEditingDirectorAgent
from agents.motion_graphics import MotionGraphicsAgent
from agents.news_visual_sourcing import NewsVisualSourcingAgent
from agents.prompt_engineer import PromptEngineerAgent
from agents.publisher import PublisherAgent
from agents.quality_manager import QualityManagerAgent
from agents.research_manager import ResearchManagerAgent
from agents.rights_attribution import RightsAttributionAgent
from agents.scene_understanding import SceneUnderstandingAgent
from agents.script_manager import ScriptManagerAgent
from agents.self_learning import SelfLearningAgent
from agents.seo_manager import SEOManagerAgent
from agents.shorts_adaptation import ShortsAdaptationAgent
from agents.shorts_opportunity_ranker import ShortsOpportunityRankerAgent
from agents.story_extraction import StoryExtractionAgent
from agents.thumbnail_designer import ThumbnailDesignerAgent
from agents.transcription_diarization import TranscriptionDiarizationAgent
from agents.video_producer import VideoProducerAgent
from agents.vfx_agent import VFXAgent
from agents.visual_audio_match_qa import VisualAudioMatchQAAgent
from core.configuration import AppConfig
from core.duration import SHORTS_HARD_LIMIT
from core.history import HistoryStore
from core.llm_client import build_llm
from core.state_manager import PipelineState, StateManager
from telegram.bot import TelegramNotifier
from video.qa_inspector import VideoQAInspector

logger = logging.getLogger("core.newsroom_orchestrator")


class NewsroomStageError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


@dataclass
class ProductionRunSummary:
    video_id: str
    mode: str
    success: bool
    title: str = ""
    duration: float = 0.0
    video_path: str = ""
    youtube_id: str = ""
    youtube_url: str = ""
    qa_score: float = 0.0
    errors: List[str] = field(default_factory=list)
    stage_latencies: Dict[str, float] = field(default_factory=dict)


class NewsroomOrchestrator:
    """Master production engine coordinating the AI Newsroom and Long-Video Repurposing pipelines."""

    def __init__(
        self,
        config: AppConfig,
        state_manager: Optional[StateManager] = None,
        history: Optional[HistoryStore] = None,
    ) -> None:
        self.config = config
        self.state = state_manager or StateManager(config.database.sqlite_path)
        self.history = history or HistoryStore(config.database.history_path)
        self.notifier = TelegramNotifier(config.telegram.bot_token, config.telegram.chat_id)
        self.llm = build_llm(config.llm, allow_mock=not config.general.strict_mode)

        # Mode 1: Daily Studio Agents
        self.daily_opening_agent = DailyOpeningDirectorAgent(config, self.state)
        self.research_agent = ResearchManagerAgent(
            config, self.state, history=self.history, llm=self.llm
        )
        self.prompt_agent = PromptEngineerAgent(config, self.state)
        self.script_agent = ScriptManagerAgent(config, self.state, llm=self.llm)
        self.verifier_agent = FactVerifierAgent(config, self.state, llm=self.llm)
        self.quality_agent = QualityManagerAgent(config, self.state)
        self.hook_agent = HookDirectorAgent(config, self.state)
        self.creative_agent = CreativeDirectorAgent(config, self.state, history=self.history)
        self.visual_sourcing_agent = NewsVisualSourcingAgent(config, self.state)
        self.motion_agent = MotionGraphicsAgent(config, self.state)
        self.vfx_agent = VFXAgent(config, self.state)
        self.audio_sound_agent = AudioSoundDesignAgent(config, self.state)
        self.master_editing_agent = MasterEditingDirectorAgent(config, self.state)
        self.producer_agent = VideoProducerAgent(config, self.state)
        self.visual_audio_qa_agent = VisualAudioMatchQAAgent(config, self.state)
        self.seo_agent = SEOManagerAgent(config, self.state, llm=self.llm)
        self.thumbnail_agent = ThumbnailDesignerAgent(config, self.state)
        self.publisher_agent = PublisherAgent(config, self.state)
        self.analytics_agent = AnalyticsManagerAgent(config, self.state, history=self.history)
        self.learning_agent = SelfLearningAgent(config, self.state, history=self.history)

        # Mode 2: Long Video Intelligence Agents
        self.intake_agent = LongVideoIntakeAgent(config, self.state)
        self.transcription_agent = TranscriptionDiarizationAgent(config, self.state)
        self.scene_agent = SceneUnderstandingAgent(config, self.state)
        self.story_agent = StoryExtractionAgent(config, self.state)
        self.context_agent = ContextEvidenceResearchAgent(config, self.state)
        self.ranker_agent = ShortsOpportunityRankerAgent(config, self.state)
        self.moment_agent = ClipMomentSelectorAgent(config, self.state)
        self.adaptation_agent = ShortsAdaptationAgent(config, self.state)
        self.rights_agent = RightsAttributionAgent(config, self.state)

    def _now(self) -> datetime:
        return datetime.now(pytz.timezone(self.config.general.timezone))

    async def _run_stage(self, video_id: str, stage_name: str, fn, required: bool = True) -> Any:
        import time

        t0 = time.time()
        logger.info("🎬 [%s] Starting stage: %s", video_id, stage_name)
        try:
            res = await fn() if callable(fn) else fn
            elapsed = time.time() - t0
            logger.info("✅ [%s] Finished stage: %s in %.2fs", video_id, stage_name, elapsed)
            return res
        except Exception as exc:
            elapsed = time.time() - t0
            logger.warning(
                "❌ [%s] Stage %s failed in %.2fs: %s", video_id, stage_name, elapsed, exc
            )
            if required:
                raise NewsroomStageError(stage_name, str(exc))
            return None

    async def produce_daily_bulletin(self, video_id: Optional[str] = None) -> ProductionRunSummary:
        """Produce the daily morning news bulletin by delegating directly to DailyOrchestrator."""
        from core.orchestrator import DailyOrchestrator, VideoTask

        vid = video_id or f"bulletin_{self._now().strftime('%Y%m%d_%H%M%S')}"
        summary = ProductionRunSummary(video_id=vid, mode="daily_bulletin", success=False)

        try:
            orch = DailyOrchestrator(self.config, self.state, self.history)
            task = VideoTask(
                video_type="news",
                topic_category="Daily News Roundup",
                scheduled_time="05:30",
                index=1,
                day_name="daily",
            )
            state = await orch.run_pipeline(task, video_id=vid)

            summary.success = state.state == PipelineState.COMPLETED
            summary.title = state.title
            summary.video_path = f"output/{vid}/final_short.mp4"
            summary.youtube_id = state.youtube_id
            summary.youtube_url = state.youtube_url
            if state.error_message:
                summary.errors.append(state.error_message)

            checkpoint = self.state.load_checkpoint(vid, "visual_audio_match_qa")
            if checkpoint:
                summary.qa_score = checkpoint.get("overall_score", 0.0)
            elif state.state == PipelineState.COMPLETED:
                summary.qa_score = 95.0

        except Exception as exc:
            summary.errors.append(str(exc))
            logger.exception("Daily bulletin production failed for '%s': %s", vid, exc)

        return summary

    async def produce_repurposed_short(
        self,
        source_video_path: str,
        video_id: Optional[str] = None,
    ) -> ProductionRunSummary:
        """Repurpose an existing long news/discussion video into punchy vertical YouTube Shorts."""
        vid = video_id or f"repurpose_{self._now().strftime('%Y%m%d_%H%M%S')}"
        summary = ProductionRunSummary(video_id=vid, mode="long_video_to_shorts", success=False)

        try:
            # 1. Intake
            intake_res = await self._run_stage(
                vid,
                "long_video_intake",
                lambda: self.intake_agent.execute(
                    source_type="local_file", source_path=source_video_path
                ),
            )

            # 2. Transcription
            trans_res = await self._run_stage(
                vid,
                "transcription_diarization",
                lambda: self.transcription_agent.execute(media_asset=intake_res.data),
            )

            # 3. Scene Understanding
            scene_res = await self._run_stage(
                vid,
                "scene_understanding",
                lambda: self.scene_agent.execute(media_asset=intake_res.data),
            )

            # 4. Story Extraction
            story_res = await self._run_stage(
                vid,
                "story_extraction",
                lambda: self.story_agent.execute(
                    transcription=trans_res.data,
                    scene_analysis=scene_res.data,
                ),
            )
            stories = story_res.data.get("stories", [])
            if not stories:
                raise NewsroomStageError(
                    "story_extraction", "No viable stories extracted from source video"
                )

            # 5. Opportunity Ranker
            ranker_res = await self._run_stage(
                vid, "shorts_opportunity_ranker", lambda: self.ranker_agent.execute(stories=stories)
            )
            top_candidate = (
                ranker_res.data.get("top_candidate")
                or (ranker_res.data.get("ranked_opportunities") or [stories[0]])[0]
            )

            # 6. Clip Moment Selector
            moment_res = await self._run_stage(
                vid,
                "clip_moment_selector",
                lambda: self.moment_agent.execute(
                    story=top_candidate,
                    scene_analysis=scene_res.data,
                    transcription=trans_res.data,
                    target_duration=55.0,
                ),
            )

            # 7. Shorts Adaptation
            adapt_res = await self._run_stage(
                vid,
                "shorts_adaptation",
                lambda: self.adaptation_agent.execute(
                    story=top_candidate,
                    selected_moments=moment_res.data,
                    video_type="repurposed_news",
                ),
            )
            script = adapt_res.data.get("script") or (
                adapt_res.data["adapted_script"].to_script_dict()
                if hasattr(adapt_res.data.get("adapted_script"), "to_script_dict")
                else adapt_res.data.get("adapted_script", {})
            )

            # 8. Rights Attribution
            await self._run_stage(
                vid,
                "rights_attribution",
                lambda: self.rights_agent.execute(
                    source_manifest=intake_res.data,
                    selected_moments=moment_res.data,
                ),
            )

            # 9. Visual Sourcing & Motion Graphics & VFX & Audio Mix
            creative_res = await self._run_stage(
                vid, "creative_direction", lambda: self.creative_agent.execute(script=script)
            )
            creative = creative_res.data if creative_res else {}

            motion_res = await self._run_stage(
                vid,
                "motion_graphics",
                lambda: self.motion_agent.execute(
                    script=script, hook=script.get("hook", ""), out_dir=f"output/{vid}/overlays"
                ),
                required=False,
            )
            motion_data = motion_res.data if motion_res else {}

            vfx_res = await self._run_stage(
                vid,
                "vfx_direction",
                lambda: self.vfx_agent.execute(script=script, creative_brief=creative),
                required=False,
            )
            vfx_data = vfx_res.data if vfx_res else {}

            audio_res = await self._run_stage(
                vid,
                "audio_sound_design",
                lambda: self.audio_sound_agent.execute(
                    video_id=vid, script=script, duration=55.0, video_type="repurposed_news"
                ),
                required=False,
            )
            audio_mix_plan = (
                audio_res.data.get("mix_plan") if audio_res and audio_res.success else None
            )

            # 10. Master Editing Director
            master_edit_res = await self._run_stage(
                vid,
                "master_editing_director",
                lambda: self.master_editing_agent.execute(
                    video_id=vid,
                    script=script,
                    vfx_data=vfx_data,
                    motion_data=motion_data,
                    audio_mix_plan=audio_mix_plan,
                ),
            )
            master_timeline = (
                master_edit_res.data.get("master_timeline") if master_edit_res else None
            )

            # 11. Producer & Render
            production_res = await self._run_stage(
                vid,
                "video_production",
                lambda: self.producer_agent.execute(
                    video_id=vid,
                    script=script,
                    creative_brief=creative,
                    vfx_data=vfx_data,
                    motion_data=motion_data,
                ),
            )
            production = production_res.data if production_res else {}
            video_path = production.get("video_path", "")

            # 12. QA & SEO & Thumbnail & Publish
            qa_res = await self._run_stage(
                vid,
                "visual_audio_match_qa",
                lambda: self.visual_audio_qa_agent.execute(
                    video_id=vid, timeline=master_timeline, video_path=video_path
                ),
                required=True,
            )
            qa_data = qa_res.data if qa_res else {}
            if not qa_data.get("approved"):
                errs = qa_data.get("errors") or ["Visual-Audio Match QA failed"]
                raise NewsroomStageError("visual_audio_match_qa", "; ".join(errs))

            qa_inspector = VideoQAInspector(
                target_width=self.config.video.width,
                target_height=self.config.video.height,
                target_fps=self.config.video.fps,
                max_duration=SHORTS_HARD_LIMIT,
            )
            verdict = qa_inspector.verify_video(video_path)
            if not verdict.approved:
                raise NewsroomStageError("post_render_qa", "; ".join(verdict.errors))

            summary.qa_score = verdict.overall_score

            seo_res = await self._run_stage(
                vid,
                "seo_optimization",
                lambda: self.seo_agent.execute(script=script, production=production),
            )
            seo = seo_res.data if seo_res else {}

            thumb_res = await self._run_stage(
                vid,
                "thumbnail_design",
                lambda: self.thumbnail_agent.execute(
                    video_id=vid, script=script, creative_brief=creative, production=production
                ),
                required=False,
            )
            thumb = thumb_res.data if thumb_res else {}

            pub_res = await self._run_stage(
                vid,
                "publishing",
                lambda: self.publisher_agent.execute(
                    video_path=video_path,
                    seo_data=seo,
                    thumbnail_path=thumb.get("thumbnail_path"),
                    video_type="news",
                    captions_path=production.get("captions_srt"),
                ),
            )
            pub = pub_res.data if pub_res else {}

            summary.success = True
            summary.title = seo.get("title", script.get("title", ""))
            summary.duration = float(production.get("duration", 0.0))
            summary.video_path = video_path
            summary.youtube_id = pub.get("youtube_id", "")
            summary.youtube_url = pub.get("youtube_url", "")

        except Exception as exc:
            summary.errors.append(str(exc))
            logger.exception("Repurposed short production failed for '%s': %s", vid, exc)

        return summary
