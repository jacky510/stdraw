# -*- coding: utf-8 -*-
"""3D 排布层（「最次」级交付形态）：节点排成规则立体。

五形体槽位生成 + 确定性指派，任意角度旋转、深度明暗、线框参考。

形体：sphere（Fibonacci 球面）/ cube（格点）/ tetra（四面体面网格）/
cone（同心环收缩至锥顶）。指派：贪心最近邻 + 两两交换优化最小化总边长
（确定性：槽位序、指派序、交换序全部固定；无 RNG）。

空间中弦线不相交由维度冗余保证；投影交叉由用户手中相机解决——
3D 层不做 2D 交叉承诺（诚实分级）。
"""
import math
from typing import Dict, List, Tuple


# ── 槽位生成（全部确定性，单位坐标，生成后统一缩放）────────────
def sphere_slots(n: int) -> List[Tuple[float, float, float]]:
    pts = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (i / max(n - 1, 1)) * 2
        r = math.sqrt(max(0.0, 1 - y * y))
        th = golden * i
        pts.append((math.cos(th) * r, y, math.sin(th) * r))
    return pts


def cube_slots(n: int) -> List[Tuple[float, float, float]]:
    m = max(2, math.ceil(n ** (1 / 3)))
    pts = []
    for z in range(m):
        for y in range(m):
            for x in range(m):
                pts.append(((x / (m - 1)) * 2 - 1,
                            (y / (m - 1)) * 2 - 1,
                            (z / (m - 1)) * 2 - 1))
    return pts[:n]


_TETRA_V = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]


def tetra_slots(n: int) -> List[Tuple[float, float, float]]:
    """四面体面网格：barycentric 层扫（每层落在 4 个面上，min 分量=0）。"""
    pts = []
    s = 3
    while len(pts) < n and s < 60:
        layer = []
        for i in range(s + 1):
            for j in range(s + 1 - i):
                for k in range(s + 1 - i - j):
                    l = s - i - j - k
                    b = (i, j, k, l)
                    if min(b) == 0:      # 面上
                        x = sum(c * v[0] for c, v in zip(b, _TETRA_V)) / s
                        y = sum(c * v[1] for c, v in zip(b, _TETRA_V)) / s
                        z = sum(c * v[2] for c, v in zip(b, _TETRA_V)) / s
                        layer.append((x, y, z))
        layer.sort()                     # 确定性顺序
        pts.extend(layer)
        s += 1
    # 兜底：满了之后截断；不够则补 Fibonacci 球面（如实记录）
    if len(pts) >= n:
        return pts[:n]
    extra = sphere_slots(n - len(pts))
    return pts + extra


def cone_slots(n: int) -> List[Tuple[float, float, float]]:
    """锥：锥顶 1 点 + 向下同心环（半径线性放大，环内均匀角度）。"""
    pts = [(0.0, 1.0, 0.0)]
    if n == 1:
        return pts
    rings = max(1, round(math.sqrt(n - 1)))
    per = max(1, (n - 1) // rings)
    t = 0
    placed = 1
    while placed < n:
        frac = (t + 1) / rings
        r = frac
        y = 1 - frac * 2
        cnt = min(per, n - placed) if placed + per < n else n - placed
        cnt = max(1, cnt)
        for k in range(cnt):
            ang = 2 * math.pi * k / cnt + 0.5 * t      # 层间错位（确定性）
            pts.append((math.cos(ang) * r, y, math.sin(ang) * r))
        placed += cnt
        t += 1
    return pts[:n]


SOLIDS = {"sphere": sphere_slots, "cube": cube_slots,
          "tetra": tetra_slots, "cone": cone_slots}


# ── 确定性指派：贪心最近邻 + 两两交换优化 ────────────────────
def assign(nodes: List[str], slots: List[Tuple[float, float, float]],
           edges: List[Tuple[str, str]]) -> Dict[str, Tuple[float, float, float]]:
    """节点→槽位。贪心（节点序固定）+ 全对交换 pass（收益为正才换，序固定）。"""
    avail = list(range(len(slots)))
    m = {v: None for v in nodes}
    # 多分量粗排：按邻接链 BFS 序出节点顺序（确定性），孤立节点最后
    adj: Dict[str, List[str]] = {v: [] for v in nodes}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    order, seen = [], set()
    for v in nodes:
        if v in seen or not adj[v]:
            continue
        stack = [v]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            order.append(u)
            for w in sorted(adj[u], reverse=True):
                if w not in seen:
                    stack.append(w)
    order += [v for v in nodes if v not in seen]

    def edge_len_sum():
        return sum(math.dist(m[a], m[b]) for a, b in edges
                   if m.get(a) and m.get(b))

    for v in order:
        if not avail:
            break
        # 贪心：选使已指派边长增量最小的槽位（平序取小，确定性）
        best, best_cost = None, None
        for si in avail:
            c = 0.0
            for w in adj[v]:
                if m.get(w) is not None:
                    c += math.dist(slots[si], m[w])
            if best_cost is None or c < best_cost - 1e-12:
                best, best_cost = si, c
        m[v] = slots[best]
        avail.remove(best)
    # 两两交换优化（最多 4 pass）
    node_list = order
    for _ in range(4):
        improved = False
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                a, b = node_list[i], node_list[j]
                m[a], m[b] = m[b], m[a]
                if edge_len_sum() < edge_len_sum() - 1e-9:
                    improved = True
                else:
                    m[a], m[b] = m[b], m[a]
        if not improved:
            break
    return m


def layout3d(graph_dict: dict, solid: str = "sphere", scale: float = 300.0):
    """graph_dict: {"nodes":[{id,label}], "edges":[{a,b}]} → {"positions": {...}}"""
    gen = SOLIDS[solid]
    ids = [n["id"] for n in graph_dict["nodes"]]
    edges = [(e["a"], e["b"]) for e in graph_dict["edges"]]
    slots = gen(len(ids))
    m = assign(ids, slots, edges)
    return {"solid": solid, "scale": scale,
            "positions": {v: [round(c * scale, 1) for c in m[v]] for v in ids}}
