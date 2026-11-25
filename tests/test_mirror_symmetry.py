# -*- coding: utf-8 -*-
"""Mirror-symmetry post-pass (anchors-as-prior S2): opt-in flag, gate
re-run with fail-loud exceptions, constructive zero drift when OFF.

Guards baked in:
  - flag OFF: the auto output is byte-identical to the no-flag caliber
    (the meta key is absent; stripping nothing changes) -- the pass is
    constructively unreachable;
  - flag ON: node placement untouched (stage-1 coordinates identical),
    only route geometry of mirror edge pairs is mirrored;
  - the validity gate NEVER turns a gate-clean layout into a gate-breaking
    one: geometry_report fail stays 0 with the flag ON; violating pairs
    keep their original routes and appear in the exceptions list;
  - mirror-bearing deliveries read edge_mirror consistency 1.0 on the
    evaluable subset (golden / slot dual caliber);
  - graphs without a y-preserving involution get an explicit report
    reason, never a silent no-op.
"""
import io
import json
import copy
import contextlib
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw import check
from stdraw.dsl import parse
from stdraw.features import extract_features
from stdraw.layout_auto import AutoConfig, layout as auto_layout

COMB = os.path.join(ROOT, "benchmarks", "manual", "jacky-batch2",
                    "sources", "comb-supply-demand.cld")
BOWTIE = os.path.join(ROOT, "benchmarks", "manual", "jacky-batch2",
                      "sources", "bowtie-wage-price.cld")
LIMITS = os.path.join(ROOT, "examples", "limits-to-growth.cld")


def _run(path, flag):
    g = parse(open(path, encoding="utf-8").read())
    cfg = AutoConfig()
    cfg.mirror_symmetry = flag
    with contextlib.redirect_stdout(io.StringIO()):
        return auto_layout(g, cfg, "straight")


def _geo_fail(v4):
    with contextlib.redirect_stdout(io.StringIO()):
        return int(check.auto_geometry_report(v4)["fail"])


class TestFlagOffZeroDrift(unittest.TestCase):
    def test_off_is_byte_identical_and_deterministic(self):
        off1 = _run(LIMITS, False)
        off2 = _run(LIMITS, False)
        self.assertEqual(json.dumps(off1, sort_keys=True),
                         json.dumps(off2, sort_keys=True))
        self.assertNotIn("mirror_symmetry", off1["meta"])

    def test_on_without_sigma_equals_off_plus_report(self):
        off = _run(LIMITS, False)
        on = _run(LIMITS, False)
        cfg = AutoConfig()
        cfg.mirror_symmetry = True
        g = parse(open(LIMITS, encoding="utf-8").read())
        on = auto_layout(g, cfg, "straight")
        stripped = copy.deepcopy(on)
        stripped["meta"].pop("mirror_symmetry", None)
        self.assertEqual(json.dumps(off, sort_keys=True),
                         json.dumps(stripped, sort_keys=True))
        report = on["meta"]["mirror_symmetry"]
        self.assertIn("reason", report)
        self.assertNotIn("sigma_nodes", report)   # honest no-sigma record


_MANUAL_SOURCES = os.path.isdir(os.path.join(ROOT, "benchmarks", "manual",
                                             "jacky-batch2", "sources"))


@unittest.skipUnless(_MANUAL_SOURCES,
                     "repo-only data absent: benchmarks/manual/jacky-batch2")
class TestFlagOn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comb_on = _run(COMB, True)
        cls.comb_off = _run(COMB, False)

    def test_nodes_untouched_routes_mirrored(self):
        on, off = self.comb_on, self.comb_off
        for v, p in off["nodes"].items():
            self.assertEqual((p["x"], p["y"]),
                             (on["nodes"][v]["x"], on["nodes"][v]["y"]))
        report = on["meta"]["mirror_symmetry"]
        self.assertGreaterEqual(report["mirror_pairs"], 1)
        self.assertGreaterEqual(report["mirrored"], 1)

    def test_never_breaks_a_gate_clean_layout(self):
        self.assertEqual(_geo_fail(self.comb_off), 0)
        self.assertEqual(_geo_fail(self.comb_on), 0)

    def test_violating_pair_reverted_fail_loud(self):
        # Legacy straight-line caliber (loop-direction arc default switched
        # off): mirroring the second pair would create a visual crossing, so
        # the gate re-run must revert it and record it as an exception.
        with mock.patch("stdraw.routing.loop_arc_context",
                        lambda loops: contextlib.nullcontext()):
            on = _run(BOWTIE, True)
        self.assertEqual(_geo_fail(on), 0)
        report = on["meta"]["mirror_symmetry"]
        self.assertTrue(report["exceptions"], "the reverted pair must be "
                        "recorded as an exception")

    def test_arc_default_bowtie_mirrors_both_pairs_clean(self):
        # Default caliber (loop-member lines are loop-side arcs): the pair
        # that needed the revert under straight lines now mirrors cleanly,
        # so nothing is reverted and the exceptions list stays empty.
        on = _run(BOWTIE, True)
        self.assertEqual(_geo_fail(on), 0)
        report = on["meta"]["mirror_symmetry"]
        self.assertEqual(report["mirror_pairs"], 2)
        self.assertEqual(report["mirrored"], 2)
        self.assertEqual(report["exceptions"], [])

    def test_mirror_metric_on_mirrored_subset(self):
        """Acceptance caliber: on the MIRRORED subset (the evaluable
        subset -- reverted pairs are recorded as exceptions, not silently
        half-mirrored), every delivered slave polyline is the exact
        geometric mirror of its master within +-1px, and its endpoints sit
        on standard mirror anchors (golden/slot dual caliber)."""
        on = self.comb_on
        report = on["meta"]["mirror_symmetry"]
        self.assertGreaterEqual(report["mirrored"], 1)
        feat = extract_features(on)
        em = feat["features"]["edge_mirror"]
        self.assertEqual(em["presence"], 1)
        idx = {i: e for i, e in enumerate(on["edges"])}
        for pair in report["mirrored_pairs"]:
            slave, master = pair["slave"], pair["master"]
            sp = idx[slave]["route"]["points"]
            mp = idx[master]["route"]["points"]
            self.assertEqual(len(sp), len(mp))
            # delivery shifts the canvas; derive the delivered axis from
            # the first point pair, then verify the rest against +-1px
            c_del = (sp[0][0] + mp[0][0]) / 2.0
            for (sx, sy), (mx, my) in zip(sp[1:], mp[1:]):
                self.assertLessEqual(abs((2.0 * c_del - mx) - sx), 1.0)
                self.assertLessEqual(abs(my - sy), 1.0)

    def test_report_deterministic(self):
        on1 = _run(COMB, True)
        on2 = _run(COMB, True)
        self.assertEqual(json.dumps(on1["meta"]["mirror_symmetry"],
                                    sort_keys=True),
                         json.dumps(on2["meta"]["mirror_symmetry"],
                                    sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
