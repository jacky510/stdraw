#!/usr/bin/env python
"""Preference-data pipeline: perturbation synthetic pairs + spot-check pack +
pairwise blind-choice viewer (pre-v3 prerequisite card, "pref-pipeline").

Two deliverables, zero labeling cost:

  A. Synthetic preference pairs from graded perturbations of the 18 human
     anchors.  Perturbation machinery, parameters and the geometric hard gate
     are reused VERBATIM from diagnose_collapse.py (same corpus loader, same
     cumulative L1-L4 dose ladder, same gate rule) so every number is
     comparable with the hub-collapse diagnosis card.  Chain pairs
     "human > light > heavy" are emitted in a training format; source labels
     and preference records are stored in SEPARATE files (review consensus
     red line).

  B. Pairwise blind-choice viewer: 3-5 hub-family representative graphs,
     4-6 gate-passing candidates each (human / archived engine / fresh CLI
     recipes), deterministic question ordering (recorded LCG seed), 24
     first-round pairs + 6 retest repeats <= 30 questions, per-question
     records (graph / candidate_a / candidate_b / model_version / choice /
     duration_ms), export to JSON.  The viewer is presentation-only: it never
     reads or influences the aesthetic score, and source labels never enter
     the page (blinding preserved).

Deterministic: no RNG beyond a fixed recorded LCG seed for question order.
Red lines honored: read-only scorer; zero hardcoding into scorer artifacts;
no card ids / absolute paths in tracked outputs (repo leak gate).
"""
from __future__ import annotations

import copy
import html
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import diagnose_collapse as dc  # noqa: E402  (caliber reuse, read-only)

# The shared anchor loader rglobs benchmarks/manual for *.json; the pairwise
# session artifacts written by THIS card under benchmarks/manual/pairwise/
# are not anchors (no edges) and must be excluded from the loader — same
# spirit as the loader's own jacky-batch2 drafts exclusion.  Monkeypatched
# on the dc module namespace only; committed files stay untouched.
_orig_collect_positive_files = dc.collect_positive_files


def _collect_positive_files_no_pairwise(root):
    out = []
    for p in _orig_collect_positive_files(root):
        rel = str(p).replace("\\", "/")
        if "/manual/pairwise/" in rel:
            continue
        out.append(p)
    return out


dc.collect_positive_files = _collect_positive_files_no_pairwise

OUT_SYN = REPO / "benchmarks" / "aesthetic" / "pref-synthetic"
OUT_PAIRWISE = REPO / "benchmarks" / "manual" / "pairwise"
SESSION_DATE = "2026-11-21"
SESSION_DIR = OUT_PAIRWISE / ("session-" + SESSION_DATE)
MODEL_VERSION = "aesthetic-v2"
BUILD_ROOT = REPO / "benchmarks" / "aesthetic" / "pref-synthetic" / "_render_cache"

# ── dose ladder: verbatim caliber from diagnose_collapse.D6 ────────────────
LEVEL_NAMES = ("L0_original", "L1_jitter", "L2_swap2", "L3_break_mirror",
               "L4_off_align")


def perturb_copy(doc, level):
    """Verbatim copy of diagnose_collapse's cumulative perturbation
    (jitter table / swap ids / mirror reflect / off-align offsets)."""
    d = copy.deepcopy(doc)
    nodes = d["nodes"]
    ids = sorted(nodes)
    if level >= 1:
        for nid in ids:
            h = dc.ihash(nid)
            dx = dc.JITTER_TABLE[h % len(dc.JITTER_TABLE)]
            dy = dc.JITTER_TABLE[(h // len(dc.JITTER_TABLE)) % len(dc.JITTER_TABLE)]
            nodes[nid]["x"] = nodes[nid]["x"] + dx
            nodes[nid]["y"] = nodes[nid]["y"] + dy
    if level >= 2 and len(ids) >= 2:
        a, b = ids[0], ids[1]
        nodes[a]["x"], nodes[b]["x"] = nodes[b]["x"], nodes[a]["x"]
        nodes[a]["y"], nodes[b]["y"] = nodes[b]["y"], nodes[a]["y"]
    if level >= 3:
        vb = d.get("viewBox") or [0, 0, 960, 560]
        cx = float(vb[0]) + float(vb[2]) / 2.0
        for nid in ids[:len(ids) // 2]:
            nodes[nid]["x"] = 2.0 * cx - float(nodes[nid]["x"])
    if level >= 4:
        for i, nid in enumerate(ids):
            if i % 2 == 1:
                nodes[nid]["x"] = float(nodes[nid]["x"]) + dc.OFFALIGN_DX
                nodes[nid]["y"] = float(nodes[nid]["y"]) + dc.OFFALIGN_DY
    return d


def gate_viability(doc, graph_name):
    """Verbatim diagnose_collapse gate rule: min card gap >= 16px AND zero
    true box-press, on straight centre-to-centre segments (certificate
    proxy).  Crossings allowed to rise — that IS the degradation."""
    cert = dc.certificate_proxy(doc, graph_name)
    m = cert["metrics"]
    ok = (m["min_card_gap"] >= 16.0 and len(m.get("occlusions_true", [])) == 0)
    return ok, cert


SLIM_EDGE_KEYS = ("a", "b", "style", "anchors", "waypoints", "ctrl")


def slim_doc(doc):
    """Training-format candidate snapshot: graph / viewBox / nodes / edges.

    Edge entries keep the human-side geometry the engine's --from-layout
    reader consumes (style / anchors / waypoints / ctrl — the exact field
    set of _manual_edge_styles / _manual_anchors / _manual_waypoints /
    _manual_arc_ctrls), so feeding a slim_doc back through --from-layout
    replays the stored layout byte-faithfully instead of re-routing from
    bare a/b.  The rendered picture and the certificate-proxy counters
    (computed on the full stored doc) therefore stay same-source.
    """
    return {"graph": doc.get("graph"),
            "viewBox": doc.get("viewBox"),
            "nodes": doc["nodes"],
            "edges": [{k: e[k] for k in SLIM_EDGE_KEYS if k in e}
                      for e in doc["edges"]]}


# ═════════════════════════════ Part A: synthetic pairs ════════════════════

def run_pairs():
    labels, pos_docs, _neg, _eng, _src = dc.load_corpus()
    rej = {ln: 0 for ln in LEVEL_NAMES}
    per_anchor = {}
    pairs = []
    pair_labels = {}
    cand_store = {}
    n_pid = 0
    for path, doc0 in pos_docs:
        g = doc0["graph"]
        stem = Path(path).stem
        aid = stem  # anchor id = file stem (stable, repo-internal)
        viable_docs = {}
        steps = []
        for lv, ln in enumerate(LEVEL_NAMES):
            doc = doc0 if lv == 0 else perturb_copy(doc0, lv)
            ok, cert = gate_viability(doc, g)
            if not ok:
                rej[ln] += 1
                steps.append({"level": ln, "gate_rejected": True,
                              "min_card_gap": cert["metrics"]["min_card_gap"]})
                continue
            viable_docs[lv] = doc
            steps.append({"level": ln, "gate_rejected": False,
                          "min_card_gap": round(cert["metrics"]["min_card_gap"], 1),
                          "crossings": cert["metrics"]["crossings"]})
        # light = L1; heavy = deepest gate-viable cumulative level >= L2
        light_ok = 1 in viable_docs
        heavy_lv = max([lv for lv in viable_docs if lv >= 2], default=None)
        made = []
        if 0 in viable_docs and light_ok:
            pid = "sp%03d" % n_pid
            n_pid += 1
            cid_a = aid + "-human"
            cid_b = aid + "-L1"
            cand_store[cid_a] = slim_doc(viable_docs[0])
            cand_store[cid_b] = slim_doc(viable_docs[1])
            pairs.append({"pair_id": pid, "graph": g,
                          "candidate_a": cid_a, "candidate_b": cid_b,
                          "expected_order": "candidate_a"})
            pair_labels[pid] = {"source": "synthetic_perturbation",
                                "dose_level": "light",
                                "anchor": aid, "graph": g,
                                "a_level": "L0_original", "b_level": "L1_jitter"}
            made.append("light")
        if light_ok and heavy_lv is not None:
            pid = "sp%03d" % n_pid
            n_pid += 1
            cid_a = aid + "-L1"
            cid_b = aid + "-L%d" % heavy_lv
            cand_store[cid_b] = slim_doc(viable_docs[heavy_lv])
            pairs.append({"pair_id": pid, "graph": g,
                          "candidate_a": cid_a, "candidate_b": cid_b,
                          "expected_order": "candidate_a"})
            pair_labels[pid] = {"source": "synthetic_perturbation",
                                "dose_level": "heavy",
                                "anchor": aid, "graph": g,
                                "a_level": "L1_jitter",
                                "b_level": LEVEL_NAMES[heavy_lv]}
            made.append("heavy@L%d" % heavy_lv)
        per_anchor[aid] = {"graph": g, "pairs": made,
                           "light_gate_ok": light_ok,
                           "heavy_level": heavy_lv, "steps": steps}
    OUT_SYN.mkdir(parents=True, exist_ok=True)
    (OUT_SYN / "pairs.json").write_text(
        json.dumps({"schema": "stdraw.pref-synthetic.pairs/1",
                    "note": "preference records only — source/dose labels "
                            "live in labels.json (separated by red line)",
                    "pairs": pairs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (OUT_SYN / "labels.json").write_text(
        json.dumps({"schema": "stdraw.pref-synthetic.labels/1",
                    "source_constant": "synthetic_perturbation",
                    "gate_rule": dc_json_gate_rule(),
                    "gate_rejections_per_level": rej,
                    "per_pair": pair_labels,
                    "per_anchor": per_anchor}, ensure_ascii=False, indent=2,
                    sort_keys=True) + "\n", encoding="utf-8")
    cand_dir = OUT_SYN / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)
    for cid, docc in sorted(cand_store.items()):
        (cand_dir / (cid + ".json")).write_text(
            json.dumps(docc, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n", encoding="utf-8")
    n_light = sum(1 for p in pair_labels.values() if p["dose_level"] == "light")
    n_heavy = n_pid - n_light
    print("anchors: %d | light pairs: %d | heavy pairs: %d | total: %d"
          % (len(pos_docs), n_light, n_heavy, n_pid))
    print("gate rejections per level:", json.dumps(rej))
    return rej


def dc_json_gate_rule():
    return ("viability = min card gap >= 16px AND zero true box-press "
            "(certificate proxy on straight segments; identical to "
            "diagnose_collapse D6 gate_rule)")


# ═══════════════════════ render helper (engine-authoritative) ═════════════

def render_doc_svg(source_cld, doc, outdir):
    """Render a layout doc through the engine CLI (--from-layout, --skip-3d);
    return the largest embedded <svg> string.  Deterministic."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    doc_path = outdir / "_doc.json"
    doc_path.write_text(json.dumps(slim_doc(doc), ensure_ascii=False),
                        encoding="utf-8")
    cmd = [dc.PY, "-m", "stdraw", "layout", str(source_cld), "--skip-3d",
           "--outdir", str(outdir), "--recipe", "auto",
           "--from-layout", str(doc_path)]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    demo = outdir / "demo-2d.html"
    if not demo.exists():
        raise RuntimeError("render failed for %s: %s"
                           % (outdir.name, ((r.stderr or "") + (r.stdout or ""))[-300:]))
    h = demo.read_text(encoding="utf-8")
    import re
    svgs = re.findall(r"<svg[^>]*>.*?</svg>", h, re.S)
    return max(svgs, key=len)


def source_cld_for(graph):
    for base in (REPO / "benchmarks" / "manual" / "jacky-batch2" / "sources",
                 REPO / "benchmarks" / "corpus" / "classic",
                 REPO / "benchmarks" / "corpus" / "random"):
        p = base / (graph + ".cld")
        if p.exists():
            return p
    return None


# ═════════════════════════════ Part A2: spot-check pack ═══════════════════

SPOTCHECK_ANCHORS = ("classic-cld-manual-layout", "coupled-underinvestment-manual-layout",
                     "comb-supply-demand-manual-layout", "nonplanar-credit-manual-layout")


def run_spotcheck():
    labels, pos_docs, _neg, _eng, _src = dc.load_corpus()
    by_stem = {Path(p).stem: (p, d) for p, d in pos_docs}
    rows = []
    cache = BUILD_ROOT / "spotcheck"
    for stem in SPOTCHECK_ANCHORS:
        if stem not in by_stem:
            print("SPOTCHECK SKIP (anchor not found): %s" % stem)
            continue
        path, doc0 = by_stem[stem]
        g = doc0["graph"]
        src = source_cld_for(g)
        if src is None:
            print("SPOTCHECK SKIP (no .cld source): %s" % stem)
            continue
        levels = {}
        cells = []
        lvs = []
        light_ok = False
        heavy_lv = None
        for lv, ln in enumerate(LEVEL_NAMES):
            doc = doc0 if lv == 0 else perturb_copy(doc0, lv)
            ok, cert = gate_viability(doc, g)
            if lv == 1 and ok:
                light_ok = True
            if lv >= 2 and ok:
                heavy_lv = lv
            if lv in (0, 1, 2, 3, 4) and ok:
                lvs.append((lv, ln))
            levels[lv] = (ok, cert)
        chosen = [0]
        if light_ok:
            chosen.append(1)
        if heavy_lv is not None:
            chosen.append(heavy_lv)
        names = {"0": "原图（人工）", "1": "轻扰 L1", "2": "重扰 L2",
                 "3": "重扰 L3", "4": "重扰 L4"}
        for lv in chosen:
            doc = doc0 if lv == 0 else perturb_copy(doc0, lv)
            svg = render_doc_svg(src, doc, cache / ("%s-L%d" % (stem, lv)))
            ok, cert = levels[lv]
            cells.append({"level": lv, "label": names[str(lv)],
                          "gap": round(cert["metrics"]["min_card_gap"], 1),
                          "crossings": cert["metrics"]["crossings"],
                          "svg": svg})
        rows.append({"anchor": stem, "graph": g,
                     "family": (labels.get(g) or "-"), "cells": cells})
    page = render_spotcheck_html(rows)
    OUT_SYN.mkdir(parents=True, exist_ok=True)
    (OUT_SYN / "spotcheck.html").write_text(page, encoding="utf-8")
    print("spotcheck rows: %d -> %s" % (len(rows), OUT_SYN / "spotcheck.html"))
    return rows


def render_spotcheck_html(rows):
    parts = ["""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>扰动合成对 · 抽查包（原图 / 轻扰 / 重扰）</title>
<style>
 body{font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;margin:0;background:#f8fafc;color:#1e293b;line-height:1.6}
 .wrap{max-width:1280px;margin:0 auto;padding:24px 20px 80px}
 h1{font-size:21px;margin:0 0 4px} .sub{color:#64748b;font-size:14px;margin-bottom:18px}
 .row{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:22px}
 .row h2{font-size:16px;margin:0 0 10px}
 .tri{display:grid;grid-template-columns:repeat(3,minmax(230px,1fr));gap:14px}
 @media (max-width:860px){.tri{grid-template-columns:1fr}}
 .cell{min-width:0}
 .cell .tag{display:inline-block;font-size:12.5px;font-weight:600;padding:2px 10px;border-radius:999px;margin-bottom:6px}
 .tag.human{background:#dcfce7;color:#166534}.tag.light{background:#e0f2fe;color:#075985}.tag.heavy{background:#ffedd5;color:#9a3412}
 .box{border:1px solid #e2e8f0;border-radius:8px;background:#f7f3ea;padding:6px;overflow:auto;max-height:420px}
 .box svg{width:100%;height:auto;display:block}
 .meta{font-size:12px;color:#64748b;margin-top:4px}
 .note{font-size:13px;color:#b45309;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;margin-bottom:16px}
</style></head><body><div class="wrap">
<h1>扰动合成对 · 抽查包</h1>
<p class="sub">4 份锚点 ×（原图 / 轻扰 / 重扰）三联，引擎权威渲染（--from-layout 重放，--skip-3d）。请肉眼确认「扰动确实更差」后再让合成对全量进训练。</p>
<p class="note">判读提示：轻扰 = 每节点 ±3px 确定性抖动（整体观感轻微变糙）；重扰 = 累积剂量（若重扰档被几何硬门拦下，则展示为可通过门的最深档，并在角标注明档位——硬门：卡片间距 ≥16px 且零真压卡）。每格下方有最小间距(px)与交叉数，供辅助判读。交叉数为证书代理口径：按存储布局的卡片中心直连线段求交计算；用户绕行折线的意义正是消除直连交叉，故画面可见交叉可少于该数（渲染画面为存储布局的字节保真重放，与该数同源）。</p>"""]
    for r in rows:
        parts.append('<div class="row"><h2>%s <span style="color:#64748b;font-size:13px;font-weight:400">（图: %s · 族: %s）</span></h2><div class="tri">' % (
            html.escape(r["anchor"]), html.escape(r["graph"]), html.escape(str(r["family"]))))
        for c in r["cells"]:
            cls = "human" if c["level"] == 0 else ("light" if c["level"] == 1 else "heavy")
            parts.append('<div class="cell"><span class="tag %s">%s</span><div class="box">%s</div><div class="meta">最小卡片间距 %s px · 交叉 %s</div></div>' % (
                cls, html.escape(c["label"]), c["svg"], c["gap"], c["crossings"]))
        parts.append("</div></div>")
    parts.append("</div></body></html>")
    return "".join(parts)


# ═══════════════════ Part B: pairwise blind-choice viewer ═════════════════

VIEWER_GRAPHS = ("coupled-underinvestment", "nonplanar-credit",
                 "comb-supply-demand", "brand-flywheel",
                 "classic-cld-growth-and-burden")
TARGET_FIRST_ROUND = 24
TARGET_RETEST = 6
MAX_CANDS = 6
LCG_SEED = 20261121  # recorded; question order is reproducible from this


def lcg(seed):
    x = seed & 0x7FFFFFFF
    while True:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        yield x


def collect_view_candidates():
    """Per graph: gate-passing candidates from human / archived engine /
    fresh CLI recipes.  Returns {graph: [{cid, doc, source, recipe, grade,
    gap, crossings}]}.  cid is opaque (g<k>c<i>); source mapping never
    leaves this file's outputs (labels.json only)."""
    labels, pos_docs, _neg, eng_by_graph, _src = dc.load_corpus()
    cache = BUILD_ROOT / "viewer"
    out = {}
    for gi, g in enumerate(VIEWER_GRAPHS, 1):
        cands = []
        # human anchors
        for p, d in pos_docs:
            if d["graph"] == g:
                ok, cert = gate_viability(d, g)
                if ok:
                    cands.append({"cid": "g%dc%d" % (gi, len(cands)),
                                  "doc": d, "source": "human",
                                  "recipe": "manual",
                                  "grade": cert.get("grade", "-"),
                                  "gap": cert["metrics"]["min_card_gap"],
                                  "crossings": cert["metrics"]["crossings"]})
        # archived engine layout (negatives library, read-only)
        eng = eng_by_graph.get(g)
        if eng is not None:
            ok, cert = gate_viability(eng, g)
            if ok:
                cands.append({"cid": "g%dc%d" % (gi, len(cands)),
                              "doc": eng, "source": "archived-engine",
                              "recipe": "archived",
                              "grade": cert.get("grade", "-"),
                              "gap": cert["metrics"]["min_card_gap"],
                              "crossings": cert["metrics"]["crossings"]})
        # batch-2 certified engine drafts (archived; same caliber as the
        # diagnosis D4 candidate table)
        draft = (REPO / "benchmarks" / "manual" / "jacky-batch2" / "drafts"
                 / g / "layout.json")
        if draft.exists():
            d = json.loads(draft.read_text(encoding="utf-8"))
            d.setdefault("graph", g)
            ok, cert = gate_viability(d, g)
            if ok:
                cands.append({"cid": "g%dc%d" % (gi, len(cands)),
                              "doc": d, "source": "archived-draft",
                              "recipe": "draft",
                              "grade": cert.get("grade", "-"),
                              "gap": cert["metrics"]["min_card_gap"],
                              "crossings": cert["metrics"]["crossings"]})
        # fresh CLI recipes
        src = source_cld_for(g)
        if src is not None:
            for name, flags in dc.FRESH_RECIPES:
                outdir = cache / ("%s.%s" % (g, name))
                lj, cj = outdir / "layout.json", outdir / "certificate.json"
                if not (lj.exists() and cj.exists()):
                    cmd = [dc.PY, "-m", "stdraw", "layout", str(src),
                           "--skip-3d", "--outdir", str(outdir)] + list(flags)
                    subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                                   text=True, encoding="utf-8",
                                   errors="replace")
                if not (lj.exists() and cj.exists()):
                    continue
                d = json.loads(lj.read_text(encoding="utf-8"))
                d.setdefault("graph", g)
                ok, cert = gate_viability(d, g)
                if ok:
                    cands.append({"cid": "g%dc%d" % (gi, len(cands)),
                                  "doc": d, "source": "fresh-cli",
                                  "recipe": name,
                                  "grade": cert.get("grade", "-"),
                                  "gap": cert["metrics"]["min_card_gap"],
                                  "crossings": cert["metrics"]["crossings"]})
        # deterministic cap: keep first MAX_CANDS in the collection order
        # above (human -> archived -> fresh), which is itself fixed.
        out[g] = cands[:MAX_CANDS]
    return out


def pick_pairs(cands, k):
    """Deterministic k-pair subset covering candidates as evenly as possible.
    Pool = all combinations in candidate-id order; greedy pick minimizing
    how often each candidate has been used (ties keep pool order)."""
    import itertools
    pool = list(itertools.combinations(range(len(cands)), 2))
    used = [0] * len(cands)
    chosen = []
    pool_left = list(pool)
    while pool_left and len(chosen) < k:
        best = min(pool_left,
                   key=lambda pr: (used[pr[0]] + used[pr[1]],
                                   max(used[pr[0]], used[pr[1]]),
                                   pr))
        chosen.append(best)
        used[best[0]] += 1
        used[best[1]] += 1
        pool_left.remove(best)
    return chosen


def run_viewer():
    cand_by_graph = collect_view_candidates()
    session_root = BUILD_ROOT / "viewer" / "render"
    questions = []
    cand_meta = {}
    svg_store = {}
    qn = 0
    pool = []
    for g, cands in cand_by_graph.items():
        for c in cands:
            cand_meta[c["cid"]] = {"graph": g, "source": c["source"],
                                   "recipe": c["recipe"], "grade": c["grade"],
                                   "gap": round(c["gap"], 1),
                                   "crossings": c["crossings"]}
            svg_store[c["cid"]] = render_doc_svg(
                source_cld_for(g), c["doc"],
                session_root / c["cid"])
        k = 5  # per-graph quota; global cap below keeps first round <= 24
        for i, j in pick_pairs(cands, k):
            pool.append((g, cands[i]["cid"], cands[j]["cid"]))
    pool = pool[:TARGET_FIRST_ROUND]
    first_round = len(pool)
    # deterministic left/right + order: fixed recorded LCG seed
    rnd = lcg(LCG_SEED)
    order = list(range(len(pool)))
    for i in range(len(order) - 1, 0, -1):
        j = next(rnd) % (i + 1)
        order[i], order[j] = order[j], order[i]
    retest_idx = sorted(set(q * 4 for q in range(TARGET_RETEST)
                            if q * 4 < first_round))
    seq = []
    for i in order:
        seq.append(("first", pool[i]))
    for r in retest_idx:
        seq.append(("retest", pool[r]))
    for kind, (g, ca, cb) in seq:
        qn += 1
        left_is_a = bool(next(rnd) % 2)
        qid = "q%02d" % qn
        questions.append({
            "qid": qid, "graph": g,
            "candidate_a": ca, "candidate_b": cb,
            "left_is_a": left_is_a, "kind": kind,
            "is_retest": kind == "retest",
            "pair_key": "%s|%s|%s" % (g, min(ca, cb), max(ca, cb))})
    svgs_js = json.dumps(svg_store, ensure_ascii=False)
    qs_public = [{k: q[k] for k in ("qid", "graph", "candidate_a",
                                    "candidate_b", "left_is_a",
                                    "is_retest", "pair_key")}
                 for q in questions]
    viewer = render_viewer_html(qs_public, svgs_js)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    (SESSION_DIR / "viewer.html").write_text(viewer, encoding="utf-8")
    (SESSION_DIR / "questions.json").write_text(
        json.dumps({"schema": "stdraw.pairwise.questions/1",
                    "session": SESSION_DATE, "lcg_seed": LCG_SEED,
                    "model_version": MODEL_VERSION,
                    "n_first_round": first_round,
                    "n_retest": len(retest_idx),
                    "questions": qs_public}, ensure_ascii=False,
                    indent=2) + "\n", encoding="utf-8")
    (SESSION_DIR / "candidates.json").write_text(
        json.dumps({"schema": "stdraw.pairwise.candidates/1",
                    "note": "SOURCE LABELS — never render into the viewer "
                            "page; blinding depends on this separation",
                    "candidates": cand_meta}, ensure_ascii=False,
                    indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("viewer: %d first-round + %d retest = %d questions -> %s"
          % (first_round, len(retest_idx), len(questions), SESSION_DIR))
    for g, cands in cand_by_graph.items():
        print("  %-32s cands=%d %s" % (g, len(cands),
              [c["source"] + "/" + c["recipe"] for c in cands]))
    return questions, cand_meta


VIEWER_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pairwise 盲选 · stdraw 审美偏好标注</title>
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
<h1>Pairwise 盲选 · 同图两候选哪个更好？</h1>
<p class="sub">候选来源已隐藏（人工 / 引擎 / 模板均不可见）。凭第一眼观感判断即可，每题约 1 分钟。__NQ__ 题：含 __NRETEST__ 道重测题（同对会重复出现，按当时观感作答即可）。</p>
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
  document.getElementById("qbadge").textContent = q.is_retest ? "重测题" : "第 " + (QS.indexOf(q)+1) + " / " + QS.length + " 题";
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
            .replace("__DATE__", SESSION_DATE)
            .replace("__NQ__", str(len(questions)))
            .replace("__NRETEST__",
                     str(sum(1 for q in questions if q["is_retest"]))))


# ═════════════════════════════ self-checks ════════════════════════════════

def run_selfcheck():
    import hashlib
    ok = True
    pairs = json.loads((OUT_SYN / "pairs.json").read_text(encoding="utf-8"))
    labs = json.loads((OUT_SYN / "labels.json").read_text(encoding="utf-8"))
    for p in pairs["pairs"]:
        missing = [k for k in ("pair_id", "graph", "candidate_a",
                               "candidate_b", "expected_order")
                   if not p.get(k)]
        assert not missing, ("pair missing fields", p, missing)
        lid = labs["per_pair"][p["pair_id"]]
        assert lid["source"] == "synthetic_perturbation"
        assert lid["dose_level"] in ("light", "heavy")
        assert p["expected_order"] == "candidate_a"  # a is always the less perturbed
    # every candidate doc exists and parses
    cdir = OUT_SYN / "candidates"
    for p in pairs["pairs"]:
        for cid in (p["candidate_a"], p["candidate_b"]):
            d = json.loads((cdir / (cid + ".json")).read_text(encoding="utf-8"))
            assert d["nodes"] and d["edges"]
    # retest pairs auto-identifiable in the question pack
    qs = json.loads((SESSION_DIR / "questions.json").read_text(encoding="utf-8"))
    from collections import Counter
    pk = Counter(q["pair_key"] for q in qs["questions"])
    retests = [q for q in qs["questions"] if q["is_retest"]]
    for q in retests:
        assert pk[q["pair_key"]] >= 2, ("retest pair not repeated", q)
        firsts = [x for x in qs["questions"]
                  if x["pair_key"] == q["pair_key"] and not x["is_retest"]]
        assert firsts, ("retest without first-round twin", q)
    dup = sum(1 for v in pk.values() if v >= 2)
    print("SELF-CHECK PASS")
    print("  pairs: %d (chain a=less-perturbed verified)" % len(pairs["pairs"]))
    print("  question pack: %d questions, %d retest, %d repeated pair keys"
          % (len(qs["questions"]), len(retests), dup))
    for f in (OUT_SYN / "pairs.json", OUT_SYN / "labels.json",
              SESSION_DIR / "questions.json", SESSION_DIR / "candidates.json"):
        b = f.read_bytes()
        print("  sha256 %-52s %s" % (f.relative_to(REPO).as_posix(),
                                     hashlib.sha256(b).hexdigest()[:16]))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("pairs", "all"):
        run_pairs()
    if cmd in ("spotcheck", "all"):
        run_spotcheck()
    if cmd in ("viewer", "all"):
        run_viewer()
    if cmd in ("selfcheck", "all"):
        run_selfcheck()
