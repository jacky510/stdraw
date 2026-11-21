#!/usr/bin/env python
"""Round-2 pairwise preference annotation tool: adaptive question selection +
byte-faithful rendering (pre-v3 prerequisite card, "pref-round2").

Extends pref_pipeline's round-1 blind-choice viewer with:

  1. Adaptive selection driven by the committed round-1 LOSO results
     (pref-ranking-m0m1m2.json):
       P1 model-uncertainty  - unasked pool pairs ranked by cross-arm vote
                               split (5 arms; closer rankings = higher
                               priority) plus closeness of mean rank margin;
       P2 fold supplements   - topology folds that read 0% held-out in round 1
                               (nonplanar-credit: M1/M2; nested-ring
                               brand-flywheel + classic-cld: M0/M1) get a
                               fold bonus;
       P3 tie stability      - 3 of the 7 round-1 both-good pairs re-asked
                               cross-session (ranked by cross-arm tie-margin
                               magnitude; these ARE the retest mix);
       P4 new information    - the pool matrix is exhausted after round 1
                               (only 10 unasked pool-pool pairs remain), so
                               the candidate pool is widened with the
                               post-spotfix synthetic-perturbation candidates
                               (L1 + deepest gate-passing dose, zero score
                               weight, deterministic) of the same viewer
                               graphs; pool x synthetic pairs complete the
                               offer.
  2. Byte-faithful rendering: pictures are rendered from the stored candidate
     geometry through the engine (--from-layout replay of the spotfix
     slim_doc, which keeps human-side edge geometry: anchors / waypoints /
     styles).  The picture IS the candidate's stored layout.
  3. Deterministic orchestration: fixed recorded LCG seed for question order
     and left/right assignment (reproducible by re-running this script).
  4. Cross-session retest mix: 3 of 20 questions re-ask round-1 answered
     pairs (15.0%, within the 10-15% protocol).

Record fields per exported item are identical to round 1: qid / graph /
candidate_a / candidate_b / left_is_a / is_retest / pair_key / model_version /
choice / duration_ms.

Red lines honored: the scorer and ranker code are untouched (LOSO JSON is
read as committed data); candidate generation carries zero score weight
(synthetic candidates come from the deterministic perturbation ladder +
geometry gate only); deterministic output (double-run byte-identical);
source labels stay separated from the viewer page (blinding preserved);
no internal ids / absolute paths in tracked outputs.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import pref_pipeline as pp  # noqa: E402  (pool, renderer, LCG — read-only reuse)

LOSO_JSON = REPO / "benchmarks" / "aesthetic" / "pref-ranking-m0m1m2.json"
R1_SESSION = REPO / "benchmarks" / "manual" / "pairwise" / "session-2026-11-21"
SESSION_ID = "2026-11-22-round2"
SESSION_DIR = REPO / "benchmarks" / "manual" / "pairwise" / ("session-" + SESSION_ID)
OUT_SELECTION = REPO / "benchmarks" / "aesthetic" / "pref-round2-selection.json"
MODEL_VERSION = "aesthetic-v2"  # record-field parity with round 1
LCG_SEED = 20261122  # recorded; question order reproducible from this
N_NEW = 17
N_RETEST = 3
N_TOTAL = N_NEW + N_RETEST  # 20 questions <= 20 burden cap
GRAPH_MIN, GRAPH_MAX = 2, 5
# round-1 LOSO held-out folds that read 0%: weighted supplement targets
FOLD_BONUS = {"nonplanar-credit": 1.0,                     # M1/M2 0/3
              "brand-flywheel": 0.75,                      # nested ring M0/M1 0/5
              "classic-cld-growth-and-burden": 0.75}       # nested ring M0/M1 0/5
FOLD_REASON = {"nonplanar-credit": "round1 LOSO M1/M2 held-out 0%",
               "brand-flywheel": "round1 LOSO nested-ring M0/M1 held-out 0%",
               "classic-cld-growth-and-burden":
                   "round1 LOSO nested-ring M0/M1 held-out 0%"}
ARMS = ("M0", "M1", "M2", "M1s", "M2s")


# ── inputs ─────────────────────────────────────────────────────────────────

def load_loso():
    return json.loads(LOSO_JSON.read_text(encoding="utf-8"))


def load_round1():
    q = json.loads((R1_SESSION / "questions.json").read_text(encoding="utf-8"))
    a = json.loads((R1_SESSION / "answers-2026-11-21.json").read_text(encoding="utf-8"))
    items = a["items"] if isinstance(a, dict) and "items" in a else a
    choice_by_qid = {i["qid"]: i["choice"] for i in items}
    asked = {}
    both_good = set()
    for x in q["questions"]:
        pk = x["pair_key"]
        asked.setdefault(pk, []).append(choice_by_qid.get(x["qid"]))
        if choice_by_qid.get(x["qid"]) == "both":
            both_good.add(pk)
    return q, asked, both_good


def load_synth_candidates():
    """Post-spotfix synthetic perturbation candidates of the viewer graphs
    (zero score weight: deterministic perturbation ladder + geometry gate)."""
    cdir = pp.OUT_SYN / "candidates"
    out = {}
    for f in sorted(cdir.glob("*.json")):
        cid = f.stem
        if cid.endswith("-human") or cid.startswith("retest-"):
            continue  # -human duplicates a pool candidate; retest-* kept out
        d = json.loads(f.read_text(encoding="utf-8"))
        g = d.get("graph")
        if g not in pp.VIEWER_GRAPHS:
            continue
        ok, cert = pp.gate_viability(d, g)
        assert ok, ("synthetic candidate failed the geometry gate", cid)
        level = cid.rsplit("-", 1)[1]
        out.setdefault(g, []).append({
            "cid": cid, "doc": d, "source": "synthetic-perturbation",
            "recipe": "jitter" if level == "L1" else "deep-" + level,
            "level": level,
            "gap": cert["metrics"]["min_card_gap"],
            "crossings": cert["metrics"]["crossings"]})
    return out


# ── adaptive scoring ───────────────────────────────────────────────────────

def pair_key(g, ca, cb):
    return "%s|%s|%s" % (g, min(ca, cb), max(ca, cb))


def arm_votes(loso, g, ca, cb):
    """Cross-arm vote split and rank-margin closeness from committed LOSO
    rankings (best first).  Returns (votes_a, votes_b, mean_abs_rank_gap)."""
    va = vb = 0
    gaps = []
    for arm in ARMS:
        rank = loso["arms"][arm]["rankings"][g]
        ia, ib = rank.index(ca), rank.index(cb)
        if ia < ib:
            va += 1
        else:
            vb += 1
        gaps.append(abs(ia - ib))
    return va, vb, sum(gaps) / len(gaps)


def new_pair_space(pool_by_graph, synth_by_graph):
    """All unasked pairs: pool-pool (round-1 leftovers) + pool x synthetic +
    synthetic x synthetic, per graph.  Zero score weight: candidate docs come
    from stored layouts only; scoring below uses committed LOSO rankings."""
    rows = []
    for g in pp.VIEWER_GRAPHS:
        pool = pool_by_graph[g]
        syn = synth_by_graph.get(g, [])
        cands = [(c["cid"], "pool") for c in pool] + [(c["cid"], "syn") for c in syn]
        for (ca, ka), (cb, kb) in itertools.combinations(cands, 2):
            rows.append({"graph": g, "a": ca, "b": cb, "kind_a": ka,
                         "kind_b": kb, "pair_key": pair_key(g, ca, cb)})
    return rows


def score_new_pairs(space, synth_by_graph, loso, asked):
    """Priority = P1 uncertainty (pool pairs with LOSO rankings) + P2 fold
    bonus + P4 source contrast + closeness.  Deterministic tie-break by
    pair_key."""
    syn_meta = {c["cid"]: c for cs in synth_by_graph.values() for c in cs}
    out = []
    for r in space:
        g, ca, cb = r["graph"], r["a"], r["b"]
        if r["pair_key"] in asked:
            continue  # asked in round 1 (retests handled separately)
        votes = None
        if r["kind_a"] == "pool" and r["kind_b"] == "pool":
            va, vb, gap = arm_votes(loso, g, ca, cb)
            unc = min(va, vb)                      # 0 consensus .. 2 split
            closeness = max(0.0, 1.0 - gap / 4.0)  # closer rankings = higher
            votes = (va, vb)
        else:
            unc, closeness = 0.0, 0.0
        contrast = 1.0 if r["kind_a"] != r["kind_b"] else 0.0
        dose = 0.0
        for k, kind in ((ca, r["kind_a"]), (cb, r["kind_b"])):
            if kind == "syn" and syn_meta[k]["level"] != "L1":
                dose = 0.3
        priority = 2.0 * unc + 0.5 * closeness + FOLD_BONUS.get(g, 0.0) \
            + 0.4 * contrast + dose
        out.append(dict(r, priority=round(priority, 4), uncertainty=unc,
                        votes=votes, closeness=round(closeness, 3),
                        contrast=contrast, fold=FOLD_BONUS.get(g, 0.0),
                        fold_reason=FOLD_REASON.get(g, "-")))
    out.sort(key=lambda r: (-r["priority"], r["pair_key"]))
    return out


def select_new(scored):
    """Greedy pick with per-graph floor then ceiling (deterministic: the
    input order is already the priority order)."""
    chosen, chosen_keys, per_graph = [], set(), {}
    for r in scored:  # floor pass: >= GRAPH_MIN per graph
        g = r["graph"]
        if per_graph.get(g, 0) < GRAPH_MIN:
            chosen.append(r)
            chosen_keys.add(r["pair_key"])
            per_graph[g] = per_graph.get(g, 0) + 1
    for r in scored:  # fill to N_NEW under GRAPH_MAX, keeping priority order
        if len(chosen) >= N_NEW:
            break
        if r["pair_key"] in chosen_keys:
            continue
        if per_graph.get(r["graph"], 0) >= GRAPH_MAX:
            continue
        chosen.append(r)
        chosen_keys.add(r["pair_key"])
        per_graph[r["graph"]] = per_graph.get(r["graph"], 0) + 1
    assert len(chosen) == N_NEW, (len(chosen), N_NEW)
    chosen.sort(key=lambda r: (-r["priority"], r["pair_key"]))
    return chosen, per_graph


def select_retests(both_good, loso):
    """P3: re-ask 3 of the 7 round-1 both-good pairs, ranked by cross-arm
    tie-margin magnitude (pairs where models most disagree with the tie are
    the strongest stability probes)."""
    margins = {}
    for arm in ARMS:
        for t in loso["arms"][arm]["tie_margins"]:
            margins.setdefault(t["pair_key"], []).append(abs(t["signed_margin"]))
    rows = []
    for pk in sorted(both_good):
        m = margins.get(pk, [])
        assert m, ("tie pair missing from LOSO tie_margins", pk)
        rows.append({"pair_key": pk, "mean_abs_margin": sum(m) / len(m)})
    rows.sort(key=lambda r: (-r["mean_abs_margin"], r["pair_key"]))
    return rows[:N_RETEST]


# ── orchestration ──────────────────────────────────────────────────────────

def build_questions(new_sel, retest_sel):
    rnd = pp.lcg(LCG_SEED)
    seq = [("new", r) for r in new_sel] + [("retest", r) for r in retest_sel]
    order = list(range(len(seq)))
    for i in range(len(order) - 1, 0, -1):
        j = next(rnd) % (i + 1)
        order[i], order[j] = order[j], order[i]
    questions = []
    for qn, idx in enumerate(order, 1):
        kind, r = seq[idx]
        if kind == "retest":
            g, ca, cb = r["pair_key"].split("|")
        else:
            g, ca, cb = r["graph"], r["a"], r["b"]
        questions.append({
            "qid": "q%02d" % qn, "graph": g,
            "candidate_a": ca, "candidate_b": cb,
            "left_is_a": bool(next(rnd) % 2),
            "kind": kind, "is_retest": kind == "retest",
            "pair_key": pair_key(g, ca, cb)})
    return questions


def render_all(questions, pool_by_graph, synth_by_graph):
    docs = {}
    for g, cands in pool_by_graph.items():
        for c in cands:
            docs[c["cid"]] = (g, c["doc"], c)
    for g, cands in synth_by_graph.items():
        for c in cands:
            docs[c["cid"]] = (g, c["doc"], c)
    svg_store, cand_meta = {}, {}
    for q in questions:
        for cid in (q["candidate_a"], q["candidate_b"]):
            if cid in svg_store:
                continue
            g, doc, meta = docs[cid]
            svg_store[cid] = pp.render_doc_svg(
                pp.source_cld_for(g), doc,
                pp.BUILD_ROOT / "viewer-round2" / cid)
            cand_meta[cid] = {"graph": g, "source": meta["source"],
                              "recipe": meta["recipe"],
                              "grade": meta.get("grade", "-"),
                              "gap": round(meta["gap"], 1),
                              "crossings": meta["crossings"]}
    return svg_store, cand_meta


# ── artifacts ──────────────────────────────────────────────────────────────

def selection_record(new_sel, retest_sel, questions):
    qsel = []
    for q in questions:
        row = {"qid": q["qid"], "graph": q["graph"], "a": q["candidate_a"],
               "b": q["candidate_b"], "pair_key": q["pair_key"],
               "kind": q["kind"]}
        if q["kind"] == "new":
            r = next(x for x in new_sel if x["pair_key"] == q["pair_key"])
            row.update({"priority": r["priority"],
                        "principles": {
                            "P1_uncertainty_votes": r["votes"],
                            "P2_fold": r["fold"], "P2_reason": r["fold_reason"],
                            "P4_source_contrast": r["contrast"]}})
        else:
            r = next(x for x in retest_sel if x["pair_key"] == q["pair_key"])
            row.update({"principles": {
                "P3_tie_stability_retest_of_round1_both_good": True,
                "P3_mean_abs_tie_margin": round(r["mean_abs_margin"], 3)}})
        qsel.append(row)
    return {"schema": "stdraw.pref-round2.selection/1",
            "session": SESSION_ID,
            "note": "adaptive selection list - P1 model uncertainty (committed "
                    "round-1 LOSO rankings) / P2 fold supplements / P3 tie "
                    "stability retests (= cross-session retest mix) / P4 new "
                    "information pairs; candidate generation carries zero "
                    "score weight",
            "lcg_seed": LCG_SEED, "model_version": MODEL_VERSION,
            "n_new": N_NEW, "n_retest": N_RETEST, "n_total": N_TOTAL,
            "retest_fraction": round(N_RETEST / N_TOTAL, 3),
            "graph_quota_floor": GRAPH_MIN, "graph_quota_cap": GRAPH_MAX,
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
                    "n_new": N_NEW, "n_retest": N_RETEST,
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
<title>Pairwise 盲选 · 第二轮（自适应选题）· stdraw 审美偏好标注</title>
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
<h1>Pairwise 盲选 · 第二轮（自适应选题）· 同图两候选哪个更好？</h1>
<p class="sub">候选来源已隐藏（人工 / 引擎 / 模板 / 扰动档均不可见），画面为候选存储几何的保真重放。凭第一眼观感判断即可，每题约 1 分钟。__NQ__ 题 = __NNEW__ 道新题 + __NRETEST__ 道跨轮重测（首轮答过的对会再次出现，按当时观感作答即可）。</p>
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
  if (q.is_retest) { b.textContent = "跨轮重测题"; b.className = "badge rt"; }
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
            .replace("__NNEW__", str(N_NEW))
            .replace("__NRETEST__", str(N_RETEST)))


README_TEXT = """# Pairwise blind-choice session ROUND 2 (adaptive selection) — """ + SESSION_ID + """

- `viewer.html` — the round-2 annotation page (self-contained, works from
  file://; mirrored under `~/Downloads/stdraw-pref-round2/pairwise/`).
- `questions.json` — deterministic question pack (LCG seed recorded inside;
  re-running benchmarks/aesthetic/pref_round2.py reproduces it
  byte-identically).
- `candidates.json` — SOURCE LABELS (source / recipe / gate metrics per
  opaque candidate id).  Deliberately NOT referenced by viewer.html:
  blinding depends on this separation (review-consensus red line).

## What changed vs round 1

- Adaptive selection driven by the committed round-1 LOSO results:
  P1 model-uncertain unasked pairs first, P2 weighted supplements for the
  folds that read 0% held-out (nonplanar-credit M1/M2; nested-ring
  brand-flywheel + classic-cld M0/M1), P3 three of the seven round-1
  both-good pairs re-asked (tie stability), P4 new information pairs via the
  post-spotfix synthetic perturbation candidates (zero score weight).
- Byte-faithful rendering: every picture is an engine --from-layout replay
  of the candidate's stored geometry (anchors / waypoints / styles kept) —
  the round-1 slim-doc anchor-stripping defect does not apply here.
- Cross-session retest mix: 3 of 20 questions re-ask round-1 answered pairs
  (15.0%) — stricter than round-1's within-session repeats.
- Selection list with per-question principle annotations:
  benchmarks/aesthetic/pref-round2-selection.json.

## How to annotate

1. Open `viewer.html`, answer all 20 questions (17 new + 3 cross-session
   retests; keyboard 1-4 works; progress persists in localStorage).
2. Click "导出 JSON" — the downloaded `pairwise-session-""" + SESSION_ID + """.json`
   goes into THIS directory.
3. Record fields per item are identical to round 1: qid / graph /
   candidate_a / candidate_b / left_is_a / is_retest / pair_key /
   model_version / choice / duration_ms.
"""


# ── self-check ─────────────────────────────────────────────────────────────

def run_selfcheck():
    q = json.loads((SESSION_DIR / "questions.json").read_text(encoding="utf-8"))
    sel = json.loads(OUT_SELECTION.read_text(encoding="utf-8"))
    qs = q["questions"]
    _r1q, asked, _both_good = load_round1()
    pk2 = [x["pair_key"] for x in qs]
    retests = [x for x in qs if x["is_retest"]]
    news = [x for x in qs if not x["is_retest"]]

    assert len(qs) == N_TOTAL <= 20, "question cap"
    assert len(news) == N_NEW and len(retests) == N_RETEST
    frac = len(retests) / len(qs)
    assert 0.10 <= frac <= 0.15 + 1e-9, ("retest fraction", frac)
    assert len(set(pk2)) == len(pk2), "duplicate pair in round 2"
    for x in retests:
        assert x["pair_key"] in asked, ("retest not asked in round 1", x)
        assert "both" in asked[x["pair_key"]], ("retest not a both-good pair", x)
    for x in news:
        assert x["pair_key"] not in asked, ("new pair already asked in round 1", x)
    # record-field parity with round 1 exported items
    q_fields = ["qid", "graph", "candidate_a", "candidate_b", "left_is_a",
                "is_retest", "pair_key"]
    missing = [k for k in q_fields if k not in qs[0]]
    assert not missing, missing
    assert "kind" not in qs[0], "kind must stay out of the public pack"
    # every used cid has a rendered svg embedded in the viewer
    viewer = (SESSION_DIR / "viewer.html").read_text(encoding="utf-8")
    used = {cid for x in qs
            for cid in (x["candidate_a"], x["candidate_b"])}
    n_svg = sum(1 for cid in used if ('"%s": "<svg' % cid) in viewer)
    assert n_svg == len(used), ("missing svgs", len(used) - n_svg)
    # selection list consistency
    assert len(sel["questions"]) == N_TOTAL
    assert sel["n_retest"] == N_RETEST and sel["retest_fraction"] <= 0.15 + 1e-9
    for row in sel["questions"]:
        if row["kind"] == "retest":
            assert row["principles"]["P3_tie_stability_retest_of_round1_both_good"]
        else:
            assert row["principles"]["P1_uncertainty_votes"] is not None \
                or row["principles"]["P2_fold"] > 0 \
                or row["principles"]["P4_source_contrast"] > 0

    print("SELF-CHECK PASS")
    print("  questions: %d = %d new + %d cross-session retest (%.1f%%)"
          % (len(qs), len(news), len(retests), 100 * frac))
    print("  retests are round-1 both-good pairs: OK")
    print("  new pairs are round-1 unasked: OK; no in-round duplicates: OK")
    print("  record fields match round-1 export schema: OK")
    print("  svgs embedded: %d candidate pictures" % n_svg)
    return {"n_total": len(qs), "n_new": len(news), "n_retest": len(retests),
            "retest_fraction": round(frac, 3), "svgs": n_svg}


# ── byte-fidelity probe (acceptance: picture contains the stored detour) ──

def run_fidelity_probe():
    """Leg 1: slim_doc replay == full-doc replay (byte-identical svg).
    Leg 2: stripping stored waypoints changes the picture (the svg encodes
    the user's detour, not a re-route).  Leg 3: slim candidate docs keep the
    human-side geometry fields."""
    import copy
    import re
    import subprocess
    import tempfile
    pool = pp.collect_view_candidates()
    synth = load_synth_candidates()
    docs = {}
    for g, cands in pool.items():
        for c in cands:
            docs[c["cid"]] = c["doc"]
    for g, cands in synth.items():
        for c in cands:
            docs[c["cid"]] = c["doc"]
    # deterministic probe target: pool human candidate with stored waypoints
    target = None
    for cid in sorted(docs):
        if cid.endswith("c0") and any(e.get("waypoints")
                                      for e in docs[cid]["edges"]):
            target = cid
            break
    assert target, "no pool candidate with stored waypoints found"
    doc = docs[target]
    g = doc["graph"]
    tmp = Path(tempfile.mkdtemp(prefix="stdraw-fidelity-"))
    slim_svg = pp.render_doc_svg(pp.source_cld_for(g), doc, tmp / "slim")
    full = copy.deepcopy(doc)
    full_path = tmp / "full" / "_doc.json"
    (tmp / "full").mkdir(parents=True)
    full_path.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    cmd = [pp.dc.PY, "-m", "stdraw", "layout", str(pp.source_cld_for(g)),
           "--skip-3d", "--outdir", str(tmp / "full"), "--recipe", "auto",
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
    stripped_svg = pp.render_doc_svg(pp.source_cld_for(g), stripped,
                                     tmp / "stripped")
    leg2 = slim_svg != stripped_svg
    slim = pp.slim_doc(doc)
    kept = sum(1 for e in slim["edges"] if e.get("waypoints"))
    leg3 = kept == n_wp
    print("FIDELITY PROBE target=%s (graph=%s, edges_with_waypoints=%d)"
          % (target, g, n_wp))
    print("  leg1 slim vs full doc svg byte-identical: %s" % leg1)
    print("  leg2 waypoints-stripped svg differs:       %s" % leg2)
    print("  leg3 slim_doc keeps waypoint fields:       %s (%d/%d)"
          % (leg3, kept, n_wp))
    assert leg1 and leg2 and leg3
    print("FIDELITY PASS: picture = stored geometry (user detour preserved)")
    return {"target": target, "graph": g, "n_waypoint_edges": n_wp,
            "leg1_slim_eq_full": leg1, "leg2_strip_changes": leg2,
            "leg3_slim_keeps_fields": leg3}


def run_viewer():
    loso = load_loso()
    _r1q, asked, both_good = load_round1()
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
    synth_by_graph = load_synth_candidates()
    space = new_pair_space(pool_by_graph, synth_by_graph)
    scored = score_new_pairs(space, synth_by_graph, loso, asked)
    new_sel, per_graph = select_new(scored)
    retest_sel = select_retests(both_good, loso)
    assert len(retest_sel) == N_RETEST
    questions = build_questions(new_sel, retest_sel)
    svg_store, cand_meta = render_all(questions, pool_by_graph, synth_by_graph)
    selection = selection_record(new_sel, retest_sel, questions)
    write_session(questions, svg_store, cand_meta, selection)
    print("viewer round2: %d new + %d retest = %d questions -> %s"
          % (N_NEW, N_RETEST, len(questions), SESSION_DIR))
    print("  per-graph new-pair quota:", json.dumps(per_graph))
    for q in questions:
        print("  %s %-6s %-60s %s" % (q["qid"], q["kind"], q["pair_key"],
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
        run_viewer()
        shas()
    if cmd in ("selfcheck", "all"):
        run_selfcheck()
    if cmd in ("fidelity", "all"):
        run_fidelity_probe()
