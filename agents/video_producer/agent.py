"""Video Producer Agent — human-like voice, one photo per beat, motion graphics, render.

News:      hook card -> 25+ fast headline beats (photo + chip + counter) -> subscribe card
Knowledge: hook -> 4 story scenes -> (outro inside last scene)
No subtitles are burned in.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytz

from agents.base_agent import AgentResult, BaseAgent
from video.media_collector import MediaCollector
from video.renderer import SceneClip, VideoRenderer
from video.scene_composer import SceneComposer, compose_chip, compose_frame, compose_title_card
from video.tts import GeminiTTS, TTSEngine, probe_duration

HINDI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
CATEGORY_BADGES = {
    "monday": "राजनीति और नेता", "tuesday": "विज्ञान और तकनीक", "wednesday": "स्वास्थ्य और विज्ञान",
    "thursday": "महान व्यक्तित्व", "friday": "इतिहास और धरोहर", "saturday": "रोचक तथ्य",
    "sunday": "अर्थव्यवस्था और समाज",
}


def _stamp(path: str, text: str) -> None:
    """Small 'symbolic image' label on AI pictures (honest news practice)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        im = Image.open(path).convert("RGB")
        d = ImageDraw.Draw(im)
        font_path = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Mukta-Bold.ttf"
        font = ImageFont.truetype(str(font_path), 34) if font_path.exists() else ImageFont.load_default()
        w = d.textlength(text, font=font)
        x, y = im.width - w - 70, 560
        d.rounded_rectangle([x - 18, y - 8, x + w + 18, y + 50], radius=14, fill=(0, 0, 0))
        d.text((x, y), text, font=font, fill=(255, 255, 255))
        im.save(path, quality=92)
    except Exception:
        pass


class VideoProducerAgent(BaseAgent):
    name = "video_producer"

    def __init__(self, config, state_manager):
        super().__init__(config, state_manager)
        t = config.tts
        gemini = None
        if config.llm.gemini_api_key and "gemini" in t.provider_order:
            gemini = GeminiTTS(config.llm.gemini_api_key, t.gemini_models, t.gemini_voice, t.gemini_fallback_voice)
        self.tts = TTSEngine(voice=t.voice, rate=t.rate, pitch=t.pitch, fallback_voice=t.fallback_voice,
                             strict=config.general.strict_mode, provider_order=t.provider_order, gemini=gemini)
        self.media = MediaCollector(pexels_key=config.media.pexels_api_key, pixabay_key=config.media.pixabay_api_key,
                                    cache_dir=config.media.cache_dir, use_wikimedia=config.media.use_wikimedia,
                                    use_openverse=config.media.use_openverse,
                                    agnes_key=config.media.agnes_api_key, agnes_model=config.media.agnes_model,
                                    use_publisher_images=config.media.use_publisher_images)
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
        is_news = video_type == "news"
        out_dir = Path("output") / video_id
        out_dir.mkdir(parents=True, exist_ok=True)
        vcfg = self.config.video

        scenes: List[Dict[str, Any]] = script.get("scenes", [])
        hook = script.get("hook", "").strip()
        outro = script.get("outro", "").strip()

        # ---- beats (one voice segment each) + small visual parts inside every beat ----------------
        items = research.get("items", [])
        lead_image = items[0].get("image_url", "") if (not is_news and items) else ""
        topic_kw = (items[0].get("seed") or items[0].get("title", "")) if (not is_news and items) else ""
        by_url = {i.get("source_url"): i for i in items}
        beats: List[Dict[str, Any]] = []
        if hook:
            first = (scenes[0].get("parts") or [{}])[0] if scenes else {}
            beats.append({"kind": "hook", "text": hook, "chip": "", "category": "",
                          "parts": [{"say": hook, "visual": first.get("visual", "") or topic_kw,
                                     "entity": first.get("entity", "") or scenes[0].get("image_query", "") if scenes else "",
                                     "search": first.get("search", "") or topic_kw, "source": first.get("source", ""),
                                     "preferred": lead_image}]})
        for i, s in enumerate(scenes):
            parts = [dict(p) for p in (s.get("parts") or [])] or [{
                "say": s["narration"], "visual": s.get("visual_keywords", ""), "entity": s.get("image_query", ""),
                "search": s.get("visual_keywords", ""), "source": ""}]
            if is_news:
                url = (s.get("sources") or [""])[0]
                parts[0]["article"] = url
                it = by_url.get(url, {})
                parts[0]["publisher"] = it.get("image_url", "")
                parts[0]["publisher_name"] = it.get("source_name", "")
                parts[0]["article_page"] = url
            elif topic_kw:
                for p in parts:
                    if p.get("search") and topic_kw.lower().split()[0] not in p["search"].lower():
                        p["search"] = f"{topic_kw} {p['search']}"
            beats.append({"kind": "item", "text": s["narration"], "chip": s.get("on_screen_text", ""),
                          "category": s.get("category", ""), "parts": parts, "n": i + 1})
        if outro:
            beats.append({"kind": "outro", "text": outro, "chip": "", "category": "", "parts": []})

        # ---- 1. voice (human-like, one pass) ----------------------------------
        style = self.config.tts.news_style if is_news else self.config.tts.knowledge_style
        texts = [b["text"] for b in beats]
        voice = await self.tts.voice_beats(texts, str(out_dir), style=style)
        self.tts.dump_timings(texts, voice.durations, voice.provider, str(out_dir / "timings.json"))
        total_audio = sum(voice.durations)
        tempo = 1.0
        max_d = vcfg.news_max_duration if is_news else vcfg.max_duration
        if total_audio > max_d:
            tempo = min(total_audio / max_d, 1.25)
            self.logger.warning("Voice %.1fs > %ss — tempo %.3f", total_audio, max_d, tempo)

        # ---- 2. one picture per small part (parallel) -------------------------
        specs = []
        for i, b in enumerate(beats):
            for k, p in enumerate(b["parts"]):
                specs.append({**p, "dest": str(out_dir / f"src_{i:03d}_{k}.jpg"), "_beat": i, "_part": k})
        found = self.media.find_visuals(specs, mode="news" if is_news else "knowledge")
        assets: Dict[tuple, Any] = {(sp["_beat"], sp["_part"]): a for sp, a in zip(specs, found)}

        # ---- 3. motion-graphics layers --------------------------------------
        composer = SceneComposer(theme, channel_name=self.config.general.channel_name)
        default_badge = "आज की बड़ी खबरें" if is_news else CATEGORY_BADGES.get(research.get("day_name", ""), "रोचक जानकारी")
        date_label = self._date_label()
        n_items = sum(1 for b in beats if b["kind"] == "item")
        total_clips = sum(max(1, len(b["parts"])) for b in beats)
        clips: List[SceneClip] = []
        credits: List[str] = []
        first_image = None
        ci = 0
        for i, (b, dur) in enumerate(zip(beats, voice.durations)):
            parts = b["parts"] or [{"say": b["text"]}]
            weights = [max(4, len(p.get("say", ""))) for p in parts]
            for k, p in enumerate(parts):
                pdur = dur * weights[k] / sum(weights)
                asset = assets.get((i, k))
                if asset:
                    if asset.source != "ai":
                        credits.append(asset.credit + (f" — {asset.page_url}" if asset.page_url else ""))
                    first_image = first_image or asset.path
                bg = str(out_dir / f"bg_{i:03d}_{k}.jpg")
                chip = None
                if b["kind"] == "hook":
                    big = script.get("title", "")[:60] if is_news else (scenes[0].get("on_screen_text", "") if scenes else "")
                    compose_title_card(composer, bg, big or hook[:40], date_label, asset.path if asset else None, seed=ci)
                elif b["kind"] == "outro":
                    compose_title_card(composer, bg, "सब्सक्राइब करें", self.config.general.channel_name,
                                       first_image, seed=ci)
                else:
                    composer.compose_background(asset.path if asset else None, bg, seed=ci,
                                                card_text="" if asset else b["chip"])
                    if asset and asset.source == "ai":
                        _stamp(bg, "सांकेतिक चित्र (AI)")
                    if vcfg.show_headline_chips and b["chip"] and asset and k == 0:
                        chip = compose_chip(composer, str(out_dir / f"chip_{i:03d}.png"), b["chip"])
                counter = f"{b['n']:02d}/{n_items}" if (is_news and b["kind"] == "item") else ""
                badge = (b.get("category") or default_badge) if b["kind"] != "outro" else ""
                frame = compose_frame(composer, str(out_dir / f"ov_{i:03d}_{k}.png"), badge, ci, total_clips,
                                      counter, date_label if not is_news else "")
                clips.append(SceneClip(bg, frame, pdur, chip=chip, story_start=(k == 0)))
                ci += 1

        # ---- 4. render ---------------------------------------------------------
        final_path = str(out_dir / "final_short.mp4")
        self.renderer.render(clips, voice.audio_path, final_path, music=vcfg.background_music,
                             music_volume=vcfg.music_volume, tempo=tempo, sfx=vcfg.sound_effects)

        duration = probe_duration(final_path)
        ok = Path(final_path).exists() and Path(final_path).stat().st_size > 200_000 and duration >= 10
        return AgentResult(
            success=ok,
            data={"video_path": final_path, "audio_path": voice.audio_path, "duration": round(duration, 1),
                  "first_image": first_image, "media_credits": list(dict.fromkeys(credits)),
                  "voice_provider": voice.provider, "beats": len(beats), "visual_parts": len(clips),
                  "images_found": sum(1 for a in assets.values() if a),
                  "ai_images": sum(1 for a in assets.values() if a and a.source == "ai")},
            errors=[] if ok else ["rendered video missing or too small"],
        )
