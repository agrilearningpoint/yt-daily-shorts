"""End-to-end long-form film: script -> voice -> visuals -> chapters -> film -> upload.

Resumable at every step: script.json, per-chapter media.json and chapter_XX.mp4
are all cached, so a crash or a re-run only redoes the missing part.
"""
from __future__ import annotations

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
        # stable id per (topic, day) so a re-run can restore its own checkpoints
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
        self.writer = None
        self._chapters: List[Dict] = []
        self.target_chapter_sec = 0.0
        self.run_errors: List[str] = []

    # ------------------------------------------------------------------ public
    async def run(self, topic: str, angle: str = "", minutes: int = 22, chapters: int = 9,
                  upload: bool = True, privacy: str = "unlisted",
                  rebuild_visuals: bool = False, force_upload: bool = False,
                  fresh: bool = False) -> Dict[str, Any]:
        t0 = time.time()
        self.video_id = f"{_slug(topic)}-{time.strftime('%Y%m%d')}"
        self.out = Path("output") / "long" / self.video_id
        self.work = self.out / "_work"
        self.out.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        # __init__ saw a timestamp id; point the visual sourcer at the real film dir so
        # media.json caching and the thumbnail picker both see the downloaded photos
        self.sourcer.out_root = self.out

        logger.info("=== long-form: %s (%d chapters, ~%d min) ===", topic, chapters, minutes)
        if fresh:
            # ignore every checkpoint: new script, new voice, new visuals, new film
            for f in list(self.out.glob("*.json")) + [self.out / "film.srt"]:
                Path(f).unlink(missing_ok=True)
            for d in sorted(self.out.glob("ch*")):
                shutil.rmtree(d, ignore_errors=True)
            logger.info("fresh run: checkpoints and script discarded")
        if rebuild_visuals:
            for d in sorted(self.out.glob("ch*")):
                for f in d.glob("*"):
                    if f.suffix in (".mp4", ".json"):
                        f.unlink(missing_ok=True)
            logger.info("rebuild-visuals: chapters cleared, script kept")
        if not fresh:
            self._checkpoint_restore()
        writer = ScriptWriter(self.llm, words_per_chapter=max(280, int(minutes * 158 / chapters)))
        self.writer = writer
        # card(5s) per chapter, plus the 3s intro and 7s outro, are not narration
        self.target_chapter_sec = max(30.0, (minutes * 60 - (CARD_SECONDS * chapters + 10)) / chapters)
        script = await writer.build(topic, angle, minutes, chapters, self.out)
        title = script["title"]
        chs = script["chapters"]
        self._chapters = chs

        from video.tts import TTSEngine
        tts = TTSEngine(provider_order=["edge"], voice="hi-IN-MadhurNeural", rate="+4%",
                        fallback_voice="hi-IN-SwaraNeural")

        for i, ch in enumerate(chs):
            ch_path = await self._chapter(i, ch, len(chs), tts, title)
            if ch_path:
                self.chapter_files.append(ch_path)
                self._checkpoint_save(i, ch, ch_path)

        if not self.chapter_files:
            raise RuntimeError("no chapters rendered")

        film = self._assemble_film(chs, title)
        thumb = self._thumbnail(title, chs)
        meta = await self._metadata(title, chs, film)

        result: Dict[str, Any] = {
            "video_id": self.video_id, "title": title, "path": film,
            "duration_sec": R.probe_duration(film), "thumbnail": thumb,
            "chapters": [{"title": c["title"], "start": c.get("_start_sec", 0)} for c in chs],
            "elapsed_min": (time.time() - t0) / 60, "metadata": meta,
        }
        logger.info("film ready: %s (%.1f min render+script)", film, result["elapsed_min"])

        if upload:
            result.update(self._upload(film, thumb, meta, privacy, force_upload))
        self._save_manifest(result)
        # one metrics line per film: the error analyst and data/improvements.md read this,
        # so long-form runs finally count in the self-improvement loop
        from longform import seo as lseo
        errs = [e for e in [result.get("upload_error")] + list(getattr(self, "run_errors", [])) if e]
        lseo.record_film("longform", result["elapsed_min"], not errs, errs,
                         title=meta.get("title", "")[:120], seo=meta.get("seo", ""),
                         minutes_film=round((result.get("duration_sec") or 0) / 60, 1),
                         chapters=len(chs), video=result.get("url", ""))
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

        # Length control on the real audio, not on the LLM's word count. Chapters that
        # come back short are rewritten longer and re-voiced (max 2 passes) so the film
        # lands inside the requested 20-25 minute window instead of drifting to 16.
        for attempt in range(2):
            target = getattr(self, "target_chapter_sec", 0) or 0
            if not target or dur >= target * 0.9 or not ch.get("narration"):
                break
            words_have = len(ch["narration"].split())
            want_words = int(words_have * (target * 1.02) / max(dur, 1))
            if want_words <= words_have * 1.05:
                break
            logger.warning("ch%02d short: %.0f s of %.0f s target — rewriting longer (%d -> %d words)",
                           idx + 1, dur, target, words_have, want_words)
            try:
                longer = await self.writer.lengthen(video_title, ch, idx, total, want_words)
            except Exception as exc:
                logger.warning("ch%02d lengthen failed: %s", idx + 1, exc)
                self.run_errors.append(f"lengthen ch{idx + 1:02d}: {exc}")
                break
            if len(longer.split()) <= words_have:
                break
            ch["narration"] = longer
            self._save_script_cache()
            audio.unlink(missing_ok=True)
            segment = await tts.synthesize_segment(ch["narration"], str(audio))
            dur = probe_duration(str(audio)) or dur
            logger.info("ch%02d re-voiced: %.1f s", idx + 1, dur)
        dur = dur or 60.0
        words = [{"word": w.word, "start": w.start, "end": w.end} for w in (segment.words if segment else [])]
        if not words:
            words = [{"word": w.word, "start": w.start, "end": w.end}
                     for w in distribute_words(ch["narration"], dur)]

        # 2. visuals
        images = self.sourcer.fetch_chapter(idx, ch["visual_queries"], want=max(12, int(dur / 9)))
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

    # ------------------------------------------------------------ checkpoints
    _CK_REPO = None

    def _hf(self):
        """Best-effort HF handle for chapter checkpoints (never fatal)."""
        if self._CK_REPO is None:
            try:
                from core.hf_storage import store_from_config
                self._store = store_from_config(self.config)
                self._CK_REPO = bool(getattr(self._store, "enabled", False))
            except Exception:
                self._CK_REPO = False
        return getattr(self, "_store", None) if self._CK_REPO else None

    def _save_script_cache(self) -> None:
        """Persist narration rewrites so a re-run re-uses the longer script."""
        cache = self.out / "script.json"
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            return
        for cached in data.get("chapters", []):
            mine = next((c for c in self._chapters if c.get("title") == cached.get("title")), None)
            if mine and mine.get("narration"):
                cached["narration"] = mine["narration"]
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _checkpoint_save(self, idx: int, ch: Dict, path: str) -> None:
        st = self._hf()
        if not st:
            return
        try:
            remote = f"long/{self.video_id}"
            st.upload_file(path, f"{remote}/ch{idx + 1:02d}.mp4")
            st.upload_file(self.out / "script.json", f"{remote}/script.json")
            logger.info("checkpoint ch%02d -> HF", idx + 1)
        except Exception as exc:
            logger.debug("checkpoint skipped: %s", exc)

    def _checkpoint_restore(self) -> None:
        """Pull finished chapters back so a re-run does not re-render 25 minutes of film."""
        st = self._hf()
        if not st:
            return
        try:
            from huggingface_hub import snapshot_download
            local = snapshot_download(repo_id=st.repo_id, repo_type="dataset",
                                      allow_patterns=[f"long/{self.video_id}/script.json",
                                                      f"long/{self.video_id}/ch*.mp4"],
                                      local_dir=str(self.work / "_ckpt"))
            src = Path(local) / "long" / self.video_id
            if not src.exists():
                logger.info("no checkpoint for %s — starting fresh", self.video_id)
                return
            if (src / "script.json").exists():
                shutil.copy(src / "script.json", self.out / "script.json")
            for mp4 in sorted(src.glob("ch*.mp4")):
                d = self.out / mp4.stem / f"chapter_{mp4.stem[2:]}.mp4"
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(mp4, d)
            logger.info("checkpoint restored: %d chapters", len(list(src.glob("ch*.mp4"))))
        except Exception as exc:
            logger.info("checkpoint restore skipped: %s", exc)

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
        channel = getattr(self.config.general, "channel_name", "") or "BHARAT KI SOCH"
        tail = R.make_outro(self.work / "outro.jpg", channel,
                            "धन्यवाद", "अगली कड़ी में मिलते हैं")
        tail_clip = R.render_still(tail, OUTRO_SECONDS, str(self.work / "p_outro.mp4"), seed=3)
        tail_av = self.work / "outro.mp4"
        R.run([R.ff(), "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
               "-i", tail_clip, "-t", str(OUTRO_SECONDS), "-c:v", "copy", "-c:a", "aac",
               "-shortest", str(tail_av)], "outro")
        parts.append(str(tail_av))

        joined = R.concat(parts, str(self.work / "joined.mp4"), self.work, reencode=True)
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
        """1280x720-safe thumbnail: a real photograph + one clean title block."""
        out = self.out / "thumbnail.jpg"
        try:
            from PIL import Image

            # Hero source, best first:
            #   1. a frame from the rendered film — always on-topic
            #   2. a downloaded photograph — keyword-matched, can be wrong (a cathedral
            #      did once illustrate a Hindu temple query)
            photos = []
            frame = self._frame_for_thumbnail()
            if frame:
                photos = [(frame.stat().st_size, frame)]
            else:
                for i in list(range(1, 4)) + list(range(4, 12)):
                    d = self.out / f"ch{i:02d}"
                    if not d.exists():
                        continue
                    for f in d.iterdir():
                        if f.suffix.lower() in (".jpg", ".jpeg") and f.name != "card.jpg" \
                                and not f.name.startswith(("sub_", "thumb")):
                            photos.append((f.stat().st_size, f))
                    if photos:
                        break
            photos.sort(reverse=True)
            # keep only landscape, non-blank pictures: a portrait or a flat scan makes a
            # poor hero image and a blank one means the download was a placeholder
            good = []
            for size, f in photos[:40]:
                try:
                    im = Image.open(f)
                    w, h = im.size
                    if w < 1200 or w / max(1, h) < 1.2:
                        continue
                    small = im.convert("L").resize((64, 36))
                    px = list(small.get_flattened_data()) if hasattr(small, "get_flattened_data") else list(small.getdata())
                    mean = sum(px) / max(1, len(px))
                    var = sum((v - mean) ** 2 for v in px) / max(1, len(px))
                    if var < 400:  # near-flat image
                        continue
                    good.append((size, f))
                except Exception:
                    continue
            if not good:
                raise RuntimeError("no usable hero image (no frame, no photo)")
            photos = good
            channel = getattr(self.config.general, "channel_name", "") or "BHARAT KI SOCH"
            R.compose_thumbnail(str(photos[0][1]), title, out, channel=channel)
        except Exception as exc:
            logger.warning("thumbnail art failed (%s) — using a plain card", exc)
            R.make_card(title, "हिंदू धर्म", out)
        return str(out)

    def _frame_for_thumbnail(self) -> Optional[Path]:
        """Grab a frame from an early chapter — the top half only, so no burned subtitles."""
        for i in (2, 3, 4, 1):
            mp4 = self.out / f"ch{i:02d}" / f"chapter_{i:02d}.mp4"
            if not mp4.exists():
                continue
            out = self.out / f"thumb_frame_{i:02d}.jpg"
            try:
                dur = R.probe_duration(str(mp4)) or 60.0
                R.run([R.ff(), "-y", "-ss", f"{max(3.0, dur * 0.4):.2f}", "-i", str(mp4), "-frames:v", "1",
                              "-vf", "crop=iw:ih*0.78:0:0,scale=1920:-1", "-q:v", "2", str(out)])
                if out.exists() and out.stat().st_size > 20_000:
                    return out
            except Exception as exc:
                logger.debug("thumbnail frame failed (ch%02d): %s", i, exc)
        return None

    def _publishing_key(self, film: str) -> str:
        """Dedupe key that changes whenever the rendered film changes.

        A plain `long-<slug>-<date>` key made every re-render look like a duplicate,
        so fixed films never reached YouTube. The fingerprint (duration + size) means
        a genuine re-render uploads, while an identical re-run is still skipped.
        """
        try:
            dur = int(R.probe_duration(film) or 0)
            mb = int(Path(film).stat().st_size / (1024 * 1024))
        except OSError:
            dur, mb = 0, 0
        return f"long-{self.video_id}-{dur}s{mb}m"

    async def _metadata(self, title: str, chs: List[Dict], film: str) -> Dict[str, Any]:
        """Title/description/tags from the SEO module: LLM-first, deterministic fallback."""
        from longform import seo as lseo
        total = R.probe_duration(film)
        stamps = []
        for ch in chs:
            sec = int(ch.get("_start_sec", 0))
            stamps.append(f"{sec // 60:02d}:{sec % 60:02d}  {ch['title']}")
        return await lseo.build_metadata(self.llm, title, chs, stamps, total)

    # ------------------------------------------------------------- upload
    def _upload(self, film: str, thumb: str, meta: Dict[str, Any], privacy: str,
                force_upload: bool = False) -> Dict[str, Any]:
        try:
            from youtube.oauth import YouTubeOAuthManager
            from youtube.uploader import YouTubeUploader
            yt = self.config.youtube
            oauth = YouTubeOAuthManager(getattr(yt, "client_secret_json", ""),
                                        getattr(yt, "token_json", ""))
            up = YouTubeUploader(oauth, dry_run=self.config.general.dry_run, strict=False)
            res = up.upload_video(
                video_path=film, title=meta["title"], description=meta["description"],
                tags=meta["tags"], category_id="27", privacy_status=privacy,
                contains_synthetic_media=True, language="hi",
                thumbnail_path=thumb,
                captions_path=(str(Path(film).parent / "film.srt")
                               if (Path(film).parent / "film.srt").exists() else None),
                publishing_key=self._publishing_key(film),
                force=force_upload,
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


def _slug(text: str) -> str:
    """Filesystem/HF-safe slug that survives Devanagari input."""
    import hashlib
    import re
    keep = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return keep or "film-" + hashlib.sha1(text.encode()).hexdigest()[:8]
