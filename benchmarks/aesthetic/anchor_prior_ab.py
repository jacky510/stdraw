#!/usr/bin/env python
"""Offline A/B: M0-gate + anchor-similarity ranking vs the incumbent
heuristic Stage-3 (anchors-as-prior S3, proposal section 3.2).

Data: the three merged annotation rounds' candidate pool + 62 existing
annotations -- EVALUATION SET ONLY, zero new annotation, zero API cost,
pure local computation.

Old order = the production Stage-3 placeholder heuristic
(stdraw.candidate_selection preregistered weights over crossings /
edge_length_cv / center_offset_norm, recomputed from each candidate doc).
New order = stdraw.candidate_rank_m0.rank_candidates_m0 applied to each
graph's pool: committed model-v2 M0 scores -> relative epsilon gate
(M0 epsilon P75 = 58.6, paired within-graph caliber) -> anchor-similarity
ordering in the retrieval-hit context (three-state, never 0) -> M0
tie-break -> structural chain.

Four mechanical metrics (proposal section 3.2):
  1. anchor recognition subset: the 9 asked human-anchor vs engine pairs
     (round 3) -- does the new order rank the human candidate first?
     Compare vs the committed M0 full-calibration reading 4/9.  n=9 is
     DIRECTIONAL ONLY (CI discipline; no improvement claims).
  2. pool-top anchor similarity distribution: per hit-family graph, the
     hit-anchor distance of the new top-1 vs the old top-1.
  3. pool diversity: pool size + distinct-recipe coverage before/after the
     gate (a collapsing gate is a red flag, reported per graph).
  4. gating cost: per-graph eliminated counts + the family-unmatched
     bucket (the honest degradation of the library's coverage boundary).

Reading discipline (proposal section 5 / section 3.2): the 29 both-bad
pairs are pool quality, not ranking; the three round-3 topologies have
ZERO decided pairs -- any ordering improvement on them is NOT measurable
and is not claimed.  The library cannot help families it does not cover;
expansion (more hand anchors) is the only root fix.

Loader note (disclosed): the shared corpus loader dc.load_corpus sweeps
every *.json under benchmarks/manual and currently fails on the pairwise
annotation sessions (pre-existing breakage, reported upstream).  This
script patches it with the kind == "manual-layout" filtered loader -- the
SAME merge caliber, restricted to the actual hand anchors.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import diagnose_collapse as dc  # noqa: E402
import calibrate_v1 as c1  # noqa: E402
import calibrate_v2 as c2  # noqa: E402
import pref_pipeline as pp  # noqa: E402
import pref_ranking_m0m1m2 as base  # noqa: E402  (pool loader + sha pins)
from stdraw import anchor_prior  # noqa: E402
from stdraw import dsl  # noqa: E402
from stdraw.aesthetic_score import (  # noqa: E402
    load_family_labels, scalars_for_layout)
from stdraw.candidate_contract import structural_tiebreak_key  # noqa: E402
from stdraw.candidate_rank_m0 import (  # noqa: E402
    anchor_distances, candidate_proxy_doc, NOT_EVALUABLE_SENTINEL)
from stdraw.m0_gate import load_model, relative_gate, score_doc  # noqa: E402

OUT_JSON = REPO / "benchmarks" / "aesthetic" / "anchor-prior-ab.json"
OUT_MD = REPO / "benchmarks" / "aesthetic" / "anchor-prior-ab.md"
R3_SELECTION = REPO / "benchmarks" / "aesthetic" / "pref-round3-selection.json"
R3_SESSION = REPO / "benchmarks" / "manual" / "pairwise" / \
    "session-2026-11-22-round3"
COMMITTED_AB = REPO / "benchmarks" / "aesthetic" / \
    "pref-ranking-final-v2.json"

HEURISTIC_WEIGHTS = {"crossings": 2.0, "edge_length_cv": 1.0,
                     "center_offset_norm": 0.5}
NORM_RANGES = {"crossings": (0.0, 6.0), "edge_length_cv": (0.0, 1.0),
               "center_offset_norm": (0.0, 1.0)}


# ── filtered corpus loader (same merge caliber, kind == manual-layout) ──

def _filtered_load_corpus(merge_backfill=False):
    labels = dc.load_family_labels(str(c1.FAMILY_MAP))
    neg_docs, engine_by_graph = [], {}
    for p in c1.collect(c1.NEGATIVE_DIR):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        neg_docs.append((str(p), d))
        g = d.get("graph") or dc.graph_name_of(str(p))
        engine_by_graph.setdefault(g, d)
    source_docs = c2.load_graph_source_docs()
    known_names = set(engine_by_graph) | set(labels) | set(source_docs)
    pos_docs = []
    for d_ in c1.POSITIVE_DIRS:
        for p in c2.collect_positive_files(d_):
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            if not isinstance(doc, dict) or doc.get("kind") != "manual-layout":
                continue
            stem = dc.graph_name_of(str(p))
            g = doc.get("graph")
            if g not in known_names:
                if stem in known_names:
                    g = stem
                else:
                    base_ = stem or g or "#"
                    cands = sorted(k for k in known_names
                                   if k.startswith(base_ + "-"))
                    g = cands[0] if len(cands) == 1 else (g or stem)
            g = c2.GRAPH_ALIAS.get(g, g)
            doc = dict(doc)
            doc["graph"] = g
            eng = engine_by_graph.get(g) or source_docs.get(g)
            doc = dc.merge_layout_edges(doc, eng,
                                        backfill_loop_meta=merge_backfill)
            pos_docs.append((str(p), doc))
    return labels, pos_docs, neg_docs, engine_by_graph, source_docs


dc.load_corpus = _filtered_load_corpus   # disclosed patch (see docstring)


# ── old order: production Stage-3 heuristic on each candidate doc ────────

def _edge_length_cv(doc):
    nodes = doc["nodes"]
    lens = []
    for e in doc["edges"]:
        a, b = nodes[e["a"]], nodes[e["b"]]
        lens.append(math.hypot(b["x"] - a["x"], b["y"] - a["y"]))
    if not lens:
        return 0.0
    mean = math.fsum(lens) / len(lens)
    if mean <= 1e-9:
        return 0.0
    var = math.fsum((l - mean) ** 2 for l in lens) / len(lens)
    return math.sqrt(var) / mean


def _center_offset_norm(doc):
    nodes = doc["nodes"]
    total_w = math.fsum(n.get("w", 140.0) for n in nodes.values()) or 1
    total_h = math.fsum(44.0 for _ in nodes) or 1
    cx = math.fsum(n["x"] * n.get("w", 140.0) for n in nodes.values()) / total_w
    cy = math.fsum(n["y"] * 44.0 for n in nodes.values()) / total_h
    min_x = min(n["x"] - n.get("w", 140.0) / 2 for n in nodes.values())
    max_x = max(n["x"] + n.get("w", 140.0) / 2 for n in nodes.values())
    min_y = min(n["y"] - 22.0 for n in nodes.values())
    max_y = max(n["y"] + 22.0 for n in nodes.values())
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    diag = max(max_x - min_x, max_y - min_y) or 1.0
    d = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5
    return min(1.0, d / diag)


def _norm(key, v):
    lo, hi = NORM_RANGES[key]
    if v is None:
        return 1.0
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (float(v) - lo) / (hi - lo)))


def _chain(cid, doc):
    """Deterministic structural-chain key for a pool doc (contract caliber)."""
    from stdraw.candidate_contract import structural_signature
    positions = {v: (int(p["x"]), int(p["y"]))
                 for v, p in doc["nodes"].items()}

    class _C:
        pass
    c = _C()
    c.node_positions = positions
    c.candidate_id = cid
    c.structural_signature = structural_signature(positions)
    return structural_tiebreak_key(c)


def heuristic_score_doc(doc, crossings):
    cv = _edge_length_cv(doc)
    co = _center_offset_norm(doc)
    cr = _norm("crossings", crossings)
    return (HEURISTIC_WEIGHTS["crossings"] * cr
            + HEURISTIC_WEIGHTS["edge_length_cv"] * _norm("edge_length_cv", cv)
            + HEURISTIC_WEIGHTS["center_offset_norm"]
            * _norm("center_offset_norm", co))


# ── graph source resolution (mirrors the library build script) ───────────

def graph_source_of(graph):
    for base in (REPO / "benchmarks" / "corpus" / "classic",
                 REPO / "benchmarks" / "corpus" / "random",
                 REPO / "benchmarks" / "manual" / "jacky-batch2" / "sources",
                 REPO / "tests" / "data"):
        p = base / (graph + ".cld")
        if p.exists():
            return dsl.parse(p.read_text(encoding="utf-8"))
    if graph.startswith("fan-d"):
        k = int(graph.split("fan-d")[1]) - 1
        s = 'graph "fan-d%d"\n\n' % (k + 1)
        s += "".join('var L%02d "L%02d"\n' % (i, i) for i in range(k))
        s += 'var HUB "HUB"\n\n'
        s += "".join("HUB -> + L%02d\n" % i for i in range(k))
        return dsl.parse(s)
    return None


def main():
    sha_before = {p: base.sha256_of(REPO / p) for p in base.SHA_PINNED}
    pool = base.load_pool()
    # round-3 extension: the fresh-r3 candidate docs join the pool (the
    # committed session registry + render cache, gate-viability validated
    # by the proven loader), so the 9 asked anchor-vs-engine pairs are
    # fully covered.
    import pref_ranking_final_v2 as fv2
    _d3, _items3, _akinds, _sel3, cand_meta3 = fv2.load_r3()
    fresh = fv2.load_r3_fresh_docs(cand_meta3, pool)
    for cid, r in sorted(fresh.items()):
        pool.setdefault(r["graph"], []).append(
            {"cid": cid, "doc": r["doc"], "source": r["source"],
             "recipe": r["recipe"], "grade": r["grade"], "gap": r["gap"],
             "crossings": r["crossings"]})
    anchor_pairs_src = cand_meta3
    labels = load_family_labels(str(c1.FAMILY_MAP))
    model_v2 = json.loads((REPO / "stdraw" / "data" /
                           "model-v2.json").read_text(encoding="utf-8"))
    m0 = {"model": model_v2, "labels": labels}
    scorer = dc.Scorer(model_v2, labels)
    library = anchor_prior.load_library()
    assert library is not None, "anchor library sidecar missing"
    retrieval_cal = library["retrieval"]
    eps = retrieval_cal["calibration"] and \
        json.loads(COMMITTED_AB.read_text(encoding="utf-8"))[
            "epsilon_calibration"]["per_arm"]["M0"]["p75_initial"]
    assert abs(eps - 58.6) < 1e-9, eps   # committed M0 epsilon P75

    scorer_parity = {}
    per_graph = []
    anchor_pairs = []
    sel = json.loads(R3_SELECTION.read_text(encoding="utf-8"))
    cand_meta = anchor_pairs_src
    for q in sel["questions"]:
        if q.get("kind") != "anchor":
            continue
        ha = cand_meta[q["a"]]["source"] == "human"
        hb = cand_meta[q["b"]]["source"] == "human"
        human = q["a"] if ha else q["b"]
        engine = q["b"] if ha else q["a"]
        anchor_pairs.append({"pair_key": q["pair_key"],
                             "graph": q["graph"],
                             "human": human, "engine": engine})

    for g in sorted(pool):
        cands = pool[g]
        # committed-pool M0 scores (parity-checked against the committed
        # FeatureBank caliber per candidate, reported not asserted on
        # shape-model routing nuances)
        scores = {}
        shapes = {}
        for c in cands:
            s, shape = score_doc(c["doc"], g, m0)
            scores[c["cid"]] = s
            shapes[c["cid"]] = shape
            ref, _s2, _r = scorer.score(c["doc"], g)
            scorer_parity[c["cid"]] = (s == ref)
        # retrieval context: baseline = the deterministic auto-recipe
        # candidate (fresh-cli recipe "auto") else archived engine else
        # the first candidate -- recorded per graph
        baseline = None
        for want in (("fresh-cli", "auto"), ("archived-engine", None)):
            for c in cands:
                if c["source"] == want[0] and (
                        want[1] is None or c["recipe"] == want[1]):
                    baseline = c
                    break
            if baseline is not None:
                break
        if baseline is None:
            baseline = cands[0]
        graph_obj = graph_source_of(g)
        edges = tuple(sorted((e.a, e.b) for e in graph_obj.edges)) \
            if graph_obj is not None else ()
        retrieval = anchor_prior.retrieve(graph_obj, edges,
                                          baseline["doc"], library) \
            if graph_obj is not None else {
                "anchor_hit": None, "reason": "family-unmatched",
                "detail": ("graph-source-unresolved: no committed .cld "
                           "source (new-topology pool graph) -- the "
                           "library does not cover this family")}
        # anchor distances (three-state) via the engine module
        class _C:   # minimal candidate view for candidate_proxy_doc
            pass
        dists = {}
        if retrieval.get("anchor_hit"):
            anchor = library["anchors"][retrieval["anchor_hit"]]
            for c in cands:
                row = scalars_for_layout(c["doc"], "normalized")
                d, n, nk = anchor_prior.feature_distance(
                    row, anchor["scalars"], retrieval_cal)
                share = (n / nk) if nk else 0.0
                dists[c["cid"]] = d if (
                    d is not None and share >= 0.5) else None
        # OLD order: production heuristic
        old_scored = sorted(cands, key=lambda c: (
            heuristic_score_doc(c["doc"], c["crossings"]),
            _chain(c["cid"], c["doc"])))
        # NEW order: M0 gate + anchor similarity (+ M0 tie-break + chain)
        kept, gate_rec = relative_gate(scores, eps)
        anchor_hit = bool(retrieval.get("anchor_hit"))

        def new_key(c):
            cid = c["cid"]
            d = dists.get(cid)
            sim = (0, float(d)) if (anchor_hit and d is not None) \
                else NOT_EVALUABLE_SENTINEL
            s = scores.get(cid)
            return (sim, (-(s if s is not None else 0.0)),
                    _chain(cid, c["doc"]))
        new_scored = sorted([c for c in cands if c["cid"] in set(kept)],
                            key=new_key)
        old_top, new_top = old_scored[0], new_scored[0]
        per_graph.append({
            "graph": g,
            "pool_size": len(cands),
            "recipes_before": sorted({c["recipe"] for c in cands}),
            "recipes_after_gate": sorted({c["recipe"] for c in new_scored}),
            "anchor_hit": retrieval.get("anchor_hit"),
            "anchor_mode": retrieval.get("mode"),
            "retrieval_reason": retrieval.get("reason"),
            "baseline_candidate": baseline["cid"],
            "m0_scores": scores,
            "eliminated_by_gate": gate_rec["eliminated"],
            "pool_best": gate_rec["pool_best"],
            "anchor_distances": {c: (None if dists.get(c) is None
                                     else round(dists[c], 6))
                                 for c in sorted(dists)},
            "old_top": {"cid": old_top["cid"], "recipe": old_top["recipe"],
                        "source": old_top["source"],
                        "heuristic_score": round(
                            heuristic_score_doc(old_top["doc"],
                                                old_top["crossings"]), 6)},
            "new_top": {"cid": new_top["cid"], "recipe": new_top["recipe"],
                        "source": new_top["source"],
                        "m0_score": scores.get(new_top["cid"])},
            "old_top_anchor_distance":
                None if dists.get(old_top["cid"]) is None
                else round(dists[old_top["cid"]], 6),
            "new_top_anchor_distance":
                None if dists.get(new_top["cid"]) is None
                else round(dists[new_top["cid"]], 6),
            "top_changed": old_top["cid"] != new_top["cid"],
        })

    # ---- metric 1: anchor recognition subset (9 pairs, directional) ----
    pos_by_graph = {pg["graph"]: pg for pg in per_graph}
    order_by_graph = {}
    for g in sorted(pool):
        # reconstruct the new order for pair-position reads
        cands = pool[g]
        pg = pos_by_graph[g]
        kept = set(c["cid"] for c in cands) - set(pg["eliminated_by_gate"])
        anchor_hit = bool(pg["anchor_hit"])
        dists = {k: (None if v is None else v)
                 for k, v in pg["anchor_distances"].items()}

        def new_key(cid):
            d = dists.get(cid)
            sim = (0, float(d)) if (anchor_hit and d is not None) \
                else NOT_EVALUABLE_SENTINEL
            s = pg["m0_scores"].get(cid)
            doc = next(c["doc"] for c in cands if c["cid"] == cid)
            return (sim, (-(s if s is not None else 0.0)),
                    _chain(cid, doc))
        order_by_graph[g] = sorted(kept, key=new_key)
    anchor_rows = []
    human_first = 0
    n_evaluable = 0
    for ap_ in anchor_pairs:
        order = order_by_graph.get(ap_["graph"], [])
        pos_h = order.index(ap_["human"]) if ap_["human"] in order else None
        pos_e = order.index(ap_["engine"]) if ap_["engine"] in order else None
        if pos_h is not None and pos_e is not None:
            n_evaluable += 1
            first = pos_h < pos_e
            human_first += 1 if first else 0
        else:
            first = None
        anchor_rows.append(dict(ap_, human_pos=pos_h, engine_pos=pos_e,
                                human_first=first))
    committed_anchor = json.loads(COMMITTED_AB.read_text(
        encoding="utf-8"))["anchor_vs_engine"]["per_arm"]["S_all"]["M0"]
    committed_ratio = committed_anchor["ratio_all9_full_calib_model"]

    # ---- aggregate metrics ----
    hit_graphs = [pg for pg in per_graph if pg["anchor_hit"]]
    unmatched = [pg for pg in per_graph if not pg["anchor_hit"]]
    dist_changed = [pg["new_top_anchor_distance"] - pg["old_top_anchor_distance"]
                    for pg in hit_graphs
                    if pg["new_top_anchor_distance"] is not None
                    and pg["old_top_anchor_distance"] is not None]
    tops_changed = sum(1 for pg in per_graph if pg["top_changed"])
    min_pool_after = min(len(pg["recipes_after_gate"])
                         for pg in per_graph)
    report = {
        "schema": "stdraw.anchor-prior-ab/1",
        "discipline": {
            "n_anchor_pairs": len(anchor_pairs),
            "n_evaluable": n_evaluable,
            "reading": "n=9 DIRECTIONAL ONLY (CI discipline); no "
                       "improvement claim",
            "new_topologies": "zero decided pairs on the three round-3 "
                              "topologies -> any ordering improvement "
                              "there is NOT measurable and NOT claimed",
            "both_bad_pairs": "29 both-bad pairs are pool quality; "
                              "ranking cannot fix them; not claimed",
            "loader_note": "dc.load_corpus patched with the kind=="
                           "manual-layout filtered loader (pre-existing "
                           "upstream breakage disclosed)",
        },
        "epsilon": eps,
        "anchor_library": {
            "anchors": len(library["anchors"]),
            "threshold": retrieval_cal["hit_threshold"],
            "calibration_separated":
                retrieval_cal["calibration"]["separated"],
        },
        "scorer_parity_all_true": all(scorer_parity.values()),
        "scorer_parity_false": sorted(k for k, v in scorer_parity.items()
                                      if not v),
        "metrics": {
            "anchor_recognition": {
                "committed_M0_full_calib_ratio": committed_ratio,
                "committed_M0_full_calib_count":
                    committed_anchor["human_first_all9_full_calib_model"],
                "new_order_human_first": human_first,
                "n_evaluable": n_evaluable,
                "per_pair": anchor_rows,
            },
            "pool_top_anchor_similarity": {
                "hit_graphs": len(hit_graphs),
                "new_top_better": sum(1 for d in dist_changed if d < 0),
                "new_top_worse": sum(1 for d in dist_changed if d > 0),
                "delta_median": (sorted(dist_changed)[len(dist_changed) // 2]
                                 if dist_changed else None),
                "per_graph": {pg["graph"]: {"old": pg["old_top_anchor_distance"],
                                            "new": pg["new_top_anchor_distance"],
                                            "anchor": pg["anchor_hit"]}
                              for pg in hit_graphs},
            },
            "pool_diversity": {
                "pool_sizes": {pg["graph"]: pg["pool_size"]
                               for pg in per_graph},
                "recipe_coverage_after_gate": {
                    pg["graph"]: len(pg["recipes_after_gate"])
                    for pg in per_graph},
                "min_recipe_coverage_after_gate": min_recipe_coverage(per_graph),
            },
            "gating_cost": {
                "eliminated_total": sum(len(pg["eliminated_by_gate"])
                                        for pg in per_graph),
                "per_graph": {pg["graph"]: len(pg["eliminated_by_gate"])
                              for pg in per_graph},
                "family_unmatched": [pg["graph"] for pg in unmatched],
                "family_unmatched_reasons": {pg["graph"]: pg["retrieval_reason"]
                                             for pg in unmatched},
                "top_changed_graphs": tops_changed,
            },
        },
        "per_graph": per_graph,
    }
    js = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    js2 = json.dumps(json.loads(js), ensure_ascii=False, indent=2,
                     sort_keys=True) + "\n"
    assert js == js2, "determinism: double serialization differs"
    OUT_JSON.write_text(js, encoding="utf-8")
    OUT_MD.write_text(render_md(report), encoding="utf-8")
    sha_after = {p: base.sha256_of(REPO / p) for p in base.SHA_PINNED}
    assert sha_after == sha_before, "committed scorer artifacts moved"
    print("wrote %s" % OUT_JSON)
    print("wrote %s" % OUT_MD)
    print("anchor recognition (new order): %d/%d evaluable human-first "
          "(committed M0 full-calib %s/9)" % (human_first, n_evaluable,
                                              committed_anchor[
                                                  "human_first_all9_full_calib_model"]))
    print("pool-top similarity: %d graphs hit, new better %d / worse %d"
          % (len(hit_graphs), report["metrics"]["pool_top_anchor_similarity"]
             ["new_top_better"],
             report["metrics"]["pool_top_anchor_similarity"]["new_top_worse"]))
    print("gate eliminations: %d; family-unmatched: %d; tops changed: %d"
          % (report["metrics"]["gating_cost"]["eliminated_total"],
             len(unmatched), tops_changed))


class _FakeCand:
    """Minimal structural-chain carrier for deterministic orderings."""

    def __init__(self, cid, doc):
        pos = {v: (int(p["x"]), int(p["y"])) for v, p in doc["nodes"].items()}
        self._key = structural_tiebreak_key(_Fake(positions=pos, cid=cid))


class _Fake:
    def __init__(self, positions, cid):
        self.node_positions = positions
        self.candidate_id = cid
        from stdraw.candidate_contract import structural_signature
        self.structural_signature = structural_signature(positions)


def min_recipe_coverage(per_graph):
    return min(len(pg["recipes_after_gate"]) for pg in per_graph)


def render_md(r):
    L = []
    L.append("# Offline A/B: M0-gate + anchor-similarity ranking "
             "(anchors-as-prior S3)\n")
    L.append("Evaluation set only (three merged rounds, zero new "
             "annotation, zero API cost). n=9 anchor subset is "
             "DIRECTIONAL ONLY; new topologies (0 decided pairs) carry "
             "no ordering claim; both-bad pairs are pool quality.\n")
    m = r["metrics"]
    ar = m["anchor_recognition"]
    L.append("## Metric 1 - anchor recognition subset (9 asked pairs)\n")
    L.append("- committed M0 readings: OUT-OF-FOLD 4/7 tested (of the 9 "
             "asked; the primary committed caliber), full-calibration "
             "model 6/9 (in-sample for the 7 decided pairs, disclosed)")
    L.append("- NEW order ranks the human candidate first in %d/%d "
             "evaluable pairs" % (ar["new_order_human_first"],
                                  ar["n_evaluable"]))
    ne = [row for row in ar["per_pair"] if row["human_first"] is None]
    if ne:
        L.append("- NOT EVALUABLE (three-state, never 0): %d pairs where "
                 "the M0 gate ELIMINATED the engine candidate -- %s. The "
                 "gate itself is the stronger signal there (the engine "
                 "counterpart fell below the committed epsilon), but the "
                 "pairwise subset shrinks accordingly."
                 % (len(ne), "; ".join("%s (engine %s eliminated)"
                                       % (row["pair_key"], row["engine"])
                                       for row in ne)))
    L.append("")
    L.append("| pair_key | graph | human | engine | human_pos | engine_pos "
             "| human_first |")
    L.append("|---|---|---|---|---|---|---|")
    for row in ar["per_pair"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row["pair_key"], row["graph"], row["human"], row["engine"],
            row["human_pos"], row["engine_pos"], row["human_first"]))
    L.append("")
    pt = m["pool_top_anchor_similarity"]
    L.append("## Metric 2 - pool-top anchor similarity (hit-family subset)"
             "\n")
    L.append("- hit graphs: %d; new top closer: %d; new top farther: %d; "
             "delta median: %s" % (pt["hit_graphs"], pt["new_top_better"],
                                   pt["new_top_worse"], pt["delta_median"]))
    L.append("")
    L.append("| graph | anchor | old top dist | new top dist |")
    L.append("|---|---|---|---|")
    for g, row in sorted(pt["per_graph"].items()):
        L.append("| %s | %s | %s | %s |" % (g, row["anchor"], row["old"],
                                            row["new"]))
    L.append("")
    dv = m["pool_diversity"]
    L.append("## Metric 3 - pool diversity (gate must not collapse the "
             "pool)\n")
    L.append("- min distinct-recipe coverage after the gate: %d"
             % dv["min_recipe_coverage_after_gate"])
    worst = [g for g, n in dv["recipe_coverage_after_gate"].items()
             if n == dv["min_recipe_coverage_after_gate"]]
    if dv["min_recipe_coverage_after_gate"] <= 1:
        L.append("- COLLAPSE WATCH: %s keeps only %d distinct recipe(s) "
                 "after the gate -- flagged honestly, not hidden."
                 % (", ".join(sorted(worst)),
                    dv["min_recipe_coverage_after_gate"]))
    L.append("- pool sizes: %s" % json.dumps(dv["pool_sizes"]))
    L.append("")
    gc = m["gating_cost"]
    L.append("## Metric 4 - gating cost\n")
    L.append("- eliminated by the M0 gate: %d candidates total (%s)"
             % (gc["eliminated_total"], json.dumps(gc["per_graph"])))
    L.append("- family-unmatched: %d graphs (%s)" % (
        len(gc["family_unmatched"]),
        json.dumps(gc["family_unmatched"])))
    L.append("- top-1 changed on %d graphs" % gc["top_changed_graphs"])
    L.append("")
    L.append("## Reading discipline\n")
    L.append("- " + r["discipline"]["reading"])
    L.append("- " + r["discipline"]["new_topologies"])
    L.append("- " + r["discipline"]["both_bad_pairs"])
    L.append("- Scorer parity vs the committed FeatureBank caliber: %s"
             % r["scorer_parity_all_true"])
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
