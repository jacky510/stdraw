# -*- coding: utf-8 -*-
"""Candidate sources (candidate-pool pipeline): templates demoted to
generators + the layered incumbent as the fallback candidate.

Plan v1.3.1 section 1.1/2/9 — the six placement templates (plus the radial
variant) stop being gatekeepers and become candidate sources. Sources carry
ZERO scoring power (section 8: "候选生成器携带专属评分权" is on the stop-
investing list):

  - a source emits EVERY construction it completes (the placement modules'
    own infeasibility exceptions are construction failures, recorded as such,
    not quality filters);
  - sources never import metrics / certificate / gate modules — enforced by
    a static import lint test (tests/test_candidate_pool.py);
  - no internal ranking, no internal top-k by any metric.

Sources:

  symmetric / bowtie-vertex / spine-wing / comb-bilateral / column-chain /
  ring-cycle / radial — wrap the existing detect_* + place_* construction
  core of each template module (the SAME construction the auto-v2 mode chain
  uses), WITHOUT the trial gates. Detection returning None is a topological
  non-trigger (recorded, not a failure).

  layered-v082 — the v0.8.2 incumbent (auto recipe full path) materialized
  as a candidate. This is the "layered 兜底候选" of the M1-A minimal loop AND
  the v0.8.2 fallback of plan section 7: the pipeline's quality floor is by
  construction the incumbent path (final delivery compares the best template
  candidate against this candidate with a deterministic metric tuple and
  keeps the one that is not worse).

Determinism: every source iterates in sorted order and records no
timestamps/absolute paths. generation_cost is a documented deterministic
construction-effort proxy (never wall-clock).
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .candidate_contract import LayoutCandidate
from .candidate_planar import (PlanarProbeUnavailable, core_is_planar,
                               planarized_candidates)

# Structural-mode node cap for the candidate pool: the engine's declared
# capability ceiling (n<=20). Individual detectors keep their own
# preregistered caps (e.g. ring MAX_RING_N=12, column n<=12) — a detector
# returning None is a topological non-trigger, recorded honestly. The
# candidate pool does NOT reproduce the mode chain's 12-node gatekeeper cap:
# templates are demoted to sources, detection feasibility decides, never a
# scheduling shortcut. (Topology rule, never a quality signal.)
TEMPLATE_NODE_CAP = 20


class SourceUnavailable(Exception):
    """Topological non-trigger (detector did not fire). Not a failure."""


class SourceConstructionError(Exception):
    """Construction failure (placement raised / produced no coordinates)."""


@dataclass
class SourceContext:
    """Everything a source may read. No metric values, no candidate-quality
    data — scheduling and generation stay quality-blind by construction."""
    graph: object
    cfg: object                 # AutoConfig
    widths: dict                # node -> card width px
    card_h: int
    edges: tuple                # ((a, b), ...) sorted
    adj: dict                   # undirected adjacency
    dense_hub: Optional[str]    # dense-mode hub (same detection as auto-v2)
    analysis: object            # GraphStructureAnalysis (topology only)
    linestyle: str = "straight" # requested line style (incumbent source)
    ops: dict = field(default_factory=dict)   # shared op counters/stash


def _candidate(source, seq, pos, y, nodes, metadata, cost):
    missing = [v for v in nodes if v not in pos]
    if missing:
        raise SourceConstructionError(
            f"placement did not produce coordinates for {sorted(missing)}")
    positions = {v: (int(pos[v]), int(y[v])) for v in sorted(nodes)}
    return LayoutCandidate(
        candidate_id=f"{source}:{seq:03d}", source=source,
        node_positions=positions,
        metadata={"internal_filter": "none", **metadata},
        generation_cost=cost)


# ---- template construction wrappers (no trial gates) ----

def _run_symmetric(ctx):
    from . import symlayout
    why = {}
    plan = symlayout.detect_bowtie(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta, _constructed = symlayout.place_bowtie(
        plan, ctx.widths, ctx.card_h, ctx.cfg, ctx.edges)
    return pos, y, {"engine": "sym-construct", "detector_reason": why.get("reason")}


def _run_bowtie_vertex(ctx):
    from . import bowtielayout
    why = {}
    plan = bowtielayout.detect_bowtie_vertex(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta, _constructed = bowtielayout.place_bowtie_vertex(
        plan, ctx.widths, ctx.card_h, ctx.cfg, ctx.edges)
    return pos, y, {"engine": "bowtie-construct", "detector_reason": why.get("reason")}


def _run_spine_wing(ctx):
    from . import spinewinglayout
    why = {}
    plan = spinewinglayout.detect_spine_wing(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta, _constructed = spinewinglayout.place_spine_wing(
        plan, ctx.widths, ctx.card_h, ctx.cfg, ctx.edges)
    return pos, y, {"engine": "spine-construct", "detector_reason": why.get("reason")}


def _run_comb(ctx):
    from . import comblayout
    why = {}
    plan = comblayout.detect_comb(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta, _constructed = comblayout.place_comb(
        plan, ctx.widths, ctx.card_h, ctx.cfg)
    return pos, y, {"engine": "comb-construct", "detector_reason": why.get("reason")}


def _run_column(ctx):
    from . import columnlayout
    why = {}
    plan = columnlayout.detect_column(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta, _constructed = columnlayout.place_column(
        plan, ctx.widths, ctx.card_h, ctx.cfg, ctx.adj, ctx.edges)
    return pos, y, {"engine": "column-construct", "detector_reason": why.get("reason")}


def _run_ring(ctx):
    from . import ringlayout
    why = {}
    plan = ringlayout.detect_ring(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta = ringlayout.place_ring(
        plan, ctx.widths, ctx.card_h, ctx.cfg, ctx.adj, ctx.edges)
    return pos, y, {"engine": "ring-construct",
                    "detector_reason": why.get("reason"),
                    "trigger": plan.get("trigger")}


def _run_radial(ctx):
    from . import radellayout
    why = {}
    plan = radellayout.detect_radial(ctx.graph, why=why)
    if plan is None:
        raise SourceUnavailable(why.get("reason") or "detector did not fire")
    pos, y, meta = radellayout.place_radial(
        plan, ctx.widths, ctx.card_h, ctx.cfg, ctx.adj, ctx.edges,
        dense_hub=ctx.dense_hub)
    return pos, y, {"engine": "radial-construct", "detector_reason": why.get("reason")}


# ---- layered incumbent: the v0.8.2 auto path materialized as a candidate ----

def _run_layered_incumbent(ctx):
    """Run the full auto recipe (v0.8.2 incumbent, mode chain + routing +
    delivery) and read back its delivered coordinates as a candidate.

    This is the honest layered fallback candidate: no re-implementation of
    the layered construction (which would drift), the incumbent pipeline
    itself is the generator. Its delivered coordinates are floor-guaranteed:
    the incumbent path is exactly what v0.8.2 ships.
    """
    from .layout_auto import layout as _auto_layout
    v4 = _auto_layout(ctx.graph, ctx.cfg, ctx.linestyle)
    ctx.ops["incumbent_v4"] = v4          # pipeline reuses the delivery
    planarization = (v4.get("meta") or {}).get("planarization") or {}
    nodes = sorted(ctx.graph.node_ids())
    pos = {v: v4["nodes"][v]["x"] for v in nodes}
    y = {v: v4["nodes"][v]["y"] for v in nodes}
    meta = {
        "engine": "incumbent-auto-v2",
        "position_engine": (v4.get("meta") or {}).get("position_engine"),
        "planarization_mode": planarization.get("mode"),
    }
    if planarization.get("mode") == "L1":
        meta["planarized_l1"] = True
    # cost proxy: deterministic construction-effort units = nodes + edges +
    # delivered edges (full pipeline ran once); never wall-clock.
    cost = len(nodes) + len(ctx.edges) + len(v4.get("edges") or ())
    return pos, y, meta, cost


TEMPLATE_SOURCES = [
    ("symmetric", _run_symmetric),
    ("bowtie-vertex", _run_bowtie_vertex),
    ("spine-wing", _run_spine_wing),
    ("comb-bilateral", _run_comb),
    ("column-chain", _run_column),
    ("ring-cycle", _run_ring),
    ("radial", _run_radial),
]

# M1-B: the planarization source joins the pool (plan section 7 M1-B
# "planarization candidate"). It is NOT a template: it runs its own
# construction core (candidate_planar.run_planarized) and may emit several
# variant candidates. Order: after the templates, before the layered
# incumbent (preregistered).
EXTRA_SOURCES = ["planarized"]

# Preregistered source order: templates first (plan section 7 priority order
# mirrored), then the planarization source, the layered incumbent last as
# the budget-reserved fallback.
SOURCE_ORDER = ([name for name, _ in TEMPLATE_SOURCES] + EXTRA_SOURCES
                + ["layered-v082"])


def template_enabled(source: str, ctx: SourceContext) -> bool:
    """Preregistered scheduling predicates (topology features only — the
    same structural-mode node cap as the auto-v2 mode chain; never candidate
    quality). ring-cycle is additionally gated on the loop model: a
    failed/degraded loop analysis honestly disarms the loop-reading source
    (failure path of plan section 7 M1 acceptance: loop-detection failure
    has a defined destination). planarized fires ONLY on a non-planar core
    (its deletion enumeration is meaningless otherwise) under the same
    node cap; a failed loop model cannot name the protected primary loop,
    so the source stays armed but the protected set is empty (recorded in
    its metadata)."""
    if source == "layered-v082":
        return True
    if ctx.analysis.n_nodes > TEMPLATE_NODE_CAP:
        return False
    if source == "ring-cycle":
        if ctx.analysis.loop_model.status not in ("ok", "no-cycles"):
            return False
        return ctx.analysis.loop_count >= 1
    if source == "planarized":
        return not core_is_planar(ctx.edges)
    return True


def generate_from_source(source: str, ctx: SourceContext,
                         seq: int = 0) -> List[LayoutCandidate]:
    """Run one source; return its candidates (one for templates, several
    for the planarization source's dual variants). Raises
    SourceUnavailable (topological non-trigger) or SourceConstructionError
    (construction failure) — the orchestrator records both and continues."""
    nodes = sorted(ctx.graph.node_ids())
    if source == "layered-v082":
        pos, y, meta, cost = _run_layered_incumbent(ctx)
        return [_candidate(source, seq, pos, y, nodes, meta, cost)]
    if source == "planarized":
        try:
            return planarized_candidates(ctx, seq=seq)
        except PlanarProbeUnavailable as e:
            raise SourceUnavailable(str(e)) from e
        except Exception as e:
            raise SourceConstructionError(
                f"{type(e).__name__}: {e}") from e
    fn = dict(TEMPLATE_SOURCES)[source]
    try:
        pos, y, meta = fn(ctx)
    except SourceUnavailable:
        raise
    except Exception as e:
        raise SourceConstructionError(f"{type(e).__name__}: {e}") from e
    # deterministic cost proxy: construction units = one per placed node
    cost = len(nodes)
    return [_candidate(source, seq, pos, y, nodes, meta, cost)]
