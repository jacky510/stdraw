# -*- coding: utf-8 -*-
"""Candidate evaluation + three-tier selection (candidate-pool pipeline).

Plan v1.3.1 section 3 — candidate three-tier screening, M1 initial form:

  Stage 1  Hard Constraint Filter — geometric L0 hard constraints (box press
           = 0, edge-box clearance >= 16px, card gap >= 16px rect-gap
           caliber, mutual-pair separation >= 4px). Violators are OUT; this
           is a constraint check, not a preference.
  Stage 2  Diversity Preservation THEN epsilon-Pareto per structural group
           — candidates whose metrics are close but structural forms differ
           must keep their class representative, so grouping by
           structural_signature runs FIRST and a metric-dominant peer from
           another group can never eliminate a form; within a group the
           epsilon-domination compresses near-duplicates and the
           deterministic group-best survives. Metric normalization uses
           FROZEN constants (never the candidate pool's own min/max — plan
           section 8).
  Stage 3  Preference Ranking (M1 placeholder) — a FIXED preregistered
           heuristic score. The learned ranker lands in Phase 3; until then
           the placeholder is deterministic and honest about being one.
           Score buckets are chained eps groups (see _score_buckets): two
           scores within SCORE_TIE_EPS of the same chain are one bucket,
           so a 2e-13 gap can no longer split ranks across a floor
           boundary.

Routing-in-the-loop: candidates are routed (same Router caliber as the
auto-v2 trial gates) under a DETERMINISTIC operation budget — each routed
edge costs 1 op, the budget is a preregistered constant times the edge
count, and candidates are processed in the deterministic generation order.
Budget exhaustion honestly marks the remaining candidates unrouted (a
resource rule, never a quality elimination).

Determinism: fixed metric computation order, candidates compared through
stable ids, epsilon comparisons by explicit numeric rules, final tie-break
chain structural_signature -> coordinate sequence -> candidate_id; floats
are never the sole tie-breaker.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .candidate_contract import (LayoutCandidate, SCORE_TIE_EPS,
                                 structural_tiebreak_key)

# ---- routing-in-the-loop operation budget (preregistered) ----
# ops = routed edges; budget allows every generated candidate to be routed
# (K * edges) — the budget is a hard ceiling so future M2 candidate-count
# growth cannot silently turn into unbounded work. Phase 0 timing data will
# recalibrate the constant; it is never wall-clock.
ROUTING_OP_BUDGET_CANDIDATES = 12
ROUTING_OP_MARGIN_OPS = 64

# ---- Stage 2 metric normalization: FROZEN ranges (plan section 3) ----
# Fixed reference scales, NOT pool-derived. To be replaced by the frozen
# benchmark ranges produced by Phase 0 (benchmarks/REPORT.md caliber) in a
# dedicated calibration step; until then they are honest declared constants.
NORM_RANGES = {
    # metric: (min, max) in native units
    "crossings": (0.0, 6.0),
    "edge_length_cv": (0.0, 1.0),
    "center_offset_norm": (0.0, 1.0),
}
# epsilon per metric, normalized units (plan section 3: near-duplicate
# compression caliber; per-metric epsilon, never a single global knee
# threshold).
EPSILON = {
    "crossings": 0.0,          # integer metric: exact domination only
    "edge_length_cv": 0.02,
    "center_offset_norm": 0.02,
}

# ---- Stage 3 placeholder heuristic weights (preregistered, M1 only) ----
# Lower is better. Placeholder until the Phase 3 learned pairwise ranker;
# documented as such wherever the score is surfaced.
HEURISTIC_WEIGHTS = {
    "crossings": 2.0,
    "edge_length_cv": 1.0,
    "center_offset_norm": 0.5,
}


@dataclass
class CandidateReport:
    """Routing-in-the-loop evaluation of one candidate (deterministic)."""
    cand: LayoutCandidate
    routed: bool = False
    budget_exhausted: bool = False
    # router-theory calibers (same Router class as the trial gates)
    crossings: Optional[int] = None
    press_count: Optional[int] = None
    clearance_violations: Optional[int] = None
    min_clear: Optional[float] = None
    min_card_gap: Optional[float] = None
    mutual_min_dist: Optional[float] = None
    # soft metric vector (Stage 2/3)
    edge_length_cv: Optional[float] = None
    center_offset_norm: Optional[float] = None
    hard_pass: Optional[bool] = None
    hard_failures: List[str] = field(default_factory=list)

    def normalized(self, key) -> float:
        lo, hi = NORM_RANGES[key]
        v = getattr(self, key)
        if v is None:
            return 1.0
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (float(v) - lo) / (hi - lo)))

    def metric_vector(self) -> Dict[str, float]:
        return {k: self.normalized(k) for k in NORM_RANGES}

    def to_dict(self):
        return {
            "candidate_id": self.cand.candidate_id,
            "source": self.cand.source,
            "structural_signature": self.cand.structural_signature,
            "routed": self.routed,
            "budget_exhausted": self.budget_exhausted,
            "crossings": self.crossings,
            "press_count": self.press_count,
            "clearance_violations": self.clearance_violations,
            "min_clear": None if self.min_clear is None else round(self.min_clear, 3),
            "min_card_gap": None if self.min_card_gap is None else round(self.min_card_gap, 3),
            "mutual_min_dist": None if self.mutual_min_dist is None else round(self.mutual_min_dist, 3),
            "edge_length_cv": None if self.edge_length_cv is None else round(self.edge_length_cv, 6),
            "center_offset_norm": None if self.center_offset_norm is None else round(self.center_offset_norm, 6),
            "hard_pass": self.hard_pass,
            "hard_failures": self.hard_failures,
        }


def _edge_length_cv(positions, edges) -> float:
    import math
    lens = []
    for a, b in edges:
        (xa, ya), (xb, yb) = positions[a], positions[b]
        lens.append(math.hypot(xb - xa, yb - ya))
    if not lens:
        return 0.0
    mean = sum(lens) / len(lens)
    if mean <= 1e-9:
        return 0.0
    var = sum((l - mean) ** 2 for l in lens) / len(lens)
    return math.sqrt(var) / mean


def _center_offset_norm(positions, widths, card_h) -> float:
    xs = [(positions[v][0], widths[v]) for v in positions]
    ys = [(positions[v][1], card_h) for v in positions]
    total_w = sum(w for _, w in xs) or 1
    total_h = sum(h for _, h in ys) or 1
    cx = sum(x * w for x, w in xs) / total_w
    cy = sum(y * h for y, h in ys) / total_h
    min_x = min(positions[v][0] - widths[v] / 2 for v in positions)
    max_x = max(positions[v][0] + widths[v] / 2 for v in positions)
    min_y = min(positions[v][1] - card_h / 2 for v in positions)
    max_y = max(positions[v][1] + card_h / 2 for v in positions)
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    diag = max(max_x - min_x, max_y - min_y) or 1.0
    d = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5
    return min(1.0, d / diag)


def route_and_evaluate(candidates: List[LayoutCandidate], ctx,
                       op_budget: Optional[int] = None) -> List[CandidateReport]:
    """Routing-in-the-loop: route each candidate (deterministic order) and
    evaluate hard constraints + metric vector under the operation budget."""
    from .routing import Router, min_pair_dist, sample_polyline, ANCHOR_MIN_DEG
    if op_budget is None:
        op_budget = (ROUTING_OP_BUDGET_CANDIDATES * max(1, len(ctx.edges))
                     + ROUTING_OP_MARGIN_OPS)
    cfg = ctx.cfg
    nodes = sorted(ctx.graph.node_ids())
    reports = []
    ops_left = op_budget
    for cand in candidates:                      # deterministic input order
        rep = CandidateReport(cand=cand)
        if ops_left <= 0:
            rep.budget_exhausted = True
            reports.append(rep)
            continue
        positions = cand.node_positions
        nodes_px = {v: (positions[v][0], positions[v][1], ctx.widths[v],
                        ctx.card_h) for v in nodes}
        router = Router(nodes_px, list(ctx.edges), cfg.clearance, cfg.pitch)
        routes = router.route_all()
        ops_left -= len(ctx.edges)               # 1 op per routed edge
        rep.routed = True
        rep.crossings = router.final_crossing_pairs(routes)
        rep.press_count = sum(1 for info in routes.values() if info.get("press", 0))
        clears = [info["min_clear"] for info in routes.values()
                  if info.get("min_clear") is not None]
        rep.min_clear = min(clears) if clears else None
        rep.clearance_violations = sum(
            1 for c in clears if c < cfg.clearance - 1e-6)
        # card gap (rect_gap caliber, same as the trial gates)
        gap = None
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                gx = abs(positions[a][0] - positions[b][0]) \
                    - (ctx.widths[a] + ctx.widths[b]) / 2
                gy = abs(positions[a][1] - positions[b][1]) - ctx.card_h
                g = max(gx, gy)
                gap = g if gap is None else min(gap, g)
        rep.min_card_gap = gap
        # mutual-pair separation (F1 caliber)
        mutual = None
        for i in range(len(ctx.edges)):
            for j in range(i + 1, len(ctx.edges)):
                ei, ej = ctx.edges[i], ctx.edges[j]
                if ei != (ej[1], ej[0]):
                    continue
                md = min_pair_dist(sample_polyline(routes[i]["points"]),
                                   sample_polyline(routes[j]["points"]))
                if md is not None:
                    mutual = md if mutual is None else min(mutual, md)
        rep.mutual_min_dist = mutual
        # soft metrics (fixed computation order)
        rep.edge_length_cv = _edge_length_cv(positions, ctx.edges)
        rep.center_offset_norm = _center_offset_norm(positions, ctx.widths,
                                                     ctx.card_h)
        # ---- Stage 1: hard constraint filter ----
        failures = []
        if rep.press_count != 0:
            failures.append("box_press_nonzero")
        if rep.min_clear is not None and rep.min_clear < cfg.clearance - 1e-6:
            failures.append("edge_box_clearance_lt_16")
        if gap is not None and gap < cfg.min_gap - 2:
            failures.append("card_gap_lt_16")
        if mutual is not None and mutual < 4.0:
            failures.append("mutual_pair_separation_lt_4px")
        if rep.crossings is not None and routes:
            for i, info in routes.items():
                if min(info.get("ang_a", ANCHOR_MIN_DEG),
                       info.get("ang_b", ANCHOR_MIN_DEG)) < ANCHOR_MIN_DEG - 1e-9:
                    failures.append("anchor_smoothing_lt_20deg")
                    break
        rep.hard_failures = sorted(set(failures))
        rep.hard_pass = not rep.hard_failures
        reports.append(rep)
    return reports


def _dominates(a: CandidateReport, b: CandidateReport) -> bool:
    """epsilon-domination (a dominates b): a no worse in every metric and
    strictly better in at least one beyond the epsilon band. Explicit
    numeric rules only."""
    better_any = False
    for key in NORM_RANGES:
        va, vb = a.normalized(key), b.normalized(key)
        eps = EPSILON[key]
        if va > vb + eps:
            return False
        if va < vb - eps:
            better_any = True
    return better_any


def _score_buckets(reports) -> Dict[float, int]:
    """Deterministic rank buckets by CHAINED SCORE_TIE_EPS grouping.

    Scores are sorted ascending; a new bucket starts when a score sits more
    than SCORE_TIE_EPS away from its bucket's first member. This replaces
    the old floor(score / eps) form, whose hard boundaries at integer
    multiples of eps let a sub-eps gap (measured: 2e-13) split two scores
    into different buckets — i.e. the float, not the declared eps band,
    decided the rank. Bucket membership is now decided by the eps band
    itself; anything inside the band falls to the structural tie-break
    chain (floats never the sole tie-breaker).
    """
    buckets: Dict[float, int] = {}
    b = -1
    anchor = None
    for s in sorted(heuristic_score(r) for r in reports):
        if anchor is None or s - anchor > SCORE_TIE_EPS:
            b += 1
            anchor = s
        buckets[s] = b
    return buckets


def _rank_key(r: CandidateReport, buckets: Dict[float, int]):
    """Rank key: eps-chain score bucket first (scores inside the tie band
    are an exact tie), then the structural tie-break chain."""
    return (buckets[heuristic_score(r)], structural_tiebreak_key(r.cand))


def pareto_and_diversity(reports: List[CandidateReport]) -> List[CandidateReport]:
    """Stage 2: diversity preservation FIRST, then epsilon-Pareto within
    each structural group.

    Grouping by structural_signature precedes the Pareto sweep: candidates
    whose metrics are close but structural forms differ must all keep a
    representative, so a metric-dominant candidate from ANOTHER structural
    group may not eliminate a form (the former full-pool-first order let
    cross-group domination bypass the diversity protection on 12/20 classic
    corpus graphs). Within a group, epsilon-domination compresses
    near-duplicates and the deterministic group-best (eps-chain score
    bucket -> structural tie-break chain) survives."""
    routed = [r for r in reports if r.routed and r.hard_pass]
    out = []
    for sig in sorted({r.cand.structural_signature for r in routed}):
        group = [r for r in routed if r.cand.structural_signature == sig]
        survivors = [r for r in group
                     if not any(_dominates(o, r) for o in group
                                if o is not r)]
        pool = survivors if survivors else group
        buckets = _score_buckets(pool)
        out.append(min(pool, key=lambda r: _rank_key(r, buckets)))
    return sorted(out, key=lambda r: structural_tiebreak_key(r.cand))


def heuristic_score(rep: CandidateReport) -> float:
    """Stage 3 placeholder: fixed preregistered weighted sum (lower better).
    NOT a learned preference model — the Phase 3 ranker replaces this."""
    return sum(HEURISTIC_WEIGHTS[k] * rep.normalized(k) for k in
               sorted(HEURISTIC_WEIGHTS))


def rank_candidates(reports: List[CandidateReport]) -> List[CandidateReport]:
    """Stage 3: fixed heuristic ranking over eps-chain score buckets,
    deterministic tie-break chain (score bucket within the tie-epsilon band
    -> structural_signature -> coordinate sequence -> candidate_id)."""
    buckets = _score_buckets(reports)
    return sorted(reports, key=lambda r: _rank_key(r, buckets))
