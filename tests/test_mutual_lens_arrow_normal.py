# -*- coding: utf-8 -*-
"""ref-scrubbed: mutual-pair lens arrows must not be twisted.

Background: the classic-cld crowding<->fundamental mutual pair regressed
when fan_spread (ref-scrubbed mid-band scaling) slid the pair's arc ANCHORS
onto the uniform fan slots (519.3 -> 508.0) while the arc body kept the
shape it was built for. The delivered lens therefore arrived 19-30 deg off
the border normal and the pair's two lines converged from 12.0px to 7.3px
("mutual_pair_min_sep").

Two engine channels are guarded here:
  1. fan_spread must NOT slot-slide arc-kind routes (their anchors are
     occupied positions instead) -- sliding an arc anchor without
     re-deriving the curve is what twisted the arrows;
  2. the mutual-lens arrow-normal channel must land both arrows within
     ARRIVAL_TARGET_DEG of the border normal, keep the pair's separation,
     and keep the lens mirror-symmetric.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw.routing import (ARRIVAL_TARGET_DEG, MIN_FROZEN_ANCHOR_SEP,
                            Router, min_pair_dist, sample_polyline)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")

PAIR = ("crowding", "fundamental")
SEP_FLOOR = 12.0            # pre-regression level (d4c1901^ measured 12.0)


def _border_normal(node_box, pt):
    """Outward normal of the border the anchor sits on."""
    cx, cy, hw, hh = node_box
    on_x = abs(abs(pt[0] - cx) - hw) <= abs(abs(pt[1] - cy) - hh)
    if on_x:
        return (1.0, 0.0) if pt[0] > cx else (-1.0, 0.0)
    return (0.0, 1.0) if pt[1] > cy else (0.0, -1.0)


class TestMutualLensArrowNormal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(EXAMPLE, encoding="utf-8") as f:
            dsl = f.read()
        cls.lay = layout(parse(dsl))
        cls.edges = cls.lay["edges"]
        cls.by_pair = {(e["a"], e["b"]): e for e in cls.edges}
        cls.nodes = cls.lay["nodes"]
        n = cls.nodes["crowding"]
        cls.crowding_box = (n["x"], n["y"], n["w"] / 2.0, n["h"] / 2.0) \
            if "h" in n else (n["x"], n["y"], n["w"] / 2.0, 22.0)

    def _route(self, pair):
        return self.by_pair[pair]["route"]

    def _arrival_dev(self, pair):
        """Deviation (deg) between the arrow tangent and the border normal."""
        r = self._route(pair)
        pts, ctrl = r["points"], r["ctrl"]
        node = self.nodes[pair[1]]
        box = (node["x"], node["y"], node["w"] / 2.0, node["h"] / 2.0) \
            if "h" in node else (node["x"], node["y"], node["w"] / 2.0, 22.0)
        end = pts[-1]
        nx, ny = _border_normal(box, end)
        tx, ty = end[0] - ctrl[0], end[1] - ctrl[1]
        n = math.hypot(tx, ty)
        self.assertGreater(n, 1e-9, f"{pair}: degenerate arrival tangent")
        c = abs(tx * nx + ty * ny) / n
        return math.degrees(math.acos(max(0.0, min(1.0, c))))

    def test_pair_separation_restored(self):
        r1 = self._route(PAIR)
        r2 = self._route((PAIR[1], PAIR[0]))
        sep = min_pair_dist(sample_polyline(r1["points"], step=2),
                            sample_polyline(r2["points"], step=2))
        self.assertGreaterEqual(
            sep, SEP_FLOOR,
            f"mutual pair separation {sep:.2f}px < {SEP_FLOOR}px "
            "(regression to the ref-scrubbed fan-slide defect)")

    # ref-scrubbed joint re-assignment: the 16-anchor quantization on the
    # MIRRORED golden pair forces one chord tilt to 13.8 deg (24px box-center
    # offset +- the 5.9px mirror offset over a 122px chord) and the ctrl-only
    # flip bottoms out at 14.4 deg delivered.  The joint pass
    # (Router.lens_joint_reassign) re-enumerates NON-mirrored anchor
    # assignments jointly for both arcs: the delivered assignment
    # (crowding s-g2 -> fundamental n for arc 1, fundamental n-g1 -> crowding
    # s-g1 for arc 2) gives chord tilts 6.27 / 8.44 deg and arrival devs
    # 2.8 / 0.9 deg with separation 16.5px -- the pre-anchor <=10 deg target
    # is RESTORED (this assertion pins it again; the 15 deg anchor-caliber
    # ceiling of ref-scrubbed is retired).
    ANCHOR_CALIBER_ARRIVAL_FLOOR = 0.0

    def test_arrow_arrival_within_target(self):
        target = max(ARRIVAL_TARGET_DEG, self.ANCHOR_CALIBER_ARRIVAL_FLOOR)
        for pair in (PAIR, (PAIR[1], PAIR[0])):
            dev = self._arrival_dev(pair)
            self.assertLessEqual(
                dev, target + 1e-6,
                f"{pair}: arrow arrives {dev:.2f}deg off the border normal "
                f"(anchor-caliber target <= {target}deg; pre-anchor target "
                f"was {ARRIVAL_TARGET_DEG}deg)")

    def test_lens_mirror_symmetric(self):
        # The two arcs must be mirror images: same anchor offset on the
        # crowding border, same outward bulge magnitude, opposite side.
        r1 = self._route(PAIR)
        r2 = self._route((PAIR[1], PAIR[0]))
        a1 = r1["points"][0]
        a2 = r2["points"][-1]
        self.assertAlmostEqual(a1[1], a2[1], places=6,
                               msg="the two lens anchors sit on different "
                                   "borders -> not a lens")
        b1 = r1["points"][-1]
        b2 = r2["points"][0]
        self.assertAlmostEqual(b1[1], b2[1], places=6,
                               msg="the two lens anchors sit on different "
                                   "borders -> not a lens")
        # outward bulges must be opposite in sign and equal in magnitude
        def bulge(route):
            pts, ctrl = route["points"], route["ctrl"]
            mid = ((pts[0][0] + pts[-1][0]) / 2.0,
                   (pts[0][1] + pts[-1][1]) / 2.0)
            dx, dy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
            L = math.hypot(dx, dy)
            px, py = -dy / L, dx / L
            return (ctrl[0] - mid[0]) * px + (ctrl[1] - mid[1]) * py
        b_1, b_2 = bulge(r1), bulge(r2)
        self.assertGreater(b_1 * b_2, 0,
                           "the two lens arcs bow to the same side "
                           "(not a symmetric lens)")
        self.assertAlmostEqual(abs(b_1), abs(b_2), delta=0.5,
                               msg=f"lens bulges differ: {b_1:.2f} vs {b_2:.2f}")

    def test_fan_spread_does_not_slide_arc_anchors(self):
        # Direct unit guard on the root cause, built from the REAL
        # classic-cld crowding-bottom fan (pre-fan_spread anchors + the
        # delivered ctrls + the real box geometry): fan_spread must leave
        # arc-kind routes' anchors untouched (their anchors occupy the slot
        # instead) and keep the straight-line fan slots clear of them.
        # On the pre-fix engine this scenario slides the lens anchors
        # (519.3 -> 508.0) -- the regression this card fixes.
        nodes = {0: (516.0, 232.0, 48.0, 22.0),      # crowding
                 1: (540.0, 392.0, 73.0, 22.0),      # fundamental
                 2: (384.0, 392.0, 48.0, 22.0),      # rate
                 3: (672.0, 312.0, 80.0, 22.0)}      # sideeffect
        edges = [(0, 1), (1, 0), (0, 2), (3, 0)]
        router = Router(nodes, edges, 16.0, 56)
        routes = {
            0: {"kind": "arc",
                "points": [[519.3, 254.0], [519.9, 260.2], [520.7, 267.0],
                           [521.6, 274.4], [522.5, 289.1], [530.0, 330.0],
                           [536.7, 370.0]],
                "ctrl": [522.5, 289.1]},
            1: {"kind": "arc",
                "points": [[548.7, 370.0], [545.0, 330.0], [541.0, 290.0],
                           [536.0, 262.0], [531.3, 254.0]],
                "ctrl": [545.5, 334.9]},
            2: {"kind": "line",
                "points": [[497.8, 254.0], [430.0, 320.0], [384.0, 392.0]]},
            3: {"kind": "line",
                "points": [[540.0, 254.0], [600.0, 290.0], [672.0, 312.0]]},
        }
        before = {i: [list(p) for p in routes[i]["points"]] for i in routes}
        out = router.fan_spread(routes, frozen=())
        for i in (0, 1):
            self.assertEqual(out[i]["points"][0], before[i][0],
                             f"fan_spread slid an arc anchor (edge {i}; arc "
                             "bodies are shaped for their anchors)")
            self.assertEqual(out[i]["points"][-1], before[i][-1],
                             f"fan_spread slid an arc anchor (edge {i}; arc "
                             "bodies are shaped for their anchors)")
        # the straight lines' fan slots must keep clear of the arc anchors
        arc_pts = [before[0][0], before[1][-1]]
        for i in (2, 3):
            anchor = out[i]["points"][0]
            d = min(math.hypot(anchor[0] - p[0], anchor[1] - p[1])
                    for p in arc_pts)
            self.assertGreaterEqual(d, MIN_FROZEN_ANCHOR_SEP,
                                    f"fan slot {i} landed on an arc anchor "
                                    f"(distance {d:.2f}px)")


if __name__ == "__main__":
    unittest.main()
