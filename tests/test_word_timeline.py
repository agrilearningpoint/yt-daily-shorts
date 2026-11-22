"""Tests for video.word_timeline module."""

import pytest
from video.tts import WordTiming
from video.word_timeline import TokenType, WordTimelineBuilder


def test_tokenization_basic():
    builder = WordTimelineBuilder()
    text = "मेरा नाम सिंह है! 2026 में, AI-driven short 😊."
    tokens = builder.tokenize(text)
    texts = [t.text for t in tokens]

    assert "मेरा" in texts
    assert "नाम" in texts
    assert "सिंह" in texts
    assert "है" in texts
    assert "!" in texts
    assert "2026" in texts
    assert "में" in texts
    assert "," in texts
    assert "AI-driven" in texts
    assert "short" in texts
    assert "😊" in texts


def test_classification():
    builder = WordTimelineBuilder()
    text = "the president is in भारत और वह बोले"
    tokens = builder.tokenize(text)
    classified = builder.classify(tokens)

    by_text = {t.text: t.token_type for t in classified}
    assert by_text["the"] == TokenType.GLUE
    assert by_text["president"] == TokenType.CUT
    assert by_text["is"] == TokenType.GLUE
    assert by_text["in"] == TokenType.GLUE
    assert by_text["भारत"] == TokenType.CUT
    assert by_text["और"] == TokenType.GLUE
    assert by_text["वह"] == TokenType.GLUE
    assert by_text["बोले"] == TokenType.CUT


def test_english_singh_three_groups():
    builder = WordTimelineBuilder()
    tokens = builder.tokenize("my name is singh")
    classified = builder.classify(tokens)
    groups = builder.group(classified)

    assert len(groups) == 3
    assert groups[0].text == "my"
    assert groups[1].text == "name"
    assert groups[2].text == "is singh"


def test_hindi_singh_three_groups():
    builder = WordTimelineBuilder()
    tokens = builder.tokenize("मेरा नाम सिंह है")
    classified = builder.classify(tokens)
    groups = builder.group(classified)

    assert len(groups) == 3
    assert groups[0].text == "मेरा"
    assert groups[1].text == "नाम"
    assert groups[2].text == "सिंह है"


def test_min_and_max_words_per_group():
    builder = WordTimelineBuilder()
    text = "in the word1 at the word2 on the word3"
    tokens = builder.tokenize(text)
    classified = builder.classify(tokens)
    groups = builder.group(classified, policy={"word_cut_max_words_per_group": 3})

    assert len(groups) == 3
    for g in groups:
        assert len([w for w in g.words if w.token_type != TokenType.PUNCT]) <= 3


def test_timeline_builder_full():
    builder = WordTimelineBuilder(fps=30)
    script = "मेरा नाम सिंह है"

    class MockVoice:
        audio_path = "dummy.mp3"
        provider = "edge-tts"
        durations = [1.2]
        beat_words = [
            [
                WordTiming("मेरा", 0.0, 0.3),
                WordTiming("नाम", 0.3, 0.6),
                WordTiming("सिंह", 0.6, 0.9),
                WordTiming("है", 0.9, 1.2),
            ]
        ]

    timeline = builder.build(script, MockVoice(), config={"fps": 30})

    assert len(timeline.groups) == 3
    assert timeline.groups[0].text == "मेरा"
    assert timeline.groups[1].text == "नाम"
    assert timeline.groups[2].text == "सिंह है"

    # Frame accuracy and monotonicity
    assert timeline.groups[0].start == 0.0
    assert timeline.groups[0].end == timeline.groups[1].start
    assert timeline.groups[1].end == timeline.groups[2].start
    assert timeline.groups[2].end == pytest.approx(1.2, abs=0.05)


def test_tiny_group_merging():
    builder = WordTimelineBuilder(fps=30)
    script = "quick flash jump"

    class MockVoiceTiny:
        audio_path = "dummy.mp3"
        provider = "test"
        durations = [1.0]
        beat_words = [
            [
                WordTiming("quick", 0.0, 0.5),
                WordTiming("flash", 0.5, 0.52),  # 20ms -> less than 66ms (2 frames)
                WordTiming("jump", 0.52, 1.0),
            ]
        ]

    timeline = builder.build(
        script, MockVoiceTiny(), config={"fps": 30, "word_cut_min_group_ms": 66}
    )
    # The tiny 20ms group must be merged
    for g in timeline.groups:
        assert g.duration >= 0.06
