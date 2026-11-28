"""Post-render vision audit.

The keyword score compares words to words; it cannot see that a frame shows an unrelated poster.
These tests pin the behaviour that actually caught that class of bug in a real run.
"""

from __future__ import annotations

from core.publish_gate import PublishGate, QualityReport
from video.vision_audit import VisionAuditor, _beats


def _timeline():
    return {
        "segments": [
            {
                "segment_id": "s0",
                "text": "मुंबई एयरपोर्ट",
                "audio_start": 0,
                "audio_end": 4,
                "visual_path": "/a.jpg",
            },
            {
                "segment_id": "s1",
                "text": "आज 28 नवंबर",
                "audio_start": 4,
                "audio_end": 8,
                "visual_path": "",
            },
            {
                "segment_id": "s2",
                "text": "इसरो का रॉकेट",
                "audio_start": 8,
                "audio_end": 12,
                "visual_path": "/c.jpg",
            },
        ]
    }


def test_beats_accept_dict_and_nested_payload():
    assert len(_beats(_timeline())) == 3
    assert len(_beats({"master_timeline": _timeline()})) == 3
    assert _beats(None) == []


def test_designed_card_is_skipped_not_judged(tmp_path):
    """A beat with no photograph is a title card on purpose — judging it only makes false alarms."""
    judged = []

    class A(VisionAuditor):
        def extract_frame(self, video_path, at_seconds, dest):  # pretend ffmpeg worked
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x" * 2048)
            return True

    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake" * 100)
    auditor = A(judge=lambda p, d: judged.append(d) or True)
    report = auditor.audit(str(video), _timeline(), tmp_path / "frames")
    assert report["checked"] == 2  # the card beat was skipped
    assert any(s["why"] == "designed card" for s in report["skipped"])


def test_rejected_frame_blocks_publication(tmp_path):
    class A(VisionAuditor):
        def extract_frame(self, video_path, at_seconds, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x" * 2048)
            return True

    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake" * 100)
    report = A(judge=lambda p, d: False).audit(str(video), _timeline(), tmp_path)
    assert report["approved"] is False and report["rejected"]
    gate = PublishGate()
    q = QualityReport("v")
    gate.check_vision_audit(q, {"vision_audit": report})
    assert not q.approved


def test_no_opinion_is_not_a_pass():
    q = QualityReport("v")
    PublishGate().check_vision_audit(
        q, {"vision_audit": {"checked": 0, "rejected": [], "reason": "quota"}}
    )
    assert not q.approved  # "could not measure" is a gap, not a pass


def test_missing_audit_is_a_failure():
    q = QualityReport("v")
    PublishGate().check_vision_audit(q, {})
    assert not q.approved
