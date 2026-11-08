# -*- coding: utf-8 -*-
"""v0.7.11 deterministic comb constraints (ref-scrubbed / 8777 comment 1750).

P1 #1: explicit source-column internal order (hard constraint, component
level so pendant trees stay contiguous). P1 #2: explicit hub side assignment
for the bilateral comb hubs. Both default None = engine-decided, meta keys
absent, byte-identical to the pre-0.7.11 deterministic contract.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, layout
from stdraw import comblayout, textmetrics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLD = os.path.join(ROOT, "tests", "data", "hdd-wide-tickers.cld")

ORDER = ["wafer", "xval", "cloud", "resonac", "hoya", "head"]
# a DISTINGUISHING order: engine's own choice on this fixture happens to
# equal the business order, so the hard-constraint proof uses the reversal
REVERSED_ORDER = list(reversed(ORDER))


def load():
    with open(CLD, encoding="utf-8") as f:
        return parse(f.read())


def widths_of(g, cfg):
    out = {}
    for v in g.node_ids():
        nd = g.id2node()[v]
        out[v], _ = textmetrics.card_size(nd.label, nd.value, cfg.fs_title,
                                          cfg.fs_value, min_w=cfg.card_min_w,
                                          value_pad=cfg.value_pad_extra)
    return out


class TestColumnOrderConstraint(unittest.TestCase):

    def test_engine_default_has_no_constraint_keys(self):
        g = load()
        cfg = AutoConfig()
        plan = comblayout.detect_comb(g)
        pos, y, meta, _ = comblayout.place_comb(plan, widths_of(g, cfg), 46, cfg)
        self.assertNotIn("column_order", meta["comb"])
        self.assertNotIn("hub_side", meta["comb"])
        v4 = layout(g, AutoConfig())
        self.assertNotIn("column_order", v4["meta"].get("comb", {}))
        self.assertNotIn("hub_side", v4["meta"].get("comb", {}))

    def test_explicit_order_is_a_hard_constraint(self):
        g = load()
        cfg = AutoConfig()
        cfg.column_order = REVERSED_ORDER
        plan = comblayout.detect_comb(g)
        pos, y, meta, _ = comblayout.place_comb(plan, widths_of(g, cfg), 46, cfg)
        col = meta["comb"]["column"]
        idx = [col.index(v) for v in REVERSED_ORDER]
        self.assertEqual(idx, sorted(idx),
                         f"listed relative order violated: {col}")
        self.assertEqual(meta["comb"]["column_order"], REVERSED_ORDER)

    def test_full_pipeline_with_constraints_is_deterministic(self):
        g = load()
        cfg = AutoConfig()
        cfg.column_order = ORDER
        cfg.hub_side = {"wdc": "left", "stx": "right"}
        v4 = layout(g, cfg)
        v4b = layout(g, cfg)
        self.assertEqual(json.dumps(v4, sort_keys=True),
                         json.dumps(v4b, sort_keys=True))


class TestHubSideConstraint(unittest.TestCase):

    def test_explicit_side_flips_assignment(self):
        g = load()
        cfg = AutoConfig()
        plan = comblayout.detect_comb(g)
        w = widths_of(g, cfg)
        _, _, meta0, _ = comblayout.place_comb(plan, w, 46, cfg)
        hl0, hr0 = meta0["comb"]["hubs"]
        cfg.hub_side = {hl0: "right"}          # one explicit side suffices
        pos, y, meta, _ = comblayout.place_comb(plan, w, 46, cfg)
        hl, hr = meta["comb"]["hubs"]
        self.assertEqual([hl, hr], [hr0, hl0])
        self.assertLess(pos[hl], pos[hr], "left hub must sit left of right hub")
        self.assertEqual(meta["comb"]["hub_side"], {hl: "left", hr: "right"})

    def test_honored_sides_match_requested_pair(self):
        g = load()
        cfg = AutoConfig()
        cfg.hub_side = {"wdc": "left", "stx": "right"}
        plan = comblayout.detect_comb(g)
        pos, y, meta, _ = comblayout.place_comb(plan, widths_of(g, cfg), 46, cfg)
        self.assertEqual(meta["comb"]["hubs"], ["wdc", "stx"])
        self.assertLess(pos["wdc"], pos["stx"])


if __name__ == "__main__":
    unittest.main()
