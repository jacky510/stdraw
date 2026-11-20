# -*- coding: utf-8 -*-
"""Graph Structure Analyzer + Loop Structure Model (candidate-pool pipeline).

Plan v1.3.1 section 1.3 / section 2: the three-layer loop model —

  Layer 1: full simple-cycle enumeration, bounded by explicit caps
           (cycle count / cycle length / deterministic operation counter).
           Overflowing a cap degrades HONESTLY (status="degraded"), it never
           silently truncates the model.
  Layer 2: structural importance scoring of every enumerated loop. The score
           is NOT dominated by loop length (a long main loop must not be
           crowded out of the top by many short loops): it combines graph
           edge coverage, node sharing with other loops (hub-ness) and a
           declared-loop bonus; length enters with a small weight only.
           Weights are preregistered module constants (never per-graph).
  Layer 3: loops below the primary tier act as auxiliary aesthetic
           constraints — the model records them and their relation data;
           consumers (Phase 2 stress layer) may read them, the M1 pipeline
           only transports them.

Polarity fidelity: every loop records its R/B kind derived from the parity
of negative-polarity edges (same caliber as loops.py) — the polarity
semantic survives in the structural model even though M1 does not optimize
with it.

Failure paths (orchestrator contract): any unexpected error inside the
analyzer is caught by the caller and reported as status="failed" with an
honest reason; a graph without cycles is status="ok" with zero loops (not a
failure). Loop-gated candidate sources are disabled on failed/degraded
models by a preregistered scheduling rule (never by candidate quality).

All iteration orders are sorted() — byte-determinism rule.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---- Layer 1 caps (preregistered; plan section 1.3 cap-and-degrade) ----
MAX_SIMPLE_CYCLES = 200      # cycle-count cap -> degraded beyond this
MAX_CYCLE_LEN = 10           # length cap (same caliber as loops.py enum)
MAX_ENUM_OPS = 200_000       # deterministic operation counter cap

# ---- Layer 2 importance weights (preregistered; never tuned per graph) ----
W_EDGE_COVERAGE = 1.0        # cycle edges / core-graph edges
W_SHARED_NODE = 0.5          # hub-ness: other loops sharing >=1 node
W_DECLARED_BONUS = 0.25      # node set matches a declared loop exactly
W_LENGTH = 0.1               # small weight: length must not dominate

PRIMARY = "primary"          # top-scored loop (the "main loop" default read)
SUPPORTING = "supporting"    # score >= SUPPORTING_RATIO * primary score
AUXILIARY = "auxiliary"      # the rest — auxiliary aesthetic constraints
SUPPORTING_RATIO = 0.5


@dataclass
class LoopRecord:
    cycle: Tuple[str, ...]        # canonical directed tuple (min-rotation)
    nodes: Tuple[str, ...]        # sorted node set (deterministic reporting)
    length: int
    kind: str                     # "R" / "B" (polarity parity caliber)
    neg_edges: int
    importance: float
    tier: str                     # primary / supporting / auxiliary
    declared_match: Optional[str]
    shared_nodes: int             # loops (other than itself) sharing >=1 node


@dataclass
class LoopStructureModel:
    status: str                   # "ok" | "degraded" | "failed" | "no-cycles"
    reason: Optional[str] = None
    loops: List[LoopRecord] = field(default_factory=list)
    enumerated_total: int = 0     # cycles found before any cap truncation
    primary_loop: Optional[LoopRecord] = None

    def to_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "enumerated_total": self.enumerated_total,
            "loop_count": len(self.loops),
            "primary_loop": (self.primary_loop.nodes if self.primary_loop
                             else None),
            "loops": [
                {"cycle": list(lp.cycle), "length": lp.length,
                 "kind": lp.kind, "neg_edges": lp.neg_edges,
                 "importance": round(lp.importance, 6), "tier": lp.tier,
                 "declared_match": lp.declared_match,
                 "shared_nodes": lp.shared_nodes}
                for lp in sorted(self.loops,
                                 key=lambda r: (-r.importance, r.cycle))
            ],
        }


def analyze_loop_structure(graph) -> LoopStructureModel:
    """Three-layer loop analysis of a stdraw Graph. Never raises: an
    unexpected error is reported as status="failed" (orchestrator contract:
    the pipeline proceeds loop-free with the failure recorded)."""
    try:
        return _analyze(graph)
    except Exception as e:                      # honest failure path
        return LoopStructureModel(status="failed", reason=f"{type(e).__name__}: {e}")


def _analyze(graph) -> LoopStructureModel:
    und: Dict[str, List[str]] = defaultdict(list)
    polarity: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    edge_set = set()
    nodes = sorted(graph.node_ids())
    for e in graph.edges:
        und[e.a].append(e.b)
        und[e.b].append(e.a)
        polarity[(e.a, e.b)].append(e.polarity)
        polarity[(e.b, e.a)].append(e.polarity)
        edge_set.add(frozenset((e.a, e.b)))
    core_edges = len(edge_set)

    # ---- Layer 1: bounded full enumeration of undirected simple cycles ----
    cycles = set()                # canonical directed tuples
    ops = 0
    degraded_reason = None
    enumerated_total = 0

    def canon(path):
        fwd = [tuple(path[i:] + path[:i]) for i in range(len(path))]
        rev = list(reversed(path))
        rev_rot = [tuple(rev[i:] + rev[:i]) for i in range(len(rev))]
        return min(fwd + rev_rot)

    for start in nodes:
        stack_visit = [(start, [start], frozenset())]
        while stack_visit:
            cur, path, seen_e = stack_visit.pop()
            for nxt in sorted(und.get(cur, ())):
                ops += 1
                if ops > MAX_ENUM_OPS:
                    degraded_reason = f"operation cap {MAX_ENUM_OPS} exceeded"
                    stack_visit = None
                    break
                if (cur, nxt) in seen_e:
                    continue
                if nxt == start and len(path) >= 3:
                    cycles.add(canon(path))
                    enumerated_total += 1
                    if len(cycles) > MAX_SIMPLE_CYCLES:
                        degraded_reason = (f"cycle cap {MAX_SIMPLE_CYCLES} "
                                           "exceeded")
                        stack_visit = None
                        break
                    continue
                if nxt in path or len(path) >= MAX_CYCLE_LEN:
                    continue
                stack_visit.append(
                    (nxt, path + [nxt], seen_e | {frozenset((cur, nxt))}))
            if degraded_reason:
                break
        if degraded_reason:
            break

    if not cycles:
        return LoopStructureModel(
            status="no-cycles" if not degraded_reason else "degraded",
            reason=degraded_reason, enumerated_total=0)

    if degraded_reason:
        kept = sorted(cycles)[:MAX_SIMPLE_CYCLES]
    else:
        kept = sorted(cycles)

    # ---- Layer 2: structural importance scoring ----
    declared_sets = [frozenset(lp.nodes) for lp in graph.loops
                     if lp.nodes]
    declared_ids = [lp.id for lp in graph.loops if lp.nodes]

    def cycle_kind(cyc):
        negs = 0
        for i in range(len(cyc)):
            a, b = cyc[i], cyc[(i + 1) % len(cyc)]
            pols = polarity.get((a, b)) or []
            if "-" in pols:
                negs += 1
        return ("B" if negs % 2 else "R"), negs

    records = []
    max_len = max(len(c) for c in kept)
    node_sets = [frozenset(c) for c in kept]
    for idx, cyc in enumerate(kept):
        kind, negs = cycle_kind(cyc)
        cset = node_sets[idx]
        cyc_edge_count = len(cyc)
        coverage = (cyc_edge_count / core_edges) if core_edges else 0.0
        shared = sum(1 for j, s in enumerate(node_sets)
                     if j != idx and s & cset)
        declared_match = None
        for lp_nodes, lid in zip(declared_sets, declared_ids):
            if lp_nodes == cset:
                declared_match = lid
                break
        score = (W_EDGE_COVERAGE * coverage
                 + W_SHARED_NODE * (shared / max(1, len(kept) - 1))
                 + W_DECLARED_BONUS * (1.0 if declared_match else 0.0)
                 + W_LENGTH * (len(cyc) / max_len))
        records.append(LoopRecord(
            cycle=cyc, nodes=tuple(sorted(cyc)), length=len(cyc), kind=kind,
            neg_edges=negs, importance=score, tier=AUXILIARY,
            declared_match=declared_match, shared_nodes=shared))

    # tier assignment: primary = best score; ties on score fall to the
    # canonical cycle tuple order (floats never the sole tie-breaker).
    records.sort(key=lambda r: (-r.importance, r.cycle))
    primary = records[0]
    primary.tier = PRIMARY
    threshold = primary.importance * SUPPORTING_RATIO
    for r in records[1:]:
        if r.importance >= threshold:
            r.tier = SUPPORTING

    return LoopStructureModel(
        status="degraded" if degraded_reason else "ok",
        reason=degraded_reason,
        loops=records, enumerated_total=enumerated_total,
        primary_loop=primary)


@dataclass
class GraphStructureAnalysis:
    """Topology features consumed by the Orchestrator's preregistered
    scheduling rules. Scheduling reads ONLY these features (+ resource
    budgets) — never candidate quality (plan section 2 power-transfer
    note)."""
    n_nodes: int
    n_edges: int
    max_degree: int
    core_nodes: int
    isolated_nodes: int
    loop_model: LoopStructureModel

    @property
    def loop_count(self):
        return len(self.loop_model.loops)

    def to_dict(self):
        return {"n_nodes": self.n_nodes, "n_edges": self.n_edges,
                "max_degree": self.max_degree,
                "core_nodes": self.core_nodes,
                "isolated_nodes": self.isolated_nodes,
                "loop_model": self.loop_model.to_dict()}


def analyze_graph(graph) -> GraphStructureAnalysis:
    nodes = sorted(graph.node_ids())
    adj = graph.adj_undirected()
    degrees = {v: len(adj.get(v, ())) for v in nodes}
    core = [v for v in nodes if degrees[v] > 0]
    return GraphStructureAnalysis(
        n_nodes=len(nodes), n_edges=len(graph.edges),
        max_degree=max(degrees.values()) if degrees else 0,
        core_nodes=len(core), isolated_nodes=len(nodes) - len(core),
        loop_model=analyze_loop_structure(graph))
