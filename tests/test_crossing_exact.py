#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WS2：精确交叉数层测试（经典图真值 + brute-force 交叉验证 + 确定性 + 降级）。

已知真值（文献，均为主流教科书/维基百科可核验口径）：
  cr(K5)=1、cr(K3,3)=1（Kuratowski 基本事实）
  cr(K6)=3（Guy 1960 公式 ⌊6/2⌋⌊5/2⌋⌊4/2⌋⌊3/2⌋/4 = 3；Saaty 1964 证明该
      公式对 n≤10 给出最优——是已证明真值。Wikipedia "Crossing number
      (graph theory)" §Complete graphs：公式值 1,3,9,… 对应 p=5,6,7,…）
  cr(Petersen)=2（Wikipedia "Petersen graph" §Embeddings 原文
      "The Petersen graph has crossing number 2"；并明示最常见的五角星
      画法有 5 处交叉但并非最优画法——「Petersen=5」是知名误读）
  可平面图 = 0（平面性 witness）
  细分不改变交叉数（homeomorphism invariance）
  ⚠ 常见误读对照：「K6=15」是 K6 的边数 |E|=C(6,2)=15，不是交叉数。

环境自报：main() 开头打印解释器版本与 ortools 可用性——proven/lb/coverage
证据必须连同该环境行一起引用（无 ortools 时全线 proven=False/lb=0/
coverage=partial 是诚实降级特征，见 docs/crossing-exact.md §9）。
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
    try:
        import ortools
        env_line = (f"python {sys.version.split()[0]} | ortools "
                    f"{ortools.__version__} available -> exact paths armed")
    except Exception:
        env_line = (f"python {sys.version.split()[0]} | ortools NOT available "
                    f"-> honest degradation expected (proven=False, lb=0, "
                    f"coverage=partial)")
    print(f"== 0. 环境: {env_line}")
    print("   文献真值: K5=1, K3,3=1, Petersen=2, K4=0, K3,3-subdiv=1, "
          "K6=3 (Guy/Saaty n<=10)")
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

    # == E. 桥/割点面三角化回归（ref-scrubbed）==
    # 贪心可平面子图 U 含桥/割点时，面游走顶点重复，旧 Triangulation 直接扇形
    # 三角化 → AssertionError「侧 x 相邻三角形数 1 != 2」（random-n20-i00 实测
    # 1.3s 崩）。回归用例 n8-m13-seed55：触发条件存在 + 旧侧计数必 !=2 + 修复后
    # （割点口袋拆分 _split_face）crossing_exact 优雅返回。
    g55 = nx.gnm_random_graph(8, 13, seed=55)
    reg = mk(8, [(a + 1, b + 1) for a, b in sorted(g55.edges())], "reg-s55")
    cores, _red = cx.safe_reduce(reg)
    cnodes, cedges = cores[0]
    U, F = cx._heuristic_planarization(cnodes, cedges)
    Ue = [cedges[i] for i in U]
    rot = cx._embed_U(cnodes, cedges, U)
    faces, ok = cx._faces_from_rotation(rot, cnodes, Ue)
    rep = [f for f in faces if len(set(f)) != len(f)]
    e_ok = bool(rep)
    if not e_ok:
        failures.append("reg-s55: 触发条件消失（面无重复顶点）——回归用例失效")
    print(f"{'OK ' if e_ok else 'FAIL'} reg-s55: UB 嵌入含重复顶点面 x{len(rep)} "
          f"(桥/割点口袋触发条件在位)")
    r = cx.crossing_exact(reg)
    ok2 = (isinstance(r.get("crossing_number"), int)
           and r.get("coverage") in ("full", "partial", "planar", "trivial"))
    if not ok2:
        failures.append(f"reg-s55: crossing_exact 未优雅返回 cr={r.get('crossing_number')} "
                        f"coverage={r.get('coverage')}")
    print(f"{'OK ' if ok2 else 'FAIL'} reg-s55: cr={r['crossing_number']} "
          f"proven={r['proven_optimal']} coverage={r['coverage']} "
          f"(ref-scrubbed 修复后零崩溃)")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nAll crossing-exact tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
