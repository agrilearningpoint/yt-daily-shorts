"""Deterministic CLI tool for word-level cut planning, rendering, and QA.

Commands:
  plan   --script ... [--voice ... | --timings ...] --out word_plan.json
  render --plan word_plan.json [--audio master.wav] --out final.mp4
  qa     --plan word_plan.json [--video final.mp4] --report qa.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_contracts import WordCut, WordCutPlan  # noqa: E402
from video.renderer import render_word_cuts  # noqa: E402
from video.tts import WordTiming  # noqa: E402
from video.word_cut_qa import validate_word_cuts  # noqa: E402
from video.word_timeline import TokenType, WordTimelineBuilder, WordToken  # noqa: E402


def cmd_plan(args: argparse.Namespace) -> int:
    script_text = ""
    if args.script:
        p = Path(args.script)
        if p.exists():
            script_text = p.read_text(encoding="utf-8")
        else:
            script_text = args.script

    if not script_text.strip():
        print("✗ Empty script text", file=sys.stderr)
        return 1

    # Load timings if provided
    raw_timings = []
    if args.timings and Path(args.timings).exists():
        data = json.loads(Path(args.timings).read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                raw_timings.append(
                    WordTiming(
                        word=item.get("word") or item.get("text", ""),
                        start=float(item.get("start", 0.0)),
                        end=float(item.get("end", 0.0)),
                        confidence=float(item.get("confidence", 1.0)),
                    )
                )

    class MockVoice:
        audio_path = args.audio or ""
        provider = "cli"
        durations = [float(args.duration)] if args.duration else []
        beat_words = [raw_timings] if raw_timings else []

    builder = WordTimelineBuilder(fps=args.fps)
    timeline = builder.build(
        script_text,
        MockVoice(),
        config={
            "fps": args.fps,
            "word_cut_max_group_seconds": args.max_group_sec,
            "word_cut_max_words_per_group": args.max_words,
            "word_cut_min_group_ms": args.min_group_ms,
            "word_cut_glue_policy": args.glue_policy,
        },
    )

    cuts = []
    for g in timeline.groups:
        cuts.append(
            WordCut(
                group_id=g.group_id,
                start=g.start,
                end=g.end,
                text=g.text,
                words=g.words,
                visual_asset=args.default_asset or "",
                motion_preset_id=args.motion_preset,
                transition_effect=args.transition,
            )
        )

    captions = [
        {"word": w.text, "start": w.start, "end": w.end}
        for w in timeline.words
        if w.token_type != TokenType.PUNCT
    ]

    plan = WordCutPlan(
        video_id=args.video_id or "cli_word_plan",
        fps=args.fps,
        audio_path=args.audio or "",
        duration=timeline.audio_duration or float(args.duration or 0.0),
        cuts=cuts,
        captions=captions,
        warnings=timeline.warnings,
    )

    out_file = Path(args.out)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Plan written with {len(cuts)} cuts to {out_file}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"✗ Plan file not found: {plan_path}", file=sys.stderr)
        return 1

    data = json.loads(plan_path.read_text(encoding="utf-8"))
    cuts = []
    for c in data.get("cuts", []):
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

    audio = args.audio or data.get("audio_path", "")
    plan = WordCutPlan(
        video_id=data.get("video_id", "cli_render"),
        fps=data.get("fps", 30),
        audio_path=audio,
        duration=data.get("duration", 0.0),
        cuts=cuts,
        captions=data.get("captions", []),
        warnings=data.get("warnings", []),
    )

    res = render_word_cuts(
        plan=plan,
        out_path=args.out,
        captions_ass_path=args.captions,
        width=args.width,
        height=args.height,
    )
    print(f"✓ Video rendered successfully: {res}")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"✗ Plan file not found: {plan_path}", file=sys.stderr)
        return 1

    data = json.loads(plan_path.read_text(encoding="utf-8"))
    cuts = []
    for c in data.get("cuts", []):
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
        video_id=data.get("video_id", "cli_qa"),
        fps=data.get("fps", 30),
        audio_path=data.get("audio_path", ""),
        duration=data.get("duration", 0.0),
        cuts=cuts,
        captions=data.get("captions", []),
    )

    qa_res = validate_word_cuts(
        plan=plan,
        video_path=args.video,
        auto_repair=args.auto_repair,
        is_shorts=args.shorts,
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(qa_res.to_dict(), indent=2), encoding="utf-8")
    status_icon = "✓ PASSED" if qa_res.passed else "✗ FAILED"
    print(f"{status_icon} — QA report written to {report_path}")
    return 0 if qa_res.passed else 2


def main() -> int:
    ap = argparse.ArgumentParser(prog="word_cut_cli", description="CLI for Word-Level Cuts")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # plan
    p_plan = sub.add_parser("plan", help="Build word cut plan")
    p_plan.add_argument("--script", required=True, help="Script text or file path")
    p_plan.add_argument("--timings", help="JSON file containing raw word timings")
    p_plan.add_argument("--audio", help="Master audio track path")
    p_plan.add_argument("--duration", type=float, default=0.0, help="Expected duration in seconds")
    p_plan.add_argument("--fps", type=int, default=30)
    p_plan.add_argument("--max-words", type=int, default=3)
    p_plan.add_argument("--min-group-ms", type=float, default=66.0)
    p_plan.add_argument("--max-group-sec", type=float, default=1.2)
    p_plan.add_argument("--glue-policy", default="auto")
    p_plan.add_argument("--default-asset", default="")
    p_plan.add_argument("--motion-preset", default="ken_burns_zoom_in")
    p_plan.add_argument("--transition", default="none")
    p_plan.add_argument("--video-id", default="short_word_plan")
    p_plan.add_argument("--out", default="word_plan.json")

    # render
    p_render = sub.add_parser("render", help="Render video from word cut plan")
    p_render.add_argument("--plan", required=True, help="Path to word_plan.json")
    p_render.add_argument("--audio", help="Master audio path override")
    p_render.add_argument("--captions", help="ASS captions file override")
    p_render.add_argument("--width", type=int, default=1080)
    p_render.add_argument("--height", type=int, default=1920)
    p_render.add_argument("--out", default="final_word_short.mp4")

    # qa
    p_qa = sub.add_parser("qa", help="Validate word cuts plan and video")
    p_qa.add_argument("--plan", required=True, help="Path to word_plan.json")
    p_qa.add_argument("--video", help="Path to rendered MP4 video")
    p_qa.add_argument("--auto-repair", action="store_true", default=True)
    p_qa.add_argument("--no-auto-repair", dest="auto_repair", action="store_false")
    p_qa.add_argument("--shorts", action="store_true", default=True)
    p_qa.add_argument("--report", default="word_qa_report.json")

    args = ap.parse_args()
    if args.cmd == "plan":
        return cmd_plan(args)
    if args.cmd == "render":
        return cmd_render(args)
    if args.cmd == "qa":
        return cmd_qa(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
