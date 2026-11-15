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

Certificate caliber (mode "radial", recalibrated 2026-11-15 against the
manual ground truth -- jacky hand-dragged fan-d12/fan-d17, exported via
"Export layout", stored under benchmarks/manual/):
  - HUB center deviation <= 2px (engine invariant: the hub sits on the
    declared ring center) AND hub-vs-ring-centroid deviation <= 24px
    (manual band: 6.2/18.9px on the two fixtures);
  - azimuth equal-spacing CV <= 0.50 (manual band: 0.486 fan-d12 /
    0.235 fan-d17 -- the former 0.05 gate REJECTED the manual ground
    truth itself, so the caliber now reads the fixtures, not the old
    engine's quantization floor);
  - radius CV <= 0.15 (manual: 0.122 / 0.081), long-edge rate = 0
    (manual: no edge longer than 2x the median on either fixture);
  - min card pair rect-gap >= 6px (manual minimum: 6px fan-d17 -- jacky
    packs tightly to keep total spoke length minimal; the chord-based
    ring radius is retired for the single-ring path);
  - total-edge fit: mean spoke length <= 1.25x the closed-form minimal
    ring radius (manual ratios: 1.227 fan-d12 / 0.996 fan-d17 -- "all
    edges as short as possible" once symmetry/uniformity hold).

Ring placement (recalibrated): the ring radius is the MINIMAL uniform
radius satisfying box-aware clearance (rect-gap caliber, PACK_GAP) for
every adjacent azimuth pair plus the hub clearance -- NOT the old
chord-based circular-packing need.  Measured on the fan family this
reproduces jacky's manual packing almost exactly (fan-d17: closed-form
minimum ~283px vs manual mean spoke 282px; the old conservative caliber
sat at 414px, +46% total edge length).  A double ring now only appears
when even the box-aware minimum exceeds the radius bound (dormant on
the whole n<=20 fan family); its interleaved legacy caliber is kept
verbatim for that over-bound fallback.
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
# dense-mode ring knobs (dense card, form-correctness gate 2026-11-15):
# the dense fan family delivers as a SINGLE large ring.  The spoke-to-card
# corridor needs lateral >= half-width(48) + 16px, and lateral = half chord
# = 48 + gap/2, so the ring adjacency gap widens 36 -> 56 (clearance
# ~22px, which also survives the nearest-standard-anchor tilt of the
# leaf-end snap); the radius bound extends accordingly -- a big clean
# sunburst beats a double ring (two equal-spaced co-prime grids ALWAYS
# near-align: min angular distance <= gcd-step/2, measured fan-d17 outer
# spoke pressed 12.6px past the inner box) and beats the layered row
# fallback (operator form gate).
DENSE_RING_ADJ_GAP = 56.0
RADIUS_MAX_DENSE = 600.0
RING_STEP = 190            # inner/outer ring radius separation (card 44 + corridors)
                           # (legacy caliber, non-dense double rings)
RING_STEP_DENSE = 120      # dense-era separation: with the gap-azimuth stagger
                           # (dense-only, form-correctness gate) same-ray box
                           # separation is no longer the binding constraint --
                           # the spoke corridor is; 120 = card 44 + corridor
                           # 76 keeps the fallback ring inside the bound.
INNER_FRACTIONS = (1.42, 1.30, 1.55, 1.18, 1.70, 1.06)   # outward along the anchor azimuth
_INNER_FS = (0.42, 0.34, 0.50, 0.26, 0.58, 0.18, 0.66)   # in-ring fallback fractions
_ANGLE_DS = (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0)

# -- manual-calibrated form calibers (2026-11-15; single source for the
#    placement, the check.py gate 9 battery and the metrics.py certificate
#    gates; every threshold is derived from the two manual fixtures --
#    benchmarks/manual/fan-d12/fan-d17-manual-layout.json -- as
#    "manual value rounded up to the next 0.5/1 band edge") --
PACK_GAP = 8.0              # placement pack target: manual min rect-gap 6px
                            # + the 2px grid guard (the placement must never
                            # land UNDER the manual floor after quantization)
RADIAL_MIN_PAIR_GAP = 6.0   # form gate: min card pair rect-gap (manual
                            # minimum: 6px fan-d17 / 12px fan-d12)
RADIAL_AZ_CV_MAX = 0.50     # manual azimuth CV: 0.4855 (d12) / 0.2352 (d17)
RADIAL_RADIUS_CV_MAX = 0.15 # manual radius CV: 0.1222 (d12) / 0.0812 (d17)
RADIAL_CENTROID_DEV_MAX = 24.0  # manual hub-vs-ring-centroid dev: 18.9 (d12)
RADIAL_TOTAL_EDGE_FIT = 1.25    # manual mean-spoke/min-radius ratio:
                                # 1.227 (d12) / 0.996 (d17)
RADIAL_LONG_EDGE_FACTOR = 2.0   # "no many long lines": an edge longer than
                                # 2x the median is a long edge; manual rate 0
                                # on both fixtures -> gate rate == 0
RADIAL_BUMP_STEPS = 30          # trial-gate radius ladder: +2px per step,
                                # deterministic give-up ceiling (+60px)


def min_ring_radius_box(ring, widths, hub_w, card_h, pack_gap=PACK_GAP):
    """Minimal uniform ring radius under box-aware clearance (manual
    calibration 2026-11-15).

    Every adjacent azimuth pair (uniform 2*pi/k steps) must satisfy the
    rect-gap caliber max(gap_x, gap_y) >= pack_gap, and every spoke must
    clear the hub card by HUB_GAP.  Both constraints are linear in r for a
    uniform circle, so the closed form below is exact (no iteration, no
    RNG).  This replaces the chord-based circular-packing need for the
    single-ring path: the chord caliber ignored card orientation (a
    vertically stacked side pair only needs dy >= card_h + gap, not the
    full chord width), which is exactly the slack jacky's manual layouts
    use to keep total spoke length minimal.
    """
    k = len(ring)
    if k < 3:
        return float(RADIUS_MIN)
    delta = 2 * math.pi / k
    half = math.sin(delta / 2)
    need = float(RADIUS_MIN)
    for i in range(k):
        wa = widths.get(ring[i], 96)
        wb = widths.get(ring[(i + 1) % k], 96)
        th1 = _azimuth(i, k)
        th2 = _azimuth((i + 1) % k, k)
        mid = math.atan2(math.sin(th1) + math.sin(th2),
                         math.cos(th1) + math.cos(th2))
        s, c = abs(math.sin(mid)), abs(math.cos(mid))
        # rect-gap >= pack_gap needs gap_x >= pack OR gap_y >= pack; both
        # gaps grow linearly with r, so the pair bound is the min of the
        # two per-axis bounds (eps guards the axis-aligned singularities)
        rx = ((wa + wb) / 2 + pack_gap) / (2 * half * s + 1e-9)
        ry = (card_h + pack_gap) / (2 * half * c + 1e-9)
        need = max(need, min(rx, ry))
        # hub clearance along the spoke (same rect-gap caliber)
        w = widths.get(ring[i], 96)
        sx, cx_ = abs(math.sin(th1)), abs(math.cos(th1))
        hx = ((hub_w + w) / 2 + HUB_GAP) / (cx_ + 1e-9)
        hy = (card_h + HUB_GAP) / (sx + 1e-9)
        need = max(need, min(hx, hy))
    return need


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


def _ring_radius(nodes_on_ring, widths, hub_w, adj_gap=ADJ_GAP):
    """Radius need: adjacent ring cards >= (w_u+w_v)/2 + adj_gap center
    distance AND every spoke clears the hub card. Above the upper bound the
    caller splits into two rings."""
    k = len(nodes_on_ring)
    need = 0.0
    for i in range(k):
        wu = widths.get(nodes_on_ring[i], 96)
        wv = widths.get(nodes_on_ring[(i + 1) % k], 96)
        need = max(need, (wu + wv) / 2 + adj_gap)
        need = max(need, (hub_w + wu) / 2 + HUB_GAP)
    if k < 3:
        need = max(need, RADIUS_MIN)
    r = need / (2 * math.sin(math.pi / k)) if k >= 3 else RADIUS_MIN
    return max(RADIUS_MIN, r)


def _azimuth(i, k):
    return 2 * math.pi * i / k - math.pi / 2


def _q2(v):
    return int(round(v / 2)) * 2


def place_radial(plan, widths, card_h, cfg, adj, edges, dense_hub=None,
                 radius_floor=0.0):
    """Radial placement -> ({v: x}, {v: y}, meta). All-integer 2px grid,
    deterministic.

    dense_hub: dense-mode node id or None — dense graphs read the dense
    ring knobs (DENSE_RING_ADJ_GAP corridor caliber + RADIUS_MAX_DENSE
    bound) so the fan family delivers as a single clean ring.
    radius_floor: retry lever for the caller's trial gate (bump loop) —
    when a radius-bump retry needs more breathing room, the caller passes
    the previous radius + 2 and the ring re-centers on that floor.
    """
    hub = plan["hub"]
    ring = list(plan["ring"])
    k = len(ring)
    hub_w = widths.get(hub, 96)
    dense = dense_hub is not None and dense_hub == hub
    radius_max = RADIUS_MAX_DENSE if dense else RADIUS_MAX
    single_r = min_ring_radius_box(ring, widths, hub_w, card_h)
    if radius_floor:
        single_r = max(single_r, float(radius_floor))
    two_rings = single_r > radius_max
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
        r_in = _ring_radius(inner, widths, hub_w,
                            adj_gap=DENSE_RING_ADJ_GAP if dense else ADJ_GAP)
        r_out = r_in + (RING_STEP_DENSE if dense else RING_STEP)
        if r_out > radius_max + RING_STEP:
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
        if (dense and two_rings and len(seqs[0]) > 0 and seq is seqs[0]):
            # form-correctness (dense card, operator gate 2026-11-15): the
            # OUTER ring sits on the INNER ring's gap azimuths (+half inner
            # step).  Both rings starting at -90 deg aligned an outer leaf
            # onto an inner leaf's ray, so the straight hub spoke to the
            # outer leaf pressed straight through the inner box (measured:
            # fan-d17 L00 blocks the HUB->L01 spoke; the 40/45 deg grids
            # also drift to 5 deg near-alignments).  Dense graphs deliver
            # single-ring (RADIUS_MAX_DENSE), so this branch only guards a
            # dense over-bound fallback; non-dense double rings keep the
            # legacy equal-step azimuths byte-for-byte.
            ang = _azimuth(i, len(inner)) + math.pi / len(inner)
        else:
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


def form_metrics(nodes, card_h, radial_meta, edges):
    """Shared radial form-coherence battery (single source: check.py gate 9
    AND the metrics.py certificate gates read this; manual-calibrated
    2026-11-15, thresholds as module constants above).

    nodes: {v: {"x": .., "y": .., "w": ..}} (scene/v4 node dicts);
    radial_meta: the meta["radial"] block (hub/center/ring_nodes/
    ring_groups); edges: [(a, b), ...] graph edges.

    Returns a dict with (None when not computable -- callers gate on the
    values being present AND within band):
      hub_center_dev   hub card vs the declared ring center (px)
      centroid_dev     hub card vs the ring-card centroid (px)
      azimuth_cv       per-ring azimuth equal-spacing CV (max over rings)
      radius_cv        per-ring spoke-length CV (max over rings)
      long_edge_rate   share of edges longer than RADIAL_LONG_EDGE_FACTOR
                       x the median edge length
      min_pair_gap     minimum rect-gap over ALL card pairs (px)
      mean_edge        mean graph-edge node-center distance (px)
      fit_ratio        mean spoke length / closed-form minimal ring radius
    """
    hub = radial_meta.get("hub")
    rc = radial_meta.get("center")
    ring_nodes = radial_meta.get("ring_nodes") or []
    groups = radial_meta.get("ring_groups") or [ring_nodes]
    if hub not in nodes or not (isinstance(rc, list) and len(rc) == 2):
        return {}
    cx, cy = float(rc[0]), float(rc[1])
    hp = nodes[hub]
    hub_center_dev = math.hypot(hp["x"] - cx, hp["y"] - cy)
    flat = [v for g in groups for v in g if v in nodes]
    centroid_dev = None
    radius_cv = None
    if flat:
        gx = sum(nodes[v]["x"] for v in flat) / len(flat)
        gy = sum(nodes[v]["y"] for v in flat) / len(flat)
        centroid_dev = max(abs(hp["x"] - gx), abs(hp["y"] - gy))
    cvs, rcvs = [], []
    for g in groups:
        gsel = [v for v in g if v in nodes]
        if len(gsel) >= 3:
            cv = _cv_of([(nodes[v]["x"], nodes[v]["y"]) for v in gsel],
                        cx, cy)
            if cv is not None:
                cvs.append(cv)
            spokes = [math.hypot(nodes[v]["x"] - cx, nodes[v]["y"] - cy)
                      for v in gsel]
            md = sum(spokes) / len(spokes)
            if md:
                rcvs.append(math.sqrt(sum((s - md) ** 2 for s in spokes)
                                      / len(spokes)) / md)
    azimuth_cv = max(cvs) if cvs else None
    radius_cv = max(rcvs) if rcvs else None
    els = []
    for a, b in edges:
        if a in nodes and b in nodes:
            els.append(math.hypot(nodes[a]["x"] - nodes[b]["x"],
                                  nodes[a]["y"] - nodes[b]["y"]))
    long_edge_rate = None
    mean_edge = None
    if els:
        els_sorted = sorted(els)
        med = els_sorted[len(els) // 2] if len(els) % 2 else \
            (els_sorted[len(els) // 2 - 1] + els_sorted[len(els) // 2]) / 2
        long_edge_rate = (sum(1 for l in els
                              if l > RADIAL_LONG_EDGE_FACTOR * med)
                          / len(els))
        mean_edge = sum(els) / len(els)
    min_pair_gap = None
    vs = list(nodes)
    if len(vs) >= 2:
        gaps = []
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                a, b = nodes[vs[i]], nodes[vs[j]]
                dx = abs(a["x"] - b["x"]) - (a.get("w", 96)
                                             + b.get("w", 96)) / 2
                dy = abs(a["y"] - b["y"]) - card_h
                gaps.append(max(dx, dy))
        min_pair_gap = min(gaps)
    fit_ratio = None
    if flat and ring_nodes:
        widths = {v: nodes[v].get("w", 96) for v in flat}
        hub_w = hp.get("w", 96)
        r_min = min_ring_radius_box(ring_nodes, widths, hub_w, card_h)
        if r_min:
            spokes = [math.hypot(nodes[v]["x"] - cx, nodes[v]["y"] - cy)
                      for v in flat]
            fit_ratio = (sum(spokes) / len(spokes)) / r_min
    return {"hub_center_dev": hub_center_dev,
            "centroid_dev": centroid_dev,
            "azimuth_cv": azimuth_cv,
            "radius_cv": radius_cv,
            "long_edge_rate": long_edge_rate,
            "min_pair_gap": min_pair_gap,
            "mean_edge": mean_edge,
            "fit_ratio": fit_ratio}
