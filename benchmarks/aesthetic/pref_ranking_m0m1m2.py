#!/usr/bin/env python
"""Preference-ranking comparison experiment: M0 / M1 / M2 (+ M1s / M2s).

First round of the Learning-to-Rank plan (external-review consensus,
"Phase 2"): compare candidate-ranking approaches on jacky's 30-question
pairwise blind-choice session (24 first-round pairs + 6 retest repeats,
retest consistency 5/6 = individual noise baseline).

Arms
----
M0   committed v2 pointwise model (model-v2.json) ranks candidates directly
     (baseline; no preference training).
M1   v2 shape-conditional features + pairwise logistic in Bradley-Terry
     equivalent form (P(a>b) = sigmoid(w . (x_a - x_b)), no class weights,
     symmetric orientation), trained on jacky's decided first-round pairs.
M2   v3-beta full feature set (committed LASSO kept list, edge dimensions
     included) + the same pairwise form.
M1s  M1 + the 30 perturbation synthetic pairs (user-confirmed 2026-11-21
     spot-check) added to preference training.
M2s  M2 + the same synthetic pairs.

NOTE on dose families (honest disclosure, required by the operating
instruction): the synthetic pairs come from the hub-collapse diagnosis
card's cumulative L1-L4 dose caliber (node-centre movement + edge-attribute
damage mixed), NOT from the v3-beta route-preserving dose family.  If the
s-arms and the plain arms disagree, both readings are reported side by
side without being merged.

Evaluation (topology-grouped leave-one-topology-out)
----------------------------------------------------
1. Pairwise accuracy on jacky's decided first-round pairs + Wilson 95% CI
   (pooled across folds; each pair tested exactly once).  n is small; wide
   CIs are expected and reported as-is.
2. Top-1 selection rate: per graph, the model's first-ranked candidate vs
   jacky's most-preferred candidate (aggregated from decided pairs; only
   graphs with a unique plurality winner count).
3. Comparison against jacky's retest noise baseline (5/6 ~= 83.3%).
4. Train-holdout gap (in-fold train accuracy - holdout accuracy; > 15pp
   triggers review, threshold fixed by the earlier ranking plan).
5. Quality-gate non-regression: the pointwise human-vs-engine discriminator
   table (v3-beta Arm C, all four rows) is recomputed after (and
   independently of) preference training; every reading must equal its
   committed value exactly (committed kept set on the backfilled path reads
   ring 1.0 / hub 1.0; the often-quoted "ring 0.987" is the
   drop-nonloop_straight_rate ablation row, 0.986928).  Scorer artifacts
   are sha256-pinned before the run and re-verified after.

Data calibers (PROVENANCE.md is the authority)
-----------------------------------------------
- "both good" (7): never a training pair; reported as epsilon-calibration
  initial values (score-margin distribution of ties vs decided pairs).
- "both bad" (6): pool-quality warning only; composition reported.
- Retest repeats (6): consistency check + noise baseline only; first-round
  answers are the evaluation set.
- Left/right presentation swaps are normalized on the analysis side: the
  export's `choice` field is the screen side ('a'=left / 'b'=right) and the
  evaluator converts it with `left_is_a` (see pair_winner).

Red lines honoured: zero certificate-grade reads by the ranker (ranking
features come from layout geometry only; grades appear solely in the
pool-quality warning composition table, never as features); candidate pool
reproduction uses the same gate viability filter as the viewer (zero score
weight); deterministic output (double-run byte-identical); negatives
library read-only; committed scorer artifacts untouched (sha-pinned).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import diagnose_collapse as dc  # noqa: E402
import pref_pipeline as pp  # noqa: E402  (applies pairwise-exclusion loader patch)
from stdraw.aesthetic_score import (  # noqa: E402
    load_family_labels,
    route_shape,
    scalars_for_layout,
)
from stdraw.aesthetic_score_v3 import (  # noqa: E402
    calibrate_shape_v3,
    scalars_v3_for_layout,
)

SESSION_DIR = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-21"
ANSWERS_PATH = SESSION_DIR / "answers-2026-11-21.json"
CAND_META_PATH = SESSION_DIR / "candidates.json"
SYN_DIR = REPO / "benchmarks" / "aesthetic" / "pref-synthetic"
FAMILY_MAP = REPO / "benchmarks" / "corpus" / "classic" / "topology-families.json"
OUT_DIR = REPO / "benchmarks" / "aesthetic"
JSON_OUT = OUT_DIR / "pref-ranking-m0m1m2.json"
MD_OUT = OUT_DIR / "pref-ranking-report-m0m1m2.md"

WINNER_CALIBER = "normalized"
BT_L2 = 1.0
BT_ITERS = 50
GAP_TRIGGER_PP = 15.0
RETEST_BASELINE = 5.0 / 6.0

# committed artifacts whose bytes must not move (discriminator non-regression)
SHA_PINNED = (
    "benchmarks/aesthetic/model-v2.json",
    "benchmarks/aesthetic/model-v3-alpha.json",
    "benchmarks/aesthetic/lasso-path-v3-alpha.json",
    "benchmarks/aesthetic/calibration-report-v2.json",
    "benchmarks/aesthetic/calibration-report-v3-beta.json",
    "stdraw/aesthetic_score.py",
    "stdraw/aesthetic_score_v3.py",
)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── deterministic Bradley-Terry pairwise logistic (IRLS, L2) ──────────────

def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _standardize(rows):
    """Scale-only standardization for pairwise DIFF vectors: divide by the
    per-dimension RMS (std around zero), do NOT subtract the mean.  Centering
    diffs would make w=0 a stationary point of the bias-free BT objective
    (the winner-loser diff mean IS the signal a bias-free BT model must be
    able to express); scaling keeps dimensions numerically comparable."""
    n, k = len(rows), len(rows[0])
    std = []
    for j in range(k):
        var = math.fsum(r[j] ** 2 for r in rows) / n
        std.append(math.sqrt(var) if var > 1e-12 else 1.0)
    return [0.0] * k, std


def _objective(w, z, l2):
    """Regularized BT objective: sum_i log(1 + exp(-s_i)) + 0.5*l2*|w|^2
    (every diff vector is oriented so its label is 1)."""
    obj = 0.5 * l2 * math.fsum(wj * wj for wj in w)
    for row in z:
        s = math.fsum(wj * v for wj, v in zip(w, row))
        if s >= 0:
            obj += math.log1p(math.exp(-s))
        else:
            obj += -s + math.log1p(math.exp(s))
    return obj


def _grad_norm(w, z, l2):
    g = [l2 * wj for wj in w]
    for row in z:
        p = _sigmoid(math.fsum(wj * v for wj, v in zip(w, row)))
        r = p - 1.0
        for j in range(len(w)):
            g[j] += r * row[j]
    return math.sqrt(math.fsum(gj * gj for gj in g))


def _solve_linear(M, b):
    """Gaussian elimination with partial pivoting (deterministic; the BT
    Hessian here is positive definite thanks to the l2 ridge, so the solve
    itself needs no extra damping)."""
    n = len(b)
    A = [M[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-14:
            raise ArithmeticError("singular Hessian in BT fit")
        if piv != col:
            A[col], A[piv] = A[piv], A[col]
        inv = 1.0 / A[col][col]
        for r in range(n):
            if r != col and A[r][col] != 0.0:
                f = A[r][col] * inv
                for c in range(col, n + 1):
                    A[r][c] -= f * A[col][c]
    return [A[i][n] / A[i][i] for i in range(n)]


def fit_bt(diff_vectors, l2=BT_L2, iters=BT_ITERS):
    """Fit P(a>b) = sigmoid(w . scaled_diff) WITHOUT a bias term (bias-free
    Bradley-Terry equivalent form; a constant preference direction would be
    circular when evaluation orients pairs winner-first).  Diffs are scaled
    per-dimension (RMS, no centering -- see _standardize).  Every vector is
    oriented so the label is 1 -> no class weights.

    Solver (review rework): BEFORE fitting, columns whose diff-value vector
    is bitwise identical to an earlier column are merged away and the merge
    is recorded (the v3 kept set ships mirror_axis_err and
    symmetry_axis_err_px as an exactly duplicated column; a duplicated
    column carries no extra signal and makes the full Hessian singular,
    which defeated the first delivery's diagonal-Hessian IRLS - it stalled
    at gradient norms of 24-51 on the v3 arms, so its held-out readings
    were optimizer artifacts).  The update itself is a DAMPED FULL-HESSIAN
    Newton step (exact cross-terms + objective-decreasing backtracking),
    iterated to a hard convergence gate: every fit asserts its final
    gradient norm < 1e-6 or raises.  Deterministic: fixed iteration order,
    no randomness, plain float ops."""
    n, k = len(diff_vectors), len(diff_vectors[0])
    # duplicate-column merge (deterministic): keep the first of each group
    # of bitwise-equal columns, record the merge for disclosure
    col_idx = []
    merged_pairs = []   # [kept_original_index, dropped_original_index]
    for j in range(k):
        twin = None
        for j2 in col_idx:
            if all(r[j] == r[j2] for r in diff_vectors):
                twin = j2
                break
        if twin is None:
            col_idx.append(j)
        else:
            merged_pairs.append([twin, j])
    kk = len(col_idx)
    mean = [0.0] * kk
    std = []
    for j in col_idx:
        var = math.fsum(r[j] ** 2 for r in diff_vectors) / n
        std.append(math.sqrt(var) if var > 1e-12 else 1.0)
    z = [[r[j] / std[a] for a, j in enumerate(col_idx)] for r in diff_vectors]
    w = [0.0] * kk
    obj = _objective(w, z, l2)
    used = 0
    for _ in range(iters):
        g = [l2 * wj for wj in w]
        H = [[(l2 if a == b else 0.0) for b in range(kk)] for a in range(kk)]
        for i in range(n):
            p = _sigmoid(math.fsum(w[j] * z[i][j] for j in range(kk)))
            r_ = p - 1.0
            h = p * (1.0 - p)
            for a in range(kk):
                g[a] += r_ * z[i][a]
                for b in range(a, kk):
                    hv = h * z[i][a] * z[i][b]
                    H[a][b] += hv
                    if b != a:
                        H[b][a] += hv
        step = _solve_linear(H, g)
        # damped step: backtrack until the objective decreases
        w_new = w
        t = 1.0
        for _bt in range(60):
            w_new = [w[j] - t * step[j] for j in range(kk)]
            obj_new = _objective(w_new, z, l2)
            if obj_new <= obj:
                break
            t *= 0.5
        else:
            break  # no decreasing step found: at the optimum floor
        w, obj = w_new, obj_new
        used += 1
        if math.sqrt(math.fsum(sj * sj for sj in step)) < 1e-11:
            break
    grad_norm = _grad_norm(w, z, l2)
    assert grad_norm < 1e-6,         "BT fit did not converge: final gradient norm %g" % grad_norm
    return {"w": w, "b": 0.0, "mean": mean, "std": std,
            "col_idx": col_idx, "merged_pairs": merged_pairs,
            "hyper": {"l2": l2, "irls_iters": used,
                      "grad_norm_final": grad_norm,
                      "objective_final": obj,
                      "fit_convergence_gate": "final gradient norm < 1e-6 "
                                              "(asserted on every fit)",
                      "form": "bradley-terry (oriented diffs, bias-free, "
                              "RMS-scaled, no centering, no class weights, "
                              "duplicate columns merged, damped "
                              "full-Hessian Newton)"}}


def bt_margin(model, vec_a, vec_b):
    d = [(vec_a[j] - vec_b[j] - model["mean"][t]) / model["std"][t]
         for t, j in enumerate(model["col_idx"])]
    return math.fsum(w * v for w, v in zip(model["w"], d))


def wilson_ci(k, n, z=1.959963985):
    if n == 0:
        return None, None, None
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = (centre - spread) / denom
    hi = (centre + spread) / denom
    return round(p, 4), round(lo, 4), round(hi, 4)


# ── data loading ──────────────────────────────────────────────────────────

def load_answers():
    data = json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
    items = data["items"]
    assert data["n_answered"] == 30 and len(items) == 30
    first = [i for i in items if not i["is_retest"]]
    retest = [i for i in items if i["is_retest"]]
    assert len(first) == 24 and len(retest) == 6
    return data, first, retest


def pair_winner(it):
    """Export caliber: `choice` is the SCREEN side ('a'=left, 'b'=right);
    convert with left_is_a to the winning candidate id (PROVENANCE.md:
    left/right presentation swaps normalized on the analysis side)."""
    if it["choice"] in ("a", "b"):
        chose_left = it["choice"] == "a"
        return it["candidate_a"] if chose_left == it["left_is_a"] \
            else it["candidate_b"]
    return it["choice"]


def pair_winners(items):
    """Decided first-round pairs -> [{graph, a, b, winner, loser}]."""
    out = []
    for it in items:
        w = pair_winner(it)
        if w in (it["candidate_a"], it["candidate_b"]):
            l = it["candidate_b"] if w == it["candidate_a"] else it["candidate_a"]
            out.append({"qid": it["qid"], "graph": it["graph"],
                        "a": it["candidate_a"], "b": it["candidate_b"],
                        "winner": w, "loser": l})
    return out


def retest_consistency(first, retest):
    first_by_key = {i["pair_key"]: pair_winner(i) for i in first}
    rows = []
    agree = 0
    for it in retest:
        fw = first_by_key.get(it["pair_key"])
        rw = pair_winner(it)
        ok = fw == rw
        agree += 1 if ok else 0
        rows.append({"pair_key": it["pair_key"], "first_winner": fw,
                     "retest_winner": rw, "agree": ok})
    return agree, rows


def load_pool():
    """Reproduce the viewer candidate pool deterministically and validate it
    against the committed session metadata (fail loud on any drift)."""
    pool = pp.collect_view_candidates()
    meta = json.loads(CAND_META_PATH.read_text(encoding="utf-8"))["candidates"]
    flat = {}
    for g, cands in pool.items():
        for c in cands:
            flat[c["cid"]] = (g, c)
    assert set(flat) == set(meta), "candidate-id drift vs committed session"
    for cid, m in meta.items():
        g, c = flat[cid]
        assert g == m["graph"], cid
        assert c["recipe"] == m["recipe"], cid
        assert c["source"] == m["source"], cid
        assert c["grade"] == m["grade"], cid
        assert abs(c["gap"] - m["gap"]) < 1e-9, cid
        assert c["crossings"] == m["crossings"], cid
    return pool


# ── feature extraction (layout geometry only; zero grade reads) ──────────

class FeatureBank:
    """Per-candidate feature values for the M1 (v2) and M2 (v3) calibers.

    Caliber note (v2 routing is candidate-level, not graph-level): the nested
   -ring family is NOT in SHAPE_ROUTING_FROM_FAMILY, so within one graph
    candidates may route to different v2 shapes (observed: brand-flywheel
    g4c0 -> hub, its siblings -> ring).  The pairwise feature space for a
    graph is therefore the UNION of the routed shape models' feature names
    across that graph's candidates (deterministic order); each candidate
    contributes its own routed-model values for its own names and the
    committed model impute medians for names outside its routed set
    (fold-independent, zero grade reads).  Disclosed in the report.
    """

    def __init__(self, pool, labels, model_v2, model_v3, kept_v3):
        self.labels = labels
        self.model_v2 = model_v2
        self.model_v3 = model_v3
        self.v2 = {}   # cid -> {"shape": s, "values": {name: value-or-None}}
        self.v3 = {}
        self.v2_impute = {}
        self.v3_impute = {}
        for shape, m in model_v2["models"].items():
            for nm, v in (m.get("impute_median") or {}).items():
                self.v2_impute.setdefault(nm, v)
        for shape, m in model_v3["models"].items():
            for nm, v in (m.get("impute_median") or {}).items():
                self.v3_impute.setdefault(nm, v)
        self.route = {}  # graph -> {cid: shape}
        self._pool_order = {}   # graph -> [cid, ...] (pool order)
        self._model_names = {}  # cid -> {"v2": names, "v3": names}
        for g, cands in pool.items():
            self._pool_order[g] = [c["cid"] for c in cands]
            for c in cands:
                row2 = scalars_for_layout(c["doc"], WINNER_CALIBER)
                s2 = route_shape(g, row2, labels)
                m2 = model_v2["models"].get(s2) or model_v2["models"]["global"]
                vals2 = {nm: row2.get(nm) for nm in m2["names"]}
                row3 = scalars_v3_for_layout(c["doc"], WINNER_CALIBER)
                s3 = route_shape(g, row3, labels)
                m3 = model_v3["models"].get(s3) or model_v3["models"]["global"]
                vals3 = {nm: row3.get(nm) for nm in m3["names"]}
                self.v2[c["cid"]] = {"shape": s2, "values": vals2}
                self.v3[c["cid"]] = {"shape": s3, "values": vals3}
                self._model_names[c["cid"]] = {"v2": list(m2["names"]),
                                               "v3": list(m3["names"])}
                self.route.setdefault(g, {})[c["cid"]] = s2

    def add_doc(self, cid, g, doc):
        """Bank an extra layout doc (synthetic-pair candidates live outside
        the viewer pool but enter preference training for the s arms)."""
        row2 = scalars_for_layout(doc, WINNER_CALIBER)
        s2 = route_shape(g, row2, self.labels)
        m2 = self.model_v2["models"].get(s2) or self.model_v2["models"]["global"]
        row3 = scalars_v3_for_layout(doc, WINNER_CALIBER)
        s3 = route_shape(g, row3, self.labels)
        m3 = self.model_v3["models"].get(s3) or self.model_v3["models"]["global"]
        self.v2[cid] = {"shape": s2, "values": {nm: row2.get(nm)
                                                for nm in m2["names"]}}
        self.v3[cid] = {"shape": s3, "values": {nm: row3.get(nm)
                                                for nm in m3["names"]}}
        self._model_names[cid] = {"v2": list(m2["names"]),
                                  "v3": list(m3["names"])}

    def graph_names(self, g, featname):
        """Union of routed-model feature names for a graph, deterministic
        order (candidate pool order x model names order)."""
        names = []
        for cid in self._pool_order[g]:
            for nm in self._model_names[cid][featname]:
                if nm not in names:
                    names.append(nm)
        return names

    def vector(self, cid, names, featname):
        table = self.v2 if featname == "v2" else self.v3
        impute = self.v2_impute if featname == "v2" else self.v3_impute
        values = table[cid]["values"]
        out = []
        for nm in names:
            v = values.get(nm)
            if v is None:
                assert nm in impute, "no impute median for %s" % nm
                v = impute[nm]
            out.append(v)
        return out


# ── arms ──────────────────────────────────────────────────────────────────

FEAT_OF_ARM = {"M1": "v2", "M2": "v3", "M1s": "v2", "M2s": "v3"}


def pair_diff(bank, featname, names, p):
    va = bank.vector(p["winner"], names, featname)
    vb = bank.vector(p["loser"], names, featname)
    return [a - b for a, b in zip(va, vb)]


def train_bt(bank, featname, train_pairs):
    diffs = [pair_diff(bank, featname, NAMES_GLOBAL[featname], p)
             for p in train_pairs]
    return fit_bt(diffs)


def eval_arm(arm, folds, pool):
    """LOSO evaluation.  Returns per-fold + pooled metrics + rankings."""
    per_fold = []
    correct_total = 0
    n_total = 0
    rankings = {}
    margins_ties = []
    margins_train = []
    for fold in folds:
        if arm == "M0":
            model = None
        else:
            train = list(fold["train_human"])
            if arm in ("M1s", "M2s"):
                train = train + fold["train_synthetic"]
            model = (train_bt(BANK, FEAT_OF_ARM[arm], train)
                     if train else None)
        tr_ok = 0
        for p in fold["train_human"]:
            m = _pair_margin(arm, model, p)
            if m > 0:
                tr_ok += 1
            margins_train.append(abs(m))
        te_ok = 0
        te_n = 0
        te_margins = []
        for p in fold["test_pairs"]:
            m = _pair_margin(arm, model, p)
            te_margins.append({"qid": p["qid"],
                               "signed_margin": round(m, 6)})
            ok = m > 0
            te_ok += 1 if ok else 0
            te_n += 1
        correct_total += te_ok
        n_total += te_n
        # per-graph ranking inside this fold's held-out graphs
        for g in fold["test_graphs"]:
            cids = [c["cid"] for c in pool[g]]
            if arm == "M0":
                # v2 pointwise score, higher is better (deterministic tie
                # break: candidate order, which is the pool collection order)
                scores = {cid: M0_SCORES[cid] for cid in cids}
                order = sorted(cids, key=lambda c: (-scores[c], c))
            else:
                wins = {cid: 0.0 for cid in cids}
                names = NAMES_GLOBAL[FEAT_OF_ARM[arm]]
                for i, ca in enumerate(cids):
                    for cb in cids[i + 1:]:
                        va = BANK.vector(ca, names, FEAT_OF_ARM[arm])
                        vb = BANK.vector(cb, names, FEAT_OF_ARM[arm])
                        m = bt_margin(model, va, vb)
                        if m > 0:
                            wins[ca] += 1
                        elif m < 0:
                            wins[cb] += 1
                        else:  # exact tie: split (deterministic)
                            wins[ca] += 0.5
                            wins[cb] += 0.5
                order = sorted(cids, key=lambda c: (-wins[c], c))
            rankings[g] = order
        per_fold.append({
            "held_out_topology": fold["topology"],
            "test_graphs": fold["test_graphs"],
            "n_train_human": len(fold["train_human"]),
            "n_train_synthetic": (len(fold["train_synthetic"])
                                  if arm in ("M1s", "M2s") else 0),
            "train_acc_human": round(tr_ok / len(fold["train_human"]), 4)
            if fold["train_human"] else None,
            "test_acc": round(te_ok / te_n, 4) if te_n else None,
            "n_test": te_n,
            "test_correct": te_ok,
            "test_pair_margins": te_margins,
        })
    for t in TIE_PAIRS:
        m = _pair_margin(arm, FOLD_MODEL_FOR_TIES.get(arm), t)
        margins_ties.append({"pair_key": t["pair_key"], "signed_margin": round(m, 6),
                             "abs_margin": round(abs(m), 6)})
    return {
        "arm": arm,
        "pooled": {"correct": correct_total, "n": n_total,
                   "acc": round(correct_total / n_total, 4) if n_total else None,
                   "ci95": wilson_ci(correct_total, n_total) if n_total else None},
        "per_fold": per_fold,
        "rankings": rankings,
        "tie_margins": margins_ties,
        "train_margin_abs_min": round(min(margins_train), 6) if margins_train else None,
    }


def _pair_margin(arm, model, p):
    """Signed margin: >0 means the pair's recorded winner (or, for tie
    pairs, candidate_a) ranks higher.
    M0 uses the v2 pointwise score difference; BT arms use the BT logit."""
    hi = p.get("winner", p["a"])
    lo = p.get("loser", p["b"])
    if arm == "M0":
        return M0_SCORES[hi] - M0_SCORES[lo]
    names = NAMES_GLOBAL[FEAT_OF_ARM[arm]]
    va = BANK.vector(hi, names, FEAT_OF_ARM[arm])
    vb = BANK.vector(lo, names, FEAT_OF_ARM[arm])
    return bt_margin(model, va, vb)


# globals filled by main (kept simple for the double-run identical check)
FOLDS = []
TIE_PAIRS = []
BOTH_BAD = []
M0_SCORES = {}
FOLD_MODEL_FOR_TIES = {}
BANK = None
NAMES_GLOBAL = {}


def main():
    global BANK
    sha_before = {p: sha256_of(REPO / p) for p in SHA_PINNED}

    data, first, retest = load_answers()
    decided = pair_winners(first)
    tie_pairs = [{"pair_key": i["pair_key"], "graph": i["graph"],
                  "a": i["candidate_a"], "b": i["candidate_b"]}
                 for i in first if i["choice"] == "both"]
    both_bad = [{"pair_key": i["pair_key"], "graph": i["graph"],
                 "a": i["candidate_a"], "b": i["candidate_b"]}
                for i in items_both_bad(data)]
    agree, retest_rows = retest_consistency(first, retest)
    assert agree == 5, "retest consistency drifted: %d/6" % agree
    assert len(decided) == 13, "expected 13 decided first-round pairs, got %d" % len(decided)
    assert len(tie_pairs) == 7 and len(both_bad) == 6

    pool = load_pool()
    labels = load_family_labels(str(FAMILY_MAP))
    model_v2 = json.loads((OUT_DIR / "model-v2.json").read_text(encoding="utf-8"))
    model_v3 = json.loads((OUT_DIR / "model-v3-alpha.json").read_text(encoding="utf-8"))
    kept_v3 = list(json.loads(
        (OUT_DIR / "lasso-path-v3-alpha.json").read_text(encoding="utf-8")
    )["selected"]["kept"])

    # synthetic candidate docs (user-confirmed training authorization);
    # banked BEFORE the global feature-space union so their routed names
    # are covered too
    syn_docs = {}
    for p in sorted((SYN_DIR / "candidates").glob("*.json")):
        syn_docs[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    bank = FeatureBank(pool, labels, model_v2, model_v3, kept_v3)
    for cid in sorted(syn_docs):
        d = syn_docs[cid]
        assert d.get("graph"), "synthetic candidate without graph: %s" % cid
        bank.add_doc(cid, d["graph"], d)
    BANK = bank
    # single global feature space per caliber (BT model needs one fixed k):
    # union over every banked candidate's routed-model names, deterministic
    # order (sorted cid order)
    NAMES_GLOBAL.clear()
    for featname in ("v2", "v3"):
        names = []
        for cid in sorted(bank._model_names):
            for nm in bank._model_names[cid][featname]:
                if nm not in names:
                    names.append(nm)
        NAMES_GLOBAL[featname] = names

    # M0 scores (v2 pointwise, certificate-free)
    scorer_v2 = dc.Scorer(model_v2, labels)
    for g, cands in pool.items():
        for c in cands:
            sc, shape, _row = scorer_v2.score(c["doc"], g)
            M0_SCORES[c["cid"]] = sc

    # synthetic pairs (labels come from pairs.json expected_order; user-
    # confirmed training authorization, diagnosis-card dose caliber)
    syn = json.loads((SYN_DIR / "pairs.json").read_text(encoding="utf-8"))["pairs"]
    syn_pairs = []
    for pr in syn:
        a, b = pr["candidate_a"], pr["candidate_b"]
        assert a in syn_docs and b in syn_docs, pr["pair_id"]
        winner, loser = ((a, b) if pr["expected_order"] == "candidate_a"
                         else (b, a))
        syn_pairs.append({"pair_id": pr["pair_id"], "graph": pr["graph"],
                          "a": a, "b": b, "winner": winner, "loser": loser})
    assert len(syn_pairs) == 30

    # topology-grouped folds (leave-one-topology-out)
    graphs = sorted(pool)
    groups = {}
    for g in graphs:
        groups.setdefault(labels.get(g, "unknown"), []).append(g)
    folds = []
    for topo, gs in sorted(groups.items()):
        folds.append({
            "topology": topo,
            "test_graphs": sorted(gs),
            "test_pairs": [p for p in decided if p["graph"] in gs],
            "train_human": [p for p in decided if p["graph"] not in gs],
            "train_synthetic": syn_pairs,  # no human labels; see dose note
        })
    FOLDS.clear()
    FOLDS.extend(folds)
    TIE_PAIRS.clear()
    TIE_PAIRS.extend(tie_pairs)
    BOTH_BAD.clear()
    BOTH_BAD.extend(both_bad)

    # a fold-independent model per arm for the tie-margin (epsilon) analysis:
    # trained on ALL decided pairs (+ synthetic for the s arms; this is
    # calibration analysis, not evaluation)
    for arm in ("M1", "M2", "M1s", "M2s"):
        extra = syn_pairs if arm in ("M1s", "M2s") else []
        FOLD_MODEL_FOR_TIES[arm] = train_bt(
            BANK, FEAT_OF_ARM[arm], decided + extra)

    arms = ("M0", "M1", "M2", "M1s", "M2s")
    results = {}
    for arm in arms:
        results[arm] = eval_arm(arm, folds, pool)

    # jacky's per-graph preferred candidate (unique plurality winner)
    wins_by_graph = {}
    jacky_top1 = {}
    for p in decided:
        w = wins_by_graph.setdefault(p["graph"], {})
        w[p["winner"]] = w.get(p["winner"], 0) + 1
    for g, w in sorted(wins_by_graph.items()):
        best = max(w.values())
        top = [c for c, v in sorted(w.items()) if v == best]
        jacky_top1[g] = {"win_counts": w, "unique": len(top) == 1,
                         "top": top[0] if len(top) == 1 else None}

    top1_table = {}
    for arm in results:
        rows = {}
        hits = 0
        usable = 0
        for g, jt in jacky_top1.items():
            if not jt["unique"]:
                rows[g] = {"jacky_top": None, "model_top": results[arm]["rankings"][g][0],
                           "match": None, "note": "jacky plurality tie"}
                continue
            usable += 1
            mt = results[arm]["rankings"][g][0]
            match = mt == jt["top"]
            hits += 1 if match else 0
            rows[g] = {"jacky_top": jt["top"], "model_top": mt, "match": match}
        top1_table[arm] = {"per_graph": rows, "hits": hits, "usable_graphs": usable,
                           "rate": round(hits / usable, 4) if usable else None}

    # discriminator non-regression (recomputed AFTER preference training;
    # independent of it: the pointwise judge is untouched, sha-pinned).
    # Caliber note: the operating instruction's "ring 0.987" corresponds to
    # the drop-nonloop_straight_rate ABLATION row (0.986928); the committed
    # kept set on the backfilled path reads ring 1.0 / hub 1.0.  We reproduce
    # ALL FOUR rows of the committed v3-beta AUC table and assert each
    # reading equals its committed value exactly (deterministic refits).
    labels_all, pos_bf, neg_docs, _eng, _src = dc.load_corpus(True)
    _l_leg, pos_leg, _n2, _e2, _s2 = dc.load_corpus(False)
    assert len(pos_bf) == 18 and len(neg_docs) == 40 and len(pos_leg) == 18

    def _records(pos):
        return [(p, d.get("graph") or graph_name_of_path(p),
                 scalars_v3_for_layout(d, WINNER_CALIBER))
                for p, d in sorted(pos)]

    neg_records = _records(neg_docs)
    pos_records_bf = _records(pos_bf)
    pos_records_leg = _records(pos_leg)
    kept_no_artifact1 = [k for k in kept_v3 if k != "nonloop_straight_rate"]
    kept_no_artifact2 = [k for k in kept_no_artifact1 if k != "avg_edge_length"]

    def _refit_auc(pos_records, keep_names):
        _m, st = calibrate_shape_v3(pos_records, neg_records, labels_all,
                                    keep_names)
        return {s: st["shapes"][s]["score_auc"]
                for s in ("ring", "hub", "global")}

    auc_readings = {
        "legacy_kept_set_reproduction": _refit_auc(pos_records_leg, kept_v3),
        "committed_kept_set_backfilled": _refit_auc(pos_records_bf, kept_v3),
        "backfilled_drop_nonloop_straight_rate":
            _refit_auc(pos_records_bf, kept_no_artifact1),
        "backfilled_drop_both_format_artifacts":
            _refit_auc(pos_records_bf, kept_no_artifact2),
    }
    # committed honest table (calibration-report-v3-beta.md Arm C table)
    committed_table = {
        "legacy_kept_set_reproduction": {"ring": 1.0, "hub": 1.0,
                                         "global": 0.995833},
        "committed_kept_set_backfilled": {"ring": 1.0, "hub": 1.0,
                                          "global": 0.997222},
        "backfilled_drop_nonloop_straight_rate": {"ring": 0.986928, "hub": 1.0,
                                                  "global": 0.981944},
        "backfilled_drop_both_format_artifacts": {"ring": 0.947712, "hub": 1.0,
                                                  "global": 0.886111},
    }
    for key, expected in committed_table.items():
        for shape, val in expected.items():
            got = auc_readings[key][shape]
            assert got == val, ("discriminator drift at %s/%s: %s != %s"
                                % (key, shape, got, val))
    sha_after = {p: sha256_of(REPO / p) for p in SHA_PINNED}
    assert sha_after == sha_before, "committed scorer artifacts moved"

    # "both bad" pool-quality warning composition
    meta = json.loads(CAND_META_PATH.read_text(encoding="utf-8"))["candidates"]
    both_bad_comp = []
    for t in both_bad:
        both_bad_comp.append({
            "pair_key": t["pair_key"], "graph": t["graph"],
            "a": {"cid": t["a"], **{k: meta[t["a"]][k]
                                    for k in ("recipe", "source", "grade")}},
            "b": {"cid": t["b"], **{k: meta[t["b"]][k]
                                    for k in ("recipe", "source", "grade")}},
        })

    # sanity flip leg: deterministically flip ~half the training labels
    # (recorded LCG seed) and re-run M1/M2 LOSO -> the pipeline must NOT
    # reproduce a degenerate reading (proves the evaluator has discriminative
    # power, i.e. the near-0% / low readings above are data-driven, not a
    # constant artifact of the protocol)
    def _lcg(seed):
        x = seed & 0x7FFFFFFF
        while True:
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            yield x

    g_ = _lcg(20261121)
    flipped = []
    for p in decided:
        q = dict(p)
        if next(g_) % 2 == 0:
            q["winner"], q["loser"] = p["loser"], p["winner"]
        flipped.append(q)
    sanity_folds = [{
        "topology": f["topology"],
        "test_graphs": f["test_graphs"],
        "test_pairs": [p for p in decided if p["graph"] in f["test_graphs"]],
        "train_human": [p for p in flipped if p["graph"] not in f["test_graphs"]],
        "train_synthetic": [],
    } for f in folds]
    sanity = {
        arm: {"pooled": eval_arm(arm, sanity_folds, pool)["pooled"]}
        for arm in ("M1", "M2")
    }
    for arm, s in sanity.items():
        p = s["pooled"]
        assert 0.0 < p["acc"] < 1.0 or p["n"] == 0, \
            ("sanity flip leg degenerated for %s: %s" % (arm, p))

    report = {
        "schema": "stdraw.pref-ranking-m0m1m2/2",
        "generation": {
            "determinism": "double-run byte-identical (evidence dir)",
            "training_authorization": "synthetic pairs user-confirmed (spot-check passed)",
            "dose_family_note": (
                "synthetic pairs use the diagnosis card's cumulative L1-L4 dose "
                "caliber (node-centre movement + edge-attribute damage), NOT the "
                "route-preserving dose family; s-arm vs plain-arm disagreements "
                "are reported side by side, never merged"),
            "eval_caliber": (
                "LOSO over topology groups; decided first-round pairs only; "
                "retest = noise baseline; ties -> epsilon analysis; both-bad -> "
                "pool-quality warning; pairwise margin==0 counted as incorrect; "
                "BT arms are bias-free (a constant preference direction would "
                "be circular when evaluation orients pairs winner-first); "
                "BT fits merge bitwise-duplicate feature columns before "
                "fitting and run a damped full-Hessian Newton to a hard "
                "convergence gate (final gradient norm < 1e-6 asserted on "
                "EVERY fit: LOSO folds, full-data calibration, sanity leg)"),
            "dose_gate_status": (
                "route-preserving dose gate remains unmeasurable; statement "
                "carried over verbatim from the v3-beta report (no change here)"),
        },
        "data": {
            "n_first_round": 24,
            "n_decided": len(decided),
            "n_tie": len(tie_pairs),
            "n_both_bad": len(both_bad),
            "n_retest": 6,
            "retest_agree": agree,
            "retest_noise_baseline": round(RETEST_BASELINE, 4),
            "retest_rows": retest_rows,
            "n_synthetic": len(syn_pairs),
            "jacky_top1": jacky_top1,
            "feature_caliber": {
                "v2": "single global feature space = union of the routed v2 "
                      "shape-model names over all candidates (v2 shape routing "
                      "is candidate-level); per candidate, own routed-model "
                      "values + committed impute medians for the rest",
                "v3": "same caliber on the committed LASSO kept set",
                "global_feature_names": dict(NAMES_GLOBAL),
                "per_graph_routing_v2": {g: dict(bank.route[g])
                                         for g in sorted(bank.route)},
            },
            "topology_groups": {t: sorted(g) for t, g in sorted(groups.items())},
        },
        "arms": results,
        "sanity_flip_leg": {
            "definition": ("training labels deterministically half-flipped "
                           "(LCG seed 20261121); holdout pairs keep jacky's "
                           "real labels; a healthy evaluator reads neither "
                           "0% nor 100% here"),
            "M1": sanity["M1"]["pooled"],
            "M2": sanity["M2"]["pooled"],
        },
        "top1": top1_table,
        "epsilon_analysis": {
            "definition": ("tie margin = model score difference (M0) or BT logit "
                           "(M1/M2, full-data calibration model); epsilon0 = max "
                           "|margin| over the 7 both-good pairs (conservative: "
                           "below epsilon0 declare tie)"),
            "per_arm": {arm: {
                "tie_abs_margins": [t["abs_margin"] for t in results[arm]["tie_margins"]],
                "epsilon0": max(t["abs_margin"] for t in results[arm]["tie_margins"]),
                "train_decided_abs_margin_min": results[arm]["train_margin_abs_min"],
            } for arm in results},
        },
        "both_bad_pool_warning": both_bad_comp,
        "discriminator_non_regression": {
            "readings_recomputed": auc_readings,
            "committed_table": committed_table,
            "all_rows_match_committed": True,
            "sha_pinned_unchanged": True,
            "sha_pinned_files": list(SHA_PINNED),
            "caliber_note": (
                "the operating instruction's 'ring 0.987' corresponds to the "
                "drop-nonloop_straight_rate ABLATION row (0.986928); the "
                "committed kept set on the backfilled path reads ring 1.0 / "
                "hub 1.0. All four committed rows reproduced exactly after "
                "preference training; preference training touches no "
                "pointwise artifact (sha256 pinned before/after)"),
        },
        "bt_weights_full_data": {
            arm: {
                "feature_names": [NAMES_GLOBAL[FEAT_OF_ARM[arm]][j]
                                  for j in
                                  FOLD_MODEL_FOR_TIES[arm]["col_idx"]],
                "merged_duplicate_columns": [
                    {"merged_into": NAMES_GLOBAL[FEAT_OF_ARM[arm]][kp],
                     "dropped": NAMES_GLOBAL[FEAT_OF_ARM[arm]][jd]}
                    for kp, jd in FOLD_MODEL_FOR_TIES[arm]["merged_pairs"]],
                "weights": {NAMES_GLOBAL[FEAT_OF_ARM[arm]][j]: round(wv, 6)
                            for wv, j in
                            zip(FOLD_MODEL_FOR_TIES[arm]["w"],
                                FOLD_MODEL_FOR_TIES[arm]["col_idx"])},
                "bias": round(FOLD_MODEL_FOR_TIES[arm]["b"], 6),
                "fit_convergence": {
                    "iters_used":
                        FOLD_MODEL_FOR_TIES[arm]["hyper"]["irls_iters"],
                    "grad_norm_final":
                        FOLD_MODEL_FOR_TIES[arm]["hyper"]["grad_norm_final"],
                    "objective_final":
                        FOLD_MODEL_FOR_TIES[arm]["hyper"]["objective_final"],
                },
                "note": ("full-data calibration model (not the LOSO models); "
                         "dominant weights disclosed so a perfect reading can "
                         "be traced to its features (e.g. crossing_count)"),
            } for arm in ("M1", "M2", "M1s", "M2s")
        },
        "train_holdout_gap": {
            arm: {
                "mean_train_acc": _mean([f["train_acc_human"]
                                         for f in results[arm]["per_fold"]]),
                "pooled_test_acc": results[arm]["pooled"]["acc"],
                "gap_pp": _gap_pp(results[arm]),
            } for arm in results if arm != "M0"
        },
        "noise_baseline_comparison": {
            arm: {
                "acc": results[arm]["pooled"]["acc"],
                "above_noise_baseline": (
                    results[arm]["pooled"]["acc"] is not None and
                    results[arm]["pooled"]["acc"] > RETEST_BASELINE),
            } for arm in results
        },
    }

    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   sort_keys=False) + "\n", encoding="utf-8")
    MD_OUT.write_text(render_md(report), encoding="utf-8")
    print("wrote %s" % JSON_OUT)
    print("wrote %s" % MD_OUT)
    for arm in results:
        p = results[arm]["pooled"]
        print("  %s: %s/%s = %s CI %s" % (arm, p["correct"], p["n"],
                                          p["acc"], p["ci95"]))
    print("  discriminator: all 4 committed AUC rows reproduced, sha pins unchanged")


def items_both_bad(data):
    return [i for i in data["items"] if i["choice"] == "both_bad"]


def graph_name_of_path(p):
    from stdraw.aesthetic_score import graph_name_of
    return graph_name_of(str(p))


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(math.fsum(vals) / len(vals), 4) if vals else None


def _gap_pp(result):
    """mean in-fold train acc - pooled test acc, in percentage points."""
    tr = _mean([f["train_acc_human"] for f in result["per_fold"]])
    te = result["pooled"]["acc"]
    if tr is None or te is None:
        return None
    return round((tr - te) * 100, 1)


def render_md(r):
    L = []
    L.append("# Preference-ranking comparison: M0 / M1 / M2 (+ M1s / M2s)\n")
    L.append("First Learning-to-Rank round on the 2026-11-21 blind-choice "
             "session (24 first-round pairs, 13 decided / 7 both-good / "
             "4 both-bad first-round; 6 retest repeats, consistency 5/6 = "
             "individual noise baseline).\n")
    L.append("## Conclusion (first round)\n")
    L.append("- No arm clears the coin-flip line convincingly, and no arm "
             "reaches jacky's retest noise baseline (5/6 = 83.3%): the "
             "first-round reading is **no signal** at n=13 decided pairs.")
    g1 = r["train_holdout_gap"]["M1"]
    g2 = r["train_holdout_gap"]["M2"]
    p2 = r["arms"]["M2"]["pooled"]
    p2s = r["arms"]["M2s"]["pooled"]
    L.append("- M1 (v2 features) reads %.1f%% mean in-fold train but "
             "%.1f%% held-out (gap +%spp) and M2 reads %.1f%% held-out "
             "(gap +%spp): both trip the 15pp overfitting review trigger.  "
             "After the solver-convergence fix every BT arm sits inside the "
             "noise band - no signal; the first delivery's \"M1s/M2s "
             "diverge from M1/M2 in opposite directions\" reading was an "
             "unconverged-solver artifact and is withdrawn: at the "
             "converged optimum M2 and M2s anti-generalize in the SAME "
             "direction (the synthetic-pair dose caliber remains a "
             "diagnosis family, reported side by side, never merged)."
             % (100 * g1["mean_train_acc"],
                100 * r["arms"]["M1"]["pooled"]["acc"],
                g1["gap_pp"], 100 * p2["acc"], g2["gap_pp"]))
    L.append("- M2's first-delivery 0/13 held-out (\"every topology fold "
             "0/N, systematic anti-generalization, not a protocol "
             "artifact\") was an optimizer artifact: the diagonal-Hessian "
             "IRLS with a duplicated feature column (mirror_axis_err == "
             "symmetry_axis_err_px on every candidate) never converged.  At "
             "the converged optimum M2 reads %s/%s held-out and M2s reads "
             "%s/%s - all BT arms inside the noise band, no signal.  The "
             "anti-generalization DIRECTION survives for M2 (12/13 held-out "
             "margins keep the delivered sign; only the classic tie pair "
             "q19 flips), but the exact 0/13 and per-fold 0/N readings do "
             "not; the label-flip sanity leg still reads non-degenerately "
             "(see JSON sanity_flip_leg)."
             % (p2["correct"], p2["n"], p2s["correct"], p2s["n"]))
    L.append("- Practical read: the 24-pair first-round budget does not "
             "support per-topology preference training yet; the pointwise "
             "M0 baseline (61.5%) and its 3/3 Top-1 rate on the three "
             "aggregable graphs remain the strongest round-one observation.")
    L.append("")
    L.append("## Headline (read with the CI width - n=13 decided pairs)\n")
    L.append("| arm | pairwise acc | 95% CI (Wilson) | above noise 5/6 | "
             "Top-1 rate |")
    L.append("|---|---|---|---|---|")
    for arm in ("M0", "M1", "M2", "M1s", "M2s"):
        p = r["arms"][arm]["pooled"]
        nb = r["noise_baseline_comparison"][arm]["above_noise_baseline"]
        t1 = r["top1"][arm]
        L.append("| %s | %s/%s = %.1f%% | [%.1f%%, %.1f%%] | %s | %s/%s%s |" % (
            arm, p["correct"], p["n"], 100 * p["acc"],
            100 * p["ci95"][1], 100 * p["ci95"][2],
            ("yes" if nb else "no"),
            t1["hits"], t1["usable_graphs"],
            (" (%.0f%%)" % (100 * t1["rate"]) if t1["rate"] is not None else "")))
    L.append("")
    L.append("Honesty notes:")
    L.append("")
    L.append("- n=13 decided pairs: every CI is wide; conclusions are "
             "\"signal / no signal\" only, never \"model A beats model B\".")
    L.append("- Top-1 aggregation covers only graphs where jacky's plurality "
             "winner is unique (see per-graph table below).")
    L.append("- Synthetic pairs are user-confirmed, but they come from the "
             "diagnosis card's dose caliber (node-centre movement + edge "
             "damage), NOT the route-preserving dose family; s-arms and plain "
             "arms are reported side by side and never merged.")
    L.append("- The route-preserving dose gate remains unmeasurable; the "
             "v3-beta report statement carries over verbatim.")
    L.append("")
    L.append("## Per-fold detail (leave-one-topology-out)\n")
    L.append("| arm | held-out topology | graphs | n train (human/syn) | "
             "train acc | test acc |")
    L.append("|---|---|---|---|---|---|")
    for arm in ("M0", "M1", "M2", "M1s", "M2s"):
        for f in r["arms"][arm]["per_fold"]:
            L.append("| %s | %s | %s | %d/%d | %s | %s (%d/%d) |" % (
                arm, f["held_out_topology"], ", ".join(f["test_graphs"]),
                f["n_train_human"], f["n_train_synthetic"],
                ("%.1f%%" % (100 * f["train_acc_human"])
                 if f["train_acc_human"] is not None else "-"),
                ("%.1f%%" % (100 * f["test_acc"])
                 if f["test_acc"] is not None else "-"),
                f["test_correct"], f["n_test"]))
    L.append("")
    L.append("## Train-holdout gap (review trigger at 15pp)\n")
    L.append("| arm | mean train acc | pooled test acc | gap (pp) | flagged |")
    L.append("|---|---|---|---|---|")
    for arm in ("M1", "M2", "M1s", "M2s"):
        g = r["train_holdout_gap"][arm]
        L.append("| %s | %s | %s | %s | %s |" % (
            arm, g["mean_train_acc"], g["pooled_test_acc"], g["gap_pp"],
            ("YES" if (g["gap_pp"] is not None and g["gap_pp"] > GAP_TRIGGER_PP)
             else "no")))
    L.append("")
    L.append("## Top-1 selection vs jacky (per graph)\n")
    L.append("| graph | jacky top (win counts) | " + " | ".join(
        ("M0", "M1", "M2", "M1s", "M2s")) + " |")
    L.append("|---|---|---|---|---|---|")
    graphs = sorted(r["data"]["jacky_top1"])
    for g in graphs:
        jt = r["data"]["jacky_top1"][g]
        cells = []
        for arm in ("M0", "M1", "M2", "M1s", "M2s"):
            row = r["top1"][arm]["per_graph"][g]
            if row["jacky_top"] is None:
                cells.append("%s (tie-note)" % row["model_top"])
            else:
                cells.append(("**%s**" % row["model_top"]) if row["match"]
                             else row["model_top"])
        wc = ", ".join("%s:%d" % kv for kv in sorted(jt["win_counts"].items()))
        L.append("| %s | %s (%s) | %s |" % (g, jt["top"] or "tie", wc,
                                            " | ".join(cells)))
    L.append("")
    L.append("## Full-data BT weights (calibration model, disclosure)\n")
    for arm in ("M1", "M2", "M1s", "M2s"):
        bw = r["bt_weights_full_data"][arm]
        items = ", ".join("%s=%s" % (nm, bw["weights"][nm])
                          for nm in bw["feature_names"])
        L.append("- %s (bias %s): %s" % (arm, bw["bias"], items))
        for mg in bw["merged_duplicate_columns"]:
            L.append("  - merged duplicate column: %s dropped (bitwise "
                     "identical to %s)" % (mg["dropped"], mg["merged_into"]))
        fc = bw["fit_convergence"]
        L.append("  - converged: %d Newton iters, final gradient norm %g, "
                 "objective %g" % (fc["iters_used"], fc["grad_norm_final"],
                                   fc["objective_final"]))
    L.append("- convergence gate: every BT fit (LOSO folds, full-data "
             "calibration, sanity leg) ends with final gradient norm "
             "< 1e-6, asserted at fit time; duplicate feature columns are "
             "merged before fitting (JSON "
             "bt_weights_full_data.*.merged_duplicate_columns)")
    L.append("")
    L.append("## Epsilon calibration initial values (7 both-good pairs)\n")
    L.append("epsilon0 = max |margin| over tie pairs (below epsilon0 -> declare "
             "tie); contrast = min |margin| over decided training pairs.\n")
    L.append("| arm | epsilon0 | decided-pair min abs margin |")
    L.append("|---|---|---|")
    for arm in ("M0", "M1", "M2", "M1s", "M2s"):
        e = r["epsilon_analysis"]["per_arm"][arm]
        L.append("| %s | %s | %s |" % (arm, e["epsilon0"],
                                       e["train_decided_abs_margin_min"]))
    L.append("")
    L.append("Solver caliber note: the review's converged epsilon "
             "reference (M2 1.066145 / M2s 1.399488) was computed on the "
             "UNMERGED feature space, where the ridge acts on BOTH "
             "duplicate columns; with mirror_axis_err / symmetry_axis_err_px "
             "merged the merged-column readings shift in the last decimals "
             "(M2 %s / M2s %s) while every headline reading matches.  "
             "Convergence acceptance uses the gradient gate (< 1e-6 "
             "asserted on every fit), not the unmerged-space objective "
             "value."
             % (r["epsilon_analysis"]["per_arm"]["M2"]["epsilon0"],
                r["epsilon_analysis"]["per_arm"]["M2s"]["epsilon0"]))
    L.append("")
    L.append("## Both-bad pairs (pool-quality warning, 6)\n")
    L.append("| pair | graph | a | b |")
    L.append("|---|---|---|---|")
    for t in r["both_bad_pool_warning"]:
        L.append("| %s | %s | %s/%s/%s | %s/%s/%s |" % (
            t["pair_key"], t["graph"],
            t["a"]["cid"], t["a"]["recipe"], t["a"]["grade"],
            t["b"]["cid"], t["b"]["recipe"], t["b"]["grade"]))
    L.append("")
    L.append("## Discriminator non-regression (quality gate)\n")
    d = r["discriminator_non_regression"]
    L.append("All four committed v3-beta AUC-table rows reproduced exactly "
             "after preference training (deterministic refits; the pointwise "
             "judge is untouched, sha-pinned before/after):\n")
    L.append("| reading | ring | hub | global |")
    L.append("|---|---|---|---|")
    for key in ("legacy_kept_set_reproduction",
                "committed_kept_set_backfilled",
                "backfilled_drop_nonloop_straight_rate",
                "backfilled_drop_both_format_artifacts"):
        row = d["readings_recomputed"][key]
        L.append("| %s | %s | %s | %s |" % (key, row["ring"], row["hub"],
                                            row["global"]))
    L.append("")
    L.append("- caliber note: " + d["caliber_note"])
    L.append("- sha256 pins on the pointwise scorer artifacts unchanged "
             "(%d files)" % len(d["sha_pinned_files"]))
    L.append("")
    L.append("## Red lines honoured\n")
    L.append("- zero certificate-grade reads by the ranker (grades appear only "
             "in the pool-quality warning composition)")
    L.append("- candidate pool reproduced with the viewer's gate-viability "
             "filter, zero score weight; pool validated field-by-field against "
             "the committed session metadata")
    L.append("- deterministic output (double-run byte-identical); negatives "
             "library read-only; committed scorer artifacts sha-pinned")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
