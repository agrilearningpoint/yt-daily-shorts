"""Agent registry — one declaration of every agent, its stage, its inputs and its outputs.

Why this exists
---------------
The orchestrator used to be a 300-line ``await self._stage(...)`` sequence: 31 agents were
instantiated by hand, and nothing checked that the agent actually ran, that the stage before it
produced what it needs, or that its output reached the consumer. A silently disconnected agent
(produced a value nobody read) looked exactly like a working one.

This module turns the pipeline into data:

* every agent declares ``name``, ``stage``, ``requires`` (upstream stages), ``provides`` (keys it
  publishes) and ``critical`` (can a run continue without it?);
* ``validate(executed, produced)`` compares the declaration against what actually happened in a
  real run and returns structured problems;
* ``dependency_graph()`` exposes the DAG so the docs and the wiring test read the same truth;
* ``render_mermaid()`` writes the graph into ``docs/`` so it cannot drift.

It does not import the agents (that would create cycles); it declares them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

__all__ = [
    "REGISTRY",
    "AgentRegistry",
    "AgentSpec",
    "build_default_registry",
]


@dataclass(frozen=True)
class AgentSpec:
    """What one stage is responsible for."""

    name: str
    stage: str
    requires: Sequence[str] = ()
    provides: Sequence[str] = ()
    critical: bool = True
    # keys that must be present in the produced payload; a missing one is a wiring break
    must_provide: Sequence[str] = ()
    description: str = ""

    def dependency_edges(self) -> Iterable[tuple[str, str]]:
        for upstream in self.requires:
            yield (upstream, self.stage)


@dataclass
class WiringReport:
    """Result of comparing the declaration with a real run."""

    missing: list[str] = field(default_factory=list)  # critical stage never ran
    skipped_optional: list[str] = field(default_factory=list)
    empty_output: list[str] = field(default_factory=list)  # ran, but published nothing
    orphan_outputs: list[str] = field(default_factory=list)  # produced, nobody consumed
    missing_contract: list[str] = field(default_factory=list)  # promised key not in payload
    unknown_stages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missing or self.empty_output or self.missing_contract or self.unknown_stages
        )

    def blocking_problems(self) -> list[str]:
        out = [f"stage '{s}' never ran" for s in self.missing]
        out += [f"stage '{s}' produced no output" for s in self.empty_output]
        out += self.missing_contract
        out += [f"unknown stage '{s}' executed" for s in self.unknown_stages]
        return out

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "missing": self.missing,
            "skipped_optional": self.skipped_optional,
            "empty_output": self.empty_output,
            "orphan_outputs": self.orphan_outputs,
            "missing_contract": self.missing_contract,
            "unknown_stages": self.unknown_stages,
            "blocking": self.blocking_problems(),
        }


class AgentRegistry:
    """An ordered collection of :class:`AgentSpec` with validation helpers."""

    def __init__(self, specs: Sequence[AgentSpec] | None = None) -> None:
        self._specs: dict[str, AgentSpec] = {}
        self._order: list[str] = []
        for spec in specs or ():
            self.register(spec)

    # -- construction -------------------------------------------------
    def register(self, spec: AgentSpec) -> AgentSpec:
        if spec.stage in self._specs:
            raise ValueError(f"duplicate stage '{spec.stage}'")
        self._specs[spec.stage] = spec
        self._order.append(spec.stage)
        return spec

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self):
        return (self._specs[s] for s in self._order)

    def get(self, stage: str) -> AgentSpec | None:
        return self._specs.get(stage)

    def stages(self) -> list[str]:
        return list(self._order)

    def critical_stages(self) -> list[str]:
        return [s for s in self._order if self._specs[s].critical]

    # -- analysis -----------------------------------------------------
    def dependency_graph(self) -> dict[str, list[str]]:
        """stage -> list of upstream stages it depends on."""
        return {s: list(self._specs[s].requires) for s in self._order}

    def topological_order(self) -> list[str]:
        """Declaration order, but only if it satisfies every dependency.

        Two different mistakes are reported differently, because they mean different things:

        * **cycle** — a depends on b and b depends on a: the pipeline can never start.
        * **forward reference** — a stage depends on one declared *after* it: the file order lies
          about the data flow. The graph could still be resolved, but the orchestrator would run
          the consumer before the producer, which is exactly the disconnect this registry exists
          to catch.

        Raises:
            ValueError: with the list of offending stages.
        """
        # a cycle is the more serious diagnosis: check it first, or every cycle would be
        # reported as "x declared later" and the real problem would never be named
        order = self._topo_sort()
        if order is None:
            raise ValueError(f"dependency cycle among: {sorted(self._cyclic_stages())}")

        declared_before: set[str] = set()
        forward: list[str] = []
        for stage in self._order:
            late = [r for r in self._specs[stage].requires if r not in declared_before]
            if late:
                forward.append(f"'{stage}' requires {late} declared later")
            declared_before.add(stage)
        if forward:
            raise ValueError("forward reference in the registry: " + "; ".join(forward))
        return order

    def _topo_sort(self) -> list[str] | None:
        """Kahn's algorithm; None when a cycle remains."""
        indeg = {s: len(set(self._specs[s].requires)) for s in self._order}
        queue = [s for s in self._order if indeg[s] == 0]
        out: list[str] = []
        while queue:
            stage = queue.pop(0)
            out.append(stage)
            for other in self._order:
                if stage in self._specs[other].requires:
                    indeg[other] -= 1
                    if indeg[other] == 0:
                        queue.append(other)
        return out if len(out) == len(self._order) else None

    def _cyclic_stages(self) -> list[str]:
        """Stages that can never run because they wait on each other."""
        resolved: set[str] = set()
        remaining = list(self._order)
        while True:
            ready = [s for s in remaining if set(self._specs[s].requires) <= resolved]
            if not ready:
                return remaining
            for s in ready:
                resolved.add(s)
                remaining.remove(s)

    def consumers_of(self, stage: str) -> list[str]:
        """Which stages consume the output of ``stage``."""
        provides = set(self._specs[stage].provides) if stage in self._specs else set()
        out = []
        for other in self._order:
            spec = self._specs[other]
            if stage in spec.requires or set(spec.requires) & provides:
                out.append(other)
        return out

    def validate(
        self,
        executed: Sequence[str],
        produced: dict[str, dict[str, object]] | None = None,
        consumed: dict[str, set[str]] | None = None,
        pending: Sequence[str] = (),
    ) -> WiringReport:
        """Compare a real run with the declaration.

        Args:
            executed: stages that actually ran (order irrelevant).
            produced: stage -> payload it emitted. Used for empty/contract checks.
            consumed: stage -> set of keys its consumers actually read. Used for orphan detection.
            pending: stages expected to run LATER in this same run. The audit before publishing
                cannot demand that publishing already happened.
        """
        report = WiringReport()
        ran = set(executed)
        payloads = produced or {}
        waiting = set(pending)

        for spec in self:
            if spec.stage in waiting and spec.stage not in ran:
                continue  # scheduled later in this run; a post-run audit will check it
            if spec.stage not in ran:
                (report.missing if spec.critical else report.skipped_optional).append(spec.stage)
                continue
            payload = payloads.get(spec.stage)
            if payload is not None and not payload:
                report.empty_output.append(spec.stage)
                continue
            if payload is not None:
                for key in spec.must_provide:
                    if key not in payload:
                        report.missing_contract.append(
                            f"stage '{spec.stage}' promised '{key}' but did not publish it"
                        )

        for stage in ran:
            if stage not in self._specs:
                report.unknown_stages.append(stage)

        if consumed is not None:
            for spec in self:
                if spec.stage not in ran or not spec.provides:
                    continue
                readers = consumed.get(spec.stage) or set()
                unused = [k for k in spec.provides if k not in readers]
                if unused:
                    report.orphan_outputs.append(f"{spec.stage}: {', '.join(unused)}")
        return report

    # -- docs ---------------------------------------------------------
    def render_mermaid(self) -> str:
        lines = ["flowchart TD"]
        for spec in self:
            label = spec.stage
            style = "" if spec.critical else ":::optional"
            lines.append(f'    {_node(spec.stage)}["{label}"]{style}')
        for spec in self:
            for upstream in spec.requires:
                if upstream in self._specs:
                    lines.append(f"    {_node(upstream)} --> {_node(spec.stage)}")
        lines.append("    classDef optional stroke-dasharray: 5 5")
        return "\n".join(lines)

    def render_table(self) -> str:
        rows = [
            "| # | stage | agent | critical | requires | provides |",
            "|---|-------|-------|----------|----------|----------|",
        ]
        for i, spec in enumerate(self, 1):
            req = ", ".join(spec.requires) or "—"
            prov = ", ".join(spec.provides) or "—"
            rows.append(
                f"| {i} | `{spec.stage}` | {spec.name} | {'yes' if spec.critical else 'no'} "
                f"| {req} | {prov} |"
            )
        return "\n".join(rows)


def _node(stage: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in stage)


def build_default_registry() -> AgentRegistry:
    """The production pipeline, in execution order.

    ``provides`` lists the keys the orchestrator and the docs rely on. ``requires`` is the real
    data dependency (what the agent reads from the previous stage's payload), not just the
    previous line in the file.
    """
    specs = [
        AgentSpec(
            name="DailyOpeningDirectorAgent",
            stage="daily_opening",
            provides=("opening_brief",),
            critical=False,
            description="Date, panchang, festival, rashifal, trading order for the opening block.",
        ),
        AgentSpec(
            name="ResearchManagerAgent",
            stage="research",
            provides=("items", "daily", "sources"),
            must_provide=("items",),
            description="Fresh (<24h) news items + the day facts the opening block needs.",
        ),
        AgentSpec(
            name="PromptEngineerAgent",
            stage="prompt_engineering",
            requires=("research",),
            provides=("prompt_engineering", "min_words", "max_words", "targets"),
            must_provide=("prompt_engineering",),
            description="Turns research into the scripting prompt with a satisfiable word budget.",
        ),
        AgentSpec(
            name="ScriptManagerAgent",
            stage="script_generation",
            requires=("prompt_engineering", "research"),
            provides=("script",),
            must_provide=("script",),
            description="Writes and mechanically repairs the Hindi script (parts, lengths).",
        ),
        AgentSpec(
            name="HookDirectorAgent",
            stage="hook_director",
            requires=("script_generation",),
            provides=("hook",),
            critical=False,
            description="Picks the first-two-seconds hook.",
        ),
        AgentSpec(
            name="FactVerifierAgent",
            stage="fact_verification",
            requires=("script_generation", "research"),
            provides=("verdict", "script"),
            must_provide=("verdict",),
            description="Claim-level check against article text and the day's own facts.",
        ),
        AgentSpec(
            name="QualityManagerAgent",
            stage="quality_check",
            requires=("fact_verification",),
            provides=("score", "script"),
            must_provide=("score",),
            description="Editorial quality gate (structure, Hindi, story discipline).",
        ),
        AgentSpec(
            name="CreativeDirectorAgent",
            stage="creative_direction",
            requires=("quality_check",),
            provides=("creative_brief",),
            description="Visual/tonal direction for the episode.",
        ),
        AgentSpec(
            name="NewsVisualSourcingAgent",
            stage="news_visual_sourcing",
            requires=("creative_direction",),
            provides=("visual_plan", "assets"),
            must_provide=("visual_plan",),
            description="Finds a real picture for every spoken beat.",
        ),
        AgentSpec(
            name="VFXAgent",
            stage="vfx_direction",
            requires=("news_visual_sourcing",),
            provides=("vfx_plan",),
            critical=False,
            description="Transitions and effects.",
        ),
        AgentSpec(
            name="MotionGraphicsAgent",
            stage="motion_graphics",
            requires=("news_visual_sourcing",),
            provides=("motion_data",),
            critical=False,
            description="Kinetic text and graphics from the preset library.",
        ),
        AgentSpec(
            name="AudioSoundDesignAgent",
            stage="audio_sound_design",
            requires=("motion_graphics",),
            provides=("audio_plan", "music", "sfx"),
            critical=False,
            description="BGM bed and SFX cues for the timeline.",
        ),
        AgentSpec(
            name="MasterEditingDirectorAgent",
            stage="master_editing_director",
            requires=("audio_sound_design", "motion_graphics", "vfx_direction"),
            provides=("timeline",),
            must_provide=("timeline",),
            description="The master timeline: single authority over scene timing.",
        ),
        AgentSpec(
            name="VideoProducerAgent",
            stage="video_production",
            requires=("master_editing_director", "news_visual_sourcing"),
            provides=("video_path", "captions_srt", "duration"),
            must_provide=("video_path",),
            description="Renders the MP4 and the captions.",
        ),
        AgentSpec(
            name="VisualAudioMatchQAAgent",
            stage="visual_audio_match_qa",
            requires=("video_production",),
            provides=("visual_match_score", "qa_report"),
            description="Per-beat check that the picture matches the words (vision-based).",
        ),
        AgentSpec(
            name="SEOManagerAgent",
            stage="seo_optimization",
            requires=("quality_check", "video_production"),
            provides=("title", "description", "tags"),
            must_provide=("title",),
            description="Title, description, tags, chapters.",
        ),
        AgentSpec(
            name="ThumbnailDesignerAgent",
            stage="thumbnail_design",
            requires=("seo_optimization",),
            provides=("thumbnail_path",),
            critical=False,
            description="Thumbnail image.",
        ),
        AgentSpec(
            name="PublisherAgent",
            stage="publishing",
            requires=("seo_optimization", "video_production"),
            provides=("youtube_id", "youtube_url"),
            must_provide=("youtube_id",),
            description="Upload, caption, playlist and scheduling.",
        ),
        AgentSpec(
            name="AnalyticsManagerAgent",
            stage="analytics",
            requires=("video_production",),
            provides=("metrics",),
            critical=False,
            description="Post-publish performance snapshot.",
        ),
        AgentSpec(
            name="SelfLearningAgent",
            stage="self_learning",
            requires=("video_production",),
            provides=("learning_notes",),
            critical=False,
            description="Turns outcomes into prompt/config suggestions (never self-pushes code).",
        ),
    ]
    return AgentRegistry(specs)


REGISTRY = build_default_registry()
