#!/usr/bin/env python
"""Diagnostic driver: hub-bucket collapse — zero-labeling-cost audits.

Card: hub-bucket collapse diagnosis (branch p0/hub-collapse-diagnosis).
Diagnosis ONLY — the scorer
(stdraw/aesthetic_score.py), the committed v2 model and every calibration
artifact are treated as READ-ONLY instruments; nothing here retunes,
refits-for-release or rewrites them.

Reproduces the exact calibrate_v2 loading caliber (same collect filters,
same edge-completion source chain, same completeness gate) so every number
below is recomputable from the committed tree, then runs:

  D1  L1-L4 layer audit of the 9 hub-bucket positives
      (L1 raw scalars -> L2 standardization -> L3 logit z -> L4 logistic),
      per-feature distinct counts / variance / weight / sign constraint;
      A (feature-blind) vs C (shrinkage) discriminating readouts, plus
      logistic-saturation readout at L4.
  D2  feature correlation + effective independent dimension inside the
      9 positives (near-duplicate pairs, matrix rank, variance carriers).
  D3  hypothesis D: sub-morphology mixture inside the hub bucket
      (family labels + structural groupings, per-group score spread).
  D4  topology-internal separation caliber: per anchor graph
      human score - best engine candidate score; hub sep pair
      decomposition; same-graph multi-candidate ranking (scorer vs
      certificate-delivery pick) incl. freshly regenerated engine
      candidates (recipes: auto / ortho / auto+arc, real certificates).
  D5  high-scoring negatives audit (top 8): family / crossings /
      certificate grade / feature distance to nearest human anchor.
  D6  perturbation dose-response per anchor (4 cumulative deterministic
      levels), geometry-gate survival counted, monotonicity per anchor.

Hypothesis taxonomy (external review 2026-11-21):
  A = feature-blind (positives indistinguishable in raw features)
  B = signal-carrying dims missing from the feature set
  C = optimization compression (normalization / L2 shrinkage / saturation)
  D = sub-morphology mixture inside one bucket

Deterministic: no RNG; node offsets come from a fixed table indexed by an
integer hash of the node id.  Stdlib only (+ the stdraw package itself).
Red lines: negatives read-only; zero hardcoding into scorer artifacts.
"""
from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from stdraw import metrics  # noqa: E402
from stdraw.aesthetic_score import (  # noqa: E402
    CALIBERS,
    SCALAR_SPECS,
    feature_discriminability,
    graph_name_of,
    merge_layout_edges,
    route_shape,
    scalars_for_layout,
    score_row,
)
from calibrate_v2 import (  # noqa: E402  (same directory)
    BATCH2_DIR,
    FAMILY_MAP,
    GRAPH_ALIAS,
    NEGATIVE_DIR,
    POSITIVE_DIRS,
    collect,
    collect_positive_files,
    family_of,
    load_family_labels,
    load_graph_source_docs,
)

MODEL_PATH = REPO / "benchmarks" / "aesthetic" / "model-v2.json"
REPORT_V2_PATH = REPO / "benchmarks" / "aesthetic" / "calibration-report-v2.json"
WINNER_CALIBER = "normalized"   # committed v2 winner (asserted below)
PY = sys.executable

CARD_W_DEFAULT = 140.0   # same defaults as stdraw.features / stdraw.metrics
CARD_H_DEFAULT = 44.0

# ── deterministic perturbation machinery (no RNG) ─────────────────────────
JITTER_TABLE = (-3, -2, -1, 0, 1, 2, 3)
OFFALIGN_DX, OFFALIGN_DY = 7, 5   # ~half the auto pitch (56/2 ~ 28; sub-grid)


def ihash(s):
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


# ── corpus loading: byte-identical caliber to calibrate_v2.main ───────────

def load_corpus():
    labels = load_family_labels(str(FAMILY_MAP))
    neg_docs, engine_by_graph = [], {}
    for p in collect(NEGATIVE_DIR):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        neg_docs.append((str(p), d))
        g = d.get("graph") or graph_name_of(str(p))
        engine_by_graph.setdefault(g, d)
    source_docs = load_graph_source_docs()
    known_names = set(engine_by_graph) | set(labels) | set(source_docs)
    pos_docs = []
    for d in POSITIVE_DIRS:
        for p in collect_positive_files(d):
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            stem = graph_name_of(str(p))
            g = doc.get("graph")
            if g not in known_names:
                if stem in known_names:
                    g = stem
                else:
                    base = stem or g or "#"
                    cands = sorted(k for k in known_names if k.startswith(base + "-"))
                    g = cands[0] if len(cands) == 1 else (g or stem)
            g = GRAPH_ALIAS.get(g, g)
            doc = dict(doc)
            doc["graph"] = g
            eng = engine_by_graph.get(g) or source_docs.get(g)
            doc = merge_layout_edges(doc, eng)
            pos_docs.append((str(p), doc))
    return labels, pos_docs, neg_docs, engine_by_graph, source_docs


# ── certificate reconstruction (declared proxy caliber for ARCHIVED docs) ─

def certificate_proxy(doc, graph_name):
    """metrics.certificate on straight centre-to-centre segments.  Card dims
    come from the doc when present; missing w/h default to the ENGINE
    DELIVERED card (96 x 44, as in the negatives-library docs) — NOT the
    140-wide feature-side default, so manual exports without explicit card
    widths are not spuriously gap-gated.  Fresh CLI candidates use their
    own real certificate.json instead."""
    nodes = {}
    for nid, p in doc["nodes"].items():
        nodes[nid] = {"x": float(p["x"]), "y": float(p["y"]),
                      "w": float(p.get("w", 96.0)),
                      "h": float(p.get("h", CARD_H_DEFAULT))}
    edges = [{"a": e["a"], "b": e["b"]} for e in doc["edges"]]
    segs = {i: ((nodes[e["a"]]["x"], nodes[e["a"]]["y"]),
                (nodes[e["b"]]["x"], nodes[e["b"]]["y"]))
            for i, e in enumerate(edges)}
    return metrics.certificate({"nodes": nodes, "edges": edges,
                                "segments": segs}, graph_name=graph_name)


# ── fresh engine candidates (real certificates from the CLI) ──────────────

FRESH_RECIPES = (("auto", ("--recipe", "auto")),
                 ("ortho", ("--recipe", "ortho")),
                 ("auto-arc", ("--recipe", "auto", "--linestyle", "arc")))


def fresh_candidate(graph, source, outroot):
    """Run the committed engine CLI on the graph source; return
    [(recipe, layout_doc, certificate_dict)].  Deterministic; --skip-3d per
    the D0 directive."""
    out = []
    for name, flags in FRESH_RECIPES:
        outdir = Path(outroot) / ("%s.%s" % (graph, name))
        lj, cj = outdir / "layout.json", outdir / "certificate.json"
        if not (lj.exists() and cj.exists()):
            cmd = [PY, "-m", "stdraw", "layout", str(source), "--skip-3d",
                   "--outdir", str(outdir)] + list(flags)
            r = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            if not (lj.exists() and cj.exists()):
                out.append({"recipe": name, "error": (r.stderr or r.stdout)[-400:]})
                continue
        # reuse: the CLI is deterministic, cached candidates are byte-identical
        with open(lj, "r", encoding="utf-8") as f:
            doc = json.load(f)
        with open(cj, "r", encoding="utf-8") as f:
            cert = json.load(f)
        doc.setdefault("graph", graph)
        out.append({"recipe": name, "doc": doc, "cert": cert})
    return out


# ── scoring helper (committed v2 model only) ──────────────────────────────

class Scorer:
    def __init__(self, model, labels):
        self.model = model
        self.labels = labels

    def score(self, doc):
        g = doc.get("graph") or graph_name_of("")
        row = scalars_for_layout(doc, WINNER_CALIBER)
        s = route_shape(g, row, self.labels)
        m = self.model["models"].get(s) or self.model["models"]["global"]
        return score_row(m, row), s, row

    def hub_model(self):
        return self.model["models"]["hub"]


def fmean(vals):
    vals = [v for v in vals if v is not None]
    return math.fsum(vals) / len(vals) if vals else None


def fvar(vals):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    m = math.fsum(vals) / len(vals)
    return math.fsum((v - m) ** 2 for v in vals) / len(vals)


def distinct(vals):
    return len({round(v, 9) for v in vals if v is not None})


def spearman(xs, ys):
    def ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            return_anchor = None
            i = j + 1
        return r
    pairs = [(x, y) for x, y in zip(xs, ys)
             if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs2 = [p[0] for p in pairs]
    ys2 = [p[1] for p in pairs]
    rx, ry = ranks(xs2), ranks(ys2)
    n = len(rx)
    mx = math.fsum(rx) / n
    my = math.fsum(ry) / n
    num = math.fsum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(math.fsum((a - mx) ** 2 for a in rx)
                    * math.fsum((b - my) ** 2 for b in ry))
    return num / den if den > 1e-12 else None


def matrix_rank(rows, tol=1e-7):
    """Float rank via Gaussian elimination with partial pivoting."""
    if not rows:
        return 0
    a = [list(r) for r in rows]
    m, n = len(a), len(a[0])
    scale = max((abs(v) for r in a for v in r), default=0.0) or 1.0
    rank = 0
    for col in range(n):
        piv = max(range(rank, m), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) <= tol * scale:
            continue
        a[rank], a[piv] = a[piv], a[rank]
        pr = a[rank][col]
        for r in range(rank + 1, m):
            f = a[r][col] / pr
            for c in range(col, n):
                a[r][c] -= f * a[rank][c]
        rank += 1
        if rank == m:
            break
    return rank


# ═════════════════════════════ main diagnosis ═════════════════════════════

def main():
    outdir = REPO / "benchmarks" / "aesthetic"
    cand_out = Path(tempfile.gettempdir()) / "stdraw-diag-candidates"
    report = {"schema": "stdraw.hub_collapse_diagnosis/v1",
              "card": "hub-bucket collapse diagnosis",
              "model": str(MODEL_PATH.relative_to(REPO)),
              "caliber": WINNER_CALIBER}

    with open(MODEL_PATH, "r", encoding="utf-8") as f:
        model = json.load(f)
    assert model["caliber"] == WINNER_CALIBER
    with open(REPORT_V2_PATH, "r", encoding="utf-8") as f:
        rep2 = json.load(f)

    labels, pos_docs, neg_docs, engine_by_graph, source_docs = load_corpus()
    scorer = Scorer(model, labels)
    hub = scorer.hub_model()
    kept = hub["names"]
    print("anchors: %d  negatives: %d  hub kept features: %r"
          % (len(pos_docs), len(neg_docs), kept))

    # ── routed buckets (must reproduce calibration-report-v2) ──
    pos_recs = []
    for p, doc in pos_docs:
        g = doc.get("graph") or graph_name_of(p)
        score, shape, row = scorer.score(doc)
        pos_recs.append({"path": p, "graph": g, "file": Path(p).name,
                         "score": score, "shape": shape, "row": row, "doc": doc})
    neg_recs = []
    for p, doc in neg_docs:
        g = doc.get("graph") or graph_name_of(p)
        score, shape, row = scorer.score(doc)
        neg_recs.append({"path": p, "graph": g, "file": Path(p).name,
                         "score": score, "shape": shape, "row": row})
    committed = rep2["calibers"][WINNER_CALIBER]["positive_scores"]
    for r in pos_recs:
        key = r["graph"] + ":" + r["file"]
        c = committed.get(key)
        assert c and abs(c["score"] - r["score"]) < 1e-9 and c["shape"] == r["shape"], \
            "loader does not reproduce committed report at %s" % key
    print("loader reproduces committed calibration-report-v2 (all %d anchors)" % len(pos_recs))

    hub_pos = [r for r in pos_recs if r["shape"] == "hub"]
    hub_neg = [r for r in neg_recs if r["shape"] == "hub"]
    all_names = [nm for nm, _k, _p, _u in SCALAR_SPECS] + ["layout_n_nodes"]
    report["hub_bucket"] = {
        "n_positive": len(hub_pos), "n_negative": len(hub_neg),
        "positives": [{"anchor": r["graph"] + ":" + r["file"],
                       "score": r["score"]} for r in hub_pos],
    }

    # ═══ D1: L1-L4 layer audit ═══
    disc = feature_discriminability([r["row"] for r in hub_pos],
                                    [r["row"] for r in hub_neg], all_names)
    rows_pos = [[r["row"][nm] if r["row"][nm] is not None
                 else hub["impute_median"].get(nm, 0.0) for nm in kept]
                for r in hub_pos]
    mean, std = hub["standardize_mean"], hub["standardize_std"]
    l1 = []
    for nm in all_names:
        vals = [r["row"][nm] for r in hub_pos]
        nz = [v for v in vals if v is not None]
        d = disc[nm]
        in_model = nm in kept
        l1.append({
            "feature": nm,
            "distinct_among_pos": distinct(vals),
            "pos_min": min(nz) if nz else None,
            "pos_max": max(nz) if nz else None,
            "pos_var": fvar(vals),
            "coverage": d["coverage"],
            "auc_pos_vs_neg": d["auc"],
            "kept_in_hub_model": in_model,
            "weight": hub["weights"].get(nm),
            "sign_constraint": (None if d["auc"] is None else
                                ("expect w>0" if d["auc"] > 0.5 else "expect w<0")),
            "blind_class": ("A-constant-among-positives" if (nz and distinct(vals) == 1)
                            else "A-no-data" if not nz else "varies"),
        })
    report["D1_raw_audit"] = {
        "kept_features": kept,
        "n_scalars_audited": len(all_names),
        "per_feature": l1,
        "n_constant_among_pos": sum(1 for e in l1 if e["blind_class"].startswith("A-constant")),
        "n_varies_but_dropped": sum(1 for e in l1
                                    if e["blind_class"] == "varies" and not e["kept_in_hub_model"]),
        "n_varies_and_kept": sum(1 for e in l1
                                 if e["blind_class"] == "varies" and e["kept_in_hub_model"]),
    }

    # L2-L4
    layers = []
    for idx, r in enumerate(hub_pos):
        raw = [r["row"][nm] if r["row"][nm] is not None
               else hub["impute_median"].get(nm, 0.0) for nm in kept]
        z2 = [(raw[j] - mean[j]) / std[j] for j in range(len(kept))]
        contrib = [hub["weights"][nm] * z2[j] for j, nm in enumerate(kept)]
        z3 = hub["bias"] + math.fsum(contrib)
        p4 = 1.0 / (1.0 + math.exp(-z3)) if z3 >= 0 else \
            math.exp(z3) / (1.0 + math.exp(z3))
        layers.append({
            "anchor": r["graph"] + ":" + r["file"],
            "L1_raw": dict(zip(kept, [round(v, 6) for v in raw])),
            "L2_standardized": dict(zip(kept, [round(v, 6) for v in z2])),
            "L3_contributions": dict(zip(kept, [round(v, 6) for v in contrib])),
            "L3_logit_z": round(z3, 6),
            "L4_p": round(p4, 6),
            "L4_score": round(100.0 * p4, 1),
            "L4_sigmoid_derivative": round(p4 * (1.0 - p4), 6),
        })
    zvals = [e["L3_logit_z"] for e in layers]
    pvals = [e["L4_p"] for e in layers]
    l2_per_feature = []
    for j, nm in enumerate(kept):
        col = [e["L2_standardized"][nm] for e in layers]
        l2_per_feature.append({"feature": nm, "distinct": distinct(col),
                               "var": fvar(col)})
    report["D1_layers"] = {
        "per_anchor": layers,
        "L2_per_kept_feature": l2_per_feature,
        "L3_distinct_z": distinct(zvals),
        "L3_z_var": fvar(zvals),
        "L4_distinct_p": distinct(pvals),
        "L4_saturation": {
            "p_at_collapsed_point": fmean([e["L4_p"] for e in layers
                                           if e["L4_score"] == 81.3]),
            "sigmoid_derivative_range": [min(e["L4_sigmoid_derivative"] for e in layers),
                                         max(e["L4_sigmoid_derivative"] for e in layers)],
            "max_abs_z": max(abs(z) for z in zvals),
            "note": ("logistic saturation is MILD when p in [0.5, 0.9]: the sigmoid "
                     "derivative p(1-p) stays >= ~0.09; saturation can only explain "
                     "score flattening between ALREADY-similar z values, not the "
                     "identity of those values"),
        },
        "score_scale_note": ("score = 100*p; reported score rounding to 0.1 makes "
                             "any dZ < ~0.001 invisible in the final score"),
    }

    # ═══ D2: correlation + effective dimension ═══
    usable = [nm for nm in all_names
              if sum(1 for r in hub_pos if r["row"][nm] is not None) >= 6]
    corr = []
    hot = []
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            rho = spearman([r["row"][usable[i]] for r in hub_pos],
                           [r["row"][usable[j]] for r in hub_pos])
            if rho is None:
                continue
            corr.append({"a": usable[i], "b": usable[j], "spearman": round(rho, 4)})
            if abs(rho) >= 0.9:
                hot.append(corr[-1])
    mat = [[(r["row"][nm] if r["row"][nm] is not None else 0.0) for nm in usable]
           for r in hub_pos]
    var_carriers = [nm for nm in usable
                    if (fvar([r["row"][nm] for r in hub_pos]) or 0) > 1e-12]
    report["D2_correlation"] = {
        "usable_features": usable,
        "n_pairs_ge_0.9": len(hot),
        "hot_pairs": hot,
        "matrix_rank_among_positives": matrix_rank(mat),
        "variance_carriers": var_carriers,
        "n_variance_carriers": len(var_carriers),
        "effective_dim_note": ("effective independent dimension among the 9 hub "
                               "positives = matrix rank of their raw feature matrix"),
        "pairwise_spearman": corr,
    }

    # ═══ D3: hypothesis D — sub-morphology mixture ═══
    groups = {}
    for r in hub_pos:
        fam = labels.get(r["graph"]) or family_of(r["graph"], labels)
        rho = r["row"]["degree_canvas_spearman"]
        struct = "radial(fan-like)" if (rho is not None and rho > 0) else "non-radial"
        groups.setdefault("family:" + str(fam), []).append(r)
        groups.setdefault("structure:" + struct, []).append(r)
    d3 = {}
    for gname, members in sorted(groups.items()):
        scores = [m["score"] for m in members]
        d3[gname] = {
            "members": [m["graph"] + ":" + m["file"] for m in members],
            "scores": scores,
            "distinct_scores": distinct(scores),
            "score_spread": (max(scores) - min(scores)) if scores else None,
        }
    report["D3_sub_morphology"] = {
        "groups": d3,
        "readout_note": ("a bucket whose members span multiple families/structures "
                         "can only collapse if the KEPT features cannot see the "
                         "difference — cross-check with D1 blind classes"),
    }

    # ═══ D4: topology-internal separation caliber ═══
    hub_sep_pairs = []
    for pp in hub_pos:
        for nn in hub_neg:
            if pp["score"] < nn["score"]:
                hub_sep_pairs.append({
                    "positive": pp["graph"] + ":" + pp["file"],
                    "pos_score": pp["score"],
                    "negative": nn["graph"], "neg_score": nn["score"],
                    "gap": round(pp["score"] - nn["score"], 1)})
    pos_min_rec = min(hub_pos, key=lambda r: r["score"])
    neg_max_rec = max(hub_neg, key=lambda r: r["score"])
    report["D4_topology_internal"] = {
        "hub_pos_min": {"anchor": pos_min_rec["graph"] + ":" + pos_min_rec["file"],
                        "score": pos_min_rec["score"]},
        "hub_neg_max": {"negative": neg_max_rec["graph"],
                        "score": neg_max_rec["score"]},
        "crossing_pairs_count": len(hub_sep_pairs),
        "crossing_pairs": hub_sep_pairs,
        "positives_above_neg_max": sum(1 for pp in hub_pos
                                       if pp["score"] > neg_max_rec["score"]),
    }

    # engine candidates per anchor graph
    anchor_graphs = sorted({r["graph"] for r in pos_recs})
    source_for = {}
    for g in anchor_graphs:
        if g in source_docs:
            source_for[g] = BATCH2_DIR / "sources" / (g + ".cld")
        elif (REPO / "benchmarks" / "corpus" / "classic" / (g + ".cld")).exists():
            source_for[g] = REPO / "benchmarks" / "corpus" / "classic" / (g + ".cld")
        elif (REPO / "benchmarks" / "corpus" / "random" / (g + ".cld")).exists():
            source_for[g] = REPO / "benchmarks" / "corpus" / "random" / (g + ".cld")
    per_graph = {}
    agree = mismatch = 0
    for g in anchor_graphs:
        anchors = [r for r in pos_recs if r["graph"] == g]
        human_scores = [r["score"] for r in anchors]
        cands = []
        if g in engine_by_graph:
            doc = engine_by_graph[g]
            sc, sh, _row = scorer.score(doc)
            cert = certificate_proxy(doc, g)
            cands.append({"source": "negatives-library (archived engine layout)",
                          "recipe": "archived", "score": sc, "shape": sh,
                          "grade": cert["grade"], "crossings": cert["metrics"]["crossings"],
                          "grade_caliber": "proxy (straight segments)"})
        drafts = sorted((BATCH2_DIR).glob((g + "-draft.json")))
        for dp in drafts:
            with open(dp, "r", encoding="utf-8") as f:
                doc = json.load(f)
            doc.setdefault("graph", g)
            eng = engine_by_graph.get(g) or source_docs.get(g)
            doc = merge_layout_edges(doc, eng)
            sc, sh, _row = scorer.score(doc)
            cert = certificate_proxy(doc, g)
            cands.append({"source": "batch-2 engine draft (archived)",
                          "recipe": "draft", "score": sc, "shape": sh,
                          "grade": cert["grade"], "crossings": cert["metrics"]["crossings"],
                          "grade_caliber": "proxy (straight segments)"})
        src = source_for.get(g)
        if src is not None and src.exists():
            for fc in fresh_candidate(g, src, cand_out):
                if "error" in fc:
                    cands.append({"source": "fresh CLI", "recipe": fc["recipe"],
                                  "error": fc["error"]})
                    continue
                sc, sh, _row = scorer.score(fc["doc"])
                cands.append({"source": "fresh CLI (this tree)",
                              "recipe": fc["recipe"], "score": sc, "shape": sh,
                              "grade": fc["cert"].get("grade"),
                              "crossings": fc["cert"].get("metrics", {}).get("crossings"),
                              "grade_caliber": "engine certificate"})
        scored = [c for c in cands if "score" in c]
        best_engine = max(scored, key=lambda c: c["score"]) if scored else None
        delivery_rank = {"best": 0, "crossed-certified": 1, "second": 2,
                         "uncertified": 3}
        delivery_pick = min(scored, key=lambda c: (delivery_rank.get(c["grade"], 9),
                                                   c["crossings"] if c["crossings"] is not None else 9999,
                                                   -c["score"])) if scored else None
        scorer_top = max(scored, key=lambda c: c["score"]) if scored else None
        rank_ok = None
        if len(scored) >= 2 and delivery_pick and scorer_top:
            rank_ok = delivery_pick["recipe"] == scorer_top["recipe"] \
                and delivery_pick["source"] == scorer_top["source"]
            agree += 1 if rank_ok else 0
            mismatch += 0 if rank_ok else 1
        per_graph[g] = {
            "human_scores": human_scores,
            "human_min": min(human_scores),
            "engine_best_score": best_engine["score"] if best_engine else None,
            "delta_human_minus_engine_best": (round(min(human_scores)
                                                    - best_engine["score"], 1)
                                              if best_engine else None),
            "n_candidates": len(scored),
            "candidates": cands,
            "scorer_top": ({"recipe": scorer_top["recipe"], "source": scorer_top["source"],
                            "score": scorer_top["score"]} if scorer_top else None),
            "delivery_pick": ({"recipe": delivery_pick["recipe"],
                               "source": delivery_pick["source"],
                               "grade": delivery_pick["grade"],
                               "score": delivery_pick["score"]} if delivery_pick else None),
            "scorer_top_equals_delivery_pick": rank_ok,
        }
    report["D4_candidate_ranking"] = {
        "per_graph": per_graph,
        "graphs_with_2plus_candidates": sum(1 for v in per_graph.values()
                                            if v["n_candidates"] >= 2),
        "scorer_top_equals_delivery_pick_agree": agree,
        "disagree": mismatch,
        "delivery_rule": ("certificate grade best > crossed-certified > second > "
                          "uncertified, tie-break crossings asc, then score desc "
                          "(delivery never reads the aesthetic score — by design)"),
    }

    # ═══ D5: high-scoring negatives audit ═══
    neg_all = []
    for r in neg_recs:
        cert = certificate_proxy(engine_by_graph[r["graph"]], r["graph"]) \
            if r["graph"] in engine_by_graph else None
        neg_all.append({
            "graph": r["graph"], "family": family_of(r["graph"], labels),
            "score": r["score"], "shape": r["shape"],
            "crossings": r["row"]["crossing_count"],
            "grade": cert["grade"] if cert else None,
            "grade_caliber": "proxy (straight segments)" if cert else None,
        })
    neg_all.sort(key=lambda e: (-e["score"], e["graph"]))
    # feature distance to nearest anchor (kept features, hub-model space)
    def kept_vec(row):
        out = []
        for j, nm in enumerate(kept):
            v = row[nm] if row[nm] is not None else hub["impute_median"].get(nm, 0.0)
            out.append((v - mean[j]) / std[j])
        return out
    anchor_vecs = [kept_vec(r["row"]) for r in pos_recs]
    for e in neg_all:
        r = next(x for x in neg_recs if x["graph"] == e["graph"])
        v = kept_vec(r["row"])
        dists = [math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(v, av)))
                 for av in anchor_vecs]
        k = min(range(len(dists)), key=lambda i: dists[i])
        e["nearest_anchor"] = pos_recs[k]["graph"] + ":" + pos_recs[k]["file"]
        e["kept_feature_l2_distance"] = round(dists[k], 4)
    report["D5_negatives_top"] = neg_all[:8]
    report["D5_negatives_summary"] = {
        "n_scored": len(neg_all),
        "negatives_with_grade_best": sum(1 for e in neg_all if e["grade"] == "best"),
        "negatives_above_human_lower_bound": sum(
            1 for e in neg_all if e["score"] > 65.4),
        "neg_score_max": neg_all[0]["score"],
    }

    # ═══ D6: perturbation dose-response ═══
    def cert_viability(doc, g):
        cert = certificate_proxy(doc, g)
        m = cert["metrics"]
        return (m["min_card_gap"] >= 16.0 and len(m.get("occlusions_true", [])) == 0), cert

    def perturb_copy(doc, level):
        d = copy.deepcopy(doc)
        nodes = d["nodes"]
        ids = sorted(nodes)
        if level >= 1:      # slight deterministic jitter, every node
            for nid in ids:
                h = ihash(nid)
                dx = JITTER_TABLE[h % len(JITTER_TABLE)]
                dy = JITTER_TABLE[(h // len(JITTER_TABLE)) % len(JITTER_TABLE)]
                nodes[nid]["x"] = nodes[nid]["x"] + dx
                nodes[nid]["y"] = nodes[nid]["y"] + dy
        if level >= 2 and len(ids) >= 2:   # swap two nodes
            a, b = ids[0], ids[1]
            nodes[a]["x"], nodes[b]["x"] = nodes[b]["x"], nodes[a]["x"]
            nodes[a]["y"], nodes[b]["y"] = nodes[b]["y"], nodes[a]["y"]
        if level >= 3:      # break edge mirror: reflect half the nodes
            vb = d.get("viewBox") or [0, 0, 960, 560]
            cx = float(vb[0]) + float(vb[2]) / 2.0
            for nid in ids[:len(ids) // 2]:
                nodes[nid]["x"] = 2.0 * cx - float(nodes[nid]["x"])
        if level >= 4:      # off alignment lines: sub-grid offsets on odd nodes
            for i, nid in enumerate(ids):
                if i % 2 == 1:
                    nodes[nid]["x"] = float(nodes[nid]["x"]) + OFFALIGN_DX
                    nodes[nid]["y"] = float(nodes[nid]["y"]) + OFFALIGN_DY
        return d

    LEVEL_NAMES = ("L0_original", "L1_jitter", "L2_swap2", "L3_break_mirror",
                   "L4_off_align")
    dose = {}
    rej = {ln: 0 for ln in LEVEL_NAMES}
    mono_ok = 0
    l0_viable = 0
    for r in pos_recs:
        g = r["graph"]
        steps = []
        prev_score = None
        monotone = True
        for lv, ln in enumerate(LEVEL_NAMES):
            doc = r["doc"] if lv == 0 else perturb_copy(r["doc"], lv)
            viable, cert = cert_viability(doc, g)
            if not viable:
                rej[ln] += 1
                steps.append({"level": ln, "gate_rejected": True,
                              "min_card_gap": cert["metrics"]["min_card_gap"],
                              "box_press_true": len(cert["metrics"].get(
                                  "occlusion_details_true") or [])})
                continue
            row = scalars_for_layout(doc, WINNER_CALIBER)
            sc2, sh2, _row = scorer.score(doc)
            kept_vals = {nm: row[nm] for nm in kept}
            drop = None if prev_score is None else round(prev_score - sc2, 1)
            if drop is not None and drop < 0:
                monotone = False
            prev_score = sc2
            if lv == 0:
                l0_viable += 1
            steps.append({"level": ln, "score": sc2, "routed_shape": sh2,
                          "delta_vs_prev": drop,
                          "kept_features": {k: (round(v, 6) if v is not None else None)
                                            for k, v in kept_vals.items()},
                          "grade": cert["grade"],
                          "crossings": cert["metrics"]["crossings"]})
        scored_steps = [s for s in steps if not s.get("gate_rejected")]
        drops = [s["delta_vs_prev"] for s in scored_steps if s["delta_vs_prev"] is not None]
        n_dec = sum(1 for d in drops if d < 0)
        n_inc = sum(1 for d in drops if d > 0)
        n_flat = sum(1 for d in drops if d == 0)
        if not scored_steps:
            resolution = "gate-blocked-at-origin"
        elif n_dec == 0 and n_inc == 0:
            resolution = "no-resolution (all steps flat)"
        elif monotone and n_dec > 0:
            resolution = "monotone-decreasing"
        else:
            resolution = "mixed (has increase step)"
        if monotone:
            mono_ok += 1
        dose[r["graph"] + ":" + r["file"]] = {
            "monotone_nondecreasing_dose": monotone,
            "resolution_class": resolution,
            "steps_decrease_flat_increase": [n_dec, n_flat, n_inc],
            "steps": steps}
    report["D6_perturbation"] = {
        "levels": LEVEL_NAMES,
        "cumulative": True,
        "n_l0_viable": l0_viable,
        "resolution_classes": {
            "monotone-decreasing": sum(1 for v in dose.values()
                                       if v["resolution_class"] == "monotone-decreasing"),
            "no-resolution": sum(1 for v in dose.values()
                                 if v["resolution_class"].startswith("no-resolution")),
            "mixed": sum(1 for v in dose.values()
                         if v["resolution_class"].startswith("mixed")),
            "gate-blocked": sum(1 for v in dose.values()
                                if v["resolution_class"] == "gate-blocked-at-origin"),
        },
        "gate_rule": ("viability = min card gap >= 16px AND zero true box-press "
                      "(metrics.certificate on straight segments; missing card w "
                      "defaults to the engine-delivered 96px); crossings allowed "
                      "to rise (that IS the degradation being measured)"),
        "gate_rejections_per_level": rej,
        "n_anchors": len(pos_recs),
        "n_anchors_monotone_nondecreasing": mono_ok,
        "per_anchor": dose,
        "dose_definition": ("L1 +-3px id-hash jitter on every node; L2 swap the "
                            "two lowest sorted ids; L3 reflect the first half of "
                            "sorted ids about the canvas centre (breaks mirror "
                            "symmetry); L4 sub-grid offset (+7,+5) on odd nodes "
                            "(breaks row/column alignment). Cumulative."),
    }

    # ═══ emit ═══
    jpath = outdir / "diagnosis-hub-collapse.json"
    jpath.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                sort_keys=True) + "\n",
                     encoding="utf-8", newline="\n")
    print("wrote", jpath)
    return report


if __name__ == "__main__":
    main()
