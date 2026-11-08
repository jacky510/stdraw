# -*- coding: utf-8 -*-
"""Standard per-box anchor set (card ref-scrubbed): 16 discrete connection
points per box for the interactive layer (hover display / endpoint snapping /
explicit edge-to-anchor assignment).

Caliber (jacky 2026-11-08 verbal spec, 16-point symmetric formulation):

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
