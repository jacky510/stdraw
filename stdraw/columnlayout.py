# -*- coding: utf-8 -*-
"""长链/少环图的纵列排布（2026-11-06 jacky 布局美学定调 v2，ref-scrubbed）。

> 「如果方框排布能有规律，那么就尽量形成规律，比如纵向对齐一列……
> 线尽量配合方框的排布来画。规律让图形更好看，也更好理解。」

触发判定（图论度量，全确定性；在 ringlayout.detect_ring 的 pure-cycle 与
ratio 分支之后、cover 分支之前判定）：
  1. 小图：3 ≤ n ≤ MAX_COLUMN_N（n 含孤立节点）；
  2. 少环：最长简单回路 k 满足 3 ≤ k ≤ MAX_RING_K（主环小 → 「环」不主导，
     主链感强；k = n 的大环归环形排布）；
  3. 长链：主环外的节点以「支路」挂在主链近邻侧（残节点 ≤ n - k）。

主链（spine）选择（同构一致性：结构性签名驱动，不依赖声明环 id 顺序）：
  候选 = 声明环（构成简单回路者，保留方向）∪ 图论枚举简单回路；
  按「环长最大 → 负边数最少（全正增长回路优先当主链）→ WL 结构色签名
  字典序」确定性选优。

排布（place_column）：
  - 主链节点沿中央纵列对齐一列（x = 列轴，y = top + i·pitch）；
  - 主链闭合边（last→first）构造为左侧大弧（quadratic bezier，控制点在
    列轴左侧按确定性阶梯外推，解析验证与全部框净距 ≥ clearance）——
    「回路聚拢/圆环感」在纵列形态下的实现；
  - 支路（残节点）挂主链近邻侧：右列优先（与闭合弧异侧），按锚点行
    对齐或跨行中点对齐；多支路结构右列 → 左列（左列在闭合弧外再外推）；
  - 孤立节点停顶部停车带（与既有模式一致）。

布线/证书：交给既有 Router 与 certificate_auto；纵列模式指标口径
（主链列对齐 + 等行距 + 回路聚拢度）在 metrics/check 内按
meta.placement == "column-chain" 切换。闭合弧以构造路线注入
（同 --from-layout waypoints 的覆盖机制，坐标交付前随 dx/dy 平移）。
"""
import math
from collections import defaultdict

MAX_COLUMN_N = 12          # 触发上限：小图
MAX_RING_K = 4             # 主环 ≤4 视为「少环」（5+ 归环形）
SIDE_GAP = 36              # 支路列与主链的水平净距（呼吸感目标档）
ARC_MARGIN = 20            # 闭合弧相对最左障碍的额外余量
ARC_LADDER = (0, 24, 48, 72, 96, 128, 160)   # 弧控制点外推阶梯（px）


class InfeasibleColumn(Exception):
    """纵列槽位不可行（闭合弧/支路位无解）——调用方回退既有路径。"""


def _adjacency(edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _wl_colors(nodes, adj):
    """WL 式结构色（2 轮 refine）：{v: tuple}。同构图的对应节点同色
    （结构性签名，不依赖 id）——同构骨架 → 同布局模板的机制基础。"""
    color = {v: (len(adj[v]),) for v in nodes}
    for _ in range(2):
        nxt = {}
        for v in nodes:
            nxt[v] = (color[v],
                      tuple(sorted(color[w] for w in sorted(adj[v]))))
        # 压缩为秩（确定性：按签名排序取序号）
        order = {sig: i for i, sig in enumerate(sorted(set(nxt.values())))}
        color = {v: (order[nxt[v]],) for v in nodes}
    return color


def _edge_signs(edges):
    """无向键 → 极性集合（一 对多 当双向边存在）。"""
    signs = defaultdict(set)
    for a, b, pol in edges:
        signs[(a, b) if a < b else (b, a)].add(pol)
    return signs


def _neg_count(seq, edges, adj):
    """环序上有向边的负边数（无向邻接但对不存在的段记 0）。"""
    esign = {}
    for a, b, pol in edges:
        esign[(a, b)] = pol
        esign.setdefault((b, a), pol)
    neg = 0
    for i in range(len(seq)):
        a, b = seq[i], seq[(i + 1) % len(seq)]
        if esign.get((a, b)) == "-":
            neg += 1
    return neg


def _declared_loop_cycles(graph, adj):
    out = []
    for lp in graph.loops:
        seq = list(lp.nodes)
        if len(seq) < 3 or len(set(seq)) != len(seq):
            continue
        if not all(seq[(i + 1) % len(seq)] in adj[seq[i]] for i in range(len(seq))):
            continue
        out.append((lp.id, seq))
    return out


def _enumerate_cycles(nodes, adj, cap=2_000_000):
    """与 ringlayout 同口径的简单回路枚举（规范形去重、步数上限）。"""
    steps = [0]
    found = {}

    def canon(seq):
        best = None
        for s in (list(seq), list(seq)[::-1]):
            for i in range(len(s)):
                rot = s[i:] + s[:i]
                if best is None or rot < best:
                    best = rot
        return tuple(best)

    class _Cap(Exception):
        pass

    def dfs(start, v, path, seen):
        steps[0] += 1
        if steps[0] > cap:
            raise _Cap
        for w in sorted(adj[v]):
            if w == start and len(path) >= 3:
                c = canon(path)
                found[c] = c
            elif w not in seen:
                seen.add(w)
                dfs(start, w, path + [w], seen)
                seen.remove(w)

    try:
        for s in sorted(nodes):
            dfs(s, s, [s], {s})
    except _Cap:
        pass
    return [list(c) for c in found.values()]


def detect_column(graph):
    """触发判定 + 主链选择。返回 column plan dict 或 None。

    plan = {"spine": [主链序（有向，起点=结构最显著节点）],
            "k": int, "declared_loop": id|None,
            "residuals": [非主链非孤立节点], "deg0": [孤立节点],
            "closing": (last, first) 主链闭合边}
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 3 or n > MAX_COLUMN_N:
        return None
    edges = [(e.a, e.b, getattr(e, "polarity", "+")) for e in graph.edges]
    adj = _adjacency([(a, b) for a, b, _ in edges])
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if not core:
        return None

    cands = []                                   # [(环序, loop_id, 负边数)]
    for lid, seq in _declared_loop_cycles(graph, adj):
        cands.append((seq, lid, _neg_count(seq, edges, adj)))
    for seq in _enumerate_cycles(core, adj):
        cands.append((seq, None, _neg_count(seq, edges, adj)))
    if not cands:
        return None

    kmax = max(len(s) for s, _, _ in cands)
    if kmax < 3 or kmax > MAX_RING_K:
        return None
    # 纯环（单连通分量全度 2 且 k=n）归环形排布
    if kmax == n and all(len(adj[v]) == 2 for v in core):
        return None
    # 主环覆盖全图（k=n）→ 环形主导，不进纵列
    if kmax >= n:
        return None

    colors = _wl_colors(core, adj)
    eligible = [(s, lid, neg) for s, lid, neg in cands if len(s) == kmax]
    # 选优：负边最少（全正增长回路当主链）→ 结构色签名 → 声明优先 → 规范形
    best = None
    for seq, lid, neg in eligible:
        key = (neg, tuple(sorted(tuple(colors[v]) for v in seq)),
               0 if lid is not None else 1, _canon(seq))
        if best is None or key < best[0]:
            best = (key, seq, lid)
    _, spine0, lid = best
    spine = _orient_spine(spine0, adj, colors, edges)
    residuals = [v for v in core if v not in set(spine)]
    return {"spine": spine, "k": len(spine), "declared_loop": lid,
            "residuals": residuals, "deg0": deg0,
            "closing": (spine[-1], spine[0])}


def _canon(seq):
    best = None
    for s in (list(seq), list(seq)[::-1]):
        for i in range(len(s)):
            rot = s[i:] + s[:i]
            if best is None or rot < best:
                best = rot
    return tuple(best)


def _orient_spine(seq, adj, colors, edges):
    """环序 → 有向主链序：起点 = 结构最显著节点（WL 色 → 度 → id），
    方向 = 沿有向边（邻接表上有向边 a→b 的环邻接方向）。"""
    esign = set()
    for a, b, _ in edges:
        esign.add((a, b))
    n = len(seq)
    # 候选起点：按（结构色字典序最大=最显著，度，-id 序）取首
    start = max(seq, key=lambda v: (tuple(colors[v]), len(adj[v]),
                                    tuple(-ord(c) for c in str(v))))
    # 两个环向，取「有向边跟随数」多者；平局取canonical 序小者
    def directed_follows(order):
        c = 0
        for i in range(len(order)):
            if (order[i], order[(i + 1) % len(order)]) in esign:
                c += 1
        return c
    o1 = [seq[(seq.index(start) + i) % n] for i in range(n)]
    o2 = [seq[(seq.index(start) - i) % n] for i in range(n)]
    c1, c2 = directed_follows(o1), directed_follows(o2)
    if c1 != c2:
        return o1 if c1 > c2 else o2
    return o1 if _canon(o1) <= _canon(o2) else o2


def _quad_points(p0, ctrl, p1, seg=24):
    """二次贝塞尔采样（与 routing.quad_points 同口径）。"""
    return [[(1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * p1[1]]
            for t in (i / seg for i in range(seg + 1))]


def _pt_rect_dist(px, py, cx, cy, hw, hh):
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def _arc_clear(pts, nodes_px, a, b, clearance):
    """弧线净距验证（与 check3 同口径）：sample_polyline step=4 加密采样——
    贝塞尔弦切效应在端部高曲率处可达 ~4px，稀疏采样会漏检。"""
    from .routing import sample_polyline
    dense = sample_polyline([tuple(p) for p in pts], step=4.0)
    for v, (nx, ny, nw, nh) in nodes_px.items():
        if v in (a, b):
            continue
        for px, py in dense:
            if _pt_rect_dist(px, py, nx, ny, nw / 2, nh / 2) < clearance + 2:
                return False
    return True


def _closing_arc(nodes_px, spine, widths, card_h, clearance, side_cols):
    """主链闭合边 (last→first)：左侧大弧。

    二次贝塞尔在 t=0.5 处的鼓出 = |ctrl − 弦中点| / 2——控制点直接按
    「目标鼓出线 = 最左障碍左缘 − (clearance + 余量)」解算，再逐框解析
    验证；验证不过按 48px 阶梯外推（上限 6 档），仍不可行 → Infeasible。

    side_cols: {side(-1左/+1右): [(cx, hw), ...]} 该侧已放支路框（弧须避开）。
    返回 {"kind": "arc", "points": [...], "ctrl": [x, y],
          "anchors": {...}, "min_clear": float}
    """
    a_last, a_first = spine[-1], spine[0]
    xa, ya = nodes_px[a_last][0], nodes_px[a_last][1]
    xb, yb = nodes_px[a_first][0], nodes_px[a_first][1]
    ha = widths[a_last] / 2
    hb = widths[a_first] / 2
    pa = [xa - ha, ya]                      # 下方卡左边中点
    pb = [xb - hb, yb]                      # 上方卡左边中点
    ymid = (ya + yb) / 2
    # 目标鼓出线：所有需避开框的左缘 − (clearance + 4px 保守余量)
    target = None
    for v, (nx, ny, nw, nh) in nodes_px.items():
        if v in (a_last, a_first):
            continue
        t = nx - nw / 2 - clearance - 4
        target = t if target is None else min(target, t)
    if target is None:
        target = (pa[0] + pb[0]) / 2 - clearance - ARC_MARGIN
    chord_mid = (pa[0] + pb[0]) / 2
    base_ctrl = 2.0 * target - chord_mid    # t=0.5 鼓出恰达 target
    for step in (0, 48, 96, 144, 192, 240):
        ctrl = [base_ctrl - step, ymid]
        pts = _quad_points(pa, ctrl, pb)
        ok = _arc_clear(pts, nodes_px, a_last, a_first, clearance)
        if ok:
            return {"kind": "arc", "points": pts, "ctrl": ctrl,
                    "min_clear": None}
    raise InfeasibleColumn("闭合弧无可行外推档")


def _side_arc(nodes_px, a, b, side, widths, card_h, clearance):
    """主链跨行弦边（|行差| ≥ 2 的主链节点对）构造为 side 侧大弧。

    与 _closing_arc 同数学：t=0.5 鼓出 = |ctrl − 弦中点| / 2，控制点按
    目标鼓出线解算 + 逐框验证 + 48px 阶梯外推（6 档），不可行返回 None
    （调用方回退 Router 候选池）。side=+1 右 / -1 左。"""
    xa, ya = nodes_px[a][0], nodes_px[a][1]
    xb, yb = nodes_px[b][0], nodes_px[b][1]
    pa = [xa + side * widths[a] / 2, ya]
    pb = [xb + side * widths[b] / 2, yb]
    ymid = (ya + yb) / 2
    target = None
    for v, (nx, ny, nw, nh) in nodes_px.items():
        if v in (a, b):
            continue
        t = (nx + side * nw / 2) + side * (clearance + 4)
        target = t if target is None else (max(target, t) if side > 0
                                           else min(target, t))
    chord_mid = (pa[0] + pb[0]) / 2
    if target is None:
        target = chord_mid + side * (clearance + ARC_MARGIN)
    base_ctrl = 2.0 * target - chord_mid
    for step in (0, 48, 96, 144, 192, 240):
        ctrl = [base_ctrl + side * step, ymid]
        pts = _quad_points(pa, ctrl, pb)
        ok = _arc_clear(pts, nodes_px, a, b, clearance)
        if ok:
            return {"kind": "arc", "points": pts, "ctrl": ctrl,
                    "min_clear": None}
    return None


def place_column(plan, widths, card_h, cfg, adj, edges):
    """纵列排布 → ({v: x}, {v: y}, meta, closing_routes)。全 2px 网格、确定性。

    支路列：右列优先（+1），多支路溢出到左列（-1，闭合弧让位外推）。
    单锚支路挂锚点行；跨两锚支路挂两锚行中点（半 pitch 偏移）。
    """
    spine = plan["spine"]
    k = len(spine)
    x0 = 0                                     # 列轴（交付层统一平移）
    pitch = cfg.pitch
    pos, y = {}, {}
    for i, v in enumerate(spine):
        pos[v] = x0
        y[v] = cfg.top + i * pitch
    spine_w_max = max(widths[v] for v in spine)

    # 残节点成组（互相邻接的残节点 = 同一支路结构），锚点 = 组内节点的主链邻居
    spine_set = set(spine)
    res_set = set(plan["residuals"])
    groups = []                                # [(锚点元组, [残节点]（id 序）)]
    seen = set()
    for v in sorted(plan["residuals"]):
        if v in seen:
            continue
        comp, stack = [], [v]
        seen.add(v)
        while stack:
            u = stack.pop()
            comp.append(u)
            for w in sorted(adj[u] & res_set):
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        anch = tuple(sorted(set().union(*[adj[u] & spine_set for u in comp])))
        groups.append((anch, sorted(comp)))
    # 组序确定性：锚点在主链上的行位 → 锚点元组 → 成员 id
    def _group_key(g):
        anch, comp = g
        rows = tuple(sorted(spine.index(a) for a in anch))
        return (rows, anch, tuple(comp))
    groups.sort(key=_group_key)

    # 列几何：右列（+1）优先；闭合弧占左侧，溢出组放左列（弧再外推让位）
    closing_side = -1
    wmax_side = max([widths[v] for _, comp in groups for v in comp] or [10])
    side_x = int((spine_w_max / 2 + SIDE_GAP + wmax_side / 2) / 2) * 2
    col_slots = {1: [], -1: []}                # 已占行位 [y]
    side_cols = {1: [], -1: []}                # (cx, hw) 供闭合弧避让

    def _base_y(anch):
        """组行位：单锚 = 锚点行；多锚 = 首末锚行中点。"""
        if len(anch) == 1:
            return y[anch[0]]
        return (y[anch[0]] + y[anch[-1]]) / 2

    def _try_place(anch, comp, side):
        """组整体放入 side 列：组内自 base 起按整 pitch 向下/上展开
        （pitch ≥ card_h+SIDE_GAP，保证组内净距）；槽位冲突 → None。"""
        base = _base_y(anch)
        offsets = []
        for i in range(len(comp)):
            offsets.append(((i + 1) // 2) * pitch * (1 if i % 2 == 0 else -1))
        ys = [base + off for off in offsets]
        for yy in ys:
            if any(abs(yy - q) < card_h + SIDE_GAP for q in col_slots[side]):
                return None
        out = {}
        for v, yy in zip(comp, ys):
            out[v] = (int((side * side_x) / 2) * 2, int(round(yy / 2) * 2))
        return out

    for anch, comp in groups:
        placed = None
        for side in (1, -1):
            cand = _try_place(anch, comp, side)
            if cand is not None:
                placed = cand
                break
        if placed is None:
            # 兜底：同组换行梯子（右列向下/上逐档试探，整 pitch 步进）
            base = _base_y(anch)
            for dy in (pitch, -pitch, pitch * 2, -pitch * 2,
                       pitch * 3 / 2, -pitch * 3 / 2):
                ys = [base + dy + off for off in
                      [((i + 1) // 2) * pitch * (1 if i % 2 == 0 else -1)
                       for i in range(len(comp))]]
                if all(not any(abs(yy - q) < card_h + SIDE_GAP
                               for q in col_slots[1]) for yy in ys):
                    placed = {v: (int(side_x / 2) * 2, int(round(yy / 2) * 2))
                              for v, yy in zip(comp, ys)}
                    break
        if placed is None:
            raise InfeasibleColumn(f"支路组 {comp} 无可行列位")
        for v, (px, py) in placed.items():
            pos[v], y[v] = px, py
            col_slots[1 if px > x0 else -1].append(py)
            side_cols[1 if px > x0 else -1].append((px, widths[v]))

    # 孤立节点停车带
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = x0 - total / 2
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in pos}
    closing = _closing_arc(nodes_px, spine, widths, card_h,
                           cfg.clearance, side_cols)

    # 主链跨行弦边（非相邻主链节点对）：构造右侧大弧（与左侧闭合弧对侧，
    # 回路聚拢的弦内布线）；不可行（多弦互撞等）回退 Router 候选池。
    constructed = {plan["closing"]: closing}
    row_of = {v: i for i, v in enumerate(spine)}
    eset = set(edges)
    for (a, b) in sorted(eset):
        if a not in row_of or b not in row_of:
            continue
        if (a, b) == plan["closing"] or (b, a) == plan["closing"]:
            continue
        if abs(row_of[a] - row_of[b]) < 2:
            continue
        sa = _side_arc(nodes_px, a, b, 1, widths, card_h, cfg.clearance)
        if sa is not None:
            constructed[(a, b)] = sa

    meta = {
        "placement": "column-chain",
        "column": {
            "spine": list(spine),
            "pitch": pitch,
            "axis_x": x0,
            "declared_loop": plan.get("declared_loop"),
            "closing": list(plan["closing"]),
            "closing_side": "left",
            "side_columns": {s: [v for v in sorted(pos)
                                 if v not in spine_set
                                 and (pos[v] > x0) == (s == 1)]
                             for s in (1, -1) if any(
                                 v not in spine_set and
                                 (pos[v] > x0) == (s == 1) for v in pos)},
            "residuals": list(plan["residuals"]),
        },
    }
    return pos, y, meta, constructed
