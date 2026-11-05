#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""④ OR-Tools CP-SAT 同题对比（2026-11-05 default 令：前三步完成后才对比）。

同输入同输出（种子化 + num_workers=1），对比口径 = 五指标 + 新硬门 + 耗时。
solver 侧 = 正常环境（装了 ortools）；construct 侧 = monkeypatch 关掉 solver，
走同一 auto-v2 引擎的构造降级路径（engine=construct）。

用法：py -3.12 tests/compare_solver.py [--out docs/ortools-comparison.md]
输出：markdown 对比表 + 按「采纳/部分采纳/不采纳」的结论草稿。
"""
import argparse
import json
import random
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stdraw
from stdraw.model import Graph, Node, Edge
from stdraw.layout_auto import layout as auto_layout, AutoConfig
from stdraw.layout_auto import _has_solver
from stdraw.metrics import certificate_auto, scene_from_auto


def case_graphs():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for name in ("limits-to-growth", "classic-cld-growth-and-burden"):
        with open(os.path.join(root, "examples", name + ".cld"), encoding="utf-8") as f:
            out.append((name, stdraw.parse(f.read())))
    # 种子化随机 CLD 图（确定性）
    for seed in range(1, 9):
        rng = random.Random(seed)
        n = rng.randint(5, 9)
        m = n + rng.randint(2, n)
        g = Graph(name=f"random-seed{seed}", nodes=[], edges=[])
        ids = [f"v{i}" for i in range(1, n + 1)]
        for i, v in enumerate(ids):
            g.nodes.append(Node(id=v, label=f"变量{i + 1}"))
        seen = set()
        while len(g.edges) < m:
            a, b = rng.sample(ids, 2)
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            g.edges.append(Edge(a=a, b=b, polarity=rng.choice("+-")))
        out.append((f"random-seed{seed}", g))
    return out


def run_one(g, solver: bool):
    if not solver:
        stdraw.layout_auto._has_solver = lambda: False
    else:
        stdraw.layout_auto._has_solver = _has_solver_orig
    t0 = time.perf_counter()
    cfg = AutoConfig()
    v4 = auto_layout(g, cfg, "straight")
    dt = time.perf_counter() - t0
    cert = certificate_auto(scene_from_auto(v4))
    return v4, cert, dt


_has_solver_orig = staticmethod(_has_solver)


def fmt_row(name, engine, cert, dt):
    m = cert["metrics"]
    hard = all(cert["gates"][k] for k in
               ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                "min_gap_ge_16", "cv_le_035"))
    return (f"| {name} | {engine} | {m['crossings']} | {m['box_press_1px']} | "
            f"{m['edge_box_min_clear']} | {m['min_card_gap']} | {m['spacing_cv']} | "
            f"{cert['gates_passed']} | {'✓' if hard else '✗'} | {cert['grade']} | "
            f"{dt:.1f}s |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    rows = ["| 图 | 引擎 | 交叉 | 框压线 | 边-框净距 | 卡净距 | CV | 门禁 | 硬门 | 分级 | 耗时 |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    summary = []
    for name, g in case_graphs():
        for engine in ("cp-sat", "construct"):
            v4, cert, dt = run_one(g, engine == "cp-sat")
            real = v4["meta"]["position_engine"]
            assert real == engine, f"{name}: engine={real} 期望 {engine}"
            rows.append(fmt_row(name, engine, cert, dt))
            summary.append((name, engine, cert, dt))
            print(f"{name} [{engine}] cross={cert['metrics']['crossings']} "
                  f"press={cert['metrics']['box_press_1px']} "
                  f"clear={cert['metrics']['edge_box_min_clear']} "
                  f"cv={cert['metrics']['spacing_cv']} grade={cert['grade']} {dt:.1f}s")

    # 聚合统计
    def agg(engine):
        sel = [c for _, e, c, _ in summary if e == engine]
        n = len(sel)
        return {
            "mean_cross": sum(c["metrics"]["crossings"] for c in sel) / n,
            "press_viol": sum(c["metrics"]["box_press_1px"] for c in sel),
            "clear_fail": sum(1 for c in sel if not c["gates"]["edge_box_clear_ge_16"]),
            "anchor_viol": sum(c["metrics"]["anchor_violations"] for c in sel),
            "cv_mean": sum(c["metrics"]["spacing_cv"] for c in sel) / n,
            "grade_best": sum(1 for c in sel if c["grade"] == "最优"),
            "grade_ok": sum(1 for c in sel if c["grade"] in ("最优", "其次")),
        }

    s_cp, s_con = agg("cp-sat"), agg("construct")
    md = ["# OR-Tools CP-SAT 同题对比报告（auto-v2，2026-11-05）", "",
          "对比口径：同输入（种子化随机图 + 两仓内案例）、同引擎代码路径，",
          "唯一变量 = 定位层是否用 CP-SAT（num_workers=1 + seed 42，确定性）。", "",
          "## 明细", ""] + rows + ["",
          "## 聚合（9 图 × 2 引擎）", "",
          f"| 指标 | CP-SAT | 构造法 |", "|---|---|---|",
          f"| 平均交叉 | {s_cp['mean_cross']:.2f} | {s_con['mean_cross']:.2f} |",
          f"| 框压线总数 | {s_cp['press_viol']} | {s_con['press_viol']} |",
          f"| 净距门禁失败图数 | {s_cp['clear_fail']} | {s_con['clear_fail']} |",
          f"| 锚点违例总数 | {s_cp['anchor_viol']} | {s_con['anchor_viol']} |",
          f"| CV 均值 | {s_cp['cv_mean']:.3f} | {s_con['cv_mean']:.3f} |",
          f"| 最优级图数 | {s_cp['grade_best']} | {s_con['grade_best']} |",
          f"| 最优+其次图数 | {s_cp['grade_ok']} | {s_con['grade_ok']} |", ""]
    text = "\n".join(md)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("-> ", a.out)


if __name__ == "__main__":
    main()
