"""Main pipeline orchestrator.

Coordinates the daily video production pipeline by:
1. Determining today's video schedule.
2. Invoking the multi-agent pipeline in sequence with checkpointing.
3. Reporting status and links via Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

from core.configuration import AppConfig
from core.state_manager import PipelineState, StateManager, VideoState

# Agent imports
from agents.research_manager import ResearchManagerAgent
from agents.prompt_engineer import PromptEngineerAgent
from agents.script_manager import ScriptManagerAgent
from agents.fact_verifier import FactVerifierAgent
from agents.quality_manager import QualityManagerAgent
from agents.creative_director import CreativeDirectorAgent
from agents.video_producer import VideoProducerAgent
from agents.seo_manager import SEOManagerAgent
from agents.thumbnail_designer import ThumbnailDesignerAgent
from agents.publisher import PublisherAgent
from agents.analytics_manager import AnalyticsManagerAgent
from agents.self_learning import SelfLearningAgent

# Telegram
from telegram.bot import TelegramNotifier
from telegram.reports import TelegramReportBuilder

logger = logging.getLogger("core.orchestrator")


@dataclass
class VideoTask:
    """A scheduled video production task for today."""
    video_type: str          # "news" | "knowledge"
    topic_category: str      # e.g. "Science and Technology"
    scheduled_time: str      # HH:MM IST
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


class DailyOrchestrator:
    """Coordinates the end-to-end multi-agent daily video pipeline."""

    def __init__(self, config: AppConfig, state_manager: Optional[StateManager] = None) -> None:
        self.config = config
        self.state = state_manager or StateManager(config.database.sqlite_path)
        self.notifier = TelegramNotifier(
            bot_token=config.telegram.bot_token,
            chat_id=config.telegram.chat_id
        )

        # Initialize all 12 agents
        self.research_agent = ResearchManagerAgent(config, self.state)
        self.prompt_agent = PromptEngineerAgent(config, self.state)
        self.script_agent = ScriptManagerAgent(config, self.state)
        self.verifier_agent = FactVerifierAgent(config, self.state)
        self.quality_agent = QualityManagerAgent(config, self.state)
        self.creative_agent = CreativeDirectorAgent(config, self.state)
        self.producer_agent = VideoProducerAgent(config, self.state)
        self.seo_agent = SEOManagerAgent(config, self.state)
        self.thumbnail_agent = ThumbnailDesignerAgent(config, self.state)
        self.publisher_agent = PublisherAgent(config, self.state)
        self.analytics_agent = AnalyticsManagerAgent(config, self.state)
        self.learning_agent = SelfLearningAgent(config, self.state)

    def get_video_schedule(self) -> List[VideoTask]:
        """Determine today's videos based on editorial calendar."""
        tz = pytz.timezone(self.config.general.timezone)
        now = datetime.now(tz)
        day_name = now.strftime("%A")

        tasks: List[VideoTask] = [
            VideoTask(
                video_type="news",
                topic_category="Daily News Roundup",
                scheduled_time="06:00",
                priority=1,
            ),
            VideoTask(
                video_type="knowledge",
                topic_category=self.config.editorial_calendar.get_today_category(day_name),
                scheduled_time="14:00",
                priority=2,
            )
        ]

        if self.config.general.max_video_count >= 3:
            tasks.append(VideoTask(
                video_type="knowledge",
                topic_category=f"{self.config.editorial_calendar.get_today_category(day_name)} - Spotlight",
                scheduled_time="18:00",
                priority=3,
            ))

        return tasks[: self.config.general.daily_video_count]

    async def run_pipeline(self, task: VideoTask) -> VideoState:
        """Run the full multi-agent pipeline for a single video."""
        vs = self.state.create_video_state(
            video_type=task.video_type,
            topic_category=task.topic_category,
        )
        video_id = vs.video_id
        logger.info("🎬 Launching video pipeline: ID=%s [%s - %s]", video_id, task.video_type, task.topic_category)

        context: Dict[str, Any] = {"video_id": video_id, "video_type": task.video_type, "topic_category": task.topic_category}

        try:
            # 1. Research Stage
            res_data = self.state.load_checkpoint(video_id, "research")
            if not res_data:
                self.state.update_state(video_id, state=PipelineState.RESEARCHING)
                res_out = await self.research_agent.execute(video_type=task.video_type, topic_category=task.topic_category)
                res_data = res_out.data
                self.state.save_checkpoint(video_id, "research", res_data)
            context["research_data"] = res_data

            # 2. Prompt Engineering Stage
            prompt_data = self.state.load_checkpoint(video_id, "prompt_engineering")
            if not prompt_data:
                prompt_out = await self.prompt_agent.execute(video_type=task.video_type, research_data=res_data)
                prompt_data = prompt_out.data
                self.state.save_checkpoint(video_id, "prompt_engineering", prompt_data)
            context["prompt_instructions"] = prompt_data.get("prompt", "")

            # 3. Script Generation Stage
            script_data = self.state.load_checkpoint(video_id, "script_generation")
            if not script_data:
                self.state.update_state(video_id, state=PipelineState.SCRIPTING)
                script_out = await self.script_agent.execute(
                    video_type=task.video_type,
                    research_data=res_data,
                    prompt_instructions=context["prompt_instructions"]
                )
                if not script_out.success:
                    raise RuntimeError(f"Script generation failed: {script_out.errors}")
                script_data = script_out.data.get("script", {})
                self.state.save_checkpoint(video_id, "script_generation", script_data)
            context["script"] = script_data
            self.state.update_state(video_id, title=script_data.get("title", ""))

            # 4. Fact Verification Stage
            verif_data = self.state.load_checkpoint(video_id, "fact_verification")
            if not verif_data:
                self.state.update_state(video_id, state=PipelineState.VERIFYING)
                verif_out = await self.verifier_agent.execute(script=context["script"], research_data=res_data)
                verif_data = verif_out.data
                self.state.save_checkpoint(video_id, "fact_verification", verif_data)
            context["verification"] = verif_data

            # 5. Quality Manager Stage
            quality_data = self.state.load_checkpoint(video_id, "quality_check")
            if not quality_data:
                quality_out = await self.quality_agent.execute(script=context["script"], verification=verif_data)
                quality_data = quality_out.data
                self.state.save_checkpoint(video_id, "quality_check", quality_data)
            context["quality"] = quality_data

            # 6. Creative Direction Stage
            creative_data = self.state.load_checkpoint(video_id, "creative_direction")
            if not creative_data:
                creative_out = await self.creative_agent.execute(script=context["script"])
                creative_data = creative_out.data
                self.state.save_checkpoint(video_id, "creative_direction", creative_data)
            context["creative_brief"] = creative_data

            # 7. Video Production Stage (TTS + Visuals + Subtitles + Render)
            prod_data = self.state.load_checkpoint(video_id, "video_production")
            if not prod_data:
                self.state.update_state(video_id, state=PipelineState.RENDERING)
                prod_out = await self.producer_agent.execute(
                    video_id=video_id,
                    script=context["script"],
                    creative_brief=creative_data
                )
                if not prod_out.success:
                    raise RuntimeError("Video production / rendering failed")
                prod_data = prod_out.data
                self.state.save_checkpoint(video_id, "video_production", prod_data)
            context["production"] = prod_data

            # 8. SEO Metadata Stage
            seo_data = self.state.load_checkpoint(video_id, "seo_optimization")
            if not seo_data:
                seo_out = await self.seo_agent.execute(script=context["script"])
                seo_data = seo_out.data
                self.state.save_checkpoint(video_id, "seo_optimization", seo_data)
            context["seo"] = seo_data

            # 9. Thumbnail Designer Stage
            thumb_data = self.state.load_checkpoint(video_id, "thumbnail_design")
            if not thumb_data:
                thumb_out = await self.thumbnail_agent.execute(
                    video_id=video_id,
                    script=context["script"],
                    creative_brief=creative_data
                )
                thumb_data = thumb_out.data
                self.state.save_checkpoint(video_id, "thumbnail_design", thumb_data)
            context["thumbnail"] = thumb_data

            # 10. Publishing Stage
            pub_data = self.state.load_checkpoint(video_id, "publishing")
            if not pub_data:
                self.state.update_state(video_id, state=PipelineState.PUBLISHING)
                pub_out = await self.publisher_agent.execute(
                    video_path=prod_data.get("video_path", ""),
                    seo_data=seo_data
                )
                pub_data = pub_out.data
                self.state.save_checkpoint(video_id, "publishing", pub_data)

            yt_id = pub_data.get("youtube_id", "")
            yt_url = pub_data.get("youtube_url", "")

            # Mark Completed
            self.state.update_state(
                video_id,
                state=PipelineState.COMPLETED,
                youtube_id=yt_id,
                youtube_url=yt_url
            )
            logger.info("✅ Video pipeline SUCCESS for %s (URL: %s)", video_id, yt_url)

        except Exception as exc:
            logger.error("❌ Pipeline failed for %s: %s", video_id, exc)
            self.state.update_state(video_id, state=PipelineState.FAILED, error_message=str(exc))
            self.notifier.send_message(
                TelegramReportBuilder.build_failure_alert("production_pipeline", video_id, str(exc))
            )

        return self.state.get_video_state(video_id)

    async def run_daily(self, video_type_filter: str = "all") -> List[VideoState]:
        """Execute scheduled videos for the day and broadcast summary report."""
        logger.info("=== YT Daily Shorts Automated Run Started ===")
        all_tasks = self.get_video_schedule()

        if video_type_filter != "all":
            tasks = [t for t in all_tasks if t.video_type == video_type_filter]
        else:
            tasks = all_tasks

        results: List[VideoState] = []
        for t in tasks:
            vs = await self.run_pipeline(t)
            if vs:
                results.append(vs)

        # Broadcast Daily Telegram Report
        completed_info = []
        failed_count = 0
        for r in results:
            if r.state == PipelineState.COMPLETED:
                completed_info.append({
                    "video_type": r.video_type,
                    "title": r.title,
                    "youtube_url": r.youtube_url,
                    "duration": 55.0,
                    "sources": ["https://pib.gov.in"]
                })
            else:
                failed_count += 1

        summary_msg = TelegramReportBuilder.build_daily_summary(
            completed_videos=completed_info,
            failed_count=failed_count,
            dry_run=self.config.general.dry_run
        )
        self.notifier.send_message(summary_msg)

        logger.info("=== YT Daily Shorts Automated Run Completed ===")
        return results
