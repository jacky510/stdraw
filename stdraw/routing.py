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
import contextvars
import math
import os
import sys
import itertools
from contextlib import contextmanager

from . import visibility as _vis
from . import gates as _gates
from .anchors import standard_anchors as _std_anchors

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


def _dbg(msg_fn):
    """Central STDRAW_SNAP_DEBUG stderr printer.

    Env switch checked dynamically at call time; msg_fn is a callable so
    lazily-built messages (and any routing stats they need) cost nothing
    when the switch is off. All snap-stage debug prints go through this
    one place.
    """
    if os.environ.get("STDRAW_SNAP_DEBUG"):
        print(msg_fn(), file=sys.stderr)


# -- loop-direction arc default (CLD drawing quality T10) ------------------
# Declared loops ride in through a context variable so that EVERY Router
# built inside the automatic candidate stage (placement trials, polish
# worlds, final routing and the repair passes) scores the same line-type
# preference; the manual (--from-layout) path never enters the context and
# keeps the legacy straight-first caliber (user styles win).
_LOOP_ARC_CTX = contextvars.ContextVar("stdraw_loop_arcs", default=None)


@contextmanager
def loop_arc_context(loops):
    """Scope in which Routers apply the loop-direction arc default for the
    given declared loops (list of Loop objects; None/[] = legacy caliber)."""
    tok = _LOOP_ARC_CTX.set(list(loops) if loops else None)
    try:
        yield
    finally:
        _LOOP_ARC_CTX.reset(tok)


def loop_arc_sides(centers, edges, loops):
    """Loop-direction arc default: preferred arc bulge sign per edge.

    centers: {id: (cx, cy)}; edges: [(a, b)] directed; loops: declared loops
    (objects with a ``nodes`` sequence).  Returns {edge idx: +1 | -1 | 0} in
    the router quad parameterization of the a->b chord:
      +1/-1 = bulge AWAY from the centroid of the union of the declared loops
              the edge belongs to (each loop reads as a closed curved ring);
       0    = loop member whose loop centroid lies on its chord line (side
              free, an arc is still preferred over a straight line).
    Edges that are not loop members, and every mutual pair (a<->b), are
    absent: non-loop lines stay straight and mutual pairs keep the lens /
    edge-placement-rules-v1 rule-8 contract unchanged.  Deterministic.
    """
    if not loops:
        return {}
    eset = set(edges)
    mutual = set()
    for a, b in edges:
        if a < b and (b, a) in eset:
            mutual.add((a, b))
    eidx = {}
    for i, e in enumerate(edges):
        eidx.setdefault(e, i)
    union = {}
    for lp in loops:
        seq = list(getattr(lp, "nodes", None) or [])
        if len(seq) < 3:
            continue
        ns = set(seq)
        for u, v in zip(seq, seq[1:] + seq[:1]):
            i = eidx.get((u, v))
            if i is None:
                i = eidx.get((v, u))     # loop declared against the edge direction
            if i is None or (min(u, v), max(u, v)) in mutual:
                continue
            union.setdefault(i, set()).update(ns)
    out = {}
    for i in sorted(union):
        ns = union[i]
        if not all(v in centers for v in ns):
            continue
        a, b = edges[i]
        ca, cb = centers[a], centers[b]
        vx, vy = cb[0] - ca[0], cb[1] - ca[1]
        d = math.hypot(vx, vy) or 1.0
        ux, uy = -vy / d, vx / d
        mx, my = (ca[0] + cb[0]) / 2.0, (ca[1] + cb[1]) / 2.0
        acc = 0.0
        for v in sorted(ns):
            acc += (centers[v][0] - mx) * ux + (centers[v][1] - my) * uy
        s = acc / len(ns)
        out[i] = 0 if abs(s) < 1e-6 else (-1 if s > 0 else 1)
    return out


def _bulge_sign(pa, pb, ctrl):
    """+1/-1: side of the pa->pb chord the quad ctrl point sits on (the
    router arc parameterization sign); 0 for a degenerate chord."""
    vx, vy = pb[0] - pa[0], pb[1] - pa[1]
    d = math.hypot(vx, vy)
    if d < 1e-9:
        return 0
    ux, uy = -vy / d, vx / d
    s = (ctrl[0] - (pa[0] + pb[0]) / 2.0) * ux + \
        (ctrl[1] - (pa[1] + pb[1]) / 2.0) * uy
    return 0 if abs(s) < 1e-9 else (1 if s > 0 else -1)


def _candidate_defects(info, clearance):
    """Human-readable defect list of one evaluated candidate (empty = all
    hard-gate terms clean)."""
    if info is None:
        return "rejected (own-box interior / off-border endpoint)"
    bad = []
    if info.get("press"):
        bad.append("presses %d box(es)" % info["press"])
    if info.get("cross"):
        bad.append("crosses %d routed line(s)" % info["cross"])
    mc = info.get("min_clear")
    if mc is not None and mc < clearance - 1e-6:
        bad.append("clearance deficit %.1fpx" % (clearance - mc))
    for end in ("a", "b"):
        ang = info.get("ang_" + end)
        if ang is not None and ang < ANCHOR_MIN_DEG:
            bad.append("%s-end anchor angle %.0f deg" % (end, ang))
    return "; ".join(bad) if bad else "clean"


def mutual_pair_members(edges, loops):
    """Edge indices of loop-member lines that belong to a mutual pair (a<->b):
    the part of the loop-member scope the loop-direction arc default leaves to
    the lens / rule-8 contract (loop_arc_sides keeps them out of arc_pref)."""
    if not loops:
        return set()
    have = set(edges)
    out = set()
    for lp in loops:
        seq = list(getattr(lp, "nodes", None) or [])
        if len(seq) < 2:
            continue
        for u, v in zip(seq, seq[1:] + seq[:1]):
            if (u, v) in have and (v, u) in have:
                out.update(i for i, e in enumerate(edges)
                           if e == (u, v) or e == (v, u))
    return out


def loop_arc_audit(nodes, edges, loops, routes, clearance=CLEARANCE, pitch=80,
                   templated=()):
    """Honest record of the loop-direction arc default on the DELIVERED
    routes (certificate ``loop_arcs`` block; report item, not a gate).

    Every loop-member line that is not a mutual pair is expected to be
    delivered as an arc bulging away from its loop centroid.  For each line
    that is not, the preferred-side arc (and, when the delivery is a
    detour, the straight line) is re-scored against the delivered routes
    of all OTHER lines and its hard-gate defects are recorded verbatim --
    the fallback reason is measured, never assumed.  A mutual-pair loop
    member is outside that scope (its geometry belongs to the lens / rule-8
    contract, so there is no preferred side to score); when it is delivered
    as a non-arc it is still listed in ``fallbacks`` and counted in
    ``mutual_pair_non_arc``, so the record accounts for every non-arc
    loop-member route that line_kind_counts reports.  ``templated``: edge
    indices whose geometry a constructed placement engine delivers by its
    own mode template (the candidate pool is skipped there); they are
    recorded as template geometry.  Returns None when the scope has no
    loop-member line (layout.json / certificate bytes then stay
    unchanged)."""
    templated = set(templated or ())
    rtr = Router(nodes, edges, clearance, pitch, loop_arcs=loops)
    pref = rtr.arc_pref
    if not pref:
        return None
    segs = {}
    for j, r in routes.items():
        rpts = (r or {}).get("points") or []
        if len(rpts) < 2:
            continue
        ss = list(zip(rpts[:-1], rpts[1:]))
        segs[j] = (ss, [(min(p[0], q[0]), min(p[1], q[1]),
                         max(p[0], q[0]), max(p[1], q[1])) for p, q in ss])

    def _best(i, a, b, test):
        rs = {j: s for j, s in segs.items() if j != i}
        bst = None
        for c in rtr._candidates(a, b, i):
            if not test(c):
                continue
            sc, inf = rtr._evaluate(c, a, b, rs, None, honest=True)
            if inf is not None and (bst is None or sc < bst[0] - EPS):
                bst = (sc, inf)
        return bst[1] if bst else None

    arced, opposite, fallbacks = 0, 0, []
    templated_n = 0
    mutual_non_arc = 0
    mutual = mutual_pair_members(edges, loops) - set(pref)
    for i in sorted(set(pref) | mutual):
        a, b = edges[i]
        info = routes.get(i)
        if not info:
            continue
        kind = info.get("kind")
        if i in mutual:
            # mutual-pair loop member delivered as a non-arc: outside the
            # arc default's scope, so nothing is scored -- only the delivery
            # is recorded (accounting only, the drawing is untouched)
            if kind == "arc":
                continue
            mutual_non_arc += 1
            fallbacks.append({
                "edge": "%s->%s" % (a, b),
                "delivered": "%s%s" % (kind or "unknown",
                                       " (mode template)" if i in templated else ""),
                "preferred_arc": ("not scored: mutual pair -- its geometry "
                                  "belongs to the lens / rule-8 contract")})
            continue
        pts = info.get("points") or []
        want = pref[i]
        sides = (want,) if want else (1, -1)
        sign = 0
        if kind == "arc" and len(pts) >= 2:
            sign = _bulge_sign(pts[0], pts[-1],
                               info.get("ctrl") or pts[len(pts) // 2])
        if kind == "arc" and sign in sides:
            arced += 1
            continue
        name = "%s->%s" % (a, b)
        if i in templated:
            # constructed placement engine: the mode template (spine / comb
            # fan / bowtie mirror lines ...) delivers this line's own
            # geometry and the candidate pool is skipped (edge-placement
            # rules v1 section 14 exemption) -- template geometry, not a
            # scored fallback
            templated_n += 1
            fallbacks.append({"edge": name,
                              "delivered": "%s (mode template)" % (kind or "unknown"),
                              "preferred_arc": ("not scored: delivered by the "
                                                "placement mode's constructed "
                                                "template")})
            continue
        if kind == "arc":
            opposite += 1
            delivered = "arc (opposite side)"
        elif info.get("joint_detour"):
            # anchor-snap repair pass: no standard-anchor pair admitted the
            # line at decision time, the whole edge was re-planned as a
            # visibility-graph detour (both endpoints on the 16-anchor set)
            delivered = "%s (anchor-snap joint detour)" % kind
        else:
            delivered = kind or "unknown"
        ia = _best(i, a, b, lambda c: c[0] == "arc"
                   and _bulge_sign(c[2], c[3], c[4]) in sides)
        rec = {"edge": name, "delivered": delivered,
               "preferred_arc": ("no preferred-side arc candidate" if ia is None
                                 else _candidate_defects(ia, clearance))}
        if delivered.endswith("joint detour)") and rec["preferred_arc"] == "clean":
            rec["preferred_arc"] = ("clean against the FINAL routes, but no "
                                    "standard-anchor pair admitted it at "
                                    "decision time")
        if kind not in ("line", "arc"):
            il = _best(i, a, b, lambda c: c[0] == "line")
            rec["straight_line"] = (_candidate_defects(il, clearance)
                                    if il else "no straight candidate")
        fallbacks.append(rec)
    return {"rule": ("loop-member lines (not mutual pairs) default to an "
                     "arc bulging away from the centroid of their declared "
                     "loops; straight / polyline are scored fallbacks"),
            "preferred": len(pref), "arced": arced,
            "opposite_side_arcs": opposite, "templated": templated_n,
            "mutual_pair_non_arc": mutual_non_arc,
            "fallbacks": fallbacks}


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

# Closed-ring caliber for mutual pairs outside the lens-chain engine
# (Router.mutual_lens_construct).  A pair is rebuilt as the constructed
# lens-chain double arc when the delivered lines fail the closed-ring
# contract (gates.arc_bulge on both arcs + separation); the anchor pair
# follows lenslayout._LENS_ANCHORS (horizontal pair: facing corners,
# vertical pair: golden anchors).  On a SHORT horizontal chord the corner
# pair (38px apart on a 44px card) makes the eye rounder than the
# lens-chain caliber (width/chord = LENS_K + 38/chord vs the chain's 0.56):
# below LENS_CORNER_MIN_CHORD the golden pair (9px apart) is the closer
# ratio (crossover: 38/c - 0.24 = 0.24 - 9/c -> c = 98).  The chord tilt
# limit is geometric: the outer arc of a lens meets its border at
# atan(2*LENS_K) = 32.6 deg off the chord, so the certificate's
# ANCHOR_MIN_DEG floor (<= 70 deg from the normal) bounds the tilt of the
# facing-normal chord by 90 - ANCHOR_MIN_DEG - atan(2*LENS_K).
LENS_CORNER_MIN_CHORD = 98.0
LENS_PAIR_MIN_SEP = 12.0   # closed-lens separation floor (lens_pair_min_sep_ge_12 caliber)
LENS_SIDE_VEC = {"N": (0.0, -1.0), "S": (0.0, 1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}
LENS_LEFT_TURN = {"E": "N", "N": "W", "W": "S", "S": "E"}
LENS_RIGHT_TURN = {"E": "S", "S": "W", "W": "N", "N": "E"}
# ((left-of-travel chord A id, B id), (right-of-travel chord A id, B id))
# per travel direction A -> B; corners only exist for horizontal pairs.
LENS_PAIR_ANCHORS = {
    "corner": {"E": (("ne", "nw"), ("se", "sw")),
               "W": (("sw", "se"), ("nw", "ne")),
               "S": (("se", "ne"), ("sw", "nw")),
               "N": (("nw", "sw"), ("ne", "se"))},
    "golden": {"E": (("e-g1", "w-g2"), ("e-g2", "w-g1")),
               "W": (("w-g1", "e-g2"), ("w-g2", "e-g1")),
               "S": (("s-g1", "n-g2"), ("s-g2", "n-g1")),
               "N": (("n-g1", "s-g2"), ("n-g2", "s-g1"))},
}


# Closed-ring rebuild scope (mutual_lens_construct): chord-tilt ceiling of the
# pairs rebuilt as a lens.  None = derived ceiling (every pair whose outer arc
# can still meet ANCHOR_MIN_DEG, ~37.4 deg); a number caps the scope -- pairs
# tilted more than that stay the delivered parallel lines and are recorded
# "tilt" (accounted exemption).  Read at call time, so the certificate
# re-measures with the same value as the router.
LENS_TILT_MAX_DEG = None


def lens_tilt_max_deg():
    """Chord tilt (off the facing border normal) up to which a constructed
    lens can still meet ANCHOR_MIN_DEG on its outer arc (LENS_TILT_MAX_DEG
    caps it when set)."""
    from .lenslayout import LENS_K
    if LENS_TILT_MAX_DEG is not None:
        return float(LENS_TILT_MAX_DEG)
    return 90.0 - ANCHOR_MIN_DEG - math.degrees(math.atan(2.0 * LENS_K))

# Line-line visual-coincidence targeted re-routing accounting (ref-scrubbed): the random n10 fan-out edges run through the same
# inter-row corridor candidates (stair/lane, y = row center +/- pitch/2) with per-segment <1px adherence. The authoritative accounting = this
# module's span_one_way_segs; the certificate side's metrics._coincidence_span delegates both directions to the same source.
COINCIDE_THR = 1.0          # distance <1px counts as adherence (same source as the certificate accounting)
COINCIDE_SPAN = 8.0         # accumulated adherence must exceed 8px to count as "visual coincidence" (endpoint meeting exempted)
FAN_STEP = 18.0             # uniform spread step for multiple anchors on the same node side (ref-scrubbed rule 3)
# Dense mode (jacky 2026-11-14 authorization: "1 anchor may be shared by
# multiple lines; angle limits may be relaxed appropriately" — dense-only
# branch, proposal stdraw-dense approved by default final review).  Every
# constant below is read ONLY when Router.dense_hub is set (dense := the
# graph's max node degree >= DENSE_MIN_DEG, a topology-pure predicate
# evaluated in layout_auto); with dense_hub=None the legacy calibers above
# apply byte-for-byte.
DENSE_MIN_DEG = 10           # dense := max node degree >= 10 (Q1)
DENSE_ANCHOR_MIN_DEG = 12    # dense-branch anchor smoothness floor (Q2)
DENSE_FAN_STEP = 12.0        # dense-branch fan slot step (gate table #3)
DENSE_GRID_STEP = 6.0        # dense slot grid step (gate table #0 / er layer)
DENSE_CAP_PER_SLOT = 4       # per-slot sharing hard cap (Q4; exceed = honest degrade)
DENSE_SLOT_SEP_MIN = 6.0     # dense adjacent distinct-slot separation (gate table #4)
DENSE_SPOKE_STRAIGHT_PENALTY = 120.0
# dense radial contract: hub spokes deliver as STRAIGHT lines (the radial
# reading; operator form-correctness gate 2026-11-15).  Arc / vg / poly
# candidates on an edge touching the dense hub carry this fixed type cost
# (same mechanism as the vg/poly/wrap costs), so a gate-clean straight
# spoke always beats a bulged arc; if no straight candidate clears the
# hard gates the arc still wins (honest fallback, dense-only branch).
# Edge placement rules v1 (edgerules preset candidates): honest fixed
# penalties for bending away from the rule geometry -- arc on the
# non-rule side / straight where a B line wants its golden-point arc.
# Hard gates (press / crossings) still dominate via their own weights.
ARC_NEAR_PENALTY = 25.0
# Straight line where the rules want an arc (a B line whose golden-point arc
# is infeasible, or a loop-member line under the loop-direction arc default).
# Sits BELOW the polyline type cost (40) on purpose: the documented order is
# arc -> straight -> detour machinery as last resort, and at the previous
# 60 a clean straight line lost to a clean horizontal-lane polyline
# (40 + 0.01 x length), turning blocked arcs into flowchart-style right-angle
# polylines even where a clean straight line existed.
STRAIGHT_FALLBACK_PENALTY = 30.0
STRAIGHT_ON_B_PENALTY = STRAIGHT_FALLBACK_PENALTY   # backward-compatible name
ARRIVAL_TARGET_DEG = 10.0   # ref-scrubbed: mutual-lens arrow-normal target (card-suggested; hard-gating pending owner decision)
MIN_FROZEN_ANCHOR_SEP = 8.0  # ref-scrubbed: fan slots must clear frozen anchors on the same side by at least this (px)
REANCHOR_STEP = 4.0         # ref-scrubbed midband_reanchor ladder-clamping step
ARC_CTRL_SCALE_LADDER = (1.0, 0.85, 1.15, 0.7, 1.3, 0.55, 1.45, 0.45, 1.6)
# ref-scrubbed anchor_snap: after snapping an arc endpoint, the departure angle
# vs the border tangent (>= ANCHOR_MIN_DEG) cannot always be met by ctrl
# lockstep translation alone (a long-tangent detour arc keeps its near-tangent
# departure).  The ladder rescales the ctrl offset around the new chord
# midpoint (preserving the detour side; gates recheck press/crossing/clearance)
# so the arc re-fits its shape to the anchored chord.  1.0 first = zero-shape-
# change preference.

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


SEG_GRID_CELL = 16         # px, exact-acceleration grid cell for the coincide gate


def build_seg_grid(segs, cell=SEG_GRID_CELL):
    """Register each segment id into every grid cell its bbox touches.

        Exact-equivalence acceleration structure for span_one_way_segs_grid:
        a segment within COINCIDE_THR (1px) of a query point has its bbox
        intersecting that point's 3x3 cell neighborhood (cell >= 2px), so the
        neighborhood scan sees every segment the exact all-segments scan
        could score -- identical membership decisions, fewer
        _pt_seg_dist calls (the n20 wall-clock regression's inner loop).
    """
    grid = {}
    for si, (p, q) in enumerate(segs):
        cx1 = int(math.floor(min(p[0], q[0]) / cell))
        cx2 = int(math.floor(max(p[0], q[0]) / cell))
        cy1 = int(math.floor(min(p[1], q[1]) / cell))
        cy2 = int(math.floor(max(p[1], q[1]) / cell))
        for cx in range(cx1, cx2 + 1):
            for cy in range(cy1, cy2 + 1):
                grid.setdefault((cx, cy), []).append(si)
    return grid


def build_seg_grid_margin(segs, cell=SEG_GRID_CELL, margin=1):
    """build_seg_grid with a `margin`-cell halo around each segment bbox.

        Used by the crossing-accounting world (_edge_world): seg_cross carries
        an EPS (1e-9) tolerance (collinear-overlap / endpoint-EPS branches), so
        a "crossing" pair may effectively meet within EPS outside the strict
        bboxes -- the halo guarantees the opposing segment is registered even
        when the effective meeting point sits a sub-EPS step past a cell
        boundary (exact verdicts, no missed pairs).
    """
    grid = {}
    for si, (p, q) in enumerate(segs):
        cx1 = int(math.floor(min(p[0], q[0]) / cell)) - margin
        cx2 = int(math.floor(max(p[0], q[0]) / cell)) + margin
        cy1 = int(math.floor(min(p[1], q[1]) / cell)) - margin
        cy2 = int(math.floor(max(p[1], q[1]) / cell)) + margin
        for cx in range(cx1, cx2 + 1):
            for cy in range(cy1, cy2 + 1):
                grid.setdefault((cx, cy), []).append(si)
    return grid


def span_one_way_segs_grid(samples, segs, grid, step=SAMPLE_STEP,
                           thr=COINCIDE_THR, cell=SEG_GRID_CELL):
    """Grid-accelerated span_one_way_segs (bit-identical accounting).

        Per sample, dmin is taken over the segments registered in the 3x3
        cell neighborhood; every segment that could be within thr of the
        sample is registered there (build_seg_grid invariant), so the
        membership decision (min dist < thr) is identical and the
        accumulated span is bit-identical to span_one_way_segs.
    """
    total = 0.0
    for px, py in samples:
        cx = int(math.floor(px / cell))
        cy = int(math.floor(py / cell))
        hit = False
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                bucket = grid.get((gx, gy))
                if not bucket:
                    continue
                for si in bucket:
                    s = segs[si]
                    if _pt_seg_dist((px, py), s[0], s[1]) < thr:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
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


def _bbox_gap_lb(pts_a, pts_b):
    """Lower bound on min distance between two point sequences: the gap
    between their bounding boxes (true min distance is never below it)."""
    ax0 = min(p[0] for p in pts_a)
    ax1 = max(p[0] for p in pts_a)
    ay0 = min(p[1] for p in pts_a)
    ay1 = max(p[1] for p in pts_a)
    bx0 = min(p[0] for p in pts_b)
    bx1 = max(p[0] for p in pts_b)
    by0 = min(p[1] for p in pts_b)
    by1 = max(p[1] for p in pts_b)
    gx = max(0.0, ax0 - bx1, bx0 - ax1)
    gy = max(0.0, ay0 - by1, by0 - ay1)
    return math.hypot(gx, gy)


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
def _dense_fan_offsets(k, half_len, shift):
    """Dense fan offsets for a k-entry hub-side group (deterministic).

    Distinct grid slots first: multiples of DENSE_FAN_STEP centered on
    the border midpoint, clamped inside +/-(half_len) by construction.
    When k exceeds the 12px-slot capacity, the grid shrinks to the
    DENSE_GRID_STEP (6px — still gate-table-#4 compliant: adjacent
    distinct slots stay >= 6px apart, so no sharing admission is needed
    for the whole d<=32 fan family).  Slot sharing (azimuth-monotone,
    cap-checked by the caller) is the last resort only.  Grid
    discipline: every offset is a multiple of DENSE_GRID_STEP so
    delivered hub endpoints sit on the dense slot grid (anchors_standard
    dense caliber, metrics side).
    """
    step = DENSE_FAN_STEP
    n_slots = int(math.floor((2.0 * half_len) / step)) + 1
    if k > n_slots:
        n_slots = int(math.floor((2.0 * half_len) / DENSE_GRID_STEP)) + 1
        step = DENSE_GRID_STEP
    if k <= n_slots:
        if step == DENSE_FAN_STEP:
            # 12px slots with half-slot centering stay on the 6px grid
            return [(t - (k - 1) / 2.0) * step + shift for t in range(k)]
        # 6px slots: integer-slot centering (half-slot centering would
        # land on 3px odd offsets and break the 6px grid discipline)
        base = -((k - 1) // 2)
        return [(t + base) * step + shift for t in range(k)]
    s = -(-k // n_slots)          # ceil sharing factor
    used = -(-k // s)             # slots actually used
    base = -((used - 1) // 2)
    return [(t // s + base) * step + shift for t in range(k)]


class EvalCache:
    """Content-keyed exact memoization shared across Router instances.

    The polish hill-climb re-routes the whole graph for every candidate
    world (one node shifted / two nodes swapped); across those worlds most
    per-candidate geometry and most node boxes are float-identical.  Every
    key in this cache embeds the exact float content of every input that
    can change the memoized value (candidate point content / box tuples /
    routed-segment content / honest flag), so a hit reproduces the
    uncached value bitwise by construction -- no invalidation logic, same
    argument as the v0.7.15 content-keyed caches.  Rejection checks and
    score arithmetic are re-run per call in the base expression order, so
    delivered floats are identical, not merely equal.

    Lifetime: ONE polish block.  layout() creates a fresh instance per
    call; route-key interning holds references to segment lists, so the
    cache (and everything it pins) dies with the block.
    """

    CROSS_CAP = 3_000_000   # safety valve; exactness never depends on hits

    def __init__(self):
        self.ck_id = {}      # candidate point-content tuple -> small int
        self.samples = {}    # ck int -> (samples list, bbox xlo xhi ylo yhi)
        self.cand_segs = {}  # ck int -> (cand segs list, per-seg bbox list)
        self.press = {}      # (ck int, box tuple) -> (press_u, dmin_u)
        self.cross = {}      # (ck int, route int) -> (cross_j, hit_j)
        self.ownang = {}     # (ck int, box a, box b, honest) ->
                             #   (rejected, press_own, ang_a, ang_b)
        self.length = {}     # ck int -> polyline length
        self.cand_linearc = {}   # (a, b, box a, box b, mutual bool) ->
                                 #   canonical line/arc candidate prefix
        self.rk_id = {}      # canonical segs key -> small int
        self._rkrefs = {}    # id(segs list) -> (ref, canonical key, int)
        # T12 mutual-pair separation memo: (candidate id, sibling id) ->
        # (unrounded pair_sep, unrounded sep_def); the 12px coarse samples
        # of a candidate and the identity-guarded sibling-sample interning
        # feed the key (same exact-content argument as the other caches).
        self.pairsep = {}
        self.samples12 = {}
        self.sib_id = {}
        self._sibrefs = {}

    def sib_key(self, samples):
        """Small-int id for a sibling coarse-sample list, content-keyed.

        Identity-guarded like route_key: route_all builds ONE sample list
        per edge per pass and reuses it across that edge's ~200 candidate
        evaluations, so the common case resolves by object identity.
        """
        ent = self._sibrefs.get(id(samples))
        if ent is not None and ent[0] is samples:
            return ent[1]
        key = tuple(samples)
        sid = self.sib_id.get(key)
        if sid is None:
            sid = self.sib_id[key] = len(self.sib_id)
        self._sibrefs[id(samples)] = (samples, sid)
        return sid

    def route_key(self, segs):
        """Small-int id for a routed-segments list, content-keyed.

        Identity-guarded interning: the same list object (reused across the
        ~200 candidate evaluations of one route_all pass) resolves without
        re-hashing its content; distinct list objects with identical
        segment content share one id (joint_reroute rebuilds segs lists
        every pair)."""
        ent = self._rkrefs.get(id(segs))
        if ent is not None and ent[0] is segs:
            return ent[2]
        key = tuple((p[0], p[1], q[0], q[1]) for p, q in segs)
        rid = self.rk_id.get(key)
        if rid is None:
            rid = self.rk_id[key] = len(self.rk_id)
        self._rkrefs[id(segs)] = (segs, key, rid)
        return rid


class Router:
    """Plan a route for each edge from the node box positions on the canvas. Deterministic: fixed candidate order + fixed scoring."""

    def __init__(self, nodes: dict, edges: list, clearance=CLEARANCE, pitch=80,
                 quality=False, presets=None, dense_hub=None,
                 eval_cache=None, loop_arcs=None):
        """nodes: {id: (x,y,w,h)} center + size; edges: [(a,b)] directed.

            quality=False (default): the legacy candidate pool, output byte-for-byte identical to v0.4.x;
            quality=True: WS3-Q routing-quality rework extends the candidate pool (multi-row stair) -- enabled only on
            the gated re-layout path after the layout-layer routing hard gate fails; never enters the normal layout path.
            presets: edge placement rules v1 (edgerules.assign) — {edge idx:
            preset}.  When present for an edge, candidates are generated
            ONLY between the pre-assigned standard-anchor endpoints
            (docs/edge-placement-rules-v1.md: anchors are decided before
            routing; the router still scores honestly between line / arc
            (rule side first) / vg / lane fallbacks).
            dense_hub: dense-mode node id (the box whose degree >=
            routing.DENSE_MIN_DEG) or None (default — every dense branch
            inert, legacy bytes preserved).  When set, only THIS box's
            repair groups enter the dense branches (slot grid + controlled
            sharing + relaxed angle floor); leaf boxes are never dense.
            loop_arcs: declared loops for the loop-direction arc default
            (None = read the enclosing loop_arc_context; still None outside
            it = legacy straight-first caliber, bytes preserved).
        """
        self.N = {v: (p[0], p[1], p[2] / 2.0, p[3] / 2.0) for v, p in nodes.items()}
        self.edges = list(edges)
        self.cl = clearance
        self.pitch = pitch
        self.quality = quality
        self.presets = dict(presets) if presets else None
        # loop-direction arc default: {edge idx: +1/-1/0} preferred bulge
        # sign computed from the CURRENT box centers (the side is a property
        # of the placement), {} when no loop is in scope.
        if loop_arcs is None:
            loop_arcs = _LOOP_ARC_CTX.get()
        self.arc_pref = (loop_arc_sides({v: n[:2] for v, n in self.N.items()},
                                        self.edges, loop_arcs)
                         if loop_arcs else {})
        # dense mode: None = inert (every dense branch skipped, legacy
        # bytes); a node id = dense repair branches active for that box.
        self.dense_hub = dense_hub
        self.dense = dense_hub is not None
        # honest degrade records of the dense branches (fan fallback
        # abolished / sharing cap exceeded); layout_auto lifts them into
        # meta.dense_mode for the certificate pass-through.
        self.dense_degrade = []
        mutual = set()
        for a, b in edges:
            if (b, a) in set(edges) and a < b:
                mutual.add((a, b))
        self.mutual = mutual
        self.eidx = {(a, b): i for i, (a, b) in enumerate(edges)}
        # Exact-memo fast path (polish worlds): None = legacy behavior
        # untouched (default); an EvalCache instance enables the cached
        # evaluate path -- outputs stay byte-identical either way.
        self._ecache = eval_cache
        # Routing order: edges spanning more rows are routed first (large spans decide the corridors), the rest by (a,b)
        self.order = sorted(range(len(edges)),
                            key=lambda i: (-self._span(edges[i]), edges[i][0], edges[i][1]))

    def _span(self, e):
        ya, yb = self.N[e[0]][1], self.N[e[1]][1]
        return abs(yb - ya)

    # -- anchors --
    def _dense_on_grid(self, v, p):
        """Dense caliber: is endpoint p of the dense hub box on the slot
        grid (border band within the 3px inset + 0.75px tolerance, tangent
        offset a multiple of DENSE_GRID_STEP, same 0.75px tolerance)?
        Non-dense routers / leaf boxes always answer False (legacy bytes)."""
        if not self.dense or v != self.dense_hub:
            return False
        cx, cy, hw, hh = self.N[v]
        on_x = abs(abs(p[0] - cx) - hw) <= abs(abs(p[1] - cy) - hh)
        # border band: the normal coordinate sits within the anchor inset
        # (3px) + membership tolerance (0.75px) of the true border
        band = 3.75
        if on_x:
            if abs(abs(p[0] - cx) - hw) > band:
                return False
            off = p[1] - cy
        else:
            if abs(abs(p[1] - cy) - hh) > band:
                return False
            off = p[0] - cx
        steps = off / DENSE_GRID_STEP
        return abs(off - round(steps) * DENSE_GRID_STEP) <= 0.75

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
    def _candidates_linearc(self, a, b, pref=None):
        """Deterministic line/arc candidate prefix: depends only on the two
        endpoint boxes and the mutual-pair flag (anchor variants, adaptive
        curvature ladder).  Returned in CANONICAL form (kind, tuple pts,
        tuple pa, tuple pb, tuple ctrl-or-None[, rule penalty]) for exact
        memoization across polish candidate worlds; _candidates materializes
        fresh mutable containers from it per call (bitwise-identical values,
        no shared-mutable aliasing).

        pref (loop-direction arc default, T10): +1/-1 = loop-side bulge
        sign, 0 = loop member with a free side, None = legacy caliber
        (straight first, both arc sides unrated).  Mutual pairs always take
        the legacy lens logic regardless of pref."""
        out = []
        key = (min(a, b), max(a, b))
        # F1 lens double-arc: both directions of a mutual pair take the same arc side sign (their reference frames are opposite -> geometrically opposite arcs,
        # forming a lens; one arc one arrow per direction, no more double-headed-arrow look)
        mutual_side = 1 if key in self.mutual else None
        loop_pref = None if mutual_side else pref
        for pa, pb in self._anchor_variants(a, b):
            vx, vy = pb[0] - pa[0], pb[1] - pa[1]
            dist = math.hypot(vx, vy)
            ux, uy = norm(-vy, vx)
            # ref-scrubbed arc-curvature parameterization: first tier = chord-adaptive k (small bends for short edges,
            # capped for long ones), the ladder kept as a feasibility fallback; order-preserving dedupe, determinism unchanged
            ks = tuple(dict.fromkeys((adaptive_arc_k(dist),) + ARC_KS))
            if loop_pref is None:
                out.append(("line", (tuple(pa), tuple(pb)),
                            tuple(pa), tuple(pb), None))
            sides = (mutual_side,) if mutual_side else \
                ((loop_pref, -loop_pref) if loop_pref else (1, -1))
            for k in ks:
                for s in sides:
                    ctrl = [(pa[0] + pb[0]) / 2 + ux * k * dist * s,
                            (pa[1] + pb[1]) / 2 + uy * k * dist * s]
                    ent = ("arc",
                           tuple(tuple(p) for p in quad_points(pa, ctrl, pb)),
                           tuple(pa), tuple(pb), (ctrl[0], ctrl[1]))
                    if loop_pref is not None and loop_pref and s != loop_pref:
                        ent = ent + (ARC_NEAR_PENALTY,)
                    out.append(ent)
            if loop_pref is not None:
                out.append(("line", (tuple(pa), tuple(pb)), tuple(pa),
                            tuple(pb), None, STRAIGHT_FALLBACK_PENALTY))
        return out

    @staticmethod
    def _materialize_linearc(canon):
        kind, pts_c, pa_c, pb_c, ctrl_c = canon[:5]
        pen = canon[5] if len(canon) > 5 else 0.0
        pa, pb = list(pa_c), list(pb_c)
        if kind == "line":
            if pen:
                return ("line", [pa, pb], pa, pb, None, pen)
            return ("line", [pa, pb], pa, pb)
        if pen:
            return ("arc", [list(p) for p in pts_c], pa, pb, list(ctrl_c), pen)
        return ("arc", [list(p) for p in pts_c], pa, pb, list(ctrl_c))

    def _candidates(self, a, b, idx):
        """Fixed-order candidates: straight -> arc (left/right x curvature) -> detour channels, x anchor variants.

        Loop-direction arc default (T10): for a loop-member edge (not a
        mutual pair) the prefix order becomes arc on the loop side (penalty
        0) -> arc on the other side (25) -> straight (30), so straight /
        polyline are honest fallbacks scored behind the curve."""
        if self.presets and idx in self.presets:
            return self._preset_candidates(a, b, idx)
        ec = self._ecache
        pref = self.arc_pref.get(idx) if self.arc_pref else None
        if ec is not None:
            pk = (a, b, self.N[a], self.N[b],
                  (min(a, b), max(a, b)) in self.mutual, pref)
            prefix = ec.cand_linearc.get(pk)
            if prefix is None:
                prefix = ec.cand_linearc[pk] = self._candidates_linearc(a, b, pref)
            cands = [self._materialize_linearc(c) for c in prefix]
        else:
            cands = [self._materialize_linearc(c)
                     for c in self._candidates_linearc(a, b, pref)]
        key = (min(a, b), max(a, b))
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
                # bbox lower bound prefilter (exact, WS5 caliber): when the
                # anchor segment's bbox is already >= the unblocked threshold
                # away from a rect's bbox, that rect cannot block -- skip the
                # exact seg_rect_distance call, verdict unchanged.
                sl = sa[0] if sa[0] < sb[0] else sb[0]
                sr = sa[0] if sa[0] > sb[0] else sb[0]
                st = sa[1] if sa[1] < sb[1] else sb[1]
                su = sa[1] if sa[1] > sb[1] else sb[1]
                blocked = False
                for rect in rects:
                    rcx, rcy, rhw, rhh = rect
                    gx = rcx - rhw - sr
                    g = sl - rcx - rhw
                    if g > gx:
                        gx = g
                    gy = rcy - rhh - su
                    g = st - rcy - rhh
                    if g > gy:
                        gy = g
                    if (gx > 0.0 or gy > 0.0) and \
                            math.hypot(gx if gx > 0.0 else 0.0,
                                       gy if gy > 0.0 else 0.0) >= \
                            c_vg - 1e-6 + 1e-9:
                        continue      # cannot block (bbox lower bound)
                    if _vis.seg_rect_distance(sa, sb, rect) < c_vg - 1e-6:
                        blocked = True
                        break
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

    def _preset_candidates(self, a, b, idx):
        """Edge placement rules v1 candidate pool: endpoints are FIXED to
        the pre-assigned standard anchors (edgerules preset); candidates
        differ only in geometry between them.  Fixed order, deterministic:
        rule geometry first (line / arc rule side, penalty 0), rule-bend
        fallbacks next (arc other side / straight where B wants an arc,
        honest fixed penalties), then the obstacle-avoidance machinery
        (vg from the fixed endpoints, horizontal lanes) as last resort.
        The 6th tuple element is a rule-preference penalty honored by
        _evaluate (legacy candidates carry no 6th element -> 0.0)."""
        p = self.presets[idx]
        pa, pb = list(p["pa"]), list(p["pb"])
        cands = []
        dist = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) or 1.0
        ux, uy = norm(-(pb[1] - pa[1]), pb[0] - pa[0])
        ks = tuple(dict.fromkeys((adaptive_arc_k(dist),) + ARC_KS))

        def arc(s, pen):
            for k in ks:
                ctrl = [(pa[0] + pb[0]) / 2 + ux * k * dist * s,
                        (pa[1] + pb[1]) / 2 + uy * k * dist * s]
                cands.append(("arc", quad_points(pa, ctrl, pb), pa, pb, ctrl, pen))

        arc_style = p["style"] in ("arc", "lens_a", "lens_b")
        if arc_style:
            arc(p["arc_side"], 0.0)
            arc(-p["arc_side"], ARC_NEAR_PENALTY)
            cands.append(("line", [pa, pb], pa, pb, None, STRAIGHT_ON_B_PENALTY))
        else:
            cands.append(("line", [pa, pb], pa, pb, None, 0.0))
            arc(1, ARC_NEAR_PENALTY)
            arc(-1, ARC_NEAR_PENALTY)
        # visibility-graph detours from the FIXED endpoints (only when the
        # straight chord is blocked -- same trigger as the legacy pool)
        rects = [n for v, n in self.N.items() if v not in (a, b)]
        if rects:
            c_vg = self.cl + VG_PAD
            blocked = any(_vis.seg_rect_distance(pa, pb, rect) < c_vg - 1e-6
                          for rect in rects)
            if blocked:
                route = _vis.plan_route(pa, pb, rects, c_vg)
                if route:
                    cands.append(("vg", route["dense"], pa, pb, route, 0.0))
        # horizontal inter-row lanes from the fixed endpoints (last resort)
        if abs(pb[1] - pa[1]) > 4:
            lane = (pa[1] + pb[1]) / 2
            for off in (0, -30, 30, -60, 60, -90, 90):
                mx = (pa[0] + pb[0]) / 2 + off
                cands.append(("poly", [pa, [pa[0], lane], [mx, lane],
                                       [pb[0], lane], pb], pa, pb, None, 0.0))
        return cands

    # -- candidate evaluation --
    def _cand_lb(self, cand, a, b):
        """Exact lower bound on a candidate's _evaluate score (T12 pruning).

        score = 4000*press + 40*cross + 30*clr_def + 0.01*length +
                PAIR_SEP_W*sep_def + kind_pref + rule_pen + 2*ang_def
                (+1500 soft rejection); every term except kind_pref /
                rule_pen is non-negative, and kind_pref is -2.0 only for a
                mutual-pair arc.  The bound keeps exactly those three terms
                (length memoized through the shared EvalCache when present).
        """
        kind, pts = cand[0], cand[1]
        ec = self._ecache
        if ec is None:
            length = sum(math.dist(pts[i], pts[i + 1])
                         for i in range(len(pts) - 1))
        else:
            ck = tuple((p[0], p[1]) for p in pts)
            cki = ec.ck_id.get(ck)
            if cki is None:
                cki = ec.ck_id[ck] = len(ec.ck_id)
            length = ec.length.get(cki)
            if length is None:
                length = ec.length[cki] = sum(
                    math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        if kind == "arc":
            kp = -2.0 if (min(a, b), max(a, b)) in self.mutual else 0.0
        elif kind == "vg":
            kp = 120.0
        elif kind == "poly":
            kp = 40.0
        elif kind == "wrap":
            kp = 200.0
        else:
            kp = 0.0
        rp = cand[5] if len(cand) > 5 else 0.0
        return kp + rp + 0.01 * length

    def _evaluate(self, cand, a, b, routed_segs, sib_samples=None, honest=False):
        if self._ecache is None:
            return self._evaluate_base(cand, a, b, routed_segs,
                                       sib_samples, honest)
        return self._evaluate_cached(cand, a, b, routed_segs,
                                     sib_samples, honest)

    def _evaluate_base(self, cand, a, b, routed_segs, sib_samples=None, honest=False):
        """Return (score, info); info carries press/clearance/crossing/anchor-angle/mutual-separation details.

                routed_segs: {j: (list of routed segments, list of per-segment bboxes)} (precomputed by route_all).
                F1: when the minimum spacing between a mutual pair (a<->b) and its already-routed sibling edge (b,a) is < PAIR_SEP_MIN,
                apply a heavy linear penalty (the shared-endpoint exemption no longer masks coincidence -- separation is measured directly on sampled point distances).
                honest=True (edge placement rules v1 preset pool): own-box interior clipping and inset off-border endpoints are
                scored honestly (press += 1 per clipped own box) instead of rejecting the candidate outright -- the rejection
                forced a hard-coded clean fallback (press=0 / ang=0.0) that blinded the hard-gate tuple (measured:
                random-n20-i00 delivered 25 presses / 4 grazing arrivals annotated as clean).
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
        # honest mode (v1 preset pool): inset endpoints are legal; own-box interior clipping is added to press (metrics counts
        # own-box presses in box_press_1px) instead of rejecting the candidate outright.
        for v, endp in ((a, pa), (b, pb)):
            cx, cy, hw, hh = self.N[v]
            if honest:
                for (px, py) in samples[1:-1]:
                    if dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN, hh + PRESS_MARGIN) <= ROUND_GUARD:
                        press += 1
                        break
                continue
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
        if (self.dense and kind != "line"
                and (a == self.dense_hub or b == self.dense_hub)):
            # dense radial contract (dense card, form-correctness gate):
            # hub spokes must deliver as straight lines -- non-line
            # candidates carry the fixed straight-preference cost so a
            # gate-clean straight spoke wins the score; arcs still win
            # when no straight candidate clears the hard gates.
            kind_pref += DENSE_SPOKE_STRAIGHT_PENALTY
        if mutual_pair:
            # F1 tightened clearance: separation candidates must not sacrifice the edge-box clearance gate (total weight 150*gap)
            clr_def *= 5.0
        # Edge placement rules v1: preset candidates carry a 6th element =
        # rule-preference penalty (arc on the non-rule side / straight where
        # B wants an arc).  Added on TOP of the honest geometry scoring so
        # the hard gates (press / crossings) still dominate (spec §4 order).
        rule_pen = cand[5] if len(cand) > 5 else 0.0
        score = (4000 * press + 40 * cross + 30.0 * clr_def + 0.01 * length +
                 PAIR_SEP_W * sep_def + kind_pref + rule_pen)
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

    def _evaluate_cached(self, cand, a, b, routed_segs, sib_samples=None,
                         honest=False):
        """Exact-memo fast path of _evaluate_base: byte-identical outputs.

        Memo keys embed the exact float content of every input that can
        change the memoized value (candidate point content / box tuples /
        routed-segment content / honest flag) -- a hit reproduces the base
        path's value bitwise by construction.  Early-out box skips are
        min_clr-order-dependent, so they are re-evaluated per call in the
        base order and never memoized; only boxes that actually ran the
        sample loop are stored.  Score/info assembly re-runs the base
        expression tree every call (same op order -> same floats).
        """
        ec = self._ecache
        kind, pts, pa, pb = cand[0], cand[1], cand[2], cand[3]
        ck = tuple((p[0], p[1]) for p in pts)
        cki = ec.ck_id.get(ck)
        if cki is None:
            cki = ec.ck_id[ck] = len(ec.ck_id)
        sbe = ec.samples.get(cki)
        if sbe is None:
            sbe = ec.samples[cki] = (
                sample_polyline(pts),
                min(p[0] for p in pts), max(p[0] for p in pts),
                min(p[1] for p in pts), max(p[1] for p in pts))
        samples, bxl, bxh, byl, byh = sbe
        # own boxes: border attachment + interior press + anchor angles
        # (depend only on candidate geometry + the two endpoint boxes)
        bok = (cki, self.N[a], self.N[b], honest)
        oent = ec.ownang.get(bok)
        if oent is None:
            rejected = False
            press_own = 0
            for v, endp in ((a, pa), (b, pb)):
                cx, cy, hw, hh = self.N[v]
                if honest:
                    for (px, py) in samples[1:-1]:
                        if dist_point_rect(px, py, cx, cy,
                                           hw + PRESS_MARGIN,
                                           hh + PRESS_MARGIN) <= ROUND_GUARD:
                            press_own += 1
                            break
                    continue
                if dist_point_rect(endp[0], endp[1], cx, cy, hw, hh) > 0.75:
                    rejected = True
                    break
                interior = False
                for (px, py) in samples[1:-1]:
                    if dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN,
                                       hh + PRESS_MARGIN) <= ROUND_GUARD:
                        interior = True
                        break
                if interior:
                    rejected = True
                    break
            ang_a = self._anchor_angle(a, pa, pts[0], pts[1])
            ang_b = self._anchor_angle(b, pb, pts[-1], pts[-2])
            oent = ec.ownang[bok] = (rejected, press_own, ang_a, ang_b)
        rejected, press_own, ang_a, ang_b = oent
        if rejected:
            return (1e9, None)
        press = press_own
        min_clr = 1e9
        cse = ec.cand_segs.get(cki)
        if cse is None:
            cand_segs = list(zip(pts[:-1], pts[1:]))
            cand_bb = [(min(p[0], q[0]), min(p[1], q[1]),
                        max(p[0], q[0]), max(p[1], q[1]))
                       for p, q in cand_segs]
            cse = ec.cand_segs[cki] = (cand_segs, cand_bb)
        cand_segs, cand_bb = cse
        for v, box in self.N.items():
            if v in (a, b):
                continue
            pent = ec.press.get((cki, box))
            if pent is None:
                cx, cy, hw, hh = box
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
                        continue      # press impossible, min_clr not refreshable
                p_u, d_u = 0, 1e9
                for (px, py) in samples:
                    # inlined dist_point_rect (hot loop): same expression,
                    # no per-sample function call
                    ddx = abs(px - cx) - mhw
                    ddy = abs(py - cy) - mhh
                    if ddx < 0.0:
                        ddx = 0.0
                    if ddy < 0.0:
                        ddy = 0.0
                    d = math.hypot(ddx, ddy)
                    if d <= ROUND_GUARD:
                        p_u = 1
                        break
                    if d < d_u:
                        d_u = d
                pent = ec.press[(cki, box)] = (p_u, d_u)
            press += pent[0]
            if pent[1] < min_clr:
                min_clr = pent[1]
        clr_def = max(0.0, self.cl - min_clr) if min_clr < 1e9 else 0.0
        # crossings vs already-routed routes, memoized per (candidate,
        # routed-route content): ints, summation order preserved
        cross = 0
        hit_edges = 0
        for j, (rsegs, rbb) in routed_segs.items():
            rke = ec.route_key(rsegs)
            cent = ec.cross.get((cki, rke))
            if cent is None:
                cj, hit = 0, False
                for si, s1 in enumerate(cand_segs):
                    x1l, y1l, x1h, y1h = cand_bb[si]
                    for k, s2 in enumerate(rsegs):
                        x2l, y2l, x2h, y2h = rbb[k]
                        if x1l > x2h or x2l > x1h or y1l > y2h or y2l > y1h:
                            continue
                        if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                            cj += 1
                            hit = True
                cent = (cj, 1 if hit else 0)
                if len(ec.cross) < ec.CROSS_CAP:
                    ec.cross[(cki, rke)] = cent
            cross += cent[0]
            hit_edges += cent[1]
        length = ec.length.get(cki)
        if length is None:
            length = ec.length[cki] = sum(
                math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        kind_pref = 0.0
        mutual_pair = (min(a, b), max(a, b)) in self.mutual
        pair_sep = None
        sep_def = 0.0
        if mutual_pair and sib_samples:
            # T12: exact memo per (candidate content, sibling-sample content)
            pk = (cki, ec.sib_key(sib_samples))
            ps = ec.pairsep.get(pk)
            if ps is None:
                s12 = ec.samples12.get(cki)
                if s12 is None:
                    s12 = ec.samples12[cki] = sample_polyline(pts, step=12)
                ps = min_pair_dist(s12, sib_samples)
                ps = ec.pairsep[pk] = (
                    ps, max(0.0, PAIR_SEP_MIN - ps) if ps is not None else 0.0)
            pair_sep, sep_def = ps
        if mutual_pair and kind == "arc":
            kind_pref = -2.0
        if kind == "vg":
            kind_pref += 120.0
        if kind == "poly":
            kind_pref += 40.0
        if kind == "wrap":
            kind_pref += 200.0
        if (self.dense and kind != "line"
                and (a == self.dense_hub or b == self.dense_hub)):
            kind_pref += DENSE_SPOKE_STRAIGHT_PENALTY
        if mutual_pair:
            clr_def *= 5.0
        rule_pen = cand[5] if len(cand) > 5 else 0.0
        score = (4000 * press + 40 * cross + 30.0 * clr_def + 0.01 * length +
                 PAIR_SEP_W * sep_def + kind_pref + rule_pen)
        ang_def = max(0.0, ANCHOR_MIN_DEG - ang_a) + max(0.0, ANCHOR_MIN_DEG - ang_b)
        score += 2.0 * ang_def
        if ang_def > 0.5:
            score += 1500.0
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
                # exact-equivalence acceleration (same caliber as
                # _edge_stats): _poly_cross_world bboxes each polyline and
                # walks the opposing seg grid -- a strict bbox-disjoint
                # pair cannot intersect, and the grid lookup sees every
                # segment a bbox-overlapping segment could cross; verdicts
                # identical to the inline double seg_cross loop.
                if self._poly_cross_world(pa, ib, pb):
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

    def _edge_world(self, j, pts):
        """Cached crossing-query world of edge j's polyline: (segs, grid, bbox).

            Content-keyed (exact point tuples), so any route mutation misses
            naturally; bounded clear keeps memory flat.  Pure acceleration:
            the segs are exactly zip(pts[:-1], pts[1:]) as _poly_cross walks
            them, and the grid registers every segment in the cells its bbox
            covers -- two segments intersect only at a point contained in
            both bboxes, so a grid lookup over one segment's bbox cells sees
            every opposing segment it could cross (identical verdicts).
        """
        cache = getattr(self, "_edge_world_cache", None)
        if cache is None:
            cache = self._edge_world_cache = {}
        key = (j, tuple(map(tuple, pts)))
        ent = cache.get(key)
        if ent is None:
            tp = [tuple(p) for p in pts]
            segs = list(zip(tp[:-1], tp[1:]))
            ent = (segs, build_seg_grid_margin(segs, 16),
                   (min(p[0] for p in tp), min(p[1] for p in tp)),
                   (max(p[0] for p in tp), max(p[1] for p in tp)))
            if len(cache) >= 2048:
                cache.clear()
            cache[key] = ent
        return ent

    def _poly_cross_world(self, pa, j, pb):
        """_poly_cross(pa, pb) with pb's segments behind a cached seg grid (exact-equivalent)."""
        segs_b, grid_b, bl, bh = self._edge_world(j, pb)
        ax_lo = min(p[0] for p in pa); ax_hi = max(p[0] for p in pa)
        ay_lo = min(p[1] for p in pa); ay_hi = max(p[1] for p in pa)
        # strict bbox disjointness => no intersection (exact reject)
        if ax_lo > bh[0] or bl[0] > ax_hi or ay_lo > bh[1] or bl[1] > ay_hi:
            return False
        for s1 in zip(pa[:-1], pa[1:]):
            (x1, y1), (x2, y2) = s1[0], s1[1]
            cx1 = int(math.floor(min(x1, x2) / 16)) - 1
            cx2 = int(math.floor(max(x1, x2) / 16)) + 1
            cy1 = int(math.floor(min(y1, y2) / 16)) - 1
            cy2 = int(math.floor(max(y1, y2) / 16)) + 1
            seen = None
            for cx in range(cx1, cx2 + 1):
                for cy in range(cy1, cy2 + 1):
                    bucket = grid_b.get((cx, cy))
                    if not bucket:
                        continue
                    if seen is None:
                        seen = set()
                    for sid in bucket:
                        if sid in seen:
                            continue
                        seen.add(sid)
                        s2 = segs_b[sid]
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
    def _pc_geom(self, pts):
        """Cached coincidence-query world of a polyline: (samples, segs,
        seg grid, sampled bbox lows/highs), content-keyed.

            _route_coincide_pairs re-derives the same sampled geometry for
            the same route content on every pre/post-snap gate evaluation
            (anchor_snap's _coincide_max_span already caches its own copy
            via _coi_geom).  Pure acceleration: the samples/segs are the
            same products _pair_coincide_span computed inline, and the grid
            is the exact-equivalence structure documented on
            span_one_way_segs_grid (differential-tested against
            span_one_way_segs).  Bounded clear keeps memory flat.
        """
        cache = getattr(self, "_pc_geom_cache", None)
        if cache is None:
            cache = self._pc_geom_cache = {}
        key = tuple(map(tuple, pts))
        ent = cache.get(key)
        if ent is None:
            s = sample_polyline(pts)
            segs = list(zip(s[:-1], s[1:]))
            ent = (s, segs, build_seg_grid(segs),
                   (min(p[0] for p in s), min(p[1] for p in s)),
                   (max(p[0] for p in s), max(p[1] for p in s)))
            if len(cache) >= 2048:
                cache.clear()
            cache[key] = ent
        return ent

    def _pair_coincide_span(self, pts_a, pts_b):
        """Adherence span (px) between two polylines, max over both directions -- same source as the certificate's _coincidence_span.

            Grid-accelerated with a bbox prefilter (exact-equivalence
            precedent: _coincide_max_span).  A polyline whose sampled bbox
            is farther than thr from the other's sampled bbox can carry no
            sample within thr of any opposing segment, so its one-way span
            is 0 -- the membership decision span_one_way_segs makes is
            identical and the returned value bit-identical.
        """
        sa, segs_a, grid_a, al, ah = self._pc_geom(pts_a)
        sb, segs_b, grid_b, bl, bh = self._pc_geom(pts_b)
        total_a = 0.0
        if not (al[0] - bh[0] > COINCIDE_THR or bl[0] - ah[0] > COINCIDE_THR
                or al[1] - bh[1] > COINCIDE_THR or bl[1] - ah[1] > COINCIDE_THR):
            total_a = span_one_way_segs_grid(sa, segs_b, grid_b)
        total_b = 0.0
        if not (bl[0] - ah[0] > COINCIDE_THR or al[0] - bh[0] > COINCIDE_THR
                or bl[1] - ah[1] > COINCIDE_THR or al[1] - bh[1] > COINCIDE_THR):
            total_b = span_one_way_segs_grid(sb, segs_a, grid_a)
        return max(total_a, total_b)

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
        # WS5 performance caliber (same as _evaluate_base): bbox-vs-box gap
        # lower bound -- if the lower bound > ROUND_GUARD, press is
        # impossible; if it >= the current min_clr, min_clr cannot be
        # refreshed.  When both hold the whole box is skipped (exactly
        # equivalent: sample evaluation order and every kept value
        # unchanged).
        bxl = min(p[0] for p in samples)
        bxh = max(p[0] for p in samples)
        byl = min(p[1] for p in samples)
        byh = max(p[1] for p in samples)
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
                mc = min_clr if min_clr is not None else 1e9
                lb2 = 0.0
                if gx > 0.0:
                    lb2 = gx * gx
                if gy > 0.0:
                    lb2 += gy * gy
                if lb2 >= mc * mc:
                    continue          # press impossible, min_clr not refreshable
            for (px, py) in samples:
                # inlined dist_point_rect (hot loop, WS5 caliber): same
                # expression, no per-sample function call
                ddx = abs(px - cx) - mhw
                ddy = abs(py - cy) - mhh
                if ddx < 0.0:
                    ddx = 0.0
                if ddy < 0.0:
                    ddy = 0.0
                d = math.hypot(ddx, ddy)
                if d <= ROUND_GUARD:
                    press += 1
                    break
                if min_clr is None or d < min_clr:
                    min_clr = d
        ang_min = min(self._anchor_angle(a, pts[0], pts[0], pts[1]),
                      self._anchor_angle(b, pts[-1], pts[-1], pts[-2]))
        cross = 0
        for j, o in routes.items():
            if j == i or self.edges[j][0] in self.edges[i] or \
                    self.edges[j][1] in self.edges[i]:
                continue
            if self._poly_cross_world(pts, j, o["points"]):
                cross += 1
        msep = None
        j = self.eidx.get((b, a))
        if j is not None and j in routes and j != i:
            msep = min_pair_dist(sample_polyline(pts, step=4),
                                 sample_polyline(routes[j]["points"], step=4))
        return (press, min_clr, ang_min, cross, msep)

    def fan_spread(self, routes, frozen=()):
        """Same node side with >= 2 anchors: sort by the other endpoint's azimuth and spread symmetrically on both sides of the midpoint along the border tangent.

                2026-11-06 connection-point accounting hard rule 3 (jacky): multiple outgoing lines on the same node must not pile up at the
                same border midpoint -- spread uniformly with step FAN_STEP, clamped inside the border at +/-(half-3).
                2026-11-09 ref-scrubbed (jacky): slot ORDER is azimuth-monotone -- on t/b borders by the other box center's horizontal
                offset, on r/l borders by its vertical offset -- so anchor order along the border always matches the targets'
                left/right (top/bottom) positions (the former incidence-angle key could invert neighbours and produce a
                visible X crossing, classic-cld adopters box). After spreading, every
                edge rechecks the hard gates (press/clearance/anchor angle/no crossing increase/mutual separation >= 4px); on any violation
                the whole node falls back to border-midpoint anchors (deterministic: fixed traversal order + fixed step, no RNG).
                frozen edges (constructed routes / user waypoints) are untouched.

                ref-scrubbed: frozen edges' anchors on the same node side OCCUPY their
                position. A fan whose middle slot lands on a frozen anchor produced a
                V-shaped co-point at the border midpoint (classic-cld: the frozen spine
                rate->adopters leaves rate's top-border midpoint while the 3-slot fan
                held word->rate on the same midpoint; same pattern at adopters' bottom).
                On conflict the whole fan gives way: deterministic candidate shifts
                (+FAN_STEP/2 preferred, then -FAN_STEP/2, then whole steps), each
                candidate band-scaled as a whole (slot order and equal spacing
                preserved) and rechecked against the same hard gates; a candidate that
                still lands within MIN_FROZEN_ANCHOR_SEP of a frozen anchor is skipped.
                No frozen anchors / no conflict -> byte-for-byte the previous behavior.
        """
        # ref-scrubbed: index the frozen edges' anchors by (node, side) so the
        # fan slot assignment below can treat them as occupied positions.
        # Stored as (anchor point, other-endpoint node id) so the group loop
        # can also check azimuth monotonicity across the frozen anchors.
        frozen_side = {}
        for i2 in sorted(routes.keys()):
            if i2 not in frozen:
                continue
            pts2 = routes[i2]["points"]
            a2, b2 = self.edges[i2]
            for end2, p2 in (("a", pts2[0]), ("b", pts2[-1])):
                v2 = a2 if end2 == "a" else b2
                other2 = b2 if end2 == "a" else a2
                frozen_side.setdefault((v2, self._side_of(v2, p2)),
                                       []).append((tuple(p2), other2))
        # ref-scrubbed: arc-kind routes are NOT slot-slidable. Sliding only the
        # anchor endpoint of a smooth Q-arc leaves the curve (and its ctrl
        # point) shaped for the OLD anchor -- measured on classic-cld
        # crowding<->fundamental: the anchor slid 519.3->508.0 while the arc
        # body stayed, departure skew 5.3->33.4 deg, and the mutual pair's
        # two lines converged 12.0->7.3px (the lens "twisted arrow" defect).
        # Arc anchors therefore OCCUPY their position (same accounting as
        # frozen anchors below: MIN_FROZEN_ANCHOR_SEP clearance + merged
        # azimuth monotonicity) and the fan spreads only the
        # implicitly-reshaping routes (straight lines) around them.
        for i2 in sorted(routes.keys()):
            if i2 in frozen or routes[i2].get("kind") != "arc":
                continue
            pts2 = routes[i2]["points"]
            a2, b2 = self.edges[i2]
            for end2, p2 in (("a", pts2[0]), ("b", pts2[-1])):
                v2 = a2 if end2 == "a" else b2
                if self.dense and v2 == self.dense_hub:
                    # dense: hub-side arc endpoints are SLIDABLE group
                    # members below (grid slots + ctrl lockstep), so they
                    # must not occupy their side as frozen anchors.
                    continue
                other2 = b2 if end2 == "a" else a2
                frozen_side.setdefault((v2, self._side_of(v2, p2)),
                                       []).append((tuple(p2), other2))
        groups = {}
        for i in sorted(routes.keys()):
            if i in frozen:
                continue
            _arc = routes[i].get("kind") == "arc"
            if _arc and not (self.dense and self.dense_hub in self.edges[i]):
                # ref-scrubbed: arc-kind routes are NOT slot-slidable on
                # the legacy path (stale-curve defect); only the dense
                # hub branch slides them (ctrl lockstep + re-discretize).
                continue
            pts = routes[i]["points"]
            a, b = self.edges[i]
            for end, p in (("a", pts[0]), ("b", pts[-1])):
                v = a if end == "a" else b
                if _arc and v != self.dense_hub:
                    # dense arc member: only the HUB-side end joins the
                    # slidable group (the leaf end keeps its anchor).
                    continue
                groups.setdefault((v, self._side_of(v, p)), []).append(
                    (i, end, tuple(p)))
        for (v, side), entries in sorted(groups.items()):
            # dense branch (dense-only, HUB box groups, dense card): the
            # mid-band clamp relaxes to the FULL edge and slots run on the
            # DENSE_FAN_STEP grid (shrinking to the 6px grid before any
            # sharing) with controlled sharing; the whole-node "fall back
            # to border-midpoint anchors" path below is ABOLISHED for
            # these groups (gate table #2 — the uncontrolled fallback is
            # what produced the 0px pileups).  Arc-kind members JOIN the
            # dense group (endpoint slides on the grid with lockstep ctrl
            # translation + Bezier re-discretization — the same reshape
            # accounting as anchor_snap tier 1); on the legacy path they
            # stay excluded (ref-scrubbed discipline).  Leaf boxes and
            # every non-dense graph keep the legacy path byte-for-byte.
            dense_grp = (self.dense and v == self.dense_hub
                         and not frozen_side.get((v, side)))
            # ref-scrubbed: single-entry groups join when frozen/arc anchors
            # occupy the same (node, side) -- the occupied-slot accounting
            # (clearance >= MIN_FROZEN_ANCHOR_SEP + merged azimuth
            # monotonicity) must also cover the 1-slidable + N-frozen case
            # (renewable-resource harvest box: the frozen lens arc and the
            # detour poly both landed on the border midpoint -> the poly's
            # final segment ran into the arc's arrival, a T-junction the
            # shared-endpoint exemption hides from the old caliber). Groups
            # with no frozen anchors on their side keep the >= 2 rule;
            # dense hub groups always join (single lines still quantize
            # onto the slot grid).
            if len(entries) < 2 and not dense_grp \
                    and not frozen_side.get((v, side)):
                continue
            cx, cy, hw, hh = self.N[v]
            vertical = side in ("r", "l")
            half_len = (hh if vertical else hw) - 3

            def _azi_key(ent):
                # ref-scrubbed: slot order must be monotone with the other
                # endpoint's azimuth (not the route segment's incidence
                # angle): on a horizontal border (t/b) sort by the other
                # box center's horizontal offset, on a vertical border
                # (r/l) by its vertical offset, ascending = left-to-right /
                # top-to-bottom slot order. The incidence-angle key could
                # invert left/right neighbours (classic-cld adopters box:
                # word vs potential anchors swapped -> visible X crossing
                # under the box). Tie-break by edge index (deterministic).
                i2, end, _p = ent
                a2, b2 = self.edges[i2]
                ox, oy, _ow, _oh = self.N[b2 if end == "a" else a2]
                # ref-scrubbed: entry-side (target-end) tie-break -- when two
                # fan members' other-box azimuths tie (both boxes centered on
                # the border axis), the box-center key cannot order them and
                # the index tie-break inverted neighbours whose ROUTES
                # approach from opposite sides (population-logistic births
                # box: the detour poly arrives from the right, the direct
                # line from straight above -> visible X). Secondary key = the
                # approach point's projection (the polyline point just before
                # the anchor): for straight lines this is the other border
                # anchor (azimuth-consistent), for detour routes it is the
                # last via -- the direction the line actually comes from.
                pts2 = routes[i2]["points"]
                ap = pts2[1] if end == "a" else pts2[-2]
                proj = (ap[1] - cy) if vertical else (ap[0] - cx)
                return ((oy - cy) if vertical else (ox - cx)), proj, i2
            ents = sorted(entries, key=_azi_key)
            k = len(ents)
            # ref-scrubbed: keep the fan inside the ref-scrubbed mid-band
            # (+/- 1/4 of the owning box dimension, the CI in-band gate):
            # when the fan half-span exceeds the band, scale the whole fan
            # uniformly into it (monotone slot order and equal spacing are
            # preserved, no stacking; deterministic).
            band = (hh if vertical else hw) / 2.0
            if dense_grp:
                band = half_len          # gate table #2: full-edge band
            # ref-scrubbed: frozen anchors on this same node side occupy their
            # tangent offset; the fan must not land on them (V co-point).
            frozen_offs = []
            for _pf, _of in frozen_side.get((v, side), ()):
                frozen_offs.append((_pf[1] - cy) if vertical
                                   else (_pf[0] - cx))
            _frozen_az = []
            for _pf, _of in frozen_side.get((v, side), ()):
                ox2, oy2, _ow2, _oh2 = self.N[_of]
                _frozen_az.append(((oy2 - cy) if vertical else (ox2 - cx),
                                   (_pf[1] - cy) if vertical
                                   else (_pf[0] - cx)))

            # its slot base is the CURRENT anchor position (not the border
            # midpoint): with no frozen conflict it must reproduce the
            # incoming position byte-for-byte (offs == [base] restores it),
            # and on conflict the candidate ladder shifts it off the frozen
            # anchor while staying clamped inside the border.
            k1_base = 0.0
            if k == 1:
                _p0 = ents[0][2]
                k1_base = (_p0[1] - cy) if vertical else (_p0[0] - cx)

            def _offs_for(shift):
                if dense_grp:
                    return _dense_fan_offsets(k, half_len, shift)
                if k == 1:
                    return [max(-half_len, min(half_len, k1_base + shift))]
                raw = [(t2 - (k - 1) / 2.0) * FAN_STEP + shift
                       for t2 in range(k)]
                half_span = max(abs(o) for o in raw)
                if half_span > band:
                    raw = [o * band / half_span for o in raw]
                return raw

            def _frozen_conflict(offs):
                # (a) clearance: no slot within MIN_FROZEN_ANCHOR_SEP of a
                # frozen anchor (kills the V co-point);
                # (b) azimuth monotonicity ACROSS the frozen anchors (the
                # ref-scrubbed rule extended): slots that would move to the
                # opposite side of a frozen anchor from their target box
                # produce a line crossing that edge (its shared-endpoint
                # exemption hides it from _edge_stats), so merged
                # (position, other-box azimuth) must stay monotone.
                for o in offs:
                    for f in frozen_offs:
                        if abs(o - f) < MIN_FROZEN_ANCHOR_SEP:
                            return True
                merged = [(o, az) for o, az in
                          zip(offs, [(_azi_key(e)[0]) for e in ents])]
                merged += [(f, az) for az, f in _frozen_az]
                merged.sort()
                for m1, m2 in zip(merged, merged[1:]):
                    if m2[1] < m1[1] - 1e-9:
                        return True
                return False

            # ref-scrubbed: a single-slidable-entry fan is give-way-only --
            # and with NO frozen conflict at the current slot it is skipped
            # entirely: rewriting the anchor through offs == [base] would
            # flip the coordinate's int/float JSON face (limits-to-growth
            # word->rate measured: geometry identical, layout.json bytes
            # drifted). Only a real conflict enters the candidate ladder.
            if (k == 1
                    and not dense_grp
                    and not (frozen_offs
                             and _frozen_conflict(_offs_for(0.0)))):
                continue
            if dense_grp:
                # dense Q4 cap accounting: the sharing factor that the
                # placement needs; above DENSE_CAP_PER_SLOT the
                # placement proceeds deterministically but the exceed is
                # recorded as an honest L2-style degrade (never silently).
                _n_slots = int(math.floor((2.0 * half_len)
                                          / DENSE_FAN_STEP)) + 1
                if k > _n_slots:
                    _n_slots = int(math.floor((2.0 * half_len)
                                              / DENSE_GRID_STEP)) + 1
                _s_share = -(-k // _n_slots)
                if _s_share > DENSE_CAP_PER_SLOT:
                    self.dense_degrade.append(
                        {"stage": "fan_spread", "node": v, "side": side,
                         "lines": k, "shared_per_slot": _s_share,
                         "reason": "per-slot sharing cap %d exceeded — L2 honest degrade"
                                   % DENSE_CAP_PER_SLOT})
            # candidate give-way shifts, deterministic: centered first, then
            # half-steps (right preferred), then whole steps. Shift 0 with no
            # frozen anchors / no conflict reproduces the previous offs
            # exactly (byte-for-byte zero drift for unaffected figures).
            cand_shifts = [0.0]
            if frozen_offs and _frozen_conflict(_offs_for(0.0)):
                cand_shifts += [FAN_STEP / 2.0, -FAN_STEP / 2.0,
                                FAN_STEP, -FAN_STEP,
                                1.5 * FAN_STEP, -1.5 * FAN_STEP]
            before = {i2: [list(p) for p in routes[i2]["points"]]
                      for i2, _e, _p in ents}
            before_ctrl = {i2: (list(routes[i2]["ctrl"])
                                if routes[i2].get("ctrl") is not None
                                else None)
                           for i2, _e, _p in ents}

            def _dense_set(i2, end, off):
                """Dense endpoint slide: straight lines set the tangent
                coordinate directly; arcs translate ctrl in lockstep with
                the endpoint delta and re-discretize the Bezier (same
                reshape accounting as anchor_snap tier 1)."""
                base_pts, base_ctrl = before[i2], before_ctrl[i2]
                pts2 = [list(q) for q in base_pts]
                idx = 0 if end == "a" else len(pts2) - 1
                if vertical:
                    new = max(cy - half_len, min(cy + half_len, cy + off))
                    dx, dy = 0.0, new - base_pts[idx][1]
                    pts2[idx] = [base_pts[idx][0], new]
                else:
                    new = max(cx - half_len, min(cx + half_len, cx + off))
                    dx, dy = new - base_pts[idx][0], 0.0
                    pts2[idx] = [new, base_pts[idx][1]]
                if base_ctrl is not None:
                    ctrl = [base_ctrl[0] + dx, base_ctrl[1] + dy]
                    p0, p1 = (pts2[idx], pts2[-1]) if idx == 0 \
                        else (pts2[0], pts2[idx])
                    routes[i2]["points"] = [list(q)
                                            for q in quad_points(p0, ctrl, p1)]
                    routes[i2]["ctrl"] = ctrl
                else:
                    routes[i2]["points"] = pts2

            stats_before = {i2: self._edge_stats(i2, routes)
                            for i2, _e, _p in ents}
            ok = False
            for shift in cand_shifts:
                offs = _offs_for(shift)
                if _frozen_conflict(offs):
                    continue
                for i2, pts_b in before.items():
                    routes[i2]["points"] = [list(p) for p in pts_b]
                    _c = before_ctrl[i2]
                    if _c is not None and routes[i2].get("ctrl") is not None:
                        routes[i2]["ctrl"] = list(_c)
                if dense_grp:
                    for (i2, end, _p), off in zip(ents, offs):
                        _dense_set(i2, end, off)
                else:
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
                    # T4: unified delivery-gate caliber (docs/routing-gates.md G-FAN;
                    # no own-box check -- registered caliber gap)
                    # dense: G-FAN-DENSE policy (msep floor 3.0) + the
                    # relaxed dense angle floor for hub edges (Q2).
                    if not _gates.edge_gate_check(
                            self, i2, routes,
                            _gates.GateBaseline(stats={i2: stats_before[i2]}),
                            _gates.FAN_SPREAD_DENSE if dense_grp
                            else _gates.FAN_SPREAD,
                            min_deg=(DENSE_ANCHOR_MIN_DEG if dense_grp
                                     else None)):
                        ok = False
                        break
                if ok:
                    break
            if not ok:
                if dense_grp:
                    # dense: the whole-node midpoint fallback is ABOLISHED
                    # (gate table #2) — re-apply the base (shift-0) grid
                    # placement deterministically and record the honest
                    # degrade; the hard gates still grade the delivery.
                    _offs0 = _offs_for(0.0)
                    for i2, pts_b in before.items():
                        routes[i2]["points"] = [list(p) for p in pts_b]
                        _c = before_ctrl[i2]
                        if _c is not None and routes[i2].get("ctrl") is not None:
                            routes[i2]["ctrl"] = list(_c)
                    for (i2, end, _p), off in zip(ents, _offs0):
                        _dense_set(i2, end, off)
                    self.dense_degrade.append(
                        {"stage": "fan_spread", "node": v, "side": side,
                         "lines": k,
                         "reason": "fan hard gates fail on every shift; "
                                   "midpoint fallback abolished (dense) — "
                                   "grid placement kept, graded honestly"})
                else:
                    for i2, pts_b in before.items():
                        routes[i2]["points"] = pts_b
        return routes

    def fan_slot_reorder(self, routes, frozen=()):
        """Fan slot competition by SWAP, keyed by the departure azimuth φ.

        jacky 2026-11-26 approval (multi-slot anchor vocabulary card),
        grounded in the stdraw20 manual-calibration lessons §4: the fan X
        5→3 fix came from SWAPPING the two competing anchors at the shared
        node, keyed by the departure azimuth φ rather than the far-end
        coordinate -- a far-end-monotone slot order still crosses when the
        routes approach the shared node from opposite sides (detour vs
        direct), which is exactly the case the azimuth/projection ordering
        in fan_spread cannot see.

        For every (node, side) group of >= 2 slidable fan members (same
        membership rules as fan_spread: frozen edges and non-dense arc
        routes are excluded; dense hub groups keep their own grid machinery
        and are skipped entirely), count crossings among the members' NEAR
        segments (anchor -> adjacent polyline point).  On any crossing, try
        candidate slot orders in fixed order: first the φ order (members
        sorted by the near-segment direction's projection on the border
        tangent axis, ascending with slot position; ties by edge index),
        then each crossing pair's simple swap.  Accept the first candidate
        that (a) passes every member's FAN_SPREAD edge gates against the
        pre-change baseline, (b) strictly reduces the near-segment crossing
        count, and (c) does not increase the route-level crossing count.
        Unaffected groups and rejected candidates restore the input
        byte-for-byte (deterministic: sorted traversal, fixed candidate
        order, no RNG).
        """
        groups = {}
        for i in sorted(routes.keys()):
            if i in frozen or routes[i].get("kind") == "arc":
                continue
            pts = routes[i]["points"]
            a, b = self.edges[i]
            for end, p in (("a", pts[0]), ("b", pts[-1])):
                v = a if end == "a" else b
                if self.dense and v == self.dense_hub:
                    continue    # dense hub groups keep their grid machinery
                groups.setdefault((v, self._side_of(v, p)), []).append(
                    (i, end, tuple(p)))
        report = []
        for (v, side), entries in sorted(groups.items()):
            k = len(entries)
            if k < 2:
                continue
            cx, cy, hw, hh = self.N[v]
            vertical = side in ("r", "l")
            half_len = (hh if vertical else hw) - 3
            # near segment + φ projection key per member
            near = {}
            phi = {}
            offs = {}
            for (i2, end2, p2) in entries:
                pts2 = routes[i2]["points"]
                if end2 == "a":
                    q2 = pts2[1]
                    idx = 0
                else:
                    q2 = pts2[-2]
                    idx = len(pts2) - 1
                near[i2] = (tuple(pts2[idx]), tuple(q2))
                # projection of the near-segment direction on the border
                # tangent axis (the azimuth φ measure; ascending with slot
                # position = crossing-free assignment)
                d2 = (q2[0] - p2[0], q2[1] - p2[1])
                phi[i2] = d2[1] if vertical else d2[0]
                offs[i2] = p2[1] if vertical else p2[0]
            cross_pairs = []
            n_before = 0
            members = [e[0] for e in entries]
            for a_i in range(k):
                for b_i in range(a_i + 1, k):
                    m1, m2 = members[a_i], members[b_i]
                    if seg_cross(near[m1][0], near[m1][1],
                                 near[m2][0], near[m2][1]):
                        cross_pairs.append((m1, m2))
                        n_before += 1
            if not cross_pairs:
                continue
            cur_order = list(members)
            cands = [tuple(sorted(members, key=lambda m: (phi[m], m)))]
            for (m1, m2) in cross_pairs:
                o = list(cur_order)
                o[o.index(m1)], o[o.index(m2)] = o[o.index(m2)], o[o.index(m1)]
                cands.append(tuple(o))
            seen, cands_u = set(), []
            for o in cands:
                if o not in seen and o != tuple(cur_order):
                    seen.add(o)
                    cands_u.append(o)
            before = {m: [list(p) for p in routes[m]["points"]]
                      for m in members}
            stats_before = {m: self._edge_stats(m, routes) for m in members}
            pre_pairs = self.final_crossing_pairs(routes)
            baseline = _gates.GateBaseline(stats=stats_before)
            applied = False
            for order in cands_u:
                # restore, then assign sorted offsets in candidate order
                for m in members:
                    routes[m]["points"] = [list(p) for p in before[m]]
                sorted_offs = sorted(offs[m] for m in members)
                for m, o_new in zip(order, sorted_offs):
                    _i, _end, _p = next(e for e in entries if e[0] == m)
                    pts2 = routes[m]["points"]
                    idx = 0 if _end == "a" else len(pts2) - 1
                    if vertical:
                        pts2[idx] = [pts2[idx][0],
                                     max(cy - half_len,
                                         min(cy + half_len, o_new))]
                    else:
                        pts2[idx] = [max(cx - half_len,
                                         min(cx + half_len, o_new)),
                                     pts2[idx][1]]
                n_after = 0
                for a_i in range(k):
                    for b_i in range(a_i + 1, k):
                        m1, m2 = members[a_i], members[b_i]
                        p1 = routes[m1]["points"]
                        p2 = routes[m2]["points"]
                        s1 = ((tuple(p1[0]), tuple(p1[1]))
                              if next(e for e in entries if e[0] == m1)[1] == "a"
                              else (tuple(p1[-2]), tuple(p1[-1])))
                        s2 = ((tuple(p2[0]), tuple(p2[1]))
                              if next(e for e in entries if e[0] == m2)[1] == "a"
                              else (tuple(p2[-2]), tuple(p2[-1])))
                        if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                            n_after += 1
                if n_after >= n_before:
                    continue
                if self.final_crossing_pairs(routes) > pre_pairs:
                    continue
                ok = True
                for m in members:
                    if not _gates.edge_gate_check(
                            self, m, routes, baseline, _gates.FAN_SPREAD):
                        ok = False
                        break
                if not ok:
                    continue
                applied = True
                report.append({"node": v, "side": side,
                               "members": [f"{self.edges[m][0]}->{self.edges[m][1]}"
                                           for m in order],
                               "near_crossings": [n_before, n_after]})
                break
            if not applied:
                for m in members:
                    routes[m]["points"] = before[m]
        if report:
            self.fan_reorder_report = report
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
            # T4: unified delivery-gate caliber (docs/routing-gates.md G-PAIR-BAND)
            for k2, st0 in ((i, st_i0), (j, st_j0)):
                if not _gates.edge_gate_check(
                        self, k2, routes,
                        _gates.GateBaseline(stats={k2: st0}),
                        _gates.PAIR_BAND):
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
                    # T4: unified delivery-gate caliber (docs/routing-gates.md
                    # G-MUTUAL-STRAIGHT): press==0 absolute; per-edge crossing cap
                    # (i: the replaced route's _evaluate cross; j: the pre-change
                    # _edge_stats cross -- two accountings, preserved verbatim).
                    ok = True
                    for k2 in (i, j):
                        if not _gates.edge_gate_check(
                                self, k2, routes,
                                _gates.GateBaseline(cross_cap={i: cur_cross,
                                                               j: st_j0[3]}),
                                _gates.MUTUAL_STRAIGHT):
                            ok = False
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
                # T4: unified delivery-gate caliber (docs/routing-gates.md
                # G-MIDBAND-T0; no own-box check -- registered caliber gap)
                ok = _gates.edge_gate_check(
                    self, i, routes,
                    _gates.GateBaseline(stats={i: before}),
                    _gates.MIDBAND_TIER0)
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
                # T4: unified delivery-gate caliber (docs/routing-gates.md G-MIDBAND-T1)
                ok = _gates.edge_gate_check(
                    self, i, routes,
                    _gates.GateBaseline(stats={i: before}),
                    _gates.MIDBAND_CLAMP)
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

    def mutual_arrival_flip(self, routes, frozen=(), enhanced_gates=False):
        """ref-scrubbed: mutual-lens arrow-normal channel (engine-wide).

        A Q-arc lens between vertically stacked but horizontally offset boxes
        has end tangents that trade off with the bulge: on classic-cld
        crowding<->fundamental the delivered lens (bulge 16.3px, ctrl at 0.5
        of the chord) made BOTH arrows arrive 24.1 deg off the border normal
        -- the "twisted arrow" look. Arrows are drawn along the arrival
        tangent, so the arrival deviation is the defect carrier.

        Feasibility (measured on this pair, chord tilt 8.6 deg): both ends
        <= ARRIVAL_TARGET_DEG requires a slim lens (bulge ~1-2px, ctrl at
        ~0.3 of the chord) -- the fat lens is geometrically incompatible with
        near-normal arrows on a tilted chord. This channel re-derives both
        arcs' ctrl from an (alpha along chord, outward bulge B) ladder,
        searching for the FULLEST lens that meets the arrival target
        (largest B first among meeting candidates); if none meets the
        target, the min-max-deviation candidate wins. Strict-improvement +
        hard-gate guarded (press / clearance / crossings / mutual separation
        no-regression / anchor angles / own-box); anchors are untouched, so
        the fan_spread occupied-slot accounting stays consistent. Routes are
        returned untouched (byte-for-byte) when no candidate improves.

        ref-scrubbed enhanced_gates=True (the post-anchor_snap second call):
        the gate accounting switches to the anchor-snap calibers --
        clearance at the CI raw accounting (>= CLEARANCE - PRESS_MARGIN on
        the inflated measure) and own-box intrusion comparative via
        _own_press (inset-3px anchors put attachment-zone samples inside the
        1px-inflated margin by construction, so the absolute _own_box_ok
        gate can never pass and would veto every candidate).  The first
        (pre-snap) call keeps the legacy gates byte-for-byte.
        """
        SideNorm = {"t": (0.0, -1.0), "b": (0.0, 1.0),
                    "r": (1.0, 0.0), "l": (-1.0, 0.0)}

        def _devs(inf, a, b):
            ctrl = inf.get("ctrl")
            if ctrl is None:
                return None
            pts = inf["points"]
            p0, p1 = pts[0], pts[-1]
            n0 = SideNorm[self._side_of(a, p0)]
            n1 = SideNorm[self._side_of(b, p1)]

            def _d(v, n):
                n_ = math.hypot(v[0], v[1])
                if n_ < 1e-9:
                    return None
                c = abs(v[0] * n[0] + v[1] * n[1]) / n_
                return math.degrees(math.acos(max(0.0, min(1.0, c))))

            dep = _d((ctrl[0] - p0[0], ctrl[1] - p0[1]), n0)
            arr = _d((p1[0] - ctrl[0], p1[1] - ctrl[1]), n1)
            if dep is None or arr is None:
                return None
            return dep, arr

        ALPHAS = (0.3, 0.4, 0.5, 0.6, 0.7)
        BULGES = (6.0, 5.0, 4.0, 3.0, 2.5, 2.0, 1.5, 1.0)
        if enhanced_gates:
            # ref-scrubbed: on the anchored mirror chords the box-center offset
            # (crowding/fundamental: 24px over 122px) puts one chord's tilt at
            # ~13.8 deg, so the arrival target (<=10 deg) is unreachable in
            # the fat-lens domain; the high-alpha tiers (ctrl near the arrival
            # end) let the flip re-fit the pair into a slim near-parallel
            # double line that meets the target on BOTH arrows.
            ALPHAS = ALPHAS + (0.8, 0.9, 0.95)

        for key in sorted(self.mutual):
            i1 = self.eidx.get((key[0], key[1]))
            i2 = self.eidx.get((key[1], key[0]))
            if i1 is None or i2 is None or i1 in frozen or i2 in frozen:
                continue
            inf1, inf2 = routes.get(i1), routes.get(i2)
            if not inf1 or not inf2:
                continue
            if inf1.get("kind") != "arc" or inf2.get("kind") != "arc":
                continue
            if inf1.get("ctrl") is None or inf2.get("ctrl") is None:
                continue
            geo = []
            ok_geo = True
            for i in (i1, i2):
                inf = routes[i]
                pts = inf["points"]
                dx, dy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
                L = math.hypot(dx, dy)
                if L < 1e-9:
                    ok_geo = False
                    break
                ux, uy = dx / L, dy / L
                px, py = -uy, ux
                mid = (pts[0][0] + dx / 2.0, pts[0][1] + dy / 2.0)
                b_sign = ((inf["ctrl"][0] - mid[0]) * px
                          + (inf["ctrl"][1] - mid[1]) * py)
                geo.append((pts[0], dx, dy, (px, py),
                            1.0 if b_sign >= 0 else -1.0, abs(b_sign)))
            if not ok_geo:
                continue
            cur1 = _devs(inf1, *self.edges[i1])
            cur2 = _devs(inf2, *self.edges[i2])
            if cur1 is None or cur2 is None:
                continue
            cur_all = cur1 + cur2
            cur_m = (max(cur_all), max(cur1[1], cur2[1]))
            cands = []
            for alpha in ALPHAS:
                for B in BULGES:
                    c1 = (geo[0][0][0] + alpha * geo[0][1]
                          + geo[0][4] * B * geo[0][3][0],
                          geo[0][0][1] + alpha * geo[0][2]
                          + geo[0][4] * B * geo[0][3][1])
                    c2 = (geo[1][0][0] + alpha * geo[1][1]
                          + geo[1][4] * B * geo[1][3][0],
                          geo[1][0][1] + alpha * geo[1][2]
                          + geo[1][4] * B * geo[1][3][1])
                    t1 = _devs({"ctrl": c1, "points": inf1["points"]},
                               *self.edges[i1])
                    t2 = _devs({"ctrl": c2, "points": inf2["points"]},
                               *self.edges[i2])
                    if t1 is None or t2 is None:
                        continue
                    all_d = t1 + t2
                    m = (max(all_d), max(t1[1], t2[1]))
                    meets = m[0] <= ARRIVAL_TARGET_DEG + 1e-9
                    cands.append(((0 if meets else 1, -B, m[0], m[1]),
                                  alpha, B, m))
            cands.sort(key=lambda c: (c[0][0], c[0][2], -c[0][1])
                       if enhanced_gates else c[0])
            _dbg(lambda: f"  [flipdbg] pair={key} cur_m={cur_m} ncands={len(cands)} "
                         f"best_meet={next((c[0] for c in cands if c[0][0] == 0), None)}")
            stats_before = {i: self._edge_stats(i, routes)
                            for i in (i1, i2)}
            own_before = ({i: self._own_press(i, routes) for i in (i1, i2)}
                          if enhanced_gates else None)
            sep_floor = max(4.0, min(stats_before[i1][4]
                                     if stats_before[i1][4] is not None
                                     else 4.0,
                                     stats_before[i2][4]
                                     if stats_before[i2][4] is not None
                                     else 4.0) - 0.05)
            if enhanced_gates:
                # ref-scrubbed: post-snap the joint lens pass delivers a wide
                # mirrored attachment (separation ~21px); locking the floor to
                # that would veto every slim re-fit candidate -- the arrival
                # target needs a SLIM lens on the anchored chord.  The lens
                # floor returns to the ref-scrubbed caliber (>= 12px).
                sep_floor = max(12.0, min(sep_floor, 12.0))
            for _rk, alpha, B, m in cands:
                if not enhanced_gates:
                    # legacy strict improvement (pre-snap path, zero drift)
                    if not (m[0] < cur_m[0] - 1e-9
                            and m[1] < cur_m[1] - 1e-9):
                        continue
                # ref-scrubbed enhanced: no strict-improvement path dependence --
                # every candidate is gate-checked against the pre-flip state
                # (stats_before) below and the search naturally stops at the
                # best-scoring candidate via the sorted order + ok break.
                saved = {i: (routes[i]["points"], routes[i].get("ctrl"))
                         for i in (i1, i2)}
                for i, g in ((i1, geo[0]), (i2, geo[1])):
                    inf = routes[i]
                    cx = g[0][0] + alpha * g[1] + g[4] * B * g[3][0]
                    cy = g[0][1] + alpha * g[2] + g[4] * B * g[3][1]
                    inf["points"] = quad_points(inf["points"][0],
                                                [cx, cy], inf["points"][-1])
                    inf["ctrl"] = [cx, cy]
                # T4: unified delivery-gate caliber (docs/routing-gates.md
                # G-ARRIVAL): the legacy/enhanced clearance + own-box caliber
                # split is expressed by the policy pair below (no caliber change).
                _pol = (_gates.ARRIVAL_ENHANCED if enhanced_gates
                        else _gates.ARRIVAL_LEGACY)
                _base = _gates.GateBaseline(
                    stats=dict(stats_before),
                    own=dict(own_before) if own_before else {})
                ok = True
                for i in (i1, i2):
                    ok = _gates.edge_gate_check(
                        self, i, routes, _base, _pol, msep_floor=sep_floor)
                    def _flip_gate_msg():
                        pr, clr, ang, cross, msep = self._edge_stats(i, routes)
                        pr0, clr0, ang0, cross0, msep0 = stats_before[i]
                        return (f"  [flipdbg] {i} alpha={alpha} B={B} ok={ok} "
                                f"pr={pr}<={pr0} clr={clr} ang={ang:.1f} "
                                f"msep={msep}>={sep_floor:.1f} "
                                f"own={self._own_press(i, routes)}"
                                f"<={own_before[i] if own_before else '?'}")
                    _dbg(_flip_gate_msg)
                    if not ok:
                        break
                if ok:
                    break
                for i, (pts_b, ctrl_b) in saved.items():
                    routes[i]["points"] = pts_b
                    if ctrl_b is not None:
                        routes[i]["ctrl"] = ctrl_b
        return routes

    # -- ref-scrubbed: joint anchor re-assignment for lens pairs the flip cannot fix --
    def lens_joint_reassign(self, routes, lens_pairs, frozen=()):
        """Joint anchor re-assignment when the ctrl-only flip misses the target.

        ref-scrubbed's joint snap assigns each lens arc a MIRRORED anchor pair
        (golden first, corner fallback).  On classic-cld crowding<->fundamental
        the quantized mirror offsets (+-10.6px on crowding / +-16.5px on
        fundamental over a 24px box-center offset) force one chord tilt to
        13.8 deg, and the ctrl-only re-fit bottoms out at 14.4 deg delivered
        (per-arc floor ~11.5) -- the pre-anchor <=10 deg target is unreachable
        on that chord.  Enumeration over NON-mirrored joint assignments,
        however, finds slim near-parallel chords (both tilts < 9 deg) that
        meet the target on all four ends with every gate green (sep 16.5px).

        This pass (ref-scrubbed) runs at the anchor-snap call site right before
        the post-snap enhanced flip, ONLY for pairs the joint snap actually
        re-anchored (report["lens_pairs"]) AND whose simulated post-flip state
        still exceeds ARRIVAL_TARGET_DEG on any end.  For every ordered pair
        of distinct facing-border anchors (both boxes; anchors claimed by
        other edges excluded) it re-fits both arcs (lockstep ctrl translate +
        ARC_CTRL_SCALE_LADDER rescale, engine gates), simulates the caller's
        enhanced flip, and keeps the deterministic best assignment by
        (max arrival deviation, -separation).  The candidate is applied ONLY
        when it meets ARRIVAL_TARGET_DEG on all four ends (partial
        "improvements" that still miss the target are rejected -- a marginal
        deviation shave is not worth re-anchoring bytes; measured on
        soil-erosion: best enumeration 21.69 deg vs delivered 21.82 deg,
        correctly untouched); the caller's flip then reproduces the
        simulated final state exactly (the pass leaves the PRE-flip ladder
        geometry, the flip derives the delivered ctrl).
        Pairs whose post-flip state already meets the target are returned
        untouched -- byte-identical by construction.
        """
        SideNorm = {"t": (0.0, -1.0), "b": (0.0, 1.0),
                    "r": (1.0, 0.0), "l": (-1.0, 0.0)}

        def _four_devs(rs):
            out = []
            for i in (i1, i2):
                inf = rs[i]
                pts, ctrl = inf["points"], inf["ctrl"]
                for end, v in ((0, self.edges[i][0]), (1, self.edges[i][1])):
                    p = pts[0] if end == 0 else pts[-1]
                    n = SideNorm[self._side_of(v, p)]
                    t = ((ctrl[0] - p[0], ctrl[1] - p[1]) if end == 0
                         else (p[0] - ctrl[0], p[1] - ctrl[1]))
                    L = math.hypot(t[0], t[1])
                    if L < 1e-9:
                        return None
                    c = abs(t[0] * n[0] + t[1] * n[1]) / L
                    out.append(math.degrees(math.acos(max(0.0, min(1.0, c)))))
            return out

        for key in sorted(self.mutual):
            if (key[0], key[1]) not in lens_pairs:
                continue
            i1 = self.eidx.get((key[0], key[1]))
            i2 = self.eidx.get((key[1], key[0]))
            if i1 is None or i2 is None or i1 == i2:
                continue
            if i1 in frozen or i2 in frozen:
                continue
            r1, r2 = routes.get(i1), routes.get(i2)
            if not r1 or not r2:
                continue
            if r1.get("kind") != "arc" or r2.get("kind") != "arc":
                continue
            if r1.get("ctrl") is None or r2.get("ctrl") is None:
                continue
            if r1.get("ua_ends") or r2.get("ua_ends"):
                continue    # T1: designated ends never re-anchor
            ends = []
            for i, v in ((i1, key[0]), (i1, key[1]), (i2, key[0]), (i2, key[1])):
                e = self.edges[i]
                ends.append((i, 0 if e[0] == v else 1, v))
            end_of = {(i1, key[0]): ends[0][1], (i1, key[1]): ends[1][1],
                      (i2, key[0]): ends[2][1], (i2, key[1]): ends[3][1]}
            pidx = {(i, v): (0 if end == 0 else len(routes[i]["points"]) - 1)
                    for i, end, v in ends}
            s1 = self._side_of(key[0], routes[i1]["points"][pidx[(i1, key[0])]])
            s2 = self._side_of(key[1], routes[i1]["points"][pidx[(i1, key[1])]])
            s3 = self._side_of(key[0], routes[i2]["points"][pidx[(i2, key[0])]])
            s4 = self._side_of(key[1], routes[i2]["points"][pidx[(i2, key[1])]])
            if s1 != s3 or s2 != s4:
                continue
            # trigger: simulate the caller's post-snap enhanced flip; pairs it
            # already fixes are left untouched (zero drift)
            sim = {j: {"points": [list(p) for p in routes[j]["points"]],
                       "ctrl": (list(routes[j]["ctrl"])
                                if routes[j].get("ctrl") is not None else None),
                       "kind": routes[j].get("kind")}
                   for j in routes}
            self.mutual_arrival_flip(sim, frozen=frozen, enhanced_gates=True)
            cur_devs = _four_devs(sim)
            if cur_devs is None or max(cur_devs) <= ARRIVAL_TARGET_DEG + 1e-9:
                continue
            # facing-border anchors per box (engine order = deterministic)
            border = {}
            ok_plan = True
            for v, s in ((key[0], s1), (key[1], s2)):
                cx, cy, hw, hh = self.N[v]
                horiz = s in ("t", "b")
                bcoord = (cy + (hh - 3.0) if s == "b" else
                          cy - (hh - 3.0) if s == "t" else
                          cx + (hw - 3.0) if s == "r" else cx - (hw - 3.0))
                ancs = []
                for aid, ax, ay in self._box_anchors(v):
                    bc = ay if horiz else ax
                    if abs(bc - bcoord) <= 0.01:
                        ancs.append(aid)
                border[v] = ancs
                if len(ancs) < 2:
                    ok_plan = False
                    break
            if not ok_plan:
                continue
            # anchors claimed by OTHER edges keep their claims
            occ_local = {}
            for j in sorted(routes):
                if j in (i1, i2):
                    continue
                pj = routes[j]["points"]
                for end, v, p in ((0, self.edges[j][0], pj[0]),
                                  (1, self.edges[j][1], pj[-1])):
                    aid = self._anchor_at(v, p)
                    if aid is not None:
                        occ_local.setdefault((v, aid), set()).add((j, end))
            saved = {i: ([list(p) for p in routes[i]["points"]],
                         list(routes[i]["ctrl"])) for i in (i1, i2)}
            before_stats = {i: self._edge_stats(i, routes) for i in (i1, i2)}
            before_own = {i: self._own_press(i, routes) for i in (i1, i2)}
            before_sib = {i: self._sibling_cross(i, routes) for i in (i1, i2)}
            best = None   # ((maxdev, -sep), geo) -- geo is the PRE-flip ladder state
            for c_pair in itertools.permutations(border[key[0]], 2):
                for f_pair in itertools.permutations(border[key[1]], 2):
                    assign = [(i1, key[0], end_of[(i1, key[0])], c_pair[0]),
                              (i1, key[1], end_of[(i1, key[1])], f_pair[0]),
                              (i2, key[0], end_of[(i2, key[0])], c_pair[1]),
                              (i2, key[1], end_of[(i2, key[1])], f_pair[1])]
                    if any(occ_local.get((v, aid))
                           for _i, v, _e, aid in assign):
                        continue
                    applied = False
                    for f in ARC_CTRL_SCALE_LADDER:
                        geo = {}
                        for i in (i1, i2):
                            pts = [list(q) for q in saved[i][0]]
                            ctrl = list(saved[i][1])
                            p0, p1 = list(pts[0]), list(pts[-1])
                            for _i, v, end, aid in assign:
                                if _i != i:
                                    continue
                                cand = next(q for q in self._box_anchors(v)
                                            if q[0] == aid)
                                if end == 0:
                                    p0 = [cand[1], cand[2]]
                                else:
                                    p1 = [cand[1], cand[2]]
                            mid = [(p0[0] + p1[0]) / 2.0,
                                   (p0[1] + p1[1]) / 2.0]
                            tctrl = [ctrl[0] + (p0[0] - saved[i][0][0][0])
                                     + (p1[0] - saved[i][0][-1][0]),
                                     ctrl[1] + (p0[1] - saved[i][0][0][1])
                                     + (p1[1] - saved[i][0][-1][1])]
                            fctrl = [mid[0] + (tctrl[0] - mid[0]) * f,
                                     mid[1] + (tctrl[1] - mid[1]) * f]
                            geo[i] = ([list(q) for q in quad_points(p0, fctrl, p1)],
                                      fctrl)
                        for i in (i1, i2):
                            routes[i]["points"] = geo[i][0]
                            routes[i]["ctrl"] = geo[i][1]
                        # T12: bbox lower bound first -- the true minimum
                        # distance of the two arcs is never below the gap
                        # between their bounding boxes, so a gap >= 12px
                        # clears the threshold without the O(n*m) 4px
                        # sample sweep (sep feeds ONLY this threshold; the
                        # flipped-state sep2 below is still measured
                        # exactly).  Empty point lists keep the original
                        # None -> continue semantics.
                        _p1, _p2 = routes[i1]["points"], routes[i2]["points"]
                        if not _p1 or not _p2:
                            continue
                        if _bbox_gap_lb(_p1, _p2) < 12.0:
                            sep = min_pair_dist(
                                sample_polyline(_p1, step=4),
                                sample_polyline(_p2, step=4))
                            if sep is None or sep < 12.0:
                                continue
                        # T4: unified delivery-gate caliber (docs/routing-gates.md G-LENS-JOINT)
                        ok = True
                        for i in (i1, i2):
                            if not _gates.edge_gate_check(
                                    self, i, routes,
                                    _gates.GateBaseline(stats=dict(before_stats),
                                                        own=dict(before_own),
                                                        sib=dict(before_sib)),
                                    _gates.LENS_JOINT):
                                ok = False
                                break
                        if ok:
                            applied = True
                            break
                    if not applied:
                        continue
                    # simulate the caller's enhanced flip on the candidate
                    flip_in = {j: {"points": [list(p) for p in routes[j]["points"]],
                                   "ctrl": (list(routes[j]["ctrl"])
                                            if routes[j].get("ctrl") is not None
                                            else None),
                                   "kind": routes[j].get("kind")}
                               for j in routes}
                    self.mutual_arrival_flip(flip_in, frozen=frozen,
                                             enhanced_gates=True)
                    devs = _four_devs(flip_in)
                    sep2 = min_pair_dist(
                        sample_polyline(flip_in[i1]["points"], step=4),
                        sample_polyline(flip_in[i2]["points"], step=4))
                    for i in (i1, i2):
                        st = self._edge_stats(i, flip_in)
                        if (st[0] > before_stats[i][0]
                                or st[3] > before_stats[i][3]
                                or (st[1] is not None and
                                    st[1] < self.cl - PRESS_MARGIN - 1e-6)
                                or st[2] < ANCHOR_MIN_DEG
                                or devs is None
                                or sep2 is None or sep2 < 12.0):
                            devs = None
                            break
                    if devs is None:
                        continue
                    score = (max(devs), -(sep2 if sep2 is not None else 0.0))
                    if best is None or score < best[0]:
                        best = (score, geo)
                    # restore the ladder-state candidate for the next iteration
                    for i in (i1, i2):
                        routes[i]["points"] = geo[i][0]
                        routes[i]["ctrl"] = geo[i][1]
                # restore the delivered state between c_pair iterations
                for i in (i1, i2):
                    routes[i]["points"] = [list(q) for q in saved[i][0]]
                    routes[i]["ctrl"] = list(saved[i][1])
            for i in (i1, i2):
                routes[i]["points"] = [list(q) for q in saved[i][0]]
                routes[i]["ctrl"] = list(saved[i][1])
            if best is not None and best[0][0] <= ARRIVAL_TARGET_DEG + 1e-9:
                for i in (i1, i2):
                    routes[i]["points"] = best[1][i][0]
                    routes[i]["ctrl"] = best[1][i][1]
        return routes

    # -- closed-ring rebuild of mutual pairs on every non-lens engine (B2/B4) --
    def _arrival_dev(self, v, p, ctrl):
        """Deviation (deg) between the arrival tangent (p - ctrl) and the
        outward normal of the border the endpoint p sits on (the
        test_mutual_lens_arrow_normal caliber)."""
        cx, cy, hw, hh = self.N[v]
        on_x = abs(abs(p[0] - cx) - hw) <= abs(abs(p[1] - cy) - hh)
        if on_x:
            nx, ny = (1.0, 0.0) if p[0] > cx else (-1.0, 0.0)
        else:
            nx, ny = (0.0, 1.0) if p[1] > cy else (0.0, -1.0)
        tx, ty = p[0] - ctrl[0], p[1] - ctrl[1]
        n = math.hypot(tx, ty)
        if n < 1e-9:
            return 180.0
        c = abs(tx * nx + ty * ny) / n
        return math.degrees(math.acos(max(0.0, min(1.0, c))))

    def _pair_arrival_dev(self, i1, i2, routes):
        """Largest arrival deviation (deg) over the four ends of the two
        routes; None when a route carries no ctrl (not a Q arc)."""
        worst = 0.0
        for i in (i1, i2):
            r = routes.get(i)
            if not r or not r.get("points") or r.get("ctrl") is None:
                return None
            pts = r["points"]
            worst = max(worst, self._arrival_dev(self.edges[i][0], pts[0], r["ctrl"]),
                        self._arrival_dev(self.edges[i][1], pts[-1], r["ctrl"]))
        return worst

    def _pair_lens_state(self, i1, i2, routes):
        """Closed-lens accounting of one mutual pair on the delivered geometry.

        Returns (closed, sep, slim): closed iff both routes are Q arcs whose
        apex offset reaches LENS_BULGE_MIN of the chord on opposite sides
        (the metrics.lens_pairs_closed caliber, measured along the pair
        direction); slim iff both routes are Q arcs on opposite sides staying
        >= LENS_PAIR_MIN_SEP apart with every arrow arriving within
        ARRIVAL_TARGET_DEG of its border normal -- the arrow-normal channel's
        (mutual_arrival_flip) own closed form, left untouched by the rebuild;
        sep = routing-caliber minimum distance between the two lines (None
        on an empty route).
        """
        from .gates import arc_bulge, LENS_BULGE_MIN
        r1, r2 = routes.get(i1), routes.get(i2)
        if (not r1 or not r2 or not r1.get("points") or not r2.get("points")):
            return False, None, False
        sep = min_pair_dist(sample_polyline(r1["points"], step=4),
                            sample_polyline(r2["points"], step=4))
        closed = slim = False
        if (r1.get("kind") == "arc" and r2.get("kind") == "arc"
                and r1.get("ctrl") is not None and r2.get("ctrl") is not None):
            ra, sa = arc_bulge(r1["points"], r1["ctrl"])
            rb, sb = arc_bulge(r2["points"], r2["ctrl"], flip=True)
            if (ra is not None and rb is not None and ra > 1e-9 and rb > 1e-9
                    and sa != 0 and sa != sb and sep is not None
                    and sep >= LENS_PAIR_MIN_SEP):
                if ra >= LENS_BULGE_MIN and rb >= LENS_BULGE_MIN:
                    closed = True
                else:
                    dev = self._pair_arrival_dev(i1, i2, routes)
                    slim = dev is not None and dev <= ARRIVAL_TARGET_DEG + 1e-6
        return closed, sep, slim

    def mutual_lens_construct(self, routes, frozen=()):
        """Rebuild non-lens mutual pairs as the constructed lens-chain double arc.

        Scope: every engine but lens-construct (whose lenses are constructed
        before routing).  The ring / column / spine / bowtie engines route a
        mutual pair through the generic candidate set and the arrival flip
        then flattens the two arcs toward the border normal (measured:
        limits-to-growth R1 reads as two near-straight lines 21px apart,
        width/chord 0.10; fixes-that-fail problem<->fix bows 3.0px / -0.2px,
        lines 4.5-7.3px apart).  This pass runs LAST in the delivery chain.
        For each unfrozen pair whose delivered lines fail the closed-ring
        contract it re-derives both arcs on the facing standard anchors
        (LENS_PAIR_ANCHORS, the lenslayout.lens_arcs caliber; K = LENS_K so
        bulge/chord = LENS_K / 2 by construction).  The candidate is kept
        only when every delivery gate holds (gates.LENS_CONSTRUCT) and the
        two arcs stay >= LENS_PAIR_MIN_SEP apart; otherwise the pair is
        returned byte-for-byte.  Anchor variants are tried in order (a
        horizontal pair: corner anchors first on a long chord, golden
        first on a short one; a vertical pair: golden first, corner
        after); a variant whose anchors another edge holds, or whose
        lens fails a gate, hands over to the next.  A pair the arrow-normal channel already
        closed as a slim lens (arcs >= LENS_PAIR_MIN_SEP apart, every arrow
        within ARRIVAL_TARGET_DEG of the border normal) is reported slim
        and left untouched: a fat lens arrives 32 deg off its chord and
        cannot meet that contract.

        Returns (routes, report); report["pairs"] carries one row per mutual
        pair with the delivered status so the certificate can account honest
        non-lenses: lens (already closed) / slim (closed by the arrow-normal
        channel) / built / frozen / designated / tilt (every variant's
        chord tilt beyond lens_tilt_max_deg: the outer arc cannot meet
        ANCHOR_MIN_DEG) / claimed (every non-tilted variant's anchors are
        held by other edges) / blocked (gate-checked, per-variant reasons).
        """
        from .lenslayout import LENS_K
        tilt_max = lens_tilt_max_deg()
        report = {"pairs": [], "k": LENS_K, "tilt_max_deg": round(tilt_max, 1)}

        def _pt(v, aid):
            for a in self._box_anchors(v):
                if a[0] == aid:
                    return [a[1], a[2]]
            return None

        def _arc(p0, p1, side, c):
            # ctrl on the chord normal (not the axis side vector): on a
            # tilted chord the axis vector has an along-chord component
            # that skews the apex (measured: limits-to-growth 0.132 < 0.15);
            # the normal keeps apex/chord = LENS_K / 2 on any tilt.  c = the
            # pair's mean chord so both arcs bow by the same absolute offset
            # (mirror-symmetric lens even when the two chords differ a little).
            nx, ny = -(p1[1] - p0[1]) / c, (p1[0] - p0[0]) / c
            sv = LENS_SIDE_VEC[side]
            if nx * sv[0] + ny * sv[1] < 0:
                nx, ny = -nx, -ny
            ctrl = [(p0[0] + p1[0]) / 2.0 + nx * LENS_K * c,
                    (p0[1] + p1[1]) / 2.0 + ny * LENS_K * c]
            return {"kind": "arc", "points": quad_points(p0, ctrl, p1),
                    "ctrl": ctrl}

        for key in sorted(self.mutual):
            i1 = self.eidx.get((key[0], key[1]))
            i2 = self.eidx.get((key[1], key[0]))
            if i1 is None or i2 is None or i1 == i2:
                continue
            r1, r2 = routes.get(i1), routes.get(i2)
            if not r1 or not r2:
                continue
            row = {"pair": [key[0], key[1]]}
            report["pairs"].append(row)
            closed, sep0, slim0 = self._pair_lens_state(i1, i2, routes)
            if closed and sep0 is not None and sep0 >= LENS_PAIR_MIN_SEP:
                row["status"] = "lens"
                continue
            if slim0:
                # the arrow-normal channel already closed this pair as a
                # slim lens (arcs within ARRIVAL_TARGET_DEG of the border
                # normal): a fat lens arrives atan(2 K) = 32 deg off its
                # chord and would break that contract -- leave it.
                row.update(status="slim", closed=True, sep=round(sep0, 1),
                           arrival_dev_deg=round(self._pair_arrival_dev(i1, i2, routes), 1))
                continue
            if i1 in frozen or i2 in frozen:
                row["status"] = "frozen"
                continue
            if r1.get("ua_ends") or r2.get("ua_ends"):
                row["status"] = "designated"
                continue
            A, B = key[0], key[1]
            dx = self.N[B][0] - self.N[A][0]
            dy = self.N[B][1] - self.N[A][1]
            if abs(dx) >= abs(dy):
                d = "E" if dx >= 0 else "W"
            else:
                d = "S" if dy >= 0 else "N"
            # anchor variants in priority order; a variant whose anchors
            # another edge holds, or whose lens fails a delivery gate, hands
            # over to the next one (measured: ring edges hold the corner
            # anchors on fishing-collapse catch<->quota and the N/S golden
            # anchors on induced-demand trips<->congestion).  Horizontal
            # pairs: long chord -> corner first (flat lens), short chord ->
            # golden first unless its tips sit closer than the pair
            # separation floor (E/W golden tips are 9px apart on a 44px
            # card -> corner, a round eye with 38px tips).  Vertical pairs:
            # N/S golden anchors (21px tips) first, corner chords after.
            variants = ["golden", "corner"]
            if d in ("E", "W"):
                (ca, cb), _ = LENS_PAIR_ANCHORS["corner"][d]
                pc = _pt(A, ca), _pt(B, cb)
                corner_chord = (math.hypot(pc[1][0] - pc[0][0], pc[1][1] - pc[0][1])
                                if pc[0] is not None and pc[1] is not None else 0.0)
                (ga, gb), (gra, grb) = LENS_PAIR_ANCHORS["golden"][d]
                tg = _pt(A, ga), _pt(A, gra)
                golden_tips = (math.hypot(tg[1][0] - tg[0][0], tg[1][1] - tg[0][1])
                               if tg[0] is not None and tg[1] is not None else 0.0)
                if corner_chord >= LENS_CORNER_MIN_CHORD or golden_tips < LENS_PAIR_MIN_SEP:
                    variants = ["corner", "golden"]
            # anchors held by OTHER edges keep their claims
            held = set()
            for j in sorted(routes):
                if j in (i1, i2):
                    continue
                pj = routes[j]["points"]
                for v, p in ((self.edges[j][0], pj[0]), (self.edges[j][1], pj[-1])):
                    aid = self._anchor_at(v, p)
                    if aid is not None:
                        held.add((v, aid))
            saved = {}
            for i in (i1, i2):
                c = dict(routes[i])
                c["points"] = [list(q) for q in routes[i]["points"]]
                if routes[i].get("ctrl") is not None:
                    c["ctrl"] = list(routes[i]["ctrl"])
                saved[i] = c
            base = _gates.GateBaseline(
                stats={i: self._edge_stats(i, routes) for i in (i1, i2)},
                own={i: self._own_press(i, routes) for i in (i1, i2)},
                sib={i: self._sibling_cross(i, routes) for i in (i1, i2)})
            attempts, tilts, claimed = [], [], 0
            for variant in variants:
                (la, lb), (ra, rb) = LENS_PAIR_ANCHORS[variant][d]
                ps, pd, qs, qd = _pt(A, la), _pt(B, lb), _pt(A, ra), _pt(B, rb)
                if ps is None or pd is None or qs is None or qd is None:
                    attempts.append(variant + ":noanchor")
                    continue
                chord = math.hypot(pd[0] - ps[0], pd[1] - ps[1])
                if chord < 1e-6:
                    attempts.append(variant + ":degenerate")
                    continue
                normal = LENS_SIDE_VEC[d]
                tilt = math.degrees(math.acos(max(0.0, min(1.0, abs(
                    ((pd[0] - ps[0]) * normal[0] + (pd[1] - ps[1]) * normal[1])
                    / chord)))))
                row.setdefault("chord_tilt_deg", round(tilt, 1))
                if tilt > tilt_max + 1e-9:
                    tilts.append(round(tilt, 1))
                    attempts.append("%s:tilt:%.1f" % (variant, tilt))
                    continue
                if any((v, aid) in held for v, aid in ((A, la), (B, lb), (A, ra), (B, rb))):
                    claimed += 1
                    attempts.append(variant + ":claimed")
                    continue
                pb_, pa_ = _pt(B, rb), _pt(A, ra)
                chord2 = math.hypot(pa_[0] - pb_[0], pa_[1] - pb_[1])
                cmean = (chord + chord2) / 2.0
                routes[i1] = _arc(ps, pd, LENS_LEFT_TURN[d], cmean)
                routes[i2] = _arc(pb_, pa_, LENS_RIGHT_TURN[d], cmean)
                ok = True
                for i in (i1, i2):
                    if not _gates.edge_gate_check(self, i, routes, base,
                                                  _gates.LENS_CONSTRUCT):
                        ok = False
                        break
                sep = min_pair_dist(sample_polyline(routes[i1]["points"], step=4),
                                    sample_polyline(routes[i2]["points"], step=4))
                if sep is None or sep < LENS_PAIR_MIN_SEP:
                    ok = False
                if ok:
                    closed2, _, _ = self._pair_lens_state(i1, i2, routes)
                    tips = math.hypot(ps[0] - qs[0], ps[1] - qs[1])
                    row.update(status="built", closed=closed2, sep=round(sep, 1),
                               chord_tilt_deg=round(tilt, 1), chord=round(chord, 1),
                               anchors=[variant, [la, lb], [ra, rb]],
                               width_over_chord=round((tips + LENS_K * chord) / chord, 3))
                    break
                reasons = []
                for i in (i1, i2):
                    st = self._edge_stats(i, routes)
                    st0 = base.stats[i]
                    if st[0] > st0[0]:
                        reasons.append("press:%d" % i)
                    if st[3] > st0[3]:
                        reasons.append("cross:%d" % i)
                    if st[1] is not None and st[1] < self.cl - PRESS_MARGIN - 1e-6:
                        reasons.append("clearance:%d:%.1f" % (i, st[1]))
                    if st[2] < ANCHOR_MIN_DEG:
                        reasons.append("angle:%d:%.1f" % (i, st[2]))
                    if self._own_press(i, routes) > base.own[i]:
                        reasons.append("ownbox:%d" % i)
                    if self._sibling_cross(i, routes) > base.sib[i]:
                        reasons.append("sibling:%d" % i)
                    if not self._cert_angle_ok(i, routes):
                        reasons.append("cert_angle:%d" % i)
                if sep is None or sep < LENS_PAIR_MIN_SEP:
                    reasons.append("sep:%s" % (sep if sep is None else round(sep, 1)))
                attempts.append(variant + ":" + ",".join(reasons))
                for i in (i1, i2):
                    routes[i] = saved[i]
            else:
                # every variant refused: tilt-only -> honest tilt exemption;
                # otherwise the gate-checked reasons travel on the row
                if tilts and claimed + len(tilts) == len(attempts) and not [
                        a for a in attempts if a.split(":")[1] not in ("tilt", "claimed")]:
                    row.update(status="tilt", chord_tilt_deg=max(tilts),
                               anchors=None, reasons=attempts)
                else:
                    row.update(status="blocked", reasons=attempts)
            if row.get("status") == "built":
                continue
            if row.get("status") == "tilt":
                continue
            if row.get("status") == "blocked" and claimed == len(
                    [a for a in attempts if a.split(":")[1] != "tilt"]) and claimed > 0:
                row.update(status="claimed", reasons=attempts)
            continue
        return routes, report

    # -- ref-scrubbed: default endpoint snapping to the 16 standard anchors --
    ANCHOR_SNAP_TOL = 0.51    # px: an endpoint within this of an anchor IS on that anchor (delivery rounds to 0.1px)

    def _box_anchors(self, v):
        """The 16 standard anchors of node v's box (anchors.py caliber; cached per layout)."""
        cache = getattr(self, "_anchor_cache", None)
        if cache is None:
            cache = self._anchor_cache = {}
        if v not in cache:
            cx, cy, hw, hh = self.N[v]
            cache[v] = _std_anchors(cx, cy, hw, hh)
        return cache[v]

    def _anchor_at(self, v, p):
        """Anchor id if endpoint p already sits on one of v's 16 standard anchors, else None.

            Deterministic tie-break: none needed -- the anchors are mutually
            far apart (>= ~18px), far beyond ANCHOR_SNAP_TOL.
        """
        for aid, ax, ay in self._box_anchors(v):
            if abs(ax - p[0]) <= self.ANCHOR_SNAP_TOL and \
                    abs(ay - p[1]) <= self.ANCHOR_SNAP_TOL:
                return aid
        return None

    def _own_press(self, i, routes):
        """Body-intrusion count of edge i against its OWN boxes (0 = clean).

            Comparative gate basis for anchor_snap: (a) several delivered
            vg/detour routes legitimately hug their own box border, so the
            ABSOLUTE own-box gate of _own_box_ok can never pass for them --
            the anchor move is accepted only when it does not ADD own-box
            intrusion vs the delivered state; (b) samples within 6px of an
            endpoint are excluded -- the attachment zone always grazes the
            inflated border by construction (the anchor sits ON the border,
            inset 3px), what the gate must catch is the arc/polyline BODY
            stabbing into the box, not the attachment stub.
        """
        pts = routes[i]["points"]
        a, b = self.edges[i]
        p0, p1 = pts[0], pts[-1]
        samples = [s for s in sample_polyline(pts)[1:-1]
                   if math.hypot(s[0] - p0[0], s[1] - p0[1]) > 6.0 and
                   math.hypot(s[0] - p1[0], s[1] - p1[1]) > 6.0]
        n = 0
        # WS5 press-only bbox skip (exact): if the samples' bbox is farther
        # than ROUND_GUARD from the inflated box, no sample can press it.
        if samples:
            bxl = min(s[0] for s in samples)
            bxh = max(s[0] for s in samples)
            byl = min(s[1] for s in samples)
            byh = max(s[1] for s in samples)
        else:
            bxl = bxh = byl = byh = 0.0
        for v in (a, b):
            cx, cy, hw, hh = self.N[v]
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
                continue          # press impossible (bbox lower bound)
            for (px, py) in samples:
                if dist_point_rect(px, py, cx, cy, hw + PRESS_MARGIN,
                                   hh + PRESS_MARGIN) <= ROUND_GUARD:
                    n += 1
                    break
        return n

    def _cert_angle_ok(self, i, routes):
        """Anchor smoothness re-checked in the CERTIFICATE's border-side
        classification caliber (metrics._anchor_tangent_angle).

            At CORNER anchors the two accountings can classify the border side
            differently (metrics: the smaller |Δ| wins; router _anchor_angle:
            its own rule) -- measured on population-logistic population->births
            nw: router 50.2 deg vs certificate 0.0 deg.  A snap candidate is
            feasible only when BOTH accountings pass (the delivered gate is
            the certificate's).
        """
        pts = routes[i]["points"]
        for v, idx, nidx in ((self.edges[i][0], 0, 1),
                             (self.edges[i][1], len(pts) - 1, len(pts) - 2)):
            cx, cy, hw, hh = self.N[v]
            a0 = pts[idx]
            on_x = abs(abs(a0[0] - cx) - hw) <= abs(abs(a0[1] - cy) - hh)
            tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
            dx, dy = pts[nidx][0] - a0[0], pts[nidx][1] - a0[1]
            n = math.hypot(dx, dy)
            if n < 1e-9:
                return False
            c = abs(dx * tx + dy * ty) / n
            ang = math.degrees(math.acos(max(0.0, min(1.0, c))))
            if ang < ANCHOR_MIN_DEG:
                return False
        return True

    def _sibling_cross(self, i, routes):
        """Mid-air intersection count between edge i and edges SHARING an
        endpoint with it (fan pairs).

            Router._edge_stats exempts shared-endpoint pairs (graph-theory
            caliber), which misses fan lines visibly crossing mid-air under
            the same box (ref-scrubbed blind spot) -- the certificate's
            visual_crossings_zero gate counts them (metrics accounting:
            strict seg_cross over the dense points, endpoint touch exempt).
            The snap gate uses the same accounting so a candidate that folds
            a fan into an X is rejected.
        """
        a, b = self.edges[i]
        pts = routes[i]["points"]
        s1 = list(zip(pts[:-1], pts[1:]))
        n = 0
        for j, o in routes.items():
            if j == i:
                continue
            ea, eb = self.edges[j]
            if not ({a, b} & {ea, eb}):
                continue
            opts = o["points"]
            s2 = list(zip(opts[:-1], opts[1:]))
            hit = False
            for q1 in s1:
                for q2 in s2:
                    if seg_cross(q1[0], q1[1], q2[0], q2[1]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                n += 1
        return n

    LENS_OFFSET_PAIRS = "golden-first"   # ref-scrubbed: golden mirror pair before corner pair

    def _lens_pair_joint_snap(self, routes, occ, report):
        """Mutual-pair lens arcs: JOINT symmetric anchoring (ref-scrubbed).

            Per-endpoint nearest-first snapping breaks the lens geometry: the
            two arcs' attachments on a shared box stop being mirrored, the
            chord tilts and the arrows twist (classic-cld crowding<->fundamental
            measured: arrival 11.8 deg > target 10, separation 10.5 < 12).
            This pre-pass assigns BOTH arcs of a mutual arc pair to the SAME
            mirrored anchor-offset pair per box (golden mirror pair first,
            corner mirror pair as fallback), preserving the lens symmetry and
            keeping the chord tilt small.  Deterministic: fixed pair ladder,
            fixed sign assignment (arc with the lower current offset takes the
            lower anchor).  Gates match the delivery accounting on BOTH arcs
            (press / crossings / clearance at CI accounting / departure angles
            in both calibers / mutual separation >= 12px lens floor / own-box
            body intrusion / fan-sibling mid-air crossings).
        """
        for key in sorted(self.mutual):
            i1 = self.eidx.get((key[0], key[1]))
            i2 = self.eidx.get((key[1], key[0]))
            if i1 is None or i2 is None or i1 == i2:
                continue
            if i1 not in routes or i2 not in routes:
                continue
            r1, r2 = routes[i1], routes[i2]
            if r1.get("kind") != "arc" or r2.get("kind") != "arc":
                continue
            if r1.get("ctrl") is None or r2.get("ctrl") is None:
                continue
            if r1.get("ua_ends") or r2.get("ua_ends"):
                continue    # T1: a user-designated end keeps its anchor --
                            # the joint mirror re-anchoring would drift it
            # ends: (edge_idx, end_idx, box) for each arc on each box
            ends = []
            for i, v in ((i1, key[0]), (i1, key[1]), (i2, key[0]), (i2, key[1])):
                e = self.edges[i]
                ends.append((i, 0 if e[0] == v else 1, v))
            pidx = {}   # (edge_idx, box) -> point index (0 or len-1; arcs are dense)
            for i, end, v in ends:
                pidx[(i, v)] = 0 if end == 0 else len(routes[i]["points"]) - 1
            # both arcs must attach on the SAME border side per box (facing
            # borders; otherwise the lens pre-pass does not apply)
            s1 = self._side_of(ends[0][2], routes[i1]["points"][pidx[(i1, key[0])]])
            s2 = self._side_of(ends[1][2], routes[i1]["points"][pidx[(i1, key[1])]])
            s3 = self._side_of(ends[2][2], routes[i2]["points"][pidx[(i2, key[0])]])
            s4 = self._side_of(ends[3][2], routes[i2]["points"][pidx[(i2, key[1])]])
            _dbg(lambda: f"  [lensdbg] {key} s={s1}/{s2} vs {s3}/{s4} "
                         f"N0={self.N.get(key[0])} N1={self.N.get(key[1])} "
                         f"e{self.edges[i1]} e{self.edges[i2]} "
                         f"p1={routes[i1]['points'][pidx[(i1, key[0])]]} "
                         f"p3={routes[i2]['points'][pidx[(i2, key[0])]]}")
            if s1 != s3 or s2 != s4:
                continue
            sep_ok_floor = 12.0
            before_sep = min_pair_dist(
                sample_polyline(r1["points"], step=4),
                sample_polyline(r2["points"], step=4))
            if before_sep is None:
                continue
            sep_ok_floor = max(sep_ok_floor, before_sep - 0.05)
            # local occupancy: OTHER edges' endpoints already exactly on an
            # anchor keep their claim (the pair's own 4 ends are excluded --
            # they are what this pass re-assigns)
            occ_local = {}
            for j in sorted(routes):
                if j in (i1, i2):
                    continue
                pj = routes[j]["points"]
                for end, v, p in ((0, self.edges[j][0], pj[0]),
                                  (1, self.edges[j][1], pj[-1])):
                    aid = self._anchor_at(v, p)
                    if aid is not None:
                        occ_local.setdefault((v, aid), set()).add((j, end))
            saved = {i: ([list(p) for p in routes[i]["points"]],
                         list(routes[i]["ctrl"]))
                     for i in (i1, i2)}
            before_stats = {i: self._edge_stats(i, routes) for i in (i1, i2)}
            before_own = {i: self._own_press(i, routes) for i in (i1, i2)}
            before_sib = {i: self._sibling_cross(i, routes) for i in (i1, i2)}
            # mirrored offset pairs per box: golden pair first, corner pair last
            box_pairs = {}
            ok_plan = True
            for v, s in ((key[0], s1), (key[1], s2)):
                cx, cy, hw, hh = self.N[v]
                ancs = self._box_anchors(v)
                horiz = s in ("t", "b")
                # border coordinate of the chosen side (anchors of OTHER sides
                # share the tangential axis -- filter by the border coordinate)
                bcoord = (cy + (hh - 3.0) if s == "b" else
                          cy - (hh - 3.0) if s == "t" else
                          cx + (hw - 3.0) if s == "r" else
                          cx - (hw - 3.0))
                low = high = None
                lows, highs = [], []
                for aid, ax, ay in ancs:
                    bc = ay if horiz else ax   # t/b borders share y; r/l share x
                    if abs(bc - bcoord) > 0.01:
                        continue      # anchor on a different border side
                    off = (ax - cx) if horiz else (ay - cy)
                    if abs(off) < 1e-6:
                        continue      # midpoint: cannot host two arcs
                    (lows if off < 0 else highs).append((abs(off), aid))
                # golden mirror pair first: smallest |tangential offset|
                # (deterministic tie -> ANCHOR_IDS order); corners only remain
                # when no golden pair exists on this border
                if lows and highs:
                    low = min(lows)[1]
                    high = min(highs)[1]
                if low is None or high is None:
                    ok_plan = False
                    break
                box_pairs[v] = (low, high)
            if not ok_plan:
                _dbg(lambda: f"  [lensdbg] {key} ok_plan=False")
                continue
            # which arc is "low" per current offsets on box key[0]
            cx0, cy0, hw0, hh0 = self.N[key[0]]
            horiz0 = s1 in ("t", "b")
            p_a = routes[i1]["points"][pidx[(i1, key[0])]]
            p_b = routes[i2]["points"][pidx[(i2, key[0])]]
            off_a = (p_a[0] - cx0) if horiz0 else (p_a[1] - cy0)
            off_b = (p_b[0] - cx0) if horiz0 else (p_b[1] - cy0)
            arc_low, arc_high = ((i1, i2) if off_a <= off_b else (i2, i1))
            end_of = {(i1, key[0]): ends[0][1], (i1, key[1]): ends[1][1],
                      (i2, key[0]): ends[2][1], (i2, key[1]): ends[3][1]}
            golden = True
            while True:
                lo1, hi1 = box_pairs[key[0]] if golden else \
                    self._corner_pair(key[0], s1)
                lo2, hi2 = box_pairs[key[1]] if golden else \
                    self._corner_pair(key[1], s2)
                if lo1 is None or lo2 is None:
                    break
                assign = [(arc_low, key[0], end_of[(arc_low, key[0])], lo1),
                          (arc_low, key[1], end_of[(arc_low, key[1])], lo2),
                          (arc_high, key[0], end_of[(arc_high, key[0])], hi1),
                          (arc_high, key[1], end_of[(arc_high, key[1])], hi2)]
                # occupancy: mirrored pair must be free for this pair
                if any(occ_local.get((v, aid)) for _i, v, _e, aid in assign):
                    if golden:
                        golden = False
                        continue
                    break
                # apply: endpoint + ctrl lockstep per arc, then a ctrl-rescale
                # ladder around the new chord midpoint (same caliber as the
                # per-endpoint snap): the lockstep-translated arc body may dip
                # into its own box (own-press gate) -- the ladder re-fits the
                # bulge until the gates pass (the post-snap arrival flip then
                # restores the arrow-normal caliber).
                ladder = []
                for f in ARC_CTRL_SCALE_LADDER:
                    geo = {}
                    for i in (i1, i2):
                        pts = [list(q) for q in saved[i][0]]
                        ctrl = list(saved[i][1])
                        p0, p1 = list(pts[0]), list(pts[-1])
                        for _i, v, end, aid in assign:
                            if _i != i:
                                continue
                            idx = 0 if end == 0 else len(pts) - 1
                            cand = next(q for q in self._box_anchors(v)
                                        if q[0] == aid)
                            if end == 0:
                                p0 = [cand[1], cand[2]]
                            else:
                                p1 = [cand[1], cand[2]]
                        mid = [(p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0]
                        # translated ctrl = original ctrl + endpoint deltas
                        tctrl = [ctrl[0] + (p0[0] - saved[i][0][0][0])
                                 + (p1[0] - saved[i][0][-1][0]),
                                 ctrl[1] + (p0[1] - saved[i][0][0][1])
                                 + (p1[1] - saved[i][0][-1][1])]
                        fctrl = [mid[0] + (tctrl[0] - mid[0]) * f,
                                 mid[1] + (tctrl[1] - mid[1]) * f]
                        geo[i] = ([list(q) for q in quad_points(p0, fctrl, p1)],
                                  fctrl)
                    ladder.append(geo)
                ok = False
                seen = []
                for geo in ladder:
                    for i in (i1, i2):
                        routes[i]["points"] = geo[i][0]
                        routes[i]["ctrl"] = geo[i][1]
                    sep = min_pair_dist(
                        sample_polyline(routes[i1]["points"], step=4),
                        sample_polyline(routes[i2]["points"], step=4))
                    if sep is None or sep < sep_ok_floor:
                        continue
                    # T4: unified delivery-gate caliber (docs/routing-gates.md G-LENS-PAIR)
                    ok = True
                    for i in (i1, i2):
                        if not _gates.edge_gate_check(
                                self, i, routes,
                                _gates.GateBaseline(stats=dict(before_stats),
                                                    own=dict(before_own),
                                                    sib=dict(before_sib)),
                                _gates.LENS_PAIR):
                            if os.environ.get("STDRAW_SNAP_DEBUG"):
                                st = self._edge_stats(i, routes)
                                seen.append(
                                    f"e{i}:own{self._own_press(i, routes)}"
                                    f"/sib{self._sibling_cross(i, routes)}"
                                    f"/cert{self._cert_angle_ok(i, routes)}"
                                    f"/clr{None if st[1] is None else round(st[1],1)}"
                                    f"/ang{round(st[2],1)}")
                            ok = False
                            break
                    if ok:
                        break
                _dbg(lambda: f"  [lensdbg] {key} golden={golden} ok={ok} sep={sep} "
                             f"floor={sep_ok_floor:.2f} "
                             f"own1={self._own_press(i1, routes)}<={before_own[i1]} "
                             f"own2={self._own_press(i2, routes)}<={before_own[i2]} "
                             f"sib1={self._sibling_cross(i1, routes)}<={before_sib[i1]} "
                             f"sib2={self._sibling_cross(i2, routes)}<={before_sib[i2]} "
                             f"cert1={self._cert_angle_ok(i1, routes)} "
                             f"cert2={self._cert_angle_ok(i2, routes)} "
                             f"assign={assign} rejects={seen}")
                if ok:
                    for _i, v, end, aid in assign:
                        occ.setdefault((v, aid), set()).add(
                            (_i, 0 if end_of[(_i, v)] == 0 else 1))
                    report["moved"] += 4
                    report.setdefault("lens_pairs", []).append(
                        (key[0], key[1]))
                    _dbg(lambda: f"  [lensdbg] {key} APPLIED golden={golden} "
                                 f"assign={assign}")
                    break
                for i in (i1, i2):
                    routes[i]["points"] = [list(q) for q in saved[i][0]]
                    routes[i]["ctrl"] = list(saved[i][1])
                if golden:
                    golden = False    # next: corner mirror pair
                    continue
                break

    def _off_of(self, v, horiz, ancs, aid):
        cx, cy, hw, hh = self.N[v]
        for a, ax, ay in ancs:
            if a == aid:
                return (ax - cx) if horiz else (ay - cy)
        return 0.0

    def _corner_pair(self, v, s):
        """Low/high corner anchor ids on border side s of box v (or (None, None))."""
        cx, cy, hw, hh = self.N[v]
        horiz = s in ("t", "b")
        ancs = self._box_anchors(v)
        low = high = None
        best_lo = best_hi = None
        for aid, ax, ay in ancs:
            off = (ax - cx) if horiz else (ay - cy)
            is_corner = abs(abs(off) - ((hw if horiz else hh) - 3.0)) < 1e-6
            if not is_corner:
                continue
            if off < 0:
                low = aid
            else:
                high = aid
        return low, high

    def anchor_snap(self, routes, max_sweeps=4):
        """Delivery-layer endpoint snapping to the 16 standard per-box anchor set (card ref-scrubbed).

        jacky 2026-11-09: the 16 standard connection points (ref-scrubbed) must
        be the DEFAULT attachment caliber of every rendered edge endpoint --
        not only the interactive layer.  Algorithm path (joint selection, not
        blind post-hoc snapping):

          1. Occupancy: every endpoint already exactly on an anchor claims it
             (per (node, anchor) occupancy -- two endpoints never share one
             anchor point, so no V co-points can be created by this pass).
          2. Sweep loop (deterministic edge order, fixed candidate ladder):
             each off-anchor endpoint evaluates the 16 anchors NEAREST FIRST
             (tie-break = fixed ANCHOR_IDS order).  A candidate is applied
             only if the full delivery hard-gate set holds against the
             CURRENT routes (press no-worse / no new crossing vs any other
             edge / clearance >= CLEARANCE / departure angle >= ANCHOR_MIN_DEG
             / mutual separation >= 4px / own-box interior clean).  Arcs
             translate their ctrl in lockstep with the endpoint displacement
             and re-discretize the Bezier (same caliber as midband_reanchor
             tier 1).  Every applied move updates the shared geometry, so a
             later neighbour's gates see the already-snapped state -- the
             assignment is sequential-joint, crossings cannot be introduced
             by a move the mover's own gate did not count.
          3. Sweeps repeat (max max_sweeps) until no endpoint changes: an
             endpoint that failed against a neighbour's pre-snap geometry may
             become feasible after that neighbour settles.

        Endpoints for which no anchor passes the gates stay untouched and
        are reported in the returned report (honest degradation; the
        certificate's anchors_standard gate counts them).  Waypoint-kind
        edges are exempt from both: their endpoints already sit on the
        16-anchor set by construction (layout_auto override caliber) and
        are not counted as failures.  Deterministic:
        fixed order + fixed ladder, no RNG.
        """
        occ = {}
        report = {"anchored": 0, "moved": 0, "failures": []}
        if self.dense:
            report["dense_anchored"] = 0
        # ref-scrubbed: the mutual-lens joint pass runs FIRST -- the generic
        # per-endpoint pass would grab the nearest anchors for the lens ends
        # independently and break the mirror symmetry.  Its occupancy only
        # counts OTHER edges' endpoints that already sit exactly on an anchor
        # (the rest of the graph is re-anchored afterwards, occupancy claims
        # from the joint pass are honoured in the main registration below).
        self._lens_pair_joint_snap(routes, occ, report)
        for i in sorted(routes):
            a, b = self.edges[i]
            pts = routes[i]["points"]
            for end, v, p in ((0, a, pts[0]), (1, b, pts[-1])):
                aid = self._anchor_at(v, p)
                if aid is not None:
                    occ.setdefault((v, aid), set()).add((i, end))
                    report["anchored"] += 1
                elif self._dense_on_grid(v, p):
                    # dense: hub endpoints on the slot grid are anchored
                    # by the dense caliber (16-set OR grid); registered
                    # occupied so nothing else claims the same slot.
                    slot = round(((p[1] - self.N[v][1])
                                  if abs(abs(p[0] - self.N[v][0])
                                         - self.N[v][2]) <= abs(abs(p[1] - self.N[v][1])
                                                                - self.N[v][3])
                                  else (p[0] - self.N[v][0])) / DENSE_GRID_STEP)
                    occ.setdefault((v, ("dgrid", slot)), set()).add((i, end))
                    report["dense_anchored"] += 1
        for _sweep in range(max_sweeps):
            changed = False
            for i in sorted(routes):
                a, b = self.edges[i]
                if routes[i].get("kind") == "waypoints":
                    # User-anchored waypoint edges are FROZEN here (same
                    # exemption as tier 2 below): their delivered endpoints
                    # already sit ON the 16-anchor set by construction
                    # (layout_auto waypoints override caliber: endpoint =
                    # standard anchor nearest to the border point aimed at
                    # the first/last waypoint), so there is nothing left for
                    # the snap to move.  They are also NOT reported as snap
                    # failures: a delivered anchored endpoint is the honest
                    # state, not a snap defect.
                    continue
                _ua = routes[i].get("ua_ends") or {}
                for end, v in ((0, a), (1, b)):
                    if _ua.get(end):
                        # T1: user-designated standard anchor (manual-layout
                        # edges[].anchors) -- never re-anchored, never counted
                        # as a snap failure (per-end exemption, same family
                        # as the waypoint-kind freeze above).
                        continue
                    idx = 0 if end == 0 else len(routes[i]["points"]) - 1
                    p = routes[i]["points"][idx]
                    if self._anchor_at(v, p) is not None:
                        continue
                    if self._dense_on_grid(v, p):
                        # dense: hub endpoint already on the slot grid —
                        # anchored under the dense caliber; re-snapping
                        # to the 16-set would destroy the controlled
                        # sharing placement (fan grid slots).
                        continue
                    before_pts = [list(q) for q in routes[i]["points"]]
                    before_ctrl = (list(routes[i]["ctrl"])
                                   if routes[i].get("ctrl") is not None else None)
                    before_vg = ([list(q) for q in routes[i]["vg_corners"]],
                                 [dict(f) for f in routes[i]["vg_fillets"]]) \
                        if routes[i].get("kind") == "vg" else None
                    before = self._edge_stats(i, routes)
                    own_before = self._own_press(i, routes)
                    sib_before = self._sibling_cross(i, routes)
                    before_coi = self._coincide_max_span(i, routes)
                    applied = False
                    cands = sorted(self._box_anchors(v),
                                   key=lambda q: (math.hypot(q[1] - p[0],
                                                             q[2] - p[1]), q[0]))
                    for aid, ax, ay in cands:
                        if occ.get((v, aid)):
                            continue  # occupied by another edge endpoint
                        dxa, dya = ax - before_pts[idx][0], ay - before_pts[idx][1]
                        geo_cands = []   # [(dense_points, ctrl_or_None), ...]
                        if before_ctrl is not None:
                            # arc: endpoint to the anchor; ctrl first translates
                            # in lockstep with the endpoint displacements (this
                            # end + the possibly-already-snapped other end),
                            # then a ladder rescales the ctrl offset around the
                            # new chord midpoint so the departure angle
                            # (>= ANCHOR_MIN_DEG) can be met on long-tangent
                            # detour arcs; Bezier re-discretized per tier
                            oidx = len(before_pts) - 1 - idx
                            dox = routes[i]["points"][oidx][0] - before_pts[oidx][0]
                            doy = routes[i]["points"][oidx][1] - before_pts[oidx][1]
                            cs = [before_ctrl[0] + dxa + dox,
                                  before_ctrl[1] + dya + doy]
                            if idx == 0:
                                p0, p1 = [ax, ay], list(routes[i]["points"][-1])
                            else:
                                p0, p1 = list(routes[i]["points"][0]), [ax, ay]
                            mid = [(p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0]
                            for f in ARC_CTRL_SCALE_LADDER:
                                ctrl = [mid[0] + (cs[0] - mid[0]) * f,
                                        mid[1] + (cs[1] - mid[1]) * f]
                                geo_cands.append(([list(q) for q in
                                                   quad_points(p0, ctrl, p1)],
                                                  ctrl))
                        else:
                            new_pts = [list(q) for q in before_pts]
                            if routes[i].get("kind") == "vg":
                                # vg: move the endpoint corner AND translate the
                                # adjacent interior corner by the same delta (the
                                # first stub segment stays collinear, departure
                                # direction preserved), then RE-DERIVE every
                                # fillet from the new corners -- rigidly shifting
                                # a fillet keeps it tangent to the shifted
                                # segment but breaks tangency against the
                                # unshifted continuation (random-n10-i05 G1 7.2
                                # deg measured); smooth_corners is deterministic,
                                # unmoved corners reproduce their original fillet
                                corners = [list(q) for q in routes[i]["vg_corners"]]
                                # NOTE: idx indexes the DENSE points; corners is
                                # the raw corner list (dense >= corners when
                                # fillets re-sample arcs) -> corner index from
                                # the END side, not from idx
                                cidx = 0 if idx == 0 else len(corners) - 1
                                jj1 = 1 if cidx == 0 else len(corners) - 2
                                corners[cidx] = [ax, ay]
                                if len(corners) > 2:
                                    corners[jj1] = [corners[jj1][0] + dxa,
                                                    corners[jj1][1] + dya]
                                rects_vg = [n for vv, n in self.N.items()
                                            if vv not in (a, b)]
                                fillets, _cp = _vis.smooth_corners(
                                    corners, rects_vg, self.cl + VG_PAD)
                                new_pts = [[px, py] for px, py in
                                           _vis.dense_geometry(corners, fillets)]
                                routes[i]["vg_corners"] = corners
                                routes[i]["vg_fillets"] = fillets
                            elif routes[i].get("kind") in ("poly", "wrap") \
                                    and len(new_pts) > 2:
                                # poly/wrap: translate the adjacent via by the
                                # same delta (departure direction preserved; the
                                # gates recheck the shifted run)
                                j1 = 1 if idx == 0 else len(new_pts) - 2
                                new_pts[j1] = [new_pts[j1][0] + dxa,
                                               new_pts[j1][1] + dya]
                                new_pts[idx] = [ax, ay]
                            else:
                                new_pts[idx] = [ax, ay]
                            geo_cands.append((new_pts, None))
                        for new_pts, new_ctrl in geo_cands:
                            routes[i]["points"] = new_pts
                            if new_ctrl is not None:
                                routes[i]["ctrl"] = new_ctrl
                            after = self._edge_stats(i, routes)
                            # T4: unified delivery-gate caliber (docs/routing-gates.md G-SNAP)
                            ok = _gates.edge_gate_check(
                                self, i, routes,
                                _gates.GateBaseline(stats={i: before},
                                                    own={i: own_before},
                                                    sib={i: sib_before},
                                                    coi={i: before_coi}),
                                _gates.SNAP, stats=after)
                            def _snap_gate_msg():
                                _c = dict(p=after[0] <= before[0],
                                          x=after[3] <= before[3],
                                          cl=(after[1] is None or after[1] >= self.cl - PRESS_MARGIN - 1e-6),
                                          an=after[2] >= ANCHOR_MIN_DEG,
                                          ms=(after[4] is None or after[4] >= 4.0),
                                          ow=self._own_press(i, routes) <= own_before,
                                          sb=self._sibling_cross(i, routes) <= sib_before,
                                          ct=self._cert_angle_ok(i, routes))
                                return (f"  [snapdbg] {a}->{b} end={end} "
                                        f"anchor={aid} press {after[0]}<={before[0]} "
                                        f"clr {after[1]} ang {after[2]:.1f} "
                                        f"cross {after[3]}<={before[3]} "
                                        f"msep {after[4]} own {self._own_press(i, routes)}"
                                        f"<={own_before} sib {self._sibling_cross(i, routes)}"
                                        f"<={sib_before} occ {bool(occ.get((v, aid)))} "
                                        f"cert {self._cert_angle_ok(i, routes)} "
                                        f"comp {_c} "
                                        f"-> {'OK' if ok else 'REJECT'}")
                            _dbg(_snap_gate_msg)
                            if ok:
                                occ.setdefault((v, aid), set()).add((i, end))
                                report["moved"] += 1
                                changed = True
                                applied = True
                                break
                            routes[i]["points"] = before_pts
                            if before_ctrl is not None:
                                routes[i]["ctrl"] = list(before_ctrl)
                            if before_vg is not None:
                                routes[i]["vg_corners"] = [list(q) for q in before_vg[0]]
                                routes[i]["vg_fillets"] = [dict(f) for f in before_vg[1]]
                        if applied:
                            break
                    if not applied:
                        # ref-scrubbed tier 2: full-detour joint re-route from a
                        # standard-anchor pair (see _snap_joint_detour) --
                        # tier 1 moves only the endpoint + adjacent via, which
                        # on dense detour polylines presses the line back into
                        # its own box or across a sibling (random-n10-i05
                        # N03->N08 end a measured: own 1>0 on every near
                        # anchor, cascading into visual_crossings x4 /
                        # lines_no_coincidence on the delivered graph).
                        if self.dense and (a == self.dense_hub
                                           or b == self.dense_hub):
                            # dense form guard (dense card, operator
                            # form-correctness gate): the tier-2 joint
                            # detour replaces the straight spoke with a vg
                            # polyline whose hub-side departure crosses the
                            # sibling spokes (measured fan-d17: two vg
                            # spokes, visual_crossings 0->2) — the hub
                            # edge keeps its straight route instead and
                            # the unsnapped end is reported honestly.
                            report["failures"].append(
                                {"edge": f"{a}->{b}",
                                 "end": "a" if end == 0 else "b"})
                            continue
                        applied = self._snap_joint_detour(
                            routes, occ, report, i, end)
                        if applied:
                            changed = True
                    if not applied:
                        report["failures"].append(
                            {"edge": f"{a}->{b}", "end": "a" if end == 0 else "b"})
            if not changed:
                break
        self._snap_retry_conflicts(routes, occ, report)
        report["failures"] = sorted({(f["edge"], f["end"])
                                     for f in report["failures"]})
        report["failures"] = [{"edge": e, "end": n} for e, n in report["failures"]]
        return report

    def _coi_geom(self, i, pts):
        """Cached coincidence geometry of route i: sampled points / segs /
        seg grid / sampled bbox, keyed by the exact point-list contents.

            anchor_snap re-evaluates the same geometries many times
            (before_coi once per endpoint per sweep + after_coi per candidate
            gate, each against EVERY other edge) -- without the cache every
            call re-sampled all ~30 dense routes of an n20 graph (measured:
            the dominant share of the 126s->956s n20 wall-clock regression).
            Content-keyed, so any route mutation naturally misses; bounded
            clear keeps memory flat.  Pure acceleration: values are the same
            sample_polyline products the exact path computed.
        """
        cache = getattr(self, "_coi_geom_cache", None)
        if cache is None:
            cache = self._coi_geom_cache = {}
        key = (i, tuple(map(tuple, pts)))
        ent = cache.get(key)
        if ent is None:
            s = sample_polyline(pts)
            segs = list(zip(s[:-1], s[1:]))
            ent = (s, segs, build_seg_grid(segs),
                   (min(p[0] for p in s), min(p[1] for p in s)),
                   (max(p[0] for p in s), max(p[1] for p in s)))
            if len(cache) >= 2048:
                cache.clear()
            cache[key] = ent
        return ent

    def _coincide_max_span(self, i, routes):
        """Max adherence span (px) between edge i and any other edge.

            Same source as the certificate's line_line_coincident accounting
            (_pair_coincide_span), bbox-prefiltered for the per-candidate
            cost of the anchor_snap gates (ref-scrubbed coincidence gate).
            Sampled geometry and the seg grid come from the content-keyed
            _coi_geom cache and the pair span runs over the 3x3 grid
            neighborhood -- an exact-equivalence speedup (bit-identical
            spans, differential-tested against span_one_way_segs), same
            caliber as the WS5 routing bbox pruning.
        """
        sa, segs_a, grid_a, il, ih = self._coi_geom(i, routes[i]["points"])
        best = 0.0
        for j, o in routes.items():
            if j == i:
                continue
            sb, segs_b, grid_b, jl, jh = self._coi_geom(j, o["points"])
            if (il[0] - jh[0] > COINCIDE_THR or jl[0] - ih[0] > COINCIDE_THR or
                    il[1] - jh[1] > COINCIDE_THR or jl[1] - ih[1] > COINCIDE_THR):
                continue
            s = max(span_one_way_segs_grid(sa, segs_b, grid_b),
                    span_one_way_segs_grid(sb, segs_a, grid_a))
            if s > best:
                best = s
        return best

    def _coincide_no_worse(self, i, routes, before_coi):
        """Coincidence gate for anchor_snap candidates (ref-scrubbed).

            A candidate may never CREATE a visual-coincidence pair: when the
            edge's current max adherence span is within the hard threshold,
            the candidate must stay within it; when the edge is already in
            violation, the candidate must not worsen it (monotone repair).
            Zero-drift-safe for the classic domain: there the baseline has no
            violation, and a snap candidate that would create one would have
            shipped a lines_no_coincidence violation -- which the 21-graph
            sweep proves never happened.
        """
        after_coi = self._coincide_max_span(i, routes)
        if before_coi <= COINCIDE_SPAN + 1e-9:
            return after_coi <= COINCIDE_SPAN + 1e-9
        return after_coi <= before_coi + 1e-9

    def _snap_joint_detour(self, routes, occ, report, i, end):
        """ref-scrubbed tier 2: full-detour re-route anchored on the 16-anchor set.

            Tier 1 (the sweeps) moves only the endpoint + its adjacent via,
            preserving the delivered departure corridor.  On dense graphs the
            detour corridor itself is the problem: every near anchor then
            presses the shifted stub back into the own box (own-press gate)
            or across a sibling lane, and the endpoint stays off-anchor --
            the off-anchor long run is exactly what cascades into visual
            crossings and coincident spans downstream.  This tier re-plans
            the WHOLE edge as a visibility-graph route from a standard-anchor
            PAIR (near box x far box, both nearest-first ladders, both
            inflation tiers cl+VG_PAD / +PAIR_VG_OFF for lane separation),
            so both endpoints land ON the standard anchor set by
            construction.  Mutual pairs are excluded (their dedicated joint
            lens snap keeps the mirror symmetry).  Acceptance = the same
            full hard-gate set as the sweeps (press / clearance / anchor
            angles both accountings / mutual separation / own-box
            comparative / sibling fan crossings / coincidence no-worse) +
            membership of both endpoints.  Deterministic: fixed ladder
            order, no RNG.

            Returns True and mutates routes/occ/report on success; restores
            the delivered route byte-for-byte on failure.
        """
        if routes[i].get("ua_ends"):
            return False   # T1: the whole-edge replan would displace the
                           # user-designated end(s) -- exempt like waypoints
        a, b = self.edges[i]
        if (min(a, b), max(a, b)) in self.mutual:
            return False
        if routes[i].get("kind") == "waypoints":
            return False    # user-anchored waypoint edges keep their polyline
        v = self.edges[i][end]
        w = self.edges[i][1 - end]
        idx = 0 if end == 0 else len(routes[i]["points"]) - 1
        p = routes[i]["points"][idx]
        q = routes[i]["points"][-1 - idx]
        before = self._edge_stats(i, routes)
        own_before = self._own_press(i, routes)
        sib_before = self._sibling_cross(i, routes)
        before_coi = self._coincide_max_span(i, routes)
        rects = [n for vv, n in self.N.items() if vv not in (a, b)]
        near = sorted(self._box_anchors(v),
                      key=lambda q2: (math.hypot(q2[1] - p[0], q2[2] - p[1]),
                                      q2[0]))
        far = sorted(self._box_anchors(w),
                     key=lambda q2: (math.hypot(q2[1] - q[0], q2[2] - q[1]),
                                     q2[0]))
        if not rects:
            return False
        infls = (self.cl + VG_PAD, self.cl + VG_PAD + PAIR_VG_OFF)
        # Endpoint ORDER follows the EDGE direction: points[0] belongs to a,
        # points[-1] to b (check.py gate 4 measures the departure at pts[0]
        # against box a -- a reversed route ships both ends "off-border";
        # measured on random-n10-i00 N03->N08).  The repaired end keeps its
        # nearest-first ladder; the opposite end iterates its own ladder.
        if end == 0:
            ladders = ((near, far), (a, b))
        else:
            ladders = ((far, near), (a, b))
        (lad_a, lad_b) = ladders[0]
        for aid_a, ax, ay in lad_a:
            if occ.get((ladders[1][0], aid_a)):
                continue
            for aid_b, bx, by in lad_b:
                if occ.get((ladders[1][1], aid_b)):
                    continue
                for c in infls:
                    # plan_route memo keyed by the full argument tuple
                    # (obstacle set is fixed per (a,b) pair + graph): the same
                    # anchor pair / inflation recurs across fixpoint sweeps
                    # for endpoints whose neighbourhood has not settled, and
                    # each miss costs a visibility-graph Dijkstra.  Pure
                    # acceleration -- plan_route is deterministic, identical
                    # arguments yield identical routes; fillets are copied on
                    # retrieval so cached entries are never shared mutably.
                    ck = (a, b, ax, ay, bx, by, c)
                    pcache = getattr(self, "_snap_plan_cache", None)
                    if pcache is None:
                        pcache = self._snap_plan_cache = {}
                    if ck in pcache:
                        route = pcache[ck]
                    else:
                        route = _vis.plan_route([ax, ay], [bx, by], rects, c)
                        if len(pcache) >= 8192:
                            pcache.clear()
                        pcache[ck] = route
                    if not route:
                        continue
                    pts_n = [list(pp) for pp in route["dense"]]
                    if self._anchor_at(a, pts_n[0]) is None or \
                            self._anchor_at(b, pts_n[-1]) is None:
                        continue
                    old = dict(routes[i])
                    routes[i] = {"kind": "vg", "points": pts_n,
                                 "press": 0, "min_clear": None, "cross": 0,
                                 "cross_edges": 0, "ang_a": 0.0, "ang_b": 0.0,
                                 "vg_corners": [list(pp) for pp in
                                                route["corner_pts"]],
                                 "vg_fillets": [dict(f) for f in
                                                route["fillets"]],
                                 # provenance for the loop-direction arc
                                 # record: this line was re-planned here
                                 "joint_detour": True}
                    after = self._edge_stats(i, routes)
                    # T4: unified delivery-gate caliber (docs/routing-gates.md G-SNAP)
                    ok = _gates.edge_gate_check(
                        self, i, routes,
                        _gates.GateBaseline(stats={i: before},
                                            own={i: own_before},
                                            sib={i: sib_before},
                                            coi={i: before_coi}),
                        _gates.SNAP, stats=after)
                    _dbg(lambda: f"  [snapdbg] JOINT {a}->{b} end={end} "
                                 f"anchors={aid_a}/{aid_b} infl={c:.1f} "
                                 f"press {after[0]}<={before[0]} "
                                 f"clr {after[1]} ang {after[2]:.1f} "
                                 f"cross {after[3]}<={before[3]} "
                                 f"own {self._own_press(i, routes)}"
                                 f"<={own_before} sib {self._sibling_cross(i, routes)}"
                                 f"<={sib_before} "
                                 f"-> {'OK' if ok else 'REJECT'}")
                    if ok:
                        occ.setdefault((ladders[1][0], aid_a), set()).add(
                            (i, 0 if end == 0 else 1))
                        occ.setdefault((ladders[1][1], aid_b), set()).add(
                            (i, 1 if end == 0 else 0))
                        report["moved"] += 1
                        return True
                    routes[i] = old
        return False

    def _snap_retry_conflicts(self, routes, occ, report):
        """Post-sweep repair: for an endpoint that failed all 16 anchors
        because earlier-snapped sibling edges occupy/blocked its feasible
        anchors (wide-comb hub fans measured: hoya->stx end b), let the
        CONFLICTING sibling give way to its next-nearest feasible anchor and
        retry the failed endpoint.  Deterministic: failures in sorted order;
        for each, blocker siblings in sorted order x blocker alternative
        anchors nearest-first x the failed endpoint's full nearest-first
        ladder; committed only when BOTH endpoints pass the full delivery
        hard-gate set (same accounting as the sweeps).  One bounded round.
        """
        for fail in list(report["failures"]):
            target = None
            for i in sorted(routes):
                a, b = self.edges[i]
                if f"{a}->{b}" == fail["edge"]:
                    target = (i, 0 if fail["end"] == "a" else 1)
                    break
            if target is None:
                continue
            i, end = target
            v = self.edges[i][end]
            idx = 0 if end == 0 else len(routes[i]["points"]) - 1
            p = routes[i]["points"][idx]
            if self._anchor_at(v, p) is not None:
                continue    # a later sweep already resolved it
            before_pts = [list(q) for q in routes[i]["points"]]
            before_ctrl = (list(routes[i]["ctrl"])
                           if routes[i].get("ctrl") is not None else None)
            before_vg = ([list(q) for q in routes[i]["vg_corners"]],
                         [dict(f) for f in routes[i]["vg_fillets"]]) \
                if routes[i].get("kind") == "vg" else None
            before = self._edge_stats(i, routes)
            own_before = self._own_press(i, routes)
            sib_before = self._sibling_cross(i, routes)
            done = False
            for j in sorted(routes):
                if j == i or done:
                    continue
                # T2 note: waypoint-kind endpoints MAY give way here -- the
                # plan-A position is the nearest FEASIBLE member of the
                # 16-anchor set, and the give-way ladder (nearest-first over
                # the same 16-set) preserves that membership while resolving
                # anchor conflicts with the failed endpoint (uncontested
                # drags deliver the literal nearest anchor, identical to the
                # JS preview).
                ja, jb = self.edges[j]
                if v not in (ja, jb):
                    continue
                jend = 0 if ja == v else 1
                if (routes[j].get("ua_ends") or {}).get(jend):
                    continue    # T1: the blocker's designated end cannot give way
                jidx = 0 if jend == 0 else len(routes[j]["points"]) - 1
                jp = routes[j]["points"][jidx]
                jaid = self._anchor_at(v, jp)
                if jaid is None:
                    continue    # j's end on this box is not the blocker
                jsaved_pts = [list(q) for q in routes[j]["points"]]
                jsaved_ctrl = (list(routes[j]["ctrl"])
                               if routes[j].get("ctrl") is not None else None)
                jbefore = self._edge_stats(j, routes)
                jown_before = self._own_press(j, routes)
                jsib_before = self._sibling_cross(j, routes)
                jocc_key = (v, jaid)
                claimants = occ.get(jocc_key, set())
                occ.pop(jocc_key, None)     # release j's claim for the retry
                cands_i = sorted(self._box_anchors(v),
                                 key=lambda q: (math.hypot(q[1] - p[0],
                                                           q[2] - p[1]), q[0]))
                for aid, ax, ay in cands_i:
                    if occ.get((v, aid)):
                        continue
                    # -- the blocker gives way FIRST: its next-nearest
                    #    feasible alternative on this box (gate-checked); if
                    #    no alternative passes, this anchor stays unavailable
                    jp0 = routes[j]["points"][jidx]
                    jbefore_pts = [list(q) for q in routes[j]["points"]]
                    jbefore_ctrl = jsaved_ctrl
                    jbefore_vg = ([list(q) for q in routes[j]["vg_corners"]],
                                  [dict(f) for f in routes[j]["vg_fillets"]]) \
                        if routes[j].get("kind") == "vg" else None
                    jbs = self._edge_stats(j, routes)
                    jownb = self._own_press(j, routes)
                    jsibb = self._sibling_cross(j, routes)
                    jalt = None
                    jcands = sorted(
                        (q for q in self._box_anchors(v) if q[0] != aid),
                        key=lambda q: (math.hypot(q[1] - jp0[0],
                                                  q[2] - jp0[1]), q[0]))
                    for jaid2, jax, jay in jcands:
                        if occ.get((v, jaid2)) or (v, jaid2) == jocc_key:
                            continue
                        jidx2 = 0 if jend == 0 else len(routes[j]["points"]) - 1
                        jdxa = jax - jbefore_pts[jidx2][0]
                        jdya = jay - jbefore_pts[jidx2][1]
                        jnp = [list(q) for q in jbefore_pts]
                        if routes[j].get("kind") in ("poly", "wrap") \
                                and len(jnp) > 2:
                            jj1 = 1 if jidx2 == 0 else len(jnp) - 2
                            jnp[jj1] = [jnp[jj1][0] + jdxa, jnp[jj1][1] + jdya]
                        jnp[jidx2] = [jax, jay]
                        routes[j]["points"] = jnp
                        # T4: unified delivery-gate caliber (docs/routing-gates.md G-SNAP-RETRY)
                        ok_j = _gates.edge_gate_check(
                            self, j, routes,
                            _gates.GateBaseline(stats={j: jbs},
                                                own={j: jownb},
                                                sib={j: jsibb}),
                            _gates.SNAP_RETRY)
                        if ok_j:
                            jalt = (jaid2, [list(q) for q in jnp])
                            break
                        routes[j]["points"] = jbefore_pts
                        if jbefore_ctrl is not None:
                            routes[j]["ctrl"] = list(jbefore_ctrl)
                        if jbefore_vg is not None:
                            routes[j]["vg_corners"] = [list(q) for q in jbefore_vg[0]]
                            routes[j]["vg_fillets"] = [dict(f) for f in jbefore_vg[1]]
                    if jalt is None:
                        continue
                    # -- retry the failed endpoint at aid --
                    dxa, dya = ax - before_pts[idx][0], ay - before_pts[idx][1]
                    geo_cands = []
                    if before_ctrl is not None:
                        oidx = len(before_pts) - 1 - idx
                        dox = routes[i]["points"][oidx][0] - before_pts[oidx][0]
                        doy = routes[i]["points"][oidx][1] - before_pts[oidx][1]
                        cs = [before_ctrl[0] + dxa + dox,
                              before_ctrl[1] + dya + doy]
                        if idx == 0:
                            q0, q1 = [ax, ay], list(routes[i]["points"][-1])
                        else:
                            q0, q1 = list(routes[i]["points"][0]), [ax, ay]
                        mid = [(q0[0] + q1[0]) / 2.0, (q0[1] + q1[1]) / 2.0]
                        for f in ARC_CTRL_SCALE_LADDER:
                            ctrl = [mid[0] + (cs[0] - mid[0]) * f,
                                    mid[1] + (cs[1] - mid[1]) * f]
                            geo_cands.append(([list(q) for q in
                                               quad_points(q0, ctrl, q1)],
                                              ctrl))
                    else:
                        np_ = [list(q) for q in before_pts]
                        if routes[i].get("kind") == "vg":
                            corners = [list(q) for q in routes[i]["vg_corners"]]
                            # idx indexes DENSE points; corners is the raw
                            # corner list -> corner index from the END side
                            cidx = 0 if idx == 0 else len(corners) - 1
                            jj1 = 1 if cidx == 0 else len(corners) - 2
                            corners[cidx] = [ax, ay]
                            if len(corners) > 2:
                                corners[jj1] = [corners[jj1][0] + dxa,
                                                corners[jj1][1] + dya]
                            # re-derive fillets from the new corners (rigid
                            # fillet shift breaks G1 vs the unshifted
                            # continuation -- same caliber as the sweeps)
                            rects_vg = [n for vv, n in self.N.items()
                                        if vv not in self.edges[i]]
                            fillets, _cp = _vis.smooth_corners(
                                corners, rects_vg, self.cl + VG_PAD)
                            np_ = [[px, py] for px, py in
                                   _vis.dense_geometry(corners, fillets)]
                            routes[i]["vg_corners"] = corners
                            routes[i]["vg_fillets"] = fillets
                        elif routes[i].get("kind") in ("poly", "wrap") \
                                and len(np_) > 2:
                            jj1 = 1 if idx == 0 else len(np_) - 2
                            np_[jj1] = [np_[jj1][0] + dxa, np_[jj1][1] + dya]
                            np_[idx] = [ax, ay]
                        else:
                            np_[idx] = [ax, ay]
                        geo_cands.append((np_, None))
                    applied_i = False
                    for new_pts, new_ctrl in geo_cands:
                        routes[i]["points"] = new_pts
                        if new_ctrl is not None:
                            routes[i]["ctrl"] = new_ctrl
                        # T4: unified delivery-gate caliber (docs/routing-gates.md G-SNAP-RETRY)
                        ok_i = _gates.edge_gate_check(
                            self, i, routes,
                            _gates.GateBaseline(stats={i: before},
                                                own={i: own_before},
                                                sib={i: sib_before}),
                            _gates.SNAP_RETRY)
                        if ok_i:
                            applied_i = True
                            break
                    if applied_i:
                        jaid2, jpts_new = jalt
                        occ.setdefault((v, jaid2), set()).add((j, jend))
                        occ.setdefault((v, aid), set()).add((i, end))
                        report["moved"] += 2
                        _dbg(lambda: f"  [snapdbg] retry {fail['edge']}:{fail['end']} "
                                     f"-> {aid}; blocker {self.edges[j]} gave way "
                                     f"{jaid}->{jaid2}")
                        done = True
                        break
                    # rollback both (i tried every anchor against this jalt)
                    routes[i]["points"] = before_pts
                    if before_ctrl is not None:
                        routes[i]["ctrl"] = list(before_ctrl)
                    if before_vg is not None:
                        routes[i]["vg_corners"] = [list(q) for q in before_vg[0]]
                        routes[i]["vg_fillets"] = [dict(f) for f in before_vg[1]]
                    routes[j]["points"] = jbefore_pts
                    if jbefore_ctrl is not None:
                        routes[j]["ctrl"] = list(jbefore_ctrl)
                    if jbefore_vg is not None:
                        routes[j]["vg_corners"] = [list(q) for q in jbefore_vg[0]]
                        routes[j]["vg_fillets"] = [dict(f) for f in jbefore_vg[1]]
                if done:
                    report["failures"] = [
                        f for f in report["failures"] if f != fail]

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
                    # P1 T12 exact branch-and-bound: every non-negative
                    # score term (press / crossings / clearance / pair
                    # separation / anchor angle) is dropped and only the
                    # three exactly-known terms (line-kind preference, rule
                    # penalty, 0.01 x polyline length) form a LOWER bound
                    # on the candidate's score.  A candidate whose bound
                    # already cannot beat the incumbent (strict-improvement
                    # selection, EPS-caliber) is skipped without evaluating
                    # -- the winner is the first candidate attaining the
                    # minimum, and a skipped candidate can never attain a
                    # score below the incumbent at its own evaluation time,
                    # so the delivered choice is bitwise unchanged (the
                    # 1e-6 absolute margin absorbs the association-order
                    # rounding of the bound).  Measured on the 4-node
                    # limits-to-growth figure: the mutual-pair wrap /
                    # polyline channels (fixed +200 / +40 type cost) are
                    # pruned as soon as one clean line/arc exists.
                    if best is not None:
                        lb = self._cand_lb(cand, a, b)
                        if lb >= best[0] - EPS + 1e-6:
                            continue
                    sc, info = self._evaluate(cand, a, b, routed_segs, sib,
                                              honest=self.presets is not None)
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
