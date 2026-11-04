"""Video layer unit tests (offline)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from video.creative_variation import CreativeVariationEngine
from video.scene_composer import SceneComposer, font
from video.subtitle_generator import SubtitleGenerator, group_words
from video.tts import distribute_words


def test_creative_theme_rotation_by_type():
    engine = CreativeVariationEngine()
    names = {engine.get_next_theme("news").name for _ in range(6)}
    assert len(names) >= 2


def test_word_distribution_and_grouping():
    words = distribute_words("आज की पहली बड़ी खबर भारत सरकार से जुड़ी है।", 4.0)
    assert words and abs(words[-1].end - 4.0) < 0.01
    groups = group_words([vars(w) for w in words])
    assert all(len(g) <= 3 for g in groups)


def test_ass_and_srt(tmp_path: Path):
    words = [vars(w) for w in distribute_words("तकनीकी क्षेत्र में यह एक बड़ा कदम साबित होगा।", 3.0)]
    gen = SubtitleGenerator()
    ass = Path(gen.generate_ass(words, str(tmp_path / "c.ass")))
    text = ass.read_text(encoding="utf-8")
    assert "Mukta ExtraBold" in text and "Dialogue:" in text and "कदम" in text
    srt = Path(gen.generate_srt_from_words(words, str(tmp_path / "s.srt")))
    assert "-->" in srt.read_text(encoding="utf-8")


def test_devanagari_font_loads():
    f = font(80)
    assert "Mukta" in " ".join(f.getname())


def test_scene_composer_layers(tmp_path: Path):
    comp = SceneComposer({"primary_color": "#FF9933"}, channel_name="Test Channel")
    bg = comp.compose_background(None, str(tmp_path / "bg.jpg"), seed=1, card_text="इसरो का नया मिशन")
    ov = comp.compose_overlay(str(tmp_path / "ov.png"), "बड़ा फैसला", "आज की बड़ी खबरें", 0, 3, "4 नवंबर 2026")
    assert Image.open(bg).size[0] > 1080
    assert Image.open(ov).size == (1080, 1920)
