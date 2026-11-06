# -*- coding: utf-8 -*-
"""WS3 布线数学层：可见性图最短直线路径 + 净距约束最小曲率弧线。

数学口径（诚实声明，与证书措辞一致）：
1. 直线绕障 = **膨胀障碍角点可见性图上的 Dijkstra 最短路**（图上精确最优，
   经典计算几何定理）。障碍按净距 c 做 box growing：膨胀矩形 ⊇ 圆角
   Minkowski 区域（|p−rect| < c），故「线段不进膨胀矩形 ⇒ 与原矩形欧氏
   净距 ≥ c」。相对圆角障碍连续空间的真最短路，每个贴角至多多
   (2−π/2)·c ≈ 0.43c px——由弧线平滑的切角效应回收。
2. 每条可见边用**线段-矩形精确距离**独立复核（Liang-Barsky 相交判定 +
   四边线段-线段距离），净距是解析保证，不靠离散采样巧合。
3. 弧线平滑 = 折角处圆弧相切内接：G1 切线连续（无拐点），全程曲率有界
   （≤ 1/r_min）。半径按确定性序列收缩，每条弧逐采样点复核净距；
   本模块按「目标净距 c」建图与复核，调用方以 c = CLEARANCE + 1.5 传入，
   交付坐标复核时留 ≥ +1.4px 余量，硬门 ≥16px 不踩线。
4. 确定性：无 RNG。节点序、候选序、半径序列全部固定；同输入逐字节同输出。

本模块 stdlib-only，不依赖 networkx/ortools。
"""
import math
from heapq import heappush, heappop

VIS_EPS = 1e-6        # 可见性判定的浮点容差
ARC_SAMPLES = 16      # 每条圆弧的采样段数（几何复核/交叉复检用）
FILLET_R_MAX = 36.0   # 平滑弧最大半径 px
FILLET_R_SHRINK = (1.0, 0.75, 0.55, 0.40, 0.28, 0.18, 0.10)  # 确定性收缩序列
FILLET_TAU_MAX = 0.45  # 切段长不超过相邻线段长的比例上限
DEFLECT_SKIP = 0.03    # 折角偏转 < ~1.7° 视为直线，不打弧


# ── 精确距离基元 ─────────────────────────────────────────
def _pt_seg_dist(px, py, a, b):
    """点到线段的最小距离。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < VIS_EPS:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / L2))
    return math.hypot(px - (a[0] + t * vx), py - (a[1] + t * vy))


def seg_seg_dist(p1, p2, p3, p4):
    """两线段距离：相交为 0；不相交时 = 四端点对彼段距离的最小值。"""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < VIS_EPS else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    if d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0:
        return 0.0
    return min(_pt_seg_dist(p1[0], p1[1], p3, p4),
               _pt_seg_dist(p2[0], p2[1], p3, p4),
               _pt_seg_dist(p3[0], p3[1], p1, p2),
               _pt_seg_dist(p4[0], p4[1], p1, p2))


def _seg_hits_rect(x1, y1, x2, y2, cx, cy, hw, hh):
    """Liang-Barsky：线段是否正长度穿入矩形（贴边不算）。与 metrics 同口径。

    自带实现（metrics → routing → 本模块会循环导入，不回引）。
    """
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - (cx - hw)), (dx, (cx + hw) - x1),
                 (-dy, y1 - (cy - hh)), (dy, (cy + hh) - y1)):
        if abs(p) < VIS_EPS:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return t1 - t0 > VIS_EPS


def seg_rect_distance(p1, p2, rect):
    """线段到矩形（中心+半宽半高）的精确最小距离：相交为 0。

    相交判定用 Liang-Barsky（正长度进入才算，贴边不算）；不相交时取
    矩形四边线段-线段距离的最小值。
    """
    cx, cy, hw, hh = rect
    if _seg_hits_rect(p1[0], p1[1], p2[0], p2[1], cx, cy, hw, hh):
        return 0.0
    corners = ((cx - hw, cy - hh), (cx + hw, cy - hh),
               (cx + hw, cy + hh), (cx - hw, cy + hh))
    return min(seg_seg_dist(p1, p2, corners[k], corners[(k + 1) % 4])
               for k in range(4))


def pt_rect_distance(px, py, rect):
    """点到矩形的欧氏距离（框内为 0）。"""
    cx, cy, hw, hh = rect
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


# ── 可见性图 + Dijkstra ──────────────────────────────────
def _graph_nodes(src, dst, rects, c):
    """节点 = 源/汇 + 每个膨胀矩形的 4 角（膨胀角距原矩形恰为 c）。"""
    nodes = [tuple(src), tuple(dst)]
    for (cx, cy, hw, hh) in rects:
        gx, gy = hw + c, hh + c
        nodes.extend([(cx - gx, cy - gy), (cx + gx, cy - gy),
                      (cx + gx, cy + gy), (cx - gx, cy + gy)])
    return nodes


def _visible(p1, p2, rects, c):
    """线段对全部障碍净距 ≥ c − ε（解析复核，不采样）。

    性能（WS5）：先用「线段包围盒 × 矩形包围盒」距离做下界快筛——线段上
    任意点到矩形的距离 ≥ 两包围盒距离，故包围盒距离 ≥ c−ε 时精确距离必
    ≥ c−ε，可跳过精确计算（精确等价，不改变任何判定结果）。
    """
    t = c - VIS_EPS
    t2 = t * t
    x1l, x1h = (p1[0], p2[0]) if p1[0] <= p2[0] else (p2[0], p1[0])
    y1l, y1h = (p1[1], p2[1]) if p1[1] <= p2[1] else (p2[1], p1[1])
    for rect in rects:
        cx, cy, hw, hh = rect
        gx = cx - hw - x1h
        g = x1l - cx - hw
        if g > gx:
            gx = g
        if gx < 0.0:
            gx = 0.0
        if gx < t:
            gy = cy - hh - y1h
            g = y1l - cy - hh
            if g > gy:
                gy = g
            if gy < 0.0:
                gy = 0.0
            # gx/gy 已钳 0：hypot(gx,gy) = 两包围盒距离；< t 才可能挡线
            if gy < t and (gx == 0.0 or gy == 0.0 or gx * gx + gy * gy < t2):
                if seg_rect_distance(p1, p2, rect) < t:
                    return False
    return True


def _dijkstra(nodes, adj, src_idx, dst_idx):
    """确定性 Dijkstra：堆键 (dist, node_idx)，node_idx 唯一 → 弹出序固定。"""
    INF = float("inf")
    dist = [INF] * len(nodes)
    prev = [-1] * len(nodes)
    dist[src_idx] = 0.0
    heap = [(0.0, src_idx)]
    while heap:
        d, u = heappop(heap)
        if d > dist[u] + VIS_EPS:
            continue
        if u == dst_idx:
            break
        # adj[u] 按 node_idx 升序生成 → 松弛序固定；等距不替换（先到先得）
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v] - VIS_EPS:
                dist[v] = nd
                prev[v] = u
                heappush(heap, (nd, v))
    if dist[dst_idx] >= INF:
        return None
    path, cur = [], dst_idx
    while cur != -1:
        path.append(nodes[cur])
        cur = prev[cur]
    path.reverse()
    return path


def shortest_path(src, dst, rects, c):
    """膨胀障碍角点可见性图最短路。不可达返回 None。

    返回折线 [src, corner*, …, dst]（图上精确最优；最优性边界见模块 docstring）。
    """
    if not rects:
        return [tuple(src), tuple(dst)]
    nodes = _graph_nodes(src, dst, rects, c)
    n = len(nodes)
    # 邻接表：O(n²) 可见性复核，按 (i,j) 升序生成 → 确定性
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if _visible(nodes[i], nodes[j], rects, c):
                w = math.hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1])
                adj[i].append((j, w))
                adj[j].append((i, w))
    return _dijkstra(nodes, adj, 0, 1)


def _shortcut(path, rects, c, rounds=3):
    """可视弦捷径（string pulling）：依序尝试跳过中间点，收敛即止。确定性。"""
    pts = list(path)
    for _ in range(rounds):
        changed = False
        i = 1
        while i < len(pts) - 1:
            if _visible(pts[i - 1], pts[i + 1], rects, c):
                del pts[i]
                changed = True
            else:
                i += 1
        if not changed:
            break
    return pts


# ── 弧线平滑（净距约束最小曲率）─────────────────────────
def _fillet(a, q, b, rects, c):
    """折角 q 处的相切圆弧。返回 None（不打弧/打不了弧）或弧参数 dict。

    G1：弧与前后段在 ta/tb 处切线连续；曲率 = 1/r 有界。
    半径确定性收缩，逐采样点复核净距 ≥ c − 0.005（弦高 ≤0.05px 量级，
    交付坐标 16px 硬门留有 c−16=1.5px 膨胀余量兜底）。
    几何边界（诚实）：凸角相切弧向障碍侧下探 r·(1/cos(θ/2)−1)，
    浅角可打大弧，直角受 1.5px 余量约束只能微圆角（r ≤ ~3.6）。
    """
    ux, uy = q[0] - a[0], q[1] - a[1]
    wx, wy = b[0] - q[0], b[1] - q[1]
    lu, lw = math.hypot(ux, uy), math.hypot(wx, wy)
    if lu < VIS_EPS or lw < VIS_EPS:
        return None
    ux, uy, wx, wy = ux / lu, uy / lu, wx / lw, wy / lw
    # 偏转角 θ = u 与 w 的夹角（θ=0 直线延续；θ=π 掉头）
    theta = math.acos(max(-1.0, min(1.0, ux * wx + uy * wy)))
    if theta < DEFLECT_SKIP or theta > math.pi - DEFLECT_SKIP:
        return None
    cos_half = math.cos(theta / 2)
    tan_half = math.tan(theta / 2)
    # 切段长 t = r·tan(θ/2)、圆心距 d = r/cos(θ/2)（圆心在折角楔形内，
    # 与前后段线相切）。半径上界 = 切段钳制与绝对上限的较小者。
    tau_max = FILLET_TAU_MAX * min(lu, lw)
    r0 = min(FILLET_R_MAX, tau_max / tan_half)
    for f in FILLET_R_SHRINK:
        r = r0 * f
        if r < 1.5:
            break
        t = min(tau_max, r * tan_half)
        r = t / tan_half
        if r < 1.5:
            continue
        # 内角平分线方向（−u 与 w 的单位和）
        bx, by = -ux + wx, -uy + wy
        lb = math.hypot(bx, by)
        if lb < VIS_EPS:
            continue
        bx, by = bx / lb, by / lb
        d = r / cos_half
        center = (q[0] + bx * d, q[1] + by * d)
        ta = (q[0] - ux * t, q[1] - uy * t)
        tb = (q[0] + wx * t, q[1] + wy * t)
        samples = _arc_samples(center, r, ta, tb)
        # 纵深防御：切向垂直度自检（ta 半径 ⊥ 入段、tb 半径 ⊥ 出段，G1 的解析条件）
        rada = (ta[0] - center[0], ta[1] - center[1])
        radb = (tb[0] - center[0], tb[1] - center[1])
        if (abs(rada[0] * ux + rada[1] * uy) > 1e-6 * r or
                abs(radb[0] * wx + radb[1] * wy) > 1e-6 * r):
            continue
        if all(pt_rect_distance(px, py, rect) >= c - 0.005
               for (px, py) in samples for rect in rects):
            cross = ((ta[0] - center[0]) * (tb[1] - center[1]) -
                     (ta[1] - center[1]) * (tb[0] - center[0]))
            return {"ta": list(ta), "tb": list(tb), "center": list(center),
                    "r": round(r, 2), "sweep": 1 if cross > 0 else 0}
    return None


def _arc_samples(center, r, ta, tb, n=ARC_SAMPLES):
    """圆弧 ta→tb 的 n+1 个采样点（沿短弧，角度插值）。"""
    a0 = math.atan2(ta[1] - center[1], ta[0] - center[0])
    a1 = math.atan2(tb[1] - center[1], tb[0] - center[0])
    da = a1 - a0
    while da > math.pi:
        da -= 2 * math.pi
    while da < -math.pi:
        da += 2 * math.pi
    return [(center[0] + r * math.cos(a0 + da * k / n),
             center[1] + r * math.sin(a0 + da * k / n)) for k in range(n + 1)]


def smooth_corners(pts, rects, c):
    """折角圆弧平滑。返回 (fillets, corner_pts)。

    fillets[i] = {"i": 角在 corner_pts 中的下标, ta/tb/center/r/sweep}。
    打不了弧的角保持尖角（净距仍由建图保证 ≥ c）。
    """
    fillets = []
    for i in range(1, len(pts) - 1):
        f = _fillet(pts[i - 1], pts[i], pts[i + 1], rects, c)
        if f:
            f["i"] = i
            fillets.append(f)
    return fillets, list(pts)


def dense_geometry(corner_pts, fillets, arc_n=ARC_SAMPLES):
    """折线 + 弧 → 密集采样点列（净距/交叉等几何复核的几何真值）。"""
    fmap = {f["i"]: f for f in fillets}
    out = [tuple(corner_pts[0])]
    for i in range(1, len(corner_pts)):
        q = tuple(corner_pts[i])
        f = fmap.get(i)
        if f:
            out.extend(tuple(p) for p in _arc_samples(f["center"], f["r"],
                                                      f["ta"], f["tb"], arc_n)[1:])
        else:
            out.append(q)
    return out


def route_svg_d(corner_pts, fillets, nd=1):
    """交付坐标 → SVG path d 串：直线段 L + 圆弧段 A（精确渲染，非折线逼近）。"""
    fmap = {f["i"]: f for f in fillets}
    r6 = lambda v: round(float(v), nd)
    parts = [f"M {r6(corner_pts[0][0])} {r6(corner_pts[0][1])}"]
    for i in range(1, len(corner_pts)):
        q = corner_pts[i]
        f = fmap.get(i)
        if f:
            # ref-scrubbed #15：带 fillet 的角点由 ta→弧→tb 替代，不得再画回
            # 角点本体（曾因 L q 无条件追加，出现 tb→q→ta_next 折返毛刺）。
            parts.append(f"L {r6(f['ta'][0])} {r6(f['ta'][1])}")
            parts.append(f"A {r6(f['r'])} {r6(f['r'])} 0 0 {f['sweep']} "
                         f"{r6(f['tb'][0])} {r6(f['tb'][1])}")
        else:
            parts.append(f"L {r6(q[0])} {r6(q[1])}")
    return " ".join(parts)


def plan_route(src, dst, rects, c):
    """高层入口：src→dst 的绕障路线（带确定性缓存——纯函数，同输入同输出）。

    ref-scrubbed 缓存命中返回**深拷贝**：调用方会把 dense 列表就地当交付
    points（midband_reanchor/fan_spread 原位改锚点），若直接返回缓存对象
    会把变异毒化进全局缓存，破坏跨 run 确定性（n20 实测 vg 路线漂移）。
    """
    key = ((round(float(src[0]), 3), round(float(src[1]), 3)),
           (round(float(dst[0]), 3), round(float(dst[1]), 3)),
           tuple((round(r[0], 3), round(r[1], 3), round(r[2], 3), round(r[3], 3))
                 for r in rects), round(float(c), 3))
    hit = _ROUTE_CACHE.get(key)
    if hit is not None:
        return {"corner_pts": [list(p) for p in hit["corner_pts"]],
                "fillets": [dict(f) for f in hit["fillets"]],
                "dense": [tuple(p) for p in hit["dense"]],
                "path_d": hit["path_d"]}
    result = _plan_route(src, dst, rects, c)
    if len(_ROUTE_CACHE) > 8192:
        _ROUTE_CACHE.clear()
    _ROUTE_CACHE[key] = result
    if result is None:
        return None
    return {"corner_pts": [list(p) for p in result["corner_pts"]],
            "fillets": [dict(f) for f in result["fillets"]],
            "dense": [tuple(p) for p in result["dense"]],
            "path_d": result["path_d"]}


_ROUTE_CACHE = {}


def _plan_route(src, dst, rects, c):
    """plan_route 实现（无缓存）。返回 dict 或 None（不可达）。"""
    src, dst = tuple(src), tuple(dst)
    path = shortest_path(src, dst, rects, c)
    if path is None:
        return None
    path = _shortcut(path, rects, c)
    fillets, corners = smooth_corners(path, rects, c)
    dense = dense_geometry(corners, fillets)
    return {"corner_pts": corners, "fillets": fillets,
            "dense": dense, "path_d": route_svg_d(corners, fillets)}
