"""Tests for Motion Graphics, VFX Engine & Semantic Visual Matcher."""

import os
from pathlib import Path
import pytest
from PIL import Image

from video.semantic_matcher import (
    SemanticVisualMatcher,
    extract_entity_from_hindi,
    detect_topic_theme,
)
from video.motion_graphics import MotionGraphicsEngine
from video.vfx_engine import VFXEngine


def test_extract_entity_from_hindi():
    assert extract_entity_from_hindi("बांकेबिहारी मंदिर में दर्शन के नए नियम लागू") == "Banke Bihari Temple"
    assert extract_entity_from_hindi("शेयर बाजार में सेंसेक्स 500 अंक लुढ़का") == "BSE SENSEX"
    assert extract_entity_from_hindi("पीएम मोदी ने नई वंदे भारत ट्रेन को हरी झंडी दिखाई") == "Narendra Modi"
    assert extract_entity_from_hindi("इसरो ने नया उपग्रह सफलतापूर्वक लॉन्च किया") == "ISRO"
    assert extract_entity_from_hindi("सुप्रीम कोर्ट ने बड़ा फैसला सुनाया") == "Supreme Court of India"
    assert extract_entity_from_hindi("सामान्य दिन की शुरुआत हुई") is None


def test_detect_topic_theme():
    assert detect_topic_theme("सेंसेक्स और निफ्टी में भारी तेजी") == "finance"
    assert detect_topic_theme("बांकेबिहारी मंदिर में दर्शन") == "temple"
    assert detect_topic_theme("वंदे भारत ट्रेन की नई समय सारिणी") == "railways"
    assert detect_topic_theme("इसरो का चंद्रयान मिशन") == "space"
    assert detect_topic_theme("सेना के जवान और मिसाइल परीक्षण") == "defence"
    assert detect_topic_theme("मौसम विभाग ने घने कोहरे की चेतावनी दी") == "weather"


def test_motion_graphics_compose_overlay(tmp_path):
    engine = MotionGraphicsEngine(channel_name="BHARAT KI SOCH")
    out_file = tmp_path / "test_overlay.png"

    path = engine.compose_broadcast_overlay(
        out_path=str(out_file),
        headline="बांकेबिहारी मंदिर में दर्शन के नए नियम लागू",
        category="राष्ट्रीय",
        story_index=1,
        total_stories=20,
        date_str="18 नवंबर 2026",
        is_hook=False,
    )

    assert Path(path).exists()
    im = Image.open(path)
    assert im.size == (1080, 1920)
    assert im.mode == "RGBA"


def test_motion_graphics_hook_overlay(tmp_path):
    engine = MotionGraphicsEngine(channel_name="BHARAT KI SOCH")
    out_file = tmp_path / "test_hook_overlay.png"

    path = engine.compose_broadcast_overlay(
        out_path=str(out_file),
        headline="आज की 20 बड़ी खबरें: देश और दुनिया की हर हलचल",
        category="बड़ी खबर",
        story_index=0,
        total_stories=20,
        date_str="18 नवंबर 2026",
        is_hook=True,
    )

    assert Path(path).exists()
    im = Image.open(path)
    assert im.size == (1080, 1920)


def test_vfx_engine():
    vfx = VFXEngine(color_grade="broadcast_crisp")
    flt = vfx.get_color_filter()
    assert "contrast" in flt
    assert "vignette" in flt

    trans = vfx.get_transition_effect("punch")
    assert "fade" in trans or "color" in trans

    zoom, x, y = vfx.get_camera_motion(idx=0, total_frames=60)
    assert "zoom" in zoom or "min" in zoom
