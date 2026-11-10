"""Video Producer Agent — human-like voice, one photo per beat, motion graphics, render.

News:      hook card -> 25+ fast headline beats (photo + chip + counter) -> subscribe card
Knowledge: hook -> 4 story scenes -> (outro inside last scene)
No subtitles are burned in.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List

import pytz

from agents.base_agent import AgentResult, BaseAgent
from video.vision_check import make_vision_check
from video.media_collector import MediaCollector
from video.renderer import SceneClip, VideoRenderer
from video.scene_composer import (SceneComposer, compose_chip, compose_frame, compose_ticker,
                                  compose_title_card)
from video.editor_director import EditorDirector
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
                                    use_publisher_images=config.media.use_publisher_images,
                                    use_news_photos=getattr(config.media, "use_news_photos", True),
                                    cf_token=getattr(config.media, "cf_api_token", ""),
                                    cf_account=getattr(config.media, "cf_account_id", ""),
                                    hf_token=getattr(config.media, "hf_token", ""),
                                    vision=(make_vision_check(config.llm.gemini_api_key)
                                            if getattr(config.media, "vision_check", True) else None))
        self.renderer = VideoRenderer(config.video.width, config.video.height, config.video.fps)
        self.renderer.depth_motion = bool(getattr(config.video, "depth_motion", True))

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
        spoken = getattr(self.config.general, "channel_name_spoken", "") or self.config.general.channel_name
        # Fixed closing line: ask for like + subscribe and say the channel's name.
        outro = (f"खबरें पसंद आईं तो वीडियो को लाइक कीजिए, और रोज़ की खबरों के लिए {spoken} को सब्सक्राइब कीजिए!"
                 if is_news else
                 f"जानकारी अच्छी लगी तो लाइक कीजिए, और ऐसी रोचक बातों के लिए {spoken} को सब्सक्राइब कीजिए!")
        script["outro"] = outro

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
                nq = it.get("title") or s.get("headline") or s.get("on_screen_text", "")
                for p in parts:
                    p["news_query"] = nq
            elif topic_kw:
                for p in parts:
                    if p.get("search") and topic_kw.lower().split()[0] not in p["search"].lower():
                        p["search"] = f"{topic_kw} {p['search']}"
            beats.append({"kind": "item", "text": s["narration"], "chip": s.get("on_screen_text", ""),
                          "category": s.get("category", ""), "parts": parts, "n": i + 1})
        if is_news and any(s.get("section") for s in scenes):
            # Two sections only, announced by the anchor like a TV bulletin.
            withsec, seen = [], set()
            for b in beats:
                sec = scenes[b["n"] - 1].get("section", "national") if b["kind"] == "item" else ""
                if sec and sec not in seen:
                    seen.add(sec)
                    intl = sec == "international"
                    withsec.append({"kind": "section", "text": "अब दुनिया की बड़ी खबरें।" if intl
                                    else "पहले देश की बड़ी खबरें।",
                                    "big": "अंतरराष्ट्रीय" if intl else "राष्ट्रीय",
                                    "small": "दुनिया की खबरें" if intl else "देश की खबरें",
                                    "chip": "", "category": "", "parts": [], "section": sec})
                if b["kind"] == "item":
                    b["section"] = sec
                withsec.append(b)
            beats = withsec
            sec_total: Dict[str, int] = {}
            for b in beats:
                if b["kind"] == "item":
                    sec_total[b["section"]] = sec_total.get(b["section"], 0) + 1
                    b["sec_n"] = sec_total[b["section"]]
            for b in beats:
                if b["kind"] == "item":
                    b["sec_of"] = sec_total[b["section"]]
        if outro:
            beats.append({"kind": "outro", "text": outro, "chip": "", "category": "", "parts": []})

        _dash = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})
        for b in beats:  # fonts lack the special hyphens (shows as a box)
            b["chip"] = (b.get("chip") or "").translate(_dash)
            b["category"] = (b.get("category") or "").translate(_dash)
        # _clean_dash
        # ---- 1. voice (human-like, one pass) ----------------------------------
        style = self.config.tts.news_style if is_news else self.config.tts.knowledge_style
        # Voice is made per small PART (the line each picture belongs to), so every picture changes
        # exactly when its own line starts: no more "voice about X over a photo of Y".
        seg_texts: List[str] = []
        seg_owner: List[tuple] = []
        for i, b in enumerate(beats):
            says = [p.get("say", "").strip() for p in b["parts"]] if b["parts"] else []
            if len(says) > 1 and all(says):
                for k, t in enumerate(says):
                    seg_texts.append(t)
                    seg_owner.append((i, k))
            else:
                seg_texts.append(b["text"])
                seg_owner.append((i, 0))
        voice = await self.tts.voice_beats(seg_texts, str(out_dir), style=style)
        self.tts.dump_timings(seg_texts, voice.durations, voice.provider, str(out_dir / "timings.json"))
        part_dur: Dict[tuple, float] = {}
        beat_dur = [0.0] * len(beats)
        for (i, k), d in zip(seg_owner, voice.durations):
            part_dur[(i, k)] = d
            beat_dur[i] += d
        total_audio = sum(voice.durations)
        tempo = 1.0
        max_d = vcfg.news_max_duration if is_news else vcfg.max_duration
        if total_audio > max_d:
            tempo = min(total_audio / max_d, 1.06)   # never chipmunk the anchor
            self.logger.warning("Voice %.1fs > %ss — tempo %.3f", total_audio, max_d, tempo)

        # ---- 2. one picture per small part (parallel) -------------------------
        specs = []
        for i, b in enumerate(beats):
            for k, p in enumerate(b["parts"]):
                specs.append({**p, "dest": str(out_dir / f"src_{i:03d}_{k}.jpg"), "_beat": i, "_part": k})
        found = self.media.find_visuals(specs, mode="news" if is_news else "knowledge")
        assets: Dict[tuple, Any] = {(sp["_beat"], sp["_part"]): a for sp, a in zip(specs, found)}
        # A part with no matching picture keeps its story's own picture (never a random one).
        for i, b in enumerate(beats):
            n = len(b["parts"])
            for k in range(n):
                if not assets.get((i, k)):
                    near = [assets.get((i, j)) for j in sorted(range(n), key=lambda j: abs(j - k)) if j != k]
                    assets[(i, k)] = next((a for a in near if a), None)

        # ---- 3. motion-graphics layers --------------------------------------
        # Editor Director: today's look (different every day, learns from yesterday's review)
        editor = EditorDirector(self.config.llm.gemini_api_key)
        recipe = editor.plan("news" if is_news else "knowledge")
        theme = EditorDirector.theme(recipe, theme)
        composer = SceneComposer(theme, channel_name=self.config.general.channel_name)
        self.renderer.recipe = recipe
        ticker_y = 0
        self.renderer.ticker = None
        if is_news and recipe.get("ticker"):
            heads = [b["chip"] for b in beats if b["kind"] == "item" and b.get("chip")]
            if heads:
                self.renderer.ticker = compose_ticker(composer, str(out_dir / "ticker.png"), heads)
                ticker_y = self.renderer.ticker_y
        fx_cycle = recipe.get("cut_fx") or ["flash"]
        default_badge = "आज की बड़ी खबरें" if is_news else CATEGORY_BADGES.get(research.get("day_name", ""), "रोचक जानकारी")
        date_label = self._date_label()
        n_items = sum(1 for b in beats if b["kind"] == "item")
        total_clips = len(seg_owner)
        clips: List[SceneClip] = []
        clip_meta: List[Dict[str, Any]] = []
        credits: List[str] = []
        first_image = None
        ci = 0
        for i, (b, dur) in enumerate(zip(beats, beat_dur)):
            parts = b["parts"] or [{"say": b["text"]}]
            if not all((i, k) in part_dur for k in range(len(parts))):
                parts = parts[:1]  # voiced as one line -> one picture for the whole line
            for k, p in enumerate(parts):
                pdur = part_dur.get((i, k), dur)
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
                elif b["kind"] == "section":
                    nxt = next((assets.get((j, 0)) for j in range(i + 1, len(beats)) if assets.get((j, 0))), None)
                    compose_title_card(composer, bg, b["big"], b["small"], nxt.path if nxt else first_image, seed=ci)
                elif b["kind"] == "outro":
                    compose_title_card(composer, bg, "लाइक + सब्सक्राइब", self.config.general.channel_name,
                                       first_image, seed=ci)
                else:
                    composer.compose_background(asset.path if asset else None, bg, seed=ci,
                                                card_text="" if asset else b["chip"])
                    if asset and asset.source == "ai":
                        _stamp(bg, "सांकेतिक चित्र (AI)")
                    if vcfg.show_headline_chips and b["chip"] and asset and k == 0:
                        chip = compose_chip(composer, str(out_dir / f"chip_{i:03d}.png"), b["chip"])
                if is_news and b["kind"] == "item" and b.get("sec_n"):
                    counter = f"{b['sec_n']:02d}/{b['sec_of']}"
                else:
                    counter = f"{b['n']:02d}/{n_items}" if (is_news and b["kind"] == "item") else ""
                badge = (b.get("category") or default_badge) if b["kind"] not in ("outro", "section") else ""
                frame = compose_frame(composer, str(out_dir / f"ov_{i:03d}_{k}.png"), badge, ci, total_clips,
                                      counter, date_label if not is_news else "",
                                      ticker_y=ticker_y if b["kind"] == "item" else 0,
                                      stat=_stat(p.get("say", "")) if b["kind"] == "item" and k > 0 else "")
                if b["kind"] in ("section", "outro"):
                    fx = "dip"
                elif k == 0:  # a new story: one clean broadcast transition
                    fx = fx_cycle[b.get("n", ci) % len(fx_cycle)]
                else:         # next line of the same story: straight cut, like TV news
                    fx = "cut"
                clips.append(SceneClip(bg, frame, pdur, chip=chip, story_start=(k == 0), fx=fx,
                                       ticker=bool(ticker_y) and b["kind"] == "item",
                                       video=(asset.video if asset and b["kind"] == "item"
                                              and getattr(asset, "video", "") else ""),
                                       depth=bool(asset and b["kind"] == "item" and asset.source != "ai")))
                clip_meta.append({"beat": i, "part": k, "kind": b["kind"], "bg": bg, "chip": b["chip"],
                                  "spec": dict(p, _part=k), "asset": asset})
                ci += 1

        # ---- 4. render ---------------------------------------------------------
        final_path = str(out_dir / "final_short.mp4")
        captions = srt_path = None
        if getattr(vcfg, "burn_captions", True):
            try:
                captions, srt_path = self._captions(clips, clip_meta, tempo, out_dir)
            except Exception as exc:
                self.logger.warning("captions skipped: %s", exc)
        self._captions_ass = captions
        self.renderer.render(clips, voice.audio_path, final_path, music=vcfg.background_music,
                             music_volume=vcfg.music_volume, tempo=tempo, sfx=vcfg.sound_effects,
                             captions=captions)

        try:
            review = editor.review(final_path, recipe, str(out_dir), learn=False)
        except Exception as exc:
            review = {"score": None, "notes": [str(exc)[:100]], "bad_tiles": []}
        # ---- 5. scene-level re-edit: replace the pictures the editor flagged, render once more ----
        try:
            final_path, review = self._reedit(editor, recipe, review, clips, clip_meta, composer, voice, vcfg,
                                              tempo, final_path, out_dir)
        except Exception as exc:
            self.logger.warning("re-edit skipped: %s", exc)
        try:
            editor._learn(recipe, review)
        except Exception:
            pass
        duration = probe_duration(final_path)
        qa = _render_qa(final_path)
        self.logger.info("Render QA: %s", qa)
        ok = Path(final_path).exists() and Path(final_path).stat().st_size > 200_000 and duration >= 10
        return AgentResult(
            success=ok,
            data={"video_path": final_path, "audio_path": voice.audio_path, "captions_srt": srt_path, "duration": round(duration, 1),
                  "first_image": first_image, "media_credits": list(dict.fromkeys(credits)),
                  "voice_provider": voice.provider, "editor_recipe": {k: v for k, v in recipe.items() if k != "notes"},
                  "editor_review": review, "render_qa": qa, "beats": len(beats), "visual_parts": len(clips),
                  "images_found": sum(1 for a in assets.values() if a),
                  "ai_images": sum(1 for a in assets.values() if a and a.source == "ai")},
            errors=[] if ok else ["rendered video missing or too small"],
        )

    def _reedit(self, editor, recipe, review, clips, clip_meta, composer, voice, vcfg, tempo, final_path, out_dir):
        score, bad = review.get("score"), review.get("bad_tiles") or []
        if not score or score >= 8.5 or not bad:   # reviewer bar: 8.5/10
            return final_path, review
        starts, t = [], 0.0
        for c in clips:
            starts.append(t)
            t += c.duration / (tempo or 1.0)
        targets = set()
        for tile in bad:
            sec = tile * 3.0 + 0.5
            idx = max(j for j, st in enumerate(starts) if st <= sec) if starts else 0
            if clip_meta[idx]["kind"] == "item":
                targets.add(idx)
        targets = sorted(targets)[:8]
        if not targets:
            return final_path, review
        replaced = 0
        for idx in targets:
            m = clip_meta[idx]
            spec = m["spec"]
            dest = Path(out_dir) / f"fix_{idx:03d}.jpg"
            old_src = getattr(m["asset"], "path", "")
            alt = None
            for fn in (lambda: spec.get("news_query") and self.media._news_photo(spec["news_query"], dest,
                                                                                int(spec.get("_part", 0)) + 3,
                                                                                cycle=False),
                       lambda: spec.get("entity") and self.media._wikipedia_exact(spec["entity"], dest),
                       lambda: self.media._cloudflare(spec.get("visual") or spec.get("search", ""), dest, "news")):
                try:
                    alt = fn()
                except Exception:
                    alt = None
                if alt and alt.path != old_src:
                    break
                alt = None
            if not alt:
                continue
            composer.compose_background(alt.path, m["bg"], seed=idx)
            if alt.source == "ai":
                _stamp(m["bg"], "सांकेतिक चित्र (AI)")
            replaced += 1
        if not replaced:
            return final_path, review
        self.logger.info("Re-edit: replaced %d flagged pictures, rendering again", replaced)
        second = str(Path(out_dir) / "final_short_v2.mp4")
        self.renderer.render(clips, voice.audio_path, second, music=vcfg.background_music,
                             music_volume=vcfg.music_volume, tempo=tempo, sfx=vcfg.sound_effects,
                             captions=getattr(self, "_captions_ass", None))
        if not Path(second).exists():
            return final_path, review
        review2 = editor.review(second, recipe, str(out_dir), learn=False)
        self.logger.info("Re-edit score %s -> %s", score, review2.get("score"))
        if (review2.get("score") or 0) >= score:
            review2["reedited"] = replaced
            return second, review2
        return final_path, review

    def _captions(self, clips, clip_meta, tempo, out_dir):
        """Word-synced Hindi captions. Each picture has its own voiced line, so words are timed inside that
        line's exact audio window (weighted by word length) -> captions stay locked to the voice."""
        from video.subtitle_generator import SubtitleGenerator
        words, t = [], 0.0
        for c, m in zip(clips, clip_meta):
            dur = c.duration / (tempo or 1.0)
            # title/section/outro cards already show big text: no captions on top of them
            say = (m["spec"].get("say") or "").strip() if m.get("kind") == "item" else ""
            toks = say.split()
            if toks:
                lead, span = 0.06, dur * 0.94 - 0.06
                weights = [len(w) + 2 for w in toks]
                tot = float(sum(weights))
                cur = t + lead
                for w, wt in zip(toks, weights):
                    d = span * wt / tot
                    words.append({"word": w, "start": round(cur, 3), "end": round(cur + d, 3)})
                    cur += d
            t += dur
        if not words:
            return None, None
        gen = SubtitleGenerator()
        ass = gen.generate_ass(words, str(Path(out_dir) / "captions.ass"), highlight_color="#FFD60A",
                               font_size=112, margin_v=730)
        srt = gen.generate_srt_from_words(words, str(Path(out_dir) / "captions.srt"))
        return ass, srt


_NUM = re.compile(r"(₹\s?[\d,.]+\s?(?:करोड़|लाख|हज़ार|हजार)?|[\d,.]+\s?(?:%|प्रतिशत|करोड़|लाख|हज़ार|हजार|किलो|किमी|मीटर|डॉलर|रुपये|साल|लोगों|लोग))")


def _stat(text: str) -> str:
    """The key number of a line ("₹500 करोड़", "40%") for an on-screen stat card, else ''."""
    m = _NUM.search(text or "")
    if not m:
        return ""
    val = m.group(1).strip().rstrip(",.")
    return val if any(ch.isdigit() for ch in val) and len(val) <= 16 else ""


def _render_qa(path: str) -> dict:
    """Post-render self-check (like a QC desk): black frames and dead air in the final MP4."""
    import subprocess
    out = {"black_s": 0.0, "silence_s": 0.0}
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf", "blackdetect=d=0.4:pix_th=0.08",
                            "-af", "silencedetect=n=-45dB:d=1.2", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=300)
        log = r.stderr
        out["black_s"] = round(sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", log)), 2)
        out["silence_s"] = round(sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)", log)), 2)
    except Exception as exc:
        out["error"] = str(exc)[:80]
    return out
