# -*- coding: utf-8 -*-
"""v0.7.8 wide-card comb tests: tier-1 facing-border fan (ref-scrubbed).

8777 consumer root cause: with double-ticker wide cards the tier-0 fan
(router-pool border_point anchors + global hub-span widening) is
angle-infeasible — widening anti-correlates with the horizontal-border
departure angle — and the comb fell back to layered (uncertified). The
tier-1 fan constructs hub edges between facing-vertical-border anchors and
delivers them through the constructed-route channel.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, layout
from stdraw import comblayout, textmetrics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDE = os.path.join(ROOT, "tests", "data", "hdd-wide-tickers.cld")


def load_wide():
    with open(WIDE, encoding="utf-8") as f:
        return parse(f.read())


def card_widths(g, cfg):
    out = {}
    for v in g.node_ids():
        nd = g.id2node()[v]
        w, _ = textmetrics.card_size(nd.label, nd.value, cfg.fs_title,
                                     cfg.fs_value, min_w=cfg.card_min_w,
                                     value_pad=cfg.value_pad_extra)
        out[v] = w
    return out


class TestWideCombPlacement(unittest.TestCase):

    def test_wide_cards_are_actually_wide(self):
        # the fixture must stay in the wide-card regime (much wider than
        # the narrow HDD example's 134-148px cards)
        cfg = AutoConfig()
        w = card_widths(load_wide(), cfg)
        self.assertGreater(w["xval"], 300)
        self.assertGreater(w["wafer"], 250)

    def test_tier0_infeasible_tier1_constructs(self):
        cfg = AutoConfig()
        g = load_wide()
        plan = comblayout.detect_comb(g)
        self.assertIsNotNone(plan)
        w = card_widths(g, cfg)
        pos, y, meta, constructed = comblayout.place_comb(plan, w, 46, cfg)
        # tier-1 marker + constructed fan for every directed hub edge
        self.assertEqual(meta["comb"].get("fan"), "facing-border")
        for s in plan["sources"]:
            for h in plan["hubs"]:
                self.assertIn((s, h), constructed)
        # narrow example stays tier 0 (no constructed routes)
        with open(os.path.join(ROOT, "examples",
                               "hdd-supply-chain.cld"), encoding="utf-8") as f:
            gn = parse(f.read())
        plann = comblayout.detect_comb(gn)
        wn = card_widths(gn, cfg)
        _, _, metan, constructedn = comblayout.place_comb(plann, wn, 44, cfg)
        self.assertNotIn("fan", metan["comb"])
        self.assertEqual(constructedn, {})

    def test_fan_anchors_on_facing_borders_and_spread(self):
        cfg = AutoConfig()
        g = load_wide()
        plan = comblayout.detect_comb(g)
        w = card_widths(g, cfg)
        pos, y, meta, constructed = comblayout.place_comb(plan, w, 46, cfg)
        for h in plan["hubs"]:
            ys = []
            for s in plan["sources"]:
                pa, pb = constructed[(s, h)]["points"]
                # source-side anchor on the source's facing vertical border
                sx = pos[s] + (-w[s] // 2 if pos[h] < pos[s] else w[s] // 2)
                self.assertEqual(pa[0], sx)
                # hub-side anchor on the hub's facing vertical border
                hx = pos[h] + (w[h] // 2 if pos[s] > pos[h] else -w[h] // 2)
                self.assertEqual(pb[0], hx)
                ys.append((y[s], pb[1]))
            # spread: distinct slots >= FAN_SEP_MIN, ordered by source row
            # (the non-crossing condition for converging fan segments)
            ys.sort()
            slots = [b for _, b in ys]
            for a, b in zip(slots, slots[1:]):
                self.assertGreaterEqual(b - a, comblayout.FAN_SEP_MIN)

    def test_fan_mirror_symmetry(self):
        cfg = AutoConfig()
        g = load_wide()
        plan = comblayout.detect_comb(g)
        w = card_widths(g, cfg)
        pos, y, meta, constructed = comblayout.place_comb(plan, w, 46, cfg)
        h1, h2 = plan["hubs"]
        # hub centers exactly mirrored about the column axis
        self.assertEqual(pos[h1] + pos[h2], 2 * meta["comb"]["axis_x"])
        for s in plan["sources"]:
            _, pb1 = constructed[(s, h1)]["points"]
            _, pb2 = constructed[(s, h2)]["points"]
            # anchor slots mirror exactly; the x offset mirrors up to the
            # hub half-width difference (hub cards may differ in width)
            self.assertEqual(pb1[1], pb2[1])
            self.assertAlmostEqual((pos[s] - pb1[0]) - (pb2[0] - pos[s]),
                                   (w[h2] - w[h1]) / 2.0, places=6)


class TestWideCombPipeline(unittest.TestCase):
    """Full auto pipeline: comb must be adopted (not fall back to layered)
    and graded best with the comb hard gates."""

    @classmethod
    def setUpClass(cls):
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load_wide()
        cls.v4 = layout(g)
        cls.cert = certificate_auto(scene_from_auto(cls.v4),
                                    graph_name=g.name, graph=g)

    def test_placement_comb_not_layered(self):
        self.assertEqual(self.v4["meta"]["position_engine"], "comb-construct")
        self.assertEqual(self.v4["meta"]["placement"], "comb-bilateral")
        self.assertEqual(self.cert["placement"], "comb-bilateral")

    def test_grade_best_all_gates(self):
        self.assertEqual(self.cert["grade"], "best")
        for k, v in self.cert["gates"].items():
            self.assertTrue(v, f"gate {k} failed")
        self.assertTrue(self.cert["gates"]["hub_edges_straight"])
        # all hub edges delivered as straight lines
        self.assertEqual(self.cert["metrics"]["line_kind_counts"],
                         {"line": 11})

    def test_delivered_hub_edges_straight_lines(self):
        for e in self.v4["edges"]:
            a, b = e["a"], e["b"]
            if a in ("stx", "wdc") or b in ("stx", "wdc"):
                self.assertEqual(e["route"]["kind"], "line")
                pts = e["route"]["points"]
                self.assertEqual(len(pts), 2)


if __name__ == "__main__":
    unittest.main()
