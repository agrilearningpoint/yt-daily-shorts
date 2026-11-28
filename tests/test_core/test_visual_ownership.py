"""Story -> picture ownership.

The renderer used to address pictures by (beat_index, part_index). One added section card and
every picture shifted one story: the voice said "रांची" and the screen showed the next story's
photo. Ownership is now built from scene IDs, and the publish gate refuses a table with problems.
"""

from __future__ import annotations

from core.publish_gate import PublishGate, QualityReport
from core.visual_ownership import build, scene_id_for, validate


class _Asset:
    def __init__(self, path="", source="pexels", labels="", match=0.8):
        self.path = path
        self.source = source
        self.labels = labels
        self.match = match


def _beats():
    return [
        {"kind": "hook", "text": "hook line", "parts": [{"say": "hook line"}]},
        {"kind": "item", "text": "story one", "parts": [{"say": "story one"}]},
        {
            "kind": "section",
            "section": "national",
            "text": "ab badi khabrein",
            "parts": [{"say": "x"}],
        },
        {"kind": "item", "text": "story two", "parts": [{"say": "story two"}]},
        {"kind": "outro", "text": "outro", "parts": [{"say": "outro"}]},
    ]


def test_scene_ids_are_stable_and_never_indexes():
    assert scene_id_for({"kind": "hook"}, 0) == "story_hook"
    assert scene_id_for({"kind": "item"}, 1) == "story_001"
    assert scene_id_for({"kind": "section", "section": "national"}, 2) == "section_national"
    assert scene_id_for({"kind": "outro"}, 3) == "outro"


def test_story_numbering_skips_cards():
    rows = build(_beats(), {(i, 0): _Asset(path=f"/tmp/{i}.jpg") for i in range(5)})
    assert [r.scene_id for r in rows] == [
        "story_hook",
        "story_001",
        "section_national",
        "story_002",
        "outro",
    ]
    assert [r.story_id for r in rows] == ["", "story_001", "", "story_002", ""]


def test_story_without_a_picture_is_a_problem():
    rows = build(_beats(), {(0, 0): _Asset("/tmp/a.jpg")})  # only the hook has an image
    problems = validate(rows)
    assert any("story_001" in p and "no picture" in p for p in problems)


def test_duplicate_scene_ids_are_a_problem():
    from core.visual_ownership import VisualOwnership

    rows = [
        VisualOwnership(scene_id="story_001", story_id="story_001", kind="item", asset_path="/a"),
        VisualOwnership(scene_id="story_001", story_id="story_001", kind="item", asset_path="/b"),
    ]
    assert any("duplicate" in p for p in validate(rows))


def test_gate_blocks_when_ownership_is_missing():
    report = QualityReport(video_id="v")
    PublishGate().check_ownership(report, {})
    assert [c.name for c in report.blocking] == ["visual_ownership"]


def test_gate_blocks_on_ownership_problems():
    report = QualityReport(video_id="v")
    PublishGate().check_ownership(
        report, {"visual_ownership": [{"scene_id": "story_001"}], "ownership_problems": ["x"]}
    )
    assert not report.approved


def test_gate_passes_a_clean_table():
    report = QualityReport(video_id="v")
    PublishGate().check_ownership(
        report, {"visual_ownership": [{"scene_id": "story_001"}], "ownership_problems": []}
    )
    assert report.approved
