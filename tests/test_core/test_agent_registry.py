"""Agent registry / wiring audit tests.

The tests that matter here are the ones that would have caught a disconnected agent:
a stage that never runs, a stage that runs but publishes nothing, and a stage whose declared
output key silently disappears.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.agent_registry import REGISTRY, AgentRegistry, AgentSpec, build_default_registry

ORCHESTRATOR = Path(__file__).resolve().parents[2] / "core" / "orchestrator.py"


def test_registry_is_not_empty_and_dependency_ordered():
    assert len(REGISTRY) >= 15
    order = REGISTRY.topological_order()
    assert len(order) == len(REGISTRY)


def test_every_orchestrator_stage_is_declared():
    """The registry is only useful if it describes the pipeline that actually runs."""
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    code_stages = set(re.findall(r'_stage\(\s*\n?\s*vid,?\s*"([a-z_]+)"', source))
    declared = set(REGISTRY.stages())
    assert code_stages, "could not find any _stage() calls — did the orchestrator change shape?"
    assert code_stages <= declared, (
        f"stages missing from the registry: {sorted(code_stages - declared)}"
    )


def test_missing_critical_stage_blocks():
    executed = [s for s in REGISTRY.stages() if s != "video_production"]
    report = REGISTRY.validate(executed=executed)
    assert not report.ok
    assert "video_production" in report.missing
    assert any("video_production" in p for p in report.blocking_problems())


def test_missing_optional_stage_does_not_block():
    executed = [s for s in REGISTRY.stages() if s not in ("motion_graphics", "vfx_direction")]
    report = REGISTRY.validate(executed=executed)
    assert report.ok
    assert set(report.skipped_optional) == {"motion_graphics", "vfx_direction"}


def test_empty_output_is_a_failure():
    executed = REGISTRY.stages()
    report = REGISTRY.validate(executed=executed, produced={"video_production": {}})
    assert not report.ok
    assert "video_production" in report.empty_output


def test_broken_output_contract_is_reported():
    report = REGISTRY.validate(
        executed=REGISTRY.stages(),
        produced={"script_generation": {"scenes": []}},  # promised "script"
    )
    assert not report.ok
    assert any("promised 'script'" in p for p in report.missing_contract)


def test_unknown_stage_is_reported():
    report = REGISTRY.validate(executed=[*REGISTRY.stages(), "made_up_stage"])
    assert not report.ok
    assert report.unknown_stages == ["made_up_stage"]


def test_orphan_outputs_are_detected():
    """A value that nobody consumes is a wiring bug — it looks like output but is dead weight."""
    registry = AgentRegistry(
        [
            AgentSpec(name="A", stage="a", provides=("value", "unused_value")),
            AgentSpec(name="B", stage="b", requires=("a",)),
        ]
    )
    report = registry.validate(executed=["a", "b"], consumed={"a": {"value"}})
    assert report.orphan_outputs == ["a: unused_value"]


def test_duplicate_stage_rejected():
    with pytest.raises(ValueError):
        AgentRegistry([AgentSpec(name="A", stage="x"), AgentSpec(name="B", stage="x")])


def test_declaration_order_can_be_resolved_when_it_is_sound():
    """Requiring a stage declared earlier is normal: the graph resolves, the order is returned."""
    registry = AgentRegistry(
        [AgentSpec(name="B", stage="b"), AgentSpec(name="A", stage="a", requires=("b",))]
    )
    assert registry.topological_order() == ["b", "a"]


def test_forward_reference_is_rejected():
    """Requiring a stage that is declared LATER is drift: the file order lies about the data flow."""
    registry = AgentRegistry(
        [AgentSpec(name="A", stage="a", requires=("b",)), AgentSpec(name="B", stage="b")]
    )
    # "b" is declared second, so the declaration order cannot satisfy it
    with pytest.raises(ValueError, match="forward reference"):
        registry.topological_order()


def test_consumers_of_resolves_by_dependency():
    assert "video_production" in REGISTRY.consumers_of("master_editing_director")


def test_rendered_docs_are_generated_from_the_registry(tmp_path):
    """Docs must be generated, never hand-maintained, or they drift from the code."""
    mermaid = REGISTRY.render_mermaid()
    assert mermaid.startswith("flowchart TD")
    assert "n_video_production" in mermaid
    table = REGISTRY.render_table()
    assert "| stage |" in table
    assert REGISTRY.render_table().count("\n") == len(build_default_registry()) + 1
