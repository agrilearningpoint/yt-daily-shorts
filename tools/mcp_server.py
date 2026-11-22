"""Model Context Protocol (MCP) server for word-cut editing & video publishing.

Exposes deterministic tools for AI coding assistants (Claude Code, OpenCode, Antigravity):
  - word_cut_plan: Tokenize, classify, and create a WordCutPlan.
  - word_cut_render: Render contiguous visual cuts with master audio.
  - word_cut_qa: Validate coverage, drift, gaps, audio continuity.
  - youtube_upload: Publish video to YouTube channel with metadata.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_contracts import WordCut, WordCutPlan  # noqa: E402
from video.renderer import render_word_cuts  # noqa: E402
from video.tts import probe_duration  # noqa: E402
from video.word_cut_qa import validate_word_cuts  # noqa: E402
from video.word_timeline import TokenType, WordTimelineBuilder, WordToken  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp_server")


def tool_word_cut_plan(
    script: str,
    audio_path: str = "",
    fps: int = 30,
    max_words_per_group: int = 3,
    min_group_ms: float = 66.0,
    glue_policy: str = "auto",
) -> Dict[str, Any]:
    """Build a frame-accurate, contiguous WordCutPlan from script text."""
    builder = WordTimelineBuilder(fps=fps)
    audio_dur = probe_duration(audio_path) if audio_path and Path(audio_path).exists() else 0.0

    class DummyAudio:
        provider = "mcp"

    a_obj = DummyAudio()
    setattr(a_obj, "audio_path", audio_path)
    setattr(a_obj, "durations", [audio_dur] if audio_dur > 0 else [])

    timeline = builder.build(
        script,
        a_obj,
        config={
            "fps": fps,
            "word_cut_max_words_per_group": max_words_per_group,
            "word_cut_min_group_ms": min_group_ms,
            "word_cut_glue_policy": glue_policy,
        },
    )

    cuts = [
        WordCut(
            group_id=g.group_id,
            start=g.start,
            end=g.end,
            text=g.text,
            words=g.words,
            visual_asset="",
            motion_preset_id="ken_burns_zoom_in",
            transition_effect="none",
        )
        for g in timeline.groups
    ]

    plan = WordCutPlan(
        video_id="mcp_plan",
        fps=fps,
        audio_path=audio_path,
        duration=timeline.audio_duration or audio_dur,
        cuts=cuts,
        captions=[
            {"word": w.text, "start": w.start, "end": w.end}
            for w in timeline.words
            if w.token_type != TokenType.PUNCT
        ],
        warnings=list(timeline.warnings),
    )
    return plan.to_dict()


def tool_word_cut_render(plan_data: Dict[str, Any], out_path: str = "output/mcp_video.mp4") -> Dict[str, Any]:
    """Render WordCutPlan to high-definition vertical video with continuous audio."""
    cuts = []
    for c in plan_data.get("cuts", []):
        words = [
            WordToken(
                text=w.get("text", ""),
                normalized=w.get("normalized", ""),
                start=w.get("start", 0.0),
                end=w.get("end", 0.0),
                token_type=TokenType(w.get("token_type", "cut")),
                confidence=w.get("confidence", 1.0),
            )
            for w in c.get("words", [])
        ]
        cuts.append(
            WordCut(
                group_id=c.get("group_id", ""),
                start=c.get("start", 0.0),
                end=c.get("end", 0.0),
                text=c.get("text", ""),
                words=words,
                visual_asset=c.get("visual_asset", ""),
                motion_preset_id=c.get("motion_preset_id", "ken_burns_zoom_in"),
                transition_effect=c.get("transition_effect", "none"),
                vfx_cue=c.get("vfx_cue"),
            )
        )

    plan = WordCutPlan(
        video_id=plan_data.get("video_id", "mcp_render"),
        fps=plan_data.get("fps", 30),
        audio_path=plan_data.get("audio_path", ""),
        duration=plan_data.get("duration", 0.0),
        cuts=cuts,
        captions=plan_data.get("captions", []),
    )

    rendered_file = render_word_cuts(plan, out_path)
    return {"status": "SUCCESS", "rendered_file": rendered_file}


def tool_word_cut_qa(plan_data: Dict[str, Any], video_path: Optional[str] = None) -> Dict[str, Any]:
    """Validate word-level plan and rendered MP4."""
    cuts = [
        WordCut(
            group_id=c.get("group_id", ""),
            start=c.get("start", 0.0),
            end=c.get("end", 0.0),
            text=c.get("text", ""),
            words=[
                WordToken(
                    text=w.get("text", ""),
                    normalized=w.get("normalized", ""),
                    start=w.get("start", 0.0),
                    end=w.get("end", 0.0),
                    token_type=TokenType(w.get("token_type", "cut")),
                )
                for w in c.get("words", [])
            ],
            visual_asset=c.get("visual_asset", ""),
        )
        for c in plan_data.get("cuts", [])
    ]
    plan = WordCutPlan(
        video_id=plan_data.get("video_id", "mcp_qa"),
        fps=plan_data.get("fps", 30),
        audio_path=plan_data.get("audio_path", ""),
        duration=plan_data.get("duration", 0.0),
        cuts=cuts,
    )
    res = validate_word_cuts(plan, video_path=video_path, auto_repair=True)
    return res.to_dict()


def tool_youtube_upload(
    video_path: str, title: str, description: str, tags: List[str]
) -> Dict[str, Any]:
    """Publish video via YouTube Data API v3 or dry-run."""
    from core.configuration import load_config
    from youtube.oauth import YouTubeOAuthManager
    from youtube.uploader import YouTubeUploader

    cfg = load_config()
    oauth = YouTubeOAuthManager(cfg.youtube.client_secret_json, cfg.youtube.token_json)
    uploader = YouTubeUploader(oauth, dry_run=cfg.youtube.dry_run, strict=False)
    result = uploader.upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
    )
    return result or {"status": "SKIPPED"}


TOOL_REGISTRY = {
    "word_cut_plan": tool_word_cut_plan,
    "word_cut_render": tool_word_cut_render,
    "word_cut_qa": tool_word_cut_qa,
    "youtube_upload": tool_youtube_upload,
}


def dispatch_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown MCP tool: {tool_name}. Available: {list(TOOL_REGISTRY.keys())}")
    return TOOL_REGISTRY[tool_name](**arguments)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        print(json.dumps(list(TOOL_REGISTRY.keys()), indent=2))
        return 0

    print("MCP Server ready. Stdio tool dispatcher active.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
