# -*- coding: utf-8 -*-
"""v0.7.7 feature tests: comb-bilateral placement + ring ratio guard +
per-edge style replay + value-line padding (ref-scrubbed)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, layout
from stdraw.metrics import certificate_auto, scene_from_auto
from stdraw import ringlayout, comblayout, textmetrics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic")


def load_example(name):
    with open(os.path.join(EXAMPLES, name + ".cld"), encoding="utf-8") as f:
        return parse(f.read())


def load_corpus(name):
    with open(os.path.join(CORPUS, name + ".cld"), encoding="utf-8") as f:
        return parse(f.read())


K52_DSL = """graph "pure-bilateral"
var s1 "Source one"
var s2 "Source two"
var s3 "Source three"
var h1 "Hub one"
var h2 "Hub two"
s1 -> + h1
s1 -> + h2
s2 -> + h1
s2 -> + h2
s3 -> + h1
s3 -> + h2
"""


class TestCombDetection(unittest.TestCase):

    def test_hdd_example_triggers_comb(self):
        g = load_example("hdd-supply-chain")
        plan = comblayout.detect_comb(g)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["hubs"], ["stx", "wdc"])
        self.assertEqual(plan["sources"],
                         ["xval", "cloud", "resonac", "hoya", "head"])
        self.assertEqual(plan["m"], 5)

    def test_column_order_pendant_at_end(self):
        # pendant wafer lands adjacent to its attachment (xval), at the
        # column end — the structurally derived chain order
        g = load_example("hdd-supply-chain")
        plan = comblayout.detect_comb(g)
        self.assertEqual(plan["column"],
                         ["wafer", "xval", "cloud", "resonac", "hoya", "head"])

    def test_pure_k52_triggers(self):
        plan = comblayout.detect_comb(parse(K52_DSL))
        self.assertIsNotNone(plan)
        self.assertEqual(plan["m"], 3)

    def test_adjacent_hubs_rejected(self):
        # hubs connected to each other are not a bilateral pair
        dsl = K52_DSL + "h1 -> + h2\n"
        self.assertIsNone(comblayout.detect_comb(parse(dsl)))

    def test_inter_source_edge_rejected(self):
        # an edge between sources breaks the pendant-tree reading
        dsl = K52_DSL + "s1 -> + s2\n"
        self.assertIsNone(comblayout.detect_comb(parse(dsl)))

    def test_too_few_sources_rejected(self):
        dsl = """graph "small"
var a "A"
var b "B"
var h1 "H1"
var h2 "H2"
a -> + h1
a -> + h2
b -> + h1
b -> + h2
"""
        self.assertIsNone(comblayout.detect_comb(parse(dsl)))


class TestCombLayout(unittest.TestCase):

    def _cert(self, g):
        v4 = layout(g)
        cert = certificate_auto(scene_from_auto(v4), graph_name=g.name, graph=g)
        return v4, cert

    def test_hdd_comb_layout_geometry(self):
        g = load_example("hdd-supply-chain")
        v4, cert = self._cert(g)
        meta = v4["meta"]
        self.assertEqual(meta["position_engine"], "comb-construct")
        self.assertEqual(meta["placement"], "comb-bilateral")
        self.assertEqual(cert["placement"], "comb-bilateral")
        # column x exactly on-axis (0 deviation, gate <= 2px)
        self.assertEqual(cert["metrics"]["column_axis_deviation"], 0)
        # hub pair exactly mirrored about the column axis
        self.assertEqual(cert["metrics"]["hub_symmetry_err"], 0)
        # all 11 edges straight lines (line-kind counts)
        self.assertEqual(cert["metrics"]["line_kind_counts"], {"line": 11})
        # honest grading: best, all comb hard gates
        self.assertEqual(cert["grade"], "best")
        for gate in ("column_axis_aligned", "column_pitch_uniform",
                     "hub_symmetry_le_2px", "hub_edges_straight"):
            self.assertTrue(cert["gates"][gate], gate)

    def test_hdd_ring_detect_grounded(self):
        # the K_{m,2} ratio misfire: detect_ring must return None for the
        # comb family (previously trigger=ratio with a 4-cycle main ring)
        g = load_example("hdd-supply-chain")
        self.assertIsNone(ringlayout.detect_ring(g))

    def test_classic_cld_ratio_trigger_preserved(self):
        # non-comb graphs keep the historical ratio behavior (k=4 is
        # legitimate there; classic-cld is spine-wing in the chain but
        # detect_ring itself still reports the ratio trigger)
        g = load_corpus("classic-cld-growth-and-burden")
        p = ringlayout.detect_ring(g)
        self.assertIsNotNone(p)
        self.assertEqual(p["trigger"], "ratio")

    def test_corpus_column_families_locked(self):
        # salience rule: burnout-attrition / urban-migration stay
        # column-chain (their spine is at least as salient as the comb
        # column) — the 19-graph corpus is byte-stable
        for name in ("burnout-attrition", "urban-migration"):
            v4 = layout(load_corpus(name))
            self.assertEqual(v4["meta"]["placement"], "column-chain", name)


class TestManualEdgeStyles(unittest.TestCase):

    def _manual(self, g, edges):
        v4_auto = layout(g)
        return {"nodes": {v: {"x": p["x"], "y": p["y"]}
                          for v, p in v4_auto["nodes"].items()},
                "viewBox": v4_auto["viewBox"],
                "edges": edges}

    def test_straight_and_arc_replay(self):
        g = load_example("hdd-supply-chain")
        manual = self._manual(g, [
            {"a": "cloud", "b": "stx", "style": "arc"},
            {"a": "xval", "b": "wdc", "style": "straight"},
        ])
        v4 = layout(g, manual=manual)
        kinds = {(e["a"], e["b"]): e["route"]["kind"] for e in v4["edges"]}
        self.assertEqual(kinds[("cloud", "stx")], "arc")
        self.assertEqual(kinds[("xval", "wdc")], "line")
        e_arc = [e for e in v4["edges"]
                 if (e["a"], e["b"]) == ("cloud", "stx")][0]
        self.assertIn("ctrl", e_arc["route"])
        self.assertEqual(v4["meta"]["from_layout"]["styled_edges"], 2)

    def test_free_waypoints_replay(self):
        g = load_example("hdd-supply-chain")
        manual = self._manual(g, [
            {"a": "hoya", "b": "wdc", "style": "free",
             "waypoints": [[300, 430]]},
        ])
        v4 = layout(g, manual=manual)
        e = [x for x in v4["edges"]
             if (x["a"], x["b"]) == ("hoya", "wdc")][0]
        self.assertEqual(e["route"]["kind"], "waypoints")
        self.assertEqual(e["route"]["via"], [[300.0, 430.0]])

    def test_invalid_style_rejected(self):
        g = load_example("hdd-supply-chain")
        manual = self._manual(g, [{"a": "cloud", "b": "stx", "style": "zigzag"}])
        with self.assertRaises(ValueError):
            layout(g, manual=manual)

    def test_unknown_edge_rejected(self):
        g = load_example("hdd-supply-chain")
        manual = self._manual(g, [{"a": "cloud", "b": "nobody", "style": "arc"}])
        with self.assertRaises(ValueError):
            layout(g, manual=manual)

    def test_arc_rule_deterministic(self):
        # the forced-arc side rule (max clearance, tie -> +1) is
        # deterministic: same input, identical output
        g = load_example("hdd-supply-chain")
        v4_auto = layout(g)
        manual = self._manual(g, [{"a": "cloud", "b": "stx", "style": "arc"}])
        a = layout(g, manual=json.loads(json.dumps(manual)))
        b = layout(g, manual=json.loads(json.dumps(manual)))
        self.assertEqual(json.dumps(a["edges"]), json.dumps(b["edges"]))
        self.assertEqual(a["viewBox"], v4_auto["viewBox"])  # nodes unchanged


class TestValuePad(unittest.TestCase):

    def test_default_baseline_unchanged(self):
        # default value_pad=None keeps the historical pad-4 baseline
        # (zero drift caliber): identical card size to the legacy call
        legacy = textmetrics.card_size("HOYA", "7741.T 22,395.00 JPY",
                                       12.5, 14.0, min_w=96)
        current = textmetrics.card_size("HOYA", "7741.T 22,395.00 JPY",
                                        12.5, 14.0, min_w=96,
                                        value_pad=None)
        self.assertEqual(legacy, current)

    def test_value_pad_widens_card(self):
        w0, _ = textmetrics.card_size("HOYA", "7741.T 22,395.00 JPY",
                                      12.5, 14.0, min_w=96)
        w1, _ = textmetrics.card_size("HOYA", "7741.T 22,395.00 JPY",
                                      12.5, 14.0, min_w=96, value_pad=18.0 + 4)
        self.assertGreater(w1, w0)
        # the long value line now fits with margin: text width + 2*pad <= w1
        tw = textmetrics.text_width("7741.T 22,395.00 JPY", 14.0, bold=True)
        self.assertGreaterEqual(w1, tw + 2 * 18.0)

    def test_config_passthrough(self):
        # AutoConfig.value_pad_extra flows into the planned card widths
        g = load_example("hdd-supply-chain")
        v4a = layout(g)
        cfg = AutoConfig()
        cfg.value_pad_extra = 22.0
        v4b = layout(g, config=cfg)
        wa = max(p["w"] for p in v4a["nodes"].values())
        wb = max(p["w"] for p in v4b["nodes"].values())
        self.assertGreaterEqual(wb, wa)


if __name__ == "__main__":
    unittest.main()
