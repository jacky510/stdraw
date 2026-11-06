# -*- coding: utf-8 -*-
"""领结（双三角共边）对称排布（2026-11-06 jacky 布局美学定调 v2，ref-scrubbed）。

> #11 learning-flywheel「可对称却偏左」——对称结构应显式对称。

触发判定（确定性局部结构，先于环形判定）：
  核心图恰为「两个三角形共享一条边」（领结/bowtie）：4 节点、5 边、
  度序列 {3,3,2,2}，且两个度-3 节点相邻（共享边端点）、两个度-2 节点
  不相邻（左右顶点）。语料命中：learning-flywheel / fixes-that-fail
  （有向同构对 → 同一布局模板）。

排布（place_bowtie）：
  - 共享边端点 A（上行）/ B（下行）居纵轴；两顶点左（-D）/右（+D）
    中行镜像 —— 显式几何对称；
  - 线型一致性硬规则：轴边 A→B 直线；4 条侧边全部构造为镜像弧
    （ctrl 向外侧对称偏移）——「同一对称结构内线型一致（不直弧折混杂）」。

居中规范化：A/B/apex 的包围盒中心即画布中心（布局层轴 x=0，交付层
统一平移居中，见 layout_auto 的居中后处理）。
"""
import math

SYM_GAP = 36              # 呼吸感目标净距
ARC_K_FALLBACK = 0.22     # 侧弧 k 兜底档（side_geom 为空时不可达，防御用）


class InfeasibleBowtie(Exception):
    pass


def _adjacency(edges):
    adj = {v: set() for a, b in edges for v in (a, b)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def detect_bowtie(graph):
    """领结判定。返回 {"A","B","L","R","deg0"} 或 None。"""
    nodes = list(graph.node_ids())
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj.get(v)]
    deg0 = [v for v in nodes if not adj.get(v)]
    if len(core) != 4 or len(edges) != 5:
        return None
    d3 = sorted(v for v in core if len(adj[v]) == 3)
    d2 = sorted(v for v in core if len(adj[v]) == 2)
    if len(d3) != 2 or len(d2) != 2:
        return None
    a, b = d3
    l, r = d2
    if b not in adj[a] or r in adj[l]:
        return None
    # 结构自检：恰两个三角形 = {a,b,l} 与 {a,b,r}，共享边 a-b
    if not (l in adj[a] and l in adj[b] and r in adj[a] and r in adj[b]):
        return None
    # A = 上行节点：确定性（id 序；a/b 为自反对换对称位，几何不变）
    return {"A": a, "B": b, "L": l, "R": r, "deg0": deg0}


from .routing import border_point as _border_point


def _quad_points(p0, ctrl, p1, seg=24):
    return [[(1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * p1[1]]
            for t in (i / seg for i in range(seg + 1))]


def _own_press(pts, na, nb):
    """弧线中间采样点是否进入两端自家框（含 1px 余量；与 check2 同口径）。

    诊断辅助（ctrl 平移口径下正常不触发，保留供调试复算）。
    """
    from .routing import dist_point_rect
    for p in pts[1:-1]:
        for bx, by, bw, bh in (na, nb):
            if dist_point_rect(p[0], p[1], bx, by, bw / 2 + 1, bh / 2 + 1) <= 0:
                return True
    return False


def _natural_border(cx, cy, hw, hh, dx, dy):
    """射线与框边的自然交点（不带带钳制；用于计算锚点钳制增量）。"""
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return [cx, cy]
    if abs(dx) < 1e-9:
        return [cx, cy + (hh if dy > 0 else -hh)]
    if abs(dy) < 1e-9:
        return [cx + (hw if dx > 0 else -hw), cy]
    t = min(hw / abs(dx), hh / abs(dy))
    return [cx + dx * t, cy + dy * t]


def _clamp_band(p, nx, ny, nw, nh):
    """锚点钳制到所属边中点 ±1/4 边长带（转角排除；连接点交付口径）。"""
    hw, hh = nw / 2.0, nh / 2.0
    dxo, dyo = p[0] - nx, p[1] - ny
    on_x = abs(abs(dxo) - hw) <= abs(abs(dyo) - hh)
    if on_x:
        return [p[0], ny + max(-hh / 2, min(hh / 2, dyo))]
    return [nx + max(-hw / 2, min(hw / 2, dxo)), p[1]]


def place_bowtie(plan, widths, card_h, cfg, edges):
    """领结对称排布 → ({v: x}, {v: y}, meta, constructed_routes)。

    constructed_routes: {(a,b): route dict}——轴边直线 + 4 侧边镜像弧，
    构造式注入（不走候选池），保证镜像对称与线型一致。
    """
    A, B, L, R = plan["A"], plan["B"], plan["L"], plan["R"]
    pitch = cfg.pitch
    yA = cfg.top
    yB = cfg.top + pitch
    yMid = cfg.top + pitch / 2
    wmax = max(widths.values())
    # D：顶点距轴——轴卡半宽 + 净距 + 顶点半宽；且左右顶点互距 ≥ SYM_GAP
    D = max(widths[A] / 2 + SYM_GAP + max(widths[L], widths[R]) / 2,
            (SYM_GAP + (widths[L] + widths[R]) / 2) / 2,
            wmax / 2 + SYM_GAP / 2)
    D = int(round(D / 2) * 2)

    pos = {A: 0, B: 0, L: -D, R: D}
    y = {A: int(yA), B: int(yB), L: int(round(yMid / 2) * 2),
         R: int(round(yMid / 2) * 2)}

    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = -total / 2
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    def _np(v):
        return (pos[v], y[v], widths[v], card_h)

    constructed = {}
    eset = {(a, b) for a, b in edges}
    # 轴边：直线（A→B / B→A 按图中有向边；锚点朝向对端框边）
    for u, v in ((A, B), (B, A)):
        if (u, v) not in eset:
            continue
        dy_u = 1 if y[v] > y[u] else -1
        dy_v = 1 if y[u] > y[v] else -1
        pa = _border_point(pos[u], y[u], widths[u] / 2, card_h / 2, 0, dy_u)
        pb = _border_point(pos[v], y[v], widths[v] / 2, card_h / 2, 0, dy_v)
        constructed[(u, v)] = {"kind": "line", "points": [pa, pb]}
    # 侧边：镜像弧（顶点↔轴点；ctrl 向外侧偏移，左右镜像同 |ctrl 偏移|）。
    # ref-scrubbed 弧度参数化：k 统一取 4 条侧弦长的 median 档（adaptive）——
    # 同一对称结构弧度一致、视觉均匀（「同环弧度一致」硬规则）。
    # 连接点口径：弧先按**自然锚点**（旧射线口径）定型，再映射到钳制后
    # 锚点——ctrl 取弦坐标变换（α 弦比例不变 + β 垂偏向量不变），弧相对
    # 形状/出发切向保持，不翻进自家框。
    side_geom = []
    for apex, s in ((L, -1), (R, 1)):
        for axis_v in (A, B):
            for e in ((apex, axis_v), (axis_v, apex)):
                if e not in eset:
                    continue
                a, b = e
                na, nb = _np(a), _np(b)
                dx, dy = nb[0] - na[0], nb[1] - na[1]
                pa_n = _natural_border(na[0], na[1], na[2] / 2, na[3] / 2,
                                       dx, dy)
                pb_n = _natural_border(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                                       -dx, -dy)
                pa_c = _clamp_band(pa_n, na[0], na[1], na[2], na[3])
                pb_c = _clamp_band(pb_n, nb[0], nb[1], nb[2], nb[3])
                dist = math.hypot(pb_n[0] - pa_n[0], pb_n[1] - pa_n[1])
                side_geom.append((e, pa_n, pb_n, pa_c, pb_c, dist, s))
    from .routing import adaptive_arc_k
    k_uni = ARC_K_FALLBACK
    if side_geom:
        dists = sorted(g[5] for g in side_geom)
        med = dists[len(dists) // 2] if len(dists) % 2 else \
            (dists[len(dists) // 2 - 1] + dists[len(dists) // 2]) / 2
        k_uni = adaptive_arc_k(med)
    for e, pa, pb, pa_c, pb_c, dist, s in side_geom:
        vx, vy = pb[0] - pa[0], pb[1] - pa[1]
        ux, uy = -vy / dist, vx / dist
        # 外侧法向：与「顶点→轴」方向的选择使 ctrl 远离纵轴
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        cx = mx + ux * k_uni * dist * s
        cy = my + uy * k_uni * dist * s
        if (cx - 0) * s < (mx - 0) * s:      # ctrl 必须比中点更靠外
            cx = mx - ux * k_uni * dist * s
            cy = my - uy * k_uni * dist * s
        # 弦坐标映射到钳制锚点：ctrl = pa_c + α·(pb_c−pa_c) + β_vec
        wx, wy = cx - pa[0], cy - pa[1]
        alpha = (wx * vx + wy * vy) / (dist * dist)
        betax = wx - alpha * vx
        betay = wy - alpha * vy
        v2x, v2y = pb_c[0] - pa_c[0], pb_c[1] - pa_c[1]
        cx2 = pa_c[0] + alpha * v2x + betax
        cy2 = pa_c[1] + alpha * v2y + betay
        constructed[e] = {"kind": "arc",
                          "points": _quad_points(pa_c, [cx2, cy2], pb_c),
                          "ctrl": [cx2, cy2]}
    meta = {
        "placement": "symmetric",
        "symmetry": {
            "axis": "vertical",
            "axis_x": 0,
            "shared_edge": [A, B],
            "mirror_pairs": [[L, R]],
            "gap": SYM_GAP,
            "line_style_rule": "axis-straight + mirrored-arcs",
        },
    }
    return pos, y, meta, constructed
