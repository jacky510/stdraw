# -*- coding: utf-8 -*-
"""Radial (hub-centered spoke) placement for star / fan graphs.

Design direction (owner ruling, 2026-11-15 proposal approved): "one node
emits many lines while the others have basically one each -- put the others
around the hub". Trigger detection (pure topology, deterministic, layout
free):

    hub := the max-degree node (tie -> smallest canonical id order)
    leaves := hub neighbors of degree 1

    radial := hub_deg >= 6 AND leaf_frac >= 0.5      (leaf_frac = |leaves| / hub_deg)
           OR hub_deg >= 10                          (large-fan backstop)

Measured safety margins on the whole corpus (61 graphs): max degree 8
(two steps from the hub_deg >= 10 backstop); among deg >= 6 hubs the
worst leaf_frac is 0.167 (3x from the 0.5 threshold); the strict and
loose branches both score zero corpus hits, so graphs that reach the
radial tier in the priority chain today never trigger (structural
zero drift for the layered corpus).

Placement (place_radial):
  - HUB at the canvas center; ring nodes (ALL hub neighbors, declaration
    order) evenly divide the full circle by azimuth (start -90 deg, then
    clockwise i*2*pi/k), each joined to the hub by one straight spoke;
    single ring while the radius need fits the rendering-ratio bound;
  - k >= 17 (or a radius need above the bound): two concentric rings,
    interleaved assignment (node i -> inner ring when i is even), each
    ring independently evenly divided over the FULL circle (the parity
    -alternation seam collision of a shared-step prototype is avoided by
    construction: different radii never collide, and independent equal
    division keeps the azimuth CV per ring);
  - residual nodes (not the hub, not on a ring, degree >= 1 -- e.g.
    branch chains hanging off a ring node): deterministic candidate
    family around the azimuth of their already-placed anchor (outward
    fractions first, then the in-ring inner fractions, then lateral
    angle offsets), scored by new straight-proxy crossings then
    collision freedom; no candidate -> InfeasibleRadial (the caller
    falls back to the existing path, byte-for-byte unchanged);
  - isolated nodes park on the top parking strip (same caliber as
    ringlayout).

Determinism: all coordinates are pure functions of the declaration order,
the fixed start angle and the 2px grid; no RNG. Trial gating and silent
fallback are the caller's job (layout_auto._radial_trial), same pattern
as ring/column/comb.

Certificate caliber (mode "radial"): HUB center deviation <= 2px, ring
center vs canvas geometric center <= 2px, azimuth equal-spacing CV
<= 0.05 (the ring equal-spacing CV caliber, rotation invariant).
"""
import math

from .ringlayout import (_adjacency, _seg_cross, InfeasibleRing as
                         _InfeasibleRingBase)

# radial infeasibility reuses the ring exception type so the caller can
# catch one shared fallback contract; the module alias keeps the docs honest.
InfeasibleRadial = _InfeasibleRingBase

HUB_DEG_MIN = 6            # branch 1: hub_deg >= 6
LEAF_FRAC_MIN = 0.5        # branch 1: leaf_frac >= 0.5
HUB_DEG_BACKSTOP = 10      # branch 2: large-fan backstop
RADIUS_MIN = 150
RADIUS_MAX = 340           # radial rendering-ratio bound (~340px per the
                           # approved proposal; fan-d16's single ring needs
                           # exactly 338 at the 36px card-gap target)
ADJ_GAP = 36               # ring adjacency margin = the 36px card-gap breathing
                           # target (GAP_TARGET; prototype radii d12=255/d16=338
                           # are exactly this need over the regular k-gon chord)
HUB_GAP = 36               # hub-card-to-ring-card margin along the spoke
DOUBLE_RING_K = 17         # legacy prototype threshold (kept for reference; the
                           # live split criterion is the radius need > RADIUS_MAX)
RING_STEP = 190            # inner/outer ring radius separation (card 44 + corridors)
INNER_FRACTIONS = (1.42, 1.30, 1.55, 1.18, 1.70, 1.06)   # outward along the anchor azimuth
_INNER_FS = (0.42, 0.34, 0.50, 0.26, 0.58, 0.18, 0.66)   # in-ring fallback fractions
_ANGLE_DS = (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0)


def detect_radial(graph, why=None):
    """Trigger detection. Returns a plan dict or None (no trigger).

    plan = {"hub": id, "hub_deg": int, "leaf_frac": float, "leaves": int,
            "ring": [hub neighbors in declaration order],
            "residuals": [remaining degree>=1 nodes], "deg0": [isolated]}

    why: optional dict -- receives a deterministic one-line reason for the
    outcome (mode decision trace).
    """
    nodes = list(graph.node_ids())
    edges = [(e.a, e.b) for e in graph.edges]
    adj, _ = _adjacency(edges)
    for v in nodes:
        adj.setdefault(v, set())
    if not edges:
        if why is not None:
            why["reason"] = "no edges -- no hub"
        return None
    hub = min(nodes, key=lambda v: (-len(adj[v]), v))
    hub_deg = len(adj[hub])
    if hub_deg < HUB_DEG_MIN:
        if why is not None:
            why["reason"] = f"hub_deg={hub_deg} < {HUB_DEG_MIN}"
        return None
    # declaration order = order of first appearance along the directed edge list
    ring = []
    for a, b in edges:
        if a == hub and b not in ring:
            ring.append(b)
        elif b == hub and a not in ring:
            ring.append(a)
    leaves = [v for v in ring if len(adj[v]) == 1]
    leaf_frac = len(leaves) / hub_deg
    ok = (hub_deg >= HUB_DEG_MIN and leaf_frac >= LEAF_FRAC_MIN) \
        or hub_deg >= HUB_DEG_BACKSTOP
    if not ok:
        if why is not None:
            why["reason"] = (f"hub_deg={hub_deg}, leaf_frac={leaf_frac:.3f} "
                             f"(need deg>={HUB_DEG_MIN} with frac>={LEAF_FRAC_MIN} "
                             f"or deg>={HUB_DEG_BACKSTOP})")
        return None
    rset = set(ring) | {hub}
    residuals = [v for v in nodes if v not in rset and adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if why is not None:
        why["reason"] = (f"star/fan: hub_deg={hub_deg}, leaves={len(leaves)}, "
                         f"leaf_frac={leaf_frac:.3f}")
    return {"hub": hub, "hub_deg": hub_deg, "leaf_frac": round(leaf_frac, 3),
            "leaves": len(leaves), "ring": ring, "residuals": residuals,
            "deg0": deg0}


def _ring_radius(nodes_on_ring, widths, hub_w):
    """Radius need: adjacent ring cards >= (w_u+w_v)/2 + ADJ_GAP center
    distance AND every spoke clears the hub card. Above the upper bound the
    caller splits into two rings."""
    k = len(nodes_on_ring)
    need = 0.0
    for i in range(k):
        wu = widths.get(nodes_on_ring[i], 96)
        wv = widths.get(nodes_on_ring[(i + 1) % k], 96)
        need = max(need, (wu + wv) / 2 + ADJ_GAP)
        need = max(need, (hub_w + wu) / 2 + HUB_GAP)
    if k < 3:
        need = max(need, RADIUS_MIN)
    r = need / (2 * math.sin(math.pi / k)) if k >= 3 else RADIUS_MIN
    return max(RADIUS_MIN, r)


def _azimuth(i, k):
    return 2 * math.pi * i / k - math.pi / 2


def _q2(v):
    return int(round(v / 2)) * 2


def place_radial(plan, widths, card_h, cfg, adj, edges):
    """Radial placement -> ({v: x}, {v: y}, meta). All-integer 2px grid,
    deterministic."""
    hub = plan["hub"]
    ring = list(plan["ring"])
    k = len(ring)
    hub_w = widths.get(hub, 96)
    single_r = _ring_radius(ring, widths, hub_w)
    two_rings = single_r > RADIUS_MAX
    if two_rings and k < 6:
        raise InfeasibleRadial(
            f"radius requirement {single_r:.0f}px exceeds the bound and "
            f"k={k} is too small to split into two rings")
    inner, outer = [], []
    if two_rings:
        # interleaved assignment: node i -> inner when i is even; each ring
        # independently evenly divides the FULL circle (different radii never
        # collide, and independent equal division keeps the per-ring azimuth
        # CV at the quantization floor)
        inner = [ring[i] for i in range(k) if i % 2 == 0]
        outer = [ring[i] for i in range(k) if i % 2 == 1]
        r_in = _ring_radius(inner, widths, hub_w)
        r_out = r_in + RING_STEP
        if r_out > RADIUS_MAX + RING_STEP:
            raise InfeasibleRadial(
                f"double-ring radius need {r_out:.0f}px exceeds the bound")
        radii = {v: (r_in if v in inner else r_out) for v in ring}
        ring_of = {v: (inner if v in inner else outer) for v in ring}
    else:
        r = single_r
        radii = {v: r for v in ring}
        ring_of = {v: ring for v in ring}
    seqs = [outer, inner] if two_rings else [ring]
    # canvas center: generous headroom for the ring + residuals on all sides
    r_max = max(radii.values()) if radii else RADIUS_MIN
    cx = int(r_max // 2) * 2
    cy = int((r_max + card_h // 2 + 40) // 2) * 2
    pos, y, angles = {}, {}, {}
    pos[hub], y[hub] = _q2(cx), _q2(cy)
    for v in ring:
        seq = ring_of[v]
        i = seq.index(v)
        ang = _azimuth(i, len(seq))
        angles[v] = ang
        rr = radii[v]
        pos[v] = _q2(cx + rr * math.cos(ang))
        y[v] = _q2(cy + rr * math.sin(ang))

    def _rect(v, px, py):
        w = widths.get(v, 96)
        return (px - w / 2, py - card_h / 2, px + w / 2, py + card_h / 2)

    placed = {v: _rect(v, pos[v], y[v]) for v in [hub] + ring}

    def _free(v, px, py, gap=18):
        rx0, ry0, rx1, ry1 = _rect(v, px, py)
        for ux0, uy0, ux1, uy1 in placed.values():
            if rx0 < ux1 + gap and ux0 < rx1 + gap and ry0 < uy1 + gap and uy0 < ry1 + gap:
                return False
        return True

    # straight-proxy segments for crossing scoring: spokes + ring adjacency chords
    segs = []
    hpos = (pos[hub], y[hub])
    for v in ring:
        segs.append((hpos, (pos[v], y[v]), frozenset((hub, v))))
    for seq in seqs:
        m = len(seq)
        for i in range(m):
            a, b = seq[i], seq[(i + 1) % m]
            segs.append(((pos[a], y[a]), (pos[b], y[b]), frozenset((a, b))))

    def _add_cross(px, py, v):
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
    # outward radial step ladder from the placed anchor (>= 120px keeps two
    # 96x44 cards apart along the ray; branch chains extend node by node)
    RESID_STEPS = (120, 160, 200, 240, 280, 320, 80)
    for v in sorted(plan["residuals"]):
        anchors = [u for u in sorted(adj[v]) if u in pos]
        # azimuth of the placed anchor relative to the hub center (works for
        # ring anchors and already-placed residual anchors alike, so chains
        # extend outward node by node)
        if anchors:
            a0 = anchors[0]
            ang0 = math.atan2(y[a0] - cy, pos[a0] - cx)
            base_r = math.hypot(pos[a0] - cx, y[a0] - cy)
        else:
            ang0, base_r = 0.0, r_max
        best = None
        for step in RESID_STEPS:
            for d in _ANGLE_DS:
                ang = ang0 + math.radians(d)
                rr = base_r + step
                px = _q2(cx + rr * math.cos(ang))
                py = _q2(cy + rr * math.sin(ang))
                if not _free(v, px, py):
                    continue
                cross = _add_cross(px, py, v)
                key = (cross, abs(d), step, px, py)
                if best is None or key < best[0]:
                    best = (key, px, py, step)
            if best is not None and best[0][0] == 0 and best[0][1] == 0.0:
                break
        if best is None:
            # last resort: in-ring inner fractions (the hub card and placed
            # cards reject collisions through _free)
            for f in _INNER_FS:
                for d in _ANGLE_DS:
                    ang = ang0 + math.radians(d)
                    px = _q2(cx + f * r_max * math.cos(ang))
                    py = _q2(cy + f * r_max * math.sin(ang))
                    if not _free(v, px, py):
                        continue
                    cross = _add_cross(px, py, v)
                    key = (cross, abs(d), abs(f - 0.42), px, py)
                    if best is None or key < best[0]:
                        best = (key, px, py, ("inner", f))
                if best is not None and best[0][0] == 0:
                    break
        if best is None:
            raise InfeasibleRadial(
                f"residual node {v} has no collision-free candidate")
        _, px, py, step = best
        pos[v], y[v] = px, py
        placed[v] = _rect(v, px, py)
        residual_pos[v] = (round(step, 3) if isinstance(step, (int, float))
                           else [step[0], round(step[1], 3)])
        for u in sorted(adj[v]):
            if u in pos:
                segs.append(((px, py), (pos[u], y[u]), frozenset((v, u))))
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = max(cfg.margin, cx - total / 2)
        for v in plan["deg0"]:
            pos[v] = _q2(cur + widths[v] / 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    meta = {
        "placement": "radial",
        "radial": {
            "hub": hub,
            "hub_deg": plan["hub_deg"],
            "leaf_frac": plan["leaf_frac"],
            "ring_nodes": list(ring),
            "ring_groups": [list(s) for s in seqs],
            "rings": 2 if two_rings else 1,
            "radius": int(round(r_max)),
            "inner_radius": int(round(min(radii.values()))) if radii else None,
            "center": [cx, cy],
            "residuals": dict(residual_pos),
        },
    }
    return pos, y, meta


def _cv_of(pts, cx, cy):
    angs = sorted(math.atan2(py - cy, px - cx) for px, py in pts)
    m = len(angs)
    gaps = []
    for i in range(m):
        d = angs[(i + 1) % m] - angs[i]
        if i == m - 1:
            d += 2 * math.pi
        gaps.append(d)
    md = sum(gaps) / m
    if not md:
        return None
    return math.sqrt(sum((d - md) ** 2 for d in gaps) / m) / md


def azimuth_cv(ring_nodes, pos, y, cx, cy):
    """Equal-spacing CV of the ring nodes' azimuths around (cx, cy)
    (successive angular gaps; the ring equal-spacing caliber, rotation
    invariant).

    ring_nodes: a flat node list (one ring) OR a list of per-ring node
    lists (double ring) -- multi-ring figures are judged PER RING (each
    ring independently equal-divides the full circle) and the result is
    the max over rings with >= 3 nodes. Requires >= 3 nodes per ring.
    """
    if ring_nodes and isinstance(ring_nodes[0], (list, tuple)):
        cvs = [_cv_of([(pos[v], y[v]) for v in g if v in pos], cx, cy)
               for g in ring_nodes]
        cvs = [c for c in cvs if c is not None]
        return max(cvs) if cvs else None
    pts = [(pos[v], y[v]) for v in ring_nodes if v in pos]
    if len(pts) < 3:
        return None
    return _cv_of(pts, cx, cy)
