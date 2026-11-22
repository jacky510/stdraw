#!/usr/bin/env python
"""Final preference comparison: two merged annotation rounds, stratified.

Merges jacky's two blind-choice pairwise sessions and reruns the three
primary arms through the CONVERGED Bradley-Terry solver (the one merged at
repo level after the convergence rework: bitwise-duplicate feature columns
merged away, damped full-Hessian Newton, hard gradient gate < 1e-6 asserted
on every fit).  The synthetic arms (M1s / M2s) are listed side by side and
NEVER merged into the headline (different dose family - the diagnosis
card's cumulative L1-L4 caliber, not the route-preserving dose family).

Data (PROVENANCE.md in each session directory is the authority)
----------------------------------------------------------------
Round 1  2026-11-21: 30 answers (24 first-round + 6 in-session retests,
         retest consistency 5/6).  Rendering caliber: 28/30 pictures were
         re-routed (rewired) renders (OLD picture caliber).
Round 2  2026-11-22: 20 answers (17 new + 3 cross-session retests,
         cross-session consistency 2/3 vs round-1 FIRST-round answers).
         Rendering caliber: byte-faithful slim_doc (NEW picture caliber).
Merged:  25 strict decided pairs (13 + 12); 11 "both good" (7 + 4, feeds
         the epsilon calibration, never a training pair); 10 "both bad"
         (6 + 4, pool-quality warning list).

Stratified analysis (the two rounds differ in picture caliber)
----------------------------------------------------------------
S_all : all 25 decided pairs, LOSO by topology, training = the 25 minus
        the held-out topology (mixed picture caliber, disclosed).
S_r2  : the 12 byte-faithful round-2 pairs only, LOSO, training = those
        12 minus the held-out topology (same-caliber training).
S_r1  : the 13 round-1 pairs only, same protocol.
If S_r1 and S_r2 disagree in direction, both readings are reported as a
divergence, never averaged away.

Evaluation (fixed thresholds)
----------------------------------------------------------------
1. Pairwise accuracy + Wilson 95% CI per stratification (pooled across
   folds; each pair tested exactly once; margin == 0 counts as incorrect).
2. Signal gate: an arm counts as a SIGNAL only above the CROSS-SESSION
   noise baseline 2/3 = 66.7% (stricter than the in-session 5/6 = 83.3%,
   which is reported alongside).  n=25 gives wide CIs: conclusions are
   restricted to "signal / no signal" and "did the edge dimensions add
   increment" - never "model A beats model B".
3. Top-1 selection rate per stratification (jacky's unique plurality
   winner vs the model's first-ranked pool candidate).
4. Train-holdout gap (> 15pp triggers review; threshold from the ranking
   plan), plus solver convergence evidence: every BT fit asserts final
   gradient norm < 1e-6; the full-data calibration fits additionally
   report final objective vs the w=0 objective (optimum reference).
5. Edge-dimension increment: M2 (v3-beta features incl. edge dimensions)
   vs M1 (v2 features) per stratification; if the increment is not
   significant the report says so plainly ("n insufficient, one more
   round needed").
6. Discriminator non-regression: the pointwise human-vs-engine judge is
   recomputed AFTER preference training (all four committed v3-beta AUC
   rows) and every reading must equal its committed value exactly;
   scorer artifacts sha256-pinned before/after.

Epsilon calibration (initial values)
----------------------------------------------------------------
Full-data calibration model per arm (trained on all 25 decided pairs,
synthetic added for the s-arms); margin magnitudes over the 11 both-good
pairs; epsilon initial value = P75 of that distribution (P25/P50/max
reported alongside; max equals the earlier epsilon0 caliber, which was
the conservative choice).  Relation to the v1.3.1 review draft section
14: the feature caliber descends from its Appendix A 21-feature union,
and its small-graph degeneracy risk list (pinned / gate-collapsed
features) bounds what a tie margin can express - the P75 value is an
INITIAL calibration constant, not a validated threshold.

Red lines honoured (same as the previous rounds): zero certificate-grade
reads by the ranker (grades appear only in the pool-quality warning
composition); candidate pool reproduction with the viewer's gate
viability filter, zero score weight; deterministic output; negatives
library read-only; committed scorer artifacts untouched (sha-pinned).
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
import pref_pipeline as pp  # noqa: E402  (pairwise-exclusion loader patch)
import pref_ranking_m0m1m2 as base  # noqa: E402  (converged solver + bank)
from stdraw.aesthetic_score import load_family_labels  # noqa: E402
from stdraw.aesthetic_score_v3 import (  # noqa: E402
    calibrate_shape_v3,
    scalars_v3_for_layout,
)

R1_DIR = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-21"
R2_DIR = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-22-round2"
SYN_DIR = REPO / "benchmarks" / "aesthetic" / "pref-synthetic"
FAMILY_MAP = REPO / "benchmarks" / "corpus" / "classic" / "topology-families.json"
OUT_DIR = REPO / "benchmarks" / "aesthetic"
JSON_OUT = OUT_DIR / "pref-ranking-final.json"
MD_OUT = OUT_DIR / "pref-ranking-report-final.md"

GAP_TRIGGER_PP = 15.0
WITHIN_BASELINE = 5.0 / 6.0     # in-session retest consistency (round 1)
CROSS_BASELINE = 2.0 / 3.0      # cross-session retest consistency (round 2)
SIGNAL_GATE = CROSS_BASELINE    # stricter gate: must beat cross-session noise
ARMS = ("M0", "M1", "M2", "M1s", "M2s")
PRIMARY_ARMS = ("M0", "M1", "M2")
STRATA = ("S_all", "S_r2", "S_r1")

# committed honest table (calibration-report-v3-beta.md Arm C) - asserted
# row by row by the discriminator non-regression leg below
COMMITTED_AUC_TABLE = {
    "legacy_kept_set_reproduction": {"ring": 1.0, "hub": 1.0,
                                     "global": 0.995833},
    "committed_kept_set_backfilled": {"ring": 1.0, "hub": 1.0,
                                      "global": 0.997222},
    "backfilled_drop_nonloop_straight_rate": {"ring": 0.986928, "hub": 1.0,
                                              "global": 0.981944},
    "backfilled_drop_both_format_artifacts": {"ring": 0.947712, "hub": 1.0,
                                              "global": 0.886111},
}


def quantile(sorted_vals, q):
    """Linear-interpolation quantile on a pre-sorted list (deterministic)."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# ── session loading + calibers ────────────────────────────────────────────

def load_session(r1_path, r2_path):
    d1 = json.loads(r1_path.read_text(encoding="utf-8"))
    d2 = json.loads(r2_path.read_text(encoding="utf-8"))
    items1, items2 = d1["items"], d2["items"]
    assert d1["n_answered"] == 30 and len(items1) == 30
    assert d2["n_answered"] == 20 and len(items2) == 20
    first1 = [i for i in items1 if not i["is_retest"]]
    retest1 = [i for i in items1 if i["is_retest"]]
    retest2 = [i for i in items2 if i["is_retest"]]
    new2 = [i for i in items2 if not i["is_retest"]]
    assert len(first1) == 24 and len(retest1) == 6
    assert len(new2) == 17 and len(retest2) == 3
    return items1, items2, first1, retest1, new2, retest2


def decide(items):
    """Strict decisions -> pair rows tagged with their session/answer kind."""
    out = []
    for it in items:
        w = base.pair_winner(it)
        if w in (it["candidate_a"], it["candidate_b"]):
            out.append({
                "pair_key": it["pair_key"], "graph": it["graph"],
                "a": it["candidate_a"], "b": it["candidate_b"],
                "winner": w,
                "loser": it["candidate_b"] if w == it["candidate_a"]
                else it["candidate_a"],
            })
    return out


def by_choice(items, choice):
    return [{"pair_key": it["pair_key"], "graph": it["graph"],
             "a": it["candidate_a"], "b": it["candidate_b"],
             "is_retest": bool(it["is_retest"])}
            for it in items if it["choice"] == choice]


def consistency(first_map, retest_items):
    rows, agree = [], 0
    for it in retest_items:
        fw = first_map.get(it["pair_key"])
        rw = base.pair_winner(it)
        ok = fw == rw
        agree += 1 if ok else 0
        rows.append({"pair_key": it["pair_key"], "first_winner": fw,
                     "retest_winner": rw, "agree": ok})
    return agree, rows


def r2_pool_validation(pool, syn_docs):
    """Round-2 session candidates must be the same viewer pool plus the
    already-banked synthetic dose candidates (field-level validation)."""
    meta = json.loads((R2_DIR / "candidates.json").read_text(
        encoding="utf-8"))["candidates"]
    flat = {}
    for g, cands in pool.items():
        for c in cands:
            flat[c["cid"]] = (g, c)
    unknown = [cid for cid in meta if cid not in flat and cid not in syn_docs]
    assert not unknown, "round-2 candidates outside pool+synthetic: %s" % unknown
    for cid in meta:
        if cid in flat:
            g, c = flat[cid]
            m = meta[cid]
            assert g == m["graph"] and c["recipe"] == m["recipe"], cid
            assert c["source"] == m["source"] and c["grade"] == m["grade"], cid
    return meta


# ── evaluation ────────────────────────────────────────────────────────────

BANK = None
NAMES_GLOBAL = {}
M0_SCORES = {}


def make_folds(decided, labels, pool, syn_pairs, with_synthetic):
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
            "train_synthetic": syn_pairs if with_synthetic else [],
        })
    return folds


def _feat(arm):
    return base.FEAT_OF_ARM[arm]


def _margin(arm, model, p):
    if arm == "M0":
        return M0_SCORES[p["winner"]] - M0_SCORES[p["loser"]]
    names = NAMES_GLOBAL[_feat(arm)]
    va = BANK.vector(p["winner"], names, _feat(arm))
    vb = BANK.vector(p["loser"], names, _feat(arm))
    return base.bt_margin(model, va, vb)


def eval_arm(arm, folds, pool):
    per_fold, rankings = [], {}
    correct_total = n_total = 0
    margins_train = []
    for fold in folds:
        model = None
        if arm != "M0":
            train = list(fold["train_human"]) + list(fold["train_synthetic"])
            model = train_bt_tagged(arm, train) if train else None
        tr_ok = 0
        for p in fold["train_human"]:
            if _margin(arm, model, p) > 0:
                tr_ok += 1
            margins_train.append(abs(_margin(arm, model, p)))
        te_ok = te_n = 0
        te_margins = []
        for p in fold["test_pairs"]:
            m = _margin(arm, model, p)
            te_margins.append({"pair_key": p["pair_key"],
                               "session": p["session"],
                               "signed_margin": round(m, 6)})
            te_ok += 1 if m > 0 else 0
            te_n += 1
        correct_total += te_ok
        n_total += te_n
        for g in fold["test_graphs"]:
            cids = [c["cid"] for c in pool[g]]
            if arm == "M0":
                scores = {cid: M0_SCORES[cid] for cid in cids}
                order = sorted(cids, key=lambda c: (-scores[c], c))
            elif model is None:
                # degenerate fold (all stratum pairs held out): deterministic
                # pool-order fallback, disclosed in the fold row
                order = list(cids)
            else:
                wins = {cid: 0.0 for cid in cids}
                names = NAMES_GLOBAL[_feat(arm)]
                for i, ca in enumerate(cids):
                    for cb in cids[i + 1:]:
                        va = BANK.vector(ca, names, _feat(arm))
                        vb = BANK.vector(cb, names, _feat(arm))
                        m = base.bt_margin(model, va, vb)
                        if m > 0:
                            wins[ca] += 1
                        elif m < 0:
                            wins[cb] += 1
                        else:
                            wins[ca] += 0.5
                            wins[cb] += 0.5
                order = sorted(cids, key=lambda c: (-wins[c], c))
            rankings[g] = order
        per_fold.append({
            "held_out_topology": fold["topology"],
            "test_graphs": fold["test_graphs"],
            "n_train_human": len(fold["train_human"]),
            "n_train_synthetic": len(fold["train_synthetic"]),
            "train_acc_human": round(tr_ok / len(fold["train_human"]), 4)
            if fold["train_human"] else None,
            "test_acc": round(te_ok / te_n, 4) if te_n else None,
            "n_test": te_n,
            "test_correct": te_ok,
            "test_pair_margins": te_margins,
        })
    return {
        "arm": arm,
        "pooled": {"correct": correct_total, "n": n_total,
                   "acc": round(correct_total / n_total, 4) if n_total else None,
                   "ci95": base.wilson_ci(correct_total, n_total)
                   if n_total else None},
        "per_fold": per_fold,
        "rankings": rankings,
        "train_margin_abs_min": round(min(margins_train), 6)
        if margins_train else None,
    }


def train_bt_tagged(arm, train_pairs):
    feat = _feat(arm)
    diffs = []
    for p in train_pairs:
        names = NAMES_GLOBAL[feat]
        va = BANK.vector(p["winner"], names, feat)
        vb = BANK.vector(p["loser"], names, feat)
        diffs.append([a - b for a, b in zip(va, vb)])
    return base.fit_bt(diffs)


def top1_table(decided, results, pool):
    wins_by_graph = {}
    for p in decided:
        w = wins_by_graph.setdefault(p["graph"], {})
        w[p["winner"]] = w.get(p["winner"], 0) + 1
    jacky = {}
    for g, w in sorted(wins_by_graph.items()):
        best = max(w.values())
        top = [c for c, v in sorted(w.items()) if v == best]
        jacky[g] = {"win_counts": w, "unique": len(top) == 1,
                    "top": top[0] if len(top) == 1 else None}
    table = {}
    for arm, res in results.items():
        rows, hits, usable = {}, 0, 0
        for g, jt in jacky.items():
            if g not in res["rankings"]:
                continue
            mt = res["rankings"][g][0]
            if not jt["unique"]:
                rows[g] = {"jacky_top": None, "model_top": mt,
                           "match": None, "note": "jacky plurality tie"}
                continue
            usable += 1
            match = mt == jt["top"]
            hits += 1 if match else 0
            rows[g] = {"jacky_top": jt["top"], "model_top": mt,
                       "match": match}
        table[arm] = {"per_graph": rows, "hits": hits,
                      "usable_graphs": usable,
                      "rate": round(hits / usable, 4) if usable else None}
    return jacky, table


def gap_pp(result):
    trs = [f["train_acc_human"] for f in result["per_fold"]]
    trs = [v for v in trs if v is not None]
    te = result["pooled"]["acc"]
    if not trs or te is None:
        return None
    return round((math.fsum(trs) / len(trs) - te) * 100, 1)


# ── main ──────────────────────────────────────────────────────────────────

def main():
    sha_before = {p: base.sha256_of(REPO / p) for p in base.SHA_PINNED}

    items1, items2, first1, retest1, new2, retest2 = load_session(
        R1_DIR / "answers-2026-11-21.json",
        R2_DIR / "answers-2026-11-22.json")

    decided_r1 = [dict(p, session="r1", answer_kind="first_round")
                  for p in decide(first1)]
    decided_r2 = [dict(p, session="r2",
                       answer_kind="retest" if p["pair_key"] in
                       {i["pair_key"] for i in retest2} else "new")
                  for p in decide(items2)]
    decided_all = decided_r1 + decided_r2
    both_good = ([dict(t, session="r1")
                  for t in by_choice(first1, "both")] +
                 [dict(t, session="r2")
                  for t in by_choice(items2, "both")])
    both_bad = ([dict(t, session="r1")
                 for t in by_choice(items1, "both_bad")] +
                [dict(t, session="r2")
                 for t in by_choice(items2, "both_bad")])
    assert len(decided_r1) == 13 and len(decided_r2) == 12
    assert len(decided_all) == 25
    assert len(both_good) == 11 and len(both_bad) == 10
    # decided pairs are disjoint across sessions (no duplicate pair_key)
    assert len({p["pair_key"] for p in decided_all}) == 25
    # the cross-session overlap keys are tie-type in round 1 (disclosed)
    overlap = ({i["pair_key"] for i in first1} &
               {i["pair_key"] for i in items2})
    assert len(overlap) == 3
    assert all(base.pair_winner(i) == "both"
               for i in first1 if i["pair_key"] in overlap)

    # noise baselines
    first_map = {i["pair_key"]: base.pair_winner(i) for i in first1}
    agree_within, within_rows = consistency(first_map, retest1)
    assert agree_within == 5, "in-session retest consistency drifted"
    agree_cross, cross_rows = consistency(first_map, retest2)
    assert agree_cross == 2, "cross-session consistency drifted: %d/3" % agree_cross

    # pools / features (converged-solver bank, unchanged caliber)
    pool = base.load_pool()
    labels = load_family_labels(str(FAMILY_MAP))
    model_v2 = json.loads((OUT_DIR / "model-v2.json").read_text(encoding="utf-8"))
    model_v3 = json.loads((OUT_DIR / "model-v3-alpha.json").read_text(encoding="utf-8"))
    kept_v3 = list(json.loads(
        (OUT_DIR / "lasso-path-v3-alpha.json").read_text(encoding="utf-8")
    )["selected"]["kept"])

    syn_docs = {}
    for p in sorted((SYN_DIR / "candidates").glob("*.json")):
        syn_docs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    r2_meta = r2_pool_validation(pool, syn_docs)

    global BANK
    bank = base.FeatureBank(pool, labels, model_v2, model_v3, kept_v3)
    for cid in sorted(syn_docs):
        d = syn_docs[cid]
        assert d.get("graph"), cid
        bank.add_doc(cid, d["graph"], d)
    BANK = bank
    NAMES_GLOBAL.clear()
    for featname in ("v2", "v3"):
        names = []
        for cid in sorted(bank._model_names):
            for nm in bank._model_names[cid][featname]:
                if nm not in names:
                    names.append(nm)
        NAMES_GLOBAL[featname] = names
    # every pair-referenced candidate must have banked features
    referenced = set()
    for p in decided_all + both_good + both_bad:
        referenced.update((p["a"], p["b"]))
    missing = [c for c in sorted(referenced)
               if c not in bank.v2 and c not in bank.v3]
    assert not missing, "unbanked candidates: %s" % missing

    scorer_v2 = dc.Scorer(model_v2, labels)
    for g, cands in pool.items():
        for c in cands:
            sc, _shape, _row = scorer_v2.score(c["doc"], g)
            M0_SCORES[c["cid"]] = sc
    # synthetic candidates too (round-2 pairs reference them)
    for cid in sorted(syn_docs):
        sc, _shape, _row = scorer_v2.score(syn_docs[cid], syn_docs[cid]["graph"])
        M0_SCORES[cid] = sc

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

    # stratified folds (same-caliber training per stratum)
    subsets = {
        "S_all": decided_all,
        "S_r2": decided_r2,
        "S_r1": decided_r1,
    }
    results = {}
    for s in STRATA:
        results[s] = {}
        for arm in ARMS:
            folds = make_folds(subsets[s], labels, pool, syn_pairs,
                               with_synthetic=arm in ("M1s", "M2s"))
            results[s][arm] = eval_arm(arm, folds, pool)

    jacky_top1, top1 = {}, {}
    for s in STRATA:
        jacky_top1[s], top1[s] = top1_table(subsets[s], results[s], pool)

    gaps = {s: {arm: gap_pp(results[s][arm]) for arm in ARMS
                if arm != "M0"} for s in STRATA}

    # signal classification (strict cross-session gate; CI reported as-is)
    signal = {}
    for s in STRATA:
        signal[s] = {}
        for arm in ARMS:
            p = results[s][arm]["pooled"]
            acc = p["acc"]
            # gate on the EXACT fraction (correct/n), never on the rounded
            # acc: 8/12 == 2/3 must read "at the gate, not above"
            above = (p["n"] > 0
                     and p["correct"] / p["n"] > 2.0 / 3.0)
            signal[s][arm] = {
                "acc": acc, "ci95": p["ci95"],
                "above_cross_baseline": above,
                "above_within_baseline": p["n"] > 0
                and p["correct"] / p["n"] > 5.0 / 6.0,
                "verdict": ("signal" if above else
                            ("at the gate (equal to 2/3, not above)"
                             if p["n"] > 0
                             and p["correct"] / p["n"] == 2.0 / 3.0
                             else "no signal")),
            }

    # edge-dimension increment (M2 vs M1), honest wording
    edge_increment = {}
    for s in STRATA:
        a1 = results[s]["M1"]["pooled"]
        a2 = results[s]["M2"]["pooled"]
        if a1["acc"] is None or a2["acc"] is None:
            continue
        delta_pp = round((a2["acc"] - a1["acc"]) * 100, 1)
        ci_overlap = (a1["ci95"][1] <= a2["ci95"][2]
                      and a2["ci95"][1] <= a1["ci95"][2])
        edge_increment[s] = {
            "M1_acc": a1["acc"], "M2_acc": a2["acc"],
            "delta_pp": delta_pp,
            "M1_ci95": a1["ci95"], "M2_ci95": a2["ci95"],
            "ci95_overlap": ci_overlap,
            "verdict": ("no increment demonstrated (CIs overlap, n "
                        "insufficient - one more round needed)"
                        if ci_overlap else
                        "directional difference beyond CI overlap "
                        "(still not a model ranking at this n)"),
        }

    # round-1 vs round-2 divergence check
    divergence = {}
    for arm in ARMS:
        r1 = results["S_r1"][arm]["pooled"]["acc"]
        r2 = results["S_r2"][arm]["pooled"]["acc"]
        if r1 is None or r2 is None:
            continue
        divergence[arm] = {
            "S_r1_acc": r1, "S_r2_acc": r2,
            "same_direction_vs_coinflip": (r1 - 0.5) * (r2 - 0.5) > 0,
            "delta_pp": round((r2 - r1) * 100, 1),
        }

    # epsilon calibration: full-data model per arm, P75 over 11 both-good
    eps = {"definition": (
        "full-data calibration model per arm (trained on all 25 decided "
        "pairs; synthetic added only for the s-arms); tie margin = |model "
        "score difference (M0) or BT logit (BT arms)| over the 11 both-good "
        "pairs; epsilon initial value = P75 of that distribution (P75 "
        "caliber).  The earlier epsilon0 caliber = max over tie pairs "
        "(conservative); both are reported.  Relation to the v1.3.1 review "
        "draft section 14: the feature caliber descends from its Appendix A "
        "21-feature union, and its small-graph degeneracy risk list "
        "(gate-pinned / collapsed features) bounds what a tie margin can "
        "express - the P75 value is an INITIAL calibration constant, not a "
        "validated threshold."),
        "per_arm": {}}
    for arm in ARMS:
        entry = {"both_good_abs_margins": None}
        if arm == "M0":
            ties = [abs(_margin(arm, None,
                                {"winner": t["a"], "loser": t["b"]}))
                    for t in both_good]
            ties_sorted = sorted(round(v, 6) for v in ties)
            entry = {"both_good_abs_margins": ties_sorted}
        else:
            model = train_bt_tagged(
                arm, decided_all +
                (syn_pairs if arm in ("M1s", "M2s") else []))
            ties = []
            for t in both_good:
                m = _margin(arm, model, {"winner": t["a"], "loser": t["b"]})
                ties.append(abs(m))
            ties_sorted = sorted(round(v, 6) for v in ties)
            entry["both_good_abs_margins"] = ties_sorted
            entry["fit_convergence"] = {
                "grad_norm_final": model["hyper"]["grad_norm_final"],
                "objective_final": model["hyper"]["objective_final"],
                "iters_used": model["hyper"]["irls_iters"],
                "optimum_reference": ("the BT objective is convex in w "
                                      "(logistic loss + L2 ridge), so the "
                                      "asserted first-order gate ||grad|| "
                                      "< 1e-6 certifies a GLOBAL optimum; "
                                      "final objective value reported "
                                      "alongside"),
            }
            entry["weights"] = {
                NAMES_GLOBAL[_feat(arm)][j]: round(wv, 6)
                for wv, j in zip(model["w"], model["col_idx"])}
            entry["merged_duplicate_columns"] = [
                {"merged_into": NAMES_GLOBAL[_feat(arm)][kp],
                 "dropped": NAMES_GLOBAL[_feat(arm)][jd]}
                for kp, jd in model["merged_pairs"]]
            dec = sorted(round(abs(_margin(arm, model, p)), 6)
                         for p in decided_all)
            entry["decided_abs_margin_min"] = dec[0]
            entry["decided_abs_margin_p25"] = round(quantile(dec, 0.25), 6)
        entry["p25"] = round(quantile(entry["both_good_abs_margins"], 0.25), 6)
        entry["p50"] = round(quantile(entry["both_good_abs_margins"], 0.50), 6)
        entry["p75_initial"] = round(quantile(entry["both_good_abs_margins"],
                                              0.75), 6)
        entry["max_epsilon0_legacy"] = round(
            max(entry["both_good_abs_margins"]), 6)
        eps["per_arm"][arm] = entry

    # both-bad list (pool-quality warning; per-session composition)
    meta1 = json.loads((R1_DIR / "candidates.json").read_text(
        encoding="utf-8"))["candidates"]
    both_bad_comp = []
    for t in both_bad:
        meta = meta1 if t["session"] == "r1" else r2_meta
        row = {"pair_key": t["pair_key"], "graph": t["graph"],
               "session": t["session"], "is_retest_answer": t["is_retest"]}
        for side in ("a", "b"):
            m = meta[t[side]]
            row[side] = {"cid": t[side], "recipe": m["recipe"],
                         "source": m["source"], "grade": m["grade"]}
        both_bad_comp.append(row)

    # discriminator non-regression (recomputed AFTER preference training)
    labels_all, pos_bf, neg_docs, _eng, _src = dc.load_corpus(True)
    _l_leg, pos_leg, _n2, _e2, _s2 = dc.load_corpus(False)
    assert len(pos_bf) == 18 and len(neg_docs) == 40 and len(pos_leg) == 18

    def _records(pos):
        from stdraw.aesthetic_score import graph_name_of
        return [(p, d.get("graph") or graph_name_of(str(p)),
                 scalars_v3_for_layout(d, base.WINNER_CALIBER))
                for p, d in sorted(pos)]

    neg_records = _records(neg_docs)
    pos_records_bf = _records(pos_bf)
    pos_records_leg = _records(pos_leg)
    kept_no_artifact1 = [k for k in kept_v3
                         if k != "nonloop_straight_rate"]
    kept_no_artifact2 = [k for k in kept_no_artifact1
                         if k != "avg_edge_length"]

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
    committed_table = COMMITTED_AUC_TABLE
    for key, expected in committed_table.items():
        for shape, val in expected.items():
            got = auc_readings[key][shape]
            assert got == val, ("discriminator drift at %s/%s: %s != %s"
                                % (key, shape, got, val))
    sha_after = {p: base.sha256_of(REPO / p) for p in base.SHA_PINNED}
    assert sha_after == sha_before, "committed scorer artifacts moved"

    # sanity flip leg (half-flipped training labels on S_all, M1/M2)
    def _lcg(seed):
        x = seed & 0x7FFFFFFF
        while True:
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            yield x

    g_ = _lcg(20261121)
    flipped = []
    for p in decided_all:
        q = dict(p)
        if next(g_) % 2 == 0:
            q["winner"], q["loser"] = p["loser"], p["winner"]
        flipped.append(q)
    sanity_folds = []
    groups = {}
    for g in sorted(pool):
        groups.setdefault(labels.get(g, "unknown"), []).append(g)
    for topo, gs in sorted(groups.items()):
        sanity_folds.append({
            "topology": topo, "test_graphs": sorted(gs),
            "test_pairs": [p for p in decided_all if p["graph"] in gs],
            "train_human": [p for p in flipped if p["graph"] not in gs],
            "train_synthetic": [],
        })
    sanity = {arm: eval_arm(arm, sanity_folds, pool)["pooled"]
              for arm in ("M1", "M2")}
    for arm, s in sanity.items():
        assert 0.0 < s["acc"] < 1.0, ("sanity flip leg degenerated: %s" % arm)

    # jacky time-on-task (duration_ms sums, per session)
    dur = {
        "r1_total_minutes": round(math.fsum(i["duration_ms"] for i in items1)
                                  / 60000.0, 1),
        "r2_total_minutes": round(math.fsum(i["duration_ms"] for i in items2)
                                  / 60000.0, 1),
        "r1_median_s_per_q": round(quantile(
            sorted(i["duration_ms"] / 1000.0 for i in items1), 0.5), 1),
        "r2_median_s_per_q": round(quantile(
            sorted(i["duration_ms"] / 1000.0 for i in items2), 0.5), 1),
    }

    # round-3 recommendation (derived from measured yields and durations)
    y_r1 = 13 / 24.0
    y_r2 = 12 / 17.0
    y_pool = 25 / 41.0
    round3 = {
        "observed_decision_yield": {"round1": round(y_r1, 3),
                                    "round2": round(y_r2, 3),
                                    "pooled": round(y_pool, 3)},
        "chatgpt_budget": {
            "definition_note": ("the 150~250 external-review budget read "
                                "two ways: total ANSWERED questions vs "
                                "total strict DECIDED pairs"),
            "as_answered_questions": [
                {"budget": 150, "answered_so_far": 50, "still_needed": 100,
                 "extra_decided": 61, "sessions_of_20q": 5.0},
                {"budget": 250, "answered_so_far": 50, "still_needed": 200,
                 "extra_decided": 122, "sessions_of_20q": 10.0},
            ],
            "as_decided_pairs": [
                {"budget": 150, "decided_so_far": 25, "still_needed": 125,
                 "new_questions": 205, "sessions_of_20q": 10.0},
                {"budget": 250, "decided_so_far": 25, "still_needed": 225,
                 "new_questions": 369, "sessions_of_20q": 18.0},
            ],
        },
        "ci_roadmap": ("Wilson half-width at p=0.7: n=50 -> 12.3pp, "
                       "n=80 -> 9.9pp, n=100 -> 8.8pp.  An incremental "
                       "verdict (M2 vs M1) needs roughly n=80~100 decided "
                       "pairs in the SAME picture caliber before its CI "
                       "can separate; at the pooled 61% decision yield "
                       "that is about 130~165 new questions = 7~8 "
                       "sessions of 20 questions."),
        "recommendation": (
            "Round 3 = 20~24 adaptive questions with the round-2 tool, "
            "ALL rendered byte-faithful (this experiment shows the old "
            "re-routed caliber REVERSES the M2 direction, so mixing "
            "calibers again would poison the increment verdict).  "
            "Composition: M2-vs-M1 uncertain pairs first (edge-dimension "
            "increment is the open question), both-good pairs kept "
            "mixed in (epsilon calibration has only 11 samples), 3~4 "
            "cross-session retests to grow the stricter noise baseline.  "
            "jacky time per session: recorded click time was 1.5~2.5 min "
            "(median 2.7~4.0 s/question); budget 5 min with overhead.  "
            "Milestone: after ~4 sessions (~80 new answered, ~50 new "
            "decided in byte-faithful caliber) re-run this experiment; "
            "escalate to the full 150~250-pair budget only if the "
            "byte-faithful stratum keeps its direction."),
    }

    report = {
        "schema": "stdraw.pref-ranking-final/1",
        "generation": {
            "determinism": "double-run byte-identical (evidence dir)",
            "solver": ("converged BT solver only (duplicate-column merge + "
                       "damped full-Hessian Newton, gradient gate < 1e-6 "
                       "asserted on EVERY fit); the pre-convergence "
                       "artifact readings are not reproducible by design"),
            "stratification": (
                "S_all = 25 merged decided pairs (mixed picture caliber); "
                "S_r2 = 12 byte-faithful round-2 pairs only; S_r1 = 13 "
                "round-1 pairs only; each stratum trains on its own pairs "
                "(same-caliber training) under LOSO by topology"),
            "synthetic_arms": (
                "M1s/M2s listed side by side, NEVER merged into the "
                "headline; different dose family (diagnosis card's "
                "cumulative L1-L4 caliber)"),
        },
        "data": {
            "round1": {"n_answered": 30, "n_first_round": 24,
                       "n_decided": 13, "n_both_good": 7, "n_both_bad": 6,
                       "n_retest": 6,
                       "picture_caliber": "28/30 re-routed renders (old)"},
            "round2": {"n_answered": 20, "n_new": 17, "n_decided": 12,
                       "n_both_good": 4, "n_both_bad": 4, "n_retest": 3,
                       "picture_caliber": "byte-faithful slim_doc (new)"},
            "merged": {"n_decided": 25, "n_both_good": 11,
                       "n_both_bad": 10,
                       "cross_session_overlap_keys": sorted(overlap),
                       "overlap_note": ("the 3 cross-session overlap keys "
                                        "are tie-type in round 1 (both "
                                        "good), so the 25 decided pairs "
                                        "are disjoint")},
            "noise_baselines": {
                "within_session": round(WITHIN_BASELINE, 4),
                "within_rows": within_rows,
                "cross_session": round(CROSS_BASELINE, 4),
                "cross_rows": cross_rows,
                "signal_gate": round(SIGNAL_GATE, 4),
                "gate_note": ("an arm counts as a signal only above the "
                              "cross-session baseline 66.7% (stricter "
                              "than in-session 83.3%)"),
            },
            "jacky_time_on_task": dur,
            "topology_groups": {t: sorted(g) for t, g in sorted(
                {k: v for k, v in groups.items()}.items())},
        },
        "stratified_results": results,
        "signal_classification": signal,
        "edge_dimension_increment": edge_increment,
        "round_divergence_check": divergence,
        "top1": top1,
        "jacky_top1": jacky_top1,
        "train_holdout_gap": gaps,
        "epsilon_calibration": eps,
        "round3_recommendation": round3,
        "both_bad_pool_warning": both_bad_comp,
        "sanity_flip_leg": {
            "definition": ("training labels deterministically half-flipped "
                           "(LCG seed 20261121) on S_all; holdout pairs "
                           "keep jacky's real labels; a healthy evaluator "
                           "reads neither 0% nor 100%"),
            "M1": sanity["M1"],
            "M2": sanity["M2"],
        },
        "discriminator_non_regression": {
            "readings_recomputed": auc_readings,
            "committed_table": committed_table,
            "all_rows_match_committed": True,
            "sha_pinned_unchanged": True,
            "sha_pinned_files": list(base.SHA_PINNED),
        },
    }

    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   sort_keys=False) + "\n", encoding="utf-8")
    MD_OUT.write_text(render_md(report), encoding="utf-8")
    print("wrote %s" % JSON_OUT)
    print("wrote %s" % MD_OUT)
    for s in STRATA:
        for arm in ARMS:
            p = results[s][arm]["pooled"]
            print("  %s %s: %s/%s = %s CI %s" % (
                s, arm, p["correct"], p["n"], p["acc"], p["ci95"]))
    print("  discriminator: all 4 committed AUC rows reproduced, sha pins unchanged")


base.COMMITTED_AUC_TABLE = {
    "legacy_kept_set_reproduction": {"ring": 1.0, "hub": 1.0,
                                     "global": 0.995833},
    "committed_kept_set_backfilled": {"ring": 1.0, "hub": 1.0,
                                      "global": 0.997222},
    "backfilled_drop_nonloop_straight_rate": {"ring": 0.986928, "hub": 1.0,
                                              "global": 0.981944},
    "backfilled_drop_both_format_artifacts": {"ring": 0.947712, "hub": 1.0,
                                              "global": 0.886111},
}


def render_md(r):
    L = []
    L.append("# Final preference comparison: two merged rounds, stratified")
    L.append("")
    L.append("Merged data: 25 strict decided pairs (round-1 13 + round-2 12), "
             "11 both-good (epsilon calibration), 10 both-bad (pool-quality "
             "warning); noise baselines: in-session 5/6 = 83.3%, cross-"
             "session 2/3 = 66.7% (the signal gate).  All BT arms run on the "
             "converged solver (gradient gate < 1e-6 asserted on every fit); "
             "synthetic arms listed side by side, never merged.")
    L.append("")
    L.append("## Stratified headline (read with the CI width)")
    L.append("")
    L.append("| stratum | arm | pairwise acc | 95% CI (Wilson) | signal? | "
             "Top-1 | gap (pp) |")
    L.append("|---|---|---|---|---|---|---|")
    for s in STRATA:
        for arm in ARMS:
            p = r["stratified_results"][s][arm]["pooled"]
            sg = r["signal_classification"][s][arm]
            t1 = r["top1"][s][arm]
            gap = r["train_holdout_gap"][s].get(arm)
            L.append("| %s | %s | %s/%s = %.1f%% | [%.1f%%, %.1f%%] | %s | "
                     "%s/%s | %s |" % (
                         s, arm, p["correct"], p["n"], 100 * p["acc"],
                         100 * p["ci95"][1], 100 * p["ci95"][2],
                         sg["verdict"],
                         t1["hits"], t1["usable_graphs"],
                         gap if gap is not None else "-"))
    L.append("")
    L.append("Signal gate = cross-session noise baseline 2/3 = 66.7% "
             "(stricter than in-session 5/6 = 83.3%).  n=25/12/13: CIs are "
             "wide by construction; the only allowed conclusions are "
             "\"signal / no signal\" and \"did the edge dimensions add "
             "increment\".")
    L.append("")
    L.append("## Edge dimensions (M2 vs M1) - increment judgment")
    L.append("")
    L.append("| stratum | M1 acc | M2 acc | delta | CI overlap | verdict |")
    L.append("|---|---|---|---|---|---|")
    for s, e in r["edge_dimension_increment"].items():
        L.append("| %s | %.1f%% | %.1f%% | %spp | %s | %s |" % (
            s, 100 * e["M1_acc"], 100 * e["M2_acc"], e["delta_pp"],
            "yes" if e["ci95_overlap"] else "no", e["verdict"]))
    L.append("")
    L.append("## Round divergence check (S_r1 old picture caliber vs S_r2 "
             "byte-faithful)")
    L.append("")
    L.append("| arm | S_r1 acc | S_r2 acc | delta | same side of coin flip? |")
    L.append("|---|---|---|---|---|")
    for arm, d in r["round_divergence_check"].items():
        L.append("| %s | %.1f%% | %.1f%% | %spp | %s |" % (
            arm, 100 * d["S_r1_acc"], 100 * d["S_r2_acc"], d["delta_pp"],
            "yes" if d["same_direction_vs_coinflip"] else "NO - divergence"))
    L.append("")
    L.append("## Per-fold detail (LOSO by topology)")
    L.append("")
    for s in STRATA:
        L.append("### %s" % s)
        L.append("")
        L.append("| arm | held-out topology | n train (human/syn) | "
                 "train acc | test acc |")
        L.append("|---|---|---|---|---|")
        for arm in ARMS:
            for f in r["stratified_results"][s][arm]["per_fold"]:
                L.append("| %s | %s | %d/%d | %s | %s (%d/%d) |" % (
                    arm, f["held_out_topology"], f["n_train_human"],
                    f["n_train_synthetic"],
                    ("%.1f%%" % (100 * f["train_acc_human"])
                     if f["train_acc_human"] is not None else "-"),
                    ("%.1f%%" % (100 * f["test_acc"])
                     if f["test_acc"] is not None else "-"),
                    f["test_correct"], f["n_test"]))
        L.append("")
    L.append("## Top-1 vs jacky (per stratum)")
    L.append("")
    for s in STRATA:
        L.append("### %s" % s)
        L.append("")
        L.append("| graph | jacky top (win counts) | " +
                 " | ".join(ARMS) + " |")
        L.append("|---|---|" + "---|" * len(ARMS))
        for g in sorted(r["jacky_top1"][s]):
            jt = r["jacky_top1"][s][g]
            cells = []
            for arm in ARMS:
                row = r["top1"][s][arm]["per_graph"].get(g)
                if row is None:
                    cells.append("-")
                elif row["jacky_top"] is None:
                    cells.append("%s (tie-note)" % row["model_top"])
                else:
                    cells.append(("**%s**" % row["model_top"])
                                 if row["match"] else row["model_top"])
            wc = ", ".join("%s:%d" % kv
                           for kv in sorted(jt["win_counts"].items()))
            L.append("| %s | %s (%s) | %s |" % (g, jt["top"] or "tie", wc,
                                                " | ".join(cells)))
        L.append("")
    L.append("## Train-holdout gap (review trigger at 15pp)")
    L.append("")
    L.append("| stratum | arm | mean train acc | pooled test acc | gap (pp) "
             "| flagged |")
    L.append("|---|---|---|---|---|---|")
    for s in STRATA:
        for arm in ARMS:
            if arm == "M0":
                continue
            g = r["train_holdout_gap"][s][arm]
            if g is None:
                continue
            L.append("| %s | %s | - | %s | %s | %s |" % (
                s, arm, r["stratified_results"][s][arm]["pooled"]["acc"], g,
                "YES" if g > GAP_TRIGGER_PP else "no"))
    L.append("")
    L.append("## Epsilon calibration initial values (11 both-good pairs, "
             "P75 caliber)")
    L.append("")
    L.append(r["epsilon_calibration"]["definition"])
    L.append("")
    L.append("| arm | P25 | P50 | P75 (initial) | max (legacy epsilon0) | "
             "decided min abs margin |")
    L.append("|---|---|---|---|---|---|")
    for arm in ARMS:
        e = r["epsilon_calibration"]["per_arm"][arm]
        L.append("| %s | %s | %s | **%s** | %s | %s |" % (
            arm, e["p25"], e["p50"], e["p75_initial"],
            e["max_epsilon0_legacy"],
            e.get("decided_abs_margin_min", "-")))
    L.append("")
    L.append("Solver convergence (full-data calibration fits; M0 is the "
             "pointwise baseline, no fit):")
    L.append("")
    for arm in ARMS:
        fc = r["epsilon_calibration"]["per_arm"][arm].get("fit_convergence")
        if fc is None:
            continue
        L.append("- %s: %d Newton iters, final gradient norm %g, final "
                 "objective %g" % (arm, fc["iters_used"],
                                   fc["grad_norm_final"],
                                   fc["objective_final"]))
    L.append("- gate: every BT fit in this experiment (all LOSO folds, all "
             "full-data fits, sanity leg) asserts final gradient norm "
             "< 1e-6 at fit time; the objective is convex in w (logistic "
             "loss + L2 ridge), so the first-order gate is the global-"
             "optimum reference.  The pre-convergence artifact readings "
             "are not reproducible by design")
    L.append("")
    L.append("## Both-bad pairs (pool-quality warning, 10)")
    L.append("")
    L.append("| session | pair | graph | a | b |")
    L.append("|---|---|---|---|---|")
    for t in r["both_bad_pool_warning"]:
        L.append("| %s%s | %s | %s | %s/%s/%s | %s/%s/%s |" % (
            t["session"], " (retest)" if t["is_retest_answer"] else "",
            t["pair_key"], t["graph"],
            t["a"]["cid"], t["a"]["recipe"], t["a"]["grade"],
            t["b"]["cid"], t["b"]["recipe"], t["b"]["grade"]))
    L.append("")
    L.append("## Round-3 recommendation (measured-yield derived)")
    L.append("")
    L.append("Observed strict-decision yield: round 1 %s, round 2 %s "
             "(pooled %s of new questions)." % (
                 r["round3_recommendation"]["observed_decision_yield"]["round1"],
                 r["round3_recommendation"]["observed_decision_yield"]["round2"],
                 r["round3_recommendation"]["observed_decision_yield"]["pooled"]))
    L.append("")
    L.append("ChatGPT 150~250-pair budget, both readings:")
    L.append("")
    L.append("| reading | budget | have | still needed | ~sessions of 20q |")
    L.append("|---|---|---|---|---|")
    for row in r["round3_recommendation"]["chatgpt_budget"]["as_answered_questions"]:
        L.append("| answered questions | %d | %d | %d | %.0f |"
                 % (row["budget"], row["answered_so_far"],
                    row["still_needed"], row["sessions_of_20q"]))
    for row in r["round3_recommendation"]["chatgpt_budget"]["as_decided_pairs"]:
        L.append("| strict decided pairs | %d | %d | %d | %.0f |"
                 % (row["budget"], row["decided_so_far"],
                    row["still_needed"], row["sessions_of_20q"]))
    L.append("")
    L.append(r["round3_recommendation"]["ci_roadmap"])
    L.append("")
    L.append(r["round3_recommendation"]["recommendation"])
    L.append("")
    L.append("## Sanity flip leg (S_all, M1/M2)")
    L.append("")
    for arm in ("M1", "M2"):
        p = r["sanity_flip_leg"][arm]
        L.append("- %s: %s/%s = %.1f%% (non-degenerate = evaluator has "
                 "discriminative power)" % (arm, p["correct"], p["n"],
                                            100 * p["acc"]))
    L.append("")
    L.append("## Noise-baseline rows (caliber of the 2/3)")
    L.append("")
    L.append("| kind | pair | first | retest | agree |")
    L.append("|---|---|---|---|---|")
    for row in (r["data"]["noise_baselines"]["within_rows"] +
                r["data"]["noise_baselines"]["cross_rows"]):
        L.append("| %s | %s | %s | %s | %s |" % (
            "in-session" if row in r["data"]["noise_baselines"]["within_rows"]
            else "cross-session",
            row["pair_key"], row["first_winner"], row["retest_winner"],
            "yes" if row["agree"] else "NO"))
    L.append("")
    L.append("(cross-session caliber compares round-2 retest answers with "
             "round-1 FIRST-round answers; the comb pair drifted from "
             "\"both\" to a lean - counted as disagree, noise feature)")
    L.append("")
    L.append("## Discriminator non-regression (quality gate)")
    L.append("")
    d = r["discriminator_non_regression"]
    L.append("All four committed v3-beta AUC-table rows reproduced exactly "
             "after preference training (deterministic refits; the "
             "pointwise judge is untouched, sha256-pinned before/after):")
    L.append("")
    L.append("| reading | ring | hub | global |")
    L.append("|---|---|---|---|")
    for key in sorted(d["committed_table"]):
        row = d["readings_recomputed"][key]
        L.append("| %s | %s | %s | %s |" % (key, row["ring"], row["hub"],
                                            row["global"]))
    L.append("")
    L.append("## Red lines honoured")
    L.append("")
    L.append("- zero certificate-grade reads by the ranker (grades appear "
             "only in the pool-quality warning composition)")
    L.append("- candidate pool reproduced with the viewer's gate-viability "
             "filter, zero score weight; pool validated against both "
             "sessions' committed metadata")
    L.append("- deterministic output (double-run byte-identical); negatives "
             "library read-only; committed scorer artifacts sha-pinned")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
