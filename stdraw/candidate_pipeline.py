# -*- coding: utf-8 -*-
"""Candidate-pool pipeline (recipe candidate-v1) — M1 minimal loop wiring.

Flow (plan v1.3.1 section 2, M1 scope):

  Graph Model
     -> Graph Structure Analyzer (three-layer loop model, polarity kept)
     -> Optimization Orchestrator (source on/off + generation budget +
        failure paths; topology/budget/preregistered rules only)
     -> candidate pool (7 template sources + layered incumbent)
     -> routing-in-the-loop under a deterministic operation budget
     -> three-tier selection (Hard Filter -> epsilon-Pareto + diversity ->
        fixed heuristic placeholder ranking, deterministic tie-breaks)
     -> delivery of the best candidate through the manual-path replay
        machinery (routing + hard-gate repair + certificate pipeline on the
        candidate coordinates). NOTE: this replay is NOT byte-equivalent to
        the auto path's routing — on layered graphs the auto path
        additionally runs the edgerules anchor presets + bounded local
        re-enumeration (layout_auto stage 2), which the manual caliber
        skips by design ("user authority over endpoints") — so a
        candidate's DELIVERED metrics can differ from its routing-time
        proxy metrics.
     -> NOT-WORSE-than-incumbent guard: BOTH sides are measured on their
        DELIVERED coordinates with the certificate machinery itself
        (certificate_auto metrics + the auto_geometry_report fail count —
        the exact values the delivered certificate / CLI rc report), and a
        delivered candidate is accepted only if it is not worse than the
        incumbent on every guard component; any regression falls back to
        the untouched v0.8.2 incumbent. The guard deliberately does NOT
        compare Router-proxy tuples: the proxy caliber can disagree with
        the delivery certificate (measured on random-n10-i04: incumbent
        proxy (4,0,0) vs its own delivered crossings=2), which let a
        4-crossing delivery tie and win. The pipeline's quality floor is
        therefore, by construction, the v0.8.2 path on the metrics the
        delivered certificate actually reports (M1-A "v0.8.2 回退"
        acceptance item).

  Failure paths: see candidate_orchestrator (source level) and below
  (delivery level). The planarization L1 ladder takes precedence exactly as
  in the incumbent path.

Everything is opt-in: the default auto-v2 recipe never enters this module,
so graphs that do not request candidate-v1 keep byte-identical output
(negative protection). The pipeline annotates only ITS OWN output meta.
"""
from dataclasses import dataclass
from typing import Optional

from .candidate_contract import LayoutCandidate
from .candidate_orchestrator import Orchestrator
from .candidate_selection import (ROUTING_OP_BUDGET_CANDIDATES,
                                  ROUTING_OP_MARGIN_OPS, pareto_and_diversity,
                                  rank_candidates, route_and_evaluate)
from .candidate_sources import SourceContext
from .layout_auto import layout as _auto_layout
from .structure_analyzer import analyze_graph

# ---- not-worse guard: DELIVERED-certificate caliber ----
# Both guard sides are computed by _cert_guard below: certificate metrics +
# the geometry-report fail count on the DELIVERED v4 (the values the
# delivered certificate reports / the CLI rc is derived from). Component
# order (lexicographic, lower is better):
#   0 geo gate fails      auto_geometry_report fail count (rc determinant)
#   1..8 hard breaches    box press / clearance deficit / anchor smoothing /
#                         anchor standard / visual crossings / line
#                         coincidence / card-gap deficit / mutual-pair deficit
#   9 crossings           delivered crossing count (soft <= 2, still ordered)
#   10..12 soft floor     spacing_cv / -min_card_gap / -edge_box_min_clear
#                         (soft metrics are part of "not worse than v0.8.2")
GUARD_TUPLE_LEN = 13


def _cert_guard(v4, cfg):
    """Certificate-caliber guard metrics on DELIVERED coordinates.

    One function for candidate and incumbent — the tuple is computed from
    the delivered v4 exactly the way the delivered certificate computes it
    (same scene, same metric machinery), so the guard comparison and the
    delivered certificate cannot disagree the way the old Router-proxy
    tuple did (incumbent proxy (4,0,0) vs its own delivered crossings=2 on
    random-n10-i04). Returns (tuple, metrics_dict) — the dict is provenance.
    """
    import contextlib
    import io
    import math as _math
    from . import check as _check
    from . import metrics as _metrics
    scene = _metrics.scene_from_auto(v4)
    cert = _metrics.certificate_auto(scene)
    m = cert["metrics"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        geo_fails = int(_check.auto_geometry_report(v4)["fail"])
    min_clear = m.get("edge_box_min_clear")
    clr_deficit = (0 if min_clear is None
                   else max(0, int(_math.ceil(cfg.clearance - min_clear))))
    gap = m.get("min_card_gap")
    gap_deficit = (0 if gap is None
                   else max(0, int(_math.ceil(cfg.min_gap - gap))))
    mutual = m.get("mutual_pair_min_sep")
    mutual_deficit = (0 if mutual is None
                      else max(0, int(_math.ceil(4.0 - mutual))))
    cv = m.get("spacing_cv")
    tup = (
        geo_fails,
        int(m["box_press_1px"]),
        clr_deficit,
        int(m["anchor_violations"]),
        int(m.get("anchor_standard_violations") or 0),
        int(m["visual_crossings"]),
        int(m.get("line_line_coincident_pairs") or 0),
        gap_deficit,
        mutual_deficit,
        int(m["crossings"]),
        float(cv) if cv is not None else 0.0,
        (-round(gap, 1)) if gap is not None else 0.0,
        (-round(min_clear, 1)) if min_clear is not None else 0.0,
    )
    metrics = {k: m[k] for k in ("crossings", "box_press_1px",
                                 "edge_box_min_clear", "min_card_gap",
                                 "spacing_cv", "visual_crossings",
                                 "anchor_violations",
                                 "anchor_standard_violations",
                                 "line_line_coincident_pairs")}
    return tup, metrics


@dataclass
class PipelineResult:
    v4: dict
    provenance: dict


def _card_metrics(graph, cfg):
    from . import textmetrics
    nodes = sorted(graph.node_ids())
    widths, heights = {}, {}
    for v in nodes:
        nd = graph.id2node()[v]
        w, h = textmetrics.card_size(nd.label, nd.value, cfg.fs_title,
                                     cfg.fs_value, min_w=cfg.card_min_w,
                                     value_pad=cfg.value_pad_extra)
        widths[v], heights[v] = w, h
    card_h = max(heights.values()) if heights else cfg.card_h
    return widths, heights, card_h


def _dense_hub(graph, adj):
    from .routing import DENSE_MIN_DEG
    nodes = sorted(graph.node_ids())
    if not nodes:
        return None, 0
    deg_max = max(len(adj[v]) for v in nodes)
    if deg_max >= DENSE_MIN_DEG:
        return sorted(nodes, key=lambda v: (-len(adj[v]), v))[0], deg_max
    return None, deg_max


def _bbox(positions, widths, card_h, margin):
    xs0 = [positions[v][0] - widths[v] / 2 for v in positions]
    xs1 = [positions[v][0] + widths[v] / 2 for v in positions]
    ys0 = [positions[v][1] - card_h / 2 for v in positions]
    ys1 = [positions[v][1] + card_h / 2 for v in positions]
    return [0, 0, int(max(xs1)) + margin, int(max(ys1)) + margin]


def layout(graph, config=None, linestyle: str = "straight", manual: dict = None):
    """candidate-v1 recipe entry. manual layouts keep user intent (delegate
    to the incumbent path unchanged)."""
    from .layout_auto import AutoConfig
    cfg = config or AutoConfig()
    edges = tuple(sorted((e.a, e.b) for e in graph.edges))
    nodes = sorted(graph.node_ids())
    adj = graph.adj_undirected()

    if manual is not None:
        return _auto_layout(graph, cfg, linestyle, manual=manual)

    # ---- M1-B: the candidate pool now runs INSIDE the L1 planarization
    # scope. The L1 ladder keeps its delivery-floor precedence exactly as
    # before -- the incumbent (delivered whenever no candidate passes the
    # not-worse guard) IS the L1 witness drawing produced by the auto path,
    # so the planarization source can only REPLACE the L1 delivery with a
    # candidate whose delivered certificate metrics are not worse. The
    # incumbent's planarization mode travels in the delivery provenance.

    widths, heights, card_h = _card_metrics(graph, cfg)
    dense_hub, dense_deg_max = _dense_hub(graph, adj)
    analysis = analyze_graph(graph)
    ctx = SourceContext(graph=graph, cfg=cfg, widths=widths, card_h=card_h,
                        edges=edges, adj=adj, dense_hub=dense_hub,
                        analysis=analysis, linestyle=linestyle)

    # ---- incumbent first (the pipeline's quality floor AND the retrieval
    # baseline). Behavior-identical: the layered-v082 source reuses the
    # stashed delivery instead of re-running the same function. A pre-run
    # failure leaves the stash unset -- the layered source then runs the
    # incumbent itself exactly as before, and retrieval is skipped with an
    # explicit record (never a crash and never a silent skip).
    incumbent_v4 = ctx.ops.get("incumbent_v4")
    if incumbent_v4 is None:
        try:
            incumbent_v4 = _auto_layout(graph, cfg, linestyle)
            ctx.ops["incumbent_v4"] = incumbent_v4
        except Exception:
            incumbent_v4 = None

    # ---- anchors-as-prior retrieval (S1): family gate (shared detect_*
    # analyzers) + in-family single-source feature distance on the frozen
    # baseline delivery. The library is DATA (only-add sidecar); absence or
    # a non-hit degrades to an EXPLICIT provenance record -- anchor_hit=null
    # with a reason (proposal section 1.1: silence is the forbidden mode).
    from . import anchor_prior, anchor_seed
    if incumbent_v4 is not None:
        library = anchor_prior.load_library()
        retrieval = anchor_prior.retrieve(graph, edges, incumbent_v4, library)
    else:
        library = None
        retrieval = {"anchor_hit": None, "reason": "baseline-unavailable",
                     "family": None}
    provenance_anchor = {k: v for k, v in sorted(retrieval.items())}
    seed = None
    if retrieval.get("anchor_hit"):
        a = library["anchors"][retrieval["anchor_hit"]]
        anchor_adj = anchor_seed._adjacency(
            [tuple(e) for e in a["graph_edges"]])
        seed = {
            "mode": retrieval["mode"],
            "anchor_key": retrieval["anchor_hit"],
            "family": retrieval["family"],
            "distance": retrieval["distance"],
            "nodes": {k: (int(p["x"]), int(p["y"]))
                      for k, p in sorted(a["nodes"].items())},
            "anchor_adj": anchor_adj,
            "matched_roles": len(anchor_seed._match_nodes(adj, anchor_adj)),
        }
    ctx.ops["anchor_seed"] = seed

    # ---- orchestrate generation (topology/budget rules only) ----
    orch = Orchestrator()
    orch_result = orch.run(ctx)
    # the incumbent v4 (materialized above, reused by the layered-v082
    # source) is the fallback delivery.
    if incumbent_v4 is None:
        incumbent_v4 = ctx.ops.get("incumbent_v4")
        if incumbent_v4 is None:
            incumbent_v4 = _auto_layout(graph, cfg, linestyle)
    incumbent_pl_mode = ((incumbent_v4.get("meta") or {})
                         .get("planarization") or {}).get("mode")

    provenance = {
        "analysis": analysis.to_dict(),
        "orchestration": orch_result.to_dict(),
        "anchor_retrieval": provenance_anchor,
        "selection": {},
        "delivery": "pending",
    }

    candidates = orch_result.candidates
    if not candidates:
        # every source failed or was disabled -> v0.8.2 incumbent untouched
        provenance["delivery"] = {
            "mode": "incumbent-fallback",
            "reason": "no candidate generated by any source",
        }
        v4 = incumbent_v4
        _annotate(v4, provenance, graph, edges)
        return v4

    # ---- routing-in-the-loop + three-tier selection ----
    reports = route_and_evaluate(candidates, ctx)
    shortlist = pareto_and_diversity(reports)
    # ---- S3 ranking replacement (isolated layer): M0 quality gate +
    # anchor-similarity ordering when the committed model resolves; the
    # previous placeholder heuristic otherwise (explicit provenance record,
    # never a silent swap).  Stage-1 viability and Stage-2 Pareto/diversity
    # are untouched; the not-worse delivery guard below is untouched.
    from . import m0_gate as _m0
    from .candidate_rank_m0 import rank_candidates_m0
    m0 = _m0.load_model()
    ranked, m0_record = rank_candidates_m0(shortlist, ctx, m0, library,
                                           retrieval)
    total_ops = (ROUTING_OP_BUDGET_CANDIDATES * max(1, len(edges))
                 + ROUTING_OP_MARGIN_OPS)
    consumed_ops = sum(len(edges) for r in reports if r.routed)
    provenance["selection"] = {
        # actual budget + consumption (MINOR-4 fix: the placeholder None
        # never reached the artifacts; now the artifact records the formula
        # value and the deterministic consumption, 1 op per routed edge)
        "op_budget": {
            "total": total_ops,
            "consumed": consumed_ops,
            "per_routed_edge": 1,
            "granularity": "per-candidate",
        },
        "evaluated": len(reports),
        "hard_pass": sum(1 for r in reports if r.hard_pass),
        "reports": [r.to_dict() for r in sorted(
            reports, key=lambda r: r.cand.candidate_id)],
        "ranked_ids": [r.cand.candidate_id for r in ranked],
        "m0_ranking": m0_record,
    }

    incumbent_tup, incumbent_metrics = _cert_guard(incumbent_v4, cfg)
    # ---- delivery attempts in rank order; not-worse guard vs incumbent ----
    best_v4 = None
    best_id = None
    best_tup = None
    consistency_ok = False
    delivery_log = []
    for rep in ranked:
        cand = rep.cand
        manual_dict = {
            "nodes": {v: {"x": cand.node_positions[v][0],
                          "y": cand.node_positions[v][1]} for v in nodes},
            "viewBox": _bbox(cand.node_positions, widths, card_h,
                             cfg.margin),
            "source": f"candidate-v1/{cand.candidate_id}",
        }
        try:
            v4c = _auto_layout(graph, cfg, linestyle, manual=manual_dict)
        except Exception as e:
            delivery_log.append({"candidate_id": cand.candidate_id,
                                 "outcome": "delivery_error",
                                 "detail": f"{type(e).__name__}: {e}"})
            continue
        tup, mets = _cert_guard(v4c, cfg)
        delivery_log.append({
            "candidate_id": cand.candidate_id,
            "outcome": "evaluated",
            "guard_tuple": list(tup),
            "delivered_metrics": mets,
            "incumbent_guard_tuple": list(incumbent_tup),
        })
        # not-worse guard on DELIVERED certificate metrics: the candidate
        # wins only if it is not worse than the incumbent on every guard
        # component; on an exact tie the candidate wins (progressive — the
        # delivered metrics are equal, so "not worse" holds either way).
        if tup <= incumbent_tup:
            best_v4, best_id, best_tup = v4c, cand.candidate_id, tup
            delivery_log[-1]["outcome"] = "delivered"
            break
        delivery_log[-1]["outcome"] = "worse-than-incumbent"
    if best_v4 is not None:
        # delivery pre/post consistency check (fail-closed): the metrics the
        # guard just compared must be exactly the delivered artifact's
        # certificate metrics; on any mismatch the incumbent is delivered.
        recheck_tup, recheck_metrics = _cert_guard(best_v4, cfg)
        consistency_ok = (recheck_tup == best_tup)
    if best_v4 is not None and consistency_ok:
        provenance["delivery"] = {
            "mode": "candidate",
            "candidate_id": best_id,
            "guard_caliber": "delivered-certificate-metrics",
            "incumbent_guard_tuple": list(incumbent_tup),
            "incumbent_delivered_metrics": incumbent_metrics,
            "delivered_metrics": recheck_metrics,
            "attempts": delivery_log,
        }
        v4 = best_v4
    else:
        # fallback reason: honest about WHICH gate emptied the delivery
        if best_v4 is not None:
            reason = ("delivery pre/post metric consistency check failed; "
                      "fail-closed to the incumbent")
        elif delivery_log and all(
                a.get("outcome") == "delivery_error" for a in delivery_log):
            reason = "every candidate delivery raised an error"
        elif delivery_log:
            reason = "no candidate delivery passed the not-worse guard"
        elif reports and all(r.hard_pass is False for r in reports):
            reason = "no candidate survived the Stage-1 hard filter"
        elif reports and all(r.budget_exhausted for r in reports):
            reason = ("routing op budget exhausted before any candidate "
                      "was evaluated")
        elif m0_record.get("active") and not ranked:
            reason = "every shortlisted candidate was eliminated by the M0 gate"
        else:
            reason = "no candidate delivery passed the not-worse guard"
        provenance["delivery"] = {
            "mode": "incumbent-fallback",
            "reason": reason,
            "guard_caliber": "delivered-certificate-metrics",
            "incumbent_guard_tuple": list(incumbent_tup),
            "incumbent_delivered_metrics": incumbent_metrics,
            "attempts": delivery_log,
        }
        v4 = incumbent_v4
    # L1-scope annotation: written ONLY when the incumbent actually came
    # through the planarization ladder (L1 graphs). Planar-graph provenance
    # stays byte-identical to M1-A (negative protection).
    if incumbent_pl_mode is not None:
        provenance["delivery"]["incumbent_planarization_mode"] = \
            incumbent_pl_mode
    _annotate(v4, provenance, graph, edges)
    return v4


def _annotate(v4, provenance, graph, edges):
    """Stamp candidate-v1 provenance onto the pipeline's OWN output meta
    (deterministic: no timestamps, no absolute paths, sorted structures).

    meta["recipe"] stays "auto-v2": it is a dispatch/caliber key consumed by
    check.py (geometry_report routing + anchor-gate caliber) and the
    certificate contract. HONESTY NOTE (corrects the former claim that the
    delivery machinery "IS the auto-v2 caliber", which measured false on
    layered graphs): the delivery REPLAYS candidate coordinates through the
    manual-path machinery — the auto path additionally runs edgerules
    anchor presets + bounded re-enumeration there — so delivered metrics
    can differ from routing-time proxies. That gap is exactly what the
    not-worse guard now measures: both sides are compared on their
    DELIVERED certificate metrics (see _cert_guard), never on proxies.
    The pipeline identity travels on "recipe_requested" + "candidate_pool".
    """
    meta = v4.setdefault("meta", {})
    meta["recipe_requested"] = "candidate-v1"
    provenance["candidate_contract_keys"] = [
        "candidate_id", "source", "node_positions", "metadata",
        "generation_cost", "structural_signature"]
    meta["candidate_pool"] = provenance
