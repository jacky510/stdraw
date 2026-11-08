# -*- coding: utf-8 -*-
"""ref-scrubbed: visual_crossings reported metric (all-edge-pair pairwise
intersection INCLUDING shared-endpoint fan pairs).

Background: the graph-theory `crossings` caliber exempts shared-endpoint
pairs, so a same-box fan whose lines cross mid-air shows an X on the
drawing while the certificate reports crossings=0 (classic-cld pre-d4c1901
measured 8 such intersections from the delivered HTML paths). The repo's
iron rule — honest grading, never masquerade as zero crossings — requires
the certificate to see what the eye sees, as a reported (non-vetoing)
metric until a legacy-number decision hardens it.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw.metrics import certificate_auto, scene_from_auto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")


def _cert_for(path_or_dsl):
    if os.path.exists(path_or_dsl):
        with open(path_or_dsl, encoding="utf-8") as f:
            dsl = f.read()
    else:
        dsl = path_or_dsl
    g = parse(dsl)
    v4 = layout(g)
    return certificate_auto(scene_from_auto(v4), graph_name="t", graph=g)


class TestVisualCrossings(unittest.TestCase):

    def test_classic_cld_visual_zero(self):
        # Acceptance anchor: post-d4c1901 classic-cld must stay 0 under the
        # all-pairs (fan-inclusive) caliber — default's HTML-path recount
        # measured 8 pre-fix, 0 post-fix.
        cert = _cert_for(EXAMPLE)
        m = cert["metrics"]
        self.assertIn("visual_crossings", m)
        self.assertEqual(m["visual_crossings"], 0)
        self.assertEqual(m["fan_visual_crossings"], 0)
        # consistency: without fan crossings, visual == graph-theory caliber
        self.assertEqual(m["visual_crossings"], m["crossings"])

    def test_report_item_present_not_a_gate(self):
        cert = _cert_for(EXAMPLE)
        self.assertIn("visual_crossings_zero", cert["reports"])
        self.assertTrue(cert["reports"]["visual_crossings_zero"])
        # must NOT leak into the hard-gate set
        self.assertNotIn("visual_crossings_zero", cert["gates"])

    def test_synthetic_fan_crossing_counted(self):
        # Hand-built fan: two edges from the same source whose straight
        # routes cross mid-air. Build the scene directly (no layout) so the
        # assertion pins the metric math, not the router.
        from stdraw.metrics import scene_from_auto
        nodes = {
            "a": {"x": 0, "y": 0, "w": 48, "h": 24},
            "b": {"x": 120, "y": -60, "w": 48, "h": 24},
            "c": {"x": 120, "y": 60, "w": 48, "h": 24},
        }
        edges = [{"a": "a", "b": "b"}, {"a": "a", "b": "c"}]
        # a's border slots swapped: the edge to b (up) departs from the
        # bottom slot and the edge to c (down) from the top slot — the two
        # straight fan lines cross mid-air (X under the fan origin)
        polylines = {
            0: [(24, 12), (60, -24), (96, -60)],
            1: [(24, -12), (60, 24), (96, 60)],
        }
        scene = {"nodes": nodes, "edges": edges, "polylines": polylines,
                 "line_kinds": ["straight", "straight"]}
        cert = certificate_auto(scene)
        m = cert["metrics"]
        self.assertEqual(m["crossings"], 0)  # graph-theory caliber: exempted
        self.assertEqual(m["visual_crossings"], 1)
        self.assertEqual(m["fan_visual_crossings"], 1)
        d = m["visual_crossing_details"][0]
        self.assertTrue(d["fan_pair"])
        self.assertEqual(d["edges"], ["a->b", "a->c"])

    def test_endpoint_touch_not_counted(self):
        # Two edges from the same source fanning out WITHOUT crossing (their
        # first segments only meet at the shared anchor) must stay 0 —
        # anchor meetings are not visual crossings.
        nodes = {
            "a": {"x": 0, "y": 0, "w": 48, "h": 24},
            "b": {"x": 120, "y": -60, "w": 48, "h": 24},
            "c": {"x": 120, "y": 60, "w": 48, "h": 24},
        }
        edges = [{"a": "a", "b": "b"}, {"a": "a", "b": "c"}]
        polylines = {
            0: [(12, -12), (60, -36), (96, -60)],
            1: [(12, 12), (60, 36), (96, 60)],
        }
        scene = {"nodes": nodes, "edges": edges, "polylines": polylines,
                 "line_kinds": ["straight", "straight"]}
        cert = certificate_auto(scene)
        self.assertEqual(cert["metrics"]["visual_crossings"], 0)

    def test_independent_pair_counted_once_in_both_calibers(self):
        # A crossing between two non-adjacent edges counts in both the
        # graph-theory caliber and the visual caliber.
        nodes = {
            "a": {"x": 0, "y": -60, "w": 48, "h": 24},
            "b": {"x": 120, "y": 60, "w": 48, "h": 24},
            "c": {"x": 0, "y": 60, "w": 48, "h": 24},
            "d": {"x": 120, "y": -60, "w": 48, "h": 24},
        }
        edges = [{"a": "a", "b": "b"}, {"a": "c", "b": "d"}]
        polylines = {
            0: [(24, -60), (96, 60)],
            1: [(24, 60), (96, -60)],
        }
        scene = {"nodes": nodes, "edges": edges, "polylines": polylines,
                 "line_kinds": ["straight", "straight"]}
        cert = certificate_auto(scene)
        m = cert["metrics"]
        self.assertEqual(m["crossings"], 1)
        self.assertEqual(m["visual_crossings"], 1)
        self.assertFalse(m["visual_crossing_details"][0]["fan_pair"])


if __name__ == "__main__":
    unittest.main()
