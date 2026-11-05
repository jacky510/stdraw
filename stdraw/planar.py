# -*- coding: utf-8 -*-
"""Planarity-Aware 2D 布局层：平面嵌入 + st 编号 + 对偶最长路 + 车道装箱。

布局数学（Rosenstiehl–Tarjan 可见性表示 → 线全严格竖直、0 交叉有定理保证），
图数据经 Graph 模型显式传入，不耦合任何具体业务模板。

不变量（check.geometry_report 逐项验证）：
  - 每条边一根严格竖线（0 拐弯 0 斜线）；平行/共线竖线永不相交；
  - 间距 < GAP_NEAR 的两列，y 覆盖带（含 1 行余量）不重叠；
  - 引线 bar 只横贯自身关联线列；无关线允许从卡片底下穿过（卡片不透明遮挡）；
  - 同行卡片互不重叠且留 CARD_GAP 间隙；坐标 2px 网格。

前提：core 子图（去掉孤立节点后）必须为平面图——本层不做平面化降级，
非平面输入抛 NotPlanarError（诚实边界：降级策略属布局层可替换实现，M1+）。
"""
import json
from collections import defaultdict, deque
from dataclasses import dataclass

import networkx as nx

from .model import Graph


class NotPlanarError(Exception):
    pass


@dataclass
class LayoutConfig:
    fs_title: float = 12.5        # 标题字号
    fs_value: float = 14.0        # 数值字号（加粗）
    card_h: int = 42
    card_min: int = 96            # 卡片最小宽
    card_pad: int = 22            # 标题左右留白
    card_gap: int = 8             # 同行卡片最小间隙
    pitch: int = 56               # 行距（卡 42 + 线隙 14）
    top: int = 76                 # 首行中心 y
    park_y: int = 26              # 孤立节点停车带中心 y
    left: int = 40                # 首列最小 x
    gap_col: int = 8              # 相邻线列最小间距（无条件）
    gap_near: int = 16            # 间距小于此值时要求 y 覆盖不相交
    target_w: int = 1280
    target_h: int = 680           # 1280×800 档 svg 净视口（评分基准）
    aspect_min: float = 1.72      # 内容窄而高时拉伸列距到该比例


def text_px(s, fs, bold=False):
    w = 0.0
    for ch in s:
        w += fs if ord(ch) > 0x2E7F else fs * 0.58
    return w * (1.05 if bold else 1.0)


class PlanarLayout:
    def __init__(self, graph: Graph, config: LayoutConfig = None):
        self.cfg = config or LayoutConfig()
        self.graph = graph
        self.id2n = graph.id2node()
        self.nodes = graph.node_ids()
        self.edges = [(e.a, e.b) for e in graph.edges]
        adj = graph.adj_undirected()
        self.deg0 = [n for n in graph.node_ids() if not adj[n]]
        self.core = [n for n in graph.node_ids() if adj[n]]
        self.core_set = set(self.core)
        self.real_adj = defaultdict(set)
        for a, b in self.edges:
            self.real_adj[a].add(b)
            self.real_adj[b].add(a)
        # 逐节点卡片宽：max(标题, 数值) + 留白，2px 网格
        c = self.cfg
        self.card_w = {}
        for nid in self.nodes:
            nd = self.id2n[nid]
            w = max(text_px(nd.label, c.fs_title) + c.card_pad,
                    text_px(nd.value, c.fs_value, bold=True) + 22,
                    c.card_min)
            self.card_w[nid] = int((w + nd.extra_w + 1) // 2 * 2)
        self._g = None  # 当前候选的 st 编号

    # ── 1. 平面嵌入 → 旋转系统 ─────────────────────────────
    def build_rotation(self):
        G = nx.Graph()
        G.add_nodes_from(self.core)
        G.add_edges_from(self.edges)
        planar, emb = nx.check_planarity(G)
        if not planar:
            raise NotPlanarError(
                f"core 子图非平面（{len(self.core)} 节点 / {len(self.edges)} 边）——"
                "2D 平面层不适用，请降级 3D 层或走均匀排布形态")
        return {v: list(emb.neighbors_cw_order(v)) for v in self.core}

    @staticmethod
    def faces_of(rot):
        seen = set()
        faces = []
        half2face = {}
        for u in rot:
            for v in rot[u]:
                if (u, v) in seen:
                    continue
                f = []
                cu, cv = u, v
                while (cu, cv) not in seen:
                    seen.add((cu, cv))
                    f.append(cu)
                    half2face[(cu, cv)] = len(faces)
                    nxt = rot[cv][(rot[cv].index(cu) + 1) % len(rot[cv])]
                    cu, cv = cv, nxt
                faces.append(f)
        return faces, half2face

    def euler_check(self, rot):
        faces, h2f = self.faces_of(rot)
        V = len(rot)
        E = sum(len(l) for l in rot.values()) // 2
        F = len(faces)
        edge_faces = defaultdict(set)
        for (u, v), fi in h2f.items():
            edge_faces[frozenset((u, v))].add(fi)
        assert all(len(s) == 2 for s in edge_faces.values()), "edge not in exactly 2 faces"
        assert V - E + F == 2, f"V-E+F={V}-{E}+{F}!=2 (rotation system invalid)"
        assert E == len(edge_faces), "multi-edge?"
        return faces, h2f

    # ── 2. 连通 + 三角剖分（补边） ─────────────────────────
    def augment(self, rot):
        rot = {v: list(l) for v, l in rot.items()}
        dummy = set()
        G = nx.Graph({v: list(l) for v, l in rot.items()})
        comps = list(nx.connected_components(G))
        while len(comps) > 1:
            a = next(iter(comps[0]))
            b = next(iter(comps[1]))
            rot[a].append(b)
            rot[b].append(a)
            dummy.add(frozenset((a, b)))
            G = nx.Graph({v: list(l) for v, l in rot.items()})
            comps = list(nx.connected_components(G))
        while True:
            faces, _ = self.faces_of(rot)
            target = None
            for f in faces:
                if len(f) > 3:
                    target = f
                    break
            if target is None:
                break
            n = len(target)
            placed = False
            for i in range(n):
                a, succ, b2, nxt2 = target[i], target[(i + 1) % n], target[(i + 2) % n], target[(i + 3) % n]
                if frozenset((a, b2)) not in [frozenset(p) for p in dummy] and b2 not in rot[a]:
                    rot[a].insert(rot[a].index(succ), b2)
                    rot[b2].insert(rot[b2].index(nxt2), a)
                    dummy.add(frozenset((a, b2)))
                    placed = True
                    break
            assert placed, "triangulation stuck"
        faces, _ = self.faces_of(rot)
        assert all(len(f) == 3 for f in faces), "not fully triangulated"
        self.euler_check(rot)
        return rot, dummy

    # ── 3. Even–Tarjan st 编号 ────────────────────────────
    @staticmethod
    def st_numbering(adj, s, t):
        n = len(adj)
        dfi, low, parent, children = {}, {}, {}, defaultdict(list)
        cyc_back = defaultdict(list)
        cyc_fwd = defaultdict(list)
        cnt = [0]

        def dfs(v):
            dfi[v] = cnt[0]; cnt[0] += 1
            low[v] = dfi[v]
            nbrs = list(adj[v])
            if v == t and s in nbrs:
                nbrs.remove(s); nbrs.insert(0, s)
            for w in nbrs:
                if w not in dfi:
                    parent[w] = v; children[v].append(w)
                    dfs(w)
                    low[v] = min(low[v], low[w])
                elif w != parent.get(v) or parent.get(v) is None:
                    if dfi[w] > dfi[v]:
                        cyc_fwd[v].append(w)
                        cyc_back[w].append(v)
                    else:
                        cyc_back[v].append(w)
                        cyc_fwd[w].append(v)
                    low[v] = min(low[v], dfi[w])

        dfs(t)
        assert len(dfi) == n
        old_edge = {frozenset((s, t))}
        old_v = {s, t}

        def find_path(v):
            for w in cyc_back[v]:
                if frozenset((v, w)) not in old_edge:
                    old_edge.add(frozenset((v, w)))
                    return [v, w]
            for w in children[v]:
                if frozenset((v, w)) not in old_edge:
                    old_edge.add(frozenset((v, w)))
                    path = [v, w]
                    while w not in old_v:
                        nxt = None
                        for x in adj[w]:
                            if frozenset((w, x)) in old_edge:
                                continue
                            if (dfi.get(x) == low[w]) or (low.get(x) == low[w] and x in children[w]):
                                nxt = x
                                break
                        assert nxt is not None, "pathfinder case2 stuck"
                        old_v.add(w)
                        old_edge.add(frozenset((w, nxt)))
                        path.append(nxt)
                        w = nxt
                    return path
            for w in cyc_fwd[v]:
                if frozenset((v, w)) not in old_edge:
                    old_edge.add(frozenset((v, w)))
                    path = [v, w]
                    while w not in old_v:
                        x = parent[w]
                        old_v.add(w)
                        old_edge.add(frozenset((w, x)))
                        path.append(x)
                        w = x
                    return path
            return None

        stack = [t, s]
        g = {}
        i = 0
        guard = 0
        while stack:
            guard += 1
            assert guard < 10000, "st-numbering loop guard"
            v = stack.pop()
            p = find_path(v)
            if p:
                for x in reversed(p[:-1]):
                    stack.append(x)
            else:
                i += 1
                g[v] = i
        assert len(g) == n and g[s] == 1 and g[t] == n, f"st fail {len(g)} {g[s]} {g[t]}"
        for v in adj:
            if v in (s, t):
                continue
            assert any(g[w] < g[v] for w in adj[v]) and any(g[w] > g[v] for w in adj[v]), \
                f"st property violated at {v}"
        return g

    # ── 4. 可见性表示 ─────────────────────────────────────
    def visibility(self, rot, g, st_edge):
        u0, v0 = st_edge
        assert g[u0] < g[v0]
        num2v = sorted(rot, key=lambda v: g[v])
        Y = {}
        for v in num2v:
            preds = [u for u in rot[v] if g[u] < g[v]]
            Y[v] = 0 if not preds else 1 + max(Y[u] for u in preds)
        faces, h2f = self.faces_of(rot)
        outer = h2f[(u0, v0)]
        for polarity in (0, 1):
            arcs = defaultdict(list)
            nodes = [f"f{i}" for i in range(len(faces)) if i != outer] + \
                    [frozenset((u, v)) for (u, v) in h2f if g[u] < g[v]]
            indeg = {n: 0 for n in nodes}

            def add_arc(a, b):
                arcs[a].append(b)
                indeg[b] += 1
            for (u, v), fi in h2f.items():
                if g[u] > g[v]:
                    continue
                fj = h2f[(v, u)]
                L, R = (f"f{fi}", f"f{fj}") if polarity == 0 else (f"f{fj}", f"f{fi}")
                e = frozenset((u, v))
                if L in indeg:
                    add_arc(L, e)
                if R in indeg:
                    add_arc(e, R)
            dq = deque([n for n in nodes if indeg[n] == 0])
            tau = {n: 0 for n in nodes}
            seen = 0
            while dq:
                a = dq.popleft()
                seen += 1
                for b in arcs[a]:
                    if tau[b] < tau[a] + 1:
                        tau[b] = tau[a] + 1
                    indeg[b] -= 1
                    if indeg[b] == 0:
                        dq.append(b)
            if seen != len(nodes):
                continue
            Xe = {e: tau[e] for e in tau if isinstance(e, frozenset)}
            if self.verify_unit(rot, g, Y, Xe):
                return Y, Xe
        return None

    @staticmethod
    def bar_span(v, Xe_incident):
        xs = [Xe_incident[e] for e in Xe_incident if v in e]
        return min(xs) - 1, max(xs) + 1

    def verify_unit(self, rot, g, Y, Xe):
        inc = defaultdict(dict)
        for e, x in Xe.items():
            u, v = tuple(e)
            inc[u][e] = x
            inc[v][e] = x
        spans = {v: self.bar_span(v, inc[v]) for v in rot}
        byrow = defaultdict(list)
        for v in rot:
            byrow[Y[v]].append(v)
        for row, vs in byrow.items():
            iv = sorted((spans[v][0], spans[v][1], v) for v in vs)
            for i in range(1, len(iv)):
                if iv[i][0] <= iv[i - 1][1]:
                    return False
        for e, x in Xe.items():
            u, v = tuple(e)
            lo, hi = min(Y[u], Y[v]), max(Y[u], Y[v])
            for w in rot:
                if w in (u, v):
                    continue
                if lo < Y[w] < hi:
                    a, b = spans[w]
                    if a <= x <= b:
                        return False
        bycol = defaultdict(list)
        for e, x in Xe.items():
            u, v = tuple(e)
            bycol[x].append((min(Y[u], Y[v]), max(Y[u], Y[v])))
        for x, rs in bycol.items():
            rs.sort()
            for i in range(1, len(rs)):
                if rs[i][0] < rs[i - 1][1]:
                    return False
        return True

    # ── 5. 真实图处理：行合并 → 像素坐标 ──────────────────
    def real_dag_levels(self, g):
        order = sorted(self.core, key=lambda v: g[v])
        Y = {}
        for v in order:
            preds = [u for u in self.real_adj[v] if g[u] < g[v]]
            Y[v] = 0 if not preds else 1 + max(Y[u] for u in preds)
        return Y

    def bar_unit(self, Y, RXe):
        inc = defaultdict(list)
        for e, x in RXe.items():
            u, v = tuple(e)
            inc[u].append(x)
            inc[v].append(x)
        return {v: (min(xs) - 1, max(xs) + 1) for v, xs in inc.items()}

    def unit_ok(self, Y, RXe):
        spans = self.bar_unit(Y, RXe)
        byrow = defaultdict(list)
        for v in self.core:
            byrow[Y[v]].append(v)
        for row, vs in byrow.items():
            iv = sorted((spans[v][0], spans[v][1], v) for v in vs)
            for i in range(1, len(iv)):
                if iv[i][0] <= iv[i - 1][1]:
                    return False
        for e, x in RXe.items():
            u, v = tuple(e)
            lo, hi = min(Y[u], Y[v]), max(Y[u], Y[v])
            for w in self.core:
                if w in (u, v):
                    continue
                if lo < Y[w] < hi and spans[w][0] <= x <= spans[w][1]:
                    return False
        bycol = defaultdict(list)
        for e, x in RXe.items():
            u, v = tuple(e)
            bycol[x].append((min(Y[u], Y[v]), max(Y[u], Y[v])))
        for x, rs in bycol.items():
            rs.sort()
            for i in range(1, len(rs)):
                if rs[i][0] < rs[i - 1][1]:
                    return False
        return True

    def compact_rows(self, Y, RXe, g):
        def gless(u, v):
            return g[u] < g[v]
        for _ in range(4):
            moved = False
            for v in sorted(self.core, key=lambda x: -Y[x]):
                preds = [u for u in self.real_adj[v] if gless(u, v)]
                lo_bound = max([Y[u] for u in preds], default=-1) + 1
                succs = [w for w in self.real_adj[v] if gless(v, w)]
                hi_bound = min([Y[w] for w in succs], default=Y[v]) - 1
                old = Y[v]
                for b in range(lo_bound, min(hi_bound, old - 1) + 1):
                    Y2 = dict(Y)
                    Y2[v] = b
                    if self.unit_ok(Y2, RXe):
                        Y.clear()
                        Y.update(Y2)
                        moved = True
                        break
            if not moved:
                break
        return Y

    # ── 6. 像素装箱 ───────────────────────────────────────
    def col_extent(self, RXe, Y, c):
        rows = []
        for e, x in RXe.items():
            if x != c:
                continue
            u, v = tuple(e)
            rows += [Y[u], Y[v]]
        return (min(rows), max(rows)) if rows else (10 ** 9, -10 ** 9)

    def pack_columns(self, Y, RXe):
        c = self.cfg
        cols = sorted(set(RXe.values()))
        ext = {col: self.col_extent(RXe, Y, col) for col in cols}
        rowcards = defaultdict(list)
        for v in self.core:
            xs = [RXe[e] for e in RXe if v in e]
            rowcards[Y[v]].append((min(xs), max(xs), v))
        for r in rowcards:
            rowcards[r].sort()
        x = {cols[0]: c.left}
        for i in range(1, len(cols)):
            col = cols[i]
            pos = x[cols[i - 1]] + c.gap_col
            while True:
                x[col] = pos
                if self._col_fits(x, cols[:i + 1], ext, rowcards, col):
                    break
                pos += 2
                assert pos < c.left + 30000, "packing stuck"
            x[col] = pos
        return x

    def _col_fits(self, x, placed, ext, rowcards, col):
        c = self.cfg
        pset = set(placed)
        e_lo, e_hi = ext[col]
        for d in placed:
            if d != col and abs(x[d] - x[col]) < c.gap_near:
                d_lo, d_hi = ext[d]
                if not (e_hi + 1 < d_lo or d_hi + 1 < e_lo):
                    return False
        for r, lst in rowcards.items():
            ok = [t for t in lst if t[0] in pset and t[1] in pset]
            for i in range(1, len(ok)):
                u, v = ok[i - 1][2], ok[i][2]
                c0 = (x[ok[i - 1][0]] + x[ok[i - 1][1]]) / 2
                c1 = (x[ok[i][0]] + x[ok[i][1]]) / 2
                if c1 - c0 < (self.card_w[u] + self.card_w[v]) / 2 + c.card_gap:
                    return False
        return True

    def _build(self, Y, RXe, x):
        c = self.cfg
        inc = defaultdict(list)
        for e, cx in RXe.items():
            u, v = tuple(e)
            inc[u].append(cx)
            inc[v].append(cx)
        nodes, bars = {}, {}
        for v in self.core:
            xs = inc[v]
            b0, b1 = x[min(xs)], x[max(xs)]
            nodes[v] = {"x": ((b0 + b1) // 2 // 2) * 2, "y": c.top + Y[v] * c.pitch,
                        "w": self.card_w[v]}
            if b1 - b0 > 8:
                bars[v] = [b0 - 4, b1 + 4]
        edges = []
        for (a, b) in self.edges:
            col = RXe[(a, b)]
            ya, yb = nodes[a]["y"], nodes[b]["y"]
            down = yb > ya
            wB = self.card_w[b]
            in_card = abs(x[col] - nodes[b]["x"]) < wB / 2 - 8
            if in_card:
                ay = yb - (c.card_h // 2 + 5) if down else yb + (c.card_h // 2 + 5)
            else:
                ay = yb - 9 if down else yb + 9
            edges.append({"a": a, "b": b, "x": x[col], "y1": ya, "y2": yb,
                          "arrow": [x[col], ay, 1 if down else -1]})
        return nodes, bars, edges

    def stage3(self, g, Y, RXe):
        c = self.cfg
        x = self.pack_columns(Y, RXe)
        nodes, bars, edges = self._build(Y, RXe, x)
        nrow = len({Y[v] for v in self.core})
        H = c.top + (nrow - 1) * c.pitch + c.card_h // 2 + 18
        xmax = max(n["x"] + n["w"] / 2 for n in nodes.values())
        W = max(int(xmax + 20), int(H * c.aspect_min))
        for i, v in enumerate(self.deg0):
            w = self.card_w[v]
            nodes[v] = {"x": int((W - 24 - w / 2 - i * (w + 14)) // 2 * 2),
                        "y": c.park_y, "w": w}
        target = W - c.left - 24
        span = max(x.values()) - c.left
        if span > 0 and target > span:
            ratio = target / span
            x = {col: int((c.left + (px - c.left) * ratio) // 2 * 2) for col, px in x.items()}
            nodes, bars, edges = self._build(Y, RXe, x)
            for i, v in enumerate(self.deg0):
                w = self.card_w[v]
                nodes[v] = {"x": int((W - 24 - w / 2 - i * (w + 14)) // 2 * 2),
                            "y": c.park_y, "w": w}
        W = ((max(int(max(n["x"] + n["w"] / 2 for n in nodes.values()) + 16), W) + 7) // 8) * 8
        H = ((H + 7) // 8) * 8
        minL = min(n["x"] - n["w"] / 2 for n in nodes.values())
        if minL < 4:
            dx = int((4 - minL + 1) // 2 * 2)
            x = {col: px + dx for col, px in x.items()}
            nodes, bars, edges = self._build(Y, RXe, x)
            for i, v in enumerate(self.deg0):
                w = self.card_w[v]
                nodes[v] = {"x": int((W - 24 - w / 2 - i * (w + 14)) // 2 * 2),
                            "y": c.park_y, "w": w}
            W = ((max(int(max(n["x"] + n["w"] / 2 for n in nodes.values()) + 16), W) + 7) // 8) * 8
        return {"viewBox": [0, 0, W, H], "nodes": nodes, "edges": edges,
                "bars": bars, "meta": {
                    "rows": nrow,
                    "rowY": [c.top + r * c.pitch for r in range(nrow)],
                    "pitch": c.pitch, "deg0": self.deg0,
                    "cols": sorted(set(x.values())),
                    "cardH": c.card_h, "fs": [c.fs_title, c.fs_value]}}

    def finalize(self, rot, g, Y_aug, RXe):
        Yr = self.real_dag_levels(g)
        Y = Yr if self.unit_ok(Yr, RXe) else dict(Y_aug)
        Y = self.compact_rows(Y, RXe, g)
        rows = sorted({Y[v] for v in self.core})
        remap = {r: i for i, r in enumerate(rows)}
        Y = {v: remap[y] for v, y in Y.items()}
        nrow = len(rows)
        down = sum(1 for a, b in self.edges if Y[a] < Y[b])
        v4 = self.stage3(g, Y, RXe)
        W, H = v4["viewBox"][2], v4["viewBox"][3]
        s = min(self.cfg.target_w / W, self.cfg.target_h / H)
        return -s, Y, {"rows": nrow, "down": down, "W": W, "H": H,
                       "scale": round(s, 3)}

    def try_candidate(self, s, t):
        rot, dummy = self.augment(self.build_rotation())
        g = self.st_numbering(rot, s, t)
        res = self.visibility(rot, g, (s, t))
        if not res:
            return None
        Y_aug, Xe = res
        re_set = {frozenset(e) for e in self.edges}
        RXe = {e: x for e, x in Xe.items() if e in re_set}
        # 双向边对拆独立列：键改有向，反向边列值 +0.5 强制独立列
        pair_n = defaultdict(int)
        directed = {}
        for (a, b) in self.edges:
            fs = frozenset((a, b))
            n = pair_n[fs]
            pair_n[fs] += 1
            directed[(a, b)] = RXe[fs] + (0.5 * n)
        RXe = directed
        sc, Y, metrics = self.finalize(rot, g, Y_aug, RXe)
        return sc, s, t, rot, g, Y_aug, Xe, RXe, dummy, Y, metrics

    def run(self):
        """全候选搜索，返回最优布局 dict（确定性：同图同输出）。"""
        cands = []
        seen_st = set()
        for a, b in self.edges:
            for s, t in ((a, b), (b, a)):
                try:
                    r = self.try_candidate(s, t)
                except AssertionError:
                    continue
                if not r:
                    continue
                key = tuple(sorted(r[4].items()))
                if key in seen_st:
                    continue
                seen_st.add(key)
                cands.append(r)
        assert cands, "no viable candidate"
        cands.sort(key=lambda x: x[0])
        sc, s, t, rot, g, Y_aug, Xe, RXe, dummy, Y, data = cands[0]
        v4 = self.stage3(g, Y, RXe)
        v4["meta"]["st"] = [s, t]
        v4["meta"]["down"] = data["down"]
        v4["meta"]["n"] = len(self.nodes)
        v4["meta"]["m"] = len(self.edges)
        v4["meta"]["method"] = ("visibility-representation (Rosenstiehl-Tarjan) "
                                "0-crossing guaranteed; wires strictly vertical; "
                                "compact packing (occlusion allowed under cards)")
        return v4


def layout(graph: Graph, config: LayoutConfig = None) -> dict:
    return PlanarLayout(graph, config).run()


def layout_to_json(v4: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(v4, f, ensure_ascii=False, indent=1)
