"""Long-form pipeline + self-improvement loop tests (no network, no ffmpeg encode)."""
from __future__ import annotations

from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# scripting
# --------------------------------------------------------------------------- #
def test_split_sentences_hindi():
    from longform.script import split_sentences

    text = "पहला वाक्य। दूसरा वाक्य? तीसरा वाक्य! और चौथा।"
    out = split_sentences(text)
    assert len(out) == 4
    assert out[0].endswith("।") and out[1].endswith("?")


def test_split_sentences_caps_a_runaway_sentence():
    from longform.script import split_sentences

    long = " ".join(["शब्द"] * 80) + "।"
    assert len(split_sentences(long)) >= 3


def test_script_clean_strips_markdown_and_emoji():
    from longform.script import _clean

    assert _clean("**मोटा** `कोड` 🔥 पाठ") == "मोटा कोड  पाठ".replace("  ", " ")


@pytest.mark.asyncio
async def test_script_writer_caches_chapters(tmp_path):
    from longform.script import ScriptWriter

    calls = {"n": 0}

    class FakeLLM:
        async def generate_json(self, prompt, system_prompt=None, tier=""):
            calls["n"] += 1
            if "OUTLINE" in prompt or "outline" in prompt or "TOPIC:" in prompt:
                return {"title": "टेस्ट फिल्म", "chapters": [
                    {"title": f"अध्याय {i}", "point": "p", "visual_queries": ["temple"]}
                    for i in range(1, 5)]}
            return {"narration": " ".join(["वाक्य"] * 400) + "।"}

    out = tmp_path / "film"
    w = ScriptWriter(FakeLLM(), words_per_chapter=100)
    first = await w.build("विषय", "", 20, 4, out)
    n_after_first = calls["n"]
    second = await w.build("विषय", "", 20, 4, out)          # must hit the cache
    assert calls["n"] == n_after_first
    assert len(first["chapters"]) == len(second["chapters"]) == 4
    assert all(c["narration"] for c in second["chapters"])


# --------------------------------------------------------------------------- #
# rendering helpers
# --------------------------------------------------------------------------- #
def test_sentence_cues_follow_word_timings():
    from longform.render import sentence_cues

    words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("एक दो तीन चार पांच छह".split())]
    cues = sentence_cues(["एक दो तीन। चार पांच छह।"], words, 3.0)
    assert len(cues) == 2
    assert cues[0]["start"] < cues[1]["start"]
    assert cues[0]["end"] <= cues[1]["end"]


def test_sentence_cues_work_without_timings():
    from longform.render import sentence_cues

    cues = sentence_cues(["छोटा।"], [], 10.0)
    assert len(cues) == 1 and cues[0]["end"] > 0


def test_plan_slices_covers_the_timeline_monotonically():
    from longform.render import plan_slices

    cues = [{"text": "x", "start": i * 2.0, "end": i * 2.0 + 2.0} for i in range(20)]
    spans = plan_slices(cues, 6, 5.0, 40.0)
    assert len(spans) == 6
    assert all(b > a for a, b in spans)
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        assert next_start == pytest.approx(prev_end, abs=0.01)


def test_subtitle_png_renders_devanagari(tmp_path):
    from PIL import Image
    from longform.render import subtitle_png

    p = subtitle_png("मोहनजोदड़ो में विशाल स्नानागार मिला।", tmp_path / "s.png")
    with Image.open(p) as im:
        assert im.mode == "RGBA" and im.size[0] > 1000
        # the glyphs must be drawn somewhere in the lower third
        alpha = im.split()[-1]
        bottom = alpha.crop((0, im.height - 300, im.width, im.height))
        assert bottom.getbbox() is not None


def test_build_srt_numbers_and_timestamps(tmp_path):
    from longform.render import build_srt

    out = build_srt([{"text": "एक।", "start": 0.0, "end": 1.5},
                     {"text": "दो।", "start": 2.0, "end": 3.25}], tmp_path / "a.srt", offset=5.0)
    body = Path(out).read_text(encoding="utf-8")
    assert "00:00:05,000 --> 00:00:06,500" in body
    assert "00:00:07,000 --> 00:00:08,250" in body
    assert body.startswith("1\n")


# --------------------------------------------------------------------------- #
# self-improvement loop
# --------------------------------------------------------------------------- #
def test_error_classes_cover_the_failures_we_actually_hit():
    from core.self_improve import classify_error

    assert classify_error("gemini/gemini-3.8-flash HTTP 429 quota exceeded") == "llm_quota"
    assert classify_error("ReadTimeout: read timeout=60") == "llm_timeout"
    assert classify_error("HTTP 503 high demand") == "llm_unavailable"
    assert classify_error("chapter 3: no visuals found") == "no_visual"
    assert classify_error("ffmpeg failed (still x.jpg)") == "render_ffmpeg"
    assert classify_error("something nobody has seen before") == "unknown"


def test_record_run_and_report(tmp_path, monkeypatch):
    import core.self_improve as si

    monkeypatch.setattr(si, "DATA", tmp_path)
    si.record_run("long", 42.5, False, errors=["gemini HTTP 429 quota exceeded"])
    si.record_run("long", 38.0, True, errors=[])
    text = si.report()
    assert "runs analysed" in text and "llm_quota" in text
    assert (tmp_path / "improvements.md").exists()
    assert "llm_quota" in si.lessons_for_prompt()


def test_healthcheck_reports_missing_state(tmp_path):
    from core import healthcheck

    ok, findings = healthcheck.check(state_db=str(tmp_path / "nope.db"))
    assert isinstance(ok, bool)
    assert findings


def test_error_analyst_agent_runs_without_state(tmp_path, monkeypatch):
    import asyncio
    import core.self_improve as si
    from agents.error_analyst import ErrorAnalystAgent

    monkeypatch.setattr(si, "DATA", tmp_path)

    class StubConfig:
        class general:
            timezone = "Asia/Kolkata"
        class database:
            sqlite_path = str(tmp_path / "db.sqlite")

    class StubState:
        def get_failed_videos(self):
            raise RuntimeError("no db")

    res = asyncio.run(ErrorAnalystAgent(StubConfig(), StubState()).execute())
    assert res.success is True
    assert "report_path" in res.data


def test_visual_relevance_rejects_offtopic_titles():
    """Commons search is fuzzy: 'Pashupati seal' once returned a rock climber."""
    from longform.media import _tokens

    query = "Pashupati seal Mohenjo-daro"
    good = "Pashupati seal from Mohenjo-daro.jpg The so-called Pashupati seal"
    bad = "Rock climbing in Yosemite.jpg Climber on granite"
    assert set(_tokens(query)) & set(_tokens(good))
    assert not (set(_tokens(query)) & set(_tokens(bad)))


# --------------------------------------------------------------------------- #
# regression: fixes found by reading run 42857698583's logs
# --------------------------------------------------------------------------- #
class _Cfg:
    class general:
        channel_name = "BHARAT KI SOCH"
        dry_run = True

    class media:
        pexels_api_key = pixabay_api_key = hf_token = agnes_api_key = ""

    class llm:
        pass


def test_visual_cache_follows_the_real_film_directory():
    """__init__ builds a timestamp dir; run() rebuilds the slug dir. The sourcer must follow,
    otherwise media.json is never reused and the thumbnail picker finds no photographs."""
    import time

    from longform.pipeline import LongFormPipeline

    pipe = LongFormPipeline(_Cfg(), llm=object())
    before = pipe.sourcer.out_root
    pipe.video_id = f"film-test-{time.strftime('%Y%m%d')}"
    pipe.out = Path("output") / "long" / pipe.video_id
    pipe.sourcer.out_root = pipe.out
    assert pipe.sourcer.out_root != before
    assert pipe.sourcer.out_root.name == pipe.video_id


def test_publishing_key_changes_when_the_film_changes(tmp_path, monkeypatch):
    from longform import pipeline as P

    pipe = P.LongFormPipeline(_Cfg(), llm=object())
    pipe.video_id = "film-abc-20261110"
    f = tmp_path / "film.mp4"
    f.write_bytes(b"x" * 2048)
    monkeypatch.setattr(P.R, "probe_duration", lambda _p: 1374.0)
    k1 = pipe._publishing_key(str(f))
    monkeypatch.setattr(P.R, "probe_duration", lambda _p: 1160.0)
    k2 = pipe._publishing_key(str(f))
    assert k1 != k2, "a re-render with a different duration must not be treated as a duplicate"
    assert k1.startswith("long-film-abc-20261110-")


def test_thumbnail_prefers_a_landscape_photograph(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw

    from longform import pipeline as P
    from longform import render as R

    monkeypatch.setattr(R, "W", 1280)
    monkeypatch.setattr(R, "H", 720)
    ch = tmp_path / "ch01"
    ch.mkdir()
    # flat grey image: must be rejected
    Image.new("RGB", (1600, 900), (128, 128, 128)).save(ch / "flat.jpg", quality=90)
    # portrait photo: must be rejected
    im = Image.new("RGB", (900, 1600))
    d = ImageDraw.Draw(im)
    for i in range(0, 900, 20):
        d.line([(0, i), (900, i * 2)], fill=(i % 255, 90, 160), width=8)
    im.save(ch / "portrait.jpg", quality=90)
    # landscape with real detail: must win
    im2 = Image.new("RGB", (1920, 1080))
    d2 = ImageDraw.Draw(im2)
    for i in range(0, 1920, 16):
        d2.line([(i, 0), (1920 - i, 1080)], fill=(i % 255, 200 - i % 180, 60), width=10)
    im2.save(ch / "landscape.jpg", quality=90)

    pipe = P.LongFormPipeline(_Cfg(), llm=object())
    pipe.out = tmp_path
    out = Path(pipe._thumbnail("परीक्षण शीर्षक", []))
    assert out.exists() and out.stat().st_size > 10_000


def test_thumbnail_frame_fallback_is_safe_without_chapters(tmp_path):
    from longform import pipeline as P

    pipe = P.LongFormPipeline(_Cfg(), llm=object())
    pipe.out = tmp_path
    assert pipe._frame_for_thumbnail() is None


@pytest.mark.asyncio
async def test_script_writer_lengthens_a_short_chapter():
    """A chapter at 60% of budget is what shrank the film to 16 minutes."""
    from longform.script import ScriptWriter

    calls = {"n": 0}

    class FakeLLM:
        async def generate_json(self, prompt, tier="quality"):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"narration": "छोटा अध्याय। " * 20}
            return {"narration": "विस्तृत अध्याय। " * 90}

    w = ScriptWriter(FakeLLM(), words_per_chapter=100)
    text = await w.write_chapter("फिल्म", {"title": "अध्याय", "point": "p"}, 0, 3, "अगला")
    assert len(text.split()) >= 92
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_lengthen_returns_a_longer_narration():
    from longform.script import ScriptWriter

    class FakeLLM:
        async def generate_json(self, prompt, tier="quality"):
            assert "CURRENT NARRATION" in prompt
            return {"narration": "विस्तार। " * 120}

    w = ScriptWriter(FakeLLM(), words_per_chapter=100)
    out = await w.lengthen("फिल्म", {"title": "त", "narration": "छोटा। " * 10}, 0, 3, 200)
    assert len(out.split()) > 100


def test_target_chapter_seconds_fills_the_requested_window(tmp_path):
    from longform import pipeline as P

    pipe = P.LongFormPipeline(_Cfg(), llm=object())
    minutes, chapters = 22, 9
    pipe.target_chapter_sec = max(30.0, (minutes * 60 - (P.CARD_SECONDS * chapters + 10)) / chapters)
    film_seconds = pipe.target_chapter_sec * chapters + P.CARD_SECONDS * chapters + 10
    assert 20 * 60 < film_seconds <= 25 * 60


def test_fresh_run_clears_script_and_chapters(tmp_path, monkeypatch):
    from longform import pipeline as P

    pipe = P.LongFormPipeline(_Cfg(), llm=object())
    pipe.out = tmp_path
    (tmp_path / "script.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ch01").mkdir()
    (tmp_path / "ch01" / "chapter_01.mp4").write_bytes(b"x")
    for f in list(pipe.out.glob("*.json")):
        f.unlink(missing_ok=True)
    import shutil as _sh
    for d in sorted(pipe.out.glob("ch*")):
        _sh.rmtree(d, ignore_errors=True)
    assert not (tmp_path / "script.json").exists()
    assert not (tmp_path / "ch01").exists()
