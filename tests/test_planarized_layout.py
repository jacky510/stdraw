# -*- coding: utf-8 -*-
"""Planarized 2D layer (L1/L2 degrade ladder) unit tests.

Implementation basis: docs/planarization-degrade-contract.md (@ d71263a).
"""
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse(path):
    from stdraw.dsl import parse
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def _graph_from_edges(nodes, edges):
    from stdraw.model import Graph, Node, Edge
    return Graph(name="t",
                 nodes=[Node(id=v, label=v) for v in nodes],
                 edges=[Edge(a=a, b=b, polarity="+") for a, b in edges])


class TestStraightThrough(unittest.TestCase):
    def test_witness_is_segment_interior(self):
        """Both neighbouring delivered segments must contain the witness
        in their interior (strict seg_cross caliber)."""
        from stdraw.planarized_layout import _straight_through
        pts = _straight_through([(0.0, 0.0), (10.0, 10.0), (30.0, 0.0)])
        # witness (10, 10): overshoot point beyond it along the incoming
        # direction and the back-cut point before it along the outgoing
        self.assertEqual(len(pts), 4)
        self.assertGreater(pts[1][0], 10.0)      # overshoot past the witness
        self.assertLess(pts[2][0], 10.0)         # back-cut before it

    def test_no_witness_passthrough(self):
        from stdraw.planarized_layout import _straight_through
        pts = _straight_through([(0.0, 0.0), (5.0, 5.0)])
        self.assertEqual(pts, [[0.0, 0.0], [5.0, 5.0]])


class TestCorePlanarity(unittest.TestCase):
    def test_planar_graph_is_L0(self):
        """A planar-core graph never enters the planarized layer
        (contract section 1: L0 untouched, zero drift by construction)."""
        from stdraw.planarized_layout import planarized_entry
        from stdraw.layout_auto import AutoConfig
        g = _graph_from_edges(
            ["A", "B", "C", "D"],
            [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"), ("A", "C")])
        mode, payload = planarized_entry(g, AutoConfig(), "straight")
        self.assertEqual(mode, "L0")
        self.assertIsNone(payload)

    def test_nonplanar_graph_enters_ladder(self):
        """K5 (5 nodes, 10 edges) is non-planar: the ladder must produce
        L1 (in budget) or an honest L2 record -- never a silent pass."""
        from stdraw.planarized_layout import planarized_entry
        from stdraw.layout_auto import AutoConfig
        nodes = [f"K{i}" for i in range(5)]
        edges = [(a, b) for a in range(5) for b in range(a + 1, 5)]
        g = _graph_from_edges(nodes, [(nodes[a], nodes[b])
                                      for a, b in edges])
        mode, payload = planarized_entry(g, AutoConfig(), "straight")
        if mode == "L1":
            self.assertIn("planarization", payload["meta"])
            self.assertEqual(payload["meta"]["planarization"]["mode"], "L1")
        else:
            self.assertEqual(mode, "L2")
            self.assertTrue(payload["deferred"]["reason"])
            self.assertEqual(payload["mode"], "L2")


class TestCertificateL1Caliber(unittest.TestCase):
    """End-to-end: the WorkBuddy n10 non-planar corpus sample must come
    out crossed-certified with the three accounts agreeing (card
    acceptance; measured on this machine, deterministic)."""

    SAMPLE = os.path.join(ROOT, "benchmarks", "corpus", "random",
                          "random-n10-i09.cld")

    def test_n10_i09_crossed_certified(self):
        if not os.path.exists(self.SAMPLE):
            self.skipTest("random corpus not present")
        from stdraw.dsl import parse
        from stdraw.layout_auto import AutoConfig, layout as auto_layout
        from stdraw.metrics import certificate_auto, scene_from_auto
        from stdraw.crossing_exact import crossing_exact
        g = _parse(self.SAMPLE)
        v4 = auto_layout(g, AutoConfig(), "straight")
        self.assertEqual(v4["meta"].get("planarization", {}).get("mode"),
                         "L1")
        exactness = v4["meta"]["planarization"]["exactness"]
        cert = certificate_auto(scene_from_auto(v4), graph_name="n10-i09",
                                layer="2D", graph=g, exactness=exactness)
        self.assertEqual(cert["grade"], "crossed-certified")
        self.assertTrue(cert["gates"]["crossings_witnessed"])
        self.assertTrue(cert["gates"]["three_account_consistent"])
        self.assertEqual(cert["metrics"]["crossings"],
                         cert["exactness"]["crossing_number"])
        self.assertGreater(cert["metrics"]["crossings"], 0)
        # witness markers carried for rendering (contract section 3)
        self.assertEqual(len(v4["meta"]["planarization"]["markers"]),
                         cert["metrics"]["crossings"])


class TestD2MarkerSpec(unittest.TestCase):
    """D2 marker spec final (UIDesignerBot, 2026-11-14): per-theme color
    tokens (R1 dark-tier fix), hover halo + render-layer tooltip, dense
    cluster folding — rendering regressions for the alignment rework."""

    def _render(self, markers, theme="light"):
        from stdraw.render import render_auto_html
        v4 = {"viewBox": [0, 0, 200, 200],
              "meta": {"cardH": 44, "fs": [12.5, 14],
                       "planarization": {"mode": "L1", "ub": 3, "lb": 3,
                                         "gap": 0, "markers": markers}},
              "nodes": {"a": {"x": 30, "y": 180, "w": 60},
                        "b": {"x": 170, "y": 180, "w": 60}},
              "edges": []}
        return render_auto_html(v4, graph_name="t", theme=theme)

    @staticmethod
    def _mk(wid, x, y):
        return {"point": [x, y], "witness_id": wid, "edges": [("a", "b")]}

    def test_d2_constants(self):
        import stdraw.planarized_layout as PL
        self.assertEqual(PL.MARKER_SIZE_PX, 9)
        self.assertEqual(PL.MARKER_STROKE_PX, 1.2)
        self.assertEqual(PL.MARKER_HOVER_FONT_PX, 11)
        self.assertEqual(PL.MARKER_HOVER_ALPHA, 0.14)
        self.assertEqual(PL.MARKER_HOVER_RING_PX, 12)
        self.assertEqual(PL.MARKER_CLUSTER_PX, 10)
        self.assertEqual(PL.MARKER_BADGE_PX, 10)
        self.assertEqual(PL.MARKER_BADGE_FONT_PX, 8.5)
        # R1: color is a per-theme token now, no single MARKER_COLOR
        self.assertFalse(hasattr(PL, "MARKER_COLOR"))
        self.assertFalse(hasattr(PL, "MARKER_HOVER_BG"))

    def test_theme_tokens_carry_marker_color(self):
        from stdraw.themes import DARK, LIGHT
        self.assertEqual(set(LIGHT) == set(DARK), True)
        self.assertEqual(LIGHT["xwitness_color"], "#64748b")
        self.assertEqual(DARK["xwitness_color"], "#8b98ab")
        self.assertEqual(LIGHT["xwitness_tip_text"], "#334155")
        self.assertEqual(DARK["xwitness_tip_text"], "#dfe7f2")

    def test_cluster_helper_groups(self):
        from stdraw.planarized_layout import _cluster_xwitnesses
        pts = [[0, 0], [5, 0], [40, 0], [46, 0], [80, 0], [86, 0], [92, 0]]
        self.assertEqual(_cluster_xwitnesses(pts),
                         [[0, 1], [2, 3], [4, 5, 6]])
        # 11px apart = outside the 10px join radius
        self.assertEqual(_cluster_xwitnesses([[0, 0], [11, 0]]), [[0], [1]])

    def test_default_state_exact_coordinates_no_title(self):
        out = self._render([self._mk(1, 100.0, 50.0), self._mk(2, 60.0, 30.0)])
        # exact witness coordinates (no displacement, <= 2 renders apart)
        self.assertIn('x1="95.5" y1="45.5"', out)
        self.assertIn('x2="104.5" y2="54.5"', out)
        # hover skeleton fields intact; SVG <title> retired
        self.assertIn("witness #1", out)
        self.assertIn("cr UB=3 (LB=3, gap=0)", out)
        self.assertEqual(out.count("<title>"), 1)  # only the page <title>
        self.assertIn("stdraw-xwitness-hit", out)
        self.assertIn('id="stdraw-xwitness-tip"', out)
        # no click behavior registered (v1: display-only)
        self.assertNotIn("crossing_details", out)

    def test_dark_theme_uses_dark_ink(self):
        markers = [self._mk(1, 100.0, 50.0)]
        dark = self._render(markers, theme="dark")
        light = self._render(markers, theme="light")
        self.assertIn('stroke="#8b98ab"', dark)
        self.assertNotIn('stroke="#64748b"', dark)
        self.assertIn('stroke="#64748b"', light)
        self.assertIn("rgba(139,152,171,0.14)", dark)
        self.assertIn("rgba(100,116,139,0.14)", light)

    def test_dense_cluster_folds_into_badge(self):
        # 3 witnesses within the 10px join radius -> one badge
        markers = [self._mk(1, 100.0, 50.0), self._mk(2, 104.0, 52.0),
                   self._mk(3, 97.0, 55.0)]
        out = self._render(markers)
        self.assertIn("stdraw-xwitness-badge", out)
        self.assertIn("&times;3", out)
        # badge center = cluster centroid; badge diameter 10px
        self.assertIn('cx="100.3" cy="52.3" r="5"', out)
        # badge tooltip lists every member, one full field per line
        tip = out.split('data-tip="')[1].split('"')[0]
        self.assertEqual(tip.count("witness #"), 3)
        # data layer untouched: markers[] entries all carry their points
        # (rendering is presentation-only; members get no x-symbols)
        self.assertEqual(out.count('<g class="stdraw-xwitness">'), 0)
        self.assertEqual(out.count('class="stdraw-xwitness-hit"'), 1)

    def test_pair_renders_independently(self):
        markers = [self._mk(1, 100.0, 50.0), self._mk(2, 104.0, 52.0)]
        out = self._render(markers)
        self.assertNotIn("stdraw-xwitness-badge", out)
        self.assertEqual(out.count('class="stdraw-xwitness"'), 2)
        self.assertEqual(out.count("witness #"), 2)

    def test_render_is_deterministic(self):
        markers = [self._mk(i + 1, 100.0 + i, 50.0 + 2 * i)
                   for i in range(4)]
        self.assertEqual(self._render(markers), self._render(markers))


class TestL2Honesty(unittest.TestCase):
    def test_cap_exceeded_defers_honestly(self):
        """When the admission cap rejects the oracle UB, the ladder must
        fall back to L2 with a measured reason (never a silent pass)."""
        import stdraw.planarized_layout as PL
        from stdraw.layout_auto import AutoConfig
        nodes = [f"K{i}" for i in range(5)]
        edges = [(nodes[a], nodes[b])
                 for a in range(5) for b in range(a + 1, 5)]
        g = _graph_from_edges(nodes, edges)
        orig_cap = PL.cap_for
        PL.cap_for = lambda n: 0          # force the cap rejection
        # run in-process (the pinned worker would not see the patch)
        prev_pinned = os.environ.get("STDRAW_L1_PINNED")
        os.environ["STDRAW_L1_PINNED"] = "1"
        try:
            mode, payload = PL.planarized_entry(g, AutoConfig(), "straight")
        finally:
            PL.cap_for = orig_cap
            if prev_pinned is None:
                os.environ.pop("STDRAW_L1_PINNED", None)
            else:
                os.environ["STDRAW_L1_PINNED"] = prev_pinned
        self.assertEqual(mode, "L2")
        rec = payload["deferred"]
        self.assertTrue(rec["reason"])
        self.assertTrue(all(r for r in rec["reason"]))
        self.assertEqual(payload["mode"], "L2")
        self.assertIn("cap", rec["reason"][0].lower())

    def test_cap_formula_is_min_3n_80(self):
        from stdraw.planarized_layout import cap_for
        self.assertEqual(cap_for(10), 30)
        self.assertEqual(cap_for(30), 80)
        self.assertEqual(cap_for(50), 80)


if __name__ == "__main__":
    unittest.main()
