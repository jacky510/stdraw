# -*- coding: utf-8 -*-
"""Certificate caliber-contract tests (WorkBuddy task 2026-11-11, S0-2).

Assertions describe the CURRENT contract only -- no product-code change:
  * v1 (ortho) and v2 (auto) certificates emit grade tokens from the
    documented token space; interactive / drag_layer exist; the gates_passed
    tally matches the gates table.
  * The two calibers are machine-distinguishable: recipe / caliber /
    placement / grade_semantics / blocking_gates / deliverable are present,
    and the v1-legacy caliber is never deliverable (D0 ban).
  * Additive certificate fields must not leak into the rendered demo page
    (E8 regression guard: render consumes only specific cert keys).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw import __version__
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, layout
from stdraw.loops import loops_audit
from stdraw.metrics import (certificate, certificate_auto, scene_from_auto,
                            scene_from_planar)
from stdraw.planar import LayoutConfig, PlanarLayout
from stdraw.render import render_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic")

# Historical token space (docs): second exists only in the v1-legacy
# caliber, 3d is the docs-level 3D-delivery tier.
GRADE_TOKENS = {"best", "second", "3d", "uncertified"}


def load(name):
    with open(os.path.join(CORPUS, name + ".cld"), encoding="utf-8") as f:
        return parse(f.read())


def _gate_tally(cert):
    gates = cert["gates"]
    passed, total = (int(x) for x in cert["gates_passed"].split("/"))
    return passed, total, gates


class TestCertificateContract(unittest.TestCase):

    def test_v2_contract_fields(self):
        g = load("limits-to-growth")
        v4 = layout(g, AutoConfig())
        cert = certificate_auto(scene_from_auto(v4), graph_name="contract",
                                layer="2D", graph=g,
                                interactive="yes", drag_layer="yes",
                                deliverable=True)
        self.assertIn(cert["grade"], GRADE_TOKENS)
        self.assertIn("interactive", cert)
        self.assertIn("drag_layer", cert)
        self.assertIn("placement", cert)
        self.assertEqual(cert["recipe"], "auto-v2")
        self.assertEqual(cert["caliber"], "v2-hardgates")
        self.assertIs(cert["deliverable"], True)
        self.assertTrue(cert["grade_semantics"])
        self.assertIsInstance(cert["blocking_gates"], list)
        passed, total, gates = _gate_tally(cert)
        self.assertEqual(total, len(gates))
        self.assertEqual(passed, sum(1 for v in gates.values() if v))
        self.assertEqual(cert["blocking_gates"],
                         [k for k, v in gates.items() if v is False])

    def test_v1_contract_fields_and_d0_ban(self):
        g = load("limits-to-growth")
        v4 = PlanarLayout(g, LayoutConfig()).run()
        cert = certificate(scene_from_planar(v4), graph_name="contract",
                           layer="2D", notes=[],
                           interactive="yes", drag_layer="yes")
        self.assertIn(cert["grade"], GRADE_TOKENS)
        self.assertIn("interactive", cert)
        self.assertIn("drag_layer", cert)
        self.assertEqual(cert["version"], __version__)
        self.assertEqual(cert["recipe"], "ortho-v1")
        self.assertEqual(cert["caliber"], "v1-legacy")
        self.assertEqual(cert["placement"], "ortho-v1")
        # D0 iron rule: the v1-legacy caliber is NEVER a deliverable.
        self.assertIs(cert["deliverable"], False)
        self.assertEqual(cert["blocked_by"], "D0")
        self.assertTrue(cert["blocked_reason"])
        passed, total, gates = _gate_tally(cert)
        self.assertEqual(total, len(gates))
        self.assertEqual(passed, sum(1 for v in gates.values() if v))
        self.assertEqual(cert["blocking_gates"],
                         [k for k, v in gates.items() if v is False])

    def test_calibers_distinguishable_when_both_best(self):
        g = load("limits-to-growth")
        v4 = PlanarLayout(g, LayoutConfig()).run()
        cert_v1 = certificate(scene_from_planar(v4), graph_name="contract",
                              layer="2D", notes=[],
                              interactive="yes", drag_layer="yes")
        auto = layout(g, AutoConfig())
        cert_v2 = certificate_auto(scene_from_auto(auto),
                                   graph_name="contract", layer="2D",
                                   graph=g, interactive="yes",
                                   drag_layer="yes", deliverable=True)
        if cert_v1["grade"] == "best" and cert_v2["grade"] == "best":
            # Both say "best" but under different calibers: the gate sets
            # must differ, so hosts can tell the two rulers apart.
            self.assertNotEqual(cert_v1["caliber"], cert_v2["caliber"])
            self.assertNotEqual(len(cert_v1["gates"]), len(cert_v2["gates"]))

    def test_additive_fields_do_not_change_demo_bytes(self):
        # E8 regression guard: the renderer consumes grade / gates /
        # gates_passed / grade_note / metrics (plus placement / reports on
        # the v2 face).  Additive certificate fields -- today's caliber
        # confession or any future field -- must not alter demo bytes.
        g = load("limits-to-growth")
        v4 = layout(g, AutoConfig())
        cert = certificate_auto(scene_from_auto(v4), graph_name="contract",
                                layer="2D", graph=g,
                                interactive="yes", drag_layer="yes",
                                deliverable=True)
        lr = loops_audit(g)
        labels = {n.id: n.label for n in g.nodes}
        values = {n.id: n.value for n in g.nodes if n.value}
        base = render_html(v4, "contract", cert, lr, labels, values, "dark")
        fat = dict(cert)
        fat["caliber"] = "v2-hardgates"
        fat["grade_semantics"] = "x"
        fat["deliverable"] = True
        fat["future_field"] = {"nested": [1, 2, 3]}
        same = render_html(v4, "contract", fat, lr, labels, values, "dark")
        self.assertEqual(base, same)


if __name__ == "__main__":
    unittest.main()
