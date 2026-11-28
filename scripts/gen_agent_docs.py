"""Regenerate the agent wiring docs from the registry (single source of truth)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent_registry import REGISTRY  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "AGENT_WIRING_MATRIX.md"


def main() -> int:
    text = OUT.read_text(encoding="utf-8")
    head, _, rest = text.partition("| # | stage |")
    tail = rest.split("```mermaid", 1)[1].split("```", 1)[1] if "```mermaid" in rest else ""
    body = (
        f"{head}| # | stage |" + REGISTRY.render_table().split("| # | stage |", 1)[1]
        + "\n\n## Dependency graph\n\n```mermaid\n"
        + REGISTRY.render_mermaid()
        + "\n```"
        + tail
    )
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT} ({len(REGISTRY)} stages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
