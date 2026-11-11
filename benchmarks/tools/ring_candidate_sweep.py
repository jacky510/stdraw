#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ring-candidate sweep (WorkBuddy task 2026-11-11, S2-2; D3 decision input).

Question: the ring-cycle main-ring selection key is
    (-k, chord_crossings, canonical)          -- coverage first
Would the alternative key
    (chord_crossings, -k, canonical)          -- chord crossings first
change the selected main ring, and if so, what happens to the layout-level
crossings and the hard gates?  This tool ONLY OBSERVES: the selection key in
stdraw/ringlayout.py stays frozen (S2-3 is blocked pending jacky's D3
ruling), and no engine byte changes.

Method, per corpus graph with n <= ringlayout.MAX_RING_N:
  1. deterministic ring detection probe (same code path the engine runs)
     collects every candidate main ring with (k, chord_crossings);
  2. current winner vs alternative winner are compared purely on those
     rows -- graphs that do not switch cannot drift (same selection ->
     byte-identical layout), reported as such without a re-layout;
  3. for switchers, TWO full auto layouts are produced:
       a. the engine as-is (current key), via subprocess;
       b. a forced-alternative run in-process: detect_ring is monkeypatched
          to return the alternative ring plan, everything downstream
          (trial gate, routing, certificate hard gates) runs unchanged.
     Both certificates' crossings / grade / hard-gate failures are logged.

Output: benchmarks/ring-candidate-sweep.md (regenerated atomically).
REPORT.md is never touched (AGENTS.md corpus rule).

Usage:  python benchmarks/tools/ring_candidate_sweep.py
"""

import glob
import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

from stdraw.dsl import parse                                  # noqa: E402
from stdraw import ringlayout as _rl                          # noqa: E402
from stdraw.layout_auto import AutoConfig, layout as _auto      # noqa: E402
from stdraw.metrics import certificate_auto, scene_from_auto    # noqa: E402

REPORT = os.path.join(REPO, "benchmarks", "ring-candidate-sweep.md")

# Chinese report face lives in this triple-quoted template (the language
# policy's EN-face check exempts triple-quoted blocks; the report .md itself
# is not an EN-face file).
_REPORT_TEMPLATE = """# ring-cycle 主环候选 sweep（D3 决策输入，S2-2）

> 生成：`benchmarks/tools/ring_candidate_sweep.py`（WorkBuddy 优化任务书
> 2026-11-11 S2-2）。**只观测，不改排序**——`stdraw/ringlayout.py` 的选环
> key `(-k, chord_crossings, canonical)` 保持冻结（S2-3 待 jacky 对 D3 拍板），
> 本报告不产生任何引擎字节变化；未切换图的布局按构造逐字节不变。

- 语料：`benchmarks/corpus/classic/*.cld` + `benchmarks/corpus/random/*.cld`（n50 退役族排除；探针仅覆盖 n≤12）
- 探针覆盖 {probed} 图；存在主环候选 {ring} 图；**备选 key 下会切换主环 {switch} 图**

备选 key = `(chord_crossings, -k, canonical)`（弦交叉数优先）。
切换图的完整对照含试验闸门后的布局级 crossings、grade 与硬门状态；
未切换图不重跑布局（同选择 ⇒ 同字节，零漂移）。

| 图 | n | 结果 | 现 key 选中 | 备选 key 选中 | 切换? | 明细 |
|---|---|---|---|---|---|---|
{table}

## 结论摘要

{conclusion}
"""

_CONCLUSION_NONE = """备选 key 下没有任何图切换主环：调整排序对语料零影响
（数据支持维持现 key，D3 可选「不改」）。"""

_CONCLUSION_SWITCH = """备选 key 会改变 {n} 张图的主环选择；逐图切换明细见上表
（含切换后布局级 crossings 升降与硬门通过情况）。
是否调整排序（S2-3）由 jacky 依本表拍板。"""


def corpus_graphs():
    pats = [os.path.join(REPO, "benchmarks", "corpus", "classic", "*.cld"),
            os.path.join(REPO, "benchmarks", "corpus", "random", "*.cld")]
    files = sorted(set(sum((glob.glob(p) for p in pats), [])))
    # n50 family is retired (never swept) -- excluded by the n<=12 probe
    # bound anyway; skip them here to keep the log honest.
    return [f for f in files if "n50" not in os.path.basename(f)]


def hard_gate_failures(cert):
    gates = cert.get("gates") or {}
    return sorted(k for k, v in gates.items()
                  if v is False and not k.endswith("_note"))


def probe(rows):
    """Current-key winner vs alternative-key winner, purely from rows."""
    cur = min(rows, key=lambda r: (-r["k"], r["chord_crossings"], r["ring"]))
    alt = min(rows, key=lambda r: (r["chord_crossings"], -r["k"], r["ring"]))
    return cur, alt


def run_subprocess_layout(cld, outdir):
    cmd = [sys.executable, "-m", "stdraw", "layout", cld,
           "--outdir", outdir, "--skip-3d"]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=REPO,
                       timeout=600)
    return r, time.time() - t0


def read_cert(outdir):
    with open(os.path.join(outdir, "certificate.json"),
              encoding="utf-8") as f:
        return json.load(f)


def forced_layout(g, force_ring, force_cross):
    """Full auto layout with detect_ring patched to the alternative plan."""
    orig = _rl.detect_ring

    def patched(graph, why=None):
        plan = orig(graph, why)
        if plan is not None and plan.get("ring") is not None:
            # residuals must track the forced ring (non-ring core nodes),
            # otherwise downstream node assignment misses them
            adj, _ = _rl._adjacency([(e.a, e.b) for e in graph.edges])
            core = set(v for v in adj if adj[v])
            ring = list(force_ring)
            plan = dict(plan)
            plan["ring"] = ring
            plan["k"] = len(ring)
            plan["chord_crossings"] = force_cross
            plan["residuals"] = sorted(v for v in core
                                       if v not in set(ring))
        return plan

    _rl.detect_ring = patched
    try:
        v4 = _auto(g, AutoConfig())
    finally:
        _rl.detect_ring = orig
    return v4


def main() -> int:
    rows_out = []
    n_probed = n_ring = n_switch = 0
    for cld in corpus_graphs():
        name = os.path.relpath(cld, REPO).replace("\\", "/")
        with open(cld, encoding="utf-8") as f:
            g = parse(f.read())
        n = len(g.nodes)
        n_probed += 1
        if n < 3 or n > _rl.MAX_RING_N:
            rows_out.append((name, n, "skip (outside ring probe bound "
                             f"3..{_rl.MAX_RING_N})", "-", "-", "-", "-"))
            continue
        why = {}
        _rl.detect_ring(g, why=why)
        cands = why.get("candidates")
        if not cands:
            rows_out.append((name, n, "no ring candidates (not "
                             "loop-dominated)", "-", "-", "-", "-"))
            continue
        n_ring += 1
        cur, alt = probe(cands)
        switch = cur["ring"] != alt["ring"]
        base = os.path.splitext(os.path.basename(cld))[0]
        if not switch:
            rows_out.append((name, n,
                             f"same winner k={cur['k']} "
                             f"chord_cross={cur['chord_crossings']} "
                             f"(no drift by construction)",
                             f"k{cur['k']}/x{cur['chord_crossings']}",
                             f"k{alt['k']}/x{alt['chord_crossings']}",
                             "no", "-"))
            continue
        n_switch += 1
        # a. engine as-is
        outdir = os.path.join(REPO, "benchmarks", "raw",
                              "ring-sweep-tmp", base + "-cur")
        r, secs = run_subprocess_layout(cld, outdir)
        if r.returncode not in (0, 1):
            rows_out.append((name, n, "current-key layout FAILED",
                             f"k{cur['k']}/x{cur['chord_crossings']}",
                             f"k{alt['k']}/x{alt['chord_crossings']}",
                             "YES", "layout error: " + r.stderr[-160:]))
            continue
        cur_cert = read_cert(outdir)
        # b. forced alternative ring
        try:
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(buf):
                v4 = forced_layout(g, alt["ring"], alt["chord_crossings"])
                cert = certificate_auto(scene_from_auto(v4),
                                        graph_name=base, layer="2D",
                                        graph=g, interactive="no",
                                        drag_layer="no")
            alt_cross = cert["metrics"]["crossings"]
            alt_grade = cert["grade"]
            fails = hard_gate_failures(cert)
            hard = ("all hard gates pass" if not fails
                    else "FAILED gates: " + ",".join(fails))
        except Exception as e:                     # honest error capture
            alt_cross, alt_grade, hard = None, None, f"forced run error: {e}"
        rows_out.append((name, n,
                         f"k{cur['k']}->k{alt['k']} "
                         f"(chord cross {cur['chord_crossings']}->"
                         f"{alt['chord_crossings']}; layout "
                         f"crossings {cur_cert['metrics']['crossings']}->"
                         f"{alt_cross}; grade {cur_cert['grade']}->"
                         f"{alt_grade}; {hard}; probe run {secs:.0f}s)",
                         f"k{cur['k']}/x{cur['chord_crossings']}",
                         f"k{alt['k']}/x{alt['chord_crossings']}",
                         "YES", hard))
    # ---- report -----------------------------------------------------
    table = "\n".join(
        "| `{}` | {} | {} | {} | {} | {} | {} |".format(
            name, n, res.replace("|", "\\|"),
            c1, c2, sw, det.replace("|", "\\|"))
        for (name, n, res, c1, c2, sw, det) in rows_out)
    if n_switch == 0:
        conclusion = _CONCLUSION_NONE
    else:
        conclusion = _CONCLUSION_SWITCH.format(n=n_switch)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write(_REPORT_TEMPLATE.format(probed=n_probed, ring=n_ring,
                                        switch=n_switch, table=table,
                                        conclusion=conclusion))
    print(f"report -> {REPORT}")
    print(f"probed={n_probed} with-candidates={n_ring} would-switch={n_switch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
