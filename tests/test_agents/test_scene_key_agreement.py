"""The scene key must mean the same thing in sourcing and in the producer.

A real run shipped a photo of China under a line about a Punjab ration card. The script had
numbered its scenes 1..9, but the sourcing agent skipped the 'today' scenes before writing files,
so file N belonged to the Nth SURVIVING scene while the producer read file N as the Nth scene of
the script. Every picture was one story off, and no score noticed because both sides were
internally consistent.
"""

from __future__ import annotations

import re
from pathlib import Path


def _scene_id_line(path: str, anchor: str) -> str:
    src = Path(path).read_text(encoding="utf-8")
    at = src.index(anchor)
    return src[at : at + 2400]  # the id is set after the parts are enriched


def test_both_sides_derive_the_id_from_script_position():
    """Both must use `enumerate(scenes)` — never `scene_number`, never a filtered index."""
    sourcing = _scene_id_line("agents/news_visual_sourcing/agent.py", "for idx, sc in enumerate(scenes):")
    producer = _scene_id_line("agents/video_producer/agent.py", "for i, s in enumerate(scenes):")
    assert 'f"scene_{idx:03d}"' in sourcing, "sourcing must key on script position"
    assert 'f"scene_{i:03d}"' in producer, "producer must key on script position"
    for block, name in ((sourcing, "sourcing"), (producer, "producer")):
        assert "scene_number" not in block, (
            f"{name} derives the scene id from scene_number; the script's numbering has gaps, "
            "so that silently attaches pictures to the wrong story"
        )
        assert not re.search(r"enumerate\(\s*(news_scenes|filtered)", block), (
            f"{name} enumerates a FILTERED list, so its indices cannot line up with the other side"
        )
