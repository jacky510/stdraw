#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""(4) OR-Tools CP-SAT same-problem comparison (2026-11-05 default order:
compare only after the first three steps are done).

Same input, same output (seeded + num_workers=1); comparison caliber = five
metrics + new hard gates + runtime. The solver side runs in the normal
environment (ortools installed); the construct side monkeypatches the solver
off and takes the same auto-v2 engine's constructive degradation path
(engine=construct).

Usage: py -3.12 tests/compare_solver.py [--out docs/ortools-comparison.md]
Output: a markdown comparison table + a conclusion draft classified as
"adopt / partially adopt / do not adopt".
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
    # seeded random CLD graphs (deterministic)
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

    rows = ["| graph | engine | crossings | box press | edge-box clear | card clear | CV | gates | hard gates | grade | time |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    summary = []
    for name, g in case_graphs():
        for engine in ("cp-sat", "construct"):
            v4, cert, dt = run_one(g, engine == "cp-sat")
            real = v4["meta"]["position_engine"]
            assert real == engine, f"{name}: engine={real} expected {engine}"
            rows.append(fmt_row(name, engine, cert, dt))
            summary.append((name, engine, cert, dt))
            print(f"{name} [{engine}] cross={cert['metrics']['crossings']} "
                  f"press={cert['metrics']['box_press_1px']} "
                  f"clear={cert['metrics']['edge_box_min_clear']} "
                  f"cv={cert['metrics']['spacing_cv']} grade={cert['grade']} {dt:.1f}s")

    # aggregate statistics
    def agg(engine):
        sel = [c for _, e, c, _ in summary if e == engine]
        n = len(sel)
        return {
            "mean_cross": sum(c["metrics"]["crossings"] for c in sel) / n,
            "press_viol": sum(c["metrics"]["box_press_1px"] for c in sel),
            "clear_fail": sum(1 for c in sel if not c["gates"]["edge_box_clear_ge_16"]),
            "anchor_viol": sum(c["metrics"]["anchor_violations"] for c in sel),
            "cv_mean": sum(c["metrics"]["spacing_cv"] for c in sel) / n,
            "grade_best": sum(1 for c in sel if c["grade"] == "best"),
            "grade_ok": sum(1 for c in sel if c["grade"] in ("best", "second")),
        }

    s_cp, s_con = agg("cp-sat"), agg("construct")
    md = ["# OR-Tools CP-SAT Same-Problem Comparison Report (auto-v2, 2026-11-05)", "",
          "Comparison caliber: same input (seeded random graphs + two in-repo examples), same engine code path;",
          "the only variable = whether the placement layer uses CP-SAT (num_workers=1 + seed 42, deterministic).", "",
          "## Details", ""] + rows + ["",
          "## Aggregates (9 graphs x 2 engines)", "",
          "| metric | CP-SAT | constructive |", "|---|---|---|",
          f"| mean crossings | {s_cp['mean_cross']:.2f} | {s_con['mean_cross']:.2f} |",
          f"| total box press | {s_cp['press_viol']} | {s_con['press_viol']} |",
          f"| graphs failing the clearance gate | {s_cp['clear_fail']} | {s_con['clear_fail']} |",
          f"| total anchor violations | {s_cp['anchor_viol']} | {s_con['anchor_viol']} |",
          f"| mean CV | {s_cp['cv_mean']:.3f} | {s_con['cv_mean']:.3f} |",
          f"| best-grade graphs | {s_cp['grade_best']} | {s_con['grade_best']} |",
          f"| best+second graphs | {s_cp['grade_ok']} | {s_con['grade_ok']} |", ""]
    text = "\n".join(md)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("-> ", a.out)


if __name__ == "__main__":
    main()
