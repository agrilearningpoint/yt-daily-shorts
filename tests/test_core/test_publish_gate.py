"""Publish gate tests.

The gate is the last thing between a broken render and the channel, so these tests focus on the
property that actually matters: **missing evidence is a failure**, not a pass.
"""

from __future__ import annotations

import json

import pytest

from core.publish_gate import THRESHOLDS, Check, GateBlocked, PublishGate, QualityReport


def _timeline(n=3, visual=True):
    return {
        "segments": [
            {
                "segment_id": f"seg_{i}",
                "text": f"line {i}",
                "visual_path": f"/tmp/img{i}.jpg" if visual else "",
                "audio_path": "/tmp/voice.mp3",
            }
            for i in range(n)
        ]
    }


def _passing_qa(n=3):
    return {
        "approved": True,
        "average_semantic_score": 0.62,
        "segment_count": n,
        "scored_segments": n,
        "max_black_duration": 0.2,
        "max_silence_duration": 0.4,
    }


def test_blocks_when_nothing_can_be_verified(tmp_path):
    gate = PublishGate()
    with pytest.raises(GateBlocked) as exc:
        gate.run("vid", video_path="", output_dir=tmp_path)
    reasons = " ".join(exc.value.reasons)
    assert "video_file" in reasons
    assert "visual_match" in reasons  # no measured score == blocked


def test_report_is_written_even_when_blocked(tmp_path):
    gate = PublishGate()
    with pytest.raises(GateBlocked):
        gate.run("vid_blocked", video_path="", output_dir=tmp_path)
    report = json.loads((tmp_path / "quality_report.json").read_text(encoding="utf-8"))
    assert report["verdict"] == "BLOCKED"
    assert report["approved"] is False
    assert report["blocking_reasons"]
    assert report["thresholds"]["min_visual_match"] == THRESHOLDS["min_visual_match"]


def test_visual_match_below_threshold_blocks(tmp_path):
    report = QualityReport(video_id="v")
    gate = PublishGate()
    qa = _passing_qa()
    qa["average_semantic_score"] = 0.10
    gate.check_visual_match(report, qa)
    assert not report.approved
    assert any(c.name == "visual_match_score" for c in report.blocking)


def test_unscored_beats_block_even_with_a_good_average(tmp_path):
    """A 0.9 average over 1 of 20 beats is not evidence about the other 19."""
    report = QualityReport(video_id="v")
    PublishGate().check_visual_match(
        report,
        {"average_semantic_score": 0.9, "segment_count": 20, "scored_segments": 2},
    )
    assert not report.approved
    assert [c.name for c in report.blocking] == ["visual_match_coverage"]


def test_story_without_a_picture_blocks(tmp_path):
    report = QualityReport(video_id="v")
    PublishGate().check_story_slides(report, _timeline(4, visual=False), {})
    assert not report.approved


def test_missing_timeline_is_a_failure_not_a_skip(tmp_path):
    report = QualityReport(video_id="v")
    PublishGate().check_story_slides(report, None, {})
    assert not report.approved


def test_black_and_silence_over_limit_block():
    report = QualityReport(video_id="v")
    PublishGate().check_black_and_silence(
        report, "", {"max_black_duration": 4.0, "max_silence_duration": 0.1}
    )
    names = [c.name for c in report.blocking]
    assert "black_frames" in names
    assert "silence" not in names


def test_editorial_score_is_a_warning_not_a_block():
    report = QualityReport(video_id="v")
    PublishGate().check_editorial(report, {"score": 4.0})
    assert report.approved  # approved, because the hard checks decide publication
    assert [c.name for c in report.warnings] == ["editorial_score"]
    assert report.verdict() == "APPROVED_WITH_WARNINGS"


def test_voice_and_captions_are_checked_not_assumed(tmp_path):
    report = QualityReport(video_id="v")
    gate = PublishGate()
    gate.check_voice(report, {}, None)
    gate.check_captions(report, {})
    assert not report.approved  # no voice
    assert [c.name for c in report.warnings] == ["captions"]


def test_check_dataclass_reports_status():
    assert Check(name="x", passed=True).status == "pass"
    assert Check(name="x", passed=False).status == "block"
    assert Check(name="x", passed=False, critical=False).status == "warn"


def test_dry_run_and_live_share_the_same_gate(tmp_path):
    """The gate must not have a dry-run bypass: a dry run that skips QA proves nothing."""
    import inspect

    source = inspect.getsource(PublishGate.run)
    assert "dry_run" not in source
