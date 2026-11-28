"""Who owns which picture: story → scene → asset, with stable IDs (never array indexes).

The renderer used to place pictures by `assets[(beat_index, part_index)]`, so a picture could
drift one scene when a section card, the hook or a dropped beat changed the index. This module
builds the ownership map once, from IDs, and is what the QA/report stage reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisualOwnership:
    """One row per rendered beat: which story it belongs to and which asset it shows."""

    scene_id: str  # story_hook | story_001 | story_002 | section_national | outro
    story_id: str  # same as scene_id for stories, "" for cards/outro
    kind: str  # hook | item | section | outro
    section: str = ""  # today | national | international
    spoken: str = ""  # the narration this picture plays under
    asset_path: str = ""
    asset_source: str = ""
    asset_labels: str = ""
    match: float = -1.0  # keyword_match of the asset's own words vs `spoken`
    parts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def scene_id_for(beat: dict[str, Any], story_index: int) -> str:
    """Canonical IDs. The hook is story_hook, never story_000 (that shift was a real bug)."""
    kind = beat.get("kind")
    if kind == "hook":
        return "story_hook"
    if kind == "outro":
        return "outro"
    if kind == "section":
        return f"section_{beat.get('section', 'national')}"
    return f"story_{story_index:03d}"


def build(beats: list[dict[str, Any]], assets: dict[Any, Any]) -> list[VisualOwnership]:
    """Turn the producer's beats + asset map into the ownership table used for QA and reports.

    `assets` is keyed by (beat_index, part_index) because that is how the collector returns
    results; the *identity* published here is story-based, so downstream stages never guess.
    """
    rows: list[VisualOwnership] = []
    story_n = 0
    for i, beat in enumerate(beats):
        if beat.get("kind") == "item":
            story_n += 1
        sid = scene_id_for(beat, story_n)
        parts = []
        for k, _part in enumerate(beat.get("parts") or []):
            a = assets.get((i, k))
            parts.append(
                {
                    "part": k,
                    "say": (_part or {}).get("say", ""),
                    "visual": (_part or {}).get("visual", ""),
                    "asset": getattr(a, "path", "") if a else "",
                    "source": getattr(a, "source", "") if a else "",
                    "match": round(float(getattr(a, "match", -1) or -1), 3) if a else -1.0,
                }
            )
        rows.append(
            VisualOwnership(
                scene_id=sid,
                story_id=sid if beat.get("kind") == "item" else "",
                kind=str(beat.get("kind") or ""),
                section=str(beat.get("section") or ""),
                spoken=str(beat.get("text") or ""),
                asset_path=getattr(assets.get((i, 0)), "path", "") if assets.get((i, 0)) else "",
                asset_source=getattr(assets.get((i, 0)), "source", "")
                if assets.get((i, 0))
                else "",
                asset_labels=getattr(assets.get((i, 0)), "labels", "")
                if assets.get((i, 0))
                else "",
                match=round(float(getattr(assets.get((i, 0)), "match", -1) or -1), 3)
                if assets.get((i, 0))
                else -1.0,
                parts=parts,
            )
        )
    return rows


def validate(rows: list[VisualOwnership]) -> list[str]:
    """Problems that must stop a publish: duplicate scene IDs, a story with no picture,
    the hook sharing a story's picture, or a card claiming a story identity."""
    problems: list[str] = []
    ids = [r.scene_id for r in rows]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        problems.append(f"duplicate scene IDs: {sorted(dupes)}")
    for r in rows:
        # The date/panchang/rashifal opening is DRAWN as a designed card on purpose — that is a
        # deliberate treatment, not a missing picture. Every other story must own a real asset.
        drawn_card = r.section == "today" or r.kind in ("section", "outro")
        if r.kind == "item" and not r.asset_path and not drawn_card:
            problems.append(f"{r.scene_id} has no picture")
        if (
            r.kind == "hook"
            and r.asset_path
            and any(s.asset_path == r.asset_path for s in rows if s.kind == "item")
        ):
            problems.append(f"hook reuses a story picture: {r.asset_path[-40:]}")
        if r.kind in ("section", "outro") and r.story_id:
            problems.append(f"{r.scene_id} must not claim a story identity")
    return problems
