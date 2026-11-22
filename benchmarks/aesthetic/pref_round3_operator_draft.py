#!/usr/bin/env python
"""Round-3 pairwise annotation tool (operator recovery build, 2026-11-22).

Differences vs round 2 (jacky approved plan A):
  1. ZERO dose pairs — round 1/2 proved dose pairs only measure degradation
     spotting, not preference.
  2. NEW topologies: 3 fresh .cld graphs (chain-loop mix / figure-eight /
     dual-hub asymmetric) generated here, candidates from engine recipes
     (auto / arc / candidate-v1 / ortho), hard-gate filtered.
  3. ANCHOR-vs-ENGINE pairs: jacky's existing manual anchors against engine
     candidates of the same graph (the most direct preference signal).
  4. Byte-faithful rendering (post-spotfix slim_doc keeps anchors/waypoints).
  5. 30-50 questions incl. 3 cross-session retests of round-2 pairs.

Reuses pref_pipeline (pool/renderer/gate/LCG) and pref_round2 (viewer HTML,
question schema) read-only.
"""
import hashlib
import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import pref_pipeline as pp  # noqa: E402
import pref_round2 as pr2  # noqa: E402 (viewer template + schema reuse)

PY = sys.executable
SESSION_ID = "2026-11-22-round3"
SESSION_DIR = REPO / "benchmarks" / "manual" / "pairwise" / ("session-" + SESSION_ID)
DL_DIR = Path.home() / "Downloads" / "stdraw-pref-round3"
SOURCES = REPO / "benchmarks" / "manual" / "pref-round3" / "sources"
BUILD = pp.BUILD_ROOT / "viewer-round3"
MODEL_VERSION = "aesthetic-v3-beta"
LCG_SEED = 20261123
N_MIN, N_MAX = 30, 55
QUOTA = {"new_topo": 18, "disagree": 15, "anchor_engine": 10, "retest": 3}
GRAPH_MIN, GRAPH_MAX = 2, 8  # per-graph caps for candidate pairs
OLD_GRAPHS = ("classic-cld-growth-and-burden", "brand-flywheel",
              "comb-supply-demand", "nonplanar-credit", "coupled-underinvestment")

NEW_GRAPHS = {
    "chain-loop-mix": {
        "title": "链环混合：广告-口碑增长",
        "vars": [("ads", "广告投放"), ("aware", "品牌认知"), ("newcust", "新客流量"),
                 ("wom", "口碑推荐"), ("repeat", "复购率"), ("trust", "信任积累"), ("churn", "客户流失")],
        "edges": [("ads", "+", "aware"), ("aware", "+", "newcust"),
                  ("newcust", "+", "wom"), ("wom", "+", "newcust"),
                  ("aware", "+", "trust"), ("trust", "-", "churn"),
                  ("newcust", "-", "churn"), ("churn", "-", "trust")],
        "loops": [("R1", "口碑推荐环", "R", ["newcust", "wom"]),
                  ("R2", "信任流失环", "R", ["trust", "churn"])]},
    "figure-eight": {
        "title": "双环共点：绩效-士气八字环",
        "vars": [("pressure", "交付压力"), ("overtime", "加班强度"),
                 ("output", "短期产出"), ("morale", "团队士气"),
                 ("quality", "交付质量"), ("rework", "返工量")],
        "edges": [("pressure", "+", "overtime"), ("overtime", "+", "output"),
                  ("output", "-", "pressure"), ("pressure", "-", "morale"),
                  ("morale", "-", "rework"), ("rework", "+", "pressure"),
                  ("quality", "+", "morale")],
        "loops": [("B1", "压力消化环", "B", ["pressure", "overtime", "output"]),
                  ("R1", "士气侵蚀环", "R", ["pressure", "morale", "rework"])]},
    "dual-hub-asymmetric": {
        "title": "双枢纽非对称：供给-需求双中心",
        "vars": [("supply", "供给能力"), ("demand", "需求热度"),
                 ("price", "市场价格"), ("inventory", "库存水位"),
                 ("leadtime", "交付周期"), ("expansion", "扩产决策"),
                 ("marketing", "营销投入"), ("substitute", "替代品吸引力"),
                 ("margin", "利润空间")],
        "edges": [("demand", "+", "price"), ("price", "+", "margin"),
                  ("margin", "+", "expansion"), ("expansion", "+", "supply"),
                  ("supply", "-", "price"), ("demand", "-", "inventory"),
                  ("inventory", "-", "price"), ("supply", "-", "leadtime"),
                  ("leadtime", "-", "demand"), ("marketing", "+", "demand"),
                  ("margin", "-", "marketing"), ("substitute", "-", "demand")],
        "loops": [("B1", "价格调节环", "B", ["demand", "price", "margin", "expansion", "supply"]),
                  ("R1", "营销需求环", "R", ["margin", "marketing", "demand", "price"])]},
}


# ── step 1: new topology sources ────────────────────────────────────────────

def write_new_sources():
    SOURCES.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, g in NEW_GRAPHS.items():
        lines = ["# round-3 new topology: %s (%s)" % (g["title"], name),
                 'graph "%s"' % g["title"], ""]
        for vid, label in g["vars"]:
            lines.append('var %s "%s"' % (vid, label))
        lines.append("")
        for a, sign, b in g["edges"]:
            lines.append("%s -> %s %s" % (a, sign, b))
        lines.append("")
        for lid, lname, lkind, members in g["loops"]:
            lines.append('loop %s "%s" "%s" [%s]' % (lid, lname, lkind, ", ".join(members)))
        p = SOURCES / (name + ".cld")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append((name, g["title"], p))
    return paths


# ── step 2: candidates for the new graphs ───────────────────────────────────

def run_engine(src, outdir, extra=()):
    outdir = Path(outdir)
    if (outdir / "layout.json").exists():
        return json.loads((outdir / "layout.json").read_text(encoding="utf-8"))
    cmd = [PY, "-m", "stdraw", *extra, "--skip-3d", "--outdir", str(outdir),
           "layout", str(src)]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    lj = outdir / "layout.json"
    if not lj.exists():
        return None
    return json.loads(lj.read_text(encoding="utf-8"))


def cld_variants(src, k=4):
    """Deterministic declaration-order permutations of a .cld (same graph
    semantics, different engine input -> legitimately different layouts).
    Yields (tag, path)."""
    lines = src.read_text(encoding="utf-8").splitlines()
    var_i = [i for i, l in enumerate(lines) if l.startswith("var ")]
    edge_i = [i for i, l in enumerate(lines) if "->" in l and not l.startswith("#")]
    out = [(src.stem, src)]
    for k_i in range(1, k + 1):
        ls = list(lines)
        if var_i:
            rot = k_i % len(var_i)
            blk = lines[var_i[0]:var_i[-1] + 1]
            blk = blk[rot:] + blk[:rot]
            ls[var_i[0]:var_i[-1] + 1] = blk
        if edge_i:
            blk = lines[edge_i[0]:edge_i[-1] + 1]
            if k_i % 2:
                blk = blk[::-1]
            else:
                blk = blk[k_i % len(blk):] + blk[:k_i % len(blk)]
            ls[edge_i[0]:edge_i[-1] + 1] = blk
        p = src.parent / (src.stem + "-perm%d.cld" % k_i)
        p.write_text("\n".join(ls) + "\n", encoding="utf-8")
        out.append(("%s-perm%d" % (src.stem, k_i), p))
    return out


def gen_candidates(name, title, src):
    arms = []
    for tag, path in cld_variants(src, 4):
        arms.append((tag, (), path))
    arms += [("ortho", ("--recipe", "ortho"), src),
             ("pad", ("--value-pad", "26"), src)]
    docs = []
    for tag, extra, path in arms:
        outdir = BUILD / "cands" / (name + "-" + tag)
        try:
            d = run_engine(path, outdir, extra)
        except subprocess.TimeoutExpired:
            print("  arm %s: TIMEOUT" % tag)
            continue
        if d is None:
            print("  arm %s: no layout.json" % tag)
            continue
        ok, cert = pp.gate_viability(d, name)
        if not ok:
            print("  arm %s: GATE FAIL gap=%s" % (tag, cert["metrics"]["min_card_gap"]))
            continue
        slim = json.dumps(pp.slim_doc(d), sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(slim.encode("utf-8")).hexdigest()[:12]
        if any(c["sha"] == h for c in docs):
            print("  arm %s: duplicate of kept candidate" % tag)
            continue
        docs.append({"cid": "%s-%s" % (name, tag), "doc": d, "sha": h,
                     "source": "engine", "recipe": tag,
                     "gap": round(cert["metrics"]["min_card_gap"], 1),
                     "crossings": cert["metrics"]["crossings"],
                     "grade": cert.get("grade", "-")})
        print("  arm %s: KEPT (%d)" % (tag, len(docs)))
    docs.sort(key=lambda c: c["cid"])
    return docs[:6]


# ── step 3: pair space ──────────────────────────────────────────────────────

def pair_key(g, ca, cb):
    return "%s|%s|%s" % (g, min(ca, cb), max(ca, cb))


def asked_keys():
    asked = set()
    for sess in ("session-2026-11-21", "session-2026-11-22-round2"):
        qf = REPO / "benchmarks" / "manual" / "pairwise" / sess / "questions.json"
        if qf.exists():
            for x in json.loads(qf.read_text(encoding="utf-8"))["questions"]:
                asked.add(x["pair_key"])
    return asked


def final_disagreement():
    """Pairs where the committed final-comparison arms split on ranking.
    Returns {pair_key: votes_split} for old-graph pool pairs."""
    f = json.loads((REPO / "benchmarks" / "aesthetic" / "pref-ranking-final.json")
                   .read_text(encoding="utf-8"))
    out = {}
    arms = f.get("arms") or {}
    for arm, blob in arms.items():
        for g, ranking in (blob.get("rankings") or {}).items():
            for i, ca in enumerate(ranking):
                for cb in ranking[i + 1:]:
                    k = pair_key(g, ca, cb)
                    rec = out.setdefault(k, [0, 0])
                    rec[0] += 1 if arm in ("M0", "M1") else 0
                    rec[1] += 1 if arm in ("M2", "M2s") else 0
    return out


def load_r2_answered():
    f = json.loads((REPO / "benchmarks" / "manual" / "pairwise" /
                    "session-2026-11-22-round2" / "answers-2026-11-22.json")
                   .read_text(encoding="utf-8"))
    out = []
    for it in f["items"]:
        if it.get("is_retest") or it["choice"] not in ("a", "b"):
            continue
        out.append(it)
    return out


# ── step 4: anchor docs ─────────────────────────────────────────────────────

def anchor_docs():
    out = {}
    for base in (REPO / "benchmarks" / "manual",
                 REPO / "benchmarks" / "manual" / "jacky-batch2" / "exports"):
        for f in sorted(base.glob("*-manual-layout.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            g = d.get("graph")
            if g in OLD_GRAPHS:
                cid = "anchor-" + f.stem.replace("-manual-layout", "")
                if any(x["cid"] == cid for x in out.get(g, [])):
                    continue  # retest-classic-cld vs original same-graph dup
                out.setdefault(g, []).append(
                    {"cid": cid, "doc": d, "source": "human-anchor",
                     "recipe": "manual", "gap": None, "crossings": None,
                     "grade": "human"})
    return out


# ── assembly ────────────────────────────────────────────────────────────────

def main():
    sources = write_new_sources()

    # candidates for new graphs
    new_cands = {}
    for name, title, src in sources:
        cands = gen_candidates(name, title, src)
        assert len(cands) >= 3, ("new topology candidates too few", name, len(cands))
        new_cands[name] = cands
        print("candidates %s: %d" % (name, len(cands)))

    # pool candidates for old graphs (returns {graph: [candidate dicts]})
    pool_by_graph = pp.collect_view_candidates()

    # ── question assembly ──
    questions_meta = []  # (kind, graph, ca, cb, note)
    asked = asked_keys()

    # 1) new-topology candidate pairs (different recipes preferred)
    per_new = 0
    for name, title, src in sources:
        cands = new_cands[name]
        combos = list(itertools.combinations(cands, 2))
        combos.sort(key=lambda pr: (pr[0]["recipe"] == pr[1]["recipe"], pr[0]["cid"]))
        take = combos[:6]
        for ca, cb in take:
            questions_meta.append({"kind": "new_topo", "graph": name,
                                   "ca": ca, "cb": cb,
                                   "note": "new-topology candidate pair"})
            per_new += 1
        print("new-topo pairs %s: %d" % (name, len(take)))

    # 2) old-graph disagreement pairs (unasked pool pairs, max arm split)
    dis = final_disagreement()
    unasked = []
    for g in OLD_GRAPHS:
        pool = pool_by_graph.get(g, [])
        for ca, cb in itertools.combinations(pool, 2):
            k = pair_key(g, ca["cid"], cb["cid"])
            if k in asked:
                continue
            votes = dis.get(k)
            split = max(votes) if votes else 0
            unasked.append({"g": g, "ca": ca, "cb": cb, "k": k,
                            "split": split})
    unasked.sort(key=lambda r: (-r["split"], r["k"]))
    dis_take = []
    per_graph = {}
    for r in unasked:
        if len(dis_take) >= QUOTA["disagree"]:
            break
        if per_graph.get(r["g"], 0) >= 3:
            continue
        dis_take.append(r)
        per_graph[r["g"]] = per_graph.get(r["g"], 0) + 1
        questions_meta.append({"kind": "disagree", "graph": r["g"],
                               "ca": r["ca"], "cb": r["cb"],
                               "note": "final-comparison arm split %s" % r["split"]})

    # 3) anchor-vs-engine pairs
    anchors = anchor_docs()
    anchor_take = []
    for g in OLD_GRAPHS:
        an = anchors.get(g, [])
        pool = pool_by_graph.get(g, [])
        if not an or not pool:
            continue
        a = an[0]
        for c in pool[:3]:
            anchor_take.append({"g": g, "a": a, "b": c,
                                "k": pair_key(g, a["cid"], c["cid"])})
        if len(anchor_take) >= QUOTA["anchor_engine"]:
            break
    for r in anchor_take:
        questions_meta.append({"kind": "anchor_engine", "graph": r["g"],
                               "ca": r["a"], "cb": r["b"],
                               "note": "human anchor vs engine candidate"})

    # 4) cross-session retests of round-2 answered pairs
    r2 = load_r2_answered()
    r2 = [it for it in r2
          if not re.search(r"-L\d+$", it["candidate_a"])
          and not re.search(r"-L\d+$", it["candidate_b"])]  # zero-dose rule
    rnd = pp.lcg(LCG_SEED)
    picks = []
    idx = list(range(len(r2)))
    for i in range(len(idx) - 1, 0, -1):
        j = next(rnd) % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    seen_graphs = {}
    for i in idx:
        if len(picks) >= QUOTA["retest"]:
            break
        it = r2[i]
        g = it["graph"]
        if seen_graphs.get(g, 0) >= 1:
            continue
        seen_graphs[g] = 1
        picks.append(it)
    for it in picks:
        questions_meta.append({"kind": "retest", "graph": it["graph"],
                               "ca": {"cid": it["candidate_a"]},
                               "cb": {"cid": it["candidate_b"]},
                               "note": "cross-session retest of round-2 pair"})

    # cap check
    total = (per_new + len(dis_take) + len(anchor_take) + len(picks))
    assert N_MIN <= total <= 60, ("question total out of band", total)
    print("total questions:", total,
          "(new %d / disagree %d / anchor %d / retest %d)"
          % (per_new, len(dis_take), len(anchor_take), len(picks)))

    # ── docs registry + render ──
    docs = {}
    for name, title, src in sources:
        for c in new_cands[name]:
            docs[c["cid"]] = (name, c["doc"], c)
    for g in OLD_GRAPHS:
        for c in pool_by_graph.get(g, []):
            docs[c["cid"]] = (g, c["doc"], c)
    for g, lst in anchors.items():
        for a in lst:
            docs[a["cid"]] = (g, a["doc"], a)

    questions = []
    for qn, m in enumerate(questions_meta, 1):
        ca, cb = m["ca"]["cid"], m["cb"]["cid"]
        questions.append({"qid": "q%02d" % qn, "graph": m["graph"],
                          "candidate_a": ca, "candidate_b": cb,
                          "left_is_a": bool(next(rnd) % 2),
                          "kind": m["kind"], "is_retest": m["kind"] == "retest",
                          "pair_key": pair_key(m["graph"], ca, cb)})

    svg_store, cand_meta = {}, {}
    for q in questions:
        for cid in (q["candidate_a"], q["candidate_b"]):
            if cid in svg_store:
                continue
            g, doc, meta = docs[cid]
            svg_store[cid] = pp.render_doc_svg(
                source_cld_for(g), doc, BUILD / "viewer-round3" / cid)
            cand_meta[cid] = {"graph": g, "source": meta["source"],
                              "recipe": meta["recipe"],
                              "grade": meta.get("grade", "-"),
                              "gap": meta.get("gap") if meta.get("gap") is not None else "-",
                              "crossings": meta.get("crossings") if meta.get("crossings") is not None else "-"}

    qs_public = [{k: q[k] for k in ("qid", "graph", "candidate_a",
                                    "candidate_b", "left_is_a",
                                    "is_retest", "pair_key")}
                 for q in questions]

    # ── write session ──
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    html = pr2.render_viewer_html(qs_public, json.dumps(svg_store, ensure_ascii=False))
    html = html.replace("第二轮（自适应选题）", "第三轮（新拓扑+锚点对比 · 字节保真）")
    (SESSION_DIR / "viewer.html").write_text(html, encoding="utf-8")
    (SESSION_DIR / "questions.json").write_text(
        json.dumps({"schema": "stdraw.pairwise.questions/1",
                    "session": SESSION_ID, "lcg_seed": LCG_SEED,
                    "model_version": MODEL_VERSION,
                    "n_questions": len(questions),
                    "questions": qs_public},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SESSION_DIR / "candidates.json").write_text(
        json.dumps({"schema": "stdraw.pairwise.candidates/1",
                    "note": "SOURCE LABELS - never render into the viewer "
                            "page; zero dose pairs by design",
                    "candidates": cand_meta},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (SESSION_DIR / "selection-notes.json").write_text(
        json.dumps([{k: q[k] for k in ("qid", "kind", "graph", "pair_key")}
                    for q in questions], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    # Downloads copy
    DL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(SESSION_DIR / "viewer.html", DL_DIR / "viewer.html")
    print("session written:", SESSION_DIR)
    print("downloads copy:", DL_DIR)


def source_cld_for(graph):
    for base in (SOURCES,
                 REPO / "benchmarks" / "manual" / "jacky-batch2" / "sources",
                 REPO / "benchmarks" / "corpus" / "classic",
                 REPO / "benchmarks" / "corpus" / "random"):
        p = base / (graph + ".cld")
        if p.exists():
            return p
    # old-graph anchors: graph name may equal corpus name
    return None


if __name__ == "__main__":
    main()
