# -*- coding: utf-8 -*-
"""Certificate caliber-contract tests (WorkBuddy task 2026-11-11, S0-2).

Assertions describe the CURRENT contract only -- no product-code change:
  * v2 (auto) certificates emit grade tokens from the documented token
    space; interactive / drag_layer exist; the gates_passed tally matches
    the gates table.
  * The caliber is machine-describable: recipe / caliber / placement /
    grade_semantics / blocking_gates / deliverable are present.
    (The v1-legacy ortho caliber tests were removed together with the
    recipe's external entry, owner ruling 2026-11-24.)
  * Additive certificate fields must not leak into the rendered demo page
    (E8 regression guard: render consumes only specific cert keys).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, layout
from stdraw.loops import loops_audit
from stdraw.metrics import certificate_auto, scene_from_auto
from stdraw.render import render_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic")

# Historical token space (docs): `second` existed only in the retired
# v1-legacy caliber, `3d` is a retired docs-level tier (3D layer removed;
# the token stays so historical certificates still read back as valid).
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
