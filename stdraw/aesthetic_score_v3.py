"""Aesthetic scorer v3-alpha: feature-system rebuild (card 2026-11-21).

Three structural changes versus the committed v2 layer
(stdraw/aesthetic_score.py — UNTOUCHED, read-only imports):

1.  Prescreen replaced.  The v2 single-variable AUC prescreen
    (|AUC - 0.5| >= AUC_KEEP, capped at n_pos features) threw away 23/32
    signals and left the hub model with 2 features (hub-collapse diagnosis).
    v3 puts the FULL differentiating feature pool into a regularized
    multivariate fit — L1 (LASSO) logistic along a deterministic lambda
    path — and lets the regularization decide what stays.  The single-var
    AUC table is still REPORTED (as the "before" arm of the before/after
    comparison), but it no longer gates anything.

2.  Edge-aggregate scalars.  The new conditioning-class edge features live
    single-source in stdraw/features.py; this module only maps them to
    scalar names (thin layer, same discipline as v2 SCALAR_SPECS).

3.  Strict mirror + tight alignment calibers enter the pool.  Mirror
    consistency uses the research-card strict caliber (slot sub-caliber =
    group anchors g<->g, per the card directive; golden reported as data).
    Alignment enters at the tightened +-1 px caliber next to the unchanged
    v1 key.

Determinism: no RNG anywhere; lambda path and CV fold assignment are
derived from sorted sample paths; coordinate descent sweeps in canonical
feature order with a fixed sweep count.  Red lines: v1/v2 models and
committed reports are never written; certificate grading does not read the
scorer; features are extracted single-source from stdraw.features.
"""
from __future__ import annotations

import math

from .aesthetic_score import (  # noqa: F401  (re-exported for the driver)
    AestheticError,
    CALIBERS,
    MIN_COVERAGE,
    SHAPE_EXCLUDED_FEATURES,
    SHAPE_GLOBAL,
    SHAPE_HUB,
    SHAPE_RING,
    _auc,
    _design_rows,
    _dig,
    _median,
    _scale,
    _standardize,
    _sigmoid,
    fit_logistic,
    route_shape,
    score_row,
    score_vector,
)
from .features import extract_features

SCHEMA_V3 = "stdraw.aesthetic_score_v3/v1alpha"
MODEL_SCHEMA_V3 = "stdraw.aesthetic_model_v3/v1alpha"

# ───────── scalar layer: v2 specs + edge-aggregate + tight alignment ─────────

# LASSO pool = every scalar below.  Coverage gates nothing here (v3 rule:
# all differentiating features enter the model; regularization decides).
# Missing values are median-imputed exactly as in v2.
V3_EXTRA_SPECS = (
    ("alignment_max_coverage_tight", "alignment_coverage_tight",
     ("max_coverage",), None),
    # anchor orientation deviation (per-endpoint, [0,1])
    ("anchor_orient_dev_mean", "edge_anchor_orientation", ("mean",), None),
    ("anchor_orient_dev_sigma", "edge_anchor_orientation", ("sigma",), None),
    ("anchor_orient_dev_worst", "edge_anchor_orientation", ("worst",), None),
    ("anchor_orient_dev_p75", "edge_anchor_orientation", ("p75",), None),
    # edge mirror consistency (strict caliber; slot = g<->g sub-caliber)
    ("edge_mirror_presence", "edge_mirror", ("presence",), None),
    ("edge_mirror_pair_coverage", "edge_mirror", ("pair_coverage",), None),
    ("edge_mirror_consistency_slot", "edge_mirror", ("consistency_slot",), None),
    ("edge_mirror_consistency_golden", "edge_mirror", ("consistency_golden",), None),
    ("edge_mirror_best_slot", "edge_mirror", ("best_consistency_slot",), None),
    ("edge_mirror_best_golden", "edge_mirror", ("best_consistency_golden",), None),
    # routing regularity (per edge; unitless detour, kink count)
    ("edge_detour_mean", "edge_routing_regularity", ("detour_ratio", "mean"), None),
    ("edge_detour_sigma", "edge_routing_regularity", ("detour_ratio", "sigma"), None),
    ("edge_detour_worst", "edge_routing_regularity", ("detour_ratio", "worst"), None),
    ("edge_detour_p75", "edge_routing_regularity", ("detour_ratio", "p75"), None),
    ("edge_bend_mean", "edge_routing_regularity", ("bend_count", "mean"), None),
    ("edge_bend_sigma", "edge_routing_regularity", ("bend_count", "sigma"), None),
    ("edge_bend_worst", "edge_routing_regularity", ("bend_count", "worst"), None),
    ("edge_bend_p75", "edge_routing_regularity", ("bend_count", "p75"), None),
    # loop closure quality (per closed loop)
    ("loop_arc_share_mean", "edge_loop_closure", ("arc_share", "mean"), None),
    ("loop_arc_share_sigma", "edge_loop_closure", ("arc_share", "sigma"), None),
    ("loop_arc_share_worst", "edge_loop_closure", ("arc_share", "worst"), None),
    ("loop_arc_share_p75", "edge_loop_closure", ("arc_share", "p75"), None),
    ("loop_bow_agree_mean", "edge_loop_closure", ("bow_agreement", "mean"), None),
    ("loop_bow_agree_worst", "edge_loop_closure", ("bow_agreement", "worst"), None),
    ("loop_bow_outward_mean", "edge_loop_closure", ("bow_outward_share", "mean"), None),
    ("loop_bow_outward_worst", "edge_loop_closure", ("bow_outward_share", "worst"), None),
    # style consistency, role-conditioned
    ("loop_arc_rate", "edge_style_consistency", ("loop_arc_rate",), None),
    ("nonloop_straight_rate", "edge_style_consistency", ("nonloop_straight_rate",), None),
)


def v3_scalar_names():
    """Canonical (sorted) pool of v3 scalar names — v2 names + v3 extras."""
    from .aesthetic_score import SCALAR_SPECS
    names = [nm for nm, *_ in SCALAR_SPECS]
    names += [nm for nm, *_ in V3_EXTRA_SPECS]
    return sorted(names)


def extract_scalars_v3(feature_doc, caliber):
    """Feature doc -> {scalar_name: float-or-None} under a caliber (v3 pool)."""
    from .aesthetic_score import SCALAR_SPECS
    if caliber not in CALIBERS:
        raise AestheticError("unknown caliber %r (expected %r)" % (caliber, CALIBERS))
    diagonal = float(feature_doc.get("canvas", {}).get("diagonal") or 0.0)
    counts = feature_doc.get("counts", {})
    out = {}
    for name, key, path, unit in tuple(SCALAR_SPECS) + tuple(V3_EXTRA_SPECS):
        raw = _dig(feature_doc, key, path)
        if raw is None:
            out[name] = None
        elif caliber == "normalized" and unit in ("px", "px2"):
            out[name] = _scale(raw, unit, diagonal)
        else:
            out[name] = raw
    n_nodes = counts.get("nodes")
    out["layout_n_nodes"] = float(n_nodes) if isinstance(n_nodes, int) else None
    return out


def scalars_v3_for_layout(layout_doc, caliber):
    """layout.json dict -> v3 scalar row (features extracted single-source)."""
    return extract_scalars_v3(extract_features(layout_doc), caliber)


def load_dataset_v3(positive_paths, negative_paths, caliber):
    """Read layout JSONs -> (rows_pos, rows_neg, failures), v3 scalar rows."""
    import json
    rows_pos, rows_neg, failures = [], [], []
    for path in positive_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows_pos.append(scalars_v3_for_layout(json.load(f), caliber))
        except Exception as exc:  # noqa: BLE001 - per-file, fail-visible
            failures.append({"path": str(path), "error": str(exc)})
    for path in negative_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows_neg.append(scalars_v3_for_layout(json.load(f), caliber))
        except Exception as exc:  # noqa: BLE001
            failures.append({"path": str(path), "error": str(exc)})
    if not rows_pos or not rows_neg:
        raise AestheticError(
            "v3 dataset incomplete: %d positive / %d negative rows (%d failures)"
            % (len(rows_pos), len(rows_neg), len(failures)))
    return rows_pos, rows_neg, failures


def single_var_auc_table(rows_pos, rows_neg, names):
    """BEFORE arm of the prescreen comparison: the v2-style single-variable
    AUC read on the v3 pool.  Reporting ONLY — nothing is gated on it."""
    names = sorted(names)
    table = {}
    for name in names:
        pos = [r[name] for r in rows_pos if r[name] is not None]
        neg = [r[name] for r in rows_neg if r[name] is not None]
        cov = ((len(pos) + len(neg)) / (len(rows_pos) + len(rows_neg))
               if (rows_pos or rows_neg) else 0.0)
        auc = _auc(pos, neg) if cov > 0 and pos and neg else None
        all_vals = sorted(pos + neg)
        table[name] = {
            "auc": None if auc is None else round(auc, 6),
            "abs_auc_minus_half": None if auc is None else round(abs(auc - 0.5), 6),
            "coverage": round(cov, 6),
            "impute_median": _median(all_vals) if all_vals else 0.0,
            "v2_would_keep": bool(
                auc is not None and cov >= MIN_COVERAGE
                and abs(auc - 0.5) >= 0.30),
        }
    return table


# ───────────────────── deterministic L1 (LASSO) path ─────────────────────

L1_SWEEPS = 150            # fixed coordinate-descent sweeps (no convergence loop)
L1_L2_TINY = 1e-4          # numerical-stability ridge inside the L1 fit
L1_N_LAMBDA = 24           # lambda grid size
L1_EPS_RATIO = 0.01        # lambda_min = lambda_max * EPS_RATIO
L1_CV_FOLDS = 5            # deterministic folds: index % FOLDS over sorted paths


def _soft_threshold(z, t):
    if z > t:
        return z - t
    if z < -t:
        return z + t
    return 0.0


def _l1_fit(vectors, labels, sw, l1):
    """One L1 logistic fit by coordinate descent (deterministic).

    Quadratic-majorization step per coordinate (glmnet-style upper bound):
    w_j <- S(h_j*w_j - g_j, l1) / (h_j + L1_L2_TINY); bias unpenalized
    (stability ridge only).  Fixed sweeps, canonical coordinate order.
    """
    n = len(vectors)
    k = len(vectors[0])
    w = [0.0] * k
    b = 0.0
    xw = [0.0] * n  # running X @ w
    for _ in range(L1_SWEEPS):
        # refresh linear predictor with current w, then sweep coordinates
        for i in range(n):
            xw[i] = math.fsum(vectors[i][j] * w[j] for j in range(k))
        for j in range(k):
            g = L1_L2_TINY * w[j]
            h = L1_L2_TINY
            for i in range(n):
                p = _sigmoid(b + xw[i])
                r = (p - labels[i]) * sw[i]
                g += r * vectors[i][j]
                h += p * (1.0 - p) * sw[i] * vectors[i][j] * vectors[i][j]
            w_new = _soft_threshold(w[j] * h - g, l1) / (h + L1_L2_TINY)
            if w_new != w[j]:
                delta = w_new - w[j]
                for i in range(n):
                    xw[i] += delta * vectors[i][j]
                w[j] = w_new
            # bias step (unpenalized)
            gb = 0.0
            hb = 0.0
            for i in range(n):
                p = _sigmoid(b + xw[i])
                r = (p - labels[i]) * sw[i]
                gb += r
                hb += p * (1.0 - p) * sw[i]
            b -= gb / (hb + L1_L2_TINY)
    return w, b


def _class_weights(labels):
    n = len(labels)
    n_pos = sum(1 for y in labels if y == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        raise AestheticError("LASSO needs both classes")
    w_pos = n / (2.0 * n_pos)
    w_neg = n / (2.0 * n_neg)
    return [w_pos if y == 1 else w_neg for y in labels], n_pos


def _standardize_rows(vectors):
    mean, std = _standardize(vectors)
    out = [[(r[j] - mean[j]) / std[j] for j in range(len(r))] for r in vectors]
    return out, mean, std


def lasso_path(rows_pos, rows_neg, names, impute):
    """Deterministic LASSO path over the full feature pool.

    Returns (path_records, selected) where path_records is a list of
    {lambda, nnz, cv_auc_mean, coefs{feat: coef}} in descending-lambda order,
    and selected = {lambda, cv_auc_mean, kept (sorted names), coefs, bias,
    standardize_mean, standardize_std}.

    Selection rule (fixed a priori, no tuning): maximize mean 5-fold CV AUC
    over the grid; tie-break fewer nonzero coefficients, then larger lambda
    (sparser); overfit guard: nonzero count must not exceed n_pos (the same
    ceiling v2 enforced prescreen-side) — walk to the sparsest satisfying
    lambda if needed.
    """
    names = sorted(names)
    vecs = _design_rows(rows_pos, names, impute) + \
        _design_rows(rows_neg, names, impute)
    labels = [1] * len(rows_pos) + [0] * len(rows_neg)
    sw, n_pos = _class_weights(labels)
    z, mean, std = _standardize_rows(vecs)

    # lambda_max: max |gradient| at w = 0 (b = class-odds offset ignored;
    # conservative larger grid start)
    lmax = 0.0
    for j in range(len(names)):
        g = math.fsum(sw[i] * (0.5 - labels[i]) * z[i][j]
                      for i in range(len(z)))
        lmax = max(lmax, abs(g))
    if lmax <= 0:
        raise AestheticError("LASSO lambda_max degenerate (zero gradient)")
    grid = [lmax * (L1_EPS_RATIO ** (i / (L1_N_LAMBDA - 1)))
            for i in range(L1_N_LAMBDA)]  # descending

    # deterministic CV fold assignment over sorted sample order
    order = list(range(len(z)))  # callers pass rows sorted by path
    folds = [i % L1_CV_FOLDS for i in order]

    def fit_chain(rows_idx):
        w = [0.0] * len(names)
        b = 0.0
        labels_sub = [labels[i] for i in rows_idx]
        sw_sub = [sw[i] for i in rows_idx]
        out = []
        for lam in grid:
            vecs_sub = [z[i] for i in rows_idx]
            w, b = _l1_fit(vecs_sub, labels_sub, sw_sub, lam) \
                if not out else _l1_fit_warm(vecs_sub, labels_sub, sw_sub, lam, w, b)
            out.append((lam, list(w), b))
        return out

    full_chain = fit_chain(order)

    # fold chains computed ONCE (warm-started along the grid), read per lambda
    fold_chains = []
    for f in range(L1_CV_FOLDS):
        tr = [i for i in order if folds[i] != f]
        va = [i for i in order if folds[i] == f]
        fold_chains.append((fit_chain(tr) if tr else None, va))

    def cv_auc_for(lam_idx):
        aucs = []
        for chain, va in fold_chains:
            if not chain or not va:
                continue
            lam, w, b = chain[lam_idx]
            pos_s, neg_s = [], []
            for i in va:
                s = b + math.fsum(z[i][j] * w[j] for j in range(len(names)))
                (pos_s if labels[i] == 1 else neg_s).append(s)
            aucs.append(_auc(pos_s, neg_s) if pos_s and neg_s else 0.5)
        return math.fsum(aucs) / len(aucs) if aucs else 0.5

    path_records = []
    for idx, (lam, w, b) in enumerate(full_chain):
        nnz = sum(1 for v in w if abs(v) > 1e-9)
        path_records.append({
            "lambda": lam,
            "nnz": nnz,
            "cv_auc_mean": round(cv_auc_for(idx), 6),
            "coefs": {nm: round(w[j], 9)
                      for j, nm in enumerate(names) if abs(w[j]) > 1e-9},
        })

    best0 = max(range(len(path_records)),
                key=lambda i: (path_records[i]["cv_auc_mean"],
                               -path_records[i]["nnz"],
                               path_records[i]["lambda"]))
    best = best0
    # overfit guard: walk sparser while nnz > n_pos
    guard_applied = False
    while path_records[best]["nnz"] > n_pos and best > 0:
        best -= 1
        guard_applied = True
    lam, w, b = full_chain[best]
    kept = [nm for j, nm in enumerate(names) if abs(w[j]) > 1e-9]
    selected = {
        "lambda": lam,
        "path_index": best,
        "cv_auc_mean": path_records[best]["cv_auc_mean"],
        "kept": sorted(kept),
        "coefs": {nm: round(w[j], 9) for j, nm in enumerate(names)
                  if abs(w[j]) > 1e-9},
        "bias": round(b, 9),
        "standardize_mean": [round(m, 9) for m in mean],
        "standardize_std": [round(s, 9) for s in std],
        "overfit_guard_applied": guard_applied,
        "rule": ("max mean CV-AUC over grid; tie-break nnz asc then lambda "
                 "desc; nnz capped at n_pos=%d" % n_pos),
    }
    return path_records, selected


def _l1_fit_warm(vectors, labels, sw, l1, w, b):
    """L1 fit warm-started from (w, b) — same coordinate descent."""
    n = len(vectors)
    k = len(vectors[0])
    xw = [0.0] * n
    for _ in range(L1_SWEEPS):
        for i in range(n):
            xw[i] = math.fsum(vectors[i][j] * w[j] for j in range(k))
        for j in range(k):
            g = L1_L2_TINY * w[j]
            h = L1_L2_TINY
            for i in range(n):
                p = _sigmoid(b + xw[i])
                r = (p - labels[i]) * sw[i]
                g += r * vectors[i][j]
                h += p * (1.0 - p) * sw[i] * vectors[i][j] * vectors[i][j]
            w_new = _soft_threshold(w[j] * h - g, l1) / (h + L1_L2_TINY)
            if w_new != w[j]:
                delta = w_new - w[j]
                for i in range(n):
                    xw[i] += delta * vectors[i][j]
                w[j] = w_new
            gb = 0.0
            hb = 0.0
            for i in range(n):
                p = _sigmoid(b + xw[i])
                r = (p - labels[i]) * sw[i]
                gb += r
                hb += p * (1.0 - p) * sw[i]
            b -= gb / (hb + L1_L2_TINY)
    return w, b


# ───────────── shape-conditional calibration on the LASSO kept set ─────────────

# ring keeps the v2 operator directive: alignment coverage must not weigh
# ring layouts — extended to the tight-caliber sibling key.
V3_SHAPE_EXCLUDED = {
    SHAPE_RING: tuple(SHAPE_EXCLUDED_FEATURES[SHAPE_RING]) +
                ("alignment_max_coverage_tight",),
    SHAPE_HUB: tuple(SHAPE_EXCLUDED_FEATURES[SHAPE_HUB]),
    SHAPE_GLOBAL: tuple(SHAPE_EXCLUDED_FEATURES[SHAPE_GLOBAL]),
}


def calibrate_shape_v3(pos_records, neg_records, labels, kept):
    """Fit per-shape L2 logistic models on the LASSO-kept feature set.

    pos_records/neg_records: [(path, graph, row)] — routing identical to v2
    (route_shape on the same row keys).  Returns (model_v3, stats).
    """
    models = {}
    stats = {"shapes": {}}
    buckets = {}
    for p, g, row in pos_records:
        buckets.setdefault(route_shape(g, row, labels), ([], []))[0].append((p, row))
    for p, g, row in neg_records:
        buckets.setdefault(route_shape(g, row, labels), ([], []))[1].append((p, row))
    for shape in (SHAPE_RING, SHAPE_HUB, SHAPE_GLOBAL):
        pos_b, neg_b = buckets.get(shape, ([], []))
        names = [nm for nm in kept if nm not in V3_SHAPE_EXCLUDED[shape]]
        if not names:
            raise AestheticError("empty v3 feature set for shape %r" % shape)
        rows_pos = [row for _p, row in pos_b]
        rows_neg = [row for _p, row in neg_b]
        impute = {}
        for nm in names:
            vals = sorted([r[nm] for r in rows_pos + rows_neg if r[nm] is not None])
            impute[nm] = _median(vals) if vals else 0.0
        model = {
            "names": list(names),
            "impute_median": {nm: round(impute[nm], 9) for nm in names},
            "caliber": "normalized",
            "schema": MODEL_SCHEMA_V3,
        }
        fitted = bool(rows_pos) and len(rows_pos) >= 3
        if fitted:
            vecs = _design_rows(rows_pos, names, impute) + \
                _design_rows(rows_neg, names, impute)
            fit = fit_logistic(vecs, [1] * len(rows_pos) + [0] * len(rows_neg),
                               names)
            model.update(fit)
            model.pop("schema", None)  # fit_logistic has no schema key
            model["schema"] = MODEL_SCHEMA_V3
            model["fit_sample_counts"] = {"positive": len(rows_pos),
                                          "negative": len(rows_neg)}
            pos_scores = [score_row(model, r) for r in rows_pos]
            neg_scores = [score_row(model, r) for r in rows_neg]
            st = {
                "fitted": True,
                "n_positive": len(rows_pos),
                "n_negative": len(rows_neg),
                "score_auc": round(_auc(pos_scores, neg_scores), 6),
                "positive_scores_min": min(pos_scores),
                "positive_scores_mean": round(
                    math.fsum(pos_scores) / len(pos_scores), 1),
                "positive_scores_max": max(pos_scores),
                "negative_scores_max": max(neg_scores),
                "negative_scores_mean": round(
                    math.fsum(neg_scores) / len(neg_scores), 1),
                "negative_scores_min": min(neg_scores),
                "separation_margin": round(min(pos_scores) - max(neg_scores), 1),
                "excluded_features": list(V3_SHAPE_EXCLUDED[shape]),
                "kept_features": list(names),
            }
            model["human_lower_bound"] = min(pos_scores)
        else:
            # v2 convention: <3 positives -> not fitted, global fallback
            st = {"fitted": False, "n_positive": len(rows_pos),
                  "n_negative": len(rows_neg),
                  "note": "below MIN_SHAPE_POSITIVE; global fallback"}
        models[shape] = model
        stats["shapes"][shape] = st
    # global model fitted on everything (fallback + absolute caliber carrier)
    names = [nm for nm in kept if nm not in V3_SHAPE_EXCLUDED[SHAPE_GLOBAL]]
    all_pos = [row for recs, _n in
               [buckets.get(s, ([], [])) for s in (SHAPE_RING, SHAPE_HUB,
                                                   SHAPE_GLOBAL)]
               for _p, row in recs]
    all_neg = [row for _r, recs in
               [buckets.get(s, ([], [])) for s in (SHAPE_RING, SHAPE_HUB,
                                                   SHAPE_GLOBAL)]
               for _p, row in recs]
    impute = {}
    for nm in names:
        vals = sorted([r[nm] for r in all_pos + all_neg if r[nm] is not None])
        impute[nm] = _median(vals) if vals else 0.0
    model = {
        "names": list(names),
        "impute_median": {nm: round(impute[nm], 9) for nm in names},
        "caliber": "normalized",
        "schema": MODEL_SCHEMA_V3,
        "fit_sample_counts": {"positive": len(all_pos), "negative": len(all_neg)},
    }
    vecs = _design_rows(all_pos, names, impute) + _design_rows(all_neg, names, impute)
    fit = fit_logistic(vecs, [1] * len(all_pos) + [0] * len(all_neg), names)
    model.update(fit)
    model["schema"] = MODEL_SCHEMA_V3
    models["global"] = model
    pos_scores = [score_row(model, r) for r in all_pos]
    neg_scores = [score_row(model, r) for r in all_neg]
    stats["shapes"]["global"] = {
        "fitted": True,
        "n_positive": len(all_pos),
        "n_negative": len(all_neg),
        "score_auc": round(_auc(pos_scores, neg_scores), 6),
        "separation_margin": round(min(pos_scores) - max(neg_scores), 1),
        "positive_scores_min": min(pos_scores),
        "negative_scores_max": max(neg_scores),
        "kept_features": list(names),
    }
    return {"models": models, "schema": MODEL_SCHEMA_V3,
            "kind": "aesthetic-model-v3-alpha"}, stats


def score_row_v3(model_v3, graph, row, labels):
    """Route + score one row with a v3 model (v2 routing caliber)."""
    shape = route_shape(graph, row, labels)
    m = model_v3["models"].get(shape) or model_v3["models"]["global"]
    return score_row(m, row), shape
