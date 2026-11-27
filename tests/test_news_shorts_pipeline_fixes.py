"""Regression tests for News Shorts pipeline fixes: continuous TTS, Hindi integrity, A/V sync, VFX/BGM/SFX, and layout safe-zones."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from agents.hook_director.agent import HookDirectorAgent
from agents.master_editing_director.agent import MasterEditingDirectorAgent
from agents.script_manager.agent import Scene, Script, ScriptManagerAgent, _clean_complete_hindi_trim
from agents.visual_audio_match_qa.agent import VisualAudioMatchQAAgent
from core.configuration import load_config
from core.state_manager import StateManager
from video.editor_director import GRADES
from video.motion_graphics import MotionGraphicsEngine
from video.renderer import SceneClip, VideoRenderer, ensure_sfx
from video.scene_composer import shape_devanagari
from video.semantic_matcher import extract_entity_from_hindi
from video.subtitle_generator import SubtitleGenerator, group_words
from video.tts import TTSEngine, WordTiming


def test_continuous_edge_tts_join_and_boundary_alignment():
    texts = [
        "आज भारत ने रक्षा क्षेत्र में बड़ी छलांग लगाई है",
        "रक्षा मंत्री ने नई मिसाइल प्रणाली का सफल परीक्षण देखा",
        "अंतरराष्ट्रीय स्तर पर इस तकनीक की काफी चर्चा हो रही है",
    ]
    joined = TTSEngine._join_continuous_beats(texts, owner_ids=[1, 1, 2])
    # Same owner beats (1, 0) & (1, 1) join with a single space; distinct stories separate on newline
    first_line, second_line = joined.splitlines()
    assert "लगाई है रक्षा मंत्री" in first_line
    assert first_line.endswith("।")
    assert "अंतरराष्ट्रीय स्तर" in second_line

    # Simulate single-pass Edge-TTS WordBoundary list containing a multi-word date token too
    tokens = []
    cur = 0.08
    for i, b in enumerate(texts):
        words = b.split()
        if i == 0:
            # Test multi-word chunk expansion behavior
            tokens.append(WordTiming("आज भारत ने", cur, cur + 0.60, source="edge-tts"))
            cur += 0.65
            for w in words[3:]:
                tokens.append(WordTiming(w, cur, cur + 0.22, source="edge-tts"))
                cur += 0.24
        else:
            for w in words:
                tokens.append(WordTiming(w, cur, cur + 0.22, source="edge-tts"))
                cur += 0.24
        cur += 0.12

    durs, beat_words = TTSEngine._align_continuous_boundaries(
        texts, tokens, total_duration=cur + 0.15
    )
    assert len(durs) == 3
    assert len(beat_words) == 3
    assert all(d >= 0.4 for d in durs)
    assert abs(sum(durs) - (cur + 0.15)) < 0.05
    # Expanded multi-word token splits cleanly into individual Hindi words
    assert beat_words[0][0].word == "आज"
    assert beat_words[0][1].word == "भारत"
    assert beat_words[1][0].word == "रक्षा"


def test_rescale_trimmed_words_bounds():
    raw = [
        WordTiming("नमस्कार", 0.30, 0.70, source="edge-tts"),
        WordTiming("भारत", 0.72, 1.15, source="edge-tts"),
        WordTiming("समाचार", 1.18, 1.65, source="edge-tts"),
    ]
    scaled = TTSEngine._rescale_trimmed_words(raw, orig_dur=1.95, new_dur=1.40)
    assert len(scaled) == 3
    assert scaled[0].start < raw[0].start
    assert scaled[-1].end <= 1.40
    assert all(scaled[i].start < scaled[i].end for i in range(len(scaled)))


def test_hindi_trim_never_severs_postposition_and_diversifies_parts(tmp_path):
    cfg = load_config()
    cfg.database.sqlite_path = str(tmp_path / "sm.db")
    sm = ScriptManagerAgent(cfg, StateManager(cfg.database.sqlite_path))

    line = (
        "सरकार ने देश के ग्रामीण इलाकों में डिजिटल स्वास्थ्य सेवा और इंटरनेट के"
    )
    trimmed = _clean_complete_hindi_trim(line.split(), 12)
    last_tok = trimmed.rstrip("।.?! ")
    assert last_tok.split()[-1] not in {"में", "की", "के", "का", "से", "और", "को", "पर", "ने"}
    assert trimmed.endswith("।")

    # Test single long scene split -> part 1 gets distinct visual query instead of repeating part 0
    scenes = [
        Scene(
            scene_number=1,
            section="today",
            narration="आज 27 नवंबर है और आज भारतीय अंतरिक्ष विज्ञान दिवस मनाया जाता है।",
            parts=[
                {
                    "say": "आज 27 नवंबर है और आज भारतीय अंतरिक्ष विज्ञान दिवस मनाया जाता है।",
                    "entity": "ISRO",
                    "search": "ISRO rocket launch",
                }
            ],
        ),
        Scene(
            scene_number=2,
            section="national",
            narration="केंद्र सरकार ने नए एक्सप्रेसवे प्रोजेक्ट को मंजूरी दे दी जिससे यात्रा तेज होगी।",
            parts=[
                {
                    "say": "केंद्र सरकार ने नए एक्सप्रेसवे प्रोजेक्ट को मंजूरी दे दी जिससे यात्रा तेज होगी।",
                    "entity": "Nitin Gadkari",
                    "search": "Nitin Gadkari expressway",
                }
            ],
        ),
        Scene(
            scene_number=3,
            section="international",
            narration="संयुक्त राष्ट्र में भारत ने जलवायु वित्त पर अपना पक्ष मजबूती से रखा है।",
            parts=[
                {
                    "say": "संयुक्त राष्ट्र में भारत ने जलवायु वित्त पर अपना पक्ष मजबूती से रखा है।",
                    "entity": "United Nations",
                    "search": "United Nations climate conference",
                }
            ],
        ),
    ]
    script = Script(title="t", hook="बड़ा फैसला", scenes=scenes, video_type="news")
    sm._normalize_scenes(script)
    sc2 = script.scenes[1]
    assert len(sc2.parts) == 2
    assert sc2.parts[1]["entity"] == ""
    assert sc2.parts[1]["search"] != sc2.parts[0]["search"]


@pytest.mark.asyncio
async def test_hook_director_binds_to_matching_lead_story_not_first_item(tmp_path):
    cfg = load_config()
    cfg.database.sqlite_path = str(tmp_path / "hd.db")
    agent = HookDirectorAgent(cfg, StateManager(cfg.database.sqlite_path), llm=None)

    script = {
        "hook": "संसद में नया डिजिटल बिल पेश हुआ!",
        "scenes": [
            {
                "scene_number": 1,
                "section": "today",
                "on_screen_text": "आज का दिन",
                "narration": "आज 27 नवंबर का दिन इतिहास में दर्ज है।",
                "sources": [],
                "parts": [{"say": "आज 27 नवंबर", "entity": "Calendar", "search": "calendar"}],
            },
            {
                "scene_number": 2,
                "section": "national",
                "headline": "Parliament clears Digital Data Bill",
                "on_screen_text": "डिजिटल बिल",
                "narration": "संसद ने आज नया डिजिटल सुरक्षा बिल पास कर दिया है।",
                "sources": ["https://news.example/parliament-bill"],
                "parts": [
                    {
                        "say": "संसद ने डिजिटल सुरक्षा बिल पास किया",
                        "entity": "Parliament of India",
                        "search": "Parliament of India New Delhi",
                    }
                ],
            },
        ],
    }
    research = {
        "items": [
            {"title": "Gold price surges in Mumbai", "source_url": "https://news.example/gold"},
            {
                "title": "Parliament passes Digital Bill",
                "source_url": "https://news.example/parliament-bill",
                "image_url": "https://upload.wikimedia.org/parliament.jpg",
            },
        ]
    }
    res = await agent.execute(research_data=research, script=script, video_type="news")
    assert res.success
    hook = res.data["approved_hook"]
    assert hook["entity_hint"] == "Parliament of India"
    assert hook.get("paired_source_url") == "https://news.example/parliament-bill"
    assert hook.get("paired_image_url") == "https://upload.wikimedia.org/parliament.jpg"
    assert "Gold" not in hook["visual_pairing_query"]


@pytest.mark.asyncio
async def test_master_editing_director_no_off_by_one_and_forwards_presets(tmp_path):
    cfg = load_config()
    cfg.database.sqlite_path = str(tmp_path / "med.db")
    med = MasterEditingDirectorAgent(cfg, StateManager(cfg.database.sqlite_path))

    hook_img = tmp_path / "hook.jpg"
    sc0_img = tmp_path / "sc0.jpg"
    sc1_img = tmp_path / "sc1.jpg"
    for p, col in ((hook_img, (200, 30, 30)), (sc0_img, (30, 200, 30)), (sc1_img, (30, 30, 200))):
        Image.new("RGB", (640, 480), col).save(p)

    script = {
        "hook": "भारत ने बड़ा कदम उठाया",
        "scenes": [
            {"narration": "पहली बड़ी खबर देश से आ रही है।", "on_screen_text": "पहली खबर"},
            {"narration": "दूसरी बड़ी खबर अंतरराष्ट्रीय जगत से है।", "on_screen_text": "दूसरी खबर"},
        ],
    }
    visual_assets = {
        "scene_000_hook": SimpleNamespace(local_path=str(hook_img), source_provider="wiki"),
        "scene_000": SimpleNamespace(local_path=str(sc0_img), source_provider="wiki"),
        "scene_001": SimpleNamespace(local_path=str(sc1_img), source_provider="wiki"),
    }
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFF" + b"\x00" * 100)

    res = await med.execute(
        video_id="med_test_unit",
        script=script,
        visual_assets=visual_assets,
        narration_audio_path=str(audio_path),
        vfx_data={
            "vfx_plan": [
                {
                    "scene_id": "scene_000_hook",
                    "motion_preset_id": "opener_zoom_punch",
                    "transition_effect": "punch",
                },
                {
                    "scene_id": "scene_001",
                    "motion_preset_id": "photo_push_in",
                    "transition_effect": "whip",
                },
            ]
        },
        measured_durations=[2.0, 4.0, 4.0],
    )
    assert res.success
    tl = res.data["master_timeline"]
    assert len(tl.segments) == 3
    assert tl.segments[0].visual_path == str(hook_img)
    assert tl.segments[1].visual_path == str(sc0_img)
    assert tl.segments[2].visual_path == str(sc1_img)

    clips, _ = med.build_renderer_clips(tl, tmp_path / "work")
    assert len(clips) == 3
    assert clips[0].background == str(hook_img)
    assert clips[0].motion_preset_id == "opener_zoom_punch"
    assert clips[0].transition_effect == "punch"
    assert clips[1].motion_preset_id == "photo_push_in"
    assert clips[1].transition_effect == "whip"
    import shutil

    shutil.rmtree(Path("output") / "med_test_unit", ignore_errors=True)


def test_overlay_and_captions_vertical_safe_zone_no_overlap(tmp_path):
    engine = MotionGraphicsEngine()
    ov_path = tmp_path / "overlay.png"
    engine.compose_broadcast_overlay(
        out_path=str(ov_path),
        headline="सुप्रीम कोर्ट का ऐतिहासिक फैसला देशभर में लागू",
        category="राष्ट्रीय",
        story_index=1,
        total_stories=8,
        date_str="27 Nov",
        is_hook=False,
    )
    img = Image.open(ov_path).convert("RGBA")
    assert img.size == (1080, 1920)
    alpha = img.getchannel("A")

    # Ticker top begins at y=1605 -> lower-third band [1375..1580] should contain the headline box,
    # whereas caption safe zone bottom baseline is y = 1920 - 560 = 1360.
    # Verify pixels in headline backdrop band y=1440..1550 are non-transparent while y=1260..1355 is clear!
    cx = 540
    caption_zone_alpha = max(alpha.getpixel((cx, y)) for y in range(1240, 1360, 4))
    box_zone_alpha = max(alpha.getpixel((cx, y)) for y in range(1450, 1555, 4))
    gap_above_ticker_alpha = max(alpha.getpixel((cx, y)) for y in range(1572, 1598, 4))
    assert caption_zone_alpha == 0
    assert box_zone_alpha > 200
    assert gap_above_ticker_alpha == 0

    ass_path = SubtitleGenerator().generate_ass(
        [{"word": "ब्रेकिंग", "start": 0.0, "end": 0.4}, {"word": "न्यूज़", "start": 0.4, "end": 0.8}],
        str(tmp_path / "cap.ass"),
        font_size=90,
        margin_v=560,
    )
    ass_txt = Path(ass_path).read_text(encoding="utf-8")
    assert ",560,1" in ass_txt


def test_bundled_news_bgm_sfx_and_grade_resolution(tmp_path):
    renderer = VideoRenderer()
    music_path = renderer._pick_music()
    assert music_path is not None
    assert Path(music_path).exists()
    assert Path(music_path).stat().st_size > 100_000

    sfx_map = ensure_sfx()
    for key in ("whoosh", "pop", "hit", "click"):
        assert key in sfx_map
        assert Path(sfx_map[key]).exists()
        assert Path(sfx_map[key]).stat().st_size > 500

    assert "broadcast_crisp" in GRADES
    assert "eq=" in GRADES["broadcast_crisp"]

    # Render single minimal SceneClip frame using named grade and filter string without raising
    bg = tmp_path / "bg.jpg"
    ov = tmp_path / "ov.png"
    out = tmp_path / "clip.mp4"
    Image.new("RGB", (1080, 1920), (40, 60, 90)).save(bg)
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(ov)
    clip = SceneClip(
        background=str(bg),
        overlay=str(ov),
        duration=0.6,
        fx="punch",
        motion_preset_id="opener_headline_slam",
    )
    renderer.recipe = {"grade": "broadcast_crisp", "vignette": True}
    renderer._beat_clip(clip, 0.6, 0, str(out))
    assert out.exists() and out.stat().st_size > 5000


def test_semantic_matcher_entities_and_duplicate_asset_qa(tmp_path):
    assert (
        extract_entity_from_hindi("तिरुपति मंदिर में दर्शन व्यवस्था बदली")
        == "Tirumala Venkateswara Temple"
    )
    assert extract_entity_from_hindi("जीएसटी काउंसिल की अहम बैठक आज") == (
        "Goods and Services Tax (India)"
    )
    assert extract_entity_from_hindi("आयुष्मान भारत योजना का विस्तार") == "Ayushman Bharat Yojana"


@pytest.mark.asyncio
async def test_visual_audio_match_qa_flags_consecutive_duplicates(tmp_path):
    # VisualAudioMatchQAAgent detects identical visual paths reused across consecutive scenes
    img = tmp_path / "dup.jpg"
    Image.new("RGB", (200, 200), (120, 80, 40)).save(img)
    audio = tmp_path / "aud.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)

    cfg = load_config()
    cfg.database.sqlite_path = str(tmp_path / "qa.db")
    qa = VisualAudioMatchQAAgent(cfg, StateManager(cfg.database.sqlite_path))
    tl = SimpleNamespace(
        total_duration=4.0,
        master_audio_path=str(audio),
        segments=[
            SimpleNamespace(
                scene_id="scene_000_hook",
                start_time=0.0,
                end_time=2.0,
                text="संसद में बड़ा फैसला",
                visual_path=str(img),
                visual_query="Parliament of India",
                is_hook=True,
                asset_id="a1",
            ),
            SimpleNamespace(
                scene_id="scene_000",
                start_time=2.0,
                end_time=4.0,
                text="मौसम विभाग का अलर्ट जारी",
                visual_path=str(img),
                visual_query="IMD weather",
                is_hook=False,
                asset_id="a2",
            ),
        ],
    )
    res = await qa.execute(timeline=tl, video_path="")
    assert res is not None
    joined = " ".join(
        res.errors + res.data.get("warnings", []) + res.data.get("errors", [])
    ).lower()
    assert "duplicate" in joined or not res.success


def test_captions_isolated_by_clip_boundary_and_devanagari_fallback(tmp_path):
    words = [
        {"word": "राहत", "start": 0.1, "end": 0.4, "clip_idx": 0, "clip_end": 0.8},
        {"word": "दी", "start": 0.4, "end": 0.7, "clip_idx": 0, "clip_end": 0.8},
        {"word": "प्रधानमंत्री", "start": 0.85, "end": 1.2, "clip_idx": 1, "clip_end": 1.8},
        {"word": "मोदी", "start": 1.2, "end": 1.6, "clip_idx": 1, "clip_end": 1.8},
    ]
    groups = group_words(words, max_words=3, max_chars=25)
    assert len(groups) == 2
    assert [w["word"] for w in groups[0]] == ["राहत", "दी"]
    assert [w["word"] for w in groups[1]] == ["प्रधानमंत्री", "मोदी"]

    ass_path = SubtitleGenerator().generate_ass(words, str(tmp_path / "iso.ass"))
    lines = Path(ass_path).read_text(encoding="utf-8").splitlines()
    dlg = [ln for ln in lines if ln.startswith("Dialogue:")]
    # Last dialogue of clip 0 ends at 0.70 (never bleeds past clip_end=0.80 into clip 1)
    assert any(",0:00:00.70," in ln and "दी" in ln for ln in dlg)
    assert not any("राहत" in ln and "प्रधानमंत्री" in ln for ln in dlg)

    # Without raqm, chhoti-i matra visually reorders before consonant cluster
    from PIL import features

    if not features.check("raqm"):
        assert shape_devanagari("इतिहास") == "इ\u093fतहास"
        assert shape_devanagari("मिशन") == "\u093fमशन"
    else:
        assert shape_devanagari("इतिहास") == "इतिहास"
