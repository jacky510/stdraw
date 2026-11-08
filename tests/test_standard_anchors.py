# -*- coding: utf-8 -*-
"""Standard per-box anchor set unit tests (card ref-scrubbed).

Pins the Python caliber in stdraw/anchors.py: 16 points = 4 edge midpoints
+ 4 corner points + 8 golden-section points (0.382/0.618), all on the
border rectangle inset by 3px (the routing fan-slot -3 inner-offset
caliber). The interactive JS layer mirrors the same formulas; the live
JS-vs-Python equality is asserted by tests/probe_interactive.py.
"""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.anchors import (ANCHOR_IDS, ANCHOR_INSET, GOLDEN_FRACS,
                            nearest_anchor, standard_anchors)


class TestStandardAnchors(unittest.TestCase):
    def setUp(self):
        # asymmetric box so left/right / top/bottom cannot mask each other
        self.cx, self.cy, self.hw, self.hh = 200.0, 150.0, 90.0, 30.0
        self.pts = standard_anchors(self.cx, self.cy, self.hw, self.hh)
        self.by_id = {p[0]: (p[1], p[2]) for p in self.pts}

    def test_sixteen_points_fixed_order(self):
        self.assertEqual(len(self.pts), 16)
        self.assertEqual([p[0] for p in self.pts], list(ANCHOR_IDS))

    def test_inset_rectangle(self):
        a, b = self.hw - ANCHOR_INSET, self.hh - ANCHOR_INSET
        for _name, x, y in self.pts:
            dx, dy = abs(x - self.cx), abs(y - self.cy)
            on_vertical = abs(dx - a) <= 1e-6 and dy <= b + 1e-6
            on_horizontal = abs(dy - b) <= 1e-6 and dx <= a + 1e-6
            self.assertTrue(on_vertical or on_horizontal,
                            "anchor not on the inset rectangle: %s" % ((x, y),))

    def test_edge_midpoints(self):
        a, b = self.hw - ANCHOR_INSET, self.hh - ANCHOR_INSET
        self.assertEqual(self.by_id["n"], (self.cx, self.cy - b))
        self.assertEqual(self.by_id["s"], (self.cx, self.cy + b))
        self.assertEqual(self.by_id["e"], (self.cx + a, self.cy))
        self.assertEqual(self.by_id["w"], (self.cx - a, self.cy))

    def test_corners_not_at_geometric_tip(self):
        a, b = self.hw - ANCHOR_INSET, self.hh - ANCHOR_INSET
        self.assertEqual(self.by_id["ne"], (self.cx + a, self.cy - b))
        self.assertEqual(self.by_id["se"], (self.cx + a, self.cy + b))
        self.assertEqual(self.by_id["sw"], (self.cx - a, self.cy + b))
        self.assertEqual(self.by_id["nw"], (self.cx - a, self.cy - b))
        # inset means no anchor sits on the geometric corner tip
        tip = (self.cx + self.hw, self.cy + self.hh)
        self.assertGreater(math.hypot(*[self.by_id["se"][i] - tip[i]
                                        for i in range(2)]), 0.0)

    def test_golden_fractions(self):
        a, b = self.hw - ANCHOR_INSET, self.hh - ANCHOR_INSET
        g1, g2 = GOLDEN_FRACS
        # top edge, left -> right
        self.assertAlmostEqual(self.by_id["n-g1"][0],
                               self.cx - a + 2 * a * g1, places=6)
        self.assertAlmostEqual(self.by_id["n-g2"][0],
                               self.cx - a + 2 * a * g2, places=6)
        # right edge, top -> bottom
        self.assertAlmostEqual(self.by_id["e-g1"][1],
                               self.cy - b + 2 * b * g1, places=6)
        # bottom edge, right -> left
        self.assertAlmostEqual(self.by_id["s-g1"][0],
                               self.cx + a - 2 * a * g1, places=6)
        # left edge, bottom -> top
        self.assertAlmostEqual(self.by_id["w-g2"][1],
                               self.cy + b - 2 * b * g2, places=6)
        # golden points are strictly between the edge midpoint and its corner
        mid_x, corner_x = self.cx, self.cx + a
        self.assertLess(self.by_id["n-g1"][0], mid_x)
        self.assertGreater(self.by_id["n-g1"][0], self.cx - a)
        self.assertGreater(self.by_id["n-g2"][0], mid_x)
        self.assertLess(self.by_id["n-g2"][0], corner_x)

    def test_symmetric_box_symmetric_anchors(self):
        pts = standard_anchors(0, 0, 80, 40)
        by_id = {p[0]: (p[1], p[2]) for p in pts}
        self.assertAlmostEqual(by_id["n"][0], by_id["s"][0], places=6)
        self.assertAlmostEqual(by_id["e"][1], by_id["w"][1], places=6)
        self.assertAlmostEqual(by_id["n-g1"][0], -by_id["n-g2"][0], places=6)
        self.assertAlmostEqual(by_id["e-g1"][1], -by_id["e-g2"][1], places=6)

    def test_nearest_anchor_deterministic(self):
        # a point near the east midpoint snaps to "e"
        aid, x, y = nearest_anchor(self.cx, self.cy, self.hw, self.hh,
                                   self.cx + 200, self.cy)
        self.assertEqual(aid, "e")
        self.assertEqual((x, y), self.by_id["e"])
        # tie-break determinism: same input twice -> same winner (a point on
        # the right edge between "e" and "ne" is nearest to the golden
        # point "e-g1")
        b = self.hh - ANCHOR_INSET
        mid = (self.by_id["e"][0], (self.by_id["e"][1] + self.by_id["ne"][1]) / 2)
        got = nearest_anchor(self.cx, self.cy, self.hw, self.hh, *mid)[0]
        self.assertEqual(got, "e-g1")
        again = nearest_anchor(self.cx, self.cy, self.hw, self.hh, *mid)[0]
        self.assertEqual(got, again)

    def test_inset_must_leave_room(self):
        with self.assertRaises(ValueError):
            standard_anchors(0, 0, 2.0, 40.0)


if __name__ == "__main__":
    unittest.main()
