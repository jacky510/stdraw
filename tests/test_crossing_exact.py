#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WS2：精确交叉数层测试（经典图真值 + brute-force 交叉验证 + 确定性 + 降级）。

已知真值（文献）：
  cr(K5)=1、cr(K3,3)=1（Kuratowski 基本事实）
  cr(K6)=3（Guy 1972：cr(K_n) 公式对 n≤10 完全证明）
  cr(Petersen)=2（Wikipedia "Petersen graph: crossing number 2"；cut-the-knot
      给出 girth 下界证明 k ≥ ⌈5/3⌉ = 2 + 2 交叉画法；注意五角星 naive 画法的
      5 处交叉不是交叉数）
  可平面图 = 0（平面性 witness）
  细分不改变交叉数（homeomorphism invariance）
"""
import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx

from stdraw.model import Graph, Node, Edge
from stdraw import crossing_exact as cx


def mk(n, edge_pairs, name=""):
    g = Graph(name=name, nodes=[], edges=[])
    for i in range(n):
        g.nodes.append(Node(id=f"v{i+1}", label=f"x{i+1}"))
    for a, b in edge_pairs:
        g.edges.append(Edge(a=f"v{a}", b=f"v{b}", polarity="+"))
    return g


def _planarizable(edges, cross_pairs):
    """交叉对集合（边对列表）→ 路径级平面化图 → 平面性。一条边可被多条
    交叉对共享（链式细分）。"""
    g = nx.Graph()
    g.add_nodes_from(set(x for e in edges for x in e))
    for a, b in edges:
        g.add_edge(a, b)
    splits = {}       # 边 idx → [a, X1, ..., b] 链段端点序列
    xc = 0
    for ei, ej in cross_pairs:
        X = f"X{xc}"
        xc += 1
        g.add_node(X)
        for idx in (ei, ej):
            a, b = edges[idx]
            chain = splits.get(idx)
            if chain is None:
                g.remove_edge(a, b)
                splits[idx] = [a, X, b]
                g.add_edge(a, X)
                g.add_edge(X, b)
            else:
                # 插到链中段（与前一交叉点之间）
                mid = chain[-2]
                g.remove_edge(mid, chain[-1])
                g.add_edge(mid, X)
                g.add_edge(X, chain[-1])
                chain.insert(-1, X)
    return nx.is_planar(g)


def brute_cr(graph, max_cross=2):
    """独立真值：枚举 ≤max_cross 个交叉对做平面化判定。
    返回 (cr 或 None, complete)。"""
    edges, _ = cx.undirected_edges(graph)
    g0 = nx.Graph()
    g0.add_nodes_from(graph.node_ids())
    for a, b in edges:
        g0.add_edge(a, b)
    if nx.is_planar(g0):
        return 0, True
    pairs = list(itertools.combinations(range(len(edges)), 2))
    good = [p for p in pairs if not cx._adjacent(edges[p[0]], edges[p[1]])]
    for p in good:
        if _planarizable(edges, [p]):
            return 1, True
    for p1, p2 in itertools.combinations(good, 2):
        if _planarizable(edges, [p1, p2]):
            return 2, True
    return None, False


def _rand_graph(rng, seed):
    n = rng.randint(5, 7)
    m = rng.randint(5, min(n * (n - 1) // 2, 11))
    pairs = rng.sample(list(itertools.combinations(range(1, n + 1), 2)), m)
    return mk(n, pairs, f"random-{seed}")


def main():
    failures = []
    petersen = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1)]
    petersen += [(i + 1, 6 + i) for i in range(5)]
    petersen += [(6 + i, 6 + (i + 2) % 5) for i in range(5)]
    k33sub = [(1, 4), (1, 5), (1, 7), (1, 6), (2, 4), (2, 5), (2, 6),
              (3, 4), (3, 5), (3, 6)]
    classics = [
        ("K5", mk(5, list(itertools.combinations(range(1, 6), 2)), "K5"), 1),
        ("K3,3", mk(6, [(1, 4), (1, 5), (1, 6), (2, 4), (2, 5), (2, 6),
                        (3, 4), (3, 5), (3, 6)], "K33"), 1),
        ("Petersen", mk(10, petersen, "Petersen"), 2),
        ("K4(planar)", mk(4, [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)],
                         "K4"), 0),
        ("K3,3-subdiv", mk(7, k33sub, "K33sub"), 1),
        ("K6", mk(6, list(itertools.combinations(range(1, 7), 2)), "K6"), 3),
    ]
    print("== A. 经典图真值 ==")
    for name, g, expect in classics:
        r = cx.crossing_exact(g)
        ok = r["crossing_number"] == expect and r["proven_optimal"]
        if not ok:
            failures.append(f"{name}: cr={r['crossing_number']}(期望{expect}) "
                            f"proven={r['proven_optimal']}")
        print(f"{'OK ' if ok else 'FAIL'} {name}: cr={r['crossing_number']} "
              f"proven={r['proven_optimal']} lb={r['lb']} gap={r['gap']} "
              f"coverage={r['coverage']}")

    print("== B. 随机图 brute-force 交叉验证（cr≤2 全枚举）==")
    rng = random.Random(20261105)
    for seed in range(8):
        g = _rand_graph(rng, seed)
        truth, complete = brute_cr(g)
        r = cx.crossing_exact(g)
        if complete and truth is not None:
            ok = r["crossing_number"] == truth
            if not ok:
                failures.append(f"random-{seed}: engine={r['crossing_number']} "
                                f"brute={truth}")
            print(f"{'OK ' if ok else 'FAIL'} random-{seed}: "
                  f"engine={r['crossing_number']} brute={truth} "
                  f"proven={r['proven_optimal']}")
        else:
            print(f"--  random-{seed}: brute 不完备(cr>2), "
                  f"engine={r['crossing_number']} gap={r['gap']}")

    print("== C. 确定性（两次运行逐字节一致）==")
    g = mk(10, petersen, "Petersen")
    j1 = json.dumps(cx.crossing_exact(g), sort_keys=True, ensure_ascii=False)
    j2 = json.dumps(cx.crossing_exact(g), sort_keys=True, ensure_ascii=False)
    if j1 != j2:
        failures.append("Petersen 两次运行不一致")
        print("FAIL 确定性")
    else:
        print("OK  确定性（逐字节一致）")

    print("== D. 无 ortools 优雅降级 ==")
    saved = {k: v for k, v in sys.modules.items() if "ortools" in k}
    for k in saved:
        del sys.modules[k]
    import builtins
    real_import = builtins.__import__

    def blocked(name, *a, **kw):
        if "ortools" in name:
            raise ImportError("blocked for test")
        return real_import(name, *a, **kw)
    builtins.__import__ = blocked
    try:
        r = cx.crossing_exact(g)
    finally:
        builtins.__import__ = real_import
        sys.modules.update(saved)
    if r["proven_optimal"] or r["coverage"] != "partial":
        failures.append(f"降级路径: proven={r['proven_optimal']} "
                        f"coverage={r['coverage']}")
        print("FAIL 降级: 应 exact=False 且 coverage=partial")
    else:
        print(f"OK  降级: cr={r['crossing_number']} proven=False "
              f"coverage=partial（如实标注）")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nAll crossing-exact tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
