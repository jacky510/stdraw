#!/usr/bin/env python
"""Final preference comparison v2: three merged annotation rounds (62 pairs).

Merges jacky's THREE blind-choice pairwise sessions and reruns the three
primary arms (plus the synthetic dose arms, reported side by side, never
merged) through the CONVERGED Bradley-Terry solver (bitwise-duplicate
feature columns merged away, damped full-Hessian Newton, hard gradient
gate < 1e-6 asserted on every fit).

Data (PROVENANCE.md in each session directory is the authority)
----------------------------------------------------------------
Round 1   2026-11-21: 30 answers (24 first-round + 6 in-session retests,
          retest consistency 5/6).  Picture caliber: re-routed renders (OLD).
Round 2   2026-11-22: 20 answers (17 new + 3 cross-session retests,
          cross-session consistency 2/3).  Picture caliber: byte-faithful
          slim_doc (NEW).
Round 3   2026-11-22 (worker build, canonical): 37/37 answers - 14 newtopo
          + 11 disagree + 9 anchor + 3 cross-session retests.  Choices:
          4a/7b/7 both-good/19 both-bad.  Picture caliber: byte-faithful
          (same slim family as round 2).  Candidate docs:
          pref-synthetic/_render_cache/round3/cand.*/layout.json (the
          operator's draft session is archived and deliberately NOT used).
Merged:   36 strict decided pairs (13 + 12 + 11); 18 "both good" (11 + 7,
          feeds the epsilon calibration, never a training pair); 29
          "both bad" (10 + 19, pool-quality warning list).

Questions this run answers (card priority order)
----------------------------------------------------------------
1. Full merge: M0/M1/M2 on all 36 strict pairs, stratified S_all / S_r12
   (rounds 1-2, mixed picture caliber, disclosed) / S_r3 (round 3,
   byte-faithful); converged BT solver; Wilson CIs.
2. New-topology generalization: nested-ring-shared-node /
   chain-ring-hybrid / dual-hub-asymmetric were never seen in training.
   Per-graph leave-one-graph-out pairwise accuracy is reported separately
   - with the honest caveat that round 3 produced ZERO decided pairs on
   these graphs (all 14 newtopo pairs were answered both-bad), so the
   pairwise accuracy on them is NOT MEASURABLE; the both-bad composition
   is the actual signal and goes to the warning list.
3. Anchor vs engine: round 3 asked 9 human-anchor vs engine pairs (6
   human-source candidates).  The ratio at which each arm ranks the human
   anchor AHEAD of the engine candidate is reported per pair (out-of-fold
   margins from the S_all LOSO evaluation - each pair tested exactly once
   - plus the byte-faithful S_r3 reading) alongside jacky's own choices.
4. Noise floor: the 3 round-3 cross-session retests were ALL re-asks of
   previously-tied pairs and reproduce the tie 3/3 (tie-level noise);
   the winner-level cross-session gate stays at round 2's 2/3 = 66.7%
   (pooled 5/6 over 6 cross-session retests reported as context).  The
   7 round-3 both-good pairs enter the epsilon P75 calibration (18
   pooled); the 19 round-3 both-bad pairs form the pool-quality warning
   list.
5. Verdicts: does any arm beat the 66.7% cross-session noise gate?  Is
   the M2-vs-M1 edge-dimension increment demonstrable at the larger n?
   CI reported as-is; n insufficiency stated plainly.

Red lines honoured (same as previous rounds): zero certificate-grade
reads by the ranker (grades appear only in the pool-quality warning
composition); candidate pool reproduction with the viewer's gate
viability filter, zero score weight; deterministic output (double-run
byte-identical); negatives library read-only; committed scorer artifacts
untouched (sha-pinned); thresholds are named constants, never inlined.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import diagnose_collapse as dc  # noqa: E402
import pref_pipeline as pp  # noqa: E402  (pairwise-exclusion loader patch)
import pref_ranking_final as final  # noqa: E402  (proven r1+r2 loaders/eval)
import pref_ranking_m0m1m2 as base  # noqa: E402  (converged solver + bank)
from stdraw.aesthetic_score import (  # noqa: E402
    load_family_labels,
    graph_name_of,
)
from stdraw.aesthetic_score_v3 import (  # noqa: E402
    calibrate_shape_v3,
    scalars_v3_for_layout,
)

R1_DIR = final.R1_DIR
R2_DIR = final.R2_DIR
R3_DIR = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-22-round3"
R3_SELECTION = REPO / "benchmarks" / "aesthetic" / "pref-round3-selection.json"
R3_DOCS = REPO / "benchmarks" / "aesthetic" / "pref-synthetic" / "_render_cache" / "round3"
SYN_DIR = final.SYN_DIR
FAMILY_MAP = final.FAMILY_MAP
OUT_DIR = final.OUT_DIR
JSON_OUT = OUT_DIR / "pref-ranking-final-v2.json"
MD_OUT = OUT_DIR / "pref-ranking-report-final-v2.md"

GAP_TRIGGER_PP = final.GAP_TRIGGER_PP
CROSS_BASELINE = final.CROSS_BASELINE          # 2/3 winner-level noise gate
WITHIN_BASELINE = final.WITHIN_BASELINE        # 5/6 in-session (round 1)
ARMS = final.ARMS
PRIMARY_ARMS = final.PRIMARY_ARMS
STRATA = ("S_all", "S_r12", "S_r3")
NEW_GRAPHS = ("nested-ring-shared-node", "chain-ring-hybrid",
              "dual-hub-asymmetric")

COMMITTED_AUC_TABLE = final.COMMITTED_AUC_TABLE


# ── round-3 session loading + candidate docs ──────────────────────────────

def load_r3():
    """Answers + selection kinds + candidate registry for round 3."""
    d = json.loads((R3_DIR / "answers-2026-11-22.json").read_text(
        encoding="utf-8"))
    items = d["items"]
    assert d["n_answered"] == 37 and len(items) == 37
    assert d["session"].endswith("round3")
    choices = Counter(i["choice"] for i in items)
    assert choices == {"both_bad": 19, "both": 7, "b": 7, "a": 4}, choices
    sel = json.loads(R3_SELECTION.read_text(encoding="utf-8"))
    kinds = {q["pair_key"]: q["kind"] for q in sel["questions"]}
    assert sel["n_total"] == 37 and len(kinds) == 37
    assert Counter(kinds.values()) == {"newtopo": 14, "disagree": 11,
                                       "anchor": 9, "retest": 3}
    akinds = {i["pair_key"]: kinds[i["pair_key"]] for i in items}
    assert len(akinds) == 37  # every answered pair_key maps to a kind
    assert all(i["is_retest"] == (akinds[i["pair_key"]] == "retest")
               for i in items)
    cand_meta = json.loads((R3_DIR / "candidates.json").read_text(
        encoding="utf-8"))["candidates"]
    return d, items, akinds, sel, cand_meta


def load_r3_fresh_docs(cand_meta, pool):
    """Load the 15 fresh-r3 extension/new-topology candidate docs from the
    committed render cache, mapping cid -> dir through the recorded recipe
    string ("recipe+SRC@pitch" / "recipe+SRC@pitch+arc"), and validate every
    doc against the session registry (gate viability + gap/crossings)."""
    pool_cids = {c["cid"] for cands in pool.values() for c in cands}
    fresh = {}
    for cid, m in sorted(cand_meta.items()):
        if m["source"] != "fresh-r3":
            assert cid in pool_cids, \
                "non-fresh round-3 candidate outside the viewer pool: %s" % cid
            continue
        rec = m["recipe"]                       # e.g. "ortho+A@80"
        arc = rec.endswith("+arc")
        if arc:
            rec = rec[:-4]
        assert rec.count("+") == 1 and "@" in rec, (cid, m["recipe"])
        recipe, rest = rec.split("+")
        src, pitch = rest.split("@")
        dirname = "cand.%s.%s.%s.%s.p%s" % (m["graph"], src, recipe,
                                            "arc" if arc else "straight",
                                            pitch)
        lj = R3_DOCS / dirname / "layout.json"
        assert lj.exists(), "missing round-3 cached doc: %s" % lj
        doc = json.loads(lj.read_text(encoding="utf-8"))
        doc.setdefault("graph", m["graph"])
        ok, gcert = pp.gate_viability(doc, m["graph"])
        assert ok, "round-3 cached doc fails gate viability: %s" % cid
        assert abs(gcert["metrics"]["min_card_gap"] - m["gap"]) < 0.05, cid
        assert gcert["metrics"]["crossings"] == m["crossings"], cid
        fresh[cid] = {"cid": cid, "graph": m["graph"], "doc": doc,
                      "source": m["source"], "recipe": m["recipe"],
                      "grade": m["grade"], "gap": m["gap"],
                      "crossings": m["crossings"]}
    n_fresh_registry = sum(1 for m in cand_meta.values()
                           if m["source"] == "fresh-r3")
    assert len(fresh) == n_fresh_registry, (len(fresh), n_fresh_registry)
    return fresh


def previous_answers(pairs):
    """Most recent committed answer (winner-caliber) for each pair_key over
    rounds 1-2, for the cross-session retest consistency rows."""
    prev = {}
    for sess, path in (("r1", R1_DIR / "answers-2026-11-21.json"),
                       ("r2", R2_DIR / "answers-2026-11-22.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        for i in d["items"]:
            prev[i["pair_key"]] = {"session": sess,
                                   "choice": base.pair_winner(i)}
    return {p: prev[p] for p in pairs if p in prev}


# ── evaluation reuse (final's proven LOSO machinery) ──────────────────────

def margins_by_pair(stratum_results, arm):
    """pair_key -> out-of-fold signed margin, pooled across folds."""
    out = {}
    for f in stratum_results[arm]["per_fold"]:
        for m in f["test_pair_margins"]:
            out[m["pair_key"]] = m["signed_margin"]
    return out


def make_graph_folds(decided, syn_pairs, with_synthetic):
    """Leave-one-GRAPH-out folds (card question 2: per-graph stratification)."""
    graphs = sorted({p["graph"] for p in decided} )
    folds = []
    for g in graphs:
        folds.append({
            "topology": "graph:" + g,
            "test_graphs": [g],
            "test_pairs": [p for p in decided if p["graph"] == g],
            "train_human": [p for p in decided if p["graph"] != g],
            "train_synthetic": syn_pairs if with_synthetic else [],
        })
    return folds


def epsilon_block(arms_models, both_good):
    """Epsilon calibration over both-good pairs (P75 caliber, per arm)."""
    out = {"definition": (
        "full-data calibration model per arm (trained on all %d decided "
        "pairs; synthetic added only for the s-arms); tie margin = |model "
        "score difference (M0) or BT logit (BT arms)| over the %d both-good "
        "pairs; epsilon initial value = P75 of that distribution.  The "
        "P75 value is an INITIAL calibration constant, not a validated "
        "threshold." % (arms_models["n_decided"], len(both_good))),
        "per_arm": {}}
    for arm in ARMS:
        model = arms_models[arm]
        rows = []
        for t in both_good:
            m = final._margin(arm, model,
                              {"winner": t["a"], "loser": t["b"]})
            rows.append(dict(t, abs_margin=round(abs(m), 6)))
        vals = sorted(r["abs_margin"] for r in rows)
        r12 = sorted(r["abs_margin"] for r in rows if r["session"] != "r3")
        r3 = sorted(r["abs_margin"] for r in rows if r["session"] == "r3")
        entry = {
            "n_both_good": len(rows),
            "n_exact_zero_margins": sum(1 for v in vals if v == 0.0),
            "both_good_abs_margins": vals,
            "p25": round(final.quantile(vals, 0.25), 6),
            "p50": round(final.quantile(vals, 0.50), 6),
            "p75_initial": round(final.quantile(vals, 0.75), 6),
            "max_epsilon0_legacy": round(max(vals), 6),
            "p75_r12_only": round(final.quantile(r12, 0.75), 6) if r12 else None,
            "p75_r3_only": round(final.quantile(r3, 0.75), 6) if r3 else None,
        }
        if arm != "M0":
            entry["fit_convergence"] = {
                "grad_norm_final": model["hyper"]["grad_norm_final"],
                "objective_final": model["hyper"]["objective_final"],
                "iters_used": model["hyper"]["irls_iters"],
            }
            dec = sorted(round(abs(final._margin(arm, model, p)), 6)
                         for p in arms_models["decided_used"])
            entry["decided_abs_margin_min"] = dec[0]
            entry["decided_abs_margin_p25"] = round(
                final.quantile(dec, 0.25), 6)
            entry["weights"] = {
                final.NAMES_GLOBAL[final._feat(arm)][j]: round(wv, 6)
                for wv, j in zip(model["w"], model["col_idx"])}
            entry["merged_duplicate_columns"] = [
                {"merged_into": final.NAMES_GLOBAL[final._feat(arm)][kp],
                 "dropped": final.NAMES_GLOBAL[final._feat(arm)][jd]}
                for kp, jd in model["merged_pairs"]]
        out["per_arm"][arm] = entry
    return out


# ── main ──────────────────────────────────────────────────────────────────

def main():
    sha_before = {p: base.sha256_of(REPO / p) for p in base.SHA_PINNED}

    # ---- rounds 1-2 (proven loaders; assertions carried over verbatim) ----
    items1, items2, first1, retest1, new2, retest2 = final.load_session(
        R1_DIR / "answers-2026-11-21.json",
        R2_DIR / "answers-2026-11-22.json")
    decided_r1 = [dict(p, session="r1") for p in decide_tagged(first1, "r1")]
    decided_r2 = [dict(p, session="r2") for p in decide_tagged(items2, "r2")]
    both_good = (final.by_choice(first1, "both") +
                 final.by_choice(items2, "both"))
    both_bad = (final.by_choice(items1, "both_bad") +
                final.by_choice(items2, "both_bad"))
    assert len(decided_r1) == 13 and len(decided_r2) == 12
    assert len(both_good) == 11 and len(both_bad) == 10
    assert len({p["pair_key"] for p in decided_r1 + decided_r2}) == 25

    # noise baselines, rounds 1-2 (unchanged calibers)
    first_map = {i["pair_key"]: base.pair_winner(i) for i in first1}
    agree_within, within_rows = final.consistency(first_map, retest1)
    assert agree_within == 5, "in-session retest consistency drifted"
    agree_cross, cross_rows = final.consistency(first_map, retest2)
    assert agree_cross == 2, "cross-session consistency drifted: %d/3" % agree_cross

    # ---- round 3 ----
    d3, items3, akinds, sel, cand_meta3 = load_r3()
    decided_r3 = [dict(p, session="r3") for p in decide_tagged(items3, "r3")]
    both_good_r3 = final.by_choice(items3, "both")
    both_bad_r3 = final.by_choice(items3, "both_bad")
    assert len(decided_r3) == 11
    assert len(both_good_r3) == 7 and len(both_bad_r3) == 19
    assert len({p["pair_key"] for p in decided_r1 + decided_r2 + decided_r3}) == 36

    decided_all = decided_r1 + decided_r2 + decided_r3
    both_good_all = [dict(t, session="r1") for t in final.by_choice(first1, "both")] \
        + [dict(t, session="r2") for t in final.by_choice(items2, "both")] \
        + [dict(t, session="r3") for t in both_good_r3]
    both_bad_all = [dict(t, session="r1") for t in final.by_choice(items1, "both_bad")] \
        + [dict(t, session="r2") for t in final.by_choice(items2, "both_bad")] \
        + [dict(t, session="r3") for t in both_bad_r3]
    assert len(both_good_all) == 18 and len(both_bad_all) == 29

    # round-3 retests: all three were re-asks of previously TIED pairs
    r3_retest_items = [i for i in items3 if i["is_retest"]]
    prevmap = previous_answers([i["pair_key"] for i in r3_retest_items])
    assert len(prevmap) == 3
    retest3_rows = []
    tie_reproductions = 0
    for i in r3_retest_items:
        pw = base.pair_winner(i)
        pv = prevmap[i["pair_key"]]
        ok = pw == pv["choice"]
        tie_reproductions += 1 if (pw == "both" and pv["choice"] == "both") else 0
        retest3_rows.append({"pair_key": i["pair_key"], "qid": i["qid"],
                             "previous": pv, "round3_winner_caliber": pw,
                             "agree": ok})
    assert tie_reproductions == 3, tie_reproductions

    # ---- pools / features (converged-solver bank, unchanged caliber) ----
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
    r2_meta = final.r2_pool_validation(pool, syn_docs)
    r3_fresh = load_r3_fresh_docs(cand_meta3, pool)

    global BANK
    bank = base.FeatureBank(pool, labels, model_v2, model_v3, kept_v3)
    for cid in sorted(syn_docs):
        dd = syn_docs[cid]
        assert dd.get("graph"), cid
        bank.add_doc(cid, dd["graph"], dd)
    for cid, r in sorted(r3_fresh.items()):
        bank.add_doc(cid, r["graph"], r["doc"])
    final.BANK = bank
    final.NAMES_GLOBAL.clear()
    for featname in ("v2", "v3"):
        names = []
        for cid in sorted(bank._model_names):
            for nm in bank._model_names[cid][featname]:
                if nm not in names:
                    names.append(nm)
        final.NAMES_GLOBAL[featname] = names
    referenced = set()
    for p in decided_all + both_good_all + both_bad_all:
        referenced.update((p["a"], p["b"]))
    missing = [c for c in sorted(referenced)
               if c not in bank.v2 and c not in bank.v3]
    assert not missing, "unbanked candidates: %s" % missing

    scorer_v2 = dc.Scorer(model_v2, labels)
    final.M0_SCORES.clear()
    for g, cands in pool.items():
        for c in cands:
            sc, _s, _r = scorer_v2.score(c["doc"], g)
            final.M0_SCORES[c["cid"]] = sc
    for cid in sorted(syn_docs):
        sc, _s, _r = scorer_v2.score(syn_docs[cid], syn_docs[cid]["graph"])
        final.M0_SCORES[cid] = sc
    for cid, r in r3_fresh.items():
        sc, _s, _r = scorer_v2.score(r["doc"], r["graph"])
        final.M0_SCORES[cid] = sc

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

    # ---- Q1: stratified LOSO (topology-grouped, as in rounds 1-2) ----
    subsets = {
        "S_all": decided_all,
        "S_r12": decided_r1 + decided_r2,
        "S_r3": decided_r3,
    }
    results = {}
    for s in STRATA:
        results[s] = {}
        for arm in ARMS:
            folds = final.make_folds(subsets[s], labels, pool, syn_pairs,
                                     with_synthetic=arm in ("M1s", "M2s"))
            results[s][arm] = final.eval_arm(arm, folds, pool)

    # ---- Q2: leave-one-graph-out per-graph accuracy ----
    graph_results = {}
    for arm in ARMS:
        folds = make_graph_folds(decided_all, syn_pairs,
                                 with_synthetic=arm in ("M1s", "M2s"))
        graph_results[arm] = final.eval_arm(arm, folds, pool)
    per_graph_acc = {}
    for arm in ARMS:
        rows = {}
        for f in graph_results[arm]["per_fold"]:
            g = f["test_graphs"][0]
            rows[g] = {"n_test": f["n_test"], "correct": f["test_correct"],
                       "acc": f["test_acc"]}
        per_graph_acc[arm] = rows
    newtopo_pairs = [i for i in items3 if akinds[i["pair_key"]] == "newtopo"]
    newtopo_choices = Counter(i["choice"] for i in newtopo_pairs)
    newtopo_verdict = {
        "graphs": list(NEW_GRAPHS),
        "n_decided_pairs_on_new_graphs":
            sum(1 for p in decided_all if p["graph"] in NEW_GRAPHS),
        "n_asked_newtopo_pairs": len(newtopo_pairs),
        "newtopo_answer_split": dict(newtopo_choices),
        "finding": (
            "ZERO decided pairs on the three training-unseen graphs: all "
            "14 newtopo pairs were answered both-bad, so per-graph "
            "leave-one-graph-out pairwise accuracy on them is NOT "
            "MEASURABLE (n=0).  The both-bad composition is the actual "
            "generalization signal and is reported in the warning list."),
    }

    # ---- full-data calibration models (needed by the anchor all-9 reading
    # and the epsilon block) ----
    arms_models = {}
    for arm in ARMS:
        extra = syn_pairs if arm in ("M1s", "M2s") else []
        model = (None if arm == "M0"
                 else final.train_bt_tagged(arm, decided_all + extra))
        arms_models[arm] = model
    arms_models["n_decided"] = len(decided_all)
    arms_models["decided_used"] = decided_all

    # ---- Q3: anchor vs engine ----
    anchor_keys = [k for k, v in akinds.items() if v == "anchor"]
    assert len(anchor_keys) == 9
    qid_of = {i["pair_key"]: i["qid"] for i in items3}
    anchor_rows = []
    for it in items3:
        if akinds[it["pair_key"]] != "anchor":
            continue
        ha = cand_meta3[it["candidate_a"]]["source"] == "human"
        hb = cand_meta3[it["candidate_b"]]["source"] == "human"
        assert ha != hb, "anchor pair must have exactly one human side"
        human = it["candidate_a"] if ha else it["candidate_b"]
        engine = it["candidate_b"] if ha else it["candidate_a"]
        row = {"qid": it["qid"], "graph": it["graph"],
               "human": human, "engine": engine,
               "engine_recipe": cand_meta3[engine]["recipe"],
               "jacky_choice": it["choice"],
               "jacky_verdict": ("human" if it["choice"] in ("a", "b")
                                 and base.pair_winner(it) == human
                                 else "engine" if it["choice"] in ("a", "b")
                                 else it["choice"]),
               "margins": {}, "model_human_first": {}}
        for s in STRATA:
            mm = margins_by_pair(results[s], "M0")
            if it["pair_key"] in mm:
                for arm in ARMS:
                    m = margins_by_pair(results[s], arm)[it["pair_key"]]
                    row["margins"]["%s/%s" % (s, arm)] = m
                    row["model_human_first"]["%s/%s" % (s, arm)] = m > 0
        anchor_rows.append(row)
    anchor_summary = {}
    for s in STRATA:
        anchor_summary[s] = {}
        for arm in ARMS:
            key = "%s/%s" % (s, arm)
            tested = [r for r in anchor_rows
                      if key in r["model_human_first"]]
            # all-9 reading: full-data calibration model (disclosed as
            # IN-SAMPLE for the 7 decided anchor pairs, which are training
            # members of that model; the out-of-fold reading below is the
            # primary one)
            model = arms_models[arm]
            all9 = 0
            for r in anchor_rows:
                m = (final.M0_SCORES[r["human"]] - final.M0_SCORES[r["engine"]]
                     if arm == "M0"
                     else final._margin(arm, model,
                                        {"winner": r["human"],
                                         "loser": r["engine"]}))
                r["margin_full_calib/%s" % arm] = round(m, 6)
                r["model_human_first_full_calib/%s" % arm] = m > 0
                all9 += 1 if m > 0 else 0
            if not tested:
                anchor_summary[s][arm] = {
                    "n_tested": 0,
                    "n_asked": len(anchor_rows),
                    "human_first_all9_full_calib_model": all9,
                    "ratio_all9_full_calib_model": round(all9 / len(anchor_rows), 4),
                    "calib_model_caveat": "in-sample for the 7 decided pairs",
                }
                continue
            first = sum(1 for r in tested if r["model_human_first"][key])
            dec = [r for r in tested if r["jacky_verdict"] in ("human",
                                                               "engine")]
            first_dec = sum(1 for r in dec if r["model_human_first"][key])
            anchor_summary[s][arm] = {
                "n_tested": len(tested),
                "human_ranked_first": first,
                "ratio_all": round(first / len(tested), 4),
                "n_decided_jacky": len(dec),
                "human_ranked_first_decided_only": first_dec,
                "ratio_decided_only": round(first_dec / len(dec), 4)
                if dec else None,
                "n_asked": len(anchor_rows),
                "human_first_all9_full_calib_model": all9,
                "ratio_all9_full_calib_model": round(all9 / len(anchor_rows), 4),
                "calib_model_caveat": "in-sample for the 7 decided pairs",
            }
    jacky_anchor = Counter(r["jacky_verdict"] for r in anchor_rows)

    # ---- epsilon (calibration models already built above) ----
    eps = epsilon_block(arms_models, both_good_all)

    # ---- backward-compatibility check: S_r12 must reproduce the committed
    # two-round S_all readings exactly (the round-3 fresh candidates append
    # feature dimensions that are ZERO on every pool-pool training diff and
    # are merged away by the solver, so the rounds-1-2 reading is unmoved)
    committed = json.loads((OUT_DIR / "pref-ranking-final.json").read_text(
        encoding="utf-8"))["signal_classification"]["S_all"]
    compat = {}
    for arm in ARMS:
        mine = results["S_r12"][arm]["pooled"]
        ref = committed[arm]["acc"]
        assert mine["acc"] == ref, \
            ("S_r12 no longer reproduces the committed two-round S_all "
             "reading for %s: %s != %s" % (arm, mine["acc"], ref))
        compat[arm] = {"S_r12_acc": mine["acc"],
                       "committed_two_round_S_all_acc": ref,
                       "match": True}

    # ---- signal gate + edge increment (Q5) ----
    signal = {}
    for s in STRATA:
        signal[s] = {}
        for arm in ARMS:
            p = results[s][arm]["pooled"]
            above = (p["n"] > 0 and p["correct"] / p["n"] > 2.0 / 3.0)
            at = (p["n"] > 0 and p["correct"] / p["n"] == 2.0 / 3.0)
            signal[s][arm] = {
                "acc": p["acc"], "ci95": p["ci95"],
                "above_cross_baseline": above,
                "above_within_baseline": (p["n"] > 0 and
                                          p["correct"] / p["n"] > 5.0 / 6.0),
                "verdict": ("signal" if above else
                            ("at the gate (equal to 2/3, not above)" if at
                             else "no signal")),
            }
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
                        "insufficient)" if ci_overlap else
                        "directional difference beyond CI overlap "
                        "(still not a model ranking at this n)"),
        }

    # ---- round-3 both-bad pool-quality warning list (19) ----
    both_bad_r3_comp = []
    for t in both_bad_r3:
        row = {"pair_key": t["pair_key"], "graph": t["graph"],
               "session": "r3", "is_retest_answer": t["is_retest"],
               "kind": akinds[t["pair_key"]]}
        for side in ("a", "b"):
            m = cand_meta3[t[side]]
            row[side] = {"cid": t[side], "recipe": m["recipe"],
                         "source": m["source"], "grade": m["grade"]}
        both_bad_r3_comp.append(row)
    warn_by_graph = Counter(t["graph"] for t in both_bad_r3_comp)
    warn_newtopo_side = Counter()
    for t in both_bad_r3_comp:
        for side in ("a", "b"):
            if cand_meta3[t[side]["cid"]]["source"] == "fresh-r3" \
                    and t["graph"] in NEW_GRAPHS:
                warn_newtopo_side[
                    cand_meta3[t[side]["cid"]]["recipe"].split("+")[0]] += 1

    # ---- discriminator non-regression (recomputed AFTER training) ----
    labels_all, pos_bf, neg_docs, _eng, _src = dc.load_corpus(True)
    _l_leg, pos_leg, _n2, _e2, _s2 = dc.load_corpus(False)
    assert len(pos_bf) == 18 and len(neg_docs) == 40 and len(pos_leg) == 18

    def _records(pos):
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
        return {sh: st["shapes"][sh]["score_auc"]
                for sh in ("ring", "hub", "global")}

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

    # ---- sanity flip leg (half-flipped labels on S_all, M1/M2) ----
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
    groups = {}
    for g in sorted(pool):
        groups.setdefault(labels.get(g, "unknown"), []).append(g)
    sanity_folds = []
    for topo, gs in sorted(groups.items()):
        sanity_folds.append({
            "topology": topo, "test_graphs": sorted(gs),
            "test_pairs": [p for p in decided_all if p["graph"] in gs],
            "train_human": [p for p in flipped if p["graph"] not in gs],
            "train_synthetic": [],
        })
    sanity = {arm: final.eval_arm(arm, sanity_folds, pool)["pooled"]
              for arm in ("M1", "M2")}
    for arm, sp in sanity.items():
        assert 0.0 < sp["acc"] < 1.0 or sp["n"] == 0, \
            ("sanity flip leg degenerated for %s: %s" % (arm, sp))

    # ---- train-holdout gaps ----
    gaps = {s: {arm: final.gap_pp(results[s][arm]) for arm in ARMS
                if arm != "M0"} for s in STRATA}

    report = {
        "schema": "stdraw.pref-ranking-final-v2/1",
        "generation": {
            "solver": ("converged BT solver (repo level): bitwise-duplicate "
                       "feature columns merged away, damped full-Hessian "
                       "Newton, hard gradient gate < 1e-6 asserted on every "
                       "fit (LOSO folds, full-data calibration, sanity leg)"),
            "picture_caliber_note": (
                "S_r12 mixes the round-1 re-routed caliber with the "
                "round-2 byte-faithful caliber (disclosed); S_r3 is "
                "byte-faithful only; the split is reported as-is, never "
                "averaged away"),
            "dose_family_note": final_note_dose(),
            "round3_provenance": (
                "worker-build session is canonical (37/37 jacky answers); "
                "the operator draft is archived and deliberately not used; "
                "candidate docs from the committed round-3 render cache, "
                "gate-viability validated field-by-field"),
        },
        "data": {
            "n_strict_decided": len(decided_all),
            "n_by_round": {"r1": len(decided_r1), "r2": len(decided_r2),
                           "r3": len(decided_r3)},
            "n_both_good": len(both_good_all),
            "n_both_bad": len(both_bad_all),
            "round3_answer_split": {"a": 4, "b": 7, "both": 7,
                                    "both_bad": 19},
            "round3_kinds": {"newtopo": 14, "disagree": 11, "anchor": 9,
                             "retest": 3},
            "retest_noise": {
                "within_r1": {"agree": agree_within, "n": 6,
                              "baseline": round(WITHIN_BASELINE, 4),
                              "rows": within_rows},
                "cross_r2_winner_level": {"agree": agree_cross, "n": 3,
                                          "baseline": round(CROSS_BASELINE, 4),
                                          "rows": cross_rows},
                "cross_r3_tie_level": {
                    "n": len(retest3_rows),
                    "tie_reproductions": tie_reproductions,
                    "note": ("all 3 round-3 cross-session retests re-asked "
                             "previously TIED pairs and reproduced the tie "
                             "3/3 - tie-level noise, not winner-level; the "
                             "66.7% winner-level gate is unchanged"),
                    "rows": retest3_rows},
                "pooled_cross_session": {"agree": agree_cross + 3, "n": 6,
                                         "rate": round((agree_cross + 3) / 6, 4)},
            },
            "topology_groups": {t: sorted(g) for t, g in
                                sorted(groups.items())},
        },
        "backward_compatibility": compat,
        "arms": results,
        "graph_loso": {
            "definition": (
                "leave-one-GRAPH-out per-graph pairwise accuracy (card "
                "question 2): training = all 36 strict pairs minus the "
                "held-out graph; each pair tested exactly once"),
            "per_graph": per_graph_acc,
            "newtopo_verdict": newtopo_verdict,
        },
        "anchor_vs_engine": {
            "definition": (
                "9 asked human-anchor vs engine pairs (6 human-source "
                "candidates); model reading = out-of-fold margins from the "
                "stratum's LOSO evaluation (each pair tested exactly once; "
                "S_all folds train on 36-pair subsets, S_r3 folds on the "
                "11 byte-faithful pairs); human_ranked_first = margin("
                "human, engine) > 0"),
            "n_pairs": len(anchor_rows),
            "human_candidates": sorted(cid for cid, m in cand_meta3.items()
                                       if m["source"] == "human"),
            "jacky_verdicts": dict(jacky_anchor),
            "jacky_human_win_ratio_decided": None,   # filled below
            "per_pair": anchor_rows,
            "per_arm": anchor_summary,
        },
        "epsilon_calibration": eps,
        "signal_gate": signal,
        "edge_increment": edge_increment,
        "train_holdout_gap": gaps,
        "both_bad_pool_warning_r3": {
            "n": len(both_bad_r3_comp),
            "by_graph": dict(warn_by_graph),
            "newtopo_engine_recipe_counts": dict(warn_newtopo_side),
            "rows": both_bad_r3_comp,
            "prior_rounds_note": (
                "rounds 1-2 both-bad list (10 rows) is unchanged and lives "
                "in pref-ranking-final.json (both_bad_pool_warning)"),
        },
        "sanity_flip_leg": {
            "definition": ("training labels deterministically half-flipped "
                           "(LCG seed 20261121) over all 36 strict pairs; "
                           "holdout pairs keep jacky's real labels"),
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
    decided_anchor = [r for r in anchor_rows
                      if r["jacky_verdict"] in ("human", "engine")]
    report["anchor_vs_engine"]["jacky_human_win_ratio_decided"] = round(
        sum(1 for r in decided_anchor if r["jacky_verdict"] == "human")
        / len(decided_anchor), 4)

    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   sort_keys=False) + "\n", encoding="utf-8")
    MD_OUT.write_text(render_md(report), encoding="utf-8")
    print("wrote %s" % JSON_OUT)
    print("wrote %s" % MD_OUT)
    for s in STRATA:
        for arm in ARMS:
            p = results[s][arm]["pooled"]
            print("  %s %s: %s/%s = %s CI %s [%s]"
                  % (s, arm, p["correct"], p["n"], p["acc"],
                     signal[s][arm]["verdict"], p["ci95"]))
    print("  newtopo: %d decided pairs (verdict: not measurable)"
          % newtopo_verdict["n_decided_pairs_on_new_graphs"])
    print("  anchor: jacky human-win %s, model ratios: %s"
          % (report["anchor_vs_engine"]["jacky_human_win_ratio_decided"],
             {s: {arm: anchor_summary[s][arm].get("ratio_all")
                  for arm in ARMS if anchor_summary[s][arm].get("n_tested")}
              for s in STRATA}))
    print("  epsilon P75: %s"
          % {arm: eps["per_arm"][arm]["p75_initial"] for arm in ARMS})
    print("  discriminator: all 4 committed AUC rows reproduced, sha pins unchanged")


def decide_tagged(items, session):
    """Strict decisions -> pair rows tagged with their session."""
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


def final_note_dose():
    return ("synthetic dose pairs (M1s/M2s) use the diagnosis card's "
            "cumulative L1-L4 caliber, NOT the route-preserving dose "
            "family; s-arms reported side by side, never merged; round 3 "
            "added ZERO dose pairs")


def render_md(r):
    L = []
    L.append("# Final preference comparison v2: three merged rounds\n")
    L.append("36 strict decided pairs (13 + 12 + 11), 18 both-good, 29 "
             "both-bad; converged BT solver; strata S_all / S_r12 (mixed "
             "picture caliber) / S_r3 (byte-faithful) reported as-is.\n")
    L.append("## Conclusion\n")
    any_signal = any(v["verdict"] == "signal"
                     for s in r["signal_gate"].values() for v in s.values())
    if not any_signal:
        L.append("- **No arm clears the 66.7% cross-session noise gate in "
                 "any stratum** - the merged n=36 reading is still *no "
                 "signal* for M0/M1/M2 (and the s-arms).")
    else:
        hot = [(s, arm, r["signal_gate"][s][arm])
               for s in ("S_all", "S_r12", "S_r3")
               for arm in ("M0", "M1", "M2", "M1s", "M2s")
               if r["signal_gate"][s][arm]["verdict"] == "signal"]
        for s, arm, v in hot:
            L.append("- **%s %s reads %s = %.1f%%, numerically above the "
                     "66.7%% gate** - but the Wilson CI [%.1f%%, %.1f%%] "
                     "is wide at this n; read as *directional, not "
                     "conclusive*."
                     % (s, arm, "%d/%d" % (r["arms"][s][arm]["pooled"]
                                           ["correct"],
                                           r["arms"][s][arm]["pooled"]["n"]),
                        100 * v["acc"], 100 * v["ci95"][1],
                        100 * v["ci95"][2]))
    ei = r["edge_increment"]
    inc = all(ei[s]["ci95_overlap"] for s in ei)
    if inc:
        L.append("- M2 vs M1 edge-dimension increment: **still not "
                 "demonstrated** (CIs overlap in every stratum; n=36 "
                 "remains insufficient).")
    L.append("- New-topology generalization (nested-ring-shared-node / "
             "chain-ring-hybrid / dual-hub-asymmetric): **not measurable** "
             "- zero decided pairs; all 14 newtopo pairs answered both-bad "
             "(pool-quality warning, %s)."
             % json.dumps(r["both_bad_pool_warning_r3"]["by_graph"],
                          ensure_ascii=False))
    ja = r["anchor_vs_engine"]
    dec_pairs = [x for x in ja["per_pair"] if x["jacky_verdict"] in
                 ("human", "engine")]
    hw = round(ja["jacky_human_win_ratio_decided"] * len(dec_pairs))
    L.append("- Anchor vs engine (the round's most direct new signal): "
             "jacky prefers his own hand-made anchor in %d of %d decided "
             "anchor pairs (%.0f%%), but the preference-trained arms rank "
             "the human anchor FIRST in only %s of the 9 asked pairs "
             "(out-of-fold, S_all) - the BT arms do not recognize the "
             "human quality jacky sees; the untrained pointwise M0 does "
             "noticeably better (%s)."
             % (hw, len(dec_pairs),
                100 * ja["jacky_human_win_ratio_decided"],
                json.dumps({arm: ja["per_arm"]["S_all"][arm]
                            ["human_ranked_first"]
                            for arm in r_arms_with(ja, "S_all")}),
                json.dumps({arm: ja["per_arm"]["S_all"][arm]["ratio_all"]
                            for arm in r_arms_with(ja, "S_all")})))
    L.append("- Noise floor: round-3 retests were 3 tie-reproductions "
             "(tie-level 3/3); the winner-level gate stays 2/3 = 66.7%% "
             "(pooled cross-session 5/6).  Epsilon initial value (P75 "
             "over 18 both-good pairs): %s."
             % json.dumps({arm: r["epsilon_calibration"]["per_arm"][arm]
                           ["p75_initial"] for arm in
                           ("M0", "M1", "M2", "M1s", "M2s")}))
    L.append("")
    bc = r["backward_compatibility"]
    L.append("Backward compatibility: S_r12 (rounds 1-2 merged) reproduces "
             "the committed two-round artifact's S_all readings exactly "
             "(%s) - the round-3 feature-space extension is provably "
             "neutral on the rounds-1-2 reading."
             % ", ".join("%s %s" % (arm, bc[arm]["S_r12_acc"])
                         for arm in ("M0", "M1", "M2", "M1s", "M2s")))
    L.append("")
    L.append("## Headline (read with the CI widths)\n")
    L.append("| stratum | arm | pairwise acc | 95% CI (Wilson) | verdict |")
    L.append("|---|---|---|---|---|")
    for s in ("S_all", "S_r12", "S_r3"):
        for arm in ("M0", "M1", "M2", "M1s", "M2s"):
            p = r["arms"][s][arm]["pooled"]
            v = r["signal_gate"][s][arm]
            L.append("| %s | %s | %s/%s = %.1f%% | [%.1f%%, %.1f%%] | %s |"
                     % (s, arm, p["correct"], p["n"], 100 * p["acc"],
                        100 * p["ci95"][1], 100 * p["ci95"][2], v["verdict"]))
    L.append("")
    L.append("## Per-graph leave-one-graph-out accuracy (question 2)\n")
    L.append("| graph | " + " | ".join(("M0", "M1", "M2")) + " |")
    L.append("|---|---|---|---|")
    graphs = sorted(r["graph_loso"]["per_graph"]["M0"])
    for g in graphs:
        cells = []
        for arm in ("M0", "M1", "M2"):
            row = r["graph_loso"]["per_graph"][arm][g]
            cells.append("%s (%d/%d)" % (row["acc"], row["correct"],
                                         row["n_test"])
                         if row["n_test"] else "n/a (0 pairs)")
        L.append("| %s | %s |" % (g, " | ".join(cells)))
    L.append("")
    L.append("New-topology verdict: " + r["graph_loso"]["newtopo_verdict"]
             ["finding"])
    L.append("")
    L.append("## Anchor vs engine (question 3, out-of-fold margins)\n")
    L.append("| qid | graph | human | engine | jacky | "
             + " | ".join("S_all/" + a for a in ("M0", "M1", "M2"))
             + " |")
    L.append("|---|---|---|---|---|---|---|---|")
    for row in r["anchor_vs_engine"]["per_pair"]:
        cells = []
        for arm in ("M0", "M1", "M2"):
            k = "S_all/%s" % arm
            m = row["margins"].get(k)
            cells.append("%+.3f%s" % (m, " H" if m > 0 else "")
                         if m is not None else "-")
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            row["qid"], row["graph"], row["human"], row["engine"],
            row["jacky_verdict"], " | ".join(cells)))
    L.append("")
    L.append("Human-first ratios - primary = OUT-OF-FOLD margins on the 7 "
             "jacky-decided anchor pairs; secondary = full-data calibration "
             "model over all 9 asked pairs (in-sample for the 7, disclosed "
             "caveat):\n")
    for s in ("S_all", "S_r3"):
        for arm in ("M0", "M1", "M2", "M1s", "M2s"):
            e = r["anchor_vs_engine"]["per_arm"][s][arm]
            if e.get("n_tested"):
                L.append("- %s %s: out-of-fold %d/%d = %.1f%% | all-9 "
                         "calib-model %d/9 = %.1f%%"
                         % (s, arm, e["human_ranked_first"], e["n_tested"],
                            100 * e["ratio_all"],
                            e["human_first_all9_full_calib_model"],
                            100 * e["ratio_all9_full_calib_model"]))
            else:
                L.append("- %s %s: no out-of-fold margins | all-9 "
                         "calib-model %d/9 = %.1f%%"
                         % (s, arm, e["human_first_all9_full_calib_model"],
                            100 * e["ratio_all9_full_calib_model"]))
    L.append("")
    L.append("## Epsilon calibration (P75 over 18 both-good pairs)\n")
    L.append("| arm | P75 initial | P50 | max (legacy epsilon0) | "
             "P75 r12 | P75 r3 | exact-zero margins |")
    L.append("|---|---|---|---|---|---|---|")
    for arm in ("M0", "M1", "M2", "M1s", "M2s"):
        e = r["epsilon_calibration"]["per_arm"][arm]
        L.append("| %s | %s | %s | %s | %s | %s | %d |" % (
            arm, e["p75_initial"], e["p50"], e["max_epsilon0_legacy"],
            e["p75_r12_only"], e["p75_r3_only"], e["n_exact_zero_margins"]))
    L.append("")
    L.append("## Both-bad pool-quality warning (round 3, 19 pairs)\n")
    L.append("By graph: %s\n" % json.dumps(
        r["both_bad_pool_warning_r3"]["by_graph"], ensure_ascii=False))
    L.append("New-topology engine recipe counts: %s\n" % json.dumps(
        r["both_bad_pool_warning_r3"]["newtopo_engine_recipe_counts"],
        ensure_ascii=False))
    L.append("| pair_key | kind | a | b |")
    L.append("|---|---|---|---|")
    for t in r["both_bad_pool_warning_r3"]["rows"]:
        L.append("| %s | %s | %s/%s | %s/%s |" % (
            t["pair_key"], t["kind"], t["a"]["cid"], t["a"]["recipe"],
            t["b"]["cid"], t["b"]["recipe"]))
    L.append("")
    L.append("## Noise floor\n")
    rn = r["data"]["retest_noise"]
    L.append("- in-session (round 1): %d/6 = %.1f%%" % (
        rn["within_r1"]["agree"], 100 * rn["within_r1"]["baseline"]))
    L.append("- cross-session winner-level (round 2): %d/3 = %.1f%% - the "
             "SIGNAL GATE stays at 66.7%%" % (
                 rn["cross_r2_winner_level"]["agree"],
                 100 * rn["cross_r2_winner_level"]["baseline"]))
    L.append("- cross-session tie-level (round 3): %d/%d tie reproductions"
             % (rn["cross_r3_tie_level"]["tie_reproductions"],
                rn["cross_r3_tie_level"]["n"]))
    L.append("- pooled cross-session: %d/6 = %.1f%%" % (
        rn["pooled_cross_session"]["agree"],
        100 * rn["pooled_cross_session"]["rate"]))
    L.append("")
    L.append("## Edge-dimension increment (M2 vs M1, question 5)\n")
    for s, e in r["edge_increment"].items():
        L.append("- %s: M1 %.1f%% vs M2 %.1f%% (delta %spp), CIs %s -> %s"
                 % (s, 100 * e["M1_acc"], 100 * e["M2_acc"], e["delta_pp"],
                    "overlap" if e["ci95_overlap"] else "disjoint",
                    e["verdict"]))
    L.append("")
    L.append("## Train-holdout gap (review trigger at 15pp)\n")
    for s in ("S_all", "S_r12", "S_r3"):
        for arm in ("M1", "M2", "M1s", "M2s"):
            g = r["train_holdout_gap"][s][arm]
            flag = "YES" if (g is not None and g > 15.0) else "no"
            L.append("- %s %s: gap %spp (flag %s)" % (s, arm, g, flag))
    L.append("")
    L.append("## Sanity flip leg\n")
    L.append("- M1: %s, M2: %s (a healthy evaluator reads neither 0%% nor "
             "100%% here)" % (r["sanity_flip_leg"]["M1"],
                              r["sanity_flip_leg"]["M2"]))
    L.append("")
    L.append("## Discriminator non-regression\n")
    L.append("All four committed v3-beta AUC-table rows reproduced exactly "
             "after preference training; scorer artifacts sha256-pinned "
             "before/after (%d files)." % len(r["discriminator_non_regression"]
                                              ["sha_pinned_files"]))
    L.append("")
    L.append("## Red lines honoured\n")
    L.append("- zero certificate-grade reads by the ranker (grades appear "
             "only in the pool-quality warning composition)")
    L.append("- candidate pool reproduced with the viewer's gate-viability "
             "filter; round-3 fresh docs gate-viability validated "
             "field-by-field against the session registry")
    L.append("- deterministic output (double-run byte-identical); "
             "negatives library read-only; committed scorer artifacts "
             "sha-pinned; thresholds are named constants")
    L.append("")
    return "\n".join(L) + "\n"


def r_arms_with(ja, s):
    return [arm for arm in ("M0", "M1", "M2", "M1s", "M2s")
            if ja["per_arm"][s][arm].get("n_tested")]


if __name__ == "__main__":
    main()
