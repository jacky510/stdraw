#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WS2: slot placement layer + regularity metric tests.

cycle graph -> regular k-gon slots: 0 crossings, regular-polygon deviation ~0
(24px quantization tolerance);
chain graph -> collinear slots: straightness = 1;
general graph -> CP-SAT layered slots: in-row clearance hard constraint holds,
deterministic across two runs.
Without ortools the cycle/chain constructive branches still work and general
returns None (honest degradation).
"""
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.model import Graph, Node, Edge
from stdraw import placement, regularity
from stdraw.crossing_exact import undirected_edges


def mk(nodes_n, edge_pairs, name=""):
    g = Graph(name=name, nodes=[], edges=[])
    for i in range(nodes_n):
        g.nodes.append(Node(id=f"v{i+1}", label=f"x{i+1}"))
    for a, b in edge_pairs:
        g.edges.append(Edge(a=f"v{a}", b=f"v{b}", polarity="+"))
    return g


def seg_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        v = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0


def count_crossings(g, x, y):
    edges, _ = undirected_edges(g)
    total = 0
    for (i, (a, b)), (j, (c, d)) in itertools.combinations(enumerate(edges), 2):
        if {a, b} & {c, d}:
            continue
        if seg_cross((x[a], y[a]), (x[b], y[b]),
                     (x[c], y[c]), (x[d], y[d])):
            total += 1
    return total


def main():
    failures = []

    # A. cycle: regular pentagon
    cyc = [(i + 1, (i + 1) % 5 + 1) for i in range(5)]
    g = mk(5, cyc, "C5")
    res = placement.place(g, {v: 96 for v in g.node_ids()})
    if res is None:
        failures.append("cycle: place() returned None")
        print("FAIL cycle: place() None")
    else:
        x, y = res["x"], res["y"]
        crossings = count_crossings(g, x, y)
        positions = {v: (x[v], y[v]) for v in x}
        report = regularity.regularity_report(g, positions)
        dev = report["cycle_polygon_deviation"]
        ok = (crossings == 0 and report["cycle_polygon_deviation"] <= 0.05
              and res["structure"] == "cycle")
        if not ok:
            failures.append(f"cycle: crossings={crossings} dev={dev} "
                            f"report={report}")
        print(f"{'OK ' if ok else 'FAIL'} cycle C5: crossings={crossings} "
              f"deviation={report['cycle_polygon_deviation']} "
              f"structure={report['structure']} dominant={report['dominant']}")

    # B. chain: collinear
    chn = [(i + 1, i + 2) for i in range(4)]
    g = mk(5, chn, "P5")
    res = placement.place(g, {v: 96 for v in g.node_ids()})
    if res is None:
        failures.append("chain: place() returned None")
        print("FAIL chain: place() None")
    else:
        x, y = res["x"], res["y"]
        positions = {v: (x[v], y[v]) for v in x}
        s = regularity.chain_straightness(positions, g.node_ids())
        crossings = count_crossings(g, x, y)
        ok = (abs(s - 1.0) < 1e-9 and crossings == 0
              and res["structure"] == "chain")
        if not ok:
            failures.append(f"chain: straight={s} crossings={crossings}")
        print(f"{'OK ' if ok else 'FAIL'} chain P5: straightness={s:.3f} "
              f"crossings={crossings}")

    # C. general: CP-SAT layered slots (if available)
    if placement.has_solver():
        edges = [(1, 3), (2, 4), (3, 5), (4, 6), (5, 1), (6, 2), (1, 6), (3, 4)]
        g = mk(6, edges, "general6")
        rows = [["v1", "v2"], ["v3", "v4"], ["v5", "v6"]]
        widths = {f"v{i}": 96 for i in range(1, 7)}
        r1 = placement.place(g, widths, rows=rows)
        r2 = placement.place(g, widths, rows=rows)
        if r1 is None:
            failures.append("general: place() returned None")
            print("FAIL general: place() None (model infeasible or exception)")
        else:
            det = (r1["x"] == r2["x"] and r1["y"] == r2["y"])
            # in-row clearance recheck (24px slot scale)
            row_of = {v: i for i, vs in enumerate(rows) for v in vs}
            gaps_ok = True
            for vs in rows:
                for a, b in itertools.combinations(vs, 2):
                    if abs(r1["x"][a] - r1["x"][b]) < 96 + 16:
                        gaps_ok = False
            ok = det and gaps_ok
            if not ok:
                failures.append(f"general: det={det} gaps_ok={gaps_ok}")
            print(f"{'OK ' if ok else 'FAIL'} general6: engine={r1['engine']} "
                  f"status={r1.get('status')} deterministic={det} gaps_ok={gaps_ok}")
    else:
        print("SKIP general: ortools unavailable (cycle/chain constructive branches still verified)")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nAll placement/regularity tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# pytest entry (CI full-suite collection; script behavior unchanged).
def test_placement_bruteforce():
    assert main() == 0
