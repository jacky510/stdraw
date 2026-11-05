# -*- coding: utf-8 -*-
"""布线层（③ 线型层）：锚点规划 + 直线/弧线/绕行候选 + 避障验证。

硬门几何口径（v0.2 质量返修）：
  - 框压线 = 0：任何边任何角度都不得进入框内矩形（含 1px 余量）；
    端点只允许贴在**自家**框边（规划锚点），禁止与他框任何接触；
  - 边-框净距 ≥ CLEARANCE px（非端点框，折线/弧线采样点最小距离）；
  - 锚点平滑：边接在框边规划锚点，出发方向与框边切线夹角 ≥ ANCHOR_MIN_DEG；
  - 互环对（a↔b 双向边）必须反向弧线分离，禁止两线重合。

所有候选按固定顺序枚举、按固定评分择优——无 RNG，同图同输出。
"""
import math

from . import visibility as _vis

CLEARANCE = 16          # 边-框最小净距（v0.2 硬门口径）
PRESS_MARGIN = 1        # 框压线判定余量 px
ANCHOR_MIN_DEG = 20     # 出发方向与框边切线最小夹角
SAMPLE_STEP = 4         # 候选验证采样步长 px
ARC_KS = (0.14, 0.24, 0.36, 0.55, 0.75)   # 弧线弯曲系数 × 距离
SIDE_MARGIN = 18.5                        # 侧通道与遮挡框的净距（16 + 1px 余量 + 建设余量）
VG_PAD = 1.5                              # WS3 可见性建图膨胀余量（弧线切角下探的兜底）

EPS = 1e-9


# ── 基础几何 ─────────────────────────────────────────────
def norm(vx, vy):
    d = math.hypot(vx, vy)
    return (vx / d, vy / d) if d > EPS else (0.0, 0.0)


def border_point(cx, cy, hw, hh, dx, dy):
    """从框心沿方向 (dx,dy) 与框边的交点（规划锚点）。"""
    if abs(dx) < EPS and abs(dy) < EPS:
        return [cx, cy]
    if abs(dx) < EPS:
        return [cx, cy + (hh if dy > 0 else -hh)]
    if abs(dy) < EPS:
        return [cx + (hw if dx > 0 else -hw), cy]
    t = min(hw / abs(dx), hh / abs(dy))
    return [cx + dx * t, cy + dy * t]


def dist_point_rect(px, py, cx, cy, hw, hh):
    """点到矩形的最小距离（框内为 0）。"""
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def sample_polyline(points, step=SAMPLE_STEP):
    """折线（含弧线离散）密集采样点列。"""
    out = []
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(d / step))
        for k in range(n):
            t = k / n
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    out.append(tuple(points[-1]))
    return out


def quad_points(p0, ctrl, p1, n=24):
    """二次贝塞尔离散（弧线）。"""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append([u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p1[1]])
    return pts


def seg_cross(p1, p2, p3, p4):
    """严格相交判定（含共线重叠；端点相触不算）。与 metrics 同口径。"""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < EPS else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    if d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0:
        return True
    if d1 == 0 and d2 == 0 and d3 == 0 and d4 == 0:
        def on(a, b, c):
            return (min(a[0], b[0]) - EPS <= c[0] <= max(a[0], b[0]) + EPS and
                    min(a[1], b[1]) - EPS <= c[1] <= max(a[1], b[1]) + EPS)
        if on(p3, p4, p1) or on(p3, p4, p2) or on(p1, p2, p3) or on(p1, p2, p4):
            near = [q for q in (p3, p4) for p in (p1, p2)
                    if abs(q[0] - p[0]) < EPS and abs(q[1] - p[1]) < EPS]
            return len(near) < 1
    return False


# ── 路由器 ───────────────────────────────────────────────
class Router:
    """按图上节点框位规划每条边的路线。确定性：固定候选序 + 固定评分。"""

    def __init__(self, nodes: dict, edges: list, clearance=CLEARANCE, pitch=80):
        """nodes: {id: (x,y,w,h)} 中心+尺寸；edges: [(a,b)] 有向。"""
        self.N = {v: (p[0], p[1], p[2] / 2.0, p[3] / 2.0) for v, p in nodes.items()}
        self.edges = list(edges)
        self.cl = clearance
        self.pitch = pitch
        mutual = set()
        for a, b in edges:
            if (b, a) in set(edges) and a < b:
                mutual.add((a, b))
        self.mutual = mutual
        # 路由顺序：跨行数多的先定（大跨度决定通道），其余按 (a,b)
        self.order = sorted(range(len(edges)),
                            key=lambda i: (-self._span(edges[i]), edges[i][0], edges[i][1]))

    def _span(self, e):
        ya, yb = self.N[e[0]][1], self.N[e[1]][1]
        return abs(yb - ya)

    # -- 锚点 --
    def _anchors(self, a, b, side):
        """框边规划锚点。side=0 正常；side=±1 互环对沿框边切向偏移分离。"""
        ax, ay, ahw, ahh = self.N[a]
        bx, by, bhw, bhh = self.N[b]
        dx, dy = bx - ax, by - ay
        pa = border_point(ax, ay, ahw, ahh, dx, dy)
        pb = border_point(bx, by, bhw, bhh, -dx, -dy)
        if side:
            pa, pb = self._offset_anchors(a, b, pa, pb, side)
        return pa, pb

    def _offset_anchors(self, a, b, pa, pb, off):
        """锚点沿各自框边切向偏移 off px（钳制在框边线段内，仍为框边锚点）。"""
        out = []
        for v, p, q in ((a, pa, pb), (b, pb, pa)):
            cx, cy, hw, hh = self.N[v]
            on_x = abs(abs(p[0] - cx) - hw) <= abs(abs(p[1] - cy) - hh)
            if on_x:   # 竖边：切向 (0,1)
                t = max(-hh + 3, min(hh - 3, p[1] + off - cy))
                q2 = [p[0], cy + t]
            else:      # 横边：切向 (1,0)
                t = max(-hw + 3, min(hw - 3, p[0] + off - cx))
                q2 = [cx + t, p[1]]
            out.append(q2)
        return out

    def _anchor_variants(self, a, b):
        """锚点变体：中线锚 + 沿框边 ±10/±20/±30（互环对额外反向 ±12 分离）。"""
        base = self._anchors(a, b, 0)
        variants = [base]
        key = (min(a, b), max(a, b))
        if key in self.mutual:
            for s in (1, -1):
                variants.append(self._offset_anchors(a, b, *base, s * 12))
        for off in (10, 20, 30):
            for s in (1, -1):
                variants.append(self._offset_anchors(a, b, *base, s * off))
        return variants

    # -- 候选生成 --
    def _candidates(self, a, b, idx):
        """固定顺序候选：直线 → 弧线（左右 × 弯曲系数）→ 绕行通道，× 锚点变体。"""
        cands = []
        key = (min(a, b), max(a, b))
        mutual_side = None
        if key in self.mutual:
            mutual_side = 1 if a < b else -1
        for pa, pb in self._anchor_variants(a, b):
            cands.append(("line", [pa, pb], pa, pb))
            vx, vy = pb[0] - pa[0], pb[1] - pa[1]
            dist = math.hypot(vx, vy)
            ux, uy = norm(-vy, vx)
            for k in ARC_KS:
                sides = (mutual_side,) if mutual_side else (1, -1)
                for s in sides:
                    ctrl = [(pa[0] + pb[0]) / 2 + ux * k * dist * s,
                            (pa[1] + pb[1]) / 2 + uy * k * dist * s]
                    cands.append(("arc", quad_points(pa, ctrl, pb), pa, pb, ctrl))
        # WS3 可见性图最短路候选（数学最优绕障）：直线被挡才生成（确定性）
        pa0, pb0 = self._anchors(a, b, 0)
        rects = [n for v, n in self.N.items() if v not in (a, b)]
        if rects:
            c_vg = self.cl + VG_PAD
            blocked = any(_vis.seg_rect_distance(pa0, pb0, rect) < c_vg - 1e-6
                          for rect in rects)
            if blocked:
                route = _vis.plan_route(pa0, pb0, rects, c_vg)
                if route:
                    cands.append(("vg", route["dense"], pa0, pb0, route))
        # 绕行通道：行间水平车道
        ax, ay = pa0
        bx, by = pb0
        if abs(by - ay) > 4:
            lane = (ay + by) / 2
            for off in (0, -30, 30, -60, 60, -90, 90):
                mx = (pa0[0] + pb0[0]) / 2 + off
                cands.append(("poly", [pa0, [pa0[0], lane], [mx, lane],
                                       [pb0[0], lane], pb0], pa0, pb0))
            # 侧通道（右/左）：同列中段遮挡的兜底——锚点改侧边正交出入
            acx, acy, ahw2, ahh2 = self.N[a]
            bcx, bcy, bhw2, bhh2 = self.N[b]
            lo, hi = min(acy, bcy), max(acy, bcy)
            between = [n for v, n in self.N.items() if v not in (a, b) and
                       not (n[1] + n[3] < lo or n[1] - n[3] > hi)]
            for s in (1, -1):
                if s > 0:
                    x_side = max([n[0] + n[2] for n in between] +
                                 [acx + ahw2, bcx + bhw2]) + SIDE_MARGIN
                    pa_s, pb_s = [acx + ahw2, acy], [bcx + bhw2, bcy]
                else:
                    x_side = min([n[0] - n[2] for n in between] +
                                 [acx - ahw2, bcx - bhw2]) - SIDE_MARGIN
                    pa_s, pb_s = [acx - ahw2, acy], [bcx - bhw2, bcy]
                cands.append(("poly", [pa_s, [x_side, acy], [x_side, bcy], pb_s],
                              pa_s, pb_s))
            # 行外绕行走廊：同排邻居堵死侧向出口时，从本行底/顶外绕
            acx, acy, ahw2, ahh2 = self.N[a]
            bcx, bcy, bhw2, bhh2 = self.N[b]
            all_bottom = max(n[1] + n[3] for n in self.N.values()) + SIDE_MARGIN
            all_top = min(n[1] - n[3] for n in self.N.values()) - SIDE_MARGIN
            others = [n for v, n in self.N.items() if v not in (a, b)]
            for off in (0, -24, 24):
                if a_below := (acy > bcy):
                    ex = acx + max(-(ahw2 - 6), min(ahw2 - 6, off))
                    pa_e = [ex, acy + ahh2]
                    y_out = all_bottom
                    y_mid = bcy + self.pitch / 2
                    if y_mid >= y_out - 4:
                        continue
                    side_opts = []
                    for s in (1, -1):
                        xs = (min([n[0] - n[2] for n in others] + [ex]) - SIDE_MARGIN if s < 0
                              else max([n[0] + n[2] for n in others] + [ex]) + SIDE_MARGIN)
                        side_opts.append(xs)
                else:
                    ex = acx + max(-(ahw2 - 6), min(ahw2 - 6, off))
                    pa_e = [ex, acy - ahh2]
                    y_out = all_top
                    y_mid = bcy - self.pitch / 2
                    if y_mid <= y_out + 4:
                        continue
                    side_opts = []
                    for s in (1, -1):
                        xs = (min([n[0] - n[2] for n in others] + [ex]) - SIDE_MARGIN if s < 0
                              else max([n[0] + n[2] for n in others] + [ex]) + SIDE_MARGIN)
                        side_opts.append(xs)
                for xs in side_opts:
                    bx2 = bcx + max(-(bhw2 - 6), min(bhw2 - 6, ex - bcx))
                    pb_e = [bx2, bcy - bhh2]
                    pts_e = [pa_e, [ex, y_out], [xs, y_out], [xs, y_mid],
                             [bx2, y_mid], pb_e]
                    cands.append(("poly", pts_e, pa_e, pb_e))
        return cands

    # -- 候选评估 --
    def _evaluate(self, cand, a, b, routed):
        """返回 (score, info)；info 含压线/净距/交叉/锚角明细。"""
        kind, pts, pa, pb = cand[0], cand[1], cand[2], cand[3]
        samples = sample_polyline(pts)
        press, clr_def = 0, 0.0
        min_clr = 1e9
        for v, (cx, cy, hw, hh) in self.N.items():
            if v in (a, b):
                continue
            for (px, py) in samples:
                d = dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN, hh + PRESS_MARGIN)
                if d <= 0:
                    press += 1
                    break
                min_clr = min(min_clr, d)
        clr_def = max(0.0, self.cl - min_clr) if min_clr < 1e9 else 0.0
        # 自家框：端点必须落在框边上，其余采样点不得进入框内（含 1px 余量）
        for v, endp in ((a, pa), (b, pb)):
            cx, cy, hw, hh = self.N[v]
            if dist_point_rect(endp[0], endp[1], cx, cy, hw, hh) > 0.75:
                return (1e9, None)
            interior = False
            for (px, py) in samples[1:-1]:
                if dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN, hh + PRESS_MARGIN) <= 0:
                    interior = True
                    break
            if interior:
                return (1e9, None)
        # 与已定路线交叉（逐段计数 cross + 逐边命中口径 cross_edges 供双口径核对）
        cross = 0
        hit_edges = 0
        segs = list(zip(pts[:-1], pts[1:]))
        for j, rpts in routed.items():
            rsegs = list(zip(rpts[:-1], rpts[1:]))
            hit = False
            for s1 in segs:
                for s2 in rsegs:
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        cross += 1
                        hit = True
            if hit:
                hit_edges += 1
        length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        kind_pref = 0.0
        score = 4000 * press + 40 * cross + 30.0 * clr_def + 0.01 * length + kind_pref
        # 锚点平滑：出发/进入方向与框边切线夹角
        ang_a = self._anchor_angle(a, pa, pts[0], pts[1])
        ang_b = self._anchor_angle(b, pb, pts[-1], pts[-2])
        ang_def = max(0.0, ANCHOR_MIN_DEG - ang_a) + max(0.0, ANCHOR_MIN_DEG - ang_b)
        score += 2.0 * ang_def
        if ang_def > 0.5:
            score += 1500.0     # 切线出锚软拒：存在平滑候选时不选它（硬门保平滑）
        info = {"kind": kind, "points": pts, "press": press,
                "min_clear": round(min_clr, 1) if min_clr < 1e9 else None,
                "cross": cross, "cross_edges": hit_edges,
                "ang_a": round(ang_a, 1), "ang_b": round(ang_b, 1)}
        if kind == "arc":
            info["ctrl"] = cand[4]
        if kind == "vg":
            info["vg_corners"] = [list(p) for p in cand[4]["corner_pts"]]
            info["vg_fillets"] = cand[4]["fillets"]
        return (score, info)

    def _anchor_angle(self, v, anchor, p_in, p_out):
        """锚点处路线方向与框边切线的夹角（度）。"""
        cx, cy, hw, hh = self.N[v]
        dx, dy = norm(p_out[0] - p_in[0], p_out[1] - p_in[1])
        on_x = abs(abs(anchor[0] - cx) - hw) < abs(abs(anchor[1] - cy) - hh)
        # 框边切线：竖边 → (0,1)；横边 → (1,0)
        tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
        c = abs(dx * tx + dy * ty)
        return math.degrees(math.acos(max(0.0, min(1.0, c))))

    # -- WS3 双口径·理论口径 --
    def final_crossing_pairs(self, out):
        """最终路线（未取整浮点几何）的交叉边对数。

        评估时的逐边计数含「对旧路线快照」的陈旧交叉，不能当理论口径；
        本方法在 route_all 收尾后对最终路线两两复算（严格求交，共享端点除外）。
        """
        items = sorted(out.items())
        total = 0
        for a in range(len(items)):
            ia, info_a = items[a]
            ea = self.edges[ia]
            for b in range(a + 1, len(items)):
                ib, info_b = items[b]
                eb = self.edges[ib]
                if ea[0] in eb or ea[1] in eb:
                    continue
                pa, pb = info_a["points"], info_b["points"]
                hit = False
                for s1 in zip(pa[:-1], pa[1:]):
                    for s2 in zip(pb[:-1], pb[1:]):
                        if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    total += 1
        return total

    # -- 主入口 --
    def route_all(self):
        """两遍路由：第一遍按序定线；第二遍对每条边以「其余边已定线」复评换优。

        两遍均确定性（固定候选序 + 固定评分），同图同输出。
        """
        routed = {}
        out = {}
        order = self.order
        for _pass in (1, 2):
            for i in order:
                a, b = self.edges[i]
                others = {j: pts for j, pts in routed.items() if j != i}
                best = None
                for cand in self._candidates(a, b, i):
                    sc, info = self._evaluate(cand, a, b, others)
                    if info is not None and (best is None or sc < best[0] - EPS):
                        best = (sc, cand, info)
                if best is None:
                    cand = self._candidates(a, b, i)[0]
                    sc, info = self._evaluate(cand, a, b, others)
                    best = (sc, cand,
                            info or {"kind": "line", "points": cand[1],
                                     "press": 0, "min_clear": None,
                                     "cross": 0, "cross_edges": 0,
                                     "ang_a": 0.0, "ang_b": 0.0})
                sc, cand, info = best
                routed[i] = info["points"]
                out[i] = info
        return out
