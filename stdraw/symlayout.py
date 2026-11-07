# -*- coding: utf-8 -*-
"""Bowtie-pair (two triangles sharing an edge) symmetric placement
(2026-11-06 jacky layout aesthetics v2, ref-scrubbed).

> #11 learning-flywheel "could be symmetric yet leans left" — symmetric
> structures should be explicitly symmetric.

Trigger detection (deterministic local structure, checked before ring
detection):
  The core graph is exactly "two triangles sharing one edge" (bowtie):
  4 nodes, 5 edges, degree sequence {3,3,2,2}, with the two degree-3
  nodes adjacent (shared-edge endpoints) and the two degree-2 nodes
  non-adjacent (left/right apexes). Corpus hits: learning-flywheel /
  fixes-that-fail (a directed-isomorphic pair -> the same layout
  template).

Placement (place_bowtie):
  - Shared-edge endpoints A (upper row) / B (lower row) sit on the
    vertical axis; the two apexes mirror left (-D) / right (+D) on the
    middle row — explicit geometric symmetry;
  - Line-style consistency hard rule: the axis edge A->B is a straight
    line; all 4 side edges are constructed as mirrored arcs (ctrl offset
    symmetrically outward) — "line styles stay consistent within one
    symmetric structure (no straight/arc/bend mixing)".

Centering normalization: the bounding-box center of A/B/apex is the
canvas center (layout-layer axis x=0; the delivery layer translates
uniformly to center — see layout_auto's centering post-process).
"""
import math

SYM_GAP = 36              # breathing-room target clearance
ARC_K_FALLBACK = 0.22     # side-arc k fallback tier (unreachable when side_geom is empty; defensive)


class InfeasibleBowtie(Exception):
    pass


def _adjacency(edges):
    adj = {v: set() for a, b in edges for v in (a, b)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def detect_bowtie(graph):
    """Bowtie detection. Returns {"A","B","L","R","deg0"} or None."""
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
    # Structural self-check: exactly two triangles = {a,b,l} and {a,b,r}, sharing edge a-b
    if not (l in adj[a] and l in adj[b] and r in adj[a] and r in adj[b]):
        return None
    # A = upper-row node: deterministic (id order; a/b sit at swap-symmetric positions, geometry invariant)
    return {"A": a, "B": b, "L": l, "R": r, "deg0": deg0}


from .routing import border_point as _border_point


def _quad_points(p0, ctrl, p1, seg=24):
    return [[(1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * p1[1]]
            for t in (i / seg for i in range(seg + 1))]


def _own_press(pts, na, nb):
    """Whether the arc's intermediate sample points enter either end's own box
    (with 1px margin; same criteria as check2).

    Diagnostic aid (normally not triggered under the ctrl-translation
    convention; kept for debugging recomputation).
    """
    from .routing import dist_point_rect
    for p in pts[1:-1]:
        for bx, by, bw, bh in (na, nb):
            if dist_point_rect(p[0], p[1], bx, by, bw / 2 + 1, bh / 2 + 1) <= 0:
                return True
    return False


def _natural_border(cx, cy, hw, hh, dx, dy):
    """The ray's natural intersection with the box edge (no band clamping; used to compute the anchor clamping delta)."""
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return [cx, cy]
    if abs(dx) < 1e-9:
        return [cx, cy + (hh if dy > 0 else -hh)]
    if abs(dy) < 1e-9:
        return [cx + (hw if dx > 0 else -hw), cy]
    t = min(hw / abs(dx), hh / abs(dy))
    return [cx + dx * t, cy + dy * t]


def _clamp_band(p, nx, ny, nw, nh):
    """Anchor clamped to the owning edge's midpoint ± 1/4 edge-length band (corners excluded; connection-point delivery convention)."""
    hw, hh = nw / 2.0, nh / 2.0
    dxo, dyo = p[0] - nx, p[1] - ny
    on_x = abs(abs(dxo) - hw) <= abs(abs(dyo) - hh)
    if on_x:
        return [p[0], ny + max(-hh / 2, min(hh / 2, dyo))]
    return [nx + max(-hw / 2, min(hw / 2, dxo)), p[1]]


def place_bowtie(plan, widths, card_h, cfg, edges):
    """Bowtie symmetric placement -> ({v: x}, {v: y}, meta, constructed_routes).

    constructed_routes: {(a,b): route dict} — axis edge as a straight line
    + 4 side edges as mirrored arcs, constructively injected (not via the
    candidate pool), guaranteeing mirror symmetry and line-style
    consistency.
    """
    A, B, L, R = plan["A"], plan["B"], plan["L"], plan["R"]
    pitch = cfg.pitch
    yA = cfg.top
    yB = cfg.top + pitch
    yMid = cfg.top + pitch / 2
    wmax = max(widths.values())
    # D: apex distance from the axis — axis card half-width + clearance + apex half-width; also L/R apex mutual distance >= SYM_GAP
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
    # Axis edge: straight line (A->B / B->A per the graph's directed edges; anchors face the peer's box edge)
    for u, v in ((A, B), (B, A)):
        if (u, v) not in eset:
            continue
        dy_u = 1 if y[v] > y[u] else -1
        dy_v = 1 if y[u] > y[v] else -1
        pa = _border_point(pos[u], y[u], widths[u] / 2, card_h / 2, 0, dy_u)
        pb = _border_point(pos[v], y[v], widths[v] / 2, card_h / 2, 0, dy_v)
        constructed[(u, v)] = {"kind": "line", "points": [pa, pb]}
    # Side edges: mirrored arcs (apex <-> axis node; ctrl offset outward, mirrors share |ctrl|).
    # ref-scrubbed arc parameterization: k takes the adaptive median tier of the 4 side chord lengths —
    # consistent curvature within one symmetric structure ("same-ring arc consistency" hard rule).
    # Connection-point convention: the arc is shaped on **natural anchors** (the old ray convention)
    # first, then mapped to clamped anchors — ctrl via chord coordinate transform (alpha ratio +
    # beta perpendicular kept): shape and departure tangent preserved, never flipping into its own box.
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
        # Outward normal: chosen vs. the "apex -> axis" direction so ctrl moves away from the vertical axis
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        cx = mx + ux * k_uni * dist * s
        cy = my + uy * k_uni * dist * s
        if (cx - 0) * s < (mx - 0) * s:      # ctrl must sit further out than the midpoint
            cx = mx - ux * k_uni * dist * s
            cy = my - uy * k_uni * dist * s
        # Map chord coordinates onto the clamped anchors: ctrl = pa_c + alpha*(pb_c-pa_c) + beta_vec
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
