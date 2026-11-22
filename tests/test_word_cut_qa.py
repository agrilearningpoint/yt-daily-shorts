"""Tests for word-cut QA verification in video.word_cut_qa."""

from core.agent_contracts import WordCut, WordCutPlan
from video.word_cut_qa import validate_word_cuts
from video.word_timeline import TokenType, WordToken


def test_validate_word_cuts_pass():
    cuts = [
        WordCut(
            group_id="wg_000",
            start=0.0,
            end=10.0,
            text="first sentence with content",
            words=[
                WordToken("first", "first", 0.0, 3.0, TokenType.CUT),
                WordToken("sentence", "sentence", 3.0, 6.0, TokenType.CUT),
                WordToken("with", "with", 6.0, 8.0, TokenType.GLUE),
                WordToken("content", "content", 8.0, 10.0, TokenType.CUT),
            ],
            visual_asset="bg1.png",
        ),
        WordCut(
            group_id="wg_001",
            start=10.0,
            end=25.0,
            text="second sentence concludes the story",
            words=[
                WordToken("second", "second", 10.0, 14.0, TokenType.CUT),
                WordToken("sentence", "sentence", 14.0, 18.0, TokenType.CUT),
                WordToken("concludes", "concludes", 18.0, 22.0, TokenType.CUT),
                WordToken("the", "the", 22.0, 23.0, TokenType.GLUE),
                WordToken("story", "story", 23.0, 25.0, TokenType.CUT),
            ],
            visual_asset="bg2.png",
        ),
    ]

    plan = WordCutPlan(
        video_id="qa_test_pass",
        fps=30,
        audio_path="",
        duration=25.0,
        cuts=cuts,
    )

    res = validate_word_cuts(plan, auto_repair=False, is_shorts=True)
    assert res.passed
    assert res.coverage_score == 1.0
    assert len(res.errors) == 0


def test_validate_word_cuts_missing_words():
    plan = WordCutPlan(
        video_id="qa_empty",
        fps=30,
        audio_path="",
        duration=20.0,
        cuts=[],
    )
    res = validate_word_cuts(plan, auto_repair=False)
    assert not res.passed
    assert any("0 cuts" in e for e in res.errors)


def test_validate_word_cuts_overlap_and_gap():
    cuts = [
        WordCut(
            group_id="wg_000",
            start=0.0,
            end=10.0,
            text="word one",
            words=[WordToken("word", "word", 0.0, 5.0, TokenType.CUT)],
        ),
        WordCut(
            group_id="wg_001",
            start=12.0,  # 2.0s gap from 10.0
            end=20.0,
            text="word two",
            words=[WordToken("word", "word", 12.0, 20.0, TokenType.CUT)],
        ),
    ]
    plan = WordCutPlan(
        video_id="qa_gap",
        fps=30,
        audio_path="",
        duration=20.0,
        cuts=cuts,
    )
    # Without auto-repair, gap should fail
    res_no_repair = validate_word_cuts(plan, auto_repair=False)
    assert not res_no_repair.passed
    assert any("gap" in e.lower() for e in res_no_repair.errors)

    # With auto-repair, gap should be closed
    res_repaired = validate_word_cuts(plan, auto_repair=True)
    assert res_repaired.repaired
    assert cuts[0].end == cuts[1].start


def test_validate_word_cuts_drift():
    cuts = [
        WordCut(
            group_id="wg_000",
            start=0.0,
            end=20.0,
            text="drifted word",
            words=[
                # first word starts at 0.2s while cut starts at 0.0s -> 200ms drift
                WordToken("drifted", "drifted", 0.2, 10.0, TokenType.CUT),
                WordToken("word", "word", 10.0, 20.0, TokenType.CUT),
            ],
        )
    ]
    plan = WordCutPlan(
        video_id="qa_drift",
        fps=30,
        audio_path="",
        duration=20.0,
        cuts=cuts,
    )
    res = validate_word_cuts(plan, auto_repair=False)
    assert res.max_drift_ms >= 150.0
    assert any("drift" in w.lower() for w in res.warnings)
