# -*- coding: utf-8 -*-
"""Routing layer (line-style layer 3): anchor planning + straight/arc/detour candidates + obstacle-avoidance validation.

Hard-gate geometric accounting (v0.2 quality rework):
    - box press = 0: no edge at any angle may enter the interior rectangle of a box (incl. 1px margin);
        endpoints may only attach to the **own** box border (planned anchors); any contact with other boxes is forbidden;
    - edge-box clearance >= CLEARANCE px (non-endpoint boxes; minimum distance over polyline/arc sample points);
    - anchor smoothness: the edge attaches at a planned anchor on the box border; the departure direction vs the border tangent must form an angle >= ANCHOR_MIN_DEG;
    - mutual pairs (a<->b bidirectional edges) must separate into a lens-shaped pair of arcs (one arc one arrow); the two lines coinciding is forbidden;
        scoring includes a coincidence penalty (PAIR_SEP_MIN/PAIR_SEP_W); vg/detour candidates use tangential anchor offsets.

All candidates are enumerated in fixed order and picked by fixed scoring -- no RNG, same graph yields same output.
"""
import math

from . import visibility as _vis

CLEARANCE = 16          # minimum edge-box clearance (v0.2 hard-gate accounting)
PRESS_MARGIN = 1        # box-press detection margin px
ANCHOR_MIN_DEG = 20     # minimum angle between the departure direction and the box-border tangent
SAMPLE_STEP = 4         # candidate validation sampling step px
ARC_KS = (0.14, 0.24, 0.36, 0.55, 0.75)   # arc curvature coefficient x distance (enumeration ladder)
ARC_BULGE_BASE = 6.0    # ref-scrubbed arc-curvature parameterization: minimum bulge px (small bends for short edges)
ARC_BULGE_SLOPE = 0.06  # bulge grows linearly with chord length (typical chord 130px -> k~=0.21 ~= the old-look tier)
ARC_BULGE_MAX = 40.0    # bulge cap for long edges
ARC_K_MIN = 0.12
ARC_K_MAX = 0.50


def adaptive_arc_k(dist):
    """Chord-length-adaptive arc curvature coefficient (ref-scrubbed aesthetics v3).

        Bulge (half the ctrl offset at t=0.5) = min(8 + 0.12*chord, 40) px: gentle bends for short edges,
        capped for long ones; k = 2*bulge/chord, clamped to [0.12, 0.50]. The first arc candidate tier uses this value
        (the ladder is kept as a feasibility fallback); arc-curvature consistency within a loop is achieved by constructed arcs uniformly taking the median chord tier.
    """
    bulge = min(ARC_BULGE_BASE + ARC_BULGE_SLOPE * dist, ARC_BULGE_MAX)
    k = 2.0 * bulge / max(dist, 1e-6)
    return max(ARC_K_MIN, min(ARC_K_MAX, k))


SIDE_MARGIN = 18.5                        # clearance between side channels and occluding boxes (16 + 1px margin + construction allowance)
VG_PAD = 1.5                              # WS3 visibility-graph build inflation allowance (fallback for the arc tangent-angle dip)

# F1 rework (2026-11-05): coincidence penalty and lens double-arc for mutual pairs (a<->b bidirectional edges)
PAIR_SEP_MIN = 10.0    # target minimum spacing between the two lines of a mutual pair (scoring accounting; DOM hard gate 4px + rounding margin)
PAIR_SEP_W = 600.0     # coincidence penalty weight (linear in the gap; full coincidence ~6000 >> single crossing 40)
PAIR_VG_OFF = 12       # tangential anchor offset for mutual-pair vg/detour candidates (opposite signs for the two directions -> parallel corridors)
ROUND_GUARD = 0.15     # conservative margin for delivery rounding (0.1px): border-hugging within <0.15px counts as a violation

# Line-line visual-coincidence targeted re-routing accounting (ref-scrubbed): the random n10 fan-out edges run through the same
# inter-row corridor candidates (stair/lane, y = row center +/- pitch/2) with per-segment <1px adherence. The authoritative accounting = this
# module's span_one_way_segs; the certificate side's metrics._coincidence_span delegates both directions to the same source.
COINCIDE_THR = 1.0          # distance <1px counts as adherence (same source as the certificate accounting)
COINCIDE_SPAN = 8.0         # accumulated adherence must exceed 8px to count as "visual coincidence" (endpoint meeting exempted)
FAN_STEP = 18.0             # uniform spread step for multiple anchors on the same node side (ref-scrubbed rule 3)
REANCHOR_STEP = 4.0         # ref-scrubbed midband_reanchor ladder-clamping step

EPS = 1e-9


# -- basic geometry ----------------------------------------------------
def norm(vx, vy):
    d = math.hypot(vx, vy)
    return (vx / d, vy / d) if d > EPS else (0.0, 0.0)


def border_point(cx, cy, hw, hh, dx, dy):
    """Intersection of the ray from the box center in direction (dx,dy) with the box border (planned anchor).

        ref-scrubbed layered accounting: the routing decision layer keeps the legacy exit geometry (candidate coverage unchanged, WS3 hard cases
        stay stable); the **delivery layer** has Router.midband_reanchor clamp anchors into the edge-midpoint +/- 1/4
        edge-length band (corners excluded, per-edge hard-gate recheck) -- see docs/layout-modes.md for the connection-point accounting.
    """
    if abs(dx) < EPS and abs(dy) < EPS:
        return [cx, cy]
    if abs(dx) < EPS:
        return [cx, cy + (hh if dy > 0 else -hh)]
    if abs(dy) < EPS:
        return [cx + (hw if dx > 0 else -hw), cy]
    t = min(hw / abs(dx), hh / abs(dy))
    return [cx + dx * t, cy + dy * t]


def dist_point_rect(px, py, cx, cy, hw, hh):
    """Minimum distance from a point to a rectangle (0 when inside)."""
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def sample_polyline(points, step=SAMPLE_STEP):
    """Densely sampled point sequence of a polyline (including arc discretization)."""
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
    """Distance from a point to a segment (for line-line adherence tests)."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    l2 = vx * vx + vy * vy
    if l2 < EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / l2))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


def span_one_way_segs(samples, segs, step=SAMPLE_STEP, thr=COINCIDE_THR):
    """One-way adherence span (px) of a sampled point sequence against a segment set -- the authoritative line-line visual-coincidence accounting.

        metrics._coincidence_span (certificate side, takes the max over both directions) delegates to this function;
        on the routing side a candidate vs an already-routed line only needs the src->routed one-way direction (long-span parallel adherence is necessarily <thr both ways,
        and endpoint-meeting momentary contact yields only 1-2 sample steps in either direction, never crossing the 8px exemption gate).
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
    """Quadratic Bezier discretization (arcs)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append([u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p1[1]])
    return pts


def min_pair_dist(pts_a, pts_b, early_px=1.0):
    """Minimum point distance between two sampled point sequences (mutual-pair separation accounting).

        Early exit: once a pair < early_px is found, report 0 (coincidence penalty capped, ranking unaffected); deterministic.
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
    """Strict intersection test (includes collinear overlap; endpoint touching does not count). Same accounting as metrics."""
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


# -- router ------------------------------------------------------------
class Router:
    """Plan a route for each edge from the node box positions on the canvas. Deterministic: fixed candidate order + fixed scoring."""

    def __init__(self, nodes: dict, edges: list, clearance=CLEARANCE, pitch=80,
                 quality=False):
        """nodes: {id: (x,y,w,h)} center + size; edges: [(a,b)] directed.

            quality=False (default): the legacy candidate pool, output byte-for-byte identical to v0.4.x;
            quality=True: WS3-Q routing-quality rework extends the candidate pool (multi-row stair) -- enabled only on
            the gated re-layout path after the layout-layer routing hard gate fails; never enters the normal layout path.
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
        # Routing order: edges spanning more rows are routed first (large spans decide the corridors), the rest by (a,b)
        self.order = sorted(range(len(edges)),
                            key=lambda i: (-self._span(edges[i]), edges[i][0], edges[i][1]))

    def _span(self, e):
        ya, yb = self.N[e[0]][1], self.N[e[1]][1]
        return abs(yb - ya)

    # -- anchors --
    def _band_clamp_pt(self, v, p):
        """ref-scrubbed anchor accounting: mutual-pair candidate anchors clamped into the edge-midpoint +/- 1/4 band.

                Only when departing from in-band anchors does the delivery-layer midband_reanchor have nothing out-of-band left to clamp --
                out-of-band anchors, once delivery-clamped, tend to send the arc tangent stabbing into the box and trigger a press fallback (classic-cld
                crowding<->quickfix measured: anchors falling back out-of-band = the root cause of the second-review rejection).
                Called only in the mutual-pair candidate layer; the decision-layer exit geometry of non-mutual edges is unchanged (zero drift).
        """
        cx, cy, hw, hh = self.N[v]
        on_x = abs(abs(p[0] - cx) - hw) <= abs(abs(p[1] - cy) - hh)
        if on_x:
            lim = hh / 2
            return [p[0], cy + max(-lim, min(lim, p[1] - cy))]
        lim = hw / 2
        return [cx + max(-lim, min(lim, p[0] - cx)), p[1]]

    def _anchors(self, a, b, side):
        """Planned anchors on box borders. side=0 is normal; side=+/-1 separates mutual pairs by tangential offset along the border."""
        ax, ay, ahw, ahh = self.N[a]
        bx, by, bhw, bhh = self.N[b]
        dx, dy = bx - ax, by - ay
        pa = border_point(ax, ay, ahw, ahh, dx, dy)
        pb = border_point(bx, by, bhw, bhh, -dx, -dy)
        if side:
            pa, pb = self._offset_anchors(a, b, pa, pb, side)
        return pa, pb

    def _offset_anchors(self, a, b, pa, pb, off):
        """Offset anchors by off px along each box's own border tangent (clamped inside the border segment, still border anchors)."""
        out = []
        for v, p, q in ((a, pa, pb), (b, pb, pa)):
            cx, cy, hw, hh = self.N[v]
            on_x = abs(abs(p[0] - cx) - hw) <= abs(abs(p[1] - cy) - hh)
            if on_x:   # vertical edge: tangent (0,1)
                t = max(-hh + 3, min(hh - 3, p[1] + off - cy))
                q2 = [p[0], cy + t]
            else:      # horizontal edge: tangent (1,0)
                t = max(-hw + 3, min(hw - 3, p[0] + off - cx))
                q2 = [cx + t, p[1]]
            out.append(q2)
        return out

    def _anchor_variants(self, a, b):
        """Anchor variants: midline anchors + +/-10/+/-20/+/-30 along the border (mutual pairs add opposite +/-12 separation)."""
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

    def _band_anchor_variants(self, a, b):
        """ref-scrubbed in-band anchor variants (only as the fallback for mutual-pair local re-routing).

                All variants (midline + +/-12 separation + +/-10/20/+/-30 exploration) are pulled into the edge-midpoint
                +/- 1/4 band via _band_clamp_pt. Not in the regular candidate pool -- the decision-layer legacy exit geometry stays unchanged
                (zero drift on the other 18 graphs); enabled only in the mutual-pair local re-routing after delivery-layer midband_reanchor
                clamping fails -- the classic classic-cld lens double-arc being exactly this case.
        """
        base = self._anchors(a, b, 0)
        variants = [(self._band_clamp_pt(a, base[0]),
                     self._band_clamp_pt(b, base[1]))]
        for off in (12, 10, 20, 30):
            for s in (1, -1):
                pa, pb = self._offset_anchors(a, b, *base, s * off)
                variants.append((self._band_clamp_pt(a, pa),
                                 self._band_clamp_pt(b, pb)))
        return variants

    # -- candidate generation --
    def _candidates(self, a, b, idx):
        """Fixed-order candidates: straight -> arc (left/right x curvature) -> detour channels, x anchor variants."""
        cands = []
        key = (min(a, b), max(a, b))
        # F1 lens double-arc: both directions of a mutual pair take the same arc side sign (their reference frames are opposite -> geometrically opposite arcs,
        # forming a lens; one arc one arrow per direction, no more double-headed-arrow look)
        mutual_side = 1 if key in self.mutual else None
        for pa, pb in self._anchor_variants(a, b):
            cands.append(("line", [pa, pb], pa, pb))
            vx, vy = pb[0] - pa[0], pb[1] - pa[1]
            dist = math.hypot(vx, vy)
            ux, uy = norm(-vy, vx)
            # ref-scrubbed arc-curvature parameterization: first tier = chord-adaptive k (small bends for short edges,
            # capped for long ones), the ladder kept as a feasibility fallback; order-preserving dedupe, determinism unchanged
            ks = tuple(dict.fromkeys((adaptive_arc_k(dist),) + ARC_KS))
            for k in ks:
                sides = (mutual_side,) if mutual_side else (1, -1)
                for s in sides:
                    ctrl = [(pa[0] + pb[0]) / 2 + ux * k * dist * s,
                            (pa[1] + pb[1]) / 2 + uy * k * dist * s]
                    cands.append(("arc", quad_points(pa, ctrl, pb), pa, pb, ctrl))
        # WS3 visibility-graph shortest-path candidates (mathematically optimal obstacle avoidance): generated only when the straight line is blocked (deterministic)
        # F1: mutual pairs build vg from several tangentially offset anchor sets x two inflation tiers -- mutually opposite shortest
        # corridors with the same inflation and same anchors hug the same obstacle corner and coincide point-by-point (0.0px), while the outer-ring
        # inflation (+PAIR_VG_OFF) corridor separates from the sibling edge by ~= the offset, preserving a "separated and clearance-compliant" candidate
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
        # Detour channels: horizontal inter-row lanes (base anchors; mutual pairs separate by picking different lanes/inflation rings via the coincidence penalty)
        pa0, pb0 = base_a, base_b
        ax, ay = pa0
        bx, by = pb0
        if abs(by - ay) > 4:
            lane = (ay + by) / 2
            for off in (0, -30, 30, -60, 60, -90, 90):
                mx = (pa0[0] + pb0[0]) / 2 + off
                cands.append(("poly", [pa0, [pa0[0], lane], [mx, lane],
                                       [pb0[0], lane], pb0], pa0, pb0))
            # Side channels (right/left): fallback for mid-column occlusion in the same column -- anchors switch to orthogonal side entry/exit
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
            # Out-of-row detour corridor: when same-row neighbors seal the side exits, detour outside via the bottom/top of this row
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
        # WS3-Q routing-quality rework: multi-row S-shape (stair). Single-lane candidates all sit on the midpoint row y;
        # horizontal connectors in the middle rows of dense graphs seal them all off (measured: i04 N02->N03 has cross>=1 on
        # every candidate). The stair runs in the inter-row corridors beside the a/b rows (y = row center +/- pitch/2, 18px from card
        # edges >= the 16px clearance gate); its mid vertical passes outside the side x_s of every card in the middle rows --
        # structurally it never enters any middle-row card band. Fixed variant order: side x
        # a exit (side anchor / top-bottom anchor x lateral offset), deterministic.
        _ca, _cb = self.N[a], self.N[b]
        if self.quality and abs(_cb[1] - _ca[1]) > self.pitch * 1.5:
            a_top = _cb[1] > _ca[1]    # b is below a
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
                # Shape 1: a exits horizontally from its side -> vertical at x_s -> horizontal in the corridor beside b -> b enters vertically at top/bottom
                pa_s3 = [acx + s * ahw2, acy]
                # a_top (entering b from above) -> enter the top border (bcy-bhh); from below -> enter the bottom border
                pb_s3 = [bx3, bcy + (-bhh2 if a_top else bhh2)]
                cands.append(("poly", [pa_s3, [x_s, acy], [x_s, y_cor_b],
                                       [bx3, y_cor_b], pb_s3], pa_s3, pb_s3))
                # Shape 2: a exits vertically from a top/bottom anchor -> corridor beside a -> x_s -> corridor beside b -> b enters at top/bottom
                # (fallback when a's same-row neighbors seal the side anchor's horizontal exit; exit lateral offsets are a fixed enumeration)
                for off in (0, ahw2 - 6, -(ahw2 - 6)):
                    ex3 = acx + off
                    pa_s4 = [ex3, acy + (ahh2 if a_top else -ahh2)]
                    pb_s4 = pb_s3
                    cands.append(("poly", [pa_s4, [ex3, y_cor_a], [x_s, y_cor_a],
                                           [x_s, y_cor_b], [bx3, y_cor_b],
                                           pb_s4], pa_s4, pb_s4))
        # F1 mutual-pair outer detour: the inter-row channel = pitch - card height = 36px (16+16+4); with both lines in the same channel
        # each keeping 16px clearance, the separation ceiling is exactly 4px -- unreliable. When they cannot separate, detour wholesale
        # outside the rows: a exits its box at top/bottom -> global upper/lower corridor -> vertical outside the sides -> b enters
        # its box vertically via a top/bottom lane (both up and down directions are tried -- a's lower exit may be sealed by a box
        # further below; fixed variant order: direction x off x side x outer distance, deterministic).
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
                                # The corridor y and the box-entry lane are staggered by the same pad -- the sibling edge's outer-ring
                                # corridor/lane sharing the same baseline would end up collinear segment by segment (sep=0)
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

    # -- candidate evaluation --
    def _evaluate(self, cand, a, b, routed_segs, sib_samples=None):
        """Return (score, info); info carries press/clearance/crossing/anchor-angle/mutual-separation details.

                routed_segs: {j: (list of routed segments, list of per-segment bboxes)} (precomputed by route_all).
                F1: when the minimum spacing between a mutual pair (a<->b) and its already-routed sibling edge (b,a) is < PAIR_SEP_MIN,
                apply a heavy linear penalty (the shared-endpoint exemption no longer masks coincidence -- separation is measured directly on sampled point distances).
        """
        kind, pts, pa, pb = cand[0], cand[1], cand[2], cand[3]
        samples = sample_polyline(pts)
        # Delivery-side coordinates are rounded to 0.1px (worst case pushing a point 0.07px closer to a box) -- routing-side
        # checks add the ROUND_GUARD conservative margin to keep 0.0x-level border-hugging candidates from flipping into violations after rounding
        press, clr_def = 0, 0.0
        min_clr = 1e9
        # WS5 performance: lower bound on the distance between the candidate bbox and each node's (PRESS_MARGIN-inflated) bbox --
        # if the lower bound > ROUND_GUARD, press is impossible; if it >= the current min_clr, min_clr cannot be
        # refreshed. When both hold the whole node is skipped (exactly equivalent, changes no value).
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
                    continue          # press impossible, min_clr not refreshable
            for (px, py) in samples:
                d = dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN, hh + PRESS_MARGIN)
                if d <= ROUND_GUARD:
                    press += 1
                    break
                min_clr = min(min_clr, d)
        clr_def = max(0.0, self.cl - min_clr) if min_clr < 1e9 else 0.0
        # Own box: endpoints must land on the box border; all other sample points must stay out of the box interior (incl. 1px margin)
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
        # Crossings against already-routed routes (per-segment count cross + per-edge hit accounting cross_edges for the dual-accounting cross-check)
        # F1 performance fidelity: segment pairs go through a bbox-disjoint pre-filter first (disjoint bboxes => no intersection possible, exactly equivalent)
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
        # F1: mutual-pair sibling-edge coincidence penalty (sib_samples precomputed by route_all at 12px coarse sampling)
        mutual_pair = (min(a, b), max(a, b)) in self.mutual
        pair_sep = None
        sep_def = 0.0
        if mutual_pair and sib_samples:
            pair_sep = min_pair_dist(sample_polyline(pts, step=12), sib_samples)
            if pair_sep is not None:
                sep_def = max(0.0, PAIR_SEP_MIN - pair_sep)
        if mutual_pair and kind == "arc":
            kind_pref = -2.0      # slight preference for the lens double-arc (avoids double straight lines winning on separation ties)
        # ref-scrubbed line-style hierarchy: arc > straight > polyline -- vg obstacle-avoidance bends and poly lane
        # polylines carry a fixed type cost, so when straight/arc are feasible they no longer compete with polylines on score (polyline = last resort)
        if kind == "vg":
            kind_pref += 120.0
        if kind == "poly":
            kind_pref += 40.0
        if kind == "wrap":
            # Fixed cost for the outer detour: only worth it to fix coincidence (600*gap), does not compete with short candidates on score
            kind_pref += 200.0
        if mutual_pair:
            # F1 tightened clearance: separation candidates must not sacrifice the edge-box clearance gate (total weight 150*gap)
            clr_def *= 5.0
        score = (4000 * press + 40 * cross + 30.0 * clr_def + 0.01 * length +
                 PAIR_SEP_W * sep_def + kind_pref)
        # Anchor smoothness: angle between the departure/entry direction and the box-border tangent
        ang_a = self._anchor_angle(a, pa, pts[0], pts[1])
        ang_b = self._anchor_angle(b, pb, pts[-1], pts[-2])
        ang_def = max(0.0, ANCHOR_MIN_DEG - ang_a) + max(0.0, ANCHOR_MIN_DEG - ang_b)
        score += 2.0 * ang_def
        if ang_def > 0.5:
            score += 1500.0     # soft rejection of tangent-anchor exits: not chosen when a smooth candidate exists (the hard gate preserves smoothness)
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
        """Angle (degrees) between the route direction at the anchor and the box-border tangent."""
        cx, cy, hw, hh = self.N[v]
        dx, dy = norm(p_out[0] - p_in[0], p_out[1] - p_in[1])
        on_x = abs(abs(anchor[0] - cx) - hw) < abs(abs(anchor[1] - cy) - hh)
        # Box-border tangent: vertical edge -> (0,1); horizontal edge -> (1,0)
        tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
        c = abs(dx * tx + dy * ty)
        return math.degrees(math.acos(max(0.0, min(1.0, c))))

    # -- WS3 dual accounting: theoretical accounting --
    def final_crossing_pairs(self, out):
        """Number of crossing edge pairs among the final routes (unrounded float geometry).

                The per-edge counts taken during evaluation include stale crossings against old route snapshots and cannot serve as the
                theoretical accounting; this method recomputes all pairs over the final routes after route_all finishes (strict intersection, shared endpoints excluded).
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

    # -- WS3-Q routing-quality rework: joint re-routing of crossing pairs --
    def _poly_cross(self, pa, pb):
        """Whether two polylines strictly intersect (the shared-endpoint exemption is handled by the caller)."""
        for s1 in zip(pa[:-1], pa[1:]):
            for s2 in zip(pb[:-1], pb[1:]):
                if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                    return True
        return False

    def joint_reroute(self, out, max_sweeps=3, top_k=25):
        """Joint re-routing of crossing pairs: breaks the "each is the other's optimum" deadlock of pass2 coordinate descent.

                For each currently crossing independent edge pair (i,j): first, against "the other routed lines (excluding i/j)",
                pre-evaluate all candidates of both sides separately, take each side's top top_k by (crossing count, score), then
                evaluate the combinations jointly and exactly (i vs rest+cj, j vs rest+ci); the whole pair is replaced only
                if the total score strictly decreases. Fixed traversal order + fixed truncation, no RNG, same graph yields same output.
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
        """Score for joint evaluation (same weight accounting as _evaluate + the same anchor soft-rejection penalty)."""
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

    # -- Line-line visual-coincidence targeted re-routing (ref-scrubbed) --
    def _pair_coincide_span(self, pts_a, pts_b):
        """Adherence span (px) between two polylines, max over both directions -- same source as the certificate's _coincidence_span."""
        sa = sample_polyline(pts_a)
        sb = sample_polyline(pts_b)
        return max(span_one_way_segs(sa, list(zip(sb[:-1], sb[1:]))),
                   span_one_way_segs(sb, list(zip(sa[:-1], sa[1:]))))

    def _route_coincide_pairs(self, routes):
        """Edge pairs among the final routes whose adherence span exceeds COINCIDE_SPAN (deterministic ascending order)."""
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
        """Re-routing candidate pool: the legacy pool + anchor-variant vg separation variants (ref-scrubbed).

                Generalizes the F1 mutual-pair separation mechanism: fan-in/out sibling edges with the same inflation and same anchors have shortest
                paths hugging the same obstacle corner and coinciding point-by-point -- enumerate `_anchor_variants` border anchor positions x
                tangential offsets of +/-PAIR_VG_OFF to plan vg (anchors stay on the box border, so the check13 render/verification contract is
                unchanged, and own-box cut-ins are naturally rejected by _evaluate's endpoint/interior checks); corridors passing different
                obstacle corners separate naturally with the clearance gate still holding. Enabled only in this channel (coincidence targeted
                re-routing); the baseline candidate pool is untouched. Deterministic enumeration.
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
        """Targeted re-routing of edges counted as line-line visual coincidence (reduce adherence spans without regressing any hard gate).

                Only edges involved in coincidence pairs are touched (frozen: edges anchored by constructed routes / user waypoints stay put;
                mutual pairs go through their dedicated mechanism and are untouched here too). A replacement must satisfy all of: press=0,
                clearance >= clearance, anchor smoothness, no increase in crossing-edge count against the other routed lines, and a strictly
                decreasing adherence span against every other edge (leaving no new adherence pairs). Fixed traversal order + fixed candidate order, no RNG.
                Graphs with zero baseline coincidence (the whole classic domain) have no affected edges -- output byte-for-byte unchanged.
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
                base = {}       # j -> (segs, per-seg bb) (reused for crossing checks)
                base_pts = {}   # j -> polyline point sequence
                base_pbox = {}  # j -> whole-polyline bbox (adherence pre-filter)
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
                        continue          # hard gate: edge-box clearance
                    if min(info.get("ang_a", 0.0), info.get("ang_b", 0.0)) \
                            < ANCHOR_MIN_DEG:
                        continue          # hard gate: anchor smoothness
                    if (min(a, b), max(a, b)) in self.mutual:
                        continue          # mutual pairs go through their dedicated mechanism
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
                        continue          # crossing count must not increase
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
        """(kept for diagnostics) Crossing-edge count of one edge against a snapshot of the other routed lines."""
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

    # -- Uniform spread of multiple anchors on the same node side (ref-scrubbed connection-point accounting rule 3) --
    def _side_of(self, v, p):
        """Which border (r/l/b/t) of node v's box anchor p sits on."""
        cx, cy, hw, hh = self.N[v]
        on_x = abs(abs(p[0] - cx) - hw) <= abs(abs(p[1] - cy) - hh)
        if on_x:
            return "r" if p[0] > cx else "l"
        return "b" if p[1] > cy else "t"

    def _edge_stats(self, i, routes):
        """Hard-gate summary of edge i's current route: (press, min_clear, ang_min, cross, mutual_sep)."""
        a, b = self.edges[i]
        pts = routes[i]["points"]
        samples = sample_polyline(pts)
        press, min_clr = 0, None
        for v, (cx, cy, hw, hh) in self.N.items():
            if v in (a, b):
                continue
            for (px, py) in samples:
                d = dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN,
                                    hh + PRESS_MARGIN)
                if d <= ROUND_GUARD:
                    press += 1
                    break
                min_clr = d if min_clr is None else min(min_clr, d)
        ang_min = min(self._anchor_angle(a, pts[0], pts[0], pts[1]),
                      self._anchor_angle(b, pts[-1], pts[-1], pts[-2]))
        cross = 0
        for j, o in routes.items():
            if j == i or self.edges[j][0] in self.edges[i] or \
                    self.edges[j][1] in self.edges[i]:
                continue
            if self._poly_cross(pts, o["points"]):
                cross += 1
        msep = None
        j = self.eidx.get((b, a))
        if j is not None and j in routes and j != i:
            msep = min_pair_dist(sample_polyline(pts, step=4),
                                 sample_polyline(routes[j]["points"], step=4))
        return (press, min_clr, ang_min, cross, msep)

    def fan_spread(self, routes, frozen=()):
        """Same node side with >= 2 anchors: sort by incidence angle and spread symmetrically on both sides of the midpoint along the border tangent.

                2026-11-06 connection-point accounting hard rule 3 (jacky): multiple outgoing lines on the same node must not pile up at the
                same border midpoint -- spread uniformly with step FAN_STEP, clamped inside the border at +/-(half-3). After spreading, every
                edge rechecks the hard gates (press/clearance/anchor angle/no crossing increase/mutual separation >= 4px); on any violation
                the whole node falls back to border-midpoint anchors (deterministic: fixed traversal order + fixed step, no RNG).
                frozen edges (constructed routes / user waypoints) are untouched.
        """
        groups = {}
        for i in sorted(routes.keys()):
            if i in frozen:
                continue
            pts = routes[i]["points"]
            a, b = self.edges[i]
            for end, p in (("a", pts[0]), ("b", pts[-1])):
                v = a if end == "a" else b
                groups.setdefault((v, self._side_of(v, p)), []).append(
                    (i, end, tuple(p)))
        for (v, side), entries in sorted(groups.items()):
            if len(entries) < 2:
                continue
            cx, cy, hw, hh = self.N[v]
            vertical = side in ("r", "l")
            half_len = (hh if vertical else hw) - 3

            def _in_angle(ent):
                i2, end, _p = ent
                pts2 = routes[i2]["points"]
                k0, k1 = (0, 1) if end == "a" else (len(pts2) - 1, len(pts2) - 2)
                return math.atan2(pts2[k1][1] - pts2[k0][1],
                                  pts2[k1][0] - pts2[k0][0])
            ents = sorted(entries, key=_in_angle)
            k = len(ents)
            offs = [(t2 - (k - 1) / 2.0) * FAN_STEP for t2 in range(k)]
            before = {i2: [list(p) for p in routes[i2]["points"]]
                      for i2, _e, _p in ents}
            stats_before = {i2: self._edge_stats(i2, routes)
                            for i2, _e, _p in ents}
            for (i2, end, _p), off in zip(ents, offs):
                pts2 = routes[i2]["points"]
                idx = 0 if end == "a" else len(pts2) - 1
                if vertical:
                    pts2[idx] = [pts2[idx][0],
                                 max(cy - half_len, min(cy + half_len,
                                                        cy + off))]
                else:
                    pts2[idx] = [max(cx - half_len, min(cx + half_len,
                                                        cx + off)),
                                 pts2[idx][1]]
            ok = True
            for i2, _e, _p in ents:
                pr, clr, ang, cross, msep = self._edge_stats(i2, routes)
                pr0, clr0, ang0, cross0, msep0 = stats_before[i2]
                if pr > pr0 or cross > cross0:
                    ok = False
                if clr is not None and clr < self.cl - 1e-6:
                    ok = False
                if ang < ANCHOR_MIN_DEG:
                    ok = False
                if msep is not None and msep < 4.0:
                    ok = False
                if not ok:
                    break
            if not ok:
                for i2, pts_b in before.items():
                    routes[i2]["points"] = pts_b
        return routes

    def _pt_in_band(self, v, p):
        """Whether anchor p is already inside the border's +/- 1/4 band (and on the border)."""
        q = self._band_clamp_pt(v, p)
        return abs(q[0] - p[0]) <= 1e-6 and abs(q[1] - p[1]) <= 1e-6

    def _own_box_ok(self, i, routes):
        """No intrusion into the own box interior (ref-scrubbed): _edge_stats only counts other-box press,
                but after in-band anchor clamping + ctrl following, the arc tangent can dip into the own box (measured on classic-cld
                crowding->quickfix), so the delivery gate must add an own-box interior check -- the same
                accounting as _evaluate's own-box rule (interior sample points + PRESS_MARGIN/ROUND_GUARD)."""
        pts = routes[i]["points"]
        a, b = self.edges[i]
        samples = sample_polyline(pts)[1:-1]
        for v in (a, b):
            cx, cy, hw, hh = self.N[v]
            for (px, py) in samples:
                if dist_point_rect(px, py, cx, cy,
                                   hw + PRESS_MARGIN, hh + PRESS_MARGIN) \
                        <= ROUND_GUARD:
                    return False
        return True

    def _anchors_in_band(self, i, routes):
        pts = routes[i]["points"]
        for idx in (0, len(pts) - 1):
            v = self.edges[i][0] if idx == 0 else self.edges[i][1]
            if not self._pt_in_band(v, pts[idx]):
                return False
        return True

    def _band_candidates(self, a, b, idx):
        """ref-scrubbed mutual-pair in-band candidates.

                line/arc: for every anchor variant, first pull into the band via _band_clamp_pt, then recompute the geometry on the
                new chord (pure filtering is not enough -- under a narrow box's +/- 1/4 band almost all raw variants are out-of-band; on
                classic-cld crowding, band width 48px vs variant offsets 30-55px left only 2 candidates measured); arc takes both side
                signs (nested arcs = the mutual-separation escape hatch under in-band accounting; the north arc's tangent stabbing into the box
                is already sealed by the _own_box_ok hard gate). vg/poly/wrap corridor families: anchors are decided by the corridor structure,
                midpoints cannot be recomputed with the anchors, so only those whose anchors are naturally in-band are kept (side-margin
                midpoint poly etc.). Called only by _reroute_pair_band (the delivery clamping-failure fallback); not in the regular candidate pool.
        """
        out = []
        seen = set()
        mutual = (min(a, b), max(a, b)) in self.mutual
        for pa, pb in self._anchor_variants(a, b):
            pa2 = pa if self._pt_in_band(a, pa) else self._band_clamp_pt(a, pa)
            pb2 = pb if self._pt_in_band(b, pb) else self._band_clamp_pt(b, pb)
            cands = [("line", [pa2, pb2], pa2, pb2)]
            vx, vy = pb2[0] - pa2[0], pb2[1] - pa2[1]
            dist = math.hypot(vx, vy)
            if dist > EPS:
                ux, uy = norm(-vy, vx)
                ks = tuple(dict.fromkeys((adaptive_arc_k(dist),) + ARC_KS))
                for k in ks:
                    for s in (1, -1):
                        ctrl = [(pa2[0] + pb2[0]) / 2 + ux * k * dist * s,
                                (pa2[1] + pb2[1]) / 2 + uy * k * dist * s]
                        cands.append(("arc", quad_points(pa2, ctrl, pb2),
                                      pa2, pb2, ctrl))
                        if mutual:
                            ctrl_m = [(pa2[0] + pb2[0]) / 2 - ux * k * dist * s,
                                      (pa2[1] + pb2[1]) / 2 - uy * k * dist * s]
                            cands.append(("arc", quad_points(pa2, ctrl_m, pb2),
                                          pa2, pb2, ctrl_m))
            for cand in cands:
                key = (cand[0], tuple(map(tuple, cand[1])))
                if key not in seen:
                    seen.add(key)
                    out.append(cand)
        for cand in self._candidates(a, b, idx):
            if cand[0] in ("line", "arc"):
                continue
            if not (self._pt_in_band(a, cand[2]) and
                    self._pt_in_band(b, cand[3])):
                continue
            key = (cand[0], tuple(map(tuple, cand[1])))
            if key not in seen:
                seen.add(key)
                out.append(cand)
        return out

    def _reroute_pair_band(self, routes, i, j):
        """Delivery fallback: mutual-pair local re-routing on in-band anchors (ref-scrubbed).

                Enabled when every tier of the midband_reanchor ladder clamping fails (out-of-band anchors cannot be clamped past the hard
                gate -- the lens arc's tangent stabbing into the box falls back): only these two edges are rebuilt with in-band candidates,
                a greedy two passes (i fixed -> j fixed against the new i -> re-evaluate) picks the best combination; the hard gates match the
                delivery accounting (press/clearance/anchor angle/no crossing increase/mutual separation >= 4px), falling back to the
                original routes when unsolvable. Deterministic: fixed candidate order + fixed scoring, no RNG. Other edges are untouched (the structural guarantee of zero drift on the other 18 graphs).
        """
        a, b = self.edges[i]
        ctx = {}
        for k2, r in routes.items():
            if k2 in (i, j):
                continue
            segs = list(zip(r["points"][:-1], r["points"][1:]))
            bb = [(min(p[0], q[0]), min(p[1], q[1]),
                   max(p[0], q[0]), max(p[1], q[1])) for p, q in segs]
            ctx[k2] = (segs, bb)
        cands_i = self._band_candidates(a, b, i)
        cands_j = self._band_candidates(b, a, j)
        keep_i, keep_j = routes[i], routes[j]
        st_i0 = self._edge_stats(i, routes)
        st_j0 = self._edge_stats(j, routes)

        def gates_ok():
            for k2, st0 in ((i, st_i0), (j, st_j0)):
                s = self._edge_stats(k2, routes)
                if (s[0] > st0[0] or s[3] > st0[3] or
                        (s[1] is not None and s[1] < self.cl - 1e-6) or
                        s[2] < ANCHOR_MIN_DEG or
                        (s[4] is not None and s[4] < 4.0) or
                        not self._own_box_ok(k2, routes)):
                    return False
            return True

        def pick(ii, aa, bb, cands, other):
            sib = sample_polyline(routes[other]["points"], step=12)
            best = None
            for cand in cands:
                sc, info = self._evaluate(cand, aa, bb, ctx, sib)
                if info is None:
                    continue
                old = routes[ii]
                routes[ii] = info
                ok = gates_ok()
                routes[ii] = old
                if ok and (best is None or sc < best[0] - EPS):
                    best = (sc, info)
            return best

        done = False
        for _pass in (0, 1):
            r1 = pick(i, a, b, cands_i, j)
            if r1 is None:
                break
            routes[i] = r1[1]
            r2 = pick(j, b, a, cands_j, i)
            if r2 is None:
                routes[i] = keep_i
                break
            routes[j] = r2[1]
        else:
            done = routes[i] is not keep_i and routes[j] is not keep_j \
                and gates_ok()
        if not done:
            routes[i] = keep_i
            routes[j] = keep_j
        return done

    # -- ref-scrubbed rework 1: cost allocation admitting "straight-line feasible" candidates for mutual pairs --
    def mutual_straight_reroute(self, routes, frozen=()):
        """Mutual-pair straight-line reassignment (WS3: when a straight line is feasible the polyline must not win on score; polyline = last resort).

                In the v0.7.3 candidate pool, all line-family anchor variants hang on the baseline-direction borders (the direction exit
                border of _anchors x the peer's entry border, _offset_anchors only moves along the same border's tangent); cross-border
                anchor combinations (e.g. a's left-midpoint x b's top-midpoint) simply are not in the pool -- mutual pairs get pushed
                by PAIR_SEP_W into poly side-lane detours (measured on classic-cld quickfix->crowding: a 298px polyline vs a 101px
                natural straight line, with the polyline truly crossing already-routed lines). This channel is enabled only for
                mutual-pair edges whose current route is a polyline (poly/vg/wrap): enumerate the two boxes' four border-midpoint anchors x
                straight-line candidates (midpoints are naturally in the +/- 1/4 band); the replacement happens only if the delivery hard
                gates (press 0/clearance/anchor angle/no crossing increase/mutual separation >= 4/own box) all pass and the total score is
                strictly better than the current route; with no feasible straight line, return as-is (byte-for-byte unchanged). The sibling
                edge (reverse edge) is rechecked in the same batch -- the separation/crossing/clearance gates must not regress because this
                edge switched routes (rework 2 accounting). Deterministic: fixed edge order + fixed enumeration order, no RNG. Invoked only
                in the enhanced (spine-construct) domain; the other engines are structurally zero-drift.
        """
        for i in sorted(routes.keys()):
            if i in frozen:
                continue
            a, b = self.edges[i]
            if (min(a, b), max(a, b)) not in self.mutual:
                continue
            cur = routes[i]
            if cur.get("kind") not in ("poly", "vg", "wrap"):
                continue
            j = self.eidx.get((b, a))
            if j is None or j in frozen:
                continue
            # Evaluation context: the other routed segments + bboxes (for _evaluate crossing/press checks)
            ctx = {}
            for k2, r in routes.items():
                if k2 in (i, j):
                    continue
                segs = list(zip(r["points"][:-1], r["points"][1:]))
                bb = [(min(p[0], q[0]), min(p[1], q[1]),
                       max(p[0], q[0]), max(p[1], q[1])) for p, q in segs]
                ctx[k2] = (segs, bb)
            sib = sample_polyline(routes[j]["points"], step=12)
            # Reference score of the current route (same _evaluate weights; the vg corner/fillet fields
            # are padded as empty shells -- scoring only consumes kind/points)
            cur_cand = (cur.get("kind", "poly"), cur["points"],
                        cur["points"][0], cur["points"][-1],
                        {"corner_pts": [], "fillets": []})
            cur_sc, _ = self._evaluate(cur_cand, a, b, ctx, sib)
            cur_cross = cur.get("cross", 0)
            st_j0 = self._edge_stats(j, routes)

            def mids(v):
                cx, cy, hw, hh = self.N[v]
                return {"t": [cx, cy - hh], "b": [cx, cy + hh],
                        "l": [cx - hw, cy], "r": [cx + hw, cy]}

            ma, mb = mids(a), mids(b)
            best = None
            for sa in ("t", "b", "l", "r"):
                for sb in ("t", "b", "l", "r"):
                    pa, pb = ma[sa], mb[sb]
                    if abs(pa[0] - pb[0]) < EPS and abs(pa[1] - pb[1]) < EPS:
                        continue
                    cand = ("line", [pa, pb], pa, pb)
                    sc, info = self._evaluate(cand, a, b, ctx, sib)
                    if info is None or info.get("press", 0):
                        continue
                    mc = info.get("min_clear")
                    if mc is not None and mc < self.cl - 1e-6:
                        continue          # hard gate: edge-box clearance
                    if min(info.get("ang_a", 0.0),
                           info.get("ang_b", 0.0)) < ANCHOR_MIN_DEG:
                        continue          # hard gate: anchor smoothness
                    if sc >= cur_sc - EPS:
                        continue          # WS3: the total score must strictly beat the current route
                    old = routes[i]
                    routes[i] = info
                    ok = True
                    for k2, st0 in ((i, None), (j, st_j0)):
                        st = self._edge_stats(k2, routes)
                        if st[0] > 0:
                            ok = False    # hard gate: box press
                        elif (st[1] is not None and st[1] < self.cl - 1e-6):
                            ok = False    # hard gate: clearance
                        elif st[2] < ANCHOR_MIN_DEG:
                            ok = False    # hard gate: anchor smoothness
                        elif st[4] is not None and st[4] < 4.0:
                            ok = False    # hard gate: mutual-pair separation
                        elif not self._own_box_ok(k2, routes):
                            ok = False    # hard gate: own box
                        elif k2 == i and st[3] > cur_cross:
                            ok = False    # hard gate: crossing count must not increase
                        elif k2 == j and st[3] > st0[3]:
                            ok = False    # sibling-edge crossing count must not increase
                        if not ok:
                            break
                    routes[i] = old
                    if ok and (best is None or sc < best[0] - EPS):
                        best = (sc, info)
            if best is not None:
                routes[i] = best[1]
        return routes

    def midband_reanchor(self, routes, frozen=(), enhanced=True):
        """Delivery-layer connection-point accounting (ref-scrubbed): anchors clamped into the edge-midpoint +/- 1/4 edge-length band.

                jacky: "the points where lines attach to boxes should also prefer each border's midpoint; avoid the corners
                possible." The routing decision layer keeps the legacy exit geometry (candidate coverage unchanged); before delivery, this channel
                clamps out-of-band anchors along their own border tangent into the +/- 1/4 band -- corners are excluded wholesale (in-band anchors
                can never hug a corner). Per-edge hard-gate recheck (press/clearance/anchor angle/no crossing increase/mutual separation >= 4px).

                ref-scrubbed rework (rejected in jacky's second review): three stages --
                Tier 0 "baseline accounting": the original v0.7.2 semantics (endpoint clamping, ctrl untouched, the original hard-gate set)
                runs first and delivers on success (the guarantee that the other 18 graphs stay byte-for-byte identical to v0.7.2);
                Tier 1 "enhanced ladder": enabled only on baseline failure / still out-of-band -- (1) for arcs (ctrl present), the ctrl
                translates in lockstep with anchor clamping (preserving the departure tangent) and dense points are re-discretized from the
                Bezier (the old version only moved the endpoint samples, leaving the arc geometry disconnected from ctrl); (2) step in a
                ladder along the border toward the border midpoint (REANCHOR_STEP=4px, capped at half the band), retrying tier by tier with
                the gate set augmented by the own-box interior check (_edge_stats only counts other-box press; after ctrl follows, the tangent
                can dip into the own box, measured on classic-cld); (3) all tiers failing -> mutual-pair in-band local re-routing
                (_reroute_pair_band). Deterministic: fixed edge order + fixed tier order, no RNG.
                frozen edges (constructed routes / waypoints) are untouched -- the symmetric-mode constructed arcs already carry their own
                chord-coordinate mapping accounting.
        """
        handled = set()
        for i in sorted(routes.keys()):
            if i in frozen or i in handled:
                continue
            before_pts = [list(p) for p in routes[i]["points"]]
            before = self._edge_stats(i, routes)
            ctrl0 = routes[i].get("ctrl")
            # -- Tier 0: baseline accounting (original v0.7.2 semantics, byte-identical on success) --
            baseline_done = False
            if self._anchors_in_band(i, routes):
                continue                     # already in band, no clamping needed
            pts = [list(p) for p in before_pts]
            changed = False
            for idx in (0, len(pts) - 1):
                v = self.edges[i][0] if idx == 0 else self.edges[i][1]
                cx, cy, hw, hh = self.N[v]
                p = pts[idx]
                dxo, dyo = p[0] - cx, p[1] - cy
                on_x = abs(abs(dxo) - hw) <= abs(abs(dyo) - hh)
                if on_x:
                    lim = hh / 2.0
                    np_ = [p[0], cy + max(-lim, min(lim, dyo))]
                else:
                    lim = hw / 2.0
                    np_ = [cx + max(-lim, min(lim, dxo)), p[1]]
                if abs(np_[0] - p[0]) > 1e-9 or abs(np_[1] - p[1]) > 1e-9:
                    pts[idx] = np_
                    changed = True
            if changed:
                routes[i]["points"] = pts
                after = self._edge_stats(i, routes)
                ok = (after[0] <= before[0] and after[3] <= before[3] and
                      (after[1] is None or after[1] >= self.cl - 1e-6) and
                      after[2] >= ANCHOR_MIN_DEG and
                      (after[4] is None or after[4] >= 4.0))
                if ok:
                    baseline_done = True
                else:
                    routes[i]["points"] = before_pts
            if baseline_done:
                continue
            if not enhanced:
                continue     # not spine-wing: stop at the baseline accounting (the other 18 graphs stay byte-identical)
            # -- Tier 1: enhanced ladder (ctrl follows + own_box gate) --
            for k in range(0, 9):
                pts = [list(p) for p in before_pts]
                changed = False
                for idx in (0, len(pts) - 1):
                    v = self.edges[i][0] if idx == 0 else self.edges[i][1]
                    cx, cy, hw, hh = self.N[v]
                    p = pts[idx]
                    dxo, dyo = p[0] - cx, p[1] - cy
                    on_x = abs(abs(dxo) - hw) <= abs(abs(dyo) - hh)
                    if on_x:
                        lim = hh / 2.0
                        np_ = [p[0], cy + max(-lim, min(lim, dyo))]
                        if k:
                            t = np_[1] - cy
                            step = max(-lim, min(lim,
                                                 t - (REANCHOR_STEP if t > 0
                                                      else -REANCHOR_STEP) * k))
                            np_[1] = cy + step
                    else:
                        lim = hw / 2.0
                        np_ = [cx + max(-lim, min(lim, dxo)), p[1]]
                        if k:
                            t = np_[0] - cx
                            step = max(-lim, min(lim,
                                                 t - (REANCHOR_STEP if t > 0
                                                      else -REANCHOR_STEP) * k))
                            np_[0] = cx + step
                    if abs(np_[0] - p[0]) > 1e-9 or abs(np_[1] - p[1]) > 1e-9:
                        pts[idx] = np_
                        changed = True
                if not changed:
                    if k == 0:
                        break            # already in band, no clamping needed
                    continue
                # Arcs: ctrl translates in lockstep (sum of the endpoint displacement vectors) + dense re-discretized, keeping the geometry consistent
                if ctrl0 is not None:
                    da = [pts[0][0] - before_pts[0][0],
                          pts[0][1] - before_pts[0][1]]
                    db = [pts[-1][0] - before_pts[-1][0],
                          pts[-1][1] - before_pts[-1][1]]
                    ctrl = [ctrl0[0] + da[0] + db[0], ctrl0[1] + da[1] + db[1]]
                    pts = quad_points(pts[0], ctrl, pts[-1])
                    routes[i]["ctrl"] = ctrl
                routes[i]["points"] = pts
                after = self._edge_stats(i, routes)
                ok = (after[0] <= before[0] and after[3] <= before[3] and
                      (after[1] is None or after[1] >= self.cl - 1e-6) and
                      after[2] >= ANCHOR_MIN_DEG and
                      (after[4] is None or after[4] >= 4.0) and
                      self._own_box_ok(i, routes))
                if ok:
                    break
                routes[i]["points"] = before_pts
                if ctrl0 is not None:
                    routes[i]["ctrl"] = list(ctrl0)
            # Every ladder tier failed (final state still out-of-band) -> mutual-pair in-band local re-routing fallback
            if not self._anchors_in_band(i, routes):
                a_, b_ = self.edges[i]
                j = self.eidx.get((b_, a_))
                if j is not None and j not in frozen and j not in handled:
                    if self._reroute_pair_band(routes, i, j):
                        handled.add(j)
        return routes

    # -- main entry --
    def route_all(self):
        """Two-pass routing: pass one routes each edge in order; pass two re-evaluates every edge against "the other edges already routed" and swaps in improvements.

                Both passes are deterministic (fixed candidate order + fixed scoring); same graph yields same output.
        """
        routed = {}
        out = {}
        order = self.order
        # WS5 performance: routed_segs maintained incrementally -- each routed line's segments/bboxes are computed once
        # (the old version fully rebuilt all routed lines for every edge, O(m^2) repeated derivation; contents are item-by-item equivalent)
        seg_cache = {}
        for _pass in (1, 2):
            for i in order:
                a, b = self.edges[i]
                # F1: precomputed routed lines (segments + bboxes, for the crossing bbox pre-filter); if the mutual sibling
                # edge (b,a) is already routed -> also prepare 12px coarse samples for the coincidence penalty
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
                seg_cache.pop(i, None)   # this edge was re-routed: old cache invalidated
                out[i] = info
        return out
