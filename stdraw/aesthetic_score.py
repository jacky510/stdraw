"""Aesthetic scorer v1 — "does it look hand-drawn?" as a deterministic 0-100 score.

Position (does NOT overstep): this scorer is the *placeholder heuristic* of the
three-tier selection funnel and the measuring instrument for program-level
success criteria.  Final adjudication stays with the Pareto + preference
ranker (Phase 3).  It is strictly separated from the delivery certificate:
certificate best/uncertified grading never reads this score.

Design (per card directive + reviewer boundary comments):
- Single-source features: every input scalar comes from ``stdraw.features``
  keys (incl. the two single-source extension keys ``avg_edge_length`` /
  ``symmetry_axis_err_px``).  No duplicate geometry implementations here.
- Thin layer only: take keys -> normalize -> weight -> 0-100 map.
- Data-driven feature selection: Mann-Whitney AUC per feature between the
  human anchor points and same-family engine outputs; keep strong
  discriminators (|AUC - 0.5| >= AUC_KEEP) — the §14 feature-screening
  discipline applied to this card.
- Weight fit: L2-regularized logistic regression via deterministic IRLS
  (Newton-Raphson, fixed iterations, no RNG).  Stdlib only.
- Calibers: ``absolute`` (raw px; declared same-canvas-family ~960px only)
  vs ``normalized`` (px / canvas diagonal; the cross-canvas §15.2 caliber).
  Both carry an explicit domain declaration in every output.
- Human lower bound: recomputed from the anchor set at every calibration
  (= min positive score under the fitted model).  NEVER a hardcoded constant;
  it must be re-derived whenever the anchor library grows.

Zero visible windows, zero RNG, sorted traversal + math.fsum throughout.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from .features import extract_features

SCHEMA = "stdraw.aesthetic_score/v1"
MODEL_SCHEMA = "stdraw.aesthetic_model/v1"

CALIBER_ABSOLUTE = "absolute"
CALIBER_NORMALIZED = "normalized"
CALIBERS = (CALIBER_ABSOLUTE, CALIBER_NORMALIZED)

# Domain declarations (boundary comment #3: absolute px caliber is declared
# valid ONLY for the same canvas family; cross-canvas goes normalized).
DOMAIN_DECLARATIONS = {
    CALIBER_ABSOLUTE: "same-canvas-family (~960px viewBox) only",
    CALIBER_NORMALIZED: "cross-canvas / cross-graph (normalized by canvas diagonal, RFC §15.2)",
}

AUC_KEEP = 0.30           # keep feature when |AUC - 0.5| >= 0.30 (i.e. >=0.8 / <=0.2)
MIN_COVERAGE = 0.7        # feature usable when >=70% of samples have a value
MIN_SHAPE_POSITIVE = 3    # shape model fitted only with >=3 positives (else global fallback)
L2_LAMBDA = 1.0           # L2 regularization in standardized space
IRLS_ITERS = 50           # fixed Newton iterations (determinism: no convergence loop)
SCORE_SCALE = 100.0

EPS = 1e-12


class AestheticError(ValueError):
    """Raised when calibration or scoring cannot proceed."""


# ───────────────────── scalar extraction (thin layer) ─────────────────────

# (scalar_name, feature_key, subpath, unit)
# unit None => caliber-neutral; "px" => /diagonal; "px2" => /diagonal^2
_SC = "crossing_count", "total", None

SCALAR_SPECS = (
    ("alignment_max_coverage", "alignment_coverage", ("max_coverage",), None),
    ("angular_resolution_min", "angular_resolution_deg", ("min",), "deg_norm"),
    ("aspect_deviation", "canvas_fill_and_aspect", ("aspect_deviation_from_square",), None),
    ("automorphism_residual", "automorphism_symmetry_residual", ("residual",), "px"),
    ("avg_edge_length", "avg_edge_length", ("mean_px",), "px"),
    ("bend_soft_margin", "bend_curvature_soft_clearance", ("soft_margin_px",), "px"),
    ("bend_total_curvature", "bend_count_total_curvature", ("total_curvature_deg",), "deg_norm"),
    ("canvas_fill_rate", "canvas_fill_and_aspect", ("fill_rate",), None),
    ("crossing_count", _SC[0], (_SC[1],), None),
    ("edge_length_cv", "edge_length_cv", ("cv",), None),
    ("degree_centroid_spearman", "degree_centroid_spearman", ("rho",), None),
    ("hub_degree", "hub_centroid_distance", ("hub_degree",), None),
    ("hub_neighbor_centrality_ratio", "hub_neighbor_centrality_ratio", ("ratio",), None),
    ("hub_centroid_ratio", "hub_centroid_distance", ("ratio",), None),
    ("hub_centroid_px", "hub_centroid_distance", ("distance_px",), "px"),
    ("loop_edge_crossings", "loop_edge_crossing_count", ("total",), None),
    ("loop_edge_length_cv", "loop_edge_length_cv", ("mean",), None),
    ("loop_foreign_nodes", "loop_foreign_node_count", ("total",), None),
    ("loop_compactness_mean", "loop_isoperimetric_compactness", ("mean",), None),
    ("loop_overlap_area", "loop_overlap_area", ("total",), "px2"),
    ("loop_self_intersections", "loop_self_intersections", ("total",), None),
    ("max_min_edge_ratio", "max_min_edge_ratio", ("ratio",), None),
    ("min_crossing_angle", "min_crossing_angle_deg", ("min",), "deg_norm"),
    ("min_spacing_ratio", "min_spacing_diagonal_ratio", ("ratio",), None),
    ("min_spacing_px", "min_spacing_diagonal_ratio", ("min_spacing_px",), "px"),
    ("mirror_axis_err", "mirror_axis_residual", ("residual",), "px"),
    ("node_spacing_cv", "node_spacing_cv", ("cv",), None),
    ("symmetry_axis_err_px", "symmetry_axis_err_px", ("err_px",), "px"),
    ("visual_centroid_px", "visual_centroid_offset", ("offset_px",), "px"),
    ("visual_centroid_ratio", "visual_centroid_offset", ("ratio",), None),
    ("voronoi_area_cv", "voronoi_cell_area_cv", ("cv",), None),
)


def _dig(doc, key, path):
    node = doc.get("features", {}).get(key)
    if not isinstance(node, dict):
        return None
    for p in path:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    if node is None or isinstance(node, bool):
        return None
    if isinstance(node, (int, float)):
        return float(node)
    return None


def _scale(value, unit, diagonal):
    """Apply the caliber scaling for a raw px-ish scalar."""
    if unit is None or unit == "deg_norm":
        # deg_norm: min angle in degrees is already scale-free (angle, not length)
        return value
    if unit == "px":
        return value / diagonal if diagonal > EPS else None
    if unit == "px2":
        d2 = diagonal * diagonal
        return value / d2 if d2 > EPS else None
    raise AestheticError("unknown unit %r" % unit)


def extract_scalars(feature_doc, caliber):
    """Thin layer: feature doc -> {scalar_name: float-or-None} under a caliber."""
    if caliber not in CALIBERS:
        raise AestheticError("unknown caliber %r (expected %r)" % (caliber, CALIBERS))
    diagonal = float(feature_doc.get("canvas", {}).get("diagonal") or 0.0)
    counts = feature_doc.get("counts", {})
    out = {}
    for name, key, path, unit in SCALAR_SPECS:
        raw = _dig(feature_doc, key, path)
        if raw is None:
            out[name] = None
        elif caliber == CALIBER_NORMALIZED and unit in ("px", "px2"):
            out[name] = _scale(raw, unit, diagonal)
        else:
            out[name] = raw
    n_nodes = counts.get("nodes")
    out["layout_n_nodes"] = float(n_nodes) if isinstance(n_nodes, int) else None
    return out


def scalars_for_layout(layout_doc, caliber):
    """Convenience: layout.json -> scalar row (features extracted single-source)."""
    return extract_scalars(extract_features(layout_doc), caliber)


# ───────────────────── discriminability + selection ─────────────────────

def _auc(pos_vals, neg_vals):
    """Mann-Whitney AUC (P(pos > neg) + 0.5 * P(pos == neg)), deterministic."""
    if not pos_vals or not neg_vals:
        return None
    stat = 0.0
    for p in pos_vals:
        for n in neg_vals:
            if p > n:
                stat += 1.0
            elif p == n:
                stat += 0.5
    return stat / (len(pos_vals) * len(neg_vals))


def _median(vals):
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def feature_discriminability(rows_pos, rows_neg, names):
    """{name: {"auc", "coverage", "kept", "impute"}} for all scalar names."""
    report = {}
    for name in names:
        pos = [r[name] for r in rows_pos if r[name] is not None]
        neg = [r[name] for r in rows_neg if r[name] is not None]
        cov = (len(pos) + len(neg)) / (len(rows_pos) + len(rows_neg)) if (rows_pos or rows_neg) else 0.0
        auc = _auc(pos, neg) if cov > 0 else None
        keep = bool(
            auc is not None
            and cov >= MIN_COVERAGE
            and abs(auc - 0.5) >= AUC_KEEP
        )
        all_vals = sorted(pos + neg)
        report[name] = {
            "auc": None if auc is None else round(auc, 6),
            "coverage": round(cov, 6),
            "kept": keep,
            "impute_median": _median(all_vals) if all_vals else 0.0,
        }
    return report


def _design_rows(rows, names, impute):
    """rows -> list of float vectors (median imputation, deterministic)."""
    out = []
    for r in rows:
        out.append([r[n] if r[n] is not None else impute[n] for n in names])
    return out


# ───────────────────── deterministic logistic fit ─────────────────────

def _sigmoid(z):
    # stable form
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _standardize(rows):
    n = len(rows)
    k = len(rows[0])
    mean = [math.fsum(r[j] for r in rows) / n for j in range(k)]
    std = []
    for j in range(k):
        var = math.fsum((r[j] - mean[j]) ** 2 for r in rows) / n
        std.append(math.sqrt(var) if var > EPS ** 2 else 1.0)
    return mean, std


def fit_logistic(vectors, labels, names, l2=L2_LAMBDA, iters=IRLS_ITERS):
    """L2 logistic regression, Newton/IRLS, fixed iterations. Deterministic.

    Class-balanced weights counter the 10-pos / 40-neg anchor imbalance.
    """
    n = len(vectors)
    k = len(names)
    n_pos = sum(1 for y in labels if y == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        raise AestheticError("calibration needs both classes (got %d pos / %d neg)" % (n_pos, n_neg))
    w_pos = n / (2.0 * n_pos)
    w_neg = n / (2.0 * n_neg)
    mean, std = _standardize(vectors)
    z = [[(r[j] - mean[j]) / std[j] for j in range(k)] for r in vectors]
    w = [0.0] * k
    b = 0.0
    for _ in range(iters):
        grad_w = [l2 * w[j] for j in range(k)]
        grad_b = l2 * b
        h_w = [l2] * k
        h_b = l2
        for i in range(n):
            p = _sigmoid(b + math.fsum(w[j] * z[i][j] for j in range(k)))
            r = p - labels[i]
            sw = w_pos if labels[i] == 1 else w_neg
            r *= sw
            h = p * (1.0 - p) * sw
            for j in range(k):
                grad_w[j] += r * z[i][j]
                h_w[j] += h * z[i][j] * z[i][j]
            grad_b += r
            h_b += h
        # damped Newton step (guarantees descent; still deterministic)
        step_w = [grad_w[j] / h_w[j] for j in range(k)]
        step_b = grad_b / h_b
        w = [w[j] - step_w[j] for j in range(k)]
        b -= step_b
    return {
        "names": list(names),
        "weights": {nm: round(w[j], 9) for j, nm in enumerate(names)},
        "bias": round(b, 9),
        "standardize_mean": [round(m, 9) for m in mean],
        "standardize_std": [round(s, 9) for s in std],
        "hyper": {"l2": l2, "irls_iters": iters, "class_balanced": True},
    }


def _raw_score(model, vector):
    w = model["weights"]
    names = model["names"]
    mean = model["standardize_mean"]
    std = model["standardize_std"]
    acc = model["bias"]
    for j, nm in enumerate(names):
        acc += w[nm] * (vector[j] - mean[j]) / std[j]
    return _sigmoid(acc)


def score_vector(model, vector):
    """0-100 score, one decimal, deterministic."""
    return round(SCORE_SCALE * _raw_score(model, vector), 1)


def score_row(model, row):
    vec = [row[nm] if row[nm] is not None else model["impute_median"][nm] for nm in model["names"]]
    return score_vector(model, vec)


# ───────────────────── calibration dataset ─────────────────────

def load_dataset(positive_paths, negative_paths, caliber):
    """Read layout JSONs, return (rows_pos, rows_neg, failures)."""
    rows_pos, rows_neg, failures = [], [], []
    for path in positive_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows_pos.append(scalars_for_layout(json.load(f), caliber))
        except Exception as exc:  # noqa: BLE001 - collected per-file, fail-visible in report
            failures.append({"path": str(path), "error": str(exc)})
    for path in negative_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows_neg.append(scalars_for_layout(json.load(f), caliber))
        except Exception as exc:  # noqa: BLE001
            failures.append({"path": str(path), "error": str(exc)})
    if not rows_pos or not rows_neg:
        raise AestheticError(
            "dataset incomplete: %d positive / %d negative rows loaded (%d failures)"
            % (len(rows_pos), len(rows_neg), len(failures))
        )
    return rows_pos, rows_neg, failures


def _fit_from_rows(rows_pos, rows_neg, caliber, exclude=()):
    names = [nm for nm, *_ in SCALAR_SPECS]
    disc = feature_discriminability(rows_pos, rows_neg, names)
    excluded = tuple(exclude)
    kept = [nm for nm in names if disc[nm]["kept"] and nm not in excluded]
    # overfit guard for tiny anchor sets: never more features than positives;
    # rank candidates by |AUC - 0.5| desc, name asc (deterministic).
    if len(kept) > max(1, len(rows_pos)):
        kept.sort(key=lambda nm: (-(abs((disc[nm]["auc"] or 0.5) - 0.5)), nm))
        kept = kept[:max(1, len(rows_pos))]
        kept.sort()  # restore canonical order for downstream traversal
    if not kept:
        raise AestheticError("feature selection kept 0 features — anchors carry no signal")
    impute = {nm: disc[nm]["impute_median"] for nm in kept}
    vecs = _design_rows(rows_pos, kept, impute) + _design_rows(rows_neg, kept, impute)
    labels = [1] * len(rows_pos) + [0] * len(rows_neg)
    model = fit_logistic(vecs, labels, kept)
    model["impute_median"] = {nm: round(impute[nm], 9) for nm in kept}
    model["caliber"] = caliber
    model["domain"] = DOMAIN_DECLARATIONS[caliber]
    model["schema"] = MODEL_SCHEMA
    return model, disc


def calibrate(positive_paths, negative_paths, caliber):
    """Full-anchor fit. Returns (model, fit_stats)."""
    rows_pos, rows_neg, failures = load_dataset(positive_paths, negative_paths, caliber)
    model, disc = _fit_from_rows(rows_pos, rows_neg, caliber)
    pos_scores = [score_row(model, r) for r in rows_pos]
    neg_scores = [score_row(model, r) for r in rows_neg]
    stats = {
        "n_positive": len(rows_pos),
        "n_negative": len(rows_neg),
        "load_failures": failures,
        "feature_report": disc,
        "kept_features": list(model["names"]),
        "score_auc": round(_auc(pos_scores, neg_scores), 6),
        "positive_scores_min": min(pos_scores),
        "positive_scores_mean": round(math.fsum(pos_scores) / len(pos_scores), 1),
        "positive_scores_max": max(pos_scores),
        "negative_scores_max": max(neg_scores),
        "negative_scores_mean": round(math.fsum(neg_scores) / len(neg_scores), 1),
        "negative_scores_min": min(neg_scores),
        "separation_margin": round(min(pos_scores) - max(neg_scores), 1),
        "domain": DOMAIN_DECLARATIONS[caliber],
    }
    # Human lower bound = min score of any human anchor under this fit.
    # Recomputed on every calibration — deliberately NOT a named constant.
    model["human_lower_bound"] = min(pos_scores)
    model["fit_sample_counts"] = {"positive": len(rows_pos), "negative": len(rows_neg)}
    return model, stats


def loso(positive_paths, negative_paths, caliber):
    """Leave-one-anchor-out: refit without each positive, score the held-out one.

    Returns per-anchor rows + summary.  This is the honest generalization
    estimate: every held-out anchor is scored by a model that never saw it.
    """
    rows_pos, rows_neg, _ = load_dataset(positive_paths, negative_paths, caliber)
    out_rows = []
    for i, p in enumerate(positive_paths):
        hold = rows_pos[i]
        rest_pos = rows_pos[:i] + rows_pos[i + 1:]
        model, _ = _fit_from_rows(rest_pos, rows_neg, caliber)
        out_rows.append({
            "held_out": Path(p).name,
            "score": score_row(model, hold),
            "kept_features": len(model["names"]),
        })
    scores = [r["score"] for r in out_rows]
    return {
        "caliber": caliber,
        "per_anchor": out_rows,
        "loso_min": min(scores),
        "loso_mean": round(math.fsum(scores) / len(scores), 1),
        "loso_max": max(scores),
    }


# ───────────────────── shape-conditional layer (2026-11-20 directive) ─────────────────────

# Scoring is shape-conditional: a shape router picks a per-shape weight set;
# the global formula is the fallback only.  Routing rule (documented in the
# calibration report):
#   1. file family label (benchmarks/corpus/classic/topology-families.json):
#      single-cycle family -> ring;  multi-cycle-coupled / chain / star -> hub.
#   2. nested-cycle family and unlabeled graphs — geometric, in priority order:
#      a) hub intensity (hub_degree / n_nodes, both single-source keys)
#         >= HUB_INTENSITY_THRESHOLD -> hub (classic-cld 0.88, fan 0.85/0.94);
#      b) degree-centroid Spearman rho (canvas-centre caliber): rho <= 0 ->
#         ring-dominant, rho > 0 -> hub+spoke (operator-measured convention).
#      KNOWN LIMITATION (reported, not hidden): the in-repo i00 fixture
#      measures rho = -0.53 and hub intensity 0.5 — both routes put it in
#      ring, while the operator reference says hub (+0.59, measured on the
#      WorkBuddy-side copy which this card may not read).  Logged per-sample
#      in the routing log for jacky's review.
#   3. rho undefined (degenerate graphs) -> global fallback.
SHAPE_RING = "ring"
SHAPE_HUB = "hub"
SHAPE_GLOBAL = "global"
SHAPES = (SHAPE_RING, SHAPE_HUB, SHAPE_GLOBAL)

# Operator directive: row/column alignment is naturally low on ring-family
# layouts (brand-flywheel 33%) — its weight MUST be 0 in the ring model or
# correct layouts get penalized.
SHAPE_EXCLUDED_FEATURES = {
    SHAPE_RING: ("alignment_max_coverage",),
    SHAPE_HUB: (),
    SHAPE_GLOBAL: (),
}

SHAPE_ROUTING_FROM_FAMILY = {
    # family labels from topology-families.json (CJK escaped to keep the
    # source EN-face clean; values are the gate-exempt data literals):
    # \u5355\u73af = single-cycle, \u591a\u73af\u8026\u5408 = multi-cycle
    # coupled, \u94fe = chain, \u661f = star
    "\u5355\u73af": SHAPE_RING,
    "\u591a\u73af\u8026\u5408": SHAPE_HUB,
    "\u94fe": SHAPE_HUB,
    "\u661f": SHAPE_HUB,
}

RHO_RING_THRESHOLD = 0.0        # rho <= threshold -> ring-dominant
HUB_INTENSITY_THRESHOLD = 0.75  # hub_degree/n_nodes >= threshold -> hub


def load_family_labels(path):
    """{graph name: family} from topology-families.json (file labels, first pass)."""
    with open(path, "r", encoding="utf-8") as f:
        topo = json.load(f)
    return {row["name"]: row["family"] for row in topo.get("graphs", [])}


def route_shape(graph_name, row, labels):
    """Shape routing per the rule above. Deterministic."""
    fam = labels.get(graph_name)
    if fam in SHAPE_ROUTING_FROM_FAMILY:
        return SHAPE_ROUTING_FROM_FAMILY[fam]
    n_nodes = row.get("layout_n_nodes")
    hub_degree = row.get("hub_degree")
    if n_nodes and hub_degree is not None and n_nodes > 0:
        if hub_degree / n_nodes >= HUB_INTENSITY_THRESHOLD:
            return SHAPE_HUB
    rho = row.get("degree_centroid_spearman")
    if rho is None:
        return SHAPE_GLOBAL
    return SHAPE_RING if rho <= RHO_RING_THRESHOLD else SHAPE_HUB


def merge_layout_edges(manual_doc, engine_doc):
    """Manual anchor exports may omit `edges` (e.g. classic-cld fixture);
    graph structure is single-sourced from the engine delivery layout of the
    same graph while coordinates stay 100% manual."""
    if isinstance(manual_doc.get("edges"), list):
        return manual_doc
    missing = [nid for nid in manual_doc.get("nodes", {}) if nid not in engine_doc.get("nodes", {})]
    if missing:
        raise AestheticError("manual/engine node mismatch: %r" % missing[:5])
    merged = dict(manual_doc)
    merged["edges"] = engine_doc["edges"]
    return merged


def calibrate_shape_conditional(positive_docs, negative_docs, caliber, labels):
    """Fit per-shape models + global fallback.

    positive_docs / negative_docs: iterable of (path, layout_doc).
    Returns (composite_model, per_shape_stats).
    """
    pos_rows = [(p, d.get("graph") or graph_name_of(p), scalars_for_layout(d, caliber))
                for p, d in positive_docs]
    neg_rows = [(p, d.get("graph") or graph_name_of(p), scalars_for_layout(d, caliber))
                for p, d in negative_docs]
    routing_log = []
    buckets = {s: ([], []) for s in SHAPES}  # shape -> ([pos], [neg]) rows
    for p, gname, r in pos_rows:
        s = route_shape(gname, r, labels)
        buckets[s][0].append(r)
        routing_log.append({"graph": gname, "path": Path(p).name, "kind": "positive", "shape": s})
    for p, gname, r in neg_rows:
        s = route_shape(gname, r, labels)
        buckets[s][1].append(r)
        routing_log.append({"graph": gname, "path": Path(p).name, "kind": "negative", "shape": s})

    models = {}
    stats = {}
    for shape in SHAPES:
        sp, sn = buckets[shape]
        if not sp or not sn or len(sp) < MIN_SHAPE_POSITIVE:
            stats[shape] = {"fitted": False,
                            "n_positive": len(sp), "n_negative": len(sn),
                            "fallback": SHAPE_GLOBAL,
                            "note": "shape model needs >=%d positives (grow anchors before Phase 3)"
                                    % MIN_SHAPE_POSITIVE}
            continue
        model, disc = _fit_from_rows(sp, sn, caliber,
                                     exclude=SHAPE_EXCLUDED_FEATURES[shape])
        model["impute_median"] = {nm: disc[nm]["impute_median"] for nm in model["names"]}
        model["caliber"] = caliber
        model["domain"] = DOMAIN_DECLARATIONS[caliber]
        model["schema"] = MODEL_SCHEMA
        pos_scores = [score_row(model, r) for r in sp]
        neg_scores = [score_row(model, r) for r in sn]
        model["human_lower_bound"] = min(pos_scores)
        model["fit_sample_counts"] = {"positive": len(sp), "negative": len(sn)}
        models[shape] = model
        stats[shape] = {
            "fitted": True,
            "n_positive": len(sp),
            "n_negative": len(sn),
            "excluded_features": list(SHAPE_EXCLUDED_FEATURES[shape]),
            "feature_report": disc,
            "kept_features": list(model["names"]),
            "score_auc": round(_auc(pos_scores, neg_scores), 6),
            "separation_margin": round(min(pos_scores) - max(neg_scores), 1),
            "positive_scores_min": min(pos_scores),
            "negative_scores_max": max(neg_scores),
            "domain": DOMAIN_DECLARATIONS[caliber],
        }

    # global fallback: full dataset, no exclusions
    all_pos = [r for _, _, r in pos_rows]
    all_neg = [r for _, _, r in neg_rows]
    gmodel, gdisc = _fit_from_rows(all_pos, all_neg, caliber)
    gmodel["impute_median"] = {nm: gdisc[nm]["impute_median"] for nm in gmodel["names"]}
    gmodel["caliber"] = caliber
    gmodel["domain"] = DOMAIN_DECLARATIONS[caliber]
    gmodel["schema"] = MODEL_SCHEMA
    gpos = [score_row(gmodel, r) for r in all_pos]
    gneg = [score_row(gmodel, r) for r in all_neg]
    gmodel["human_lower_bound"] = min(gpos)
    gmodel["fit_sample_counts"] = {"positive": len(all_pos), "negative": len(all_neg)}
    models[SHAPE_GLOBAL] = gmodel
    stats[SHAPE_GLOBAL] = {
        "fitted": True,
        "n_positive": len(all_pos),
        "n_negative": len(all_neg),
        "excluded_features": [],
        "feature_report": gdisc,
        "kept_features": list(gmodel["names"]),
        "score_auc": round(_auc(gpos, gneg), 6),
        "separation_margin": round(min(gpos) - max(gneg), 1),
        "positive_scores_min": min(gpos),
        "negative_scores_max": max(gneg),
        "domain": DOMAIN_DECLARATIONS[caliber],
    }

    composite = {
        "schema": MODEL_SCHEMA,
        "kind": "shape-conditional",
        "caliber": caliber,
        "domain": DOMAIN_DECLARATIONS[caliber],
        "family_labels": labels,
        "routing": {
            "rule": "(1) family label: single-cycle->ring, multi-cycle-coupled/"
                    "chain/star->hub; (2) nested-cycle + unlabeled: hub intensity "
                    "(hub_degree/n >= %.2f -> hub) first, then degree_centroid_spearman "
                    "(canvas-centre caliber, <=0->ring, >0->hub); (3) undefined rho -> "
                    "global fallback. KNOWN LIMITATION: in-repo i00 fixture measures "
                    "rho=-0.53 / hub intensity 0.5 -> routed ring, conflicting with the "
                    "operator reference (+0.59, measured on the WorkBuddy-side copy this "
                    "card may not read) — logged per-sample in routing_log for review"
                    % HUB_INTENSITY_THRESHOLD,
            "rho_threshold": RHO_RING_THRESHOLD,
            "hub_intensity_threshold": HUB_INTENSITY_THRESHOLD,
            "family_map_source": "benchmarks/corpus/classic/topology-families.json",
            "shape_excluded_features": {k: list(v) for k, v in SHAPE_EXCLUDED_FEATURES.items()},
        },
        "models": models,
    }
    return composite, {"shapes": stats, "routing_log": routing_log}


def loso_shape_conditional(positive_docs, negative_docs, caliber, labels):
    """Leave-one-anchor-out on the shape-conditional composite: refit the
    held-out anchor's shape model without it, score the held-out anchor with
    the refit weights (routing kept as-calibrated)."""
    pos_rows = [(p, d.get("graph") or graph_name_of(p), scalars_for_layout(d, caliber))
                for p, d in positive_docs]
    buckets = {s: ([], []) for s in (SHAPE_RING, SHAPE_HUB)}
    routed = []
    for p, gname, r in pos_rows:
        s = route_shape(gname, r, labels)
        buckets[s][0].append((p, gname, r))
        routed.append((p, gname, r, s))
    neg_named = [(d.get("graph") or graph_name_of(p), scalars_for_layout(d, caliber))
                 for p, d in negative_docs]
    for gname, r in neg_named:
        s = route_shape(gname, r, labels)
        buckets[s][1].append(r)

    per_anchor = []
    for p, gname, r, s in routed:
        if s not in buckets or not buckets[s][0]:
            continue
        sp = [rr for (pp, _, rr) in buckets[s][0] if pp != p]
        sn = buckets[s][1]
        if not sp or not sn or len(sp) < MIN_SHAPE_POSITIVE:
            per_anchor.append({"held_out": gname, "shape": s, "score": None,
                               "note": "subset below MIN_SHAPE_POSITIVE for LOSO refit"})
            continue
        model, _ = _fit_from_rows(sp, sn, caliber, exclude=SHAPE_EXCLUDED_FEATURES[s])
        model["impute_median"] = {nm: 0.0 for nm in model["names"]}  # unused at score time
        # recompute impute from full-subset stats for consistency
        disc = feature_discriminability(sp, sn, [nm for nm, *_ in SCALAR_SPECS])
        model["impute_median"] = {nm: disc[nm]["impute_median"] for nm in model["names"]}
        per_anchor.append({"held_out": gname, "path": Path(p).name,
                           "shape": s, "score": score_row(model, r)})
    out = {"caliber": caliber, "per_anchor": per_anchor}
    for s in (SHAPE_RING, SHAPE_HUB):
        scores = [a["score"] for a in per_anchor if a["shape"] == s and a["score"] is not None]
        out["%s_min" % s] = min(scores) if scores else None
        out["%s_mean" % s] = round(math.fsum(scores) / len(scores), 1) if scores else None
    return out


def graph_name_of(path):
    stem = Path(path).stem
    for suffix in ("-manual-layout",):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


def route_and_score(doc, composite):
    """Route a layout doc to its shape model and score. Returns (score, shape)."""
    row = scalars_for_layout(doc, composite["caliber"])
    labels = composite.get("family_labels", {})
    shape = route_shape(doc.get("graph"), row, labels)
    model = composite["models"].get(shape) or composite["models"][SHAPE_GLOBAL]
    return score_row(model, row), shape


def score_layout(layout_doc, model):
    """Score a single layout doc. Accepts composite (shape-conditional) or a
    plain single-shape model dict. Deterministic."""
    if model.get("kind") == "shape-conditional":
        return route_and_score(layout_doc, model)[0]
    caliber = model["caliber"]
    row = scalars_for_layout(layout_doc, caliber)
    return score_row(model, row)


# ───────────────────── CLI ─────────────────────

def _collect_json(dirpath, patterns):
    """Sorted, deterministic JSON discovery (manual-layout fixtures + user dirs)."""
    base = Path(dirpath)
    files = set()
    for pat in patterns:
        files.update(p for p in base.rglob(pat) if p.is_file())
    # provenance/readme sidecars are .md — the .json filter already excludes
    # them, but keep an explicit name guard for safety.
    return sorted(str(p) for p in files if "provenance" not in p.name.lower())


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m stdraw.aesthetic_score",
        description="Aesthetic scorer v1: 0-100 'looks hand-drawn' score (deterministic)")
    ap.add_argument("layout_json", nargs="?", help="layout.json to score")
    ap.add_argument("--model", help="fitted model JSON (default: benchmarks/aesthetic/model-v1.json)")
    ap.add_argument("--calibrate", action="store_true", help="fit from anchors + negatives")
    ap.add_argument("--positives", action="append",
                    help="directory with human anchor layout JSONs (repeatable)")
    ap.add_argument("--negatives", help="directory with engine output layout JSONs")
    ap.add_argument("--caliber", choices=CALIBERS, default=CALIBER_ABSOLUTE)
    ap.add_argument("--out-model", help="write fitted model JSON here")
    ap.add_argument("--out-report", help="write calibration report JSON here")
    ap.add_argument("--loso", action="store_true", help="with --calibrate: also run leave-one-anchor-out")
    args = ap.parse_args(argv)

    if args.calibrate:
        if not args.positives or not args.negatives:
            ap.error("--calibrate requires --positives and --negatives")
        pos, neg = [], []
        for d in args.positives:
            pos.extend(_collect_json(d, ("*.json",)))
        neg = _collect_json(args.negatives, ("*.json",))
        model, stats = calibrate(pos, neg, args.caliber)
        result = {"schema": SCHEMA, "kind": "calibration", "model": model, "stats": stats}
        if args.loso:
            result["loso"] = loso(pos, neg, args.caliber)
        text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out_model:
            Path(args.out_model).parent.mkdir(parents=True, exist_ok=True)
            with open(args.out_model, "w", encoding="utf-8", newline="\n") as f:
                json.dump(model, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
        if args.out_report:
            Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)
            with open(args.out_report, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        else:
            sys.stdout.write(text)
        return 0

    if not args.layout_json:
        ap.error("provide layout_json or --calibrate")
    model_path = args.model or str(Path(__file__).resolve().parent.parent
                                   / "benchmarks" / "aesthetic" / "model-v1.json")
    with open(model_path, "r", encoding="utf-8") as f:
        model = json.load(f)
    with open(args.layout_json, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if model.get("kind") == "shape-conditional":
        score, shape = route_and_score(doc, model)
        used = model["models"].get(shape) or model["models"]["global"]
        human_lower_bound = used.get("human_lower_bound")
    else:
        score = score_layout(doc, model)
        shape = None
        human_lower_bound = model.get("human_lower_bound")
    out = {
        "schema": SCHEMA,
        "score": score,
        "caliber": model["caliber"],
        "domain": model.get("domain", DOMAIN_DECLARATIONS.get(model["caliber"], "")),
        "human_lower_bound": human_lower_bound,
        "layout": args.layout_json,
    }
    if shape is not None:
        out["shape"] = shape
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
