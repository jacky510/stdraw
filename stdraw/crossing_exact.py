# -*- coding: utf-8 -*-
"""精确交叉数层（WS2）：OIL 路由 ILP + 平面化 oracle 裁决 + B&B 夹逼。

数学框架（完整证明见 docs/crossing-exact.md）：

1. 安全缩减（每条都有 cr 保持证明）：
   - 自环删除（自环局部画出，0 交叉）；连通分量分解（cr 可加）；
   - 度 ≤1 顶点迭代删除（叶子放进邻居关联面 0 交叉重连）；
   - 桥分解（cr 对 2-边-连通块可加）。

2. 上界（UB）：贪心极大可平面子图 U + 对 (U, Π) 求同时最优插入。
   插入解经 oracle 验证后是真实画法 → UB 恒真。

3. 分解定理（docs §2）：cr(G) = min over 可平面子图 U、U 的全部平面嵌入 Π、
   E\\U 同时插入 Π 的最少交叉数。
   B&B 枚举（docs §3）：候选 F=E\\U 满足 |F| ≤ 2·UB−2 必覆盖最优；
   每候选：G−F 可平面 + 2-连通 + 全嵌入（旋转系枚举 + 欧拉面数判据）+
   「存在 cost ≤ UB−1 的**可实现**解」判定。覆盖完备 → cr=UB 是证明。

4. 插入子问题（对固定 (U, Π)）：**CP-SAT 提议 + oracle 裁决**。
   - ILP（超集建模，宽松无妨）：每条 F 边 = 三角化嵌入对偶图上的
     source→sink 单位流路径（每侧 ≤1 次，good drawing 口径；相邻边禁交叉）；
     c_{e,f} = F-F 互交叉指示（≤1；须共享三角形）。
   - 裁决：由 (路径, c) 构造**平面化图 H**（U + 弧路径 + 交叉点合一顶点），
     H 平面 ⇔ 该解可实现（docs §4 双向证明）。H 平面 → 解真实、代价即交叉数；
     不平面 → no-good 子句精确剔除该解，重解。
   - 正确性不依赖任何手工拓扑约束集：ILP 是可实现集的超集，oracle 是真值；
     循环终止于「最优可实现解」或「该代价下无可实现解」。两者皆精确。
   - 确定性：num_workers=1 + 固定 seed + no-good 循环计数上界（超限如实降级）。

5. 下界（LB，全局有效恒 ≤ cr）：Kuratowski 反例贪心抽取（边不相交）+
   z-ILP（每个 Kuratowski 子图至少一条边被标）；cr ≥ ⌈被标边数/2⌉。
   LB == UB 时无论覆盖是否完备都可证最优。

6. 无 ortools / 核规模 >30 / 枚举超 cap → 构造降级，proven_optimal=false，
   gap 如实标注。
"""
import itertools
import math
from collections import defaultdict


# ────────────────────────── 图的简单无向视图 ──────────────────────────


def undirected_edges(graph):
    """(a,b) 无向边列表：去自环、保留平行边（good drawing 下平行边不互交）。"""
    edges, selfloops = [], []
    for e in graph.edges:
        if e.a == e.b:
            selfloops.append((e.a, e.b))
            continue
        edges.append((e.a, e.b))
    return edges, selfloops


def _adjacent(e1, e2):
    return bool({e1[0], e1[1]} & {e2[0], e2[1]})


# ────────────────────────── 安全缩减（cr 保持） ──────────────────────────


def _iter_degree_prune(nodes, edges):
    nodes, edges = list(nodes), list(edges)
    changed = True
    while changed:
        changed = False
        deg = defaultdict(int)
        for a, b in edges:
            deg[a] += 1
            deg[b] += 1
        drop = {v for v in nodes if deg[v] <= 1}
        if drop:
            nodes = [v for v in nodes if v not in drop]
            edges = [(a, b) for a, b in edges if a not in drop and b not in drop]
            changed = True
    return nodes, edges


def _components(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
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


def _bridges_split(nodes, edges):
    """Tarjan 桥 → 2-边-连通块列表 [(nodes, edges)]（单边桥块 cr=0 已弃）。"""
    adj = defaultdict(list)
    for i, (a, b) in enumerate(edges):
        adj[a].append((b, i))
        adj[b].append((a, i))
    disc, low, is_bridge = {}, {}, [False] * len(edges)
    parent, depth = {}, {}
    timer = [0]
    for root in nodes:
        if root in disc:
            continue
        disc[root] = low[root] = timer[0]
        timer[0] += 1
        depth[root] = 0
        stack = [(root, -1, iter(adj[root]))]
        while stack:
            v, pe, it = stack[-1]
            advanced = False
            for w, ei in it:
                if ei == pe:
                    continue
                if w not in disc:
                    parent[w] = (v, ei)
                    disc[w] = low[w] = timer[0]
                    timer[0] += 1
                    depth[w] = depth[v] + 1
                    stack.append((w, ei, iter(adj[w])))
                    advanced = True
                    break
                elif ei != parent.get(v, (None, -1))[1]:
                    low[v] = min(low[v], disc[w])
            if not advanced:
                stack.pop()
                if stack:
                    pv = stack[-1][0]
                    low[pv] = min(low[pv], low[v])
                    if low[v] > disc[pv]:
                        is_bridge[parent[v][1]] = True
    nbedges = [i for i in range(len(edges)) if not is_bridge[i]]
    adj2 = defaultdict(list)
    for i in nbedges:
        a, b = edges[i]
        adj2[a].append(i)
        adj2[b].append(i)
    seen_e, blocks = set(), []
    for i in nbedges:
        if i in seen_e:
            continue
        bl_edges, bl_nodes, stack = [], set(), [i]
        seen_e.add(i)
        while stack:
            ei = stack.pop()
            x, y = edges[ei]
            bl_edges.append(edges[ei])
            bl_nodes.update((x, y))
            for nxt in adj2[x] + adj2[y]:
                if nxt not in seen_e:
                    seen_e.add(nxt)
                    stack.append(nxt)
        blocks.append((sorted(bl_nodes), bl_edges))
    return blocks


def safe_reduce(graph):
    """安全缩减主入口 → (cores, info)。cr(图) = Σ cr(cores[i])。"""
    edges, selfloops = undirected_edges(graph)
    nodes = graph.node_ids()
    cores = []
    for comp in _components(nodes, edges):
        cset = set(comp)
        ce = [(a, b) for a, b in edges if a in cset and b in cset]
        n2, e2 = _iter_degree_prune(comp, ce)
        if not e2:
            continue
        for bn, be in _bridges_split(n2, e2):
            if be:
                cores.append((bn, be))
    return cores, {"selfloops_removed": len(selfloops), "cores": len(cores)}


# ────────────────────────── 嵌入工具 ──────────────────────────


def _faces_from_rotation(rotation, nodes, edges):
    """旋转系 → 面列表 + 可平面判据（面数 == m − n + 2，连通图欧拉判据）。

    dart (u→v) 的后继 = (v→x)，x = rotation[v] 中 u 的循环后继。"""
    nxt = {}
    for v in nodes:
        rot = list(rotation[v])
        for i, w in enumerate(rot):
            nxt[(w, v)] = rot[(i + 1) % len(rot)]
    seen, faces = set(), []
    for v0 in nodes:
        for w0 in rotation[v0]:
            if (v0, w0) in seen:
                continue
            face, v, w = [], v0, w0
            while (v, w) not in seen:
                seen.add((v, w))
                face.append(v)
                w2 = nxt[(v, w)]
                v, w = w, w2
            faces.append(face)
    n, m = len(nodes), len(edges)
    return faces, len(faces) == m - n + 2


def _enum_rotations(nodes, edges, cap=20000):
    """枚举连通图全部平面嵌入（旋转系）。

    每顶点固定首元素（折叠旋转等价）；首顶点再要求第二元素 < 末元素
    （折叠全局镜像——镜像插入代价相同）；叶上欧拉面数判据验证可平面。
    返回 (embeddings, capped)。"""
    deg, neigh = defaultdict(int), defaultdict(set)
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
        neigh[a].add(b)
        neigh[b].add(a)
    vs = sorted(nodes, key=lambda v: (-deg[v], v))
    orders = {}
    for v in vs:
        ns = sorted(neigh[v])
        cand = [[ns[0]] + list(p) for p in itertools.permutations(ns[1:])]
        if v == vs[0] and len(ns) >= 3:
            cand = [r for r in cand if r[1] < r[-1]]
        orders[v] = cand
    embeddings, seen = [], set()
    count, capped = [0], [False]

    def dfs(i, cur):
        if capped[0]:
            return
        if i == len(vs):
            count[0] += 1
            if count[0] > cap:
                capped[0] = True
                return
            faces, ok = _faces_from_rotation(cur, nodes, edges)
            if not ok:
                return
            key = tuple((v, tuple(cur[v])) for v in vs)
            if key not in seen:
                seen.add(key)
                embeddings.append({v: list(cur[v]) for v in nodes})
            return
        v = vs[i]
        for rot in orders[v]:
            cur[v] = rot
            dfs(i + 1, cur)
        cur[v] = None

    dfs(0, {v: None for v in nodes})
    return embeddings, capped[0]


# ────────────────────────── 三角化结构 ──────────────────────────


def _split_face(face):
    """含重复顶点的面游走 → 简单圈列表（割点口袋分解）。

    桥/割点使同一几何面经割点多次：游走 w 在重复顶点 v 处切开，
    内圈 w[i:j] 与外圈 w[:i]+w[j:] 均为合法闭游走（相邻对都是原游走
    的 dart），递归至无重复顶点。返回的每个圈首顶点不再重复出现。"""
    walks, out = [face], []
    while walks:
        w = walks.pop()
        first = {}
        cut = None
        for i, v in enumerate(w):
            if v in first:
                cut = (first[v], i)
                break
            first[v] = i
        if cut is None:
            out.append(w)
            continue
        i, j = cut
        walks.append(w[i:j])            # 内圈（v…返回 v 前，v 仅在首位）
        if i > 0 or j < len(w):
            walks.append(w[:i] + w[j:])  # 外圈（去掉内圈段，闭合同游走）
    return out


class Triangulation:
    """可平面嵌入的三角化：三角形列表 + 侧（真边侧 / 虚弦侧）。

    sides[i] = {kind: 'edge'|'chord', nodes: (x, y), payload, t1, t2}
      'edge':  真边侧——穿行计 1 交叉；payload = 该边在全图边表的下标
      'chord': 面内虚弦——穿行免费；payload = (face_id, p, q)
    tri_sides[t] = 三角形 t 的 3 个侧 id；node_tris[v] = 含顶点 v 的三角形。
    含重复顶点的面（桥/割点口袋）先经 _split_face 拆成简单圈。
    """

    def __init__(self, faces, global_index):
        self.triangles = []
        self.sides = []
        self.node_tris = defaultdict(list)
        self.tri_sides = defaultdict(list)
        edge_side, chord_sides = {}, {}
        simple_faces = []
        for face in faces:
            simple_faces.extend(_split_face(face))

        def real_side(x, y):
            key = tuple(sorted((x, y)))
            if key not in edge_side:
                edge_side[key] = len(self.sides)
                self.sides.append({"kind": "edge", "nodes": (x, y),
                                   "payload": global_index[key],
                                   "t1": None, "t2": None})
            return edge_side[key]

        def chord_side(fi, p, q):
            key = (fi,) + tuple(sorted((p, q)))
            if key not in chord_sides:
                chord_sides[key] = len(self.sides)
                self.sides.append({"kind": "chord", "nodes": (p, q),
                                   "payload": key[1:], "t1": None, "t2": None})
            return chord_sides[key]

        for fi, face in enumerate(simple_faces):
            if len(face) < 3:
                continue                     # 二角面（平行边残片）：无三角形
            k = len(face)
            v0 = face[0]
            tris_f = []
            for j in range(1, k - 1):
                t = len(self.triangles)
                self.triangles.append((v0, face[j], face[j + 1]))
                for v in self.triangles[-1]:
                    self.node_tris[v].append(t)
                tris_f.append(t)
            for j in range(len(tris_f)):
                jf = j + 1
                t = tris_f[j]
                if jf == 1:
                    self.tri_sides[t].append(real_side(v0, face[1]))
                else:
                    self.tri_sides[t].append(chord_side(fi, v0, face[jf]))
                self.tri_sides[t].append(real_side(face[jf], face[jf + 1]))
                if jf + 1 == k - 1:
                    self.tri_sides[t].append(real_side(v0, face[k - 1]))
                else:
                    self.tri_sides[t].append(chord_side(fi, v0, face[jf + 1]))
        use = defaultdict(list)
        for t, sids in self.tri_sides.items():
            for sid in sids:
                use[sid].append(t)
        for sid, ts in use.items():
            ts = sorted(set(ts))
            if len(ts) != 2:
                raise AssertionError(f"侧 {sid} 相邻三角形数 {len(ts)} != 2")
            self.sides[sid]["t1"], self.sides[sid]["t2"] = ts


# ────────────────────────── OIL 路由 ILP + oracle 裁决 ──────────────────────────


def _build_model(tri, nodes, edges, F, cp_model):
    """超集 ILP：路由流 + 互交叉指示（宽松——正确性由 oracle 保证）。"""
    m = cp_model.CpModel()
    nT = len(tri.triangles)
    nS = len(tri.sides)
    side_real = [tri.sides[s]["kind"] == "edge" for s in range(nS)]
    side_edge = [tri.sides[s]["payload"] if tri.sides[s]["kind"] == "edge"
                 else None for s in range(nS)]
    side_tris = [(tri.sides[s]["t1"], tri.sides[s]["t2"]) for s in range(nS)]
    all_tris = list(range(nT))

    u, sel_src, sel_end, fdir = {}, {}, {}, {}
    for k, (a, b) in enumerate(F):
        src_tris = tri.node_tris.get(a, all_tris)
        end_tris = tri.node_tris.get(b, all_tris)
        for t in all_tris:
            sel_src[(k, t)] = m.NewBoolVar(f"src_{k}_{t}")
            sel_end[(k, t)] = m.NewBoolVar(f"end_{k}_{t}")
        m.Add(sum(sel_src[(k, t)] for t in src_tris) == 1)
        m.Add(sum(sel_src[(k, t)] for t in all_tris if t not in src_tris) == 0)
        m.Add(sum(sel_end[(k, t)] for t in end_tris) == 1)
        m.Add(sum(sel_end[(k, t)] for t in all_tris if t not in end_tris) == 0)
        fk = {}
        for sid in range(nS):
            g = side_edge[sid]
            uv = m.NewBoolVar(f"u_{k}_{sid}")
            if g is not None and _adjacent(F[k], edges[g]):
                m.Add(uv == 0)          # 相邻边禁交叉（good drawing 可扰动消除）
            u[(k, sid)] = uv
            t1, t2 = side_tris[sid]
            f0 = m.NewBoolVar(f"f_{k}_{sid}_a")
            f1 = m.NewBoolVar(f"f_{k}_{sid}_b")
            m.Add(f0 + f1 == uv)
            fk[(sid, 0)] = f0
            fk[(sid, 1)] = f1
        fdir[k] = fk
        for t in all_tris:
            outflow = sum(fk[(sid, 0)] for sid in tri.tri_sides[t]
                          if side_tris[sid][0] == t) + \
                      sum(fk[(sid, 1)] for sid in tri.tri_sides[t]
                          if side_tris[sid][1] == t)
            inflow = sum(fk[(sid, 1)] for sid in tri.tri_sides[t]
                         if side_tris[sid][0] == t) + \
                     sum(fk[(sid, 0)] for sid in tri.tri_sides[t]
                         if side_tris[sid][1] == t)
            m.Add(outflow - inflow == sel_src[(k, t)] - sel_end[(k, t)])

    onroute, zvars, cvar = {}, {}, {}
    for k in range(len(F)):
        for t in all_tris:
            terms = [sel_src[(k, t)], sel_end[(k, t)]] + \
                    [u[(k, sid)] for sid in tri.tri_sides[t]]
            o = m.NewBoolVar(f"on_{k}_{t}")
            m.Add(o <= sum(terms))
            for term in terms:
                m.AddImplication(term, o)
            onroute[(k, t)] = o
    for k1 in range(len(F)):
        for k2 in range(k1 + 1, len(F)):
            if _adjacent(F[k1], F[k2]):
                continue
            c = m.NewBoolVar(f"c_{k1}_{k2}")
            zl = []
            for t in all_tris:
                z = m.NewBoolVar(f"z_{k1}_{k2}_{t}")
                m.Add(z <= onroute[(k1, t)])
                m.Add(z <= onroute[(k2, t)])
                zl.append(z)
            m.Add(c <= sum(zl))
            cvar[(k1, k2)] = c
            zvars[(k1, k2)] = zl

    scope = list(u.values()) + list(sel_src.values()) + \
        list(sel_end.values()) + list(cvar.values())
    return {"model": m, "u": u, "sel_src": sel_src, "sel_end": sel_end,
            "fdir": fdir, "cvar": cvar, "zvars": zvars, "scope": scope,
            "side_real": side_real, "side_edge": side_edge,
            "side_tris": side_tris, "all_tris": all_tris}


def _extract_solution(tri, edges, F, F_idx, parts, solver):
    """从解值提取 (事件序列, mutual)。事件序列[k] 按弧上次序：
    ('x', 边 idx) = 穿该真边；('m', pair_key) = 与配对弧互交叉。"""
    u, sel_src, sel_end = parts["u"], parts["sel_src"], parts["sel_end"]
    fdir, cvar, zvars = parts["fdir"], parts["cvar"], parts["zvars"]
    side_real, side_edge, side_tris = (parts["side_real"], parts["side_edge"],
                                       parts["side_tris"])
    all_tris = parts["all_tris"]
    nT = len(tri.triangles)
    mutual_tri = {}
    for (k1, k2), c in cvar.items():
        if solver.Value(c):
            for i, z in enumerate(zvars[(k1, k2)]):
                if solver.Value(z):
                    mutual_tri[(k1, k2)] = i
                    break
    events = {}
    for k, (a, b) in enumerate(F):
        cur = next(t for t in all_tris if solver.Value(sel_src[(k, t)]))
        end_t = next(t for t in all_tris if solver.Value(sel_end[(k, t)]))
        seq = []
        guard = 0
        while True:
            seq += [("m", pk) for pk, tt in sorted(mutual_tri.items())
                    if k in pk and tt == cur]
            if cur == end_t:
                break
            guard += 1
            moved = False
            for sid in tri.tri_sides[cur]:
                t1, t2 = side_tris[sid]
                if cur not in (t1, t2):
                    continue
                d = 0 if t1 == cur else 1
                if solver.Value(fdir[k][(sid, d)]):
                    if side_real[sid]:
                        seq.append(("x", side_edge[sid]))
                    cur = side_tris[sid][1 - d]
                    moved = True
                    break
            if not moved or guard > nT + 2:
                seq.append(("stuck", None))
                break
        events[k] = seq
    mutual = [[F_idx[k1], F_idx[k2]]
              for (k1, k2), c in cvar.items() if solver.Value(c)]
    return events, mutual


def _planarized_graph(nodes, edges, U_idx, F, F_idx, events, mutual):
    """(路径, 互交叉) → 平面化抽象图 H。H 平面 ⇔ 解可实现（docs §4）。

    返回 None 表示路线断裂（直接判不可实现）。"""
    import networkx as nx
    H = nx.Graph()
    H.add_nodes_from(nodes)
    for i in U_idx:
        H.add_edge(*edges[i])
    split = {}          # 边 idx → 当前细分后 (ga, gb)，同边可被多条弧穿
    xc = 0
    arc_vertex = {}
    for k, (a, b) in enumerate(F):
        seq = events.get(k, [])
        prev = a
        for item in seq:
            if item[0] == "x":
                g = item[1]
                x = f"X{xc}"
                xc += 1
                ga, gb = split.get(g, edges[g])
                H.remove_edge(ga, gb)
                H.add_edge(ga, x)
                H.add_edge(x, gb)
                split[g] = (ga, x)      # 交叉点在弧路径序下依次排列
                H.add_edge(prev, x)
                prev = x
            elif item[0] == "m":
                pk = item[1]
                if pk not in arc_vertex:
                    x = f"X{xc}"
                    xc += 1
                    arc_vertex[pk] = x
                    H.add_node(x)
                x = arc_vertex[pk]
                H.add_edge(prev, x)
                prev = x
            else:
                return None
        H.add_edge(prev, b)
    return H


def oil_insertion(nodes, edges, U_idx, F_idx, rotation,
                  ub=None, minimize=True, lex=True, max_nogood=400):
    """固定 (U, Π) 的同时最优插入（CP-SAT 提议 + 平面化 oracle 裁决）。

    minimize=True：返回最优可实现解（ok/cost/routes/events/mutual）；
    minimize=False：判定「存在 cost ≤ ub 的可实现解」（ok/feasible）。
    why='nogood-cap' 表示裁决循环超限未决——调用方应如实降级覆盖标记。
    """
    U_key = {}
    for i in U_idx:
        x, y = edges[i]
        U_key[tuple(sorted((x, y)))] = i
    U_edges = [edges[i] for i in U_idx]
    F = [edges[i] for i in F_idx]
    if not F:
        return {"ok": True, "cost": 0, "routes": {}, "events": {}, "mutual": []}
    faces, ok = _faces_from_rotation(rotation, nodes, U_edges)
    if not ok:
        return {"ok": False, "why": "rotation-not-planar"}
    try:
        tri = Triangulation(faces, U_key)
    except AssertionError as exc:
        # 嵌入结构异常（面游走非简单圈等）——如实降级，不崩
        return {"ok": False, "why": f"triangulation-failed: {exc}"}

    try:
        from ortools.sat.python import cp_model
    except Exception:
        return {"ok": False, "why": "no-ortools"}
    import networkx as nx

    parts = _build_model(tri, nodes, edges, F, cp_model)
    m = parts["model"]
    cost_real = [parts["u"][(k, sid)] for k in range(len(F))
                 for sid in range(len(tri.sides)) if parts["side_real"][sid]]
    total = sum(cost_real) + sum(parts["cvar"].values())
    if minimize:
        if lex:
            wu = sum((i + 1) * v for i, v in enumerate(cost_real))
            m.Minimize(10 ** 7 * total + 10 ** 5 * sum(parts["cvar"].values()) + wu)
        else:
            m.Minimize(total)
    else:
        m.Add(total <= ub)

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1          # 确定性铁律
    solver.parameters.random_seed = 42
    for _round in range(max_nogood + 1):
        st = solver.Solve(m)
        if st == cp_model.INFEASIBLE:
            if not minimize:
                return {"ok": False, "why": "infeasible"}
            if _round == 0:
                return {"ok": False, "why": "infeasible"}
            return {"ok": False, "why": "exhausted"}
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {"ok": False, "why": "unknown"}
        events, mutual = _extract_solution(tri, edges, F, F_idx, parts, solver)
        H = _planarized_graph(nodes, edges, U_idx, F, F_idx, events, mutual)
        if H is not None and nx.is_planar(H):
            if not minimize:
                return {"ok": True, "feasible": True}
            routes = {}
            for k, (a, b) in enumerate(F):
                routes[F_idx[k]] = {
                    "a": a, "b": b,
                    "crossings": [it[1] for it in events[k] if it[0] == "x"],
                }
            cost_x = sum(len(r["crossings"]) for r in routes.values()) + len(mutual)
            return {"ok": True, "cost": cost_x, "routes": routes,
                    "events": {F_idx[k]: events[k] for k in events},
                    "mutual": mutual}
        # 不可实现 → no-good 精确剔除当前 (路由, 互交叉) 指派
        lits = [v.Not() if solver.Value(v) else v for v in parts["scope"]]
        m.AddBoolOr(lits)
    return {"ok": False, "why": "nogood-cap"}


# ────────────────────────── 启发式 / 下界 ──────────────────────────


def _heuristic_planarization(nodes, edges):
    import networkx as nx
    order = sorted(range(len(edges)),
                   key=lambda i: (min(edges[i]), max(edges[i]), i))
    U = []
    for i in order:
        g = nx.Graph()
        g.add_nodes_from(nodes)
        for j in U + [i]:
            g.add_edge(*edges[j])
        if nx.is_planar(g):
            U = U + [i]
    F = [i for i in range(len(edges)) if i not in set(U)]
    return U, F


def _embed_U(nodes, edges, U_idx):
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for i in U_idx:
        g.add_edge(*edges[i])
    planar, emb = nx.check_planarity(g)
    if not planar:
        return None
    return {v: list(emb.neighbors_cw_order(v)) for v in g.nodes}


def _kuratowski_lb(nodes, edges):
    """全局下界（恒 ≤ cr）：Kuratowski 反例贪心抽取（边不相交）+ z-ILP。

    cr ≥ ⌈min 被标边数 / 2⌉：任何画法中每个 Kuratowski 子图内部必有交叉；
    min 被标边数 ≤ 被交叉边数 ≤ 2·交叉数。"""
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for a, b in edges:
        g.add_edge(a, b)
    ks = []
    while g.number_of_edges() > 0:
        planar, cert = nx.check_planarity(g, counterexample=True)
        if planar:
            break
        kedges = sorted({tuple(sorted((x, y))) for x, y in cert.edges()})
        if not kedges:
            break
        ks.append(kedges)
        g.remove_edges_from(kedges)
    if not ks:
        return 0, []
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return 0, ks
    m = cp_model.CpModel()
    z = {}
    for a, b in edges:
        z[tuple(sorted((a, b)))] = m.NewBoolVar(f"z_{a}_{b}")
    for kedges in ks:
        m.Add(sum(z[e] for e in kedges) >= 1)
    m.Minimize(sum(z.values()))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 42
    if solver.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        zmin = int(round(solver.ObjectiveValue()))
        return (zmin + 1) // 2, ks
    return 0, ks


# ────────────────────────── 主入口 ──────────────────────────


def crossing_exact(graph, max_nodes_exact=30, subset_cap=4000,
                   rotation_cap=200000, max_nogood=400):
    """CLD Graph → 交叉数证书块。

    crossing_number=UB（oracle 验证的真实画法计数，恒真）；
    proven_optimal 相对 docs/crossing-exact.md 模型类；
    lb/gap 如实；coverage: full/partial/planar/trivial。"""
    cores, red = safe_reduce(graph)
    total_ub, total_lb = 0, 0
    proven, coverage = True, "full"
    witnesses, methods = [], []
    for cnodes, cedges in cores:
        try:
            if len(cnodes) > max_nodes_exact or not _has_solver():
                r = _core_heuristic(cnodes, cedges)
            else:
                r = _core_exact(cnodes, cedges, subset_cap, rotation_cap,
                                max_nogood)
        except Exception as exc:      # noqa: BLE001 —— 未预期路径兜底，如实降级
            r = {"ub": len(cedges), "lb": 0, "proven": False,
                 "coverage": "partial",
                 "method": (f"core failed ({type(exc).__name__}: {exc}) — "
                            "heuristic upper-bound fallback"),
                 "witness": None}
        total_ub += r["ub"]
        total_lb += r["lb"]
        proven = proven and r["proven"]
        if r["coverage"] == "partial":
            coverage = "partial"
        if r.get("witness"):
            witnesses.append(r["witness"])
        methods.append(r["method"])
    if not cores:
        coverage = "trivial"
        methods = ["trivial (0 crossings by reduction)"]
    return {
        "crossing_number": total_ub,
        "proven_optimal": proven,
        "lb": total_lb,
        "gap": total_ub - total_lb,
        "coverage": coverage,
        "method": "; ".join(dict.fromkeys(methods)),
        "witness": witnesses,
        "reduced": red,
    }


def _has_solver():
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        return True
    except Exception:
        return False


def _core_heuristic(nodes, edges):
    U, F = _heuristic_planarization(nodes, edges)
    ub, witness = None, None
    if _has_solver():
        rot = _embed_U(nodes, edges, U)
        if rot is not None:
            r = oil_insertion(nodes, edges, U, F, rot, minimize=True, lex=True)
            if r.get("ok") and r.get("cost") is not None:
                ub = r["cost"]
                witness = {"F": F, "routes": r["routes"], "mutual": r["mutual"]}
    if ub is None:
        ub = len(F)
    lb, _ = _kuratowski_lb(nodes, edges)
    return {"ub": ub, "lb": lb, "proven": False, "coverage": "partial",
            "method": "heuristic planarization (optimality not proven)",
            "witness": witness}


def _core_exact(nodes, edges, subset_cap, rotation_cap, max_nogood):
    """单核精确层：UB 启发式 → B&B 全枚举夹逼。"""
    import networkx as nx

    m = len(edges)

    def planar_subset(idxs):
        g = nx.Graph()
        g.add_nodes_from(nodes)
        for i in idxs:
            g.add_edge(*edges[i])
        return nx.is_planar(g)

    if planar_subset(range(m)):
        return {"ub": 0, "lb": 0, "proven": True, "coverage": "planar",
                "method": "planar (planarity witness)", "witness": None}

    U, F = _heuristic_planarization(nodes, edges)
    best_ub, witness = None, None
    rot = _embed_U(nodes, edges, U)
    if rot is not None:
        r = oil_insertion(nodes, edges, U, F, rot, minimize=True, lex=True,
                          max_nogood=max_nogood)
        if r.get("ok") and r.get("cost") is not None:
            best_ub = r["cost"]
            witness = {"F": F, "routes": r["routes"], "mutual": r["mutual"]}
    if best_ub is None:
        best_ub = len(F)
    lb, _ks = _kuratowski_lb(nodes, edges)
    if lb >= best_ub:
        return {"ub": best_ub, "lb": lb, "proven": True, "coverage": "full",
                "method": ("exact (Kuratowski-z lower bound meets "
                           "planarization upper bound)"),
                "witness": witness}

    coverage_full = True
    checked = 0
    kmax = min(m, 2 * best_ub - 2)
    for k in range(1, kmax + 1):
        if k > 2 * best_ub - 2:
            break              # UB 改善后枚举上界动态收缩（仍覆盖最优，docs §3）
        if (k + 1) // 2 >= best_ub:
            continue
        for Fc in itertools.combinations(range(m), k):
            checked += 1
            if checked > subset_cap:
                coverage_full = False
                break
            fset = set(Fc)
            Uc = [i for i in range(m) if i not in fset]
            if not planar_subset(Uc):
                continue
            if not _two_connected(nodes, Uc, edges):
                continue
            embs, capped = _enum_rotations(
                nodes, [edges[i] for i in Uc], cap=rotation_cap)
            if capped:
                coverage_full = False
            for rot2 in embs:
                r = oil_insertion(nodes, edges, Uc, Fc, rot2,
                                  ub=best_ub - 1, minimize=False,
                                  max_nogood=max_nogood)
                if r.get("why") == "nogood-cap":
                    coverage_full = False
                    continue
                if not r.get("ok"):
                    # why != infeasible/nogood-cap：该嵌入未完整裁决（三角化
                    # 失败/求解器 unknown 等）——覆盖不完备，如实标 partial
                    if r.get("why") != "infeasible":
                        coverage_full = False
                    continue
                if r.get("feasible"):
                    r2 = oil_insertion(nodes, edges, Uc, Fc, rot2,
                                       minimize=True, lex=True,
                                       max_nogood=max_nogood)
                    if r2.get("ok") and r2.get("cost") is not None and \
                            r2["cost"] < best_ub:
                        best_ub = r2["cost"]
                        witness = {"F": list(Fc), "routes": r2["routes"],
                                   "mutual": r2["mutual"]}
        if not coverage_full:
            break
    if coverage_full:
        proven = True
    else:
        proven = lb >= best_ub
    return {"ub": best_ub, "lb": lb, "proven": proven,
            "coverage": "full" if coverage_full else "partial",
            "method": ("exact OIL (routing ILP + planarization oracle, "
                       "exhaustive B&B over planar subgraphs x embeddings)"
                       if coverage_full else
                       "OIL B&B, enumeration capped — honest gap"),
            "witness": witness}


def _two_connected(nodes, U_idx, edges):
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for i in U_idx:
        g.add_edge(*edges[i])
    return nx.is_biconnected(g)
