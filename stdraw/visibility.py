# -*- coding: utf-8 -*-
"""WS3 routing math layer: visibility-graph shortest straight-line paths + clearance-constrained minimum-curvature arcs.

Mathematical accounting (honest statement, consistent with the certificate wording):
1. Straight-line obstacle avoidance = **Dijkstra shortest path on the visibility graph over inflated obstacle corners**
      (exactly optimal on the graph, a classic computational-geometry theorem). Obstacles are box-grown by clearance c: the inflated
      rectangle >= the rounded-corner Minkowski region (|p-rect| < c), hence "segment misses the inflated rectangle => Euclidean
      clearance to the original rectangle >= c". Versus the true shortest path in the continuous space of rounded obstacles, each
      hugged corner adds at most (2-pi/2)*c ~= 0.43c px -- recovered by the corner-cutting effect of arc smoothing.
2. Every visibility edge is independently rechecked with the **exact segment-rectangle distance** (Liang-Barsky intersection
      test + four-border segment-segment distances); clearance is an analytic guarantee, not a coincidence of discrete sampling.
3. Arc smoothing = tangent-inscribed circular arcs at bends: G1 tangent continuity (no inflection), curvature bounded
      throughout (<= 1/r_min). Radii shrink along a deterministic sequence; each arc rechecks clearance at every sampled point;
      this module builds the graph and rechecks at the "target clearance c"; the caller passes c = CLEARANCE + 1.5, leaving
      a >= +1.4px margin at delivery-coordinate recheck, so the >=16px hard gate is never grazed.
4. Deterministic: no RNG. Node order, candidate order, radius sequence all fixed; same input gives byte-for-byte the same output.

This module is stdlib-only, with no networkx/ortools dependency.
"""
import math
from heapq import heappush, heappop

VIS_EPS = 1e-6        # float tolerance for visibility tests
ARC_SAMPLES = 16      # sampled segments per circular arc (for geometry/crossing rechecks)
FILLET_R_MAX = 36.0   # smoothing-arc maximum radius px
FILLET_R_SHRINK = (1.0, 0.75, 0.55, 0.40, 0.28, 0.18, 0.10)  # deterministic shrink sequence
FILLET_TAU_MAX = 0.45  # upper bound on tangent-segment length as a fraction of the adjacent segment length
DEFLECT_SKIP = 0.03    # bend deflection < ~1.7 degrees is treated as straight, no arc


# -- exact distance primitives -----------------------------------------
def _pt_seg_dist(px, py, a, b):
    """Minimum distance from a point to a segment."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < VIS_EPS:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / L2))
    return math.hypot(px - (a[0] + t * vx), py - (a[1] + t * vy))


def seg_seg_dist(p1, p2, p3, p4):
    """Distance between two segments: 0 if intersecting; otherwise the minimum of the four endpoint-to-other-segment distances."""
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
    """Liang-Barsky: whether a segment enters the rectangle with positive length (border-touching does not count). Same accounting as metrics.

        Self-contained implementation (metrics -> routing -> this module would be a circular import, so no back-reference).
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
    """Exact minimum distance from a segment to a rectangle (center + half-width/half-height): 0 if intersecting.

        Intersection uses Liang-Barsky (positive-length entry counts, border-touching does not); when disjoint, take the minimum
        segment-segment distance over the rectangle's four borders.
    """
    cx, cy, hw, hh = rect
    if _seg_hits_rect(p1[0], p1[1], p2[0], p2[1], cx, cy, hw, hh):
        return 0.0
    corners = ((cx - hw, cy - hh), (cx + hw, cy - hh),
               (cx + hw, cy + hh), (cx - hw, cy + hh))
    return min(seg_seg_dist(p1, p2, corners[k], corners[(k + 1) % 4])
               for k in range(4))


def pt_rect_distance(px, py, rect):
    """Euclidean distance from a point to a rectangle (0 when inside)."""
    cx, cy, hw, hh = rect
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


# -- visibility graph + Dijkstra ----------------------------------------
def _graph_nodes(src, dst, rects, c):
    """Nodes = source/sink + the 4 corners of every inflated rectangle (inflated corners sit exactly c from the original rectangle)."""
    nodes = [tuple(src), tuple(dst)]
    for (cx, cy, hw, hh) in rects:
        gx, gy = hw + c, hh + c
        nodes.extend([(cx - gx, cy - gy), (cx + gx, cy - gy),
                      (cx + gx, cy + gy), (cx - gx, cy + gy)])
    return nodes


def _visible(p1, p2, rects, c):
    """Segment keeps clearance >= c - epsilon against all obstacles (analytic recheck, no sampling).

        Performance (WS5): first a lower-bound quick filter via the "segment bbox x rectangle bbox" distance -- any point on the
        segment is at a distance from the rectangle >= the bbox distance, so when the bbox distance >= c - epsilon the exact distance
        is necessarily >= c - epsilon and the exact computation can be skipped (exactly equivalent, changes no test outcome).
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
            # gx/gy already clamped to 0: hypot(gx,gy) = the bbox distance; only < t can possibly block the line
            if gy < t and (gx == 0.0 or gy == 0.0 or gx * gx + gy * gy < t2):
                if seg_rect_distance(p1, p2, rect) < t:
                    return False
    return True


def _dijkstra(nodes, adj, src_idx, dst_idx):
    """Deterministic Dijkstra: heap key (dist, node_idx); node_idx is unique -> fixed pop order."""
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
        # adj[u] generated in ascending node_idx order -> fixed relaxation order; ties not replaced (first come, first kept)
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
    """Shortest path on the visibility graph over inflated obstacle corners. Returns None when unreachable.

        Returns the polyline [src, corner*, ..., dst] (exactly optimal on the graph; optimality bounds in the module docstring).

        Exact-equivalence speedup (WS5 caliber, measured on the dev box during
        the dense-snap wall-clock regression fix): the corner-corner visibility
        submatrix depends only on (rects, c) -- cached per (rounded rects,
        rounded c) and consulted as a set membership instead of a fresh
        _visible recheck per pair; src/dst pairs are still computed live.
        Same _visible verdicts on the same inputs, same weights, same
        ascending (i, j) adjacency generation order -> byte-identical paths.
    """
    if not rects:
        return [tuple(src), tuple(dst)]
    nodes = _graph_nodes(src, dst, rects, c)
    n = len(nodes)
    vis = _corner_visibility(rects, c)
    # Adjacency list: O(n^2) visibility rechecks, generated in ascending (i,j) order -> deterministic
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if i >= 2 and j >= 2:
                ok = (i, j) in vis
            else:
                ok = _visible(nodes[i], nodes[j], rects, c)
            if ok:
                w = math.hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1])
                adj[i].append((j, w))
                adj[j].append((i, w))
    return _dijkstra(nodes, adj, 0, 1)


_CORNER_VIS_CACHE = {}


def _corner_visibility(rects, c):
    """Set of visible corner-corner pairs (global indices in _graph_nodes order), cached per (rects, c)."""
    key = (tuple(tuple(r) for r in rects), float(c))
    ent = _CORNER_VIS_CACHE.get(key)
    if ent is None:
        corners = []
        for (cx, cy, hw, hh) in rects:
            gx, gy = hw + c, hh + c
            corners.extend([(cx - gx, cy - gy), (cx + gx, cy - gy),
                            (cx + gx, cy + gy), (cx - gx, cy + gy)])
        vis = set()
        m = len(corners)
        for i in range(m):
            for j in range(i + 1, m):
                if _visible(corners[i], corners[j], rects, c):
                    vis.add((i + 2, j + 2))
        if len(_CORNER_VIS_CACHE) >= 512:
            _CORNER_VIS_CACHE.clear()
        _CORNER_VIS_CACHE[key] = ent = vis
    return ent


def _shortcut(path, rects, c, rounds=3):
    """Visible-chord shortcuts (string pulling): try skipping intermediate points in order, stop on convergence. Deterministic."""
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


# -- arc smoothing (clearance-constrained minimum curvature) -------------
def _fillet(a, q, b, rects, c):
    """Tangent arc at bend q. Returns None (no arc wanted / no arc possible) or an arc-parameter dict.

        G1: the arc is tangent-continuous with the adjacent segments at ta/tb; curvature = 1/r is bounded.
        Radii shrink deterministically; clearance is rechecked at every sampled point as >= c - 0.005 (chord height on the
        <=0.05px scale; the delivery-coordinate 16px hard gate keeps the c-16=1.5px inflation margin as a fallback).
        Geometric bound (honest): the tangent arc at a convex corner dips r*(1/cos(theta/2)-1) toward the obstacle side;
        shallow corners admit large arcs while right angles, constrained by the 1.5px margin, admit only a tiny fillet (r <= ~3.6).
    """
    ux, uy = q[0] - a[0], q[1] - a[1]
    wx, wy = b[0] - q[0], b[1] - q[1]
    lu, lw = math.hypot(ux, uy), math.hypot(wx, wy)
    if lu < VIS_EPS or lw < VIS_EPS:
        return None
    ux, uy, wx, wy = ux / lu, uy / lu, wx / lw, wy / lw
    # Deflection angle theta = angle between u and w (theta=0 straight continuation; theta=pi U-turn)
    theta = math.acos(max(-1.0, min(1.0, ux * wx + uy * wy)))
    if theta < DEFLECT_SKIP or theta > math.pi - DEFLECT_SKIP:
        return None
    cos_half = math.cos(theta / 2)
    tan_half = math.tan(theta / 2)
    # Tangent-segment length t = r*tan(theta/2), center distance d = r/cos(theta/2) (the center sits inside the bend wedge,
    # tangent to both adjacent segment lines). Radius upper bound = the smaller of the tangent-segment clamp and the absolute cap.
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
        # Interior angle-bisector direction (the sum of the unit vectors -u and w)
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
        # Defense in depth: tangent-perpendicularity self-check (the ta radius perpendicular to the incoming segment, the tb radius to the outgoing segment -- the analytic G1 condition)
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
    """n+1 sampled points of the arc ta->tb (along the short arc, angular interpolation)."""
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
    """Arc smoothing of bends. Returns (fillets, corner_pts).

        fillets[i] = {"i": index of the corner in corner_pts, ta/tb/center/r/sweep}.
        Corners that cannot take an arc stay sharp (clearance is still >= c by construction of the graph).
    """
    fillets = []
    for i in range(1, len(pts) - 1):
        f = _fillet(pts[i - 1], pts[i], pts[i + 1], rects, c)
        if f:
            f["i"] = i
            fillets.append(f)
    return fillets, list(pts)


def dense_geometry(corner_pts, fillets, arc_n=ARC_SAMPLES):
    """Polyline + arcs -> densely sampled point sequence (the geometric ground truth for clearance/crossing rechecks)."""
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
    """Delivery coordinates -> SVG path d string: straight segments L + arc segments A (exact rendering, not a polyline approximation)."""
    fmap = {f["i"]: f for f in fillets}
    r6 = lambda v: round(float(v), nd)
    parts = [f"M {r6(corner_pts[0][0])} {r6(corner_pts[0][1])}"]
    for i in range(1, len(corner_pts)):
        q = corner_pts[i]
        f = fmap.get(i)
        if f:
            # ref-scrubbed #15: a corner with a fillet is replaced by ta->arc->tb and must not be drawn back to
            # the corner itself (an unconditional L q once caused tb->q->ta_next zigzag glitches).
            parts.append(f"L {r6(f['ta'][0])} {r6(f['ta'][1])}")
            parts.append(f"A {r6(f['r'])} {r6(f['r'])} 0 0 {f['sweep']} "
                         f"{r6(f['tb'][0])} {r6(f['tb'][1])}")
        else:
            parts.append(f"L {r6(q[0])} {r6(q[1])}")
    return " ".join(parts)


def plan_route(src, dst, rects, c):
    """High-level entry: the obstacle-avoiding route from src to dst (with a deterministic cache -- a pure function, same input same output).

    ref-scrubbed cache hits return a **deep copy**: callers reuse the dense list in place as delivery
        points (midband_reanchor/fan_spread mutate anchors in place); returning the cached object directly
        would poison the global cache with those mutations and break cross-run determinism (measured: vg route drift on n20).
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
    """plan_route implementation (no cache). Returns a dict, or None when unreachable."""
    src, dst = tuple(src), tuple(dst)
    path = shortest_path(src, dst, rects, c)
    if path is None:
        return None
    path = _shortcut(path, rects, c)
    fillets, corners = smooth_corners(path, rects, c)
    dense = dense_geometry(corners, fillets)
    return {"corner_pts": corners, "fillets": fillets,
            "dense": dense, "path_d": route_svg_d(corners, fillets)}
