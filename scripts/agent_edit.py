"""Agentic editing loop for word-level cuts using deterministic repository tools.

Execution loop:
  Plan -> Render -> QA -> Analyze -> Fix -> Re-render (Max 3 iterations)

Deterministic fixes only (no hallucinations, no prompt-only guesses).
Produces edit_report.json documenting before/after metrics and applied repairs.
"""

from __future__ import annotations

import argparse
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
from video.word_timeline import TokenType, WordTimelineBuilder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent_edit")


class AgenticEditor:
    def __init__(self, fps: int = 30, max_iterations: int = 3, is_shorts: bool = True) -> None:
        self.fps = fps
        self.max_iterations = max_iterations
        self.is_shorts = is_shorts

    def run_edit_loop(
        self,
        script: str,
        audio_path: str,
        visual_assets: Optional[List[str]] = None,
        out_dir: str = "output/agent_edit",
        video_id: str = "agent_short",
    ) -> Dict[str, Any]:
        work_dir = Path(out_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        final_mp4 = str(work_dir / f"{video_id}.mp4")

        logger.info("=== Starting Agentic Editing Loop for %s ===", video_id)
        audio_dur = probe_duration(audio_path) if audio_path and Path(audio_path).exists() else 30.0

        # Step 1: Initial Planning
        builder = WordTimelineBuilder(fps=self.fps)

        class AudioInfo:
            provider = "agent_edit"

        a_info = AudioInfo()
        setattr(a_info, "audio_path", audio_path)
        setattr(a_info, "durations", [audio_dur])

        timeline = builder.build(script, a_info, config={"fps": self.fps})

        assets = visual_assets or []
        cuts: List[WordCut] = []
        for idx, g in enumerate(timeline.groups):
            asset = assets[idx % len(assets)] if assets else ""
            cuts.append(
                WordCut(
                    group_id=g.group_id,
                    start=g.start,
                    end=g.end,
                    text=g.text,
                    words=g.words,
                    visual_asset=asset,
                    motion_preset_id="ken_burns_zoom_in",
                    transition_effect="flash" if idx == 0 else "cut",
                )
            )

        plan = WordCutPlan(
            video_id=video_id,
            fps=self.fps,
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

        initial_metrics: Dict[str, Any] = {}
        final_metrics: Dict[str, Any] = {}
        fixes_log: List[str] = []
        passed = False

        for iteration in range(1, self.max_iterations + 1):
            logger.info("--- Iteration %d/%d: Rendering & QA ---", iteration, self.max_iterations)

            # Render
            render_word_cuts(plan, final_mp4)

            # QA
            qa_res = validate_word_cuts(plan, final_mp4, auto_repair=True, is_shorts=self.is_shorts)
            current_metrics = qa_res.to_dict()

            if iteration == 1:
                initial_metrics = current_metrics

            logger.info(
                "Iteration %d QA verdict: %s (Errors: %d, Warnings: %d, Drift: %.1fms)",
                iteration,
                "PASSED" if qa_res.passed else "FAILED",
                len(qa_res.errors),
                len(qa_res.warnings),
                qa_res.max_drift_ms,
            )

            if qa_res.passed:
                passed = True
                final_metrics = current_metrics
                fixes_log.append(f"Iteration {iteration}: All broadcast quality gates verified.")
                break

            # Analyze failures and apply deterministic fixes
            applied_repairs = False
            for err in qa_res.errors:
                logger.warning("Analyzing defect: %s", err)
                if "gap" in err.lower() or "overlap" in err.lower() or "inverted" in err.lower():
                    # Re-snap cuts to contiguous boundary
                    for i in range(1, len(plan.cuts)):
                        plan.cuts[i].start = plan.cuts[i - 1].end
                    applied_repairs = True
                    fixes_log.append(f"Iteration {iteration}: Re-snapped all cut boundaries contiguously.")

                elif "shorter than 2 frames" in err.lower():
                    # Merge tiny cuts
                    valid_cuts = []
                    for c in plan.cuts:
                        if (c.end - c.start) >= (2.0 / self.fps):
                            valid_cuts.append(c)
                        elif valid_cuts:
                            valid_cuts[-1].end = c.end
                            valid_cuts[-1].text += f" {c.text}"
                    plan.cuts = valid_cuts
                    applied_repairs = True
                    fixes_log.append(f"Iteration {iteration}: Merged sub-frame cuts into adjacent segments.")

                elif "below Shorts minimum" in err.lower() or "exceeds Shorts hard limit" in err.lower():
                    # Adjust final cut boundary to clamp to target
                    target_dur = max(15.5, min(59.0, audio_dur))
                    plan.cuts[-1].end = round(target_dur, 3)
                    applied_repairs = True
                    fixes_log.append(f"Iteration {iteration}: Clamped timeline duration to {target_dur}s.")

            final_metrics = current_metrics
            if not applied_repairs:
                logger.info("No further deterministic repair rules available.")
                break

        report = {
            "video_id": video_id,
            "status": "APPROVED" if passed else "FLAGGED_FOR_REVIEW",
            "iterations_run": iteration,
            "output_video": final_mp4,
            "initial_metrics": initial_metrics,
            "final_metrics": final_metrics,
            "fixes_applied": fixes_log,
        }

        report_file = work_dir / "edit_report.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info("Edit report generated at %s", report_file)
        return report


def main() -> int:
    ap = argparse.ArgumentParser(prog="agent_edit", description="Agentic Word-Cut Editing Loop")
    ap.add_argument("--script", required=True, help="Script text or file")
    ap.add_argument("--audio", required=True, help="Master voiceover audio file")
    ap.add_argument("--assets", nargs="*", help="Image/video asset paths")
    ap.add_argument("--out-dir", default="output/agent_edit")
    ap.add_argument("--video-id", default="agentic_short")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--max-iter", type=int, default=3)

    args = ap.parse_args()
    script_content = Path(args.script).read_text(encoding="utf-8") if Path(args.script).exists() else args.script

    editor = AgenticEditor(fps=args.fps, max_iterations=args.max_iter)
    report = editor.run_edit_loop(
        script=script_content,
        audio_path=args.audio,
        visual_assets=args.assets,
        out_dir=args.out_dir,
        video_id=args.video_id,
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "APPROVED" else 1


if __name__ == "__main__":
    sys.exit(main())
