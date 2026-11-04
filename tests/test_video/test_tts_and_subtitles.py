"""Unit tests for video subtitles, media, and creative variations."""

from __future__ import annotations

import tempfile
from pathlib import Path
from video.creative_variation import CreativeVariationEngine
from video.media_collector import MediaCollector
from video.subtitle_generator import SubtitleGenerator


def test_creative_theme_rotation():
    engine = CreativeVariationEngine()
    t1 = engine.get_next_theme()
    t2 = engine.get_next_theme()
    assert t1.name != ""
    assert t2.name != ""


def test_subtitle_generator():
    gen = SubtitleGenerator()
    scenes = [
        {"scene_number": 1, "narration": "आज की पहली बड़ी खबर भारत सरकार के नए निर्णय से जुड़ी है।", "duration": 15.0},
        {"scene_number": 2, "narration": "तकनीकी क्षेत्र में यह एक बड़ा कदम साबित होगा।", "duration": 18.0}
    ]
    with tempfile.TemporaryDirectory() as tmp_dir:
        srt_path = str(Path(tmp_dir) / "test.srt")
        out = gen.generate_srt(scenes, srt_path)
        assert Path(out).exists()
        content = Path(out).read_text(encoding="utf-8")
        assert "-->" in content
        assert "खबर" in content


def test_media_procedural_card():
    collector = MediaCollector()
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest = str(Path(tmp_dir) / "card.jpg")
        res = collector._generate_procedural_card(1, "ISRO Space Exploration Mission", dest, "knowledge")
        assert Path(res).exists()
        assert Path(res).stat().st_size > 1000
