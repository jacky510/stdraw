# -*- coding: utf-8 -*-
"""布线层（③ 线型层）：锚点规划 + 直线/弧线/绕行候选 + 避障验证。

硬门几何口径（v0.2 质量返修）：
  - 框压线 = 0：任何边任何角度都不得进入框内矩形（含 1px 余量）；
    端点只允许贴在**自家**框边（规划锚点），禁止与他框任何接触；
  - 边-框净距 ≥ CLEARANCE px（非端点框，折线/弧线采样点最小距离）；
  - 锚点平滑：边接在框边规划锚点，出发方向与框边切线夹角 ≥ ANCHOR_MIN_DEG；
  - 互环对（a↔b 双向边）必须分离为透镜形双弧（一弧一箭头），禁止两线重合；
    评分含重合惩罚（PAIR_SEP_MIN/PAIR_SEP_W），vg/绕行候选锚点切向偏移。

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

# F1 返修（2026-11-05）：互环对（a↔b 双向边）重合惩罚与透镜双弧
PAIR_SEP_MIN = 10.0    # 互环对两线最小间距目标（评分口径；DOM 硬门 4px + 舍入余量）
PAIR_SEP_W = 600.0     # 重合惩罚权重（对缺口线性；全重合 ≈6000 >> 单次交叉 40）
PAIR_VG_OFF = 12       # 互环对 vg/绕行候选的锚点切向偏移（两方向反号 → 平行走廊）
ROUND_GUARD = 0.15     # 交付舍入（0.1px）保守余量：贴边 <0.15px 判违例

# 线-线视觉重合定向重定线口径（ref-scrubbed）：random n10 扇出边经同一行间
# 走廊候选（stair/lane，y=行心±pitch/2）逐段 <1px 贴合。口径正本 = 本模块
# span_one_way_segs，证书侧 metrics._coincidence_span 两方向委托同源。
COINCIDE_THR = 1.0          # 距离 <1px 视为贴合（与证书口径同源）
COINCIDE_SPAN = 8.0         # 贴合累计 >8px 才计「视觉重合」（端点会合豁免）

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


def _pt_seg_dist(p, a, b):
    """点到线段距离（线-线贴合判定用）。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    l2 = vx * vx + vy * vy
    if l2 < EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / l2))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


def span_one_way_segs(samples, segs, step=SAMPLE_STEP, thr=COINCIDE_THR):
    """采样点列对线段集合的单向贴合跨度（px）——线-线视觉重合口径正本。

    metrics._coincidence_span（证书侧，两方向取大）委托本函数；
    路由侧候选对已定线只需 src→已定线单向（长跨度并行贴合必双向 <thr，
    端点会合瞬时接触两个方向都只给 1-2 个采样步，不越 8px 豁免门）。
    """
    total = 0.0
    for p in samples:
        dmin = float("inf")
        for s in segs:
            d = _pt_seg_dist(p, s[0], s[1])
            if d < dmin:
                dmin = d
                if dmin < thr:
                    break
        if dmin < thr:
            total += step
    return total


def quad_points(p0, ctrl, p1, n=24):
    """二次贝塞尔离散（弧线）。"""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append([u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p1[1]])
    return pts


def min_pair_dist(pts_a, pts_b, early_px=1.0):
    """两采样点列的最小点距（互环对分离度口径）。

    早退：一旦发现 < early_px 即判 0（重合惩罚封顶，不影响排序）；确定性。
    """
    best = float("inf")
    e2 = early_px * early_px
    for ax, ay in pts_a:
        for bx, by in pts_b:
            d2 = (ax - bx) ** 2 + (ay - by) ** 2
            if d2 < best:
                if d2 < e2:
                    return 0.0
                best = d2
    return math.sqrt(best) if best < float("inf") else None


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

    def __init__(self, nodes: dict, edges: list, clearance=CLEARANCE, pitch=80,
                 quality=False):
        """nodes: {id: (x,y,w,h)} 中心+尺寸；edges: [(a,b)] 有向。

        quality=False（默认）：历史候选池，输出与 v0.4.x 逐字节一致；
        quality=True：WS3-Q 布线质量返修扩充候选池（跨多行 stair）——仅在
        布局层布线硬门失败后的门控重排路径启用，不进普通布局路径。
        """
        self.N = {v: (p[0], p[1], p[2] / 2.0, p[3] / 2.0) for v, p in nodes.items()}
        self.edges = list(edges)
        self.cl = clearance
        self.pitch = pitch
        self.quality = quality
        mutual = set()
        for a, b in edges:
            if (b, a) in set(edges) and a < b:
                mutual.add((a, b))
        self.mutual = mutual
        self.eidx = {(a, b): i for i, (a, b) in enumerate(edges)}
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
        # F1 透镜双弧：互环对两方向 arc 侧别取同号（各自参考系相反 → 几何反向弧，
        # 构成透镜形；每方向一条弧一个箭头，不再出现双头箭头观感）
        mutual_side = 1 if key in self.mutual else None
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
        # F1：互环对从多组切向偏移锚点 × 两档膨胀生成 vg——同膨胀同锚的互反向
        # 最短走廊会贴同一障碍角逐点重合（0.0px），外圈膨胀（+PAIR_VG_OFF）
        # 的走廊与兄弟边天然分开 ≈ 偏移量，保住「分离且净距达标」的候选存在
        base_a, base_b = self._anchors(a, b, 0)
        rects = [n for v, n in self.N.items() if v not in (a, b)]
        if rects:
            c_vg = self.cl + VG_PAD
            anchor_sets = [(base_a, base_b)]
            if key in self.mutual:
                d = 1 if (a, b) == key else -1
                for o in (PAIR_VG_OFF * d, -PAIR_VG_OFF * d):
                    anchor_sets.append(self._offset_anchors(a, b, base_a, base_b, o))
            for sa, sb in anchor_sets:
                blocked = any(_vis.seg_rect_distance(sa, sb, rect) < c_vg - 1e-6
                              for rect in rects)
                if not blocked:
                    continue
                infls = ((c_vg, c_vg + PAIR_VG_OFF) if key in self.mutual
                         else (c_vg,))
                for c in infls:
                    route = _vis.plan_route(sa, sb, rects, c)
                    if route:
                        cands.append(("vg", route["dense"], sa, sb, route))
        # 绕行通道：行间水平车道（基锚；互环对靠重合惩罚择不同车道/膨胀圈分离）
        pa0, pb0 = base_a, base_b
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
        # WS3-Q 布线质量返修：跨多行 S 型（stair）。单 lane 候选全部压在
        # 中点行 y 上，稠密图中间行的水平连接器会把它们全部封死（实测 i04
        # N02->N03 全候选 cross≥1）。stair 走 a/b 行旁的行间走廊（y=行心
        # ±pitch/2，距卡边 18px ≥16 净距门），中段垂直在中间行所有卡的
        # 侧外 x_s 通过——结构上不进任何中间行卡带。固定变体序：侧别 ×
        # a 出口（侧锚/顶底锚 × 横向偏移），确定性。
        _ca, _cb = self.N[a], self.N[b]
        if self.quality and abs(_cb[1] - _ca[1]) > self.pitch * 1.5:
            a_top = _cb[1] > _ca[1]    # b 在 a 下方
            band = [n for v, n in self.N.items() if v not in (a, b) and
                    (_ca[1] < n[1] < _cb[1] if a_top else _cb[1] < n[1] < _ca[1])]
            y_cor_b = (bcy - self.pitch / 2) if a_top else (bcy + self.pitch / 2)
            y_cor_a = (acy + self.pitch / 2) if a_top else (acy - self.pitch / 2)
            bx3 = bcx + (bhw2 - 6)
            for s in (1, -1):
                if band:
                    x_s = (max([n[0] + n[2] for n in band] +
                               [acx + ahw2, bcx + bhw2]) + SIDE_MARGIN if s > 0
                           else min([n[0] - n[2] for n in band] +
                                    [acx - ahw2, bcx - bhw2]) - SIDE_MARGIN)
                else:
                    x_s = (max(acx + ahw2, bcx + bhw2) + SIDE_MARGIN if s > 0
                           else min(acx - ahw2, bcx - bhw2) - SIDE_MARGIN)
                # 形态 1：a 侧边水平出 → x_s 垂直 → b 旁走廊水平 → b 顶/底垂直入
                pa_s3 = [acx + s * ahw2, acy]
                # a_top（自上方进入 b）→ 入顶边（bcy−bhh）；自下方 → 入底边
                pb_s3 = [bx3, bcy + (-bhh2 if a_top else bhh2)]
                cands.append(("poly", [pa_s3, [x_s, acy], [x_s, y_cor_b],
                                       [bx3, y_cor_b], pb_s3], pa_s3, pb_s3))
                # 形态 2：a 顶/底锚垂直出 → a 旁走廊 → x_s → b 旁走廊 → b 顶/底入
                # （a 同行邻居封死侧锚水平出口时的兜底；出口横向偏移固定枚举）
                for off in (0, ahw2 - 6, -(ahw2 - 6)):
                    ex3 = acx + off
                    pa_s4 = [ex3, acy + (ahh2 if a_top else -ahh2)]
                    pb_s4 = pb_s3
                    cands.append(("poly", [pa_s4, [ex3, y_cor_a], [x_s, y_cor_a],
                                           [x_s, y_cor_b], [bx3, y_cor_b],
                                           pb_s4], pa_s4, pb_s4))
        # F1 互环对外围绕行：行间通道 = pitch − 卡高 = 36px（16+16+4），双线同
        # 通道且各自保 16px 净距时分离上限恰 4px——不可靠。不可分时从行外
        # 整体绕行：a 顶/底出框 → 全局上/下走廊 → 侧外垂直 → b 顶/底车道
        # 垂直入框（上下两个方向都试——a 的下侧出口可能被更下方邻框封死；
        # 固定变体序：方向 × off × 侧 × 外距，确定性）。
        if key in self.mutual:
            acx2, acy2, ahw3, ahh3 = self.N[a]
            bcx2, bcy2, bhw3, bhh3 = self.N[b]
            y_below = max(n[1] + n[3] for n in self.N.values()) + SIDE_MARGIN
            y_above = min(n[1] - n[3] for n in self.N.values()) - SIDE_MARGIN
            x_right = max(n[0] + n[2] for n in self.N.values())
            x_left = min(n[0] - n[2] for n in self.N.values())
            for d in ("down", "up"):
                pa_y = acy2 + ahh3 if d == "down" else acy2 - ahh3
                for entry in ("bottom", "top"):
                    if entry == "bottom":
                        pb_y = bcy2 + bhh3
                    else:
                        pb_y = bcy2 - bhh3
                    for off in (0, ahw3 - 6, -(ahw3 - 6)):
                        ex2 = acx2 + off
                        for s in (1, -1):
                            for pad in (8.0, 20.0):
                                # 走廊 y 与入框车道同按 pad 错层——兄弟边的外环
                                # 走廊/车道共用同一基线会逐段共线（sep=0）
                                if d == "down":
                                    y_out2 = y_below + pad
                                else:
                                    y_out2 = y_above - pad
                                if entry == "bottom":
                                    lane2 = bcy2 + bhh3 + 18.0 + pad
                                else:
                                    lane2 = bcy2 - bhh3 - 18.0 - pad
                                x_out2 = (x_right + SIDE_MARGIN + pad if s > 0
                                          else x_left - SIDE_MARGIN - pad)
                                bxf = bcx2 + s * (bhw3 - 6)
                                pa_w = [ex2, pa_y]
                                pb_w = [bxf, pb_y]
                                pts_w = [pa_w, [ex2, y_out2], [x_out2, y_out2],
                                         [x_out2, lane2], [bxf, lane2], pb_w]
                                cands.append(("wrap", pts_w, pa_w, pb_w))
        return cands

    # -- 候选评估 --
    def _evaluate(self, cand, a, b, routed_segs, sib_samples=None):
        """返回 (score, info)；info 含压线/净距/交叉/锚角/互环分离度明细。

        routed_segs: {j: (已定线段列表, 段包围盒列表)}（由 route_all 预算）。
        F1：互环对（a↔b）与已定线的兄弟边 (b,a) 最小间距 < PAIR_SEP_MIN 时
        线性重罚（共享端点豁免不再掩盖重合——分离度按采样点距直接量）。
        """
        kind, pts, pa, pb = cand[0], cand[1], cand[2], cand[3]
        samples = sample_polyline(pts)
        # 交付侧坐标会舍入到 0.1px（最坏把点推近框 0.07px）——路由侧判定
        # 加 ROUND_GUARD 保守余量，防止 0.0x 级贴边候选舍入后翻成违例
        press, clr_def = 0, 0.0
        min_clr = 1e9
        # WS5 性能：候选包围盒 × 节点（膨胀 PRESS_MARGIN）包围盒距离下界——
        # 下界 > ROUND_GUARD 时不可能 press；下界 ≥ 当前 min_clr 时不可能刷新
        # min_clr。两者都成立则整节点跳过（精确等价，不改变任何数值）。
        bxl = min(p[0] for p in pts)
        bxh = max(p[0] for p in pts)
        byl = min(p[1] for p in pts)
        byh = max(p[1] for p in pts)
        for v, (cx, cy, hw, hh) in self.N.items():
            if v in (a, b):
                continue
            mhw = hw + PRESS_MARGIN
            mhh = hh + PRESS_MARGIN
            gx = cx - mhw - bxh
            g = bxl - cx - mhw
            if g > gx:
                gx = g
            gy = cy - mhh - byh
            g = byl - cy - mhh
            if g > gy:
                gy = g
            if gx > ROUND_GUARD or gy > ROUND_GUARD:
                lb2 = 0.0
                if gx > 0.0:
                    lb2 = gx * gx
                if gy > 0.0:
                    lb2 += gy * gy
                if lb2 >= min_clr * min_clr:
                    continue          # 不可能 press 也不可能刷新 min_clr
            for (px, py) in samples:
                d = dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN, hh + PRESS_MARGIN)
                if d <= ROUND_GUARD:
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
                if dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN, hh + PRESS_MARGIN) <= ROUND_GUARD:
                    interior = True
                    break
            if interior:
                return (1e9, None)
        # 与已定路线交叉（逐段计数 cross + 逐边命中口径 cross_edges 供双口径核对）
        # F1 性能保真：段对先做 bbox 不相交预过滤（包围盒不相交 ⇒ 必不相交，精确等价）
        cross = 0
        hit_edges = 0
        cand_segs = list(zip(pts[:-1], pts[1:]))
        cand_bb = [(min(a[0], b[0]), min(a[1], b[1]),
                    max(a[0], b[0]), max(a[1], b[1]))
                   for a, b in cand_segs]
        for j, (rsegs, rbb) in routed_segs.items():
            hit = False
            for si, s1 in enumerate(cand_segs):
                x1l, y1l, x1h, y1h = cand_bb[si]
                for k, s2 in enumerate(rsegs):
                    x2l, y2l, x2h, y2h = rbb[k]
                    if x1l > x2h or x2l > x1h or y1l > y2h or y2l > y1h:
                        continue
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        cross += 1
                        hit = True
            if hit:
                hit_edges += 1
        length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        kind_pref = 0.0
        # F1：互环兄弟边重合惩罚（sib_samples 由 route_all 按 12px 粗采样预算好）
        mutual_pair = (min(a, b), max(a, b)) in self.mutual
        pair_sep = None
        sep_def = 0.0
        if mutual_pair and sib_samples:
            pair_sep = min_pair_dist(sample_polyline(pts, step=12), sib_samples)
            if pair_sep is not None:
                sep_def = max(0.0, PAIR_SEP_MIN - pair_sep)
        if mutual_pair and kind == "arc":
            kind_pref = -2.0      # 透镜双弧轻微优先（分离度相同时避免双直线胜出）
        # ref-scrubbed 线型层级：弧线 > 直线 > 折线——vg 绕障折角与 poly 车道
        # 折线加固定类型代价，直线/弧线可行时不再与折线抢分（折线=最后手段）
        if kind == "vg":
            kind_pref += 120.0
        if kind == "poly":
            kind_pref += 40.0
        if kind == "wrap":
            # 外围绕行固定代价：修重合（600·缺口）才值得，不与短候选抢分
            kind_pref += 200.0
        if mutual_pair:
            # F1 净距加严：分离候选不得牺牲边-框净距门（总权重 150·缺口）
            clr_def *= 5.0
        score = (4000 * press + 40 * cross + 30.0 * clr_def + 0.01 * length +
                 PAIR_SEP_W * sep_def + kind_pref)
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
                "ang_a": ang_a, "ang_b": ang_b,
                "pair_sep": round(pair_sep, 1) if pair_sep is not None else None,
                "sep_def": round(sep_def, 2)}
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

    # -- WS3-Q 布线质量返修：交叉对联合重定线 --
    def _poly_cross(self, pa, pb):
        """两条折线是否严格相交（共享端点豁免由调用方处理）。"""
        for s1 in zip(pa[:-1], pa[1:]):
            for s2 in zip(pb[:-1], pb[1:]):
                if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                    return True
        return False

    def joint_reroute(self, out, max_sweeps=3, top_k=25):
        """交叉对联合重定线：打破 pass2 坐标下降的「互为最优」僵局。

        对每个当前交叉的独立边对 (i,j)：先以「其余已定线（互斥 i/j）」
        分别预评两边的全部候选，按 (交叉数, 评分) 取各自前 top_k，再对
        组合精确联合评估（i 对 其余+cj、j 对 其余+ci），总评严格下降才
        整对替换。固定遍历序 + 固定截断，无 RNG，同图同输出。
        """
        idx = sorted(out.keys())
        for _ in range(max_sweeps):
            changed = False
            for ii in range(len(idx)):
                i = idx[ii]
                for jj in range(ii + 1, len(idx)):
                    j = idx[jj]
                    ea, eb = self.edges[i], self.edges[j]
                    if ea[0] in eb or ea[1] in eb:
                        continue
                    pi, pj = out[i]["points"], out[j]["points"]
                    if not self._poly_cross(pi, pj):
                        continue

                    def base_segs():
                        d = {}
                        for k in idx:
                            if k in (i, j):
                                continue
                            pts = out[k]["points"]
                            segs = list(zip(pts[:-1], pts[1:]))
                            bb = [(min(p[0], q[0]), min(p[1], q[1]),
                                   max(p[0], q[0]), max(p[1], q[1]))
                                  for p, q in segs]
                            d[k] = (segs, bb)
                        return d

                    a, b = self.edges[i]
                    base = base_segs()
                    li = []
                    for cand in self._candidates(ea[0], ea[1], i):
                        sc, info = self._evaluate(cand, ea[0], ea[1], base, None)
                        if info is not None:
                            li.append((info["cross"], sc, cand, info))
                    lj = []
                    c, d = self.edges[j]
                    for cand in self._candidates(c, d, j):
                        sc, info = self._evaluate(cand, c, d, base, None)
                        if info is not None:
                            lj.append((info["cross"], sc, cand, info))
                    if not li or not lj:
                        continue
                    li.sort(key=lambda t: (t[0], t[1]))
                    lj.sort(key=lambda t: (t[0], t[1]))
                    best = None
                    for ci in li[:top_k]:
                        segs_j = list(zip(ci[3]["points"][:-1], ci[3]["points"][1:]))
                        bb_j = [(min(p[0], q[0]), min(p[1], q[1]),
                                 max(p[0], q[0]), max(p[1], q[1])) for p, q in segs_j]
                        base_ij = dict(base)
                        base_ij[j] = (segs_j, bb_j)
                        for cj in lj[:top_k]:
                            segs_i = list(zip(cj[3]["points"][:-1], cj[3]["points"][1:]))
                            bb_i = [(min(p[0], q[0]), min(p[1], q[1]),
                                     max(p[0], q[0]), max(p[1], q[1])) for p, q in segs_i]
                            base_ji = dict(base)
                            base_ji[i] = (segs_i, bb_i)
                            _, info_i = self._evaluate(ci[2], ea[0], ea[1],
                                                       base_ij, None)
                            _, info_j = self._evaluate(cj[2], c, d,
                                                       base_ji, None)
                            if info_i is None or info_j is None:
                                continue
                            tot = (self._joint_score(info_i) +
                                   self._joint_score(info_j))
                            if best is None or tot < best[0]:
                                best = (tot, info_i, info_j)
                    if best is None:
                        continue
                    cur_tot = (self._joint_score(out[i]) +
                               self._joint_score(out[j]))
                    if best[0] < cur_tot - 1e-9:
                        out[i], out[j] = best[1], best[2]
                        changed = True
            if not changed:
                break
        return out

    def _joint_score(self, info):
        """联合评估用评分（与 _evaluate 同权重口径 + 锚点软拒同罚）。"""
        length = sum(math.dist(info["points"][k], info["points"][k + 1])
                     for k in range(len(info["points"]) - 1))
        clr = info.get("min_clear")
        clr_pen = (30.0 * max(0.0, self.cl - clr) if clr is not None
                   else 30.0 * self.cl)
        ang_pen = (1500.0 if min(info.get("ang_a", ANCHOR_MIN_DEG),
                                 info.get("ang_b", ANCHOR_MIN_DEG)) < ANCHOR_MIN_DEG
                   else 0.0)
        return (4000 * info.get("press", 0) + 40 * info.get("cross", 0) +
                clr_pen + ang_pen + 0.01 * length)

    # -- 线-线视觉重合定向重定线（ref-scrubbed）--
    def _pair_coincide_span(self, pts_a, pts_b):
        """两条折线的贴合跨度（px，双向取大）——与证书 _coincidence_span 同源。"""
        sa = sample_polyline(pts_a)
        sb = sample_polyline(pts_b)
        return max(span_one_way_segs(sa, list(zip(sb[:-1], sb[1:]))),
                   span_one_way_segs(sb, list(zip(sa[:-1], sa[1:]))))

    def _route_coincide_pairs(self, routes):
        """最终路线两两贴合跨度 > COINCIDE_SPAN 的边对（确定性升序）。"""
        idx = sorted(routes.keys())
        out = []
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                ia, ib = idx[a], idx[b]
                span = self._pair_coincide_span(routes[ia]["points"],
                                                routes[ib]["points"])
                if span > COINCIDE_SPAN:
                    out.append((ia, ib, span))
        return out

    def _reroute_candidates(self, a, b, i):
        """重定线候选池：历史候选池 + 锚点变体 vg 分离变体（ref-scrubbed）。

        通用化 F1 互环对分离机制：fan-in/out 兄弟边同膨胀同锚的最短路贴同
        一障碍角逐点重合——枚举 `_anchor_variants` 框边锚点位 × 切向偏移
        ±PAIR_VG_OFF 规划 vg（锚点仍在框边上，check13 渲染/核验契约不变，
        ownbox 切入由 _evaluate 的端点/框内检查天然拒收），走廊走不同障碍角
        天然分离且净距门依旧成立。只在本通道（重合定向重定线）启用，基线
        候选池零扰动。确定性枚举。
        """
        cands = list(self._candidates(a, b, i))
        rects = [n for v, n in self.N.items() if v not in (a, b)]
        if rects:
            c_vg = self.cl + VG_PAD
            for pa, pb in self._anchor_variants(a, b):
                for off in (0, PAIR_VG_OFF, -PAIR_VG_OFF):
                    sa, sb = ((pa, pb) if not off
                              else self._offset_anchors(a, b, pa, pb, off))
                    route = _vis.plan_route(sa, sb, rects, c_vg)
                    if route:
                        cands.append(("vg", route["dense"], sa, sb, route))
        return cands

    def coincide_reroute(self, routes, frozen=(), max_sweeps=3):
        """对计入线-线视觉重合的边做定向重定线（硬门不回退前提下降贴合跨度）。

        只动重合对涉及的边（frozen：构造路线/用户 waypoints 锚定的边不动；
        互环对走专用机制，本通道也不动）。替换须同时满足：压线=0、净距
        ≥clearance、锚点平滑、与其余已定线交叉边数不增、对任意其余边的
        贴合跨度严格下降（不留新贴合对）。固定遍历序 + 固定候选序，无 RNG。
        基线零重合的图（classic 全域）无受影响边——输出逐字节不变。
        """
        for _ in range(max_sweeps):
            pairs = self._route_coincide_pairs(routes)
            if not pairs:
                break
            affected = sorted({k for i, j, _s in pairs for k in (i, j)
                               if k not in frozen})
            changed = False
            for i in affected:
                a, b = self.edges[i]
                cur = routes[i]
                cands = self._reroute_candidates(a, b, i)
                base = {}       # j -> (segs, per-seg bb)（交叉判定复用）
                base_pts = {}   # j -> 折线点列
                base_pbox = {}  # j -> 全折线包围盒（贴合预过滤）
                for j, info in routes.items():
                    if j == i:
                        continue
                    pts_j = info["points"]
                    segs = list(zip(pts_j[:-1], pts_j[1:]))
                    bb = [(min(p[0], q[0]), min(p[1], q[1]),
                           max(p[0], q[0]), max(p[1], q[1])) for p, q in segs]
                    base[j] = (segs, bb)
                    base_pts[j] = pts_j
                    base_pbox[j] = (min(x[0] for x in bb), min(x[1] for x in bb),
                                    max(x[2] for x in bb), max(x[3] for x in bb))

                def span_vs_routes(samples):
                    total = 0.0
                    for j, (jl, jt, jh, jb) in base_pbox.items():
                        if (jl - samples["_h"][0] > COINCIDE_THR or
                                samples["_l"][0] - jh > COINCIDE_THR or
                                jt - samples["_h"][1] > COINCIDE_THR or
                                samples["_l"][1] - jb > COINCIDE_THR):
                            continue
                        total = max(total, span_one_way_segs(
                            samples["pts"], base[j][0]))
                    return total

                cur_samples = sample_polyline(cur["points"])
                cur_s = {"pts": cur_samples,
                         "_l": (min(p[0] for p in cur_samples),
                                min(p[1] for p in cur_samples)),
                         "_h": (max(p[0] for p in cur_samples),
                                max(p[1] for p in cur_samples))}
                cur_span = span_vs_routes(cur_s)
                cur_cross = sum(1 for pts_j in base_pts.values()
                                if self._poly_cross(cur["points"], pts_j))
                best = None
                for cand in cands:
                    sc, info = self._evaluate(cand, a, b, base, None)
                    if info is None or info.get("press", 0):
                        continue
                    mc = info.get("min_clear")
                    if mc is not None and mc < self.cl - 1e-6:
                        continue          # 硬门：边-框净距
                    if min(info.get("ang_a", 0.0), info.get("ang_b", 0.0)) \
                            < ANCHOR_MIN_DEG:
                        continue          # 硬门：锚点平滑
                    if (min(a, b), max(a, b)) in self.mutual:
                        continue          # 互环对走专用机制
                    pts_n = info["points"]
                    s_n = sample_polyline(pts_n)
                    s_ns = {"pts": s_n,
                            "_l": (min(p[0] for p in s_n),
                                   min(p[1] for p in s_n)),
                            "_h": (max(p[0] for p in s_n),
                                   max(p[1] for p in s_n))}
                    span = span_vs_routes(s_ns)
                    cross = sum(1 for pts_j in base_pts.values()
                                if self._poly_cross(pts_n, pts_j))
                    if cross > cur_cross:
                        continue          # 交叉数不增
                    key = (span, cross, sc)
                    if best is None or key < best[0]:
                        best = (key, info)
                if best is not None and best[0][0] < cur_span - 1e-9:
                    routes[i] = best[1]
                    changed = True
            if not changed:
                break
        return routes

    def _pair_cross_vs_base(self, pts, base):
        """（诊断保留）单边对其余已定线快照的交叉边数。"""
        n = 0
        for k, (segs, bb) in base.items():
            hit = False
            for s1 in zip(pts[:-1], pts[1:]):
                for s2 in segs:
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                n += 1
        return n

    # -- 主入口 --
    def route_all(self):
        """两遍路由：第一遍按序定线；第二遍对每条边以「其余边已定线」复评换优。

        两遍均确定性（固定候选序 + 固定评分），同图同输出。
        """
        routed = {}
        out = {}
        order = self.order
        # WS5 性能：routed_segs 增量维护——同一条已定线的段/包围盒只算一次
        # （旧版每条边都对全部已定线全量重建，O(m²) 重复派生；内容逐项等价）
        seg_cache = {}
        for _pass in (1, 2):
            for i in order:
                a, b = self.edges[i]
                # F1：已定线预算（段+包围盒，供交叉 bbox 预过滤）；互环兄弟边
                # (b,a) 已定线 → 另备 12px 粗采样供重合惩罚
                routed_segs = {}
                sib = None
                for j, rpts in routed.items():
                    if j == i:
                        continue
                    ent = seg_cache.get(j)
                    if ent is None:
                        segs = list(zip(rpts[:-1], rpts[1:]))
                        bb = [(min(p[0], q[0]), min(p[1], q[1]),
                               max(p[0], q[0]), max(p[1], q[1]))
                              for p, q in segs]
                        ent = (segs, bb)
                        seg_cache[j] = ent
                    routed_segs[j] = ent
                    if self.eidx.get((b, a)) == j:
                        sib = sample_polyline(rpts, step=12)
                best = None
                for cand in self._candidates(a, b, i):
                    sc, info = self._evaluate(cand, a, b, routed_segs, sib)
                    if info is not None and (best is None or sc < best[0] - EPS):
                        best = (sc, cand, info)
                if best is None:
                    cand = self._candidates(a, b, i)[0]
                    sc, info = self._evaluate(cand, a, b, routed_segs, sib)
                    best = (sc, cand,
                            info or {"kind": "line", "points": cand[1],
                                     "press": 0, "min_clear": None,
                                     "cross": 0, "cross_edges": 0,
                                     "ang_a": 0.0, "ang_b": 0.0})
                sc, cand, info = best
                routed[i] = info["points"]
                seg_cache.pop(i, None)   # 本边重定线：旧缓存作废
                out[i] = info
        return out
