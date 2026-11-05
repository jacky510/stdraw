# -*- coding: utf-8 -*-
"""排布规律性（WS2 第 6 项）：结构检测 + 可计算的数学定义。

「规律性」在本模块全部给出**可计算的数学定义**（docs/crossing-exact.md §6
与本文件 docstring 同源），不做任何肉眼判断：

1. 结构检测 detect_structure：
   cycle   —— 连通且全部顶点度数 = 2（单环图）
   chain   —— 连通、度数 ≤ 2 且恰有 2 个度 1 顶点（链图）
   general —— 其余

2. 环图正多边形偏差 D_poly（值域 [0,1)，0 = 完美正 k 边形）：
   设画出的 k 个中心点 p_1..p_k，质心 c = mean(p_i)，半径 r_i = |p_i − c|，
   相邻极角差 δ_i = (θ_{i+1} − θ_i) mod 2π（θ 按环序）。
     radial_cv   = std(r) / mean(r)
     angular_cv  = std(δ) / mean(δ)
     D_poly      = 1 − exp(−(radial_cv + angular_cv))
   exp 形式保证单调、有界、可微解释：两项 CV 全 0 ⇔ D_poly = 0。

3. 链图直线度 S_straight（值域 [0,1]，1 = 完全共线/单调折线）：
   链顶点依链序 p_1..p_k， interior 转角 α_i = 相邻两段的夹角
   （cos 归一，∈[−1,1]，共线同向 = 1）。
     S_straight = mean_i (α_i + 1) / 2
   完全直线 = 1；随机折线 ≈ 0.5；多处反向 ≈ 0。

4. 对称轴对齐度 A_sym（值域 [0,1]，1 = 存在竖直轴使全部节点成对镜像）：
   候选轴 = 所有节点 x 坐标（以及其两两中点，容差 24px 槽位网格）。
   对每条候选轴 c，镜像伙伴命中率：
     hit(c) = |{i : ∃ j ≠ i, y_j = y_i, |x_j − (2c − x_i)| ≤ 24}| / k
   A_sym = max_c hit(c)。竖直轴约定与行结构（y 行）一致。

5. 全量报告 regularity_report：按结构检测选取主导项，全部指标都算、
   全部入证书（结构只是决定哪个是「主导指标」，不隐藏其他）。
"""
import math
from collections import defaultdict


def detect_structure(graph):
    """结构检测（见模块 docstring §1）。返回 {kind, cycle_nodes, chain_nodes}。"""
    nodes = graph.node_ids()
    adj = graph.adj_undirected()
    comps = _components(nodes, adj)
    cycle_nodes, chain_nodes = [], []
    for comp in comps:
        degs = [len(adj[v]) for v in comp]
        if degs and all(d == 2 for d in degs):
            cycle_nodes.append(sorted(comp))
        elif all(d <= 2 for d in degs) and degs.count(1) == 2:
            chain_nodes.append(sorted(comp))
    kind = "general"
    if len(comps) == 1:
        if cycle_nodes:
            kind = "cycle"
        elif chain_nodes:
            kind = "chain"
    return {"kind": kind, "cycle_nodes": cycle_nodes, "chain_nodes": chain_nodes}


def _components(nodes, adj):
    seen, comps = set(), []
    for v in nodes:
        if v in seen:
            continue
        stack, comp = [v], []
        seen.add(v)
        while stack:
            x = stack.pop()
            comp.append(x)
            for w in adj[x]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        comps.append(comp)
    return comps


def cycle_polygon_deviation(positions, cycle):
    """环图正多边形偏差 D_poly（见 §2）。positions: {node: (x, y)}。"""
    k = len(cycle)
    if k < 3:
        return 0.0
    pts = [positions[v] for v in cycle]
    cx = sum(p[0] for p in pts) / k
    cy = sum(p[1] for p in pts) / k
    rs = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    mr = sum(rs) / k
    radial_cv = (math.sqrt(sum((r - mr) ** 2 for r in rs) / k) / mr) if mr else 0.0
    angles = [math.atan2(p[1] - cy, p[0] - cx) for p in pts]
    deltas = []
    for i in range(k):
        d = (angles[(i + 1) % k] - angles[i]) % (2 * math.pi)
        deltas.append(d)
    md = sum(deltas) / k
    angular_cv = (math.sqrt(sum((d - md) ** 2 for d in deltas) / k) / md) if md else 0.0
    return 1.0 - math.exp(-(radial_cv + angular_cv))


def chain_straightness(positions, chain):
    """链图直线度 S_straight ∈ [0,1]（见 §3）。chain: 链序节点列表。"""
    if len(chain) < 3:
        return 1.0
    seq = chain if len(chain) >= 2 else []
    s = 0.0
    cnt = 0
    for i in range(1, len(seq) - 1):
        p0, p1, p2 = (positions[seq[i - 1]], positions[seq[i]],
                      positions[seq[i + 1]])
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        s += (cosang + 1.0) / 2.0
        cnt += 1
    return s / cnt if cnt else 1.0


def symmetry_axis_alignment(positions, tol=24.0):
    """对称轴对齐度 A_sym ∈ [0,1]（见 §4）。"""
    items = list(positions.items())
    if len(items) < 2:
        return 1.0
    xs = [p[0] for _, p in items]
    cands = set()
    for x in xs:
        cands.add(round(x / tol) * tol)
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            cands.add(round((xs[i] + xs[j]) / 2 / tol) * tol)
    best = 0.0
    for c in cands:
        hits = 0
        for v, (x, y) in items:
            mirror = 2 * c - x
            if any(abs(yy - y) <= 1e-6 and abs(xx - mirror) <= tol
                   for vv, (xx, yy) in items if vv != v):
                hits += 1
        best = max(best, hits / len(items))
    return best


def regularity_report(graph, positions):
    """全量规律性报告（主导指标由结构检测决定，其余照算照报）。"""
    st = detect_structure(graph)
    out = {
        "structure": st["kind"],
        "cycle_polygon_deviation": None,
        "chain_straightness": None,
        "symmetry_axis_alignment": round(
            symmetry_axis_alignment(positions), 3),
    }
    if st["cycle_nodes"]:
        vals = [cycle_polygon_deviation(positions, cyc)
                for cyc in st["cycle_nodes"]]
        out["cycle_polygon_deviation"] = round(max(vals), 3)
    if st["chain_nodes"]:
        vals = [chain_straightness(positions, ch) for ch in st["chain_nodes"]]
        out["chain_straightness"] = round(min(vals), 3)
    out["dominant"] = {
        "cycle": "cycle_polygon_deviation",
        "chain": "chain_straightness",
        "general": "symmetry_axis_alignment",
    }[st["kind"] if st["kind"] in ("cycle", "chain") else "general"]
    return out
