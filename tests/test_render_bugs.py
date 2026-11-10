# -*- coding: utf-8 -*-
"""ref-scrubbed triple render-bug regression tests.

#05/#10(1) line-line visual coincidence metric (machine-checkable),
#10(2) badge collision avoidance,
#15 route_svg_d fillet corner-redraw glitch + check13 delivery/verification
consistency gate.

Historical bug shape (observed in the d4b378f review snapshot):
  route_svg_d unconditionally redrew "L <corner>" after a fillet arc
  (L ta; A tb), producing a tb->corner->ta_next fold-back glitch in the
  rendered layer; the certificate only checked the dense sampled points
  (smooth), so delivery and verification were disconnected.
"""
import unittest

from stdraw.visibility import route_svg_d
from stdraw.check import (_parse_path_d, _path_d_all_points, _max_poly_dev,
                          _path_d_g1_max_deg)
from stdraw.metrics import _coincidence_span, certificate_auto, scene_from_auto


FIXED_D = ("M 226.8 230.0 L 211.2 219.8 A 34.6 34.6 0 0 1 196.0 196.5 "
           "L 188.0 147.5 A 34.6 34.6 0 0 0 172.8 124.2 L 157.2 114.0")
# glitch d captured before the fix (corners 198.5 211.5 / 185.5 132.5 redrawn after tb)
BUGGY_D = ("M 226.8 230.0 L 211.2 219.8 A 34.6 34.6 0 0 1 196.0 196.5 "
           "L 198.5 211.5 L 188.0 147.5 A 34.6 34.6 0 0 0 172.8 124.2 "
           "L 185.5 132.5 L 157.2 114.0")


class TestRouteSvgD(unittest.TestCase):
    def test_fillet_corner_not_redrawn(self):
        """The fillet corner is replaced by ta->arc->tb; the corner itself must not reappear."""
        corners = [(0, 0), (100, 0), (100, 100)]
        fillets = [{"i": 1, "ta": [90, 0], "tb": [100, 10],
                    "center": [90, 10], "r": 10, "sweep": 1}]
        d = route_svg_d(corners, fillets)
        self.assertIn("A 10.0 10.0 0 0 1 100.0 10.0", d)
        self.assertNotIn("L 100.0 0.0", d)      # the corner itself must not be redrawn
        self.assertTrue(d.endswith("L 100.0 100.0"))

    def test_unfilleted_corner_kept(self):
        corners = [(0, 0), (100, 0), (100, 100)]
        d = route_svg_d(corners, [])
        self.assertIn("L 100.0 0.0", d)


class TestCheck13PathD(unittest.TestCase):
    def test_buggy_d_fails_deviation(self):
        dense = _path_d_all_points(_parse_path_d(FIXED_D))
        dev = _max_poly_dev(_path_d_all_points(_parse_path_d(BUGGY_D)), dense)
        self.assertGreater(dev, 1.5)            # the glitch must be detected

    def test_fixed_d_passes_g1_and_deviation(self):
        elems = _parse_path_d(FIXED_D)
        dense = _path_d_all_points(elems)
        self.assertLessEqual(_max_poly_dev(dense, dense), 1.5)
        self.assertLessEqual(_path_d_g1_max_deg(elems), 4.0)

    def test_g1_catches_sharp_reversal(self):
        d = "M 0 0 L 100 0 L 100 5 L 100 -50 L 50 -50"
        self.assertGreater(_path_d_g1_max_deg(_parse_path_d(d)), 4.0)


class TestCoincidenceMetric(unittest.TestCase):
    def _cert(self, polylines):
        v4 = {
            "meta": {"cardH": 44, "placement": "grid"},
            "nodes": {
                "n1": {"x": 200, "y": 100, "w": 60},
                "n2": {"x": 200, "y": 300, "w": 60},
                "n3": {"x": 600, "y": 100, "w": 60},
                "n4": {"x": 600, "y": 300, "w": 60},
            },
            "edges": [
                {"a": "n1", "b": "n2", "route": {"points": polylines[0]},
                 "anchors": {}},
                {"a": "n3", "b": "n4", "route": {"points": polylines[1]},
                 "anchors": {}},
            ],
        }
        return certificate_auto(scene_from_auto(v4), graph_name="t")

    def test_parallel_overlap_counted(self):
        cert = self._cert([[(200, 200), (600, 200)],
                           [(200, 200.5), (600, 200.5)]])
        self.assertEqual(cert["metrics"]["line_line_coincident_pairs"], 1)
        self.assertFalse(cert["gates"]["lines_no_coincidence"])

    def test_separated_lines_pass(self):
        cert = self._cert([[(200, 200), (600, 200)],
                           [(200, 240), (600, 240)]])
        self.assertEqual(cert["metrics"]["line_line_coincident_pairs"], 0)
        self.assertTrue(cert["gates"]["lines_no_coincidence"])

    def test_crossing_not_counted(self):
        # single-point crossing: coincidence span is only ~1 sample step, below the 8px gate
        cert = self._cert([[(200, 100), (600, 300)],
                           [(200, 300), (600, 100)]])
        self.assertEqual(cert["metrics"]["line_line_coincident_pairs"], 0)

    def test_span_helper(self):
        from stdraw.routing import sample_polyline
        a = sample_polyline([(0, 0), (50, 0)])
        b = sample_polyline([(0, 0.4), (50, 0.4)])
        self.assertGreater(_coincidence_span(a, b, 4.0), 8.0)
        c = sample_polyline([(0, 30), (50, 30)])
        self.assertLessEqual(_coincidence_span(a, c, 4.0), 8.0)


class TestLoopColoring(unittest.TestCase):
    """ref-scrubbed: R/B letter badges removed; loop polarity is now expressed by edge coloring."""

    def _layout_edges(self, cld_text):
        from stdraw.dsl import parse
        from stdraw.layout_auto import layout
        g = parse(cld_text)
        v4 = layout(g)
        return g, v4

    def test_loop_edge_colored_by_declared_kind(self):
        g, v4 = self._layout_edges(open(
            "benchmarks/corpus/classic/wage-price-spiral.cld",
            encoding="utf-8").read())
        by_pair = {(e["a"], e["b"]): e for e in v4["edges"]}
        # R1 [wages, cost, prices]: all on-loop edges amber
        for a, b in (("wages", "cost"), ("cost", "prices"),
                     ("prices", "wages")):
            self.assertEqual(by_pair[(a, b)]["loop_kinds"], ["R"], (a, b))
            self.assertEqual(by_pair[(a, b)]["loop_color"], "#d97706", (a, b))
        # B1 [prices, real_income, demand]: all on-loop edges sky blue
        for a, b in (("prices", "real_income"), ("real_income", "demand"),
                     ("demand", "prices")):
            self.assertEqual(by_pair[(a, b)]["loop_kinds"], ["B"], (a, b))
            self.assertEqual(by_pair[(a, b)]["loop_color"], "#0284c7", (a, b))

    def test_mixed_loop_edge_neutral(self):
        # brand-flywheel: ad_effect->awareness belongs to both R1(R) and B1(B) -> neutral
        g, v4 = self._layout_edges(open(
            "benchmarks/corpus/classic/brand-flywheel.cld",
            encoding="utf-8").read())
        by_pair = {(e["a"], e["b"]): e for e in v4["edges"]}
        e = by_pair[("ad_effect", "awareness")]
        self.assertEqual(set(e["loop_kinds"]), {"R", "B"})
        self.assertIsNone(e["loop_color"])

    def test_render_no_letter_badges(self):
        from stdraw.render import render_auto_html
        g, v4 = self._layout_edges(open(
            "benchmarks/corpus/classic/wage-price-spiral.cld",
            encoding="utf-8").read())
        html = render_auto_html(v4, "wage")
        self.assertNotIn("data-pol", html)          # badge group no longer emitted
        self.assertIn('stroke="#c2410c"', html)     # '+' edges vermilion (UI-A light ink)
        self.assertIn('stroke="#1e6fae"', html)     # '−' edges drafting blue (UI-A light ink)
        self.assertNotIn('stroke-dasharray="', html)   # two-color caliber: all solid
        self.assertNotIn('stroke="#64748b"', html)     # no neutral-gray edges


if __name__ == "__main__":
    unittest.main()
