# -*- coding: utf-8 -*-
"""Standard per-box anchor set (card ref-scrubbed): 16 discrete connection
points per box for the interactive layer (hover display / endpoint snapping /
explicit edge-to-anchor assignment).

Caliber (owner verbal spec, 16-point symmetric formulation; docs/adr/ADR-0001):

  4 edge midpoints + 4 corner points + 2 golden-section points per edge
  (fractions 0.382 / 0.618) = 16 points.

Inset: corner points and golden points are NOT placed on the geometric
corner tips / raw border — all 16 points live on the border rectangle
inset by ``ANCHOR_INSET`` px on every side.  The 3px inset reuses the
existing border-inner-offset caliber of the fan-slot clamp
(``routing.fan_spread`` clamps slots inside the border at +/- (half - 3)),
so the anchor set never touches the rounded frame corner (render rx=7)
or the exact geometric tip.

Coordinate convention: box center (cx, cy) + half extents (hw, hh).
Edge order and golden-point direction are fixed and deterministic
(clockwise, g1 = 0.382 from the edge's first endpoint in clockwise
direction, g2 = 0.618):

    top (n):  left  -> right      right (e): top -> bottom
    bottom (s): right -> left     left (w): bottom -> top

This module is a pure function library — nothing in the static layout /
routing pipeline imports it (the auto-routing anchor planning keeps its
own caliber unchanged; the 21-input sweep stays byte-identical).  The
interactive JS layer mirrors the same formulas on live node geometry
(``_interactive_js.stdAnchors``); ``tests/test_standard_anchors.py``
pins the Python side and the probe cross-checks JS vs Python equality.
"""
import math
import re

ANCHOR_INSET = 3.0          # px, same -3 inner offset as the fan-slot clamp
GOLDEN_FRACS = (0.382, 0.618)

# Fixed deterministic order (probe hooks and export rely on the indices):
# 0..3 edge midpoints, 4..7 corners, 8..15 golden points.
ANCHOR_IDS = ("n", "e", "s", "w",
              "ne", "se", "sw", "nw",
              "n-g1", "n-g2", "e-g1", "e-g2",
              "s-g1", "s-g2", "w-g1", "w-g2")


def _r6(v):
    """Round to 1e-6 to keep JSON / probe comparisons stable."""
    return round(v + 0.0, 6)


def rounded_tip(p_prev, p_last, cx, cy, hw, hh, radius):
    """Arrow tip on the rounded card outline for a route ending at ``p_last``.

    Anchors sit on the border rectangle; with a rounded frame (render
    ``card_radius``) the four corner anchors hang outside the visible
    outline by the corner sagitta (measured on the golden set: 16 of 48
    arrowheads floated 1.1-1.9px off the frame).  A tip inside the straight
    part of a side is returned unchanged; a tip in a corner zone (within
    ``radius`` of both adjoining sides) is moved onto the corner arc along
    the last-segment ray (the arrowhead keeps its heading), falling back to
    the radial direction from the corner centre when the ray misses the
    arc.  Pure geometry: the route points / anchors are not touched, so
    the certificate caliber (which reads them) is unchanged.
    """
    x, y = p_last
    if radius <= 0 or hw <= radius or hh <= radius:
        return (x, y)
    if abs(x - cx) <= hw - radius or abs(y - cy) <= hh - radius:
        return (x, y)
    ccx = cx + (hw - radius) * (1.0 if x >= cx else -1.0)
    ccy = cy + (hh - radius) * (1.0 if y >= cy else -1.0)
    ux, uy = x - p_prev[0], y - p_prev[1]
    n = math.hypot(ux, uy)
    if n > 1e-9:
        ux, uy = ux / n, uy / n
        fx, fy = x - ccx, y - ccy
        b = fx * ux + fy * uy
        disc = b * b - (fx * fx + fy * fy - radius * radius)
        if disc >= 0:
            s = math.sqrt(disc)
            for t in (-b - s, -b + s):
                if t >= -1e-9:
                    t = max(t, 0.0)
                    return (x + t * ux, y + t * uy)
    d = math.hypot(x - ccx, y - ccy)
    if d < 1e-9:
        return (x, y)
    return (ccx + (x - ccx) * radius / d, ccy + (y - ccy) * radius / d)


def standard_anchors(cx, cy, hw, hh, inset=ANCHOR_INSET):
    """The 16 standard anchor points of one box.

    Returns a list of ``[id, x, y]`` in the fixed ANCHOR_IDS order.
    All points sit on the rectangle inset by ``inset`` px (half extents
    ``hw - inset`` / ``hh - inset``); with the default inset the
    midpoints are 3px inside the true border midpoint and the corners
    sit on the inset rectangle's corner (never the geometric tip).
    """
    if hw <= inset or hh <= inset:
        raise ValueError("box half extents must exceed the anchor inset")
    a = hw - inset
    b = hh - inset
    g1, g2 = GOLDEN_FRACS
    out = [
        ["n", cx, cy - b],
        ["e", cx + a, cy],
        ["s", cx, cy + b],
        ["w", cx - a, cy],
        ["ne", cx + a, cy - b],
        ["se", cx + a, cy + b],
        ["sw", cx - a, cy + b],
        ["nw", cx - a, cy - b],
        # top edge, left -> right
        ["n-g1", cx - a + 2 * a * g1, cy - b],
        ["n-g2", cx - a + 2 * a * g2, cy - b],
        # right edge, top -> bottom
        ["e-g1", cx + a, cy - b + 2 * b * g1],
        ["e-g2", cx + a, cy - b + 2 * b * g2],
        # bottom edge, right -> left
        ["s-g1", cx + a - 2 * a * g1, cy + b],
        ["s-g2", cx + a - 2 * a * g2, cy + b],
        # left edge, bottom -> top
        ["w-g1", cx - a, cy + b - 2 * b * g1],
        ["w-g2", cx - a, cy + b - 2 * b * g2],
    ]
    return [[p[0], _r6(p[1]), _r6(p[2])] for p in out]


def nearest_anchor(cx, cy, hw, hh, px, py, inset=ANCHOR_INSET):
    """Nearest standard anchor of one box to an arbitrary point.

    Returns ``[id, x, y]``.  Deterministic tie-break: lower ANCHOR_IDS
    index wins (fixed order = fixed winner).
    """
    pts = standard_anchors(cx, cy, hw, hh, inset)
    best = None
    for p in pts:
        d = math.hypot(p[1] - px, p[2] - py)
        if best is None or d < best[0] - 1e-9:
            best = (d, p)
    return list(best[1])


# ── Multi-slot side vocabulary (owner approval 2026-11-26; docs/adr/ADR-0018;
#    grounded in the
#    stdraw20 manual-calibration lessons §4: the manual vocabulary is
#    multi-slot -- s-g1 / s-g2 / ... -- and a single side may carry many
#    lines, so the fixed 16-point set cannot express it) ──────────────────
#
# Each side carries a numbered slot ladder ``g1..g7`` at fixed, context-free
# fractions measured clockwise from the side's first endpoint (same clockwise
# convention as ``standard_anchors`` above):
#
#   g1 = 0.382, g2 = 0.618   the legacy golden pair -- byte-stable with the
#                            16-point set (GOLDEN_FRACS)
#   g3 = 0.500               midway between the golden pair
#   g4 = 0.250, g5 = 0.750   outer pair
#   g6 = 0.125, g7 = 0.875   near-corner pair
#
# "Adaptive k" (slot count follows the number of lines attached to that
# side) decides how many slots are USED, never where they sit: the
# id -> coordinate mapping is independent of k, so ids stay unambiguous
# across DSL, exports, replays and engines.  The legacy 16-point set is a
# subset of this vocabulary (its ids resolve to identical coordinates).
SLOT_FRACS = ((1, GOLDEN_FRACS[0]), (2, GOLDEN_FRACS[1]),
              (3, 0.5), (4, 0.25), (5, 0.75), (6, 0.125), (7, 0.875))
MAX_SLOTS = 7

ANCHOR_ID_RE = re.compile(
    r"^(?:[nsew]|[nsew]-g[1-7]|ne|se|sw|nw)$")


def is_anchor_id(aid):
    """True when ``aid`` is a vocabulary id: a side midpoint (n/e/s/w),
    a corner (ne/se/sw/nw), or a numbered side slot (``<side>-g<j>``,
    j = 1..MAX_SLOTS).  Includes the legacy 16-point set."""
    return isinstance(aid, str) and bool(ANCHOR_ID_RE.match(aid))


def anchor_point(cx, cy, hw, hh, aid, inset=ANCHOR_INSET):
    """Resolve one vocabulary id to its (x, y) on the box border rectangle
    (inset by ``inset``; same rectangle as ``standard_anchors``).

    Legacy ids resolve to exactly the ``standard_anchors`` coordinates;
    slot ids g3..g7 extend the same clockwise fraction formulas.  Returns
    ``None`` for an unknown id.
    """
    if hw <= inset or hh <= inset:
        raise ValueError("box half extents must exceed the anchor inset")
    a = hw - inset
    b = hh - inset
    m = ANCHOR_ID_RE.match(aid) if isinstance(aid, str) else None
    if not m:
        return None
    aid = m.group(0)
    if aid in ("ne", "se", "sw", "nw"):
        sx = 1.0 if "e" in aid else -1.0
        sy = 1.0 if "s" in aid else -1.0
        return (_r6(cx + sx * a), _r6(cy + sy * b))
    side, frac = aid, None
    if "-g" in aid:
        side, j = aid.split("-g")
        frac = dict(SLOT_FRACS).get(int(j))
        if frac is None:
            return None
    elif aid in ("n", "e", "s", "w"):
        frac = 0.5
    else:
        return None
    if side == "n":
        return (_r6(cx - a + 2 * a * frac), _r6(cy - b))
    if side == "e":
        return (_r6(cx + a), _r6(cy - b + 2 * b * frac))
    if side == "s":
        return (_r6(cx + a - 2 * a * frac), _r6(cy + b))
    if side == "w":
        return (_r6(cx - a), _r6(cy + b - 2 * b * frac))
    return None
