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
    ("degree_canvas_spearman", "degree_canvas_spearman", ("rho",), None),
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
#         >= HUB_INTENSITY_THRESHOLD -> hub (measured, supplemented-edge
#         caliber: classic-cld 0.875, fan-d12 0.923 / fan-d17 0.944);
#      b) degree-canvas Spearman rho (canvas-centre caliber): rho <= 0 ->
#         ring-dominant, rho > 0 -> hub+spoke (operator-measured convention).
#      NOTE on the operator reference values: they were measured on an
#      out-of-repo copy and are NOT reproducible from in-repo data (independent
#      review, 270-combination search); routing therefore follows the in-repo
#      supplemented-edge measurements only, logged per-sample for review.
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
# Hub-intensity routing threshold, DERIVED not asserted (independent-review
# MINOR-3; re-derived on a real run after review MAJOR-3 found the prior 0.81
# derivation rested on a crashed probe — the distribution had never actually
# been measured).  The threshold only applies to the unlabeled / nested-cycle
# population (family-labeled graphs route in step 1 and never see it).  Over
# that population, full corpus at calibration (supplemented-edge caliber,
# measured distribution logged in the card evidence intensity_distribution.txt),
# the hub intensity (hub_degree/n) measures:
#   low band max 0.70 (random-n10 i03/i11/i14 negatives; i11-a/b anchors);
#   induced-demand 0.80; classic-cld-growth-and-burden 0.875;
#   high band min 0.923 (fan-d12; fan-d17 0.944).
# The REAL empty gaps are therefore [0.70, 0.80] (midpoint 0.75) and
# [0.80, 0.875] (midpoint 0.8375).  0.75 is chosen over 0.8375: the
# counterfactual refit over both candidates (card evidence
# threshold_counterfactual.json) measures 0.75 better on the headline
# metrics — normalized ring AUC 0.9765 vs 0.9556, ring LOSO min 17.3 vs
# 15.2, hub LOSO min 57.9 vs 57.4 — while CONCEDING three: hub separation
# margin -9.2 vs -9.0, hub negative-scores-max 77.0 vs 76.4, ring
# negative-scores-max 56.8 vs 54.1 (absolute ring neg-max 50.3 vs 49.7).
# NOT strictly better on every metric; the full per-dimension comparison is
# in calibration-report.json "candidate_comparison".  0.8375 (routing
# identical to the superseded 0.81) reclassifies induced-demand (0.80)
# hub->ring.  The choice reclassifies induced-demand relative to the 0.81
# snapshot (ring n_negative 18 -> 17); disclosed, not tuned around.  It
# MUST be re-derived whenever the corpus grows: 0.75 is a hand-derived
# value, so every calibration run logs the measured intensity per sample
# (routing_log "hub_intensity", surfaced under
# "hub_intensity_threshold_derivation.measured_distribution_this_run") and
# calibrate_shape_conditional calls check_hub_intensity_gap(), which RAISES
# if a threshold-eligible value lands inside the (0.70, 0.80) gap — a
# fail-loud abort, not a silent re-route on a stale derivation.
HUB_INTENSITY_THRESHOLD = 0.75  # midpoint of the measured empty gap [0.70, 0.80]

# The measured empty gap the hand-derived threshold rests on (fail-loud
# guard below watches exactly this interval).
HUB_INTENSITY_MEASURED_GAP = (0.70, 0.80)


def hub_intensity_of(row):
    """Measured hub intensity (hub_degree/n), or None when not measurable."""
    n_nodes = row.get("layout_n_nodes")
    hub_degree = row.get("hub_degree")
    if n_nodes and hub_degree is not None and n_nodes > 0:
        return hub_degree / n_nodes
    return None


def check_hub_intensity_gap(routing_log):
    """Fail-loud guard on the MANUAL threshold derivation (review MAJOR-2).

    0.75 is a hand-derived value: the midpoint of the measured empty gap
    (0.70, 0.80) at calibration time.  Nothing re-derives it automatically,
    so if the corpus grows and a threshold-eligible sample now measures
    strictly inside that gap, the derivation is stale — silently keeping
    0.75 would route by a value the data no longer supports.  Runs on every
    calibration pass (calibrate_shape_conditional) and raises instead.
    Boundary values (0.70 / 0.80 themselves) do not close the gap; family-
    labeled samples never see the threshold and are exempt.
    """
    low, high = HUB_INTENSITY_MEASURED_GAP
    hits = sorted({round(e["hub_intensity"], 6)
                   for e in routing_log
                   if e.get("threshold_eligible")
                   and e.get("hub_intensity") is not None
                   and low < e["hub_intensity"] < high})
    if hits:
        raise AestheticError(
            "hub-intensity gap (%.2f, %.2f) behind HUB_INTENSITY_THRESHOLD="
            "%.2f has CLOSED: threshold-eligible sample(s) now measure %s "
            "inside it.  The manual threshold derivation is stale — "
            "re-derive the threshold from the current corpus before "
            "trusting any routing; refusing to continue silently."
            % (low, high, HUB_INTENSITY_THRESHOLD, hits))
    return hits


def hub_intensity_threshold_derivation():
    """Shared narrative/metadata block for the composite model and the
    calibration report (single source, so the two artifacts cannot drift).

    Review MAJOR-1: the candidate comparison carries EVERY routing-affected
    dimension including the separation margins 0.75 concedes — never again a
    selective column set behind a "strictly better" claim (which was false:
    0.8375 wins hub sep / hub neg-max / ring neg-max).
    """
    return {
        "method": "midpoint of the measured empty hub-intensity gap "
                  "over the threshold-eligible (unlabeled/nested-cycle) "
                  "population (full corpus, supplemented-edge caliber). "
                  "HAND-DERIVED, not auto-recomputed: every calibration "
                  "run logs the per-sample intensity (routing_log "
                  "\"hub_intensity\"; the calibration report carries "
                  "measured_distribution_this_run) and "
                  "check_hub_intensity_gap() RAISES if a "
                  "threshold-eligible value lands strictly inside the "
                  "(0.70, 0.80) gap — fail-loud, never a silent "
                  "re-route on a stale derivation",
        "measured_values_around_gap": {
            "low_band_max": 0.70,
            "induced_demand": 0.80,
            "classic_cld_growth_and_burden": 0.875,
            "high_band_min": 0.923,
        },
        "empty_gaps": [[0.70, 0.80], [0.80, 0.875]],
        "gap_midpoints": {"0.75": "chosen", "0.8375": "rejected"},
        "candidate_comparison": {
            "values_are": ["0.75 (chosen)", "0.8375 (rejected)"],
            "source": "counterfactual refit over both gap midpoints "
                      "(threshold-only difference; card evidence "
                      "threshold_counterfactual.json — same numbers)",
            "normalized": {
                "ring": {
                    "score_auc": [0.976471, 0.955556],
                    "separation_margin": [-6.9, -8.7],
                    "positive_scores_min": [49.9, 45.4],
                    "negative_scores_max": [56.8, 54.1],
                    "loso_min": [17.3, 15.2],
                },
                "hub": {
                    "score_auc": [0.973913, 0.972727],
                    "separation_margin": [-9.2, -9.0],
                    "positive_scores_min": [67.8, 67.4],
                    "negative_scores_max": [77.0, 76.4],
                    "loso_min": [57.9, 57.4],
                },
                "global": {
                    "score_auc": [0.955, 0.955],
                    "separation_margin": [-47.1, -47.1],
                    "note": "global fallback does not depend on the threshold",
                },
            },
            "verdict": "0.75 better on the headline dims (norm ring "
                       "AUC/sep/pos_min/LOSO, norm hub AUC/pos_min/LOSO); "
                       "0.8375 better on three (hub separation_margin "
                       "-9.0 vs -9.2, hub negative_scores_max 76.4 vs "
                       "77.0, ring negative_scores_max 54.1 vs 56.8; "
                       "absolute ring neg-max 49.7 vs 50.3) — 0.75 is "
                       "NOT strictly better on every metric; the choice "
                       "rests on the headline AUC/LOSO advantage",
            "routing_note": "0.8375 routing identical to the superseded "
                            "0.81 per-sample; 0.75 reclassifies "
                            "induced-demand (0.80) hub->ring",
        },
        "derived_threshold": HUB_INTENSITY_THRESHOLD,
        "reclassify_disclosure": "vs the superseded 0.81 snapshot this "
                  "choice routes induced-demand (measured intensity "
                  "0.80) back to hub (ring n_negative 18 -> 17)",
        "rederive_rule": "re-measure whenever the corpus grows; gap "
                         "closure raises via check_hub_intensity_gap() "
                         "(fail-loud), never tuned around",
    }


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
    intensity = hub_intensity_of(row)
    if intensity is not None:
        if intensity >= HUB_INTENSITY_THRESHOLD:
            return SHAPE_HUB
    rho = row.get("degree_canvas_spearman")
    if rho is None:
        return SHAPE_GLOBAL
    return SHAPE_RING if rho <= RHO_RING_THRESHOLD else SHAPE_HUB


def merge_layout_edges(manual_doc, engine_doc=None, backfill_loop_meta=True):
    """Complete a manual anchor's edge set from the graph source.

    Root cause this closes (independent-review MAJOR-1): the interactive
    "Export layout" writes only the edges the user touched
    (``st !== 'auto' || waypoints || userAnchor``) — a manual layout JSON is
    naturally a PARTIAL edge set + full coordinates.  Structural features
    (degree, hub intensity, rho, avg edge length, crossings, row alignment)
    must be measured on the FULL graph edge set to be comparable with engine
    negatives, which always carry the complete edge list.

    Merge semantics (decision: completion is unconditional, not only when the
    ``edges`` key is absent):
    - every manual edge is kept verbatim (style/waypoints/anchors — manual
      routing info stays 100% human);
    - with an engine doc (the graph-source delivery layout of the same
      graph): edges missing from the manual export are appended as minimal
      ``{"a", "b"}`` pairs (renderer behavior: an untouched edge = straight
      line between card centres);
    - without an engine doc: structural completion for the pure-fan family
      only — a fan graph is one hub + one spoke per remaining node, so any
      degree-0 node gets its hub spoke appended (fan anchors have no engine
      layout in the negatives library; the structure is unambiguous from the
      anchor's own full node list).  A doc WITH an edge list that is not
      fan-completable is kept as-is (nothing to append from; e.g. the
      --from-layout CLI anchors, whose edge list is already complete);
      a doc with NO edges at all fails visibly instead of being guessed.
    - node sets must match exactly (fail-visible, never silently guessed).

    The merged doc records how many edges were appended under
    ``edges_supplemented`` so the calibration report can log per-anchor
    completeness.

    Loop metadata completion (independent-review MAJOR-3 root fix,
    ``backfill_loop_meta=True`` — calibration data path only, delivery
    geometry untouched): the manual export carries NO loop membership
    (``edges[].loop_kinds``), so the role-conditioned families (loop-closure
    scalars, loop_arc_rate / nonloop_straight_rate) degrade on manual
    anchors and measure export format, not drawing quality.  With an engine
    doc available:
    - manual edges missing ``loop_kinds`` get it backfilled (plus
      ``loop_color``) from the same-graph engine layout, matched by
      multiplicity-aware (a, b) pair identity — loop membership is pure
      graph topology, position-independent, and never overrides a manual
      value (a manual edge that already declares loop_kinds stays human);
    - appended (untouched) edges additionally carry the engine's declared
      route kind as ``style`` ("arc" -> "arc", "line" -> "straight"; other
      kinds are omitted and fall through to the geometric classification) —
      the renderer draws untouched loop edges as auto-routed arcs, so the
      style proxy is renderer-faithful while geometry stays the minimal
      centre line (residual limitation: bow-direction reads on appended
      arc-styled edges use that centre line; disclosed in the v3-beta
      report).
    Pass ``backfill_loop_meta=False`` for the legacy (v3-alpha) caliber —
    byte-identical to the pre-fix merge, used by the v3-beta committed-
    caliber reproduction arm.
    """
    nodes = manual_doc.get("nodes", {})
    appended = []
    loop_backfilled = 0
    if engine_doc is not None:
        eng_nodes = engine_doc.get("nodes", {})
        missing_nodes = [nid for nid in nodes if nid not in eng_nodes]
        if missing_nodes:
            raise AestheticError("manual/engine node mismatch: %r" % missing_nodes[:5])
        eng_edges = engine_doc.get("edges")
        if not isinstance(eng_edges, list):
            raise AestheticError("engine doc carries no edge list to complete from")

        def _pair(e):
            return tuple(sorted((e.get("a"), e.get("b"))))
        have = {}
        for e in manual_doc.get("edges") or []:
            have[_pair(e)] = have.get(_pair(e), 0) + 1
        # multiplicity-aware engine edge lookup: engine_edges[k] is a FIFO
        # list so parallel edges resolve one-to-one in a stable order.
        engine_edges = {}
        for e in eng_edges:
            engine_edges.setdefault(_pair(e), []).append(e)
        if backfill_loop_meta:
            kept_edges = []
            for e in manual_doc.get("edges") or []:
                if e.get("loop_kinds") is None:
                    q = engine_edges.get(_pair(e))
                    if q:
                        src = q.pop(0)
                        e2 = dict(e)   # never mutate the caller's edge dicts
                        e2["loop_kinds"] = list(src.get("loop_kinds") or [])
                        if src.get("loop_color") is not None:
                            e2["loop_color"] = src.get("loop_color")
                        loop_backfilled += 1
                        kept_edges.append(e2)
                        continue
                kept_edges.append(e)
            manual_edges_backfilled = kept_edges
        for e in eng_edges:
            k = _pair(e)
            if have.get(k, 0) > 0:
                have[k] -= 1
                continue
            added = {"a": e.get("a"), "b": e.get("b")}
            if backfill_loop_meta:
                kinds = list(e.get("loop_kinds") or [])
                if kinds:
                    added["loop_kinds"] = kinds
                    if e.get("loop_color") is not None:
                        added["loop_color"] = e.get("loop_color")
                rk = (e.get("route") or {}).get("kind")
                if rk == "arc":
                    added["style"] = "arc"
                elif rk == "line":
                    added["style"] = "straight"
            appended.append(added)
    else:
        # structural fan completion: exactly one hub candidate (max degree),
        # every other node a spoke with degree <= 1; degree-0 nodes are
        # unexported spokes.
        deg = {}
        for e in manual_doc.get("edges") or []:
            deg[e.get("a")] = deg.get(e.get("a"), 0) + 1
            deg[e.get("b")] = deg.get(e.get("b"), 0) + 1
        spoke_ids = [nid for nid in nodes if deg.get(nid, 0) <= 1]
        hub_ids = [nid for nid in nodes if deg.get(nid, 0) > 1]
        orphans = sorted(nid for nid in nodes if deg.get(nid, 0) == 0)
        if not (len(hub_ids) == 1 and orphans
                and len(hub_ids) + len(spoke_ids) == len(nodes)):
            if manual_doc.get("edges"):
                # no graph source and nothing structurally derivable — keep
                # the doc's own edge list (completeness cannot be verified
                # here; the calibration log shows appended=0 for this anchor)
                merged = dict(manual_doc)
                merged.setdefault("edges_supplemented", 0)
                return merged
            raise AestheticError(
                "no graph source available and doc carries no edges; "
                "cannot complete the edge set (orphans=%r)" % orphans[:5])
        hub = hub_ids[0]
        for nid in orphans:
            appended.append({"a": hub, "b": nid})
    merged = dict(manual_doc)
    base = manual_edges_backfilled if engine_doc is not None \
        and backfill_loop_meta else (manual_doc.get("edges") or [])
    merged["edges"] = list(base) + appended
    merged["edges_supplemented"] = len(appended)
    if engine_doc is not None and backfill_loop_meta:
        merged["loop_meta_backfilled"] = loop_backfilled
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
        routing_log.append({"graph": gname, "path": Path(p).name, "kind": "positive",
                            "shape": s, "hub_intensity": hub_intensity_of(r),
                            "threshold_eligible":
                                labels.get(gname) not in SHAPE_ROUTING_FROM_FAMILY})
    for p, gname, r in neg_rows:
        s = route_shape(gname, r, labels)
        buckets[s][1].append(r)
        routing_log.append({"graph": gname, "path": Path(p).name, "kind": "negative",
                            "shape": s, "hub_intensity": hub_intensity_of(r),
                            "threshold_eligible":
                                labels.get(gname) not in SHAPE_ROUTING_FROM_FAMILY})
    # Fail-loud (review MAJOR-2): the 0.75 threshold is hand-derived from the
    # measured empty gap (0.70, 0.80); a corpus update that closes the gap
    # must abort here, never silently re-route on a stale derivation.
    check_hub_intensity_gap(routing_log)

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
                    "(hub_degree/n >= %.2f -> hub; DERIVED = midpoint of the "
                    "measured empty gap [0.70, 0.80] over the threshold-eligible "
                    "population) first, then degree_canvas_spearman (canvas-centre "
                    "caliber, <=0->ring, >0->hub); (3) undefined rho -> global "
                    "fallback. Anchor edge sets are completed from the graph "
                    "source before any feature is measured (review MAJOR-1); "
                    "operator reference rho values are out-of-repo and not "
                    "reproducible in-repo — routing follows in-repo measurements, "
                    "logged per-sample in routing_log"
                    % HUB_INTENSITY_THRESHOLD,
            "rho_threshold": RHO_RING_THRESHOLD,
            "hub_intensity_threshold": HUB_INTENSITY_THRESHOLD,
            "hub_intensity_threshold_derivation": hub_intensity_threshold_derivation(),
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
