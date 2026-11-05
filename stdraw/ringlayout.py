# -*- coding: utf-8 -*-
"""回路主导环形排布（2026-11-05 产品定调，ref-scrubbed）。

> 「有平衡环形成，环形会让人们把这个循环理解得更好，图形也更优美」

触发判定（图论度量，非感觉；全确定性）：
  1. 小图：3 ≤ n ≤ 12（n 含孤立节点）；
  2. 主环：存在覆盖 ≥ n-2 节点的简单回路；或 环边（非桥边）占无向边比例 ≥ 0.9；
  3. 纯环（单连通分量全度 2）：直接取该环（复用 WS2 cycle 正多边形槽位构造，
     构造本身不变）。

主环选择：候选 = 声明环（DSL loop，构成简单回路者，保留声明环序——R/B 极性
徽标沿环可读）∪ 图论枚举简单回路（规范形去重）。在覆盖 ≥ n-2 的候选里按
「弦交叉 0 优先 → 覆盖最多 → 规范形字典序」确定性选优。

排布（place_ring）：
  - 主环节点按环序放正多边形槽位（placement._place_cycle 同源构造：角度均分
    i·2π/k − π/2、2px 网格量化；半径按相邻卡宽需求自适应，上界受 check8
    1280×800 档渲染比例约束）；
  - 残节点（弦尾巴/外部变量）：邻居角质心方向、环内固定分数候选序，卡距
    冲突退环外近邻侧；孤立节点停顶部停车带；
  - 半径需求超上界 → InfeasibleRing（调用方回退既有分层路径，逐字节不变）。

布线/证书：交给既有 Router 与 certificate_auto；环形模式指标口径（环上等间距
CV + 正多边形模板拟合误差，替代行对齐/列吸附）在 metrics/check 内按
meta.placement == "ring-cycle" 切换。
"""
import math
from collections import defaultdict

MAX_RING_N = 12            # 触发上限：小图
COVER_SLACK = 2            # 主环覆盖 ≥ n - 2
CYCLE_EDGE_RATIO = 0.90    # 环边（非桥）占比阈值（OR 分支）
DFS_STEP_CAP = 2_000_000   # 简单回路枚举步数上限（确定性：操作计数口径）
RADIUS_MIN = 150
RADIUS_MAX = 320           # check8 渲染比例 ≥0.85 的半径上界（2r+card+边几何 ≤ ~780px）
ADJ_GAP = 60               # 相邻环卡中心距余量（≥16 门 + 布线通道）


class InfeasibleRing(Exception):
    """环形槽位不可行（半径需求超上界）——调用方回退既有分层路径。"""


def _adjacency(edges):
    adj = defaultdict(set)
    pairs = set()
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
        pairs.add((a, b) if a < b else (b, a))
    return adj, pairs


def _canonical(seq):
    """环序列规范形：所有旋转 × 两方向中字典序最小（去重/定序用）。"""
    best = None
    for s in (list(seq), list(seq)[::-1]):
        for i in range(len(s)):
            rot = s[i:] + s[:i]
            if best is None or rot < best:
                best = rot
    return tuple(best)


def _seg_cross(p1, p2, p3, p4):
    """两线段是否真交叉（端点相触/共线重叠不算；直线代理口径）。"""

    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(v) < 1e-9:
            return 0
        return 1 if v > 0 else -1

    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def _crossing_count(segments):
    """线段两两真交叉计数（segments: (p1, p2, endpoint_ids)；共享端点跳过）。"""
    n = len(segments)
    c = 0
    for i in range(n):
        for j in range(i + 1, n):
            a1, b1, e1 = segments[i]
            a2, b2, e2 = segments[j]
            if e1[0] in e2 or e1[1] in e2:
                continue
            if _seg_cross(a1, b1, a2, b2):
                c += 1
    return c


class _CapExceeded(Exception):
    pass


def _enumerate_cycles(nodes, adj):
    """枚举全部简单回路（规范形去重；步数上限保护，超限即停、用已有结果）。"""
    steps = [0]
    found = {}

    def dfs(start, v, path, seen):
        steps[0] += 1
        if steps[0] > DFS_STEP_CAP:
            raise _CapExceeded
        for w in sorted(adj[v]):
            if w == start and len(path) >= 3:
                can = _canonical(path)
                if can not in found:
                    found[can] = can
            elif w not in seen:
                seen.add(w)
                dfs(start, w, path + [w], seen)
                seen.remove(w)

    try:
        for s in sorted(nodes):
            dfs(s, s, [s], {s})
    except _CapExceeded:
        pass
    return [list(c) for c in found.values()]


def _declared_loop_cycles(graph, adj):
    """声明环中构成简单回路者。返回 [(loop_id, kind, 声明环序)]。"""
    out = []
    for lp in graph.loops:
        seq = list(lp.nodes)
        if len(seq) < 3 or len(set(seq)) != len(seq):
            continue
        if not all(seq[(i + 1) % len(seq)] in adj[seq[i]] for i in range(len(seq))):
            continue
        out.append((lp.id, getattr(lp, "kind", None), seq))
    return out


def _is_pure_cycle(nodes, adj):
    if len(nodes) < 3 or any(len(adj[v]) != 2 for v in nodes):
        return False
    seen, stack = {min(nodes)}, [min(nodes)]
    while stack:
        x = stack.pop()
        for w in adj[x]:
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return len(seen) == len(nodes)


def _pure_cycle_order(nodes, adj):
    """纯环环序：最小 id 起点，首步向较小邻居（确定性）。"""
    start = min(nodes)
    order = [start]
    prev, cur = None, start
    while True:
        nxts = sorted(w for w in adj[cur] if w != prev)
        if not nxts:
            return None
        step = nxts[0]
        if step == start:
            break
        order.append(step)
        prev, cur = cur, step
        if len(order) > len(nodes):
            return None
    return order if len(order) == len(nodes) else None


def _non_bridge_ratio(nodes, adj, pairs):
    """环边占比 = 非桥边 / 无向边数（桥 = 删除后连通分量增加）。"""
    def ncomp(adj2):
        seen, c = set(), 0
        for s in nodes:
            if s in seen:
                continue
            c += 1
            st = [s]
            seen.add(s)
            while st:
                x = st.pop()
                for y in adj2[x]:
                    if y not in seen:
                        seen.add(y)
                        st.append(y)
        return c

    base = ncomp(adj)
    nb = 0
    for e in sorted(pairs):
        adj2 = defaultdict(set)
        for v in nodes:
            for w in adj[v]:
                if ((v, w) if v < w else (w, v)) != e:
                    adj2[v].add(w)
                    adj2[w].add(v)
        if ncomp(adj2) == base:
            nb += 1
    return nb / len(pairs) if pairs else 0.0


def _chord_segments(ring, edges):
    """环内弦边（ring-ring 非环边）单位圆直线段（交叉代理）。"""
    rset = set(ring)
    rpos = {v: (math.cos(2 * math.pi * i / len(ring) - math.pi / 2),
                math.sin(2 * math.pi * i / len(ring) - math.pi / 2))
            for i, v in enumerate(ring)}
    cyc_pairs = {(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))}
    cyc_pairs |= {(b, a) for a, b in cyc_pairs}
    segs, seen = [], set()
    for a, b in edges:
        if a not in rset or b not in rset:
            continue
        p = (a, b) if a < b else (b, a)
        if p in cyc_pairs or p in seen:
            continue
        seen.add(p)
        segs.append((rpos[a], rpos[b], (a, b)))
    return segs


def detect_ring(graph):
    """触发判定 + 主环选择。返回 ring plan dict 或 None（不触发）。

    plan = {"ring": [环序], "k": int, "declared_loop": id|None,
            "polarity": "R"|"B"|None, "trigger": "pure-cycle"|"cover"|"ratio",
            "residuals": [非环非孤立节点], "deg0": [孤立节点],
            "chord_crossings": int}
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 3 or n > MAX_RING_N:
        return None
    edges = [(e.a, e.b) for e in graph.edges]
    adj, pairs = _adjacency(edges)
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]

    if _is_pure_cycle(core, adj):
        seq = _pure_cycle_order(core, adj)
        if seq:
            return {"ring": seq, "k": len(seq), "declared_loop": None,
                    "polarity": None, "trigger": "pure-cycle",
                    "residuals": [], "deg0": deg0,
                    "chord_crossings": 0}

    cands = []                                        # [(环序, loop_id, kind)]
    for lid, kind, seq in _declared_loop_cycles(graph, adj):
        cands.append((seq, lid, kind))
    for seq in _enumerate_cycles(core, adj):
        cands.append((seq, None, None))
    if not cands:
        return None

    ratio = _non_bridge_ratio(nodes, adj, pairs)
    cover_ok = any(len(s) >= n - COVER_SLACK for s, _, _ in cands)
    if not (cover_ok or ratio >= CYCLE_EDGE_RATIO):
        return None

    eligible = [(s, lid, pol) for s, lid, pol in cands
                if len(s) >= n - COVER_SLACK] or cands
    best = None
    for seq, lid, pol in eligible:
        cross = _crossing_count(_chord_segments(seq, edges))
        # 主环 = 覆盖最大的环（真·主导回路）；同覆盖下弦交叉 0 优先 → 字典序
        key = (-len(seq), cross, _canonical(seq))
        if best is None or key < best[0]:
            best = (key, seq, lid, pol, cross)
    _, ring, lid, pol, cross = best
    residuals = [v for v in core if v not in set(ring)]
    return {"ring": list(ring), "k": len(ring), "declared_loop": lid,
            "polarity": pol, "trigger": "cover" if cover_ok else "ratio",
            "residuals": residuals, "deg0": deg0, "chord_crossings": cross}


def _ring_radius(k, ring_widths, n_residuals=0):
    """正 k 边形半径：相邻卡中心距 ≥ (w_u+w_v)/2 + ADJ_GAP；超上界不可行。

    n_residuals>0 时抬高半径给环内让位（每残节点 +40px，上界内）。
    """
    need = 0.0
    for i in range(k):
        wu = ring_widths.get(i, 96)
        wv = ring_widths.get((i + 1) % k, 96)
        need = max(need, (wu + wv) / 2 + ADJ_GAP)
    r = need / (2 * math.sin(math.pi / k))
    r = max(r, RADIUS_MIN + 40 * n_residuals)
    if r > RADIUS_MAX:
        raise InfeasibleRing(f"半径需求 {r:.0f}px 超上界 {RADIUS_MAX}")
    return max(RADIUS_MIN, int(math.ceil(r / 2) * 2))


# 残节点确定性候选族：环内分数 × 角度偏移（固定序，先近心后远心、先零偏移）
_INNER_FS = (0.42, 0.34, 0.50, 0.26, 0.58, 0.18, 0.66)
_ANGLE_DS = (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0, 120.0, -120.0)


def place_ring(plan, widths, card_h, cfg, adj, edges):
    """环形排布 → ({v: x}, {v: y}, meta)。全整数 2px 网格、确定性。

    残节点指派：候选 = 环内分数 × 角度偏移（邻居角质心为 0°），逐残节点
    （id 序）取「新增直线代理交叉最少 → 角度偏移最小 → 分数最接近 0.42」
    的无碰撞候选；环内全撞则试环外近邻侧；再无 → InfeasibleRing。
    edges：直线代理交叉打分用（环边 + 弦 + 已放残节点辐条）。
    """
    ring, k = plan["ring"], plan["k"]
    ring_widths = {i: widths.get(v, 96) for i, v in enumerate(ring)}
    r = _ring_radius(k, ring_widths, len(plan["residuals"]))
    cx = int(r // 2) * 2
    cy = int((r + card_h // 2 + 40) // 2) * 2
    pos, y, angles = {}, {}, {}
    for i, v in enumerate(ring):
        ang = 2 * math.pi * i / k - math.pi / 2
        angles[v] = ang
        pos[v] = int(round((cx + r * math.cos(ang)) / 2) * 2)
        y[v] = int(round((cy + r * math.sin(ang)) / 2) * 2)

    def _rect(v, px, py):
        w = widths.get(v, 96)
        return (px - w / 2, py - card_h / 2, px + w / 2, py + card_h / 2)

    placed = {v: _rect(v, pos[v], y[v]) for v in ring}

    def _free(v, px, py, gap=18):
        rx0, ry0, rx1, ry1 = _rect(v, px, py)
        for ux0, uy0, ux1, uy1 in placed.values():
            if rx0 < ux1 + gap and ux0 < rx1 + gap and ry0 < uy1 + gap and uy0 < ry1 + gap:
                return False
        return True

    # 直线代理段（交叉打分）：环边 + 环内弦
    segs = []
    rpos = {v: (pos[v], y[v]) for v in ring}
    for i in range(k):
        a, b = ring[i], ring[(i + 1) % k]
        segs.append((rpos[a], rpos[b], frozenset((a, b))))
    cyc_pairs = {(ring[i], ring[(i + 1) % k]) for i in range(k)}
    cyc_pairs |= {(b, a) for a, b in cyc_pairs}
    rset = set(ring)
    seen_e = set()
    for a, b in edges:
        if a in rset and b in rset:
            p = (a, b) if a < b else (b, a)
            if p not in cyc_pairs and p not in seen_e:
                seen_e.add(p)
                segs.append((rpos[a], rpos[b], frozenset((a, b))))

    def _add_cross(px, py, v):
        """候选 (px,py) 处放 v 的新增直线代理交叉数（对已放邻居）。"""
        c = 0
        for u in sorted(adj[v]):
            if u not in pos:
                continue
            seg = ((px, py), (pos[u], y[u]), frozenset((v, u)))
            for q1, q2, eids in segs:
                if v in eids or u in eids:
                    continue
                if _seg_cross(seg[0], seg[1], q1, q2):
                    c += 1
        return c

    residual_pos = {}
    for v in sorted(plan["residuals"]):
        nbrs = [angles[u] for u in sorted(adj[v]) if u in angles]
        ang0 = (math.atan2(sum(math.sin(a) for a in nbrs),
                           sum(math.cos(a) for a in nbrs))
                if nbrs else 0.0)
        best = None
        for zone in ("inner", "outer"):
            for f in (_INNER_FS if zone == "inner"
                      else (1.0 + (card_h / 2 + 40 + 40 * i) / r for i in range(3))):
                for d in _ANGLE_DS:
                    ang = ang0 + math.radians(d)
                    px = int(round((cx + f * r * math.cos(ang)) / 2) * 2)
                    py = int(round((cy + f * r * math.sin(ang)) / 2) * 2)
                    if not _free(v, px, py):
                        continue
                    cross = _add_cross(px, py, v)
                    key = (cross, abs(d), abs(f - 0.42) if zone == "inner" else 1.0 + abs(f - 1.3),
                           px, py)
                    if best is None or key < best[0]:
                        best = (key, px, py, zone, f)
                if best is not None and best[0][0] == 0 and zone == "inner":
                    break       # 环内已零交叉，无需再扫
            if best is not None:
                break
        if best is None:
            raise InfeasibleRing(f"残节点 {v} 无无碰撞候选")
        _, px, py, zone, f = best
        pos[v], y[v] = px, py
        placed[v] = _rect(v, px, py)
        residual_pos[v] = [zone, round(f, 3)]
        for u in sorted(adj[v]):
            if u in pos:
                segs.append(((px, py), (pos[u], y[u]), frozenset((v, u))))
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = max(cfg.margin, cx - total / 2)
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    meta = {
        "placement": "ring-cycle",
        "ring": {
            "nodes": list(ring),
            "radius": r,
            "center": [cx, cy],
            "declared_loop": plan.get("declared_loop"),
            "polarity": plan.get("polarity"),
            "trigger": plan.get("trigger"),
            "chord_crossings": plan.get("chord_crossings", 0),
            "residuals": {v: info for v, info in residual_pos.items()},
        },
    }
    return pos, y, meta
