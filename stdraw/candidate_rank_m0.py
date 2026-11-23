# -*- coding: utf-8 -*-
"""M0-gate + anchor-similarity candidate ranking (anchors-as-prior S3).

Replaces the Stage-3 placeholder heuristic in the candidate-v1 pipeline
(proposal section 3.1), as an ISOLATED layer: the viability hard filter
(Stage 1) and the epsilon-Pareto + diversity stage (Stage 2) are untouched,
and when the M0 model cannot be resolved the pipeline falls back to the
previous ranking caliber with an explicit provenance record.

Ordering (deterministic; proposal section 3.1):

    M0 gate (relative, paired epsilon within the pool)
      -> anchor similarity ascending -- ONLY in an anchor-hit retrieval
         context; NOT evaluable (no hit / missing keys) is a THREE-STATE
         value: those candidates take the sentinel and are never scored 0
         -> tie-break M0 score descending
         -> final tie-break: the structural chain (signature -> coordinate
            sequence -> candidate_id) via structural_tiebreak_key

Boundary (anti-drift, proposal section 3.1): the anchor similarity is NOT
a scoring-key extension (the 8-candidate list vetoed that road); it exists
only as an ordering signal in the anchor-hit context.

Candidate proxy docs: each candidate is scored on a straight
centre-to-centre segment rendering of its node positions (the same proxy
caliber the certificate reconstruction uses for archived docs).  The
DELIVERED artifact still goes through the routing replay + not-worse guard
-- the ranking only decides the delivery ATTEMPT ORDER and the gate
eliminations, it never grades the final artifact.
"""
from .anchor_prior import feature_distance, MIN_EVALUABLE_KEY_SHARE
from .candidate_contract import structural_tiebreak_key
from .m0_gate import M0_EPS_P75, relative_gate, score_doc

# Sentinel rank component for candidates whose anchor similarity is not
# evaluable (three-state discipline: never a 0).  Evaluable candidates sort
# first within their gate class; the disclosed alternative (interleaving by
# M0) is recorded in the A/B report as a follow-up caliber decision.
NOT_EVALUABLE_SENTINEL = (1, 0.0)


def candidate_proxy_doc(cand, ctx):
    """Straight centre-to-centre rendering of a candidate's positions."""
    nodes = sorted(ctx.graph.node_ids())
    pos = cand.node_positions
    widths, card_h = ctx.widths, ctx.card_h
    nodes_doc = {v: {"x": pos[v][0], "y": pos[v][1], "w": widths[v]}
                 for v in nodes}
    xs0 = min(pos[v][0] - widths[v] / 2 for v in nodes)
    xs1 = max(pos[v][0] + widths[v] / 2 for v in nodes)
    ys0 = min(pos[v][1] - card_h / 2 for v in nodes)
    ys1 = max(pos[v][1] + card_h / 2 for v in nodes)
    edges_doc = [{"a": a, "b": b} for a, b in ctx.edges]
    return {"nodes": nodes_doc, "edges": edges_doc,
            "viewBox": [0, 0, int(xs1 - xs0) + 1, int(ys1 - ys0) + 1],
            "meta": {"cardH": card_h}}


def anchor_distances(reports, ctx, library, retrieval):
    """{cid: distance-or-None}: feature distance from each candidate's
    proxy doc to the hit anchor's committed row (three-state)."""
    if not retrieval or not retrieval.get("anchor_hit") or not library:
        return {r.cand.candidate_id: None for r in reports}
    anchor = library["anchors"][retrieval["anchor_hit"]]
    out = {}
    for r in reports:
        doc = candidate_proxy_doc(r.cand, ctx)
        try:
            from .aesthetic_score import scalars_for_layout
            row = scalars_for_layout(doc, "normalized")
            d, n, nk = feature_distance(row, anchor["scalars"],
                                        library["retrieval"])
            share = (n / nk) if nk else 0.0
            out[r.cand.candidate_id] = d if (
                d is not None and share >= MIN_EVALUABLE_KEY_SHARE) else None
        except Exception:  # noqa: BLE001 - honest three-state, never a guess
            out[r.cand.candidate_id] = None
    return out


def rank_candidates_m0(reports, ctx, m0, library, retrieval,
                       eps=None):
    """M0 gate + anchor-similarity ranking. Returns (ranked, record).

    ``reports``: the Stage-2 shortlist. ``m0``: m0_gate.load_model() result
    or None (caller falls back when None -- this module returns the old
    caliber's ranking with the honest record instead of guessing)."""
    from .candidate_selection import rank_candidates as legacy_rank
    cids = [r.cand.candidate_id for r in reports]
    if m0 is None:
        return legacy_rank(reports), {
            "active": False, "reason": "model-unavailable",
            "candidates": len(cids)}
    graph_name = getattr(ctx.graph, "name", "") or ""
    scores = {}
    shapes = {}
    for r in reports:
        cid = r.cand.candidate_id
        try:
            s, shape = score_doc(candidate_proxy_doc(r.cand, ctx),
                                 graph_name, m0)
            scores[cid] = s
            shapes[cid] = shape
        except Exception:  # noqa: BLE001 - three-state, never 0
            scores[cid] = None
            shapes[cid] = None
    kept, gate_rec = relative_gate(scores, eps or M0_EPS_P75)
    kept_set = set(kept)
    distances = anchor_distances(reports, ctx, library, retrieval)
    anchor_hit = bool(retrieval and retrieval.get("anchor_hit"))

    def sort_key(r):
        cid = r.cand.candidate_id
        d = distances.get(cid)
        s = scores.get(cid)
        if anchor_hit and d is not None:
            sim = (0, float(d))
        else:
            sim = NOT_EVALUABLE_SENTINEL
        # M0 score desc -> structural chain (floats never the sole
        # tie-breaker; the chain follows the contract's eps discipline)
        return (sim, (-(s if s is not None else 0.0)),
                structural_tiebreak_key(r.cand))

    ranked = sorted([r for r in reports if r.cand.candidate_id in kept_set],
                    key=sort_key)
    record = {
        "active": True,
        "model": "benchmarks/aesthetic/model-v2.json (committed, read-only)",
        "epsilon": gate_rec.get("epsilon"),
        "pool_best": gate_rec.get("pool_best"),
        "eliminated_by_gate": gate_rec.get("eliminated"),
        "anchor_hit": retrieval.get("anchor_hit") if retrieval else None,
        "anchor_sim_context": anchor_hit,
        "scores": {c: scores[c] for c in sorted(scores)},
        "shapes": {c: shapes[c] for c in sorted(shapes)},
        "anchor_distances": {c: (None if distances.get(c) is None
                                 else round(distances[c], 6))
                             for c in sorted(distances)},
        "not_evaluable_note": (
            "anchor similarity None = not evaluable (three-state), "
            "never 0; those candidates rank behind evaluable ones"),
    }
    return ranked, record
