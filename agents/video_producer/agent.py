"""Video Producer Agent — voice, visuals, word-synced captions and final render."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytz

from agents.base_agent import AgentResult, BaseAgent
from video.media_collector import MediaCollector
from video.renderer import SceneClip, VideoRenderer
from video.scene_composer import SceneComposer
from video.subtitle_generator import SubtitleGenerator
from video.tts import TTSEngine

HINDI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
CATEGORY_BADGES = {
    "monday": "राजनीति और नेता", "tuesday": "विज्ञान और तकनीक", "wednesday": "स्वास्थ्य और विज्ञान",
    "thursday": "महान व्यक्तित्व", "friday": "इतिहास और धरोहर", "saturday": "रोचक तथ्य",
    "sunday": "अर्थव्यवस्था और समाज",
}


class VideoProducerAgent(BaseAgent):
    name = "video_producer"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        self.tts = TTSEngine(voice=config.tts.voice, rate=config.tts.rate, pitch=config.tts.pitch,
                             fallback_voice=config.tts.fallback_voice, strict=config.general.strict_mode)
        self.media = MediaCollector(pexels_key=config.media.pexels_api_key, pixabay_key=config.media.pixabay_api_key,
                                    cache_dir=config.media.cache_dir, use_wikimedia=config.media.use_wikimedia,
                                    use_openverse=config.media.use_openverse)
        self.subs = SubtitleGenerator()
        self.renderer = VideoRenderer(config.video.width, config.video.height, config.video.fps)

    def _date_label(self) -> str:
        now = datetime.now(pytz.timezone(self.config.general.timezone))
        return f"{now.day} {HINDI_MONTHS[now.month - 1]} {now.year}"

    async def execute(self, **kwargs: Any) -> AgentResult:
        script: Dict[str, Any] = kwargs.get("script", {}) or {}
        theme: Dict[str, Any] = kwargs.get("creative_brief", {}) or {}
        research: Dict[str, Any] = kwargs.get("research_data", {}) or {}
        video_id = kwargs.get("video_id", "daily_short")
        video_type = script.get("video_type", "news")
        out_dir = Path("output") / video_id
        out_dir.mkdir(parents=True, exist_ok=True)

        scenes: List[Dict[str, Any]] = script.get("scenes", [])
        hook = script.get("hook", "").strip()

        # 1. Voice, one segment per beat (hook + scenes) -----------------------
        texts = ([hook] if hook else []) + [s["narration"] for s in scenes]
        segments = await self.tts.synthesize_segments(texts, str(out_dir))
        voice_path = self.tts.concat_audio(segments, str(out_dir / "voiceover.m4a"))
        self.tts.dump_timings(segments, str(out_dir / "timings.json"))
        total_audio = sum(s.duration for s in segments)

        # Keep the Short inside the limit: speed up slightly if needed (max 15%).
        tempo = 1.0
        max_d = float(self.config.video.max_duration)
        if total_audio > max_d:
            tempo = min(total_audio / max_d, 1.15)
            self.logger.warning("Audio %.1fs > %.0fs, applying tempo %.3f", total_audio, max_d, tempo)

        # 2. Absolute word timings -> captions ---------------------------------
        words = []
        t0 = 0.0
        for seg in segments:
            for w in seg.words:
                words.append({"word": w.word, "start": (t0 + w.start) / tempo, "end": (t0 + w.end) / tempo})
            t0 += seg.duration
        captions = self.subs.generate_ass(words, str(out_dir / "captions.ass"),
                                          highlight_color=theme.get("caption_highlight", "#FFD60A"))
        srt = self.subs.generate_srt_from_words(words, str(out_dir / "subtitles.srt"))

        # 3. Visuals ----------------------------------------------------------
        composer = SceneComposer(theme, channel_name=self.config.general.channel_name)
        items = research.get("items", [])
        lead_image = items[0].get("image_url", "") if (video_type == "knowledge" and items) else ""
        topic_kw = (items[0].get("seed") or items[0].get("title", "")) if (video_type == "knowledge" and items) else ""
        badge = "आज की बड़ी खबरें" if video_type == "news" else CATEGORY_BADGES.get(research.get("day_name", ""), "रोचक जानकारी")
        date_label = self._date_label()

        beats = []
        if hook:
            beats.append({"headline": scenes[0].get("on_screen_text", "") if video_type == "knowledge" else script.get("title", "")[:60],
                          "keywords": scenes[0].get("visual_keywords", "") if scenes else topic_kw,
                          "preferred": lead_image})
        for i, s in enumerate(scenes):
            kw = s.get("visual_keywords", "")
            if video_type == "knowledge" and topic_kw and topic_kw.lower().split()[0] not in kw.lower():
                kw = f"{topic_kw} {kw}"
            beats.append({"headline": s.get("on_screen_text", ""), "keywords": kw,
                          "preferred": lead_image if (i == 0 and not hook) else ""})

        clips: List[SceneClip] = []
        credits: List[str] = []
        first_image = None
        for i, (beat, seg) in enumerate(zip(beats, segments)):
            asset = self.media.find_image(beat["keywords"], str(out_dir / f"src_{i:02d}.jpg"), beat["preferred"])
            if asset:
                credits.append(asset.credit + (f" — {asset.page_url}" if asset.page_url else ""))
                first_image = first_image or asset.path
            bg = composer.compose_background(asset.path if asset else None, str(out_dir / f"bg_{i:02d}.jpg"),
                                             seed=i, card_text="" if asset else beat["headline"])
            ov = composer.compose_overlay(str(out_dir / f"ov_{i:02d}.png"),
                                          headline=beat["headline"] if asset else "",
                                          badge=badge, index=i, total=len(beats), date_label=date_label)
            clips.append(SceneClip(bg, ov, seg.duration))

        # 4. Render -------------------------------------------------------------
        final_path = str(out_dir / "final_short.mp4")
        self.renderer.render(clips, voice_path, captions, final_path, transition=theme.get("transition", "fade"),
                             music=self.config.video.background_music, music_volume=self.config.video.music_volume,
                             tempo=tempo)

        from video.tts import probe_duration
        duration = probe_duration(final_path)
        ok = Path(final_path).exists() and Path(final_path).stat().st_size > 200_000 and duration >= 10
        return AgentResult(
            success=ok,
            data={"video_path": final_path, "audio_path": voice_path, "subtitle_path": srt,
                  "captions_path": captions, "duration": round(duration, 1), "first_image": first_image,
                  "media_credits": list(dict.fromkeys(credits))},
            errors=[] if ok else ["rendered video missing or too small"],
        )
