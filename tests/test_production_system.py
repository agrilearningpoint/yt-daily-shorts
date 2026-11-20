"""Unit tests for the upgraded multi-agent architecture and synchronization engine."""

from core.production_context import STAGE_DEPENDENCY_GRAPH, ProductionContext
from core.state_manager import StateManager
from video.qa_inspector import VideoQAInspector
from video.synchronization_engine import SynchronizationEngine


def test_production_context_dependency_graph():
    """Verify production context tracks downstream dependencies."""
    ProductionContext(video_id="test_001", run_id="test_001", video_type="news")
    assert "script_generation" in STAGE_DEPENDENCY_GRAPH
    downstream = STAGE_DEPENDENCY_GRAPH["script_generation"]
    assert "video_production" in downstream
    assert "publishing" in downstream


def test_state_manager_downstream_invalidation(tmp_path):
    """Verify that StateManager can invalidate downstream checkpoints."""
    db_file = tmp_path / "test.db"
    sm = StateManager(str(db_file))
    sm.save_checkpoint("vid_1", "script_generation", {"text": "hello"})
    sm.save_checkpoint("vid_1", "video_production", {"status": "rendered"})
    sm.save_checkpoint("vid_1", "publishing", {"youtube_id": "123"})

    assert sm.load_checkpoint("vid_1", "video_production") is not None

    invalidated = sm.invalidate_downstream("vid_1", "script_generation")
    assert "video_production" in invalidated
    assert sm.load_checkpoint("vid_1", "video_production") is None
    assert sm.load_checkpoint("vid_1", "publishing") is None
    # Upstream script_generation is still kept
    assert sm.load_checkpoint("vid_1", "script_generation") is not None


def test_synchronization_engine_zero_drift():
    """Verify that SynchronizationEngine quantizes frame boundaries with zero cumulative drift."""
    sync = SynchronizationEngine(fps=30, max_drift_tolerance=0.05)

    beats = [
        {"kind": "hook", "text": "Hook text", "parts": [{"say": "Hook text", "entity": "India"}]},
        {"kind": "item", "text": "Story 1", "parts": [{"say": "Story 1", "entity": "ISRO"}]},
        {
            "kind": "item",
            "text": "Story 2",
            "parts": [{"say": "Story 2", "entity": "Supreme Court"}],
        },
        {
            "kind": "outro",
            "text": "Subscribe text",
            "parts": [{"say": "Subscribe text", "entity": ""}],
        },
    ]
    # Arbitrary non-integer frame durations
    raw_durs = [2.633, 2.417, 2.891, 3.123]
    seg_owner = [(0, 0), (1, 0), (2, 0), (3, 0)]
    assets = {
        (0, 0): type("Asset", (), {"path": "/tmp/hook.jpg"})(),
        (1, 0): type("Asset", (), {"path": "/tmp/s1.jpg"})(),
        (2, 0): type("Asset", (), {"path": "/tmp/s2.jpg"})(),
        (3, 0): type("Asset", (), {"path": "/tmp/outro.jpg"})(),
    }

    timeline = sync.build_timeline(beats, raw_durs, seg_owner, assets, fps=30, tail=0.0)
    assert len(timeline.segments) == 4

    # Check that each segment is an exact integer multiple of 1/30
    for seg in timeline.segments:
        seg_dur = seg.audio_end - seg.audio_start
        frames = round(seg_dur * 30)
        assert abs(seg_dur - (frames / 30)) < 1e-3

    # Run sync verification
    report = sync.verify_sync(timeline)
    assert report.is_valid is True
    assert report.drift_seconds == 0.0
    assert len(report.errors) == 0


def test_hook_director_scoring():
    """Verify HookDirector scoring matrix and archetype assignment."""
    from agents.hook_director.agent import HookDirectorAgent
    from core.configuration import AppConfig

    cfg = AppConfig()
    sm = StateManager(":memory:")
    agent = HookDirectorAgent(cfg, sm)

    lead_story = {
        "title": "सुप्रीम कोर्ट ने नया फैसला सुनाया",
        "summary": "उच्चतम न्यायालय ने महत्वपूर्ण निर्देश जारी किए।",
        "verified": True,
    }

    cand = agent._score_candidate(
        text="सुप्रीम कोर्ट के इस बड़े फैसले से पूरा देश हैरान!",
        archetype="breaking_news",
        lead_story=lead_story,
        paired_entity="Supreme Court of India",
    )

    assert cand.composite_score >= 75.0
    assert cand.impact_score >= 70.0
    assert cand.factual_score >= 70.0


def test_video_qa_inspector_duration_bounds():
    """Verify VideoQAInspector enforces Shorts limits."""
    inspector = VideoQAInspector(max_duration=59.9, min_duration=15.0)

    # Fake stream info check
    from video.qa_inspector import MediaStreamInfo

    info = MediaStreamInfo(
        has_video=True, has_audio=True, width=1080, height=1920, fps=30.0, duration=55.0
    )
    assert info.duration <= inspector.max_duration
    assert info.duration >= inspector.min_duration
