# -*- coding: utf-8 -*-
"""Unified feature extractor v1 -- 21 layout-quality features + RFC-level definitions.

Scope (optimization-plan v1.3.1, Appendix A union + §15 RFC definitions):
    Input  = a delivered layout.json (nodes/edges/viewBox, delivery coordinates).
    Output = one deterministic JSON document with all features under "features".

Design contracts honored here:
    * Determinism: fixed traversal orders (sorted ids), ``math.fsum`` for all
      summation, zero RNG -- the same input yields byte-identical output.
    * RFC §15.1 approximate symmetry reports the five-field struct
      {deleted_edge_costs, coverage, dir_keep_ratio, polarity_keep_ratio,
      confidence}; confidence is monotone (deleted cost ↑ => confidence ↓).
    * RFC §15.2 alignment = max coverage of anchor grouping (groups need >=3
      anchors, tolerance normalized by canvas scale, deterministic greedy
      grouping: sort by projected coordinate, ties by anchor id).
    * RFC §15.3 loop polygon vs planar face are DIFFERENT features; this module
      keeps loop semantics only (planar-face uniformity belongs to a planarized
      candidate pipeline, not here).
    * Read-only w.r.t. the layout pipeline: pure new file, no existing module
      is modified or imported for mutation.

Calibration notes (v1 placeholders, weights pending data calibration):
    * alignment tolerance  = ALIGN_TOL_FRAC * min(canvas_w, canvas_h)
    * edge deletion cost   = 1.0 per deleted edge (non-ring, non-bridge only)
    * confidence formula   = coverage * dir_keep * polarity_keep
                             / (1 + deleted_cost / total_edge_cost)

CLI:
    python -m stdraw.features <layout.json> [--out features.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from math import atan2, fsum, hypot, pi, sqrt

SCHEMA = "stdraw.features/v1"

EPS = 1e-9                 # geometric degeneracy guard
ALIGN_AXES_DEG = (0.0, 45.0, 90.0, 135.0)
ALIGN_TOL_FRAC = 0.04      # v1 initial value, pending calibration (RFC §15.2: never a fixed px)
ALIGN_MIN_GROUP = 3        # RFC §15.2: a group counts only with >=3 anchors
DEFAULT_CARD_W = 140       # same default as stdraw.metrics
DEFAULT_CARD_H = 44        # same default as stdraw.metrics (meta.cardH)
DEFAULT_CLEARANCE = 16.0   # L0 soft clearance (px), overridable by meta.clearance
AUTO_MAP_CAP = 512         # automorphism enumeration cap
AUTO_DEL_CAP = 64          # candidate single-edge deletions cap
AUTO_DEL_MAP_CAP = 128     # automorphism cap per deletion candidate

# The 21 Appendix-A features (+ alignment per RFC §15.2 and the
# increment-only stability slot).  Order is documentation only; JSON keys are
# emitted sorted.
FEATURE_KEYS = (
    "alignment_coverage",            # RFC §15.2 / Appendix A anchor_conflicts
    "automorphism_symmetry_residual",
    "bend_count_total_curvature",
    "bend_curvature_soft_clearance",
    "canvas_fill_and_aspect",
    "crossing_count",
    "edge_length_cv",
    "hub_centroid_distance",
    "layout_stability",              # increment-only slot (null on static input)
    "loop_edge_crossing_count",
    "loop_edge_length_cv",
    "loop_foreign_node_count",
    "loop_isoperimetric_compactness",
    "loop_overlap_area",
    "loop_self_intersections",
    "max_min_edge_ratio",
    "min_crossing_angle_deg",
    "min_spacing_diagonal_ratio",
    "mirror_axis_residual",
    "node_spacing_cv",
    "visual_centroid_offset",
    "voronoi_cell_area_cv",
    "angular_resolution_deg",
)


class FeatureError(ValueError):
    """Raised when the input layout cannot be interpreted."""


# ────────────────────────── numeric helpers ──────────────────────────

def _r(x, nd=9):
    """Deterministic rounding for JSON emission (None passes through)."""
    if x is None:
        return None
    return round(float(x), nd)


def _mean(vals):
    if not vals:
        return None
    return fsum(vals) / len(vals)


def _pstdev(vals, mu):
    if not vals:
        return None
    return sqrt(fsum((v - mu) ** 2 for v in vals) / len(vals))


def _cv(vals):
    """Population coefficient of variation; None when undefined."""
    if not vals:
        return None
    mu = _mean(vals)
    if mu is None or abs(mu) < EPS:
        return None
    sd = _pstdev(vals, mu)
    return sd / mu


def _dist(p, q):
    return hypot(p[0] - q[0], p[1] - q[1])


# ────────────────────────── geometry helpers ──────────────────────────

def _poly_area(poly):
    """Signed shoelace area (fsum); empty/None-safe."""
    n = len(poly)
    if n < 3:
        return 0.0
    s = fsum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
             for i in range(n))
    return s / 2.0


def _poly_perimeter(poly):
    n = len(poly)
    if n < 2:
        return 0.0
    return fsum(_dist(poly[i], poly[(i + 1) % n]) for i in range(n))


def _point_in_poly(pt, poly):
    """Ray casting; boundary points are NOT inside."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xint:
                inside = not inside
    return inside


def _seg_proper_cross(p1, p2, p3, p4):
    """Proper crossing point of open segments (endpoints touching excluded).

    Returns the crossing point or None.  Collinear overlaps return None
    (documented v1 limitation: collinear-overlap crossings are not counted).
    """
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = p4[0] - p3[0], p4[1] - p3[1]
    den = d1x * d2y - d1y * d2x
    if abs(den) < EPS:
        return None
    dx, dy = p3[0] - p1[0], p3[1] - p1[1]
    t = (dx * d2y - dy * d2x) / den
    u = (dx * d1y - dy * d1x) / den
    if EPS < t < 1 - EPS and EPS < u < 1 - EPS:
        return (p1[0] + t * d1x, p1[1] + t * d1y)
    return None


def _seg_angle_deg(p1, p2, p3, p4):
    """Acute angle (0..90] between segment directions, in degrees."""
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p4[0] - p3[0], p4[1] - p3[1])
    n1 = hypot(*v1)
    n2 = hypot(*v2)
    if n1 < EPS or n2 < EPS:
        return None
    c = abs((v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2))
    c = min(1.0, max(0.0, c))
    ang = math.degrees(math.acos(c))
    return 90.0 if ang < EPS else ang


def _polyline(points):
    """Drop consecutive duplicates; deterministic."""
    out = []
    for p in points:
        if not out or _dist(out[-1], p) > EPS:
            out.append((float(p[0]), float(p[1])))
    return out


def _polyline_len(pts):
    return fsum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _turn_angles_deg(pts):
    """Absolute turn angle at each interior vertex."""
    out = []
    for i in range(1, len(pts) - 1):
        a1 = atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])
        a2 = atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
        d = math.degrees(abs(a2 - a1))
        if d > 180.0:
            d = 360.0 - d
        out.append(d)
    return out


def _pt_seg_dist(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < EPS:
        return _dist(p, a)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / L2))
    return _dist(p, (a[0] + t * vx, a[1] + t * vy))


def _seg_rect_dist(a, b, cx, cy, hw, hh):
    """Distance between open segment (a,b) and an axis-aligned card rect.

    0 when they intersect.  Card rect given as center + half-extents.
    """
    if _seg_proper_cross(a, b, (cx - hw, cy - hh), (cx + hw, cy - hh)) or \
       _seg_proper_cross(a, b, (cx + hw, cy - hh), (cx + hw, cy + hh)) or \
       _seg_proper_cross(a, b, (cx + hw, cy + hh), (cx - hw, cy + hh)) or \
       _seg_proper_cross(a, b, (cx - hw, cy + hh), (cx - hw, cy - hh)):
        return 0.0
    corners = [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]
    # segment endpoint inside the rect => intersects
    for p in (a, b):
        if abs(p[0] - cx) <= hw and abs(p[1] - cy) <= hh:
            return 0.0
    return min(_pt_seg_dist(c, a, b) for c in corners)


def _clip_halfplane(poly, keep_fn):
    """Sutherland-Hodgman clip of a polygon against one half-plane (keep_fn)."""
    out = []
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        nxt = poly[(i + 1) % n]
        ck = keep_fn(cur)
        nk = keep_fn(nxt)
        if ck:
            out.append(cur)
        if ck != nk:
            # linear interpolation on the bisector boundary
            t = 0.5
            lo, hi = 0.0, 1.0
            # bisection for determinism (avoid exact division edge cases)
            a = cur
            b = (nxt[0] - cur[0], nxt[1] - cur[1])
            for _ in range(60):
                t = (lo + hi) / 2.0
                p = (a[0] + t * b[0], a[1] + t * b[1])
                if keep_fn(p) == ck:
                    lo = t
                else:
                    hi = t
            out.append((a[0] + ((lo + hi) / 2.0) * b[0], a[1] + ((lo + hi) / 2.0) * b[1]))
    return out


def _clip_polygons(subject, clip):
    """Intersect two polygons (Sutherland-Hodgman, clip polygon traversed as-is).

    Exact when the clip polygon is convex; a documented approximation for two
    concave polygons (v1 limitation, deterministic either way).
    """
    out = list(subject)
    n = len(clip)
    for i in range(n):
        if not out:
            return []
        a = clip[i]
        b = clip[(i + 1) % n]
        # keep the side of edge a->b where the clip polygon interior lies
        ex, ey = b[0] - a[0], b[1] - a[1]
        # interior side test via clip centroid
        cxm = _mean([p[0] for p in clip])
        cym = _mean([p[1] for p in clip])
        s = (cxm - a[0]) * ey - (cym - a[1]) * ex
        if abs(s) < EPS:
            continue
        sgn = 1.0 if s > 0 else -1.0

        def keep2(p, a=a, ex=ex, ey=ey, sgn=sgn):
            return sgn * ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) >= 0.0
        out = _clip_halfplane(out, keep2)
    return out


# ────────────────────────── layout model ──────────────────────────

class Layout:
    """Parsed delivery layout (delivery coordinates, read-only)."""

    def __init__(self, doc):
        if not isinstance(doc, dict):
            raise FeatureError("layout document must be a JSON object")
        nodes = doc.get("nodes")
        edges = doc.get("edges")
        if not isinstance(nodes, dict) or not nodes:
            raise FeatureError("layout.nodes must be a non-empty object")
        if not isinstance(edges, list):
            raise FeatureError("layout.edges must be a list")
        vb = doc.get("viewBox") or [0, 0, 0, 0]
        self.vx, self.vy, self.vw, self.vh = (float(vb[0]), float(vb[1]),
                                              float(vb[2]), float(vb[3]))
        meta = doc.get("meta") or {}
        self.card_h_default = float(meta.get("cardH", DEFAULT_CARD_H))
        self.clearance = float(meta.get("clearance", DEFAULT_CLEARANCE))

        self.ids = sorted(nodes.keys())
        self.pos = {}
        self.card_w = {}
        self.card_h = {}
        for nid in self.ids:
            p = nodes[nid]
            if "x" not in p or "y" not in p:
                raise FeatureError("node %r missing x/y" % nid)
            self.pos[nid] = (float(p["x"]), float(p["y"]))
            self.card_w[nid] = float(p.get("w", DEFAULT_CARD_W))
            self.card_h[nid] = float(p.get("h", self.card_h_default))

        self.edges = []  # deterministic order: sorted by (a, b, original index)
        keyed = []
        for i, e in enumerate(edges):
            a, b = e.get("a"), e.get("b")
            if a not in self.pos or b not in self.pos:
                raise FeatureError("edge %d references unknown node" % i)
            pts = None
            route = e.get("route") or {}
            rp = route.get("points")
            if isinstance(rp, list) and len(rp) >= 2:
                pts = _polyline(rp)
            keyed.append((str(a), str(b), i, e, pts))
        keyed.sort(key=lambda t: (t[0], t[1], t[2]))
        for a, b, i, e, pts in keyed:
            if pts is None:
                anchors = e.get("anchors") or {}
                pa, pb = anchors.get("a"), anchors.get("b")
                if pa and pb:
                    pts = _polyline([pa, pb])
                else:
                    pts = [self.pos[a], self.pos[b]]
            loops = frozenset(str(k) for k in (e.get("loop_kinds") or []))
            self.edges.append({
                "a": a, "b": b,
                "polarity": "-" if e.get("polarity") == "-" else "+",
                "loops": loops,
                "pts": pts,
                "orig_index": i,
            })
        self.degree = {nid: 0 for nid in self.ids}
        for e in self.edges:
            self.degree[e["a"]] += 1
            self.degree[e["b"]] += 1

    # derived geometry -------------------------------------------------
    @property
    def diagonal(self):
        return hypot(self.vw, self.vh)

    def rect(self, nid):
        x, y = self.pos[nid]
        return (x, y, self.card_w[nid] / 2.0, self.card_h[nid] / 2.0)

    def card_area(self, nid):
        return self.card_w[nid] * self.card_h[nid]


def _extract_loops(layout):
    """Deterministic loop cycles per loop kind.

    Each distinct loop kind forms a subgraph from its edges; a cycle walk
    starts at the smallest node id and always takes the smallest-id unused
    edge.  Returns a list of loop dicts (sorted by (kind, first node id)).
    """
    kinds = sorted({k for e in layout.edges for k in e["loops"]})
    loops = []
    for kind in kinds:
        idxs = [i for i, e in enumerate(layout.edges) if kind in e["loops"]]
        used = set()
        start = min(min(layout.edges[i]["a"], layout.edges[i]["b"]) for i in idxs)
        adj = {}
        for i in idxs:
            e = layout.edges[i]
            adj.setdefault(e["a"], []).append((e["b"], i))
            adj.setdefault(e["b"], []).append((e["a"], i))
        for nid in adj:
            adj[nid].sort()
        path = [start]
        cur = start
        closed = False
        guard = 0
        while guard < 4 * len(idxs) + 8:
            guard += 1
            nxt = None
            for nb, ei in adj.get(cur, []):
                if ei in used:
                    continue
                if nb == start and len(path) >= 2:
                    nxt = (nb, ei)
                    break
                if nb not in path:
                    nxt = (nb, ei)
                    break
            if nxt is None:
                break
            nb, ei = nxt
            used.add(ei)
            if nb == start:
                closed = True
                break
            path.append(nb)
            cur = nb
        loops.append({
            "kind": kind,
            "nodes": path,
            "closed": closed,
        })
    loops.sort(key=lambda lp: (lp["kind"], lp["nodes"][0]))
    return loops


def _loop_polygon(layout, loop):
    return [layout.pos[nid] for nid in loop["nodes"]]


# ────────────────────────── features 1-5 (loops) ──────────────────────────

def _feat_loop_geometry(layout, loops):
    """Features 1-5 + per-loop details shared by other features."""
    self_int_total = 0
    foreign_total = 0
    compact_vals = []
    compact_details = []
    edge_cv_vals = []
    edge_cv_details = []
    loop_details = []
    for lp in loops:
        poly = _loop_polygon(layout, lp)
        n = len(poly)
        # 1. self-intersections of the loop polygon (non-adjacent segments)
        cnt = 0
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # adjacent through the wrap-around vertex
                if _seg_proper_cross(poly[i], poly[(i + 1) % n],
                                     poly[j], poly[(j + 1) % n]):
                    cnt += 1
        self_int_total += cnt
        # 2. foreign (non-loop) nodes strictly inside the polygon
        on_loop = set(lp["nodes"])
        foreign = sum(1 for nid in layout.ids
                      if nid not in on_loop and _point_in_poly(layout.pos[nid], poly))
        foreign_total += foreign
        # 3. isoperimetric compactness 4*pi*A/P^2 (RFC §15.3 loop semantics)
        comp = None
        if lp["closed"] and n >= 3:
            area = abs(_poly_area(poly))
            per = _poly_perimeter(poly)
            if per > EPS and area > EPS:
                comp = 4.0 * pi * area / (per * per)
        if comp is not None:
            compact_vals.append(comp)
        # 5. per-loop edge length CV (polygon sides from node centers)
        lcv = None
        if n >= 3:
            sides = [_dist(poly[i], poly[(i + 1) % n]) for i in range(n)]
            lcv = _cv(sides)
        if lcv is not None:
            edge_cv_vals.append(lcv)
        loop_details.append({
            "kind": lp["kind"],
            "nodes": list(lp["nodes"]),
            "closed": bool(lp["closed"]),
            "self_intersections": cnt,
            "foreign_nodes_inside": foreign,
            "isoperimetric_compactness": _r(comp),
            "edge_length_cv": _r(lcv),
        })
    overlap = _feat_loop_overlap(layout, loops)
    return {
        "loop_self_intersections": {
            "total": self_int_total,
            "per_loop": [{k: d[k] for k in ("kind", "self_intersections")}
                         for d in loop_details],
        },
        "loop_foreign_node_count": {
            "total": foreign_total,
            "per_loop": [{k: d[k] for k in ("kind", "foreign_nodes_inside")}
                         for d in loop_details],
        },
        "loop_isoperimetric_compactness": {
            "mean": _r(_mean(compact_vals)),
            "worst": _r(min(compact_vals)) if compact_vals else None,
            "valid_loops": len(compact_vals),
            "per_loop": [{k: d[k] for k in ("kind", "isoperimetric_compactness",
                                            "closed")} for d in loop_details],
        },
        "loop_overlap_area": overlap,
        "loop_edge_length_cv": {
            "mean": _r(_mean(edge_cv_vals)),
            "worst": _r(max(edge_cv_vals)) if edge_cv_vals else None,
            "per_loop": [{k: d[k] for k in ("kind", "edge_length_cv")}
                         for d in loop_details],
        },
        "_loop_details": loop_details,
    }


def _feat_loop_overlap(layout, loops):
    """Pairwise overlap area of loop polygons; loops sharing nodes excluded
    (Appendix A: 环间空间关系·共享节点除外)."""
    polys = []
    for lp in loops:
        poly = _loop_polygon(layout, lp)
        polys.append((lp["kind"], set(lp["nodes"]), poly, abs(_poly_area(poly))))
    details = []
    total_terms = []
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            k1, s1, p1, a1 = polys[i]
            k2, s2, p2, a2 = polys[j]
            if s1 & s2:
                continue
            if a1 < EPS or a2 < EPS:
                continue
            inter = _clip_polygons(p1, p2)
            area = abs(_poly_area(inter))
            if area > EPS:
                total_terms.append(area)
                details.append({"loops": [k1, k2], "overlap_area": _r(area)})
    return {
        "total": _r(fsum(total_terms)) if total_terms else 0.0,
        "pairs": details,
        "method": "sutherland_hodgman",
    }


# ────────────────────────── features 6-8 (crossings) ──────────────────────────

def _all_crossings(layout):
    """Proper crossings between routes of distinct edges.

    Adjacent edges (sharing a node) are excluded, as are intersections within
    EPS of a shared route endpoint.  Intra-route self-crossings are not
    counted (v1 limitation, documented).
    """
    crossings = []
    m = len(layout.edges)
    for i in range(m):
        for j in range(i + 1, m):
            ei, ej = layout.edges[i], layout.edges[j]
            shared = {ei["a"], ei["b"]} & {ej["a"], ej["b"]}
            if shared:
                continue
            loop_involved = bool(ei["loops"] or ej["loops"])
            for si, (a1, b1) in enumerate(_seg_iter(ei["pts"])):
                for sj, (a2, b2) in enumerate(_seg_iter(ej["pts"])):
                    pt = _seg_proper_cross(a1, b1, a2, b2)
                    if pt is None:
                        continue
                    crossings.append({
                        "point": pt,
                        "edges": (i, j),
                        "segments": (si, sj),
                        "loop_involved": loop_involved,
                        "segs": ((a1, b1), (a2, b2)),
                    })
    crossings.sort(key=lambda c: (round(c["point"][0], 6), round(c["point"][1], 6),
                                  c["edges"][0], c["edges"][1]))
    return crossings


def _seg_iter(pts):
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _feat_crossings(layout):
    crossings = _all_crossings(layout)
    total = len(crossings)
    loop_total = sum(1 for c in crossings if c["loop_involved"])
    angles = [_seg_angle_deg(c["segs"][0][0], c["segs"][0][1],
                             c["segs"][1][0], c["segs"][1][1]) for c in crossings]
    angles = [a for a in angles if a is not None]
    return {
        "crossing_count": {"total": total},
        "loop_edge_crossing_count": {"total": loop_total},
        "min_crossing_angle_deg": {
            "min": _r(min(angles)) if angles else None,
            "crossings_with_angle": len(angles),
        },
    }


# ────────────────────── features 9-10 (symmetry, RFC §15.1) ──────────────────────

def _adjacency(layout):
    """Polarity-labeled undirected adjacency (sorted, deterministic)."""
    adj = {nid: [] for nid in layout.ids}
    for e in layout.edges:
        adj[e["a"]].append((e["b"], e["polarity"]))
        adj[e["b"]].append((e["a"], e["polarity"]))
    for nid in adj:
        adj[nid].sort()
    return adj


def _node_signature(adj, nid):
    lst = adj[nid]
    return (len(lst), tuple(sorted(pol for _, pol in lst)))


def _has_edge(adj, u, v, pol):
    return (v, pol) in adj.get(u, [])


def _automorphisms(layout, adj, cap):
    """Enumerate polarity-preserving graph automorphisms (backtracking).

    Deterministic: fixed node order (sorted ids), candidates tried in sorted
    id order.  The identity is excluded from results.
    """
    ids = layout.ids
    order = list(ids)
    sig = {nid: _node_signature(adj, nid) for nid in ids}
    results = []
    mapping = {}
    used = set()

    def bt(idx):
        if len(results) >= cap:
            return
        if idx == len(order):
            if any(mapping[v] != v for v in order):
                results.append(dict(mapping))
            return
        v = order[idx]
        for u in ids:
            if u in used or sig[u] != sig[v]:
                continue
            ok = True
            for (nbr, pol) in adj[v]:
                w = mapping.get(nbr)
                if w is not None and not _has_edge(adj, u, w, pol):
                    ok = False
                    break
            if ok:
                mapping[v] = u
                used.add(u)
                bt(idx + 1)
                del mapping[v]
                used.discard(u)
                if len(results) >= cap:
                    return
    bt(0)
    return results


def _fit_isometry(src_pts, dst_pts):
    """Closed-form 2D fit of a reflection-allowed isometry (no SVD needed).

    residual(θ) = C − 2(P·cosθ + Q·sinθ) with the optimum in closed form.
    Returns (residual_mean, is_reflection, theta, pivot) where the transform
    is  p -> R·(p − src_centroid) + dst_centroid.
    """
    n = len(src_pts)
    scx = fsum(p[0] for p in src_pts) / n
    scy = fsum(p[1] for p in src_pts) / n
    dcx = fsum(p[0] for p in dst_pts) / n
    dcy = fsum(p[1] for p in dst_pts) / n
    A = [(p[0] - scx, p[1] - scy) for p in src_pts]
    B = [(p[0] - dcx, p[1] - dcy) for p in dst_pts]
    c_norm = fsum(a[0] * a[0] + a[1] * a[1] for a in A)
    # rotation variant: R(θ) = [[c,-s],[s,c]]
    Pr = fsum(B[i][0] * A[i][0] + B[i][1] * A[i][1] for i in range(n))
    Qr = fsum(B[i][0] * A[i][1] - B[i][1] * A[i][0] for i in range(n))
    # reflection variant: R(θ) = [[c,s],[s,-c]]
    Pf = fsum(B[i][0] * A[i][0] - B[i][1] * A[i][1] for i in range(n))
    Qf = fsum(B[i][0] * A[i][1] + B[i][1] * A[i][0] for i in range(n))
    mr = hypot(Pr, Qr)
    mf = hypot(Pf, Qf)
    c_res = c_norm + fsum(b[0] * b[0] + b[1] * b[1] for b in B)
    if mf > mr:
        theta = atan2(Qf, Pf)
        resid = (c_res - 2.0 * mf) / n
        return resid, True, theta, (dcx, dcy)
    theta = atan2(Qr, Pr)
    resid = (c_res - 2.0 * mr) / n
    return resid, False, theta, (dcx, dcy)


def _fit_reflection(src_pts, dst_pts):
    """Pure-reflection fit (mirror axis); returns (residual, axis_deg, pivot)."""
    resid, is_ref, theta, pivot = _fit_isometry(src_pts, dst_pts)
    if not is_ref:
        # force the reflection variant
        n = len(src_pts)
        scx = fsum(p[0] for p in src_pts) / n
        scy = fsum(p[1] for p in src_pts) / n
        dcx = fsum(p[0] for p in dst_pts) / n
        dcy = fsum(p[1] for p in dst_pts) / n
        A = [(p[0] - scx, p[1] - scy) for p in src_pts]
        B = [(p[0] - dcx, p[1] - dcy) for p in dst_pts]
        Pf = fsum(B[i][0] * A[i][0] - B[i][1] * A[i][1] for i in range(n))
        Qf = fsum(B[i][0] * A[i][1] + B[i][1] * A[i][0] for i in range(n))
        c_res = fsum(a[0] ** 2 + a[1] ** 2 for a in A) + \
            fsum(b[0] ** 2 + b[1] ** 2 for b in B)
        theta = atan2(Qf, Pf)
        resid = (c_res - 2.0 * hypot(Pf, Qf)) / n
        pivot = (dcx, dcy)
    # reflection matrix [[cos θ, sin θ],[sin θ, −cos θ]] = mirror about a line
    # through the pivot with direction angle θ/2.
    return resid, _r(math.degrees(theta / 2.0) % 180.0, 6), pivot


def _bridges(layout):
    """Bridge edges of the undirected simple graph (iterative low-link)."""
    ids = layout.ids
    adj = {nid: set() for nid in ids}
    for e in layout.edges:
        adj[e["a"]].add(e["b"])
        adj[e["b"]].add(e["a"])
    disc, low = {}, {}
    bridges = set()
    timer = [0]
    for root in ids:
        if root in disc:
            continue
        stack = [(root, None, iter(sorted(adj[root])))]
        disc[root] = low[root] = timer[0]
        timer[0] += 1
        while stack:
            v, parent, it = stack[-1]
            advanced = False
            for w in it:
                if w == parent:
                    parent = None
                    continue
                if w not in disc:
                    disc[w] = low[w] = timer[0]
                    timer[0] += 1
                    stack.append((w, v, iter(sorted(adj[w]))))
                    advanced = True
                    break
                else:
                    low[v] = min(low[v], disc[w])
            if not advanced:
                stack.pop()
                if stack:
                    pv = stack[-1][0]
                    low[pv] = min(low[pv], low[v])
                    if low[v] > disc[pv]:
                        bridges.add(frozenset((pv, v)))
    return bridges


def _dir_keep_ratios(layout, mapping):
    """Direction/polarity preservation ratios of a candidate mapping."""
    total = len(layout.edges)
    if total == 0:
        return 1.0, 1.0
    pairs = {(e["a"], e["b"]) for e in layout.edges}
    adjset = {(e["a"], e["b"], e["polarity"]) for e in layout.edges}
    dir_ok = 0
    pol_ok = 0
    for e in layout.edges:
        ma, mb = mapping.get(e["a"]), mapping.get(e["b"])
        if (ma, mb, e["polarity"]) in adjset:
            dir_ok += 1
            pol_ok += 1
        elif (ma, mb) in pairs or (mb, ma) in pairs:
            dir_ok += 1
    return dir_ok / total, pol_ok / total


def _feat_symmetry(layout):
    """Features 9-10: automorphism-geometric symmetry residual + mirror axis.

    RFC §15.1: five-field struct for approximate symmetry; edge deletion is
    filtered (non-ring, non-bridge only) and confidence is monotone in the
    deleted-structure cost.
    """
    adj = _adjacency(layout)
    autos = _automorphisms(layout, adj, AUTO_MAP_CAP)
    ring_nodes = set()
    for lp in _extract_loops(layout):
        ring_nodes.update(lp["nodes"])
    bridges = _bridges(layout)
    edge_cost_total = float(len(layout.edges))

    best_full = None  # (residual, mapping, is_ref, theta, pivot)
    for mapping in autos:
        src = [layout.pos[v] for v in layout.ids]
        dst = [layout.pos[mapping[v]] for v in layout.ids]
        resid, is_ref, theta, pivot = _fit_isometry(src, dst)
        if best_full is None or resid < best_full[0]:
            best_full = (resid, mapping, is_ref, theta, pivot)

    five_full = None
    residual = None
    mirror = None
    if best_full is not None:
        resid, mapping, is_ref, theta, pivot = best_full
        coverage = sum(1 for v in layout.ids if mapping[v] != v) / len(layout.ids)
        dir_r, pol_r = _dir_keep_ratios(layout, mapping)
        five_full = {
            "deleted_edge_costs": [],
            "coverage": _r(coverage),
            "dir_keep_ratio": _r(dir_r),
            "polarity_keep_ratio": _r(pol_r),
            "confidence": _r(coverage * dir_r * pol_r),
        }
        residual = resid
        # mirror axis: pure-reflection fit over the same pairing
        src = [layout.pos[v] for v in layout.ids]
        dst = [layout.pos[mapping[v]] for v in layout.ids]
        mresid, axis_deg, mpivot = _fit_reflection(src, dst)
        mirror = {
            "residual": _r(mresid),
            "axis_deg": axis_deg,
            "pivot": [_r(mpivot[0]), _r(mpivot[1])],
            "fallback": "none",
        }

    # approximate (single-edge deletion) symmetry search
    best_approx = None
    if len(layout.edges) > 0:
        cands = []
        for idx, e in enumerate(layout.edges):
            if e["loops"]:
                continue  # never delete ring edges (RFC §15.1 filter)
            if frozenset((e["a"], e["b"])) in bridges:
                continue  # never delete bridges
            cands.append((e["a"], e["b"], idx, e["polarity"]))
        cands.sort()
        cands = cands[:AUTO_DEL_CAP]
        for (a, b, idx, pol) in cands:
            sub_edges = [e for k, e in enumerate(layout.edges) if k != idx]
            sub = _sub_layout(layout, sub_edges)
            sub_adj = _adjacency(sub)
            for mapping in _automorphisms(sub, sub_adj, AUTO_DEL_MAP_CAP):
                moved = sum(1 for v in sub.ids if mapping[v] != v)
                if moved == 0:
                    continue
                coverage = moved / len(sub.ids)
                dir_r, pol_r = _dir_keep_ratios(sub, mapping)
                cost = 1.0
                conf = coverage * dir_r * pol_r / (1.0 + cost / edge_cost_total)
                if best_approx is None or conf > best_approx["confidence"]:
                    best_approx = {
                        "deleted_edge_costs": [cost],
                        "coverage": _r(coverage),
                        "dir_keep_ratio": _r(dir_r),
                        "polarity_keep_ratio": _r(pol_r),
                        "confidence": _r(conf),
                        "deleted_edge": [a, b],
                    }
    return {
        "automorphism_symmetry_residual": {
            "residual": _r(residual),
            "automorphisms_found": len(autos),
            "five_fields": five_full,
            "approximate_five_fields": best_approx,
            "note": "confidence weights pending data calibration (RFC §15.1)",
        },
        "mirror_axis_residual": mirror,
    }


class _sub_layout(Layout):
    """Layout view over a subset of edges (nodes/canvas shared)."""

    def __init__(self, base, edges):
        self.ids = base.ids
        self.pos = base.pos
        self.card_w = base.card_w
        self.card_h = base.card_h
        self.vx, self.vy, self.vw, self.vh = base.vx, base.vy, base.vw, base.vh
        self.card_h_default = base.card_h_default
        self.clearance = base.clearance
        self.edges = edges
        self.degree = {nid: 0 for nid in self.ids}
        for e in self.edges:
            self.degree[e["a"]] += 1
            self.degree[e["b"]] += 1


# ────────────────────── features 11-18 (distribution / canvas) ──────────────────────

def _feat_edge_stats(layout):
    lens = [_dist(layout.pos[e["a"]], layout.pos[e["b"]]) for e in layout.edges]
    cv = _cv(lens)
    ratio = None
    if lens and min(lens) > EPS:
        ratio = max(lens) / min(lens)
    return {
        "edge_length_cv": {"cv": _r(cv), "n_edges": len(lens)},
        "max_min_edge_ratio": {"ratio": _r(ratio)},
    }


def _feat_angular_resolution(layout):
    best = None
    per_node = []
    for nid in layout.ids:
        angs = []
        for e in layout.edges:
            if e["a"] == nid:
                p = layout.pos[e["b"]]
            elif e["b"] == nid:
                p = layout.pos[e["a"]]
            else:
                continue
            angs.append(math.degrees(atan2(p[1] - layout.pos[nid][1],
                                           p[0] - layout.pos[nid][0])) % 360.0)
        angs.sort()
        if len(angs) >= 2:
            local = min((angs[(k + 1) % len(angs)] - angs[k]) % 360.0
                        for k in range(len(angs)))
            local = min(local, 360.0 - local) if local == 0 else local
            per_node.append({"node": nid, "min_gap_deg": _r(local)})
            if best is None or local < best:
                best = local
    return {
        "angular_resolution_deg": {
            "min": _r(best),
            "per_node": per_node,
        },
    }


def _feat_spacing(layout):
    ids = layout.ids
    n = len(ids)
    nn = []
    min_pair = None
    for i, a in enumerate(ids):
        dists = sorted(_dist(layout.pos[a], layout.pos[b]) for b in ids if b != a)
        if dists:
            nn.append(dists[0])
        if dists and (min_pair is None or dists[0] < min_pair):
            min_pair = dists[0]
    diag = layout.diagonal
    ratio = (min_pair / diag) if (min_pair is not None and diag > EPS) else None
    return {
        "node_spacing_cv": {"cv": _r(_cv(nn)), "n_nodes": n},
        "min_spacing_diagonal_ratio": {"ratio": _r(ratio), "min_spacing_px": _r(min_pair)},
    }


def _feat_bends(layout):
    bends = 0
    curv_terms = []
    for e in layout.edges:
        pts = e["pts"]
        ta = _turn_angles_deg(pts)
        bends += len(ta)
        curv_terms.extend(ta)
    return {
        "bend_count_total_curvature": {
            "bend_count": bends,
            "total_curvature_deg": _r(fsum(curv_terms)),
        },
    }


def _feat_centroid_hub(layout):
    ids = layout.ids
    total_area = fsum(layout.card_area(nid) for nid in ids)
    if total_area < EPS:
        return {"visual_centroid_offset": {"ratio": None},
                "hub_centroid_distance": {"ratio": None}}
    cx = fsum(layout.pos[nid][0] * layout.card_area(nid) for nid in ids) / total_area
    cy = fsum(layout.pos[nid][1] * layout.card_area(nid) for nid in ids) / total_area
    ccx = layout.vx + layout.vw / 2.0
    ccy = layout.vy + layout.vh / 2.0
    off = hypot(cx - ccx, cy - ccy)
    diag = layout.diagonal
    max_deg = max(layout.degree[nid] for nid in ids)
    hub = min(nid for nid in ids if layout.degree[nid] == max_deg)
    hd = _dist(layout.pos[hub], (cx, cy))
    return {
        "visual_centroid_offset": {
            "offset_px": _r(off),
            "ratio": _r(off / diag if diag > EPS else None),
            "area_centroid": [_r(cx), _r(cy)],
            "canvas_center": [_r(ccx), _r(ccy)],
        },
        "hub_centroid_distance": {
            "hub": hub,
            "hub_degree": max_deg,
            "distance_px": _r(hd),
            "ratio": _r(hd / diag if diag > EPS else None),
        },
    }


def _feat_voronoi(layout):
    """Voronoi cell areas clipped to the canvas rect (bisector half-plane clip)."""
    rect = [(layout.vx, layout.vy), (layout.vx + layout.vw, layout.vy),
            (layout.vx + layout.vw, layout.vy + layout.vh), (layout.vx, layout.vy + layout.vh)]
    ids = layout.ids
    areas = []
    per = []
    for nid in ids:
        cell = list(rect)
        p = layout.pos[nid]
        for oid in ids:
            if oid == nid:
                continue
            q = layout.pos[oid]
            nx, ny = q[0] - p[0], q[1] - p[1]
            mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0

            def keep(pt, nx=nx, ny=ny, mx=mx, my=my):
                return (pt[0] - mx) * nx + (pt[1] - my) * ny <= 0.0
            cell = _clip_halfplane(cell, keep)
            if not cell:
                break
        a = abs(_poly_area(cell))
        areas.append(a)
        per.append({"node": nid, "cell_area": _r(a)})
    return {
        "voronoi_cell_area_cv": {
            "cv": _r(_cv(areas)) if areas else None,
            "per_node": per,
        },
    }


def _rects_union_area(layout):
    """Exact union area of node card rectangles (coordinate compression)."""
    xs = set()
    ys = set()
    rects = []
    for nid in layout.ids:
        cx, cy, hw, hh = layout.rect(nid)
        xs.add(cx - hw)
        xs.add(cx + hw)
        ys.add(cy - hh)
        ys.add(cy + hh)
        rects.append((cx - hw, cy - hh, cx + hw, cy + hh))
    xs = sorted(xs)
    ys = sorted(ys)
    if len(xs) < 2 or len(ys) < 2:
        return 0.0, None, None
    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            mx = (xs[i] + xs[i + 1]) / 2.0
            my = (ys[j] + ys[j + 1]) / 2.0
            for (x1, y1, x2, y2) in rects:
                if x1 <= mx <= x2 and y1 <= my <= y2:
                    total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
                    break
    bx1 = min(r[0] for r in rects)
    by1 = min(r[1] for r in rects)
    bx2 = max(r[2] for r in rects)
    by2 = max(r[3] for r in rects)
    return total, (bx2 - bx1), (by2 - by1)


def _feat_canvas(layout):
    union, bw, bh = _rects_union_area(layout)
    canvas_area = layout.vw * layout.vh
    fill = union / canvas_area if canvas_area > EPS else None
    aspect = bw / bh if (bw and bh and bh > EPS) else None
    dev = abs(aspect - 1.0) if aspect is not None else None
    return {
        "canvas_fill_and_aspect": {
            "fill_rate": _r(fill),
            "content_bbox": [_r(bw), _r(bh)],
            "aspect_ratio": _r(aspect),
            "aspect_deviation_from_square": _r(dev),
        },
    }


def _feat_soft_clearance(layout):
    """Feature 21: soft clearance margin (min route-to-foreign-card gap)."""
    terms = []
    worst = None
    for e in layout.edges:
        endpoints = {e["a"], e["b"]}
        segs = _seg_iter(e["pts"])
        for nid in layout.ids:
            if nid in endpoints:
                continue
            cx, cy, hw, hh = layout.rect(nid)
            d = min(_seg_rect_dist(a, b, cx, cy, hw, hh) for (a, b) in segs)
            terms.append(d)
            if worst is None or d < worst[0]:
                worst = (d, e["orig_index"], nid)
    margin = None
    if terms:
        mn = min(terms)
        margin = mn - layout.clearance
    return {
        "bend_curvature_soft_clearance": {
            "min_gap_px": _r(min(terms)) if terms else None,
            "soft_margin_px": _r(margin),
            "clearance_threshold_px": layout.clearance,
            "worst_pair": ([_edge_key(layout, worst[1]), worst[2]] if worst else None),
        },
    }


def _edge_key(layout, orig_index):
    for e in layout.edges:
        if e["orig_index"] == orig_index:
            return [e["a"], e["b"]]
    return None


# ────────────────────── RFC §15.2 alignment + stability slot ──────────────────────

def _feat_alignment(layout):
    """Anchor-grouping max coverage (RFC §15.2).

    Anchors = card centers + route endpoints.  Candidate axes: 0/45/90/135°.
    Tolerance = ALIGN_TOL_FRAC * min(canvas_w, canvas_h).  Greedy grouping:
    anchors sorted by projected coordinate (ties by anchor id), fixed-order
    scan; a group counts only with >= ALIGN_MIN_GROUP anchors; each anchor
    belongs to at most one group.
    """
    anchors = []
    for nid in layout.ids:
        x, y = layout.pos[nid]
        anchors.append((x, y, "card:%s" % nid))
    for ei, e in enumerate(layout.edges):
        for which in ("a", "b"):
            p = e["pts"][0] if which == "a" else e["pts"][-1]
            anchors.append((p[0], p[1], "edge:%d:%s" % (ei, which)))
    tol = ALIGN_TOL_FRAC * min(layout.vw, layout.vh)
    total = len(anchors)
    per_axis = []
    best = None
    for axis_deg in ALIGN_AXES_DEG:
        t = math.radians(axis_deg)
        ct, st = math.cos(t), math.sin(t)
        proj = sorted((a[0] * ct + a[1] * st, a[2]) for a in anchors)
        groups = []
        cur = None
        for (s, aid) in proj:
            if cur is not None and s - cur[0] <= tol:
                cur[1].append(aid)
            else:
                if cur is not None:
                    groups.append(cur)
                cur = (s, [aid])
        if cur is not None:
            groups.append(cur)
        covered = fsum(len(g[1]) for g in groups if len(g[1]) >= ALIGN_MIN_GROUP)
        cov = covered / total if total else None
        per_axis.append({"axis_deg": axis_deg, "coverage": _r(cov),
                         "groups_ge3": sum(1 for g in groups if len(g[1]) >= ALIGN_MIN_GROUP)})
        if best is None or (cov is not None and cov > best):
            best = cov
    return {
        "alignment_coverage": {
            "max_coverage": _r(best),
            "tolerance_px": _r(tol),
            "anchors": total,
            "per_axis": per_axis,
            "note": "RFC §15.2: tolerance normalized by canvas scale (v1 initial value)",
        },
    }


def _feat_stability():
    return {
        "layout_stability": {
            "value": None,
            "applicable": False,
            "note": "increment-only feature (Appendix A); static extraction v1 reports null",
        },
    }


# ────────────────────────── entry points ──────────────────────────

def extract_features(doc):
    """layout.json dict -> full feature document (deterministic)."""
    layout = Layout(doc)
    loops = _extract_loops(layout)
    loop_feats = _feat_loop_geometry(layout, loops)
    loop_feats.pop("_loop_details")
    features = {}
    features.update(loop_feats)
    features.update(_feat_crossings(layout))
    features.update(_feat_symmetry(layout))
    features.update(_feat_edge_stats(layout))
    features.update(_feat_angular_resolution(layout))
    features.update(_feat_spacing(layout))
    features.update(_feat_bends(layout))
    features.update(_feat_centroid_hub(layout))
    features.update(_feat_voronoi(layout))
    features.update(_feat_canvas(layout))
    features.update(_feat_soft_clearance(layout))
    features.update(_feat_alignment(layout))
    features.update(_feat_stability())

    missing = [k for k in FEATURE_KEYS if k not in features]
    if missing:
        raise FeatureError("internal error: missing features %r" % missing)
    return {
        "schema": SCHEMA,
        "canvas": {
            "viewBox": [layout.vx, layout.vy, layout.vw, layout.vh],
            "diagonal": _r(layout.diagonal),
        },
        "counts": {
            "nodes": len(layout.ids),
            "edges": len(layout.edges),
            "loops": len(loops),
        },
        "clearance_px": layout.clearance,
        "determinism": {
            "summation": "math.fsum",
            "traversal": "sorted ids / sorted edges",
            "rng": "none",
        },
        "features": features,
    }


def features_to_json(feature_doc):
    return json.dumps(feature_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m stdraw.features",
        description="Extract 21 deterministic layout features from a layout.json")
    ap.add_argument("layout_json", help="path to layout.json (delivery coordinates)")
    ap.add_argument("--out", help="write feature JSON here (default: stdout)")
    args = ap.parse_args(argv)
    with open(args.layout_json, "r", encoding="utf-8") as f:
        doc = json.load(f)
    doc_out = extract_features(doc)
    js = features_to_json(doc_out)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(js)
    else:
        sys.stdout.write(js)
    return 0


if __name__ == "__main__":
    sys.exit(main())
