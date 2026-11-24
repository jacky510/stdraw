#!/usr/bin/env python
"""Round-3 pairwise preference annotation tool: new topologies + anchor pairs +
zero dose pairs ("pref-round3").

Differences vs round 2 (all three proven signal types, NO dose pairs):

  1. New topology sources (2-3 graphs, n=8-10, under
     benchmarks/manual/pref-round3/sources/): pure nested-ring variant
     (inner ring shares ONE node with the outer ring), chain+ring hybrid,
     asymmetric dual-hub.  Each graph gets 4-6 diverse engine candidates
     from a fixed recipe x pitch ladder (all passing the hard viability
     gate: min card gap >= 16px AND zero true box-press).
  2. Old-graph pools are widened with the same recipe x pitch ladder
     (rounds 1+2 exhausted every unasked pool-pool pair; probe verified 0
     remaining).  New information comes from:
       - anchor-vs-engine pairs (the user's human anchor vs fresh engine
         candidates of the same graph - the direct preference signal
         missing from rounds 1-2);
       - model-disagreement pairs: candidates (pool + extension) scored
         OFFLINE with the committed arms M0/M1/M2 (v2 pointwise score +
         BT margins refit on the committed 25 decided pair labels);
         selection-only use, committed analysis artifacts untouched.
  3. Zero dose pairs: the synthetic perturbation ladder is not loaded at
     all (hard-asserted in the self-check).
  4. Cross-session retests: 2 round-2-only both-good ties + 1 tie already
     asked in BOTH rounds (a third observation grows the cross-session
     noise baseline that the final comparison flagged as the binding gate).
  5. Byte-faithful rendering (spotfix slim_doc caliber: anchors / waypoints
     / styles replayed through --from-layout) and deterministic LCG
     orchestration (recorded seed; double-run byte-identical).

Record fields per exported item are identical to rounds 1-2: qid / graph /
candidate_a / candidate_b / left_is_a / is_retest / pair_key /
model_version / choice / duration_ms.

Red lines honored: no dose pairs enter the question set; preference data
and source labels are stored separately (candidates.json is never
referenced by viewer.html); scorer/ranker artifacts untouched (offline
scoring is selection-only); deterministic output; no internal ids or
absolute paths in tracked outputs.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import pref_pipeline as pp  # noqa: E402  (pool, renderer, LCG — read-only reuse)
import pref_ranking_m0m1m2 as pr  # noqa: E402  (offline scoring machinery)

SRC_DIR = REPO / "benchmarks" / "manual" / "pref-round3" / "sources"
CACHE = pp.BUILD_ROOT / "round3"
R1_SESSION = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-21"
R2_SESSION = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-22-round2"
SESSION_ID = "2026-11-22-round3"
SESSION_DIR = REPO / "benchmarks" / "manual" / "pairwise" / ("session-" + SESSION_ID)
OUT_SELECTION = REPO / "benchmarks" / "aesthetic" / "pref-round3-selection.json"
MODEL_VERSION = "aesthetic-v2"  # record-field parity with rounds 1-2
LCG_SEED = 20261123  # recorded; question order reproducible from this

NEW_GRAPHS = ("nested-ring-shared-node", "chain-ring-hybrid", "dual-hub-asymmetric")
PY = sys.executable

# source variants per new graph: A = committed source, B = committed
# declaration-reordered variant (same graph structure, deterministic
# different engine tie-breaking -> genuinely diverse layouts)
SOURCES = ("A", "B")


def source_files(graph):
    if graph in NEW_GRAPHS:
        return {"A": SRC_DIR / (graph + ".cld"),
                "B": SRC_DIR / (graph + "-alt.cld")}
    src = pp.source_cld_for(graph)
    return {"A": src, "B": src}


# recipe x source x pitch ladders (fixed order; keep the first
# gate-passing non-duplicate entries)
LADDER_NEW = (("A", "auto", None, 68), ("A", "ortho", None, 80),
              ("A", "candidate-v1", None, 56), ("B", "auto", None, 68),
              ("B", "ortho", None, 80), ("A", "auto", "arc", 68),
              ("B", "candidate-v1", None, 68))
LADDER_OLD = (("A", "auto", None, 68), ("A", "ortho", None, 80),
              ("A", "candidate-v1", None, 56), ("A", "auto", "arc", 68),
              ("A", "auto", None, 72))
N_NEW_CANDS_MAX = 6   # per new topology graph
N_NEW_CANDS_MIN = 4
N_EXT_CANDS_MAX = 3   # per old graph

# question allocation (card ranges; total 38 <= 45 min budget)
N_NEWTOPO = 14        # 12-18, spread evenly over the 3 new graphs
N_DISAGREE = 11       # 10-15, model-uncertain old-graph engine pairs
N_ANCHOR = 9          # 8-12, human anchor vs engine candidate
N_RETEST = 3          # 2-3, cross-session re-asks of round-2 answered pairs
N_TOTAL = N_NEWTOPO + N_DISAGREE + N_ANCHOR + N_RETEST
DISAGREE_GRAPH_CAP = 3
DISAGREE_GRAPH_FLOOR = 2
ANCHOR_GRAPH_CAP = 3
ANCHOR_GRAPH_FLOOR = 1
ARMS3 = ("M0", "M1", "M2")


# ── engine candidate generation (fixed ladders, hard gate, dedupe) ─────────

def run_recipe(source_cld, outdir, recipe, pitch, linestyle):
    outdir = Path(outdir)
    lj, cj = outdir / "layout.json", outdir / "certificate.json"
    if not (lj.exists() and cj.exists()):
        cmd = [PY, "-m", "stdraw", "layout", str(source_cld),
               "--outdir", str(outdir), "--recipe", recipe,
               "--pitch", str(pitch)]
        if linestyle:
            cmd += ["--linestyle", linestyle]
        r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not (lj.exists() and cj.exists()):
            return None, ((r.stderr or "") + (r.stdout or ""))[-200:]
    d = json.loads(lj.read_text(encoding="utf-8"))
    c = json.loads(cj.read_text(encoding="utf-8"))
    return (d, c), None


def doc_fingerprint(doc):
    return hashlib.sha256(json.dumps(pp.slim_doc(doc), sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")
                          ).hexdigest()[:16]


def ladder_candidates(graph, ladder, seen_prints, prefix, cap):
    """Gate-passing, deduped engine candidates from the fixed ladder.
    seen_prints: fingerprints already used for THIS graph (pool first).
    Returns (cands, ladder_report)."""
    srcs = source_files(graph)
    cands, reports = [], []
    for src_tag, recipe, ls, pitch in ladder:
        if len(cands) >= cap:
            reports.append({"src": src_tag, "recipe": recipe, "pitch": pitch,
                            "status": "cap-reached"})
            continue
        outdir = CACHE / ("cand.%s.%s.%s.%s.p%d"
                          % (graph, src_tag, recipe, ls or "straight", pitch))
        got, err = run_recipe(srcs[src_tag], outdir, recipe, pitch, ls)
        if got is None:
            reports.append({"src": src_tag, "recipe": recipe, "pitch": pitch,
                            "status": "cli-failed", "detail": err})
            continue
        doc, cert = got
        doc.setdefault("graph", graph)
        ok, gcert = pp.gate_viability(doc, graph)
        fp = doc_fingerprint(doc)
        if not ok:
            reports.append({"src": src_tag, "recipe": recipe, "pitch": pitch,
                            "status": "gate-rejected",
                            "min_card_gap": gcert["metrics"]["min_card_gap"]})
            continue
        if fp in seen_prints:
            reports.append({"src": src_tag, "recipe": recipe, "pitch": pitch,
                            "status": "duplicate-of-existing"})
            continue
        seen_prints.add(fp)
        cid = "%sg0c%d" % (prefix, len(cands))
        cands.append({"cid": cid, "doc": doc, "source": "fresh-r3",
                      "recipe": "%s+%s@%d" % (recipe, src_tag, pitch)
                      + ("+arc" if ls == "arc" else ""),
                      "grade": cert.get("grade", "-"),
                      "gap": gcert["metrics"]["min_card_gap"],
                      "crossings": gcert["metrics"]["crossings"]})
        reports.append({"src": src_tag, "recipe": recipe, "pitch": pitch,
                        "status": "candidate", "cid": cid,
                        "grade": cert.get("grade", "-"),
                        "gap": round(gcert["metrics"]["min_card_gap"], 1)})
    return cands, reports


def collect_new_graph_candidates():
    out, reports = {}, {}
    for gi, g in enumerate(NEW_GRAPHS, 1):
        for tag, p in source_files(g).items():
            assert p.exists(), p
        seen = set()
        cands, report = ladder_candidates(g, LADDER_NEW, seen,
                                          "r3n%d" % gi, N_NEW_CANDS_MAX)
        assert len(cands) >= N_NEW_CANDS_MIN, (g, len(cands), report)
        out[g] = cands
        reports[g] = report
    return out, reports


def collect_old_extension(pool_by_graph):
    out, reports = {}, {}
    for gi, g in enumerate(pp.VIEWER_GRAPHS, 1):
        seen = {doc_fingerprint(c["doc"]) for c in pool_by_graph[g]}
        cands, report = ladder_candidates(g, LADDER_OLD, seen,
                                          "r3e%d" % gi, N_EXT_CANDS_MAX)
        out[g] = cands
        reports[g] = report
    return out, reports


# ── offline arm scoring over the widened old-graph pool (selection only) ───

def load_decided_merged():
    """Decided pairs from BOTH committed rounds (winner/loser form)."""
    out = []
    for sess in (R1_SESSION, R2_SESSION):
        a = json.loads((sess / ("answers-" +
                                ("2026-11-21" if sess is R1_SESSION
                                 else "2026-11-22") + ".json"))
                       .read_text(encoding="utf-8"))
        items = a["items"] if isinstance(a, dict) and "items" in a else a
        for it in items:
            if it.get("is_retest"):
                continue
            w = pr.pair_winner(it)
            if w in (it["candidate_a"], it["candidate_b"]):
                l = (it["candidate_b"] if w == it["candidate_a"]
                     else it["candidate_a"])
                out.append({"graph": it["graph"], "a": it["candidate_a"],
                            "b": it["candidate_b"], "winner": w, "loser": l})
    return out


class OfflineArms:
    """M0/M1/M2 margins over pool + extension candidates of the old graphs.

    Selection-only: the committed LOSO/final artifacts are read as data and
    never rewritten.  The BT refits here use the committed 25 decided pair
    labels; the global feature-name union covers the extension candidates,
    which only APPENDS impute-median constants for the pool candidates'
    training diffs (their pair diffs are unchanged)."""

    def __init__(self, pool_by_graph, ext_by_graph):
        labels = pr.load_family_labels(str(pr.FAMILY_MAP))
        model_v2 = json.loads((pr.REPO / "stdraw" / "data" / "model-v2.json")
                              .read_text(encoding="utf-8"))
        model_v3 = json.loads((pr.OUT_DIR / "model-v3-alpha.json")
                              .read_text(encoding="utf-8"))
        kept_v3 = list(json.loads(
            (pr.OUT_DIR / "lasso-path-v3-alpha.json").read_text(encoding="utf-8")
        )["selected"]["kept"])
        bank = pr.FeatureBank(pool_by_graph, labels, model_v2, model_v3,
                              kept_v3)
        self.docs = {}
        for g, cands in pool_by_graph.items():
            for c in cands:
                self.docs[c["cid"]] = (g, c["doc"])
        for g, cands in ext_by_graph.items():
            for c in cands:
                bank.add_doc(c["cid"], g, c["doc"])
                self.docs[c["cid"]] = (g, c["doc"])
        # global feature-name union over EVERY banked candidate (main()'s
        # caliber, extended to the extension cids)
        for featname in ("v2", "v3"):
            names = []
            for cid in sorted(bank._model_names):
                for nm in bank._model_names[cid][featname]:
                    if nm not in names:
                        names.append(nm)
            pr.NAMES_GLOBAL[featname] = names
        self.bank = bank
        scorer_v2 = pp.dc.Scorer(model_v2, labels)
        self.m0 = {}
        for cid, (g, doc) in self.docs.items():
            sc, _shape, _row = scorer_v2.score(doc, g)
            self.m0[cid] = sc
        decided = [p for p in load_decided_merged()
                   if p["winner"] in self.docs and p["loser"] in self.docs]
        # selection-only caliber: all committed decided labels from both
        # rounds restricted to pool candidates; round-2 pool x synthetic
        # (dose) pairs are excluded here as everywhere in this round
        # (rounds 1-2 left only 15 pool-pool decided labels)
        assert len(decided) >= 15, len(decided)
        self.n_decided = len(decided)
        self.models = {"M1": pr.train_bt(bank, "v2", decided),
                       "M2": pr.train_bt(bank, "v3", decided)}

    def margin(self, arm, ca, cb):
        """>0: ca preferred; <0: cb preferred; 0: exact tie."""
        if arm == "M0":
            return self.m0[ca] - self.m0[cb]
        names = pr.NAMES_GLOBAL[pr.FEAT_OF_ARM[arm]]
        va = self.bank.vector(ca, names, pr.FEAT_OF_ARM[arm])
        vb = self.bank.vector(cb, names, pr.FEAT_OF_ARM[arm])
        return pr.bt_margin(self.models[arm], va, vb)

    def votes(self, ca, cb):
        va = vb = half = 0
        for arm in ARMS3:
            m = self.margin(arm, ca, cb)
            if m > 0:
                va += 1
            elif m < 0:
                vb += 1
            else:
                half += 1
        return va, vb, half


# ── asked-pair bookkeeping ─────────────────────────────────────────────────

def load_asked():
    asked = {}
    for sess in (R1_SESSION, R2_SESSION):
        q = json.loads((sess / "questions.json").read_text(encoding="utf-8"))
        for x in q["questions"]:
            asked[x["pair_key"]] = asked.get(x["pair_key"], 0) + 1
    return asked


def pair_key(g, ca, cb):
    return "%s|%s|%s" % (g, min(ca, cb), max(ca, cb))


def load_round2_ties():
    a = json.loads((R2_SESSION / "answers-2026-11-22.json")
                   .read_text(encoding="utf-8"))
    items = a["items"] if isinstance(a, dict) and "items" in a else a
    choice = {i["qid"]: i["choice"] for i in items}
    q = json.loads((R2_SESSION / "questions.json").read_text(encoding="utf-8"))
    asked_r1 = set()
    q1 = json.loads((R1_SESSION / "questions.json").read_text(encoding="utf-8"))
    asked_r1 = {x["pair_key"] for x in q1["questions"]}
    ties, per_graph = [], {}
    for x in q["questions"]:
        if choice.get(x["qid"]) != "both":
            continue
        pk = x["pair_key"]
        g = x["graph"]
        n = per_graph.get(g, 0)
        if n >= 2:
            continue  # deterministic per-graph cap
        ties.append({"pair_key": pk, "graph": g, "a": x["candidate_a"],
                     "b": x["candidate_b"],
                     "asked_in_round1": pk in asked_r1})
        per_graph[g] = n + 1
    # round-2-only ties first, then both-rounds ties (3rd observation);
    # deterministic order inside each group
    ties.sort(key=lambda t: (t["asked_in_round1"], t["pair_key"]))
    return ties[:N_RETEST]


# ── selection ──────────────────────────────────────────────────────────────

def even_pairs(cands, k):
    """Deterministic k pairs evenly covering the candidate list
    (pref_pipeline.pick_pairs caliber, candidate-order pool)."""
    idx = list(range(len(cands)))
    return [(cands[i], cands[j])
            for i, j in pp.pick_pairs(idx, k)]


def select_newtopo(new_by_graph):
    rows, per_graph = [], {}
    for g in NEW_GRAPHS:
        cands = new_by_graph[g]
        pairs = even_pairs(cands, N_NEWTOPO // len(NEW_GRAPHS)
                           + (1 if NEW_GRAPHS.index(g) < N_NEWTOPO
                              % len(NEW_GRAPHS) else 0))
        for ca, cb in pairs:
            rows.append({"graph": g, "a": ca["cid"], "b": cb["cid"],
                         "kind": "newtopo",
                         "pair_key": pair_key(g, ca["cid"], cb["cid"])})
        per_graph[g] = len(pairs)
    assert len(rows) == N_NEWTOPO
    return rows, per_graph


def select_old_pairs(pool_by_graph, ext_by_graph, arms, asked):
    anchor_rows, disagree_rows = [], []
    for g in pp.VIEWER_GRAPHS:
        pool = pool_by_graph[g]
        ext = ext_by_graph[g]
        humans = [c for c in pool if c["source"] == "human"]
        engines_old = [c for c in pool if c["source"] != "human"]
        engines = engines_old + ext
        # anchor vs engine (unasked only; every remaining anchor pair
        # necessarily involves an extension candidate)
        for h in humans:
            for e in engines:
                pk = pair_key(g, h["cid"], e["cid"])
                if pk in asked:
                    continue
                anchor_rows.append({"graph": g, "a": h["cid"], "b": e["cid"],
                                    "kind": "anchor", "pair_key": pk,
                                    "engine_is_extension": e in ext})
        # engine vs engine disagreement (at least one extension candidate;
        # pool-pool pairs are all asked - probe verified 0 remaining)
        for ca, cb in itertools.combinations(engines, 2):
            pk = pair_key(g, ca["cid"], cb["cid"])
            if pk in asked:
                continue
            va, vb, half = arms.votes(ca["cid"], cb["cid"])
            split = min(va, vb) + (0.5 if half else 0.0)
            if split <= 0:
                continue
            disagree_rows.append({"graph": g, "a": ca["cid"], "b": cb["cid"],
                                  "kind": "disagree", "pair_key": pk,
                                  "votes": [va, vb], "halves": half,
                                  "split": split,
                                  "involves_extension":
                                      (ca in ext) or (cb in ext)})
    # deterministic greedy: per-graph floor pass then fill under cap,
    # priority = split desc then pair_key
    disagree_rows.sort(key=lambda r: (-r["split"], r["pair_key"]))
    anchor_rows.sort(key=lambda r: (not r["engine_is_extension"],
                                    r["pair_key"]))
    def greedy(rows, total, cap, floor):
        chosen, keys, per = [], set(), {}
        for r in rows:
            g = r["graph"]
            if per.get(g, 0) < floor:
                chosen.append(r)
                keys.add(r["pair_key"])
                per[g] = per.get(g, 0) + 1
        for r in rows:
            if len(chosen) >= total:
                break
            if r["pair_key"] in keys or per.get(r["graph"], 0) >= cap:
                continue
            chosen.append(r)
            keys.add(r["pair_key"])
            per[r["graph"]] = per.get(r["graph"], 0) + 1
        assert len(chosen) == total, (len(chosen), total)
        return chosen, per
    disagree_sel, disagree_per = greedy(disagree_rows, N_DISAGREE,
                                        DISAGREE_GRAPH_CAP,
                                        DISAGREE_GRAPH_FLOOR)
    anchor_sel, anchor_per = greedy(anchor_rows, N_ANCHOR, ANCHOR_GRAPH_CAP,
                                    ANCHOR_GRAPH_FLOOR)
    return disagree_sel, disagree_per, anchor_sel, anchor_per


# ── orchestration ──────────────────────────────────────────────────────────

def build_questions(newtopo_sel, disagree_sel, anchor_sel, retest_sel):
    rnd = pp.lcg(LCG_SEED)
    seq = ([("newtopo", r) for r in newtopo_sel]
           + [("disagree", r) for r in disagree_sel]
           + [("anchor", r) for r in anchor_sel]
           + [("retest", r) for r in retest_sel])
    order = list(range(len(seq)))
    for i in range(len(order) - 1, 0, -1):
        j = next(rnd) % (i + 1)
        order[i], order[j] = order[j], order[i]
    questions = []
    for qn, idx in enumerate(order, 1):
        kind, r = seq[idx]
        questions.append({
            "qid": "q%02d" % qn, "graph": r["graph"],
            "candidate_a": r["a"], "candidate_b": r["b"],
            "left_is_a": bool(next(rnd) % 2),
            "kind": kind, "is_retest": kind == "retest",
            "pair_key": r["pair_key"]})
    return questions


def render_all(questions, docs_by_cid):
    svg_store, cand_meta = {}, {}
    for q in questions:
        for cid in (q["candidate_a"], q["candidate_b"]):
            if cid in svg_store:
                continue
            g, doc, meta = docs_by_cid[cid]
            svg_store[cid] = pp.render_doc_svg(
                source_cld_for(g), doc,
                pp.BUILD_ROOT / "viewer-round3" / cid)
            cand_meta[cid] = {"graph": g, "source": meta["source"],
                              "recipe": meta["recipe"],
                              "grade": meta.get("grade", "-"),
                              "gap": round(meta["gap"], 1),
                              "crossings": meta["crossings"]}
    return svg_store, cand_meta


def source_cld_for(graph):
    if graph in NEW_GRAPHS:
        return SRC_DIR / (graph + ".cld")
    return pp.source_cld_for(graph)


# ── artifacts ──────────────────────────────────────────────────────────────

def selection_record(newtopo_sel, disagree_sel, anchor_sel, retest_sel,
                     questions, new_reports, ext_reports, per_graph,
                     n_decided_labels):
    qsel = []
    for q in questions:
        row = {"qid": q["qid"], "graph": q["graph"], "a": q["candidate_a"],
               "b": q["candidate_b"], "pair_key": q["pair_key"],
               "kind": q["kind"]}
        if q["kind"] == "disagree":
            r = next(x for x in disagree_sel
                     if x["pair_key"] == q["pair_key"])
            row["principles"] = {"arm_votes_M0_M1_M2": r["votes"],
                                 "halves": r["halves"],
                                 "split": r["split"],
                                 "scoring_caliber":
                                     "offline refit of committed arms on "
                                     "the 25 committed decided labels; "
                                     "selection-only"}
        elif q["kind"] == "anchor":
            r = next(x for x in anchor_sel
                     if x["pair_key"] == q["pair_key"])
            row["principles"] = {
                "human_anchor_vs_engine_same_graph": True,
                "engine_is_extension": r["engine_is_extension"]}
        elif q["kind"] == "retest":
            r = next(x for x in retest_sel
                     if x["pair_key"] == q["pair_key"])
            row["principles"] = {
                "cross_session_retest_of_round2_tie": True,
                "asked_in_round1_too": r["asked_in_round1"],
                "note": ("third observation grows the cross-session noise "
                         "baseline" if r["asked_in_round1"]
                         else "round-2-only tie re-asked cross-session")}
        else:
            row["principles"] = {"new_topology_pool_pairs": True,
                                 "engine_ladder_gate_passing": True}
        qsel.append(row)
    return {"schema": "stdraw.pref-round3.selection/1",
            "session": SESSION_ID,
            "note": "round-3 selection - new topology engine pools (hard "
                    "gate), widened old-graph pools, anchor-vs-engine "
                    "pairs, offline-arm disagreement pairs, cross-session "
                    "retests; ZERO dose pairs (perturbation ladder not "
                    "loaded); preference data and source labels stored "
                    "separately",
            "lcg_seed": LCG_SEED, "model_version": MODEL_VERSION,
            "n_newtopo": N_NEWTOPO, "n_disagree": N_DISAGREE,
            "n_anchor": N_ANCHOR, "n_retest": N_RETEST,
            "n_total": N_TOTAL,
            "per_graph_newtopo": per_graph,
            "offline_scoring": {
                "n_decided_pool_labels": n_decided_labels,
                "arms": list(ARMS3),
                "caliber": "committed model files + BT refit on committed "
                           "pool-pool decided labels; selection ranking "
                           "only, committed analysis artifacts untouched"},
            "ladder_reports": {"new": new_reports, "old": ext_reports},
            "questions": qsel}


def write_session(questions, svg_store, cand_meta, selection):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    qs_public = [{k: q[k] for k in ("qid", "graph", "candidate_a",
                                    "candidate_b", "left_is_a",
                                    "is_retest", "pair_key")}
                 for q in questions]
    (SESSION_DIR / "viewer.html").write_text(
        render_viewer_html(qs_public,
                           json.dumps(svg_store, ensure_ascii=False)),
        encoding="utf-8")
    (SESSION_DIR / "questions.json").write_text(
        json.dumps({"schema": "stdraw.pairwise.questions/1",
                    "session": SESSION_ID, "lcg_seed": LCG_SEED,
                    "model_version": MODEL_VERSION,
                    "n_newtopo": N_NEWTOPO, "n_disagree": N_DISAGREE,
                    "n_anchor": N_ANCHOR, "n_retest": N_RETEST,
                    "questions": qs_public},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SESSION_DIR / "candidates.json").write_text(
        json.dumps({"schema": "stdraw.pairwise.candidates/1",
                    "note": "SOURCE LABELS - never render into the viewer "
                            "page; blinding depends on this separation",
                    "candidates": cand_meta},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    OUT_SELECTION.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n", encoding="utf-8")
    (SESSION_DIR / "README.md").write_text(README_TEXT, encoding="utf-8")


VIEWER_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pairwise 盲选 · 第三轮（新拓扑+锚点对）· stdraw 审美偏好标注</title>
<style>
 body{font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;margin:0;background:#f8fafc;color:#1e293b;line-height:1.6}
 .wrap{max-width:1400px;margin:0 auto;padding:20px 16px 60px}
 h1{font-size:20px;margin:0 0 2px}
 .sub{color:#64748b;font-size:13.5px;margin-bottom:14px}
 .bar{display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap}
 .prog{flex:1;min-width:200px;height:8px;background:#e2e8f0;border-radius:99px;overflow:hidden}
 .prog i{display:block;height:100%;background:#1e6fae;width:0%}
 .qcard{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px}
 .qhead{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:10px}
 .qhead .g{font-size:16px;font-weight:700}
 .badge{font-size:12px;padding:2px 10px;border-radius:999px;background:#fef3c7;color:#92400e}
 .badge.rt{background:#dbeafe;color:#1e40af}
 .duo{display:flex;gap:14px;flex-wrap:wrap}
 .pane{flex:1 1 420px;min-width:320px}
 .pane .tag{font-size:14px;font-weight:700;margin-bottom:6px;display:inline-block;background:#e2e8f0;border-radius:8px;padding:3px 14px}
 .box{border:1.5px solid #cbd5e1;border-radius:10px;background:#f7f3ea;padding:8px;overflow:auto;max-height:520px;min-height:260px}
 .box svg{width:100%;height:auto;display:block}
 .btns{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
 .btns button{font-size:15px;padding:12px 6px;border-radius:10px;border:1.5px solid #cbd5e1;background:#fff;cursor:pointer;font-weight:600}
 .btns button:hover{border-color:#1e6fae;background:#eff6ff}
 .btns button kbd{font-size:11px;color:#64748b;font-weight:400}
 .foot{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
 .foot button{padding:10px 22px;font-size:14px;border-radius:9px;border:none;cursor:pointer}
 #export{background:#0a7d43;color:#fff}
 #reset{background:#fff;color:#b45309;border:1px solid #fde68a}
 .msg{font-size:13px;color:#64748b}
</style></head><body><div class="wrap">
<h1>Pairwise 盲选 · 第三轮 · 同图两候选哪个更好？</h1>
<p class="sub">候选来源已隐藏（人工锚点 / 引擎 / 配方档均不可见），画面为候选存储几何的保真重放。凭第一眼观感判断即可，每题约 1 分钟。__NQ__ 题 = 新拓扑图 __NNEWTOPO__ + 老图引擎对比 __NDIS__ + 人工 vs 引擎 __NANCHOR__ + 跨会话重测 __NRETEST__。</p>
<div class="bar"><span class="msg" id="progtext"></span><div class="prog"><i id="progfill"></i></div></div>
<div class="qcard" id="qcard">
 <div class="qhead"><span class="g" id="qgraph"></span><span class="badge" id="qbadge"></span></div>
 <div class="duo">
  <div class="pane"><span class="tag">候选 A</span><div class="box" id="boxL"></div></div>
  <div class="pane"><span class="tag">候选 B</span><div class="box" id="boxR"></div></div>
 </div>
 <div class="btns">
  <button data-c="a">&#9650; A 更好 <kbd>(1)</kbd></button>
  <button data-c="b">&#9650; B 更好 <kbd>(2)</kbd></button>
  <button data-c="both">都好 <kbd>(3)</kbd></button>
  <button data-c="both_bad">都差 <kbd>(4)</kbd></button>
 </div>
</div>
<div class="foot">
 <button id="export">导出 JSON（完成后点这里）</button>
 <button id="reset">重置本会话</button>
 <span class="msg" id="hint">进度会自动保存在本页（刷新不丢）。全部答完后点「导出 JSON」，把下载的文件放到 benchmarks/manual/pairwise/session-__DATE__/。</span>
</div>
<script>
const QS = __QUESTIONS__;
const SVGS = __SVGS__;
const MODEL_VERSION = "__MODEL__";
const KEY = "stdraw-pairwise-__DATE__";
let answers = {};
try { answers = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch(e) { answers = {}; }
let cur = null, t0 = 0;
function save(){ localStorage.setItem(KEY, JSON.stringify(answers)); }
function answeredCount(){ return Object.keys(answers).length; }
function show(q){
  cur = q; t0 = performance.now();
  document.getElementById("qgraph").textContent = "图: " + q.graph;
  const b = document.getElementById("qbadge");
  if (q.is_retest) { b.textContent = "跨会话重测题"; b.className = "badge rt"; }
  else { b.textContent = "第 " + (QS.indexOf(q)+1) + " / " + QS.length + " 题"; b.className = "badge"; }
  const A = SVGS[q.candidate_a], B = SVGS[q.candidate_b];
  document.getElementById("boxL").innerHTML = q.left_is_a ? A : B;
  document.getElementById("boxR").innerHTML = q.left_is_a ? B : A;
  const done = QS.every(x => answers[x.qid]);
  if (done) { document.getElementById("qcard").style.display = "none"; }
  else { document.getElementById("qcard").style.display = ""; }
  updateProgress();
}
function updateProgress(){
  const n = answeredCount();
  document.getElementById("progfill").style.width = (100*n/QS.length) + "%";
  document.getElementById("progtext").textContent = "已答 " + n + " / " + QS.length;
}
function answer(choice){
  if (!cur) return;
  answers[cur.qid] = {choice: choice, duration_ms: Math.round(performance.now() - t0)};
  save();
  const next = QS.find(x => !answers[x.qid]);
  if (next) show(next); else { updateProgress(); finish(); }
}
function finish(){
  document.getElementById("qcard").style.display = "none";
  document.getElementById("hint").textContent = "全部完成！点「导出 JSON」保存标注结果。";
}
document.querySelectorAll(".btns button").forEach(b => {
  b.addEventListener("click", () => answer(b.dataset.c));
});
document.addEventListener("keydown", e => {
  if (e.key === "1") answer("a");
  else if (e.key === "2") answer("b");
  else if (e.key === "3") answer("both");
  else if (e.key === "4") answer("both_bad");
});
document.getElementById("export").addEventListener("click", () => {
  const items = QS.filter(q => answers[q.qid]).map(q => ({
    qid: q.qid, graph: q.graph,
    candidate_a: q.candidate_a, candidate_b: q.candidate_b,
    left_is_a: q.left_is_a, is_retest: q.is_retest, pair_key: q.pair_key,
    model_version: MODEL_VERSION,
    choice: answers[q.qid].choice, duration_ms: answers[q.qid].duration_ms
  }));
  const payload = {schema: "stdraw.pairwise.session/1", session: "__DATE__",
                   model_version: MODEL_VERSION, n_questions: QS.length,
                   n_answered: items.length, items: items};
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "pairwise-session-__DATE__.json";
  a.click(); URL.revokeObjectURL(a.href);
});
document.getElementById("reset").addEventListener("click", () => {
  if (!confirm("清空本页全部作答并重新开始？")) return;
  answers = {}; save();
  const first = QS.find(x => !answers[x.qid]);
  document.getElementById("qcard").style.display = "";
  document.getElementById("hint").textContent = "已重置。";
  if (first) show(first);
});
(function init(){
  const first = QS.find(x => !answers[x.qid]);
  if (first) show(first); else finish();
  updateProgress();
})();
</script></body></html>
"""


def render_viewer_html(questions, svgs_js):
    return (VIEWER_TEMPLATE
            .replace("__QUESTIONS__", json.dumps(questions, ensure_ascii=False))
            .replace("__SVGS__", svgs_js)
            .replace("__MODEL__", MODEL_VERSION)
            .replace("__DATE__", SESSION_ID)
            .replace("__NQ__", str(len(questions)))
            .replace("__NNEWTOPO__", str(N_NEWTOPO))
            .replace("__NDIS__", str(N_DISAGREE))
            .replace("__NANCHOR__", str(N_ANCHOR))
            .replace("__NRETEST__", str(N_RETEST)))


README_TEXT = """# Pairwise blind-choice session ROUND 3 (new topologies + anchor pairs) — """ + SESSION_ID + """

- `viewer.html` — the round-3 annotation page (self-contained, works from
  file://; mirrored under `~/Downloads/stdraw-pref-round3/pairwise/`).
- `questions.json` — deterministic question pack (LCG seed recorded inside;
  re-running benchmarks/aesthetic/pref_round3.py reproduces it
  byte-identically).
- `candidates.json` — SOURCE LABELS (source / recipe / gate metrics per
  opaque candidate id).  Deliberately NOT referenced by viewer.html:
  blinding depends on this separation (review-consensus red line).

## What changed vs round 2

- ZERO dose pairs: the synthetic perturbation ladder is not loaded at all
  (hard-asserted in the self-check).
- New topology sources under benchmarks/manual/pref-round3/sources/
  (n=8-10 each): pure nested-ring variant (inner ring shares ONE node with
  the outer ring), chain+ring hybrid, asymmetric dual-hub.  Each got 4-6
  diverse engine candidates from a fixed recipe x pitch ladder, all
  passing the hard viability gate (min card gap >= 16px, zero box-press).
- The old-graph pools were widened with the same ladder (rounds 1-2 left
  ZERO unasked pool pairs); new pairs are anchor-vs-engine (the user's
  human anchor vs fresh engine candidates, same graph) and
  model-disagreement pairs (committed arms M0/M1/M2 scored OFFLINE for
  selection only; committed analysis artifacts untouched).
- Byte-faithful rendering: every picture is an engine --from-layout replay
  of the candidate's stored geometry (anchors / waypoints / styles kept).
- Cross-session retests: 2 round-2-only both-good ties + 1 tie already
  asked in both rounds (a third observation on the noise-baseline pairs).

## How to annotate

1. Open `viewer.html`, answer all """ + str(N_TOTAL) + """ questions (keyboard 1-4
   works; progress persists in localStorage).
2. Click "导出 JSON" — the downloaded `pairwise-session-""" + SESSION_ID + """.json`
   goes into THIS directory.
3. Record fields per item are identical to rounds 1-2: qid / graph /
   candidate_a / candidate_b / left_is_a / is_retest / pair_key /
   model_version / choice / duration_ms.
"""


# ── self-check ─────────────────────────────────────────────────────────────

def run_selfcheck():
    q = json.loads((SESSION_DIR / "questions.json").read_text(encoding="utf-8"))
    sel = json.loads(OUT_SELECTION.read_text(encoding="utf-8"))
    qs = q["questions"]
    asked = load_asked()
    kinds = {}
    for x in sel["questions"]:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
    assert sum(kinds.values()) == len(qs)
    # allocation ranges (card)
    assert kinds.get("newtopo", 0) == N_NEWTOPO and 12 <= N_NEWTOPO <= 18
    assert kinds.get("disagree", 0) == N_DISAGREE and 10 <= N_DISAGREE <= 15
    assert kinds.get("anchor", 0) == N_ANCHOR and 8 <= N_ANCHOR <= 12
    assert kinds.get("retest", 0) == N_RETEST and 2 <= N_RETEST <= 3
    assert len(qs) == N_TOTAL and 30 <= N_TOTAL <= 50
    # zero dose pairs: no perturbation source anywhere in the candidate meta
    cands = json.loads((SESSION_DIR / "candidates.json")
                       .read_text(encoding="utf-8"))["candidates"]
    for cid, m in cands.items():
        blob = json.dumps(m, ensure_ascii=False).lower()
        for bad in ("jitter", "dose", "perturb", "swap", "mirror", "l1", "l2",
                    "l3", "l4"):
            assert bad not in blob, (cid, bad)
        assert m["source"] in ("human", "archived-engine", "archived-draft",
                               "fresh-cli", "fresh-r3"), (cid, m["source"])
    # used cids ⊆ candidates.json
    used = {cid for x in qs for cid in (x["candidate_a"], x["candidate_b"])}
    assert used <= set(cands), used - set(cands)
    # no duplicates; new pairs unasked in rounds 1-2; retests asked in round 2
    pks = [x["pair_key"] for x in qs]
    assert len(set(pks)) == len(pks), "duplicate pair within round 3"
    r2_q = json.loads((R2_SESSION / "questions.json").read_text(encoding="utf-8"))
    r2_pks = {x["pair_key"] for x in r2_q["questions"]}
    for x in qs:
        if x["is_retest"]:
            assert x["pair_key"] in r2_pks, x
        else:
            assert x["pair_key"] not in asked, x
    # record-field parity with rounds 1-2 export schema
    q_fields = ["qid", "graph", "candidate_a", "candidate_b", "left_is_a",
                "is_retest", "pair_key"]
    missing = [k for k in q_fields if k not in qs[0]]
    assert not missing, missing
    assert "kind" not in qs[0], "kind must stay out of the public pack"
    # every used cid has a rendered svg embedded in the viewer
    viewer = (SESSION_DIR / "viewer.html").read_text(encoding="utf-8")
    n_svg = sum(1 for cid in used if ('"%s": "<svg' % cid) in viewer)
    assert n_svg == len(used), ("missing svgs", len(used) - n_svg)
    # selection list consistency
    assert len(sel["questions"]) == N_TOTAL
    # at least two new topology graphs contributed questions
    nt_graphs = {x["graph"] for x in sel["questions"]
                 if x["kind"] == "newtopo"}
    assert len(nt_graphs) >= 2, nt_graphs
    # anchor pairs must involve a human-source candidate
    for row in sel["questions"]:
        if row["kind"] == "anchor":
            a, b = row["a"], row["b"]
            srcs = {cands[a]["source"], cands[b]["source"]}
            assert "human" in srcs, row

    print("SELF-CHECK PASS")
    print("  questions: %d = %d newtopo + %d disagree + %d anchor + %d retest"
          % (len(qs), kinds.get("newtopo", 0), kinds.get("disagree", 0),
             kinds.get("anchor", 0), kinds.get("retest", 0)))
    print("  zero dose pairs (perturbation ladder not loaded): OK")
    print("  new topology graphs used: %d %s" % (len(nt_graphs),
                                                 sorted(nt_graphs)))
    print("  new pairs unasked in rounds 1-2; retests are round-2 ties: OK")
    print("  svgs embedded: %d candidate pictures" % n_svg)
    return {"n_total": len(qs), "kinds": kinds, "svgs": n_svg}


# ── byte-fidelity probe (acceptance: picture contains the stored detour) ──

def run_fidelity_probe(questions):
    """Round-3 caliber: the probe target must be a HUMAN ANCHOR candidate
    actually used in this session (old-graph pair), i.e. the delivered
    question pictures replay the user's stored detour byte-faithfully."""
    import copy
    import re
    import tempfile
    cands = json.loads((SESSION_DIR / "candidates.json")
                       .read_text(encoding="utf-8"))["candidates"]
    used = {cid for x in questions
            for cid in (x["candidate_a"], x["candidate_b"])}
    target = None
    for cid in sorted(used):
        if cands[cid]["source"] == "human":
            doc = anchor_doc_by_cid(cid)
            if doc is not None and any(e.get("waypoints")
                                       for e in doc["edges"]):
                target = (cid, doc)
                break
    assert target, "no session anchor candidate with stored waypoints"
    cid, doc = target
    g = doc["graph"]
    tmp = Path(tempfile.mkdtemp(prefix="stdraw-fidelity-r3-"))
    slim_svg = pp.render_doc_svg(source_cld_for(g), doc, tmp / "slim")
    full = copy.deepcopy(doc)
    (tmp / "full").mkdir(parents=True)
    full_path = tmp / "full" / "_doc.json"
    full_path.write_text(json.dumps(full, ensure_ascii=False),
                         encoding="utf-8")
    cmd = [PY, "-m", "stdraw", "layout", str(source_cld_for(g)),
           "--outdir", str(tmp / "full"), "--recipe", "auto",
           "--from-layout", str(full_path)]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert (tmp / "full" / "demo-2d.html").exists(), r.stderr[-300:]
    hh = (tmp / "full" / "demo-2d.html").read_text(encoding="utf-8")
    svgs = re.findall(r"<svg[^>]*>.*?</svg>", hh, re.S)
    full_svg = max(svgs, key=len)
    leg1 = slim_svg == full_svg
    stripped = copy.deepcopy(doc)
    n_wp = 0
    for e in stripped["edges"]:
        if e.get("waypoints"):
            n_wp += 1
            e.pop("waypoints")
    assert n_wp > 0
    stripped_svg = pp.render_doc_svg(source_cld_for(g), stripped,
                                     tmp / "stripped")
    leg2 = slim_svg != stripped_svg
    slim = pp.slim_doc(doc)
    kept = sum(1 for e in slim["edges"] if e.get("waypoints"))
    leg3 = kept == n_wp
    # leg 4: the embedded viewer svg for this cid is byte-identical to the
    # probe replay (the delivered page carries the detour)
    viewer = (SESSION_DIR / "viewer.html").read_text(encoding="utf-8")
    marker = "const SVGS = "
    i = viewer.index(marker) + len(marker)
    j = viewer.index("};", i) + 1
    svg_store = json.loads(viewer[i:j])
    leg4 = svg_store[cid] == slim_svg
    print("FIDELITY PROBE target=%s (graph=%s, edges_with_waypoints=%d)"
          % (cid, g, n_wp))
    print("  leg1 slim vs full doc svg byte-identical: %s" % leg1)
    print("  leg2 waypoints-stripped svg differs:       %s" % leg2)
    print("  leg3 slim_doc keeps waypoint fields:       %s (%d/%d)"
          % (leg3, kept, n_wp))
    print("  leg4 embedded viewer svg == probe replay:  %s" % leg4)
    assert leg1 and leg2 and leg3 and leg4
    print("FIDELITY PASS: delivered question replays the user's stored detour")
    return {"target": cid, "graph": g, "n_waypoint_edges": n_wp,
            "legs": [leg1, leg2, leg3, leg4]}


def anchor_doc_by_cid(cid):
    """Re-fetch the human anchor doc for a round-1 pool cid (read-only)."""
    pool = pp.collect_view_candidates()
    for g, cands in pool.items():
        for c in cands:
            if c["cid"] == cid:
                return c["doc"]
    return None


# ── entry ──────────────────────────────────────────────────────────────────

def run_viewer():
    pool_by_graph = pp.collect_view_candidates()
    # pool identity guard: shared cids must reproduce round-1 labels exactly
    r1_cands = json.loads((R1_SESSION / "candidates.json")
                          .read_text(encoding="utf-8"))["candidates"]
    for g, cands in pool_by_graph.items():
        for c in cands:
            m = r1_cands.get(c["cid"])
            assert m is not None, ("cid not in round-1 candidates", c["cid"])
            assert (m["source"], m["recipe"]) == (c["source"], c["recipe"]), \
                c["cid"]
    new_by_graph, new_reports = collect_new_graph_candidates()
    ext_by_graph, ext_reports = collect_old_extension(pool_by_graph)
    asked = load_asked()
    arms = OfflineArms(pool_by_graph, ext_by_graph)
    newtopo_sel, per_graph = select_newtopo(new_by_graph)
    disagree_sel, _dper, anchor_sel, _aper = select_old_pairs(
        pool_by_graph, ext_by_graph, arms, asked)
    retest_sel = load_round2_ties()
    assert len(retest_sel) == N_RETEST
    questions = build_questions(newtopo_sel, disagree_sel, anchor_sel,
                                retest_sel)
    docs_by_cid = {}
    for g, cands in pool_by_graph.items():
        for c in cands:
            docs_by_cid[c["cid"]] = (g, c["doc"], c)
    for g, cands in ext_by_graph.items():
        for c in cands:
            docs_by_cid[c["cid"]] = (g, c["doc"], c)
    for g, cands in new_by_graph.items():
        for c in cands:
            docs_by_cid[c["cid"]] = (g, c["doc"], c)
    svg_store, cand_meta = render_all(questions, docs_by_cid)
    selection = selection_record(newtopo_sel, disagree_sel, anchor_sel,
                                 retest_sel, questions, new_reports,
                                 ext_reports, per_graph, arms.n_decided)
    write_session(questions, svg_store, cand_meta, selection)
    print("viewer round3: %d newtopo + %d disagree + %d anchor + %d retest"
          " = %d questions -> %s"
          % (N_NEWTOPO, N_DISAGREE, N_ANCHOR, N_RETEST, len(questions),
             SESSION_DIR))
    print("  per-graph newtopo:", json.dumps(per_graph))
    for q in questions:
        print("  %s %-8s %-64s %s" % (q["qid"], q["kind"], q["pair_key"],
                                      "L=A" if q["left_is_a"] else "L=B"))
    return questions


def shas():
    files = [SESSION_DIR / "viewer.html", SESSION_DIR / "questions.json",
             SESSION_DIR / "candidates.json", OUT_SELECTION,
             SESSION_DIR / "README.md"]
    for f in files:
        print("  sha256 %-64s %s" % (str(f.relative_to(REPO)),
                                     hashlib.sha256(f.read_bytes()).hexdigest()[:16]))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("viewer", "all"):
        questions = run_viewer()
        shas()
    if cmd in ("selfcheck", "all"):
        run_selfcheck()
    if cmd in ("fidelity", "all"):
        q = json.loads((SESSION_DIR / "questions.json").read_text(encoding="utf-8"))
        run_fidelity_probe(q["questions"])
