"""End-to-end long-form film: script -> voice -> visuals -> chapters -> film -> upload.

Resumable at every step: script.json, per-chapter media.json and chapter_XX.mp4
are all cached, so a crash or a re-run only redoes the missing part.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from longform import render as R
from longform.media import VisualSourcer
from longform.script import ScriptWriter, split_sentences

logger = logging.getLogger("longform.pipeline")

CARD_SECONDS = 5.0
OUTRO_SECONDS = 7.0


class LongFormPipeline:
    def __init__(self, config, llm=None) -> None:
        self.config = config
        self.video_id = time.strftime("%Y%m%d-%H%M%S")
        self.out = Path("output") / "long" / self.video_id
        self.work = self.out / "_work"
        media = getattr(config, "media", None)
        self.sourcer = VisualSourcer(
            out_root=self.out,
            pexels_key=getattr(media, "pexels_api_key", "") or "",
            pixabay_key=getattr(media, "pixabay_api_key", "") or "",
            hf_token=getattr(media, "hf_token", "") or "",
            agnes_key=getattr(media, "agnes_api_key", "") or "",
        )
        if llm is None:
            from core.llm_client import build_llm
            llm = build_llm(config.llm)
        self.llm = llm
        self.chapter_files: List[str] = []

    # ------------------------------------------------------------------ public
    async def run(self, topic: str, angle: str = "", minutes: int = 22, chapters: int = 9,
                  upload: bool = True, privacy: str = "unlisted") -> Dict[str, Any]:
        t0 = time.time()
        self.out.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)

        logger.info("=== long-form: %s (%d chapters, ~%d min) ===", topic, chapters, minutes)
        writer = ScriptWriter(self.llm, words_per_chapter=max(260, int(minutes * 145 / chapters)))
        script = await writer.build(topic, angle, minutes, chapters, self.out)
        title = script["title"]
        chs = script["chapters"]

        from video.tts import TTSEngine
        tts = TTSEngine(provider_order=["edge"], voice="hi-IN-MadhurNeural", rate="+4%",
                        fallback_voice="hi-IN-SwaraNeural")

        for i, ch in enumerate(chs):
            ch_path = await self._chapter(i, ch, len(chs), tts, title)
            if ch_path:
                self.chapter_files.append(ch_path)

        if not self.chapter_files:
            raise RuntimeError("no chapters rendered")

        film = self._assemble_film(chs, title)
        thumb = self._thumbnail(title, chs)
        meta = self._metadata(title, chs, film)

        result: Dict[str, Any] = {
            "video_id": self.video_id, "title": title, "path": film,
            "duration_sec": R.probe_duration(film), "thumbnail": thumb,
            "chapters": [{"title": c["title"], "start": c.get("_start_sec", 0)} for c in chs],
            "elapsed_min": (time.time() - t0) / 60, "metadata": meta,
        }
        logger.info("film ready: %s (%.1f min render+script)", film, result["elapsed_min"])

        if upload:
            result.update(self._upload(film, thumb, meta, privacy))
        self._save_manifest(result)
        return result

    # ---------------------------------------------------------------- one chapter
    async def _chapter(self, idx: int, ch: Dict, total: int, tts, video_title: str) -> Optional[str]:
        ch_dir = self.out / f"ch{idx + 1:02d}"
        ch_dir.mkdir(parents=True, exist_ok=True)
        final = ch_dir / f"chapter_{idx + 1:02d}.mp4"
        if final.exists() and R.probe_duration(str(final)) > 20:
            logger.info("ch%02d already rendered — skipping", idx + 1)
            return str(final)

        t0 = time.time()
        # 1. narration
        audio = ch_dir / "narration.mp3"
        segment = None
        if not (audio.exists() and audio.stat().st_size > 5000):
            segment = await tts.synthesize_segment(ch["narration"], str(audio))
            logger.info("ch%02d voice: %.1f s", idx + 1, segment.duration)
        from video.tts import probe_duration, distribute_words
        dur = probe_duration(str(audio)) or 60.0
        words = [{"word": w.word, "start": w.start, "end": w.end} for w in (segment.words if segment else [])]
        if not words:
            words = [{"word": w.word, "start": w.start, "end": w.end}
                     for w in distribute_words(ch["narration"], dur)]

        # 2. visuals
        images = self.sourcer.fetch_chapter(idx, ch["visual_queries"], want=max(8, int(dur / 16)))
        cues = R.sentence_cues(split_sentences(ch["narration"]), words, dur)

        # 3. one clip per subtitle cue: sentence-boundary cuts, text burned in by PIL
        pieces: List[str] = []
        card = R.make_card(f"अध्याय {idx + 1} / {total}", ch["title"], ch_dir / "card.jpg")
        pieces.append(R.render_still(card, CARD_SECONDS, str(ch_dir / "p_card.mp4"), seed=idx))

        for j, cue in enumerate(cues):
            span = max(1.2, cue["end"] - cue["start"])
            img = images[j % len(images)]
            png = R.subtitle_png(cue["text"], ch_dir / f"sub_{j:03d}.png")
            pieces.append(R.render_still(img, span, str(ch_dir / f"c_{j:03d}.mp4"),
                                         seed=idx + j, overlay=png))

        silent = R.concat(pieces, str(ch_dir / "video_silent.mp4"), ch_dir)
        out = R.mux_chapter(silent, str(audio), None, str(final),
                            audio_delay_ms=int(CARD_SECONDS * 1000))
        R.build_srt(cues, ch_dir / "chapter.srt", offset=CARD_SECONDS)
        logger.info("ch%02d done in %.1f min (%.1f s film, %d cues, %d images)",
                    idx + 1, (time.time() - t0) / 60, R.probe_duration(out), len(cues), len(images))
        ch["_start_sec"] = 0.0
        return out

    # ----------------------------------------------------------------- film
    def _assemble_film(self, chs: List[Dict], title: str) -> str:
        film = self.out / "film_1080p.mp4"
        if film.exists() and R.probe_duration(str(film)) > 60:
            logger.info("film already assembled — skipping")
            self._fill_start_times(chs, film)
            return str(film)

        # opening title card (3 s, silent) + chapters + outro
        head = R.make_card(title, "एक शोधपरक प्रस्तुति", self.work / "open.jpg")
        head_clip = R.render_still(head, 3.0, str(self.work / "p_open.mp4"), seed=2)
        # silence for the title card so audio stays aligned per chapter
        head_av = self.work / "intro.mp4"
        R.run([R.ff(), "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
               "-i", head_clip, "-t", "3.0", "-c:v", "copy", "-c:a", "aac",
               "-shortest", str(head_av)], "intro")

        parts = [str(head_av)] + list(self.chapter_files)
        tail = R.make_outro(self.work / "outro.jpg", self.config.youtube.channel_name or "BHARAT KI SOCH",
                            "धन्यवाद", "अगली कड़ी में मिलते हैं")
        tail_clip = R.render_still(tail, OUTRO_SECONDS, str(self.work / "p_outro.mp4"), seed=3)
        tail_av = self.work / "outro.mp4"
        R.run([R.ff(), "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
               "-i", tail_clip, "-t", str(OUTRO_SECONDS), "-c:v", "copy", "-c:a", "aac",
               "-shortest", str(tail_av)], "outro")
        parts.append(str(tail_av))

        joined = R.concat(parts, str(self.work / "joined.mp4"), self.work)
        self._merge_srt(chs)
        R.run([R.ff(), "-y", "-i", joined, "-c", "copy", "-movflags", "+faststart", str(film)],
              "finalise film")
        self._fill_start_times(chs, film)
        return str(film)

    def _merge_srt(self, chs: List[Dict]) -> None:
        """One caption track for the whole film, chapter timings included."""
        out = self.out / "film.srt"
        blocks, n = [], 1
        for i, ch in enumerate(chs):
            src = self.out / f"ch{i + 1:02d}" / "chapter.srt"
            if not src.exists():
                continue
            offset = ch.get("_start_sec", 0.0)
            for raw in src.read_text(encoding="utf-8").split("\n\n"):
                lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
                if len(lines) < 3:
                    continue
                try:
                    a, b = lines[1].split(" --> ")
                except ValueError:
                    continue
                def shift(ts: str) -> str:
                    h, m, rest = ts.split(":")
                    sec = float(rest.replace(",", "."))
                    total = int(h) * 3600 + int(m) * 60 + sec + offset
                    hh, rem = divmod(total, 3600)
                    mm, ss = divmod(rem, 60)
                    return f"{int(hh):02d}:{int(mm):02d}:{ss:06.3f}".replace(".", ",")
                blocks.append(f"{n}\n{shift(a)} --> {shift(b)}\n" + "\n".join(lines[2:]))
                n += 1
        if blocks:
            out.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
            logger.info("captions: %s (%d cues)", out, len(blocks))

    def _fill_start_times(self, chs: List[Dict], film) -> None:
        t = 3.0
        for i, ch in enumerate(chs):
            path = self.out / f"ch{i + 1:02d}" / f"chapter_{i + 1:02d}.mp4"
            ch["_start_sec"] = t
            t += R.probe_duration(str(path)) if path.exists() else 0

    # ------------------------------------------------------------ extras
    def _thumbnail(self, title: str, chs: List[Dict]) -> str:
        out = self.out / "thumbnail.jpg"
        card = R.make_card(title, "हिंदू धर्म · उत्पत्ति से आज तक", self.work / "thumb_bg.jpg")
        try:
            from PIL import Image, ImageDraw, ImageFont
            base = Image.open(card).convert("RGB")
            hero = None
            for p in sorted((self.out / "ch01").glob("*.jpg"))[:1]:
                hero = p
            src = hero or next(iter(sorted((self.out / "ch02").glob("*.jpg"))), None)
            if src:
                pic = Image.open(src).convert("RGB")
                scale = max(R.W / pic.width, R.H / pic.height) * 1.0
                pic = pic.resize((int(pic.width * scale), int(pic.height * scale)))
                left = (pic.width - R.W) // 2
                top = (pic.height - R.H) // 2
                pic = pic.crop((left, top, left + R.W, top + R.H)).convert("L")
                pic = pic.point(lambda v: int(v * 0.55))
                base = Image.blend(pic.convert("RGB"), base, 0.45)
            d = ImageDraw.Draw(base)
            f = ImageFont.truetype(str(R.FONT_DIR / "Mukta-ExtraBold.ttf"), 96)
            d.rectangle([100, 150, 210, 158], fill=(212, 175, 55))
            y = 210
            for line in R._wrap(d, title, f, R.W - 240)[:3]:
                d.text((100, y), line, font=f, fill=(248, 248, 252))
                y += 112
            base.save(out, "JPEG", quality=90)
        except Exception as exc:
            logger.warning("thumbnail art failed (%s) — using the plain card", exc)
            shutil.copy(card, out)
        return str(out)

    def _metadata(self, title: str, chs: List[Dict], film: str) -> Dict[str, Any]:
        total = R.probe_duration(film)
        stamps = []
        for i, ch in enumerate(chs):
            sec = int(ch.get("_start_sec", 0))
            stamps.append(f"{sec // 60:02d}:{sec % 60:02d}  {ch['title']}")
        desc = (
            f"{title}\n\n"
            "इस वीडियो में हम हिंदू धर्म की यात्रा को उसकी शुरुआत से आज तक समझेंगे — सिंधु घाटी से "
            "वैदिक काल, उपनिषदों के दर्शन, महाकाव्यों, पुराणों और मंदिर परंपरा से लेकर भक्ति आंदोलन "
            "और आधुनिक भारत तक।\n\n"
            "⏱ अध्याय\n" + "\n".join(stamps) + "\n\n"
            "यह वीडियो शैक्षिक उद्देश्य से बनाया गया है। तिथियाँ और तथ्य मानक इतिहास-ग्रंथों पर आधारित हैं; "
            "जहाँ इतिहासकारों में मतभेद है, वहाँ स्पष्ट रूप से बताया गया है।\n\n"
            f"#हिंदूधर्म #इतिहास #भारत #सनातन #documentary"
        )
        tags = ["हिंदू धर्म", "hindu dharma", "history of hinduism in hindi", "सिंधु घाटी सभ्यता",
                "वैदिक काल", "उपनिषद", "भक्ति आंदोलन", "भारतीय इतिहास", "sanatan dharma explained",
                "indian history documentary hindi", "hinduism explained", "hindu temple history"]
        return {"title": title[:95], "description": desc[:4900], "tags": tags[:15],
                "duration_sec": round(total, 1), "chapter_stamps": stamps}

    # ------------------------------------------------------------- upload
    def _upload(self, film: str, thumb: str, meta: Dict[str, Any], privacy: str) -> Dict[str, Any]:
        try:
            from youtube.oauth_manager import YouTubeOAuthManager
            from youtube.uploader import YouTubeUploader
            oauth = YouTubeOAuthManager(self.config.youtube)
            up = YouTubeUploader(oauth, dry_run=self.config.general.dry_run, strict=False)
            res = up.upload_video(
                video_path=film, title=meta["title"], description=meta["description"],
                tags=meta["tags"], category_id="27", privacy_status=privacy,
                contains_synthetic_media=True, language="hi",
                thumbnail_path=thumb,
                captions_path=(str(Path(film).parent / "film.srt")
                               if (Path(film).parent / "film.srt").exists() else None),
                publishing_key=f"long-{self.video_id}",
            )
            logger.info("upload: %s", res)
            return {"upload": res, "url": (res or {}).get("url", "")}
        except Exception as exc:
            logger.error("upload failed: %s", exc)
            return {"upload_error": str(exc)[:300]}

    def _save_manifest(self, result: Dict[str, Any]) -> None:
        path = self.out / "manifest.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("manifest: %s", path)
