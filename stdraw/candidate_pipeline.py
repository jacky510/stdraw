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
     -> delivery of the best candidate through the incumbent's manual-path
        machinery (same routing + hard-gate repair + certificate pipeline)
     -> NOT-WORSE-than-incumbent guard: the delivered candidate is compared
        against the v0.8.2 incumbent with a deterministic routing-metric
        tuple; the incumbent wins the comparison on any regression. The
        pipeline's quality floor is therefore, by construction, the v0.8.2
        path (M1-A "v0.8.2 回退" acceptance item).

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
from .candidate_selection import (pareto_and_diversity, rank_candidates,
                                  route_and_evaluate)
from .candidate_sources import SourceContext
from .layout_auto import layout as _auto_layout
from .planarized_layout import planarized_entry
from .structure_analyzer import analyze_graph

# Deterministic routing-metric tuple caliber for the not-worse guard and the
# delivery verification: (router-theory crossing pairs, edges pressing a
# box, edges below clearance). Same Router class as the auto-v2 trial gates.
GUARD_TUPLE_LEN = 3


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


def _guard_tuple(v4, graph, cfg, widths, card_h, edges):
    """Routing-metric tuple on DELIVERED coordinates (same caliber for
    candidate and incumbent)."""
    from .routing import Router
    nodes = sorted(graph.node_ids())
    nodes_px = {v: (v4["nodes"][v]["x"], v4["nodes"][v]["y"], widths[v],
                    card_h) for v in nodes}
    router = Router(nodes_px, list(edges), cfg.clearance, cfg.pitch)
    routes = router.route_all()
    pairs = router.final_crossing_pairs(routes)
    press = sum(1 for info in routes.values() if info.get("press", 0))
    clr = sum(1 for info in routes.values()
              if info.get("min_clear") is not None
              and info["min_clear"] < cfg.clearance - 1e-6)
    return (pairs, press, clr)


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

    # ---- planarization ladder guard (same precedence as the incumbent) ----
    pl_mode, pl_payload = planarized_entry(graph, cfg, linestyle)
    if pl_mode == "L1":
        v4 = _auto_layout(graph, cfg, linestyle)
        provenance = {
            "delivery": "planarized-l1-incumbent",
            "note": "planarized L1 witness drawing: incumbent output kept "
                    "(candidate pool out of scope for the L1 ladder in M1)",
        }
        _annotate(v4, provenance, graph, edges)
        return v4

    widths, heights, card_h = _card_metrics(graph, cfg)
    dense_hub, dense_deg_max = _dense_hub(graph, adj)
    analysis = analyze_graph(graph)
    ctx = SourceContext(graph=graph, cfg=cfg, widths=widths, card_h=card_h,
                        edges=edges, adj=adj, dense_hub=dense_hub,
                        analysis=analysis, linestyle=linestyle)

    # ---- orchestrate generation (topology/budget rules only) ----
    orch = Orchestrator()
    orch_result = orch.run(ctx)
    # the incumbent v4 (materialized by the layered-v082 source) is reused
    # as the fallback delivery; re-run deterministically if absent.
    incumbent_v4 = ctx.ops.get("incumbent_v4")
    if incumbent_v4 is None:
        incumbent_v4 = _auto_layout(graph, cfg, linestyle)

    provenance = {
        "analysis": analysis.to_dict(),
        "orchestration": orch_result.to_dict(),
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
    ranked = rank_candidates(shortlist)
    provenance["selection"] = {
        "op_budget": None,
        "evaluated": len(reports),
        "hard_pass": sum(1 for r in reports if r.hard_pass),
        "reports": [r.to_dict() for r in sorted(
            reports, key=lambda r: r.cand.candidate_id)],
        "ranked_ids": [r.cand.candidate_id for r in ranked],
    }

    incumbent_tuple = _guard_tuple(incumbent_v4, graph, cfg, widths, card_h,
                                   edges)
    # ---- delivery attempts in rank order; not-worse guard vs incumbent ----
    best_v4 = None
    best_id = None
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
        tup = _guard_tuple(v4c, graph, cfg, widths, card_h, edges)
        delivery_log.append({
            "candidate_id": cand.candidate_id,
            "outcome": "evaluated",
            "guard_tuple": list(tup),
            "incumbent_guard_tuple": list(incumbent_tuple),
        })
        # not-worse guard: candidate wins only if strictly better on the
        # deterministic tuple; on a tie the candidate wins (progressive;
        # metrics are equal so "not worse than v0.8.2" holds either way).
        if tup < incumbent_tuple or tup == incumbent_tuple:
            best_v4, best_id = v4c, cand.candidate_id
            delivery_log[-1]["outcome"] = "delivered"
            break
        delivery_log[-1]["outcome"] = "worse-than-incumbent"
    if best_v4 is not None:
        provenance["delivery"] = {
            "mode": "candidate",
            "candidate_id": best_id,
            "incumbent_guard_tuple": list(incumbent_tuple),
            "attempts": delivery_log,
        }
        v4 = best_v4
    else:
        provenance["delivery"] = {
            "mode": "incumbent-fallback",
            "reason": ("no candidate delivery passed the not-worse guard"
                       if delivery_log else
                       "no candidate was routable under the op budget"),
            "attempts": delivery_log,
        }
        v4 = incumbent_v4
    _annotate(v4, provenance, graph, edges)
    return v4


def _annotate(v4, provenance, graph, edges):
    """Stamp candidate-v1 provenance onto the pipeline's OWN output meta
    (deterministic: no timestamps, no absolute paths, sorted structures).

    meta["recipe"] stays "auto-v2": it is a dispatch/caliber key consumed by
    check.py (geometry_report routing + anchor-gate caliber) and the
    certificate contract — the delivery machinery IS the auto-v2 caliber.
    The pipeline identity travels on "recipe_requested" + "candidate_pool".
    """
    meta = v4.setdefault("meta", {})
    meta["recipe_requested"] = "candidate-v1"
    provenance["candidate_contract_keys"] = [
        "candidate_id", "source", "node_positions", "metadata",
        "generation_cost", "structural_signature"]
    meta["candidate_pool"] = provenance
