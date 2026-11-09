# -*- coding: utf-8 -*-
"""ref-scrubbed mode decision trace: certificate mode_decision_trace field.

The trigger-template audit trail (review report item 5): every rule
evaluation in the deterministic priority chain is recorded — which rule hit,
why, trial-gate outcome, and whether the registered anchor-band legacy
exemption applies. Recording only — the decision logic is untouched.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, layout
from stdraw.metrics import certificate_auto, scene_from_auto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic")


def load(name):
    with open(os.path.join(CORPUS, name + ".cld"), encoding="utf-8") as f:
        return parse(f.read())


class TestModeDecisionTrace(unittest.TestCase):

    def test_trace_present_and_wellformed(self):
        # every auto layout carries the trace; every rule entry is well-formed
        for name in ("classic-cld-growth-and-burden", "limits-to-growth",
                     "learning-flywheel", "debt-spiral"):
            tr = layout(load(name))["meta"]["mode_decision_trace"]
            self.assertFalse(tr["manual"], name)
            self.assertTrue(tr["rules"], name)
            for r in tr["rules"]:
                self.assertIn("tier", r, name)
                self.assertIn("rule", r, name)
                self.assertIsInstance(r["triggered"], bool, name)
                self.assertTrue(r["reason"], (name, r["rule"]))
                self.assertIn(r["trial_gate"], (None, "pass", "fail"), name)
            self.assertIn("legacy_band_exemption", tr, name)
            self.assertIsInstance(
                tr["legacy_band_exemption"]["triggered"], bool, name)

    def test_spine_wing_hit_records_the_winning_rule(self):
        tr = layout(load("classic-cld-growth-and-burden"))[
            "meta"]["mode_decision_trace"]
        hits = [r for r in tr["rules"] if r["triggered"]]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["rule"], "spine-wing")
        self.assertEqual(hits[0]["trial_gate"], "pass")
        self.assertIn("hub pair", hits[0]["reason"])
        # tiers evaluated before the hit carry concrete non-hit reasons
        earlier = [r for r in tr["rules"] if r["tier"] < hits[0]["tier"]]
        self.assertTrue(earlier)
        for r in earlier:
            self.assertFalse(r["triggered"])
            self.assertIsNotNone(r["reason"])
        # spine-wing is the enhanced-channel engine: no legacy exemption
        self.assertFalse(tr["legacy_band_exemption"]["triggered"])
        self.assertIn("100% in-band",
                      tr["legacy_band_exemption"]["detail"])

    def test_limits_to_growth_column_with_spine_wing_rejection_reason(self):
        # isomorphic spine but rest=0 (pure growth core) — the trace must say so
        tr = layout(load("limits-to-growth"))["meta"]["mode_decision_trace"]
        sw = [r for r in tr["rules"] if r["rule"] == "spine-wing"][0]
        self.assertFalse(sw["triggered"])
        # deterministic size gate fires first (core n=5 < 6): the reason carries
        # the measured number, not a bare rejection
        self.assertIn("core n=5", sw["reason"])
        hit = [r for r in tr["rules"] if r["triggered"]][0]
        self.assertEqual(hit["rule"], "column-chain")
        # non-spine-wing engines keep the registered v0.7.2 band baselines
        self.assertTrue(tr["legacy_band_exemption"]["triggered"])
        self.assertIn("registered v0.7.2",
                      tr["legacy_band_exemption"]["detail"])

    def test_certificate_carries_the_trace(self):
        g = load("classic-cld-growth-and-burden")
        v4 = layout(g, AutoConfig())
        cert = certificate_auto(scene_from_auto(v4), graph_name="t")
        tr = cert.get("mode_decision_trace")
        self.assertIsInstance(tr, dict)
        self.assertEqual(tr["placement"], "spine-wing")
        self.assertTrue(any(r["rule"] == "spine-wing" and r["triggered"]
                            for r in tr["rules"]))

    def test_manual_path_records_no_rules(self):
        # manual layouts bypass the priority chain — the trace says so honestly
        from stdraw.__main__ import load_manual_layout
        g = load("classic-cld-growth-and-burden")
        manual = load_manual_layout(os.path.join(
            ROOT, "tests", "baselines",
            "classic-cld-growth-and-burden.layout.json"))
        tr = layout(g, AutoConfig(), manual=manual)[
            "meta"]["mode_decision_trace"]
        self.assertTrue(tr["manual"])
        self.assertEqual(tr["rules"], [])
        self.assertIn("manual layout", tr["legacy_band_exemption"]["detail"])


if __name__ == "__main__":
    unittest.main()
