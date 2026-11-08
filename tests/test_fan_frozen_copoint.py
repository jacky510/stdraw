# -*- coding: utf-8 -*-
"""ref-scrubbed: fan_spread must treat frozen-edge anchors as occupied slots.

Background: the classic-cld frozen spine (rate->adopters constructed route)
leaves the border midpoint of rate's top / adopters' bottom, and the 3-slot
fan on the same side held its middle slot at the SAME midpoint -- a V-shaped
co-point of two different edges' anchors (visually one line forking into a
V). fan_spread now indexes frozen anchors per (node, side), and on conflict
gives the whole fan a deterministic half-step shift that (a) clears every
frozen anchor by >= MIN_FROZEN_ANCHOR_SEP and (b) stays azimuth-monotone
across the frozen anchors (slots must not cross to the opposite side of a
frozen anchor from their target box -- that would hide a real line crossing
behind the shared-endpoint exemption).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw.routing import MIN_FROZEN_ANCHOR_SEP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")


def _seg_min_dist(p1, p2, p3, p4):
    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1]

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1])

    r, s = sub(p2, p1), sub(p4, p3)
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) > 1e-12:
        t = ((p3[0] - p1[0]) * s[1] - (p3[1] - p1[1]) * s[0]) / denom
        u = ((p3[0] - p1[0]) * r[1] - (p3[1] - p1[1]) * r[0]) / denom
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            return 0.0
    best = None

    def pt_seg(p, a, b):
        ab = sub(b, a)
        L2 = dot(ab, ab)
        if L2 == 0:
            d = ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
            return d
        t = max(0.0, min(1.0, dot(sub(p, a), ab) / L2))
        q = (a[0] + t * ab[0], a[1] + t * ab[1])
        return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5

    for cand in (pt_seg(p1, p3, p4), pt_seg(p2, p3, p4),
                 pt_seg(p3, p1, p2), pt_seg(p4, p1, p2)):
        best = cand if best is None or cand < best else best
    return best


class TestFanFrozenCoPoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(EXAMPLE, encoding="utf-8") as f:
            dsl = f.read()
        cls.lay = layout(parse(dsl))
        cls.edges = cls.lay["edges"]
        cls.by_pair = {(e["a"], e["b"]): e for e in cls.edges}

    def _anchor(self, pair, end):
        e = self.by_pair[pair]
        return e["route"]["points"][0] if end == "a" else e["route"]["points"][-1]

    def test_spine_and_fan_anchors_separated(self):
        # The V co-point: frozen spine rate->adopters at the border midpoint
        # vs word->rate / adopters->word fan middle slots at the same point.
        spine_a = self._anchor(("rate", "adopters"), "a")   # rate top
        spine_b = self._anchor(("rate", "adopters"), "b")   # adopters bottom
        for fan_pair, end, spine_pt in (
                (("word", "rate"), "b", spine_a),
                (("adopters", "word"), "a", spine_b)):
            p = self._anchor(fan_pair, end)
            d = ((p[0] - spine_pt[0]) ** 2 + (p[1] - spine_pt[1]) ** 2) ** 0.5
            self.assertGreaterEqual(d, MIN_FROZEN_ANCHOR_SEP,
                                    f"{fan_pair} anchor {p} within "
                                    f"{MIN_FROZEN_ANCHOR_SEP}px of the frozen "
                                    f"spine anchor {spine_pt} (V co-point)")

    def test_fan_slots_azimuth_monotone_across_frozen(self):
        # word/potential boxes sit left of the spine axis, crowding right:
        # their slots must stay on the matching side of the frozen anchor.
        for box_side, spine_end, fans in (
                ("rate", "a", ((("potential", "rate"), -1),
                               (("word", "rate"), -1),
                               (("crowding", "rate"), +1))),
                ("adopters", "b", ((("adopters", "potential"), -1),
                                   (("adopters", "word"), -1),
                                   (("adopters", "crowding"), +1)))):
            spine_pt = self._anchor(("rate", "adopters"), spine_end)
            for pair, want_side in fans:
                p = self._anchor(pair, "b" if pair[1] == box_side else "a")
                side = 1 if p[0] > spine_pt[0] else -1
                self.assertEqual(side, want_side,
                                 f"{pair} slot crossed the frozen spine "
                                 f"(x={p[0]} vs spine x={spine_pt[0]})")

    def test_all_edge_pairs_no_cross_no_touch(self):
        # Coordinate-level acceptance: over ALL delivered edge pairs (incl.
        # pairs sharing an endpoint node): zero strict crossings AND zero
        # touches/co-points (contact at a point that is not a shared graph
        # endpoint of both edges).
        edges = [(e["a"], e["b"], e["route"]["points"]) for e in self.edges]
        bad = []
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                ai, bi, pi = edges[i]
                aj, bj, pj = edges[j]
                best = None
                for s1 in zip(pi[:-1], pi[1:]):
                    for s2 in zip(pj[:-1], pj[1:]):
                        d = _seg_min_dist(s1[0], s1[1], s2[0], s2[1])
                        best = d if best is None or d < best else best
                if best <= 1e-6:
                    bad.append((i, j, (ai, bi), (aj, bj), best))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
