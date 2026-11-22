# -*- coding: utf-8 -*-
"""Anchors-as-prior candidate generation (S1): family gate, retrieval,
anchor-replay / anchor-seeded sources, provenance honesty.

Guards baked in:
  - the library sidecar is DATA (schema + only-add discipline asserted by
    shape, never by content copies of coordinates);
  - the family gate is a pure topology function (same input -> same key,
    zero thresholds);
  - non-hits are EXPLICIT in provenance (anchor_hit=null + reason) --
    silence is the forbidden mode (proposal section 1.1);
  - the anchor sources obey the zero-scoring-power source contract and stay
    disarmed without a retrieval hit;
  - the auto recipe stays byte-identical whether or not the pipeline ran
    (negative protection, S1 never touches the auto path).
"""
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw import anchor_prior, anchor_seed
from stdraw.candidate_pipeline import layout as cand_layout
from stdraw.candidate_sources import (ANCHOR_SOURCES, SOURCE_ORDER,
                                      generate_from_source)
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig

CLASSIC = os.path.join(ROOT, "examples",
                       "classic-cld-growth-and-burden.cld")
LIMITS = os.path.join(ROOT, "examples", "limits-to-growth.cld")
LONGTAIL = os.path.join(ROOT, "examples", "longtail-coupled-loops.cld")


def _graph(path=LIMITS):
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def _json(v4):
    return json.dumps(v4, sort_keys=True, ensure_ascii=False)


class TestFamilyGate(unittest.TestCase):
    def test_deterministic_and_threshold_free(self):
        g = _graph(CLASSIC)
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        f1, t1 = anchor_prior.family_of_graph(g, edges)
        f2, t2 = anchor_prior.family_of_graph(g, edges)
        self.assertEqual(f1, f2)
        self.assertEqual(t1, t2)
        self.assertIn(f1, ("ring", "hub", "column"))

    def test_chain_family_unmatched(self):
        g = _graph(LONGTAIL)
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        fam, _trace = anchor_prior.family_of_graph(g, edges)
        self.assertIsNone(fam)


class TestLibrary(unittest.TestCase):
    def test_sidecar_shape(self):
        lib = anchor_prior.load_library()
        self.assertIsNotNone(lib, "library sidecar must ship with the repo")
        self.assertEqual(lib["schema"], anchor_prior.LIBRARY_SCHEMA)
        anchors = lib["anchors"]
        self.assertGreaterEqual(len(anchors), 18)
        for key, a in anchors.items():
            self.assertIn("family", a)
            self.assertIn("nodes", a)
            self.assertIn("scalars", a)
            self.assertIn("graph_edges", a)
            self.assertTrue(a["path"].replace("\\", "/").startswith(
                "benchmarks/"), "library paths stay repo-relative")
        retrieval = lib["retrieval"]
        self.assertTrue(retrieval["feature_keys"])
        self.assertGreater(retrieval["hit_threshold"], 0)
        cal = retrieval["calibration"]
        self.assertIn("should_hit_distribution", cal)
        self.assertIn("should_not_hit_distribution", cal)
        # weights stay equal until a LOGO-calibrated alternative exists
        self.assertEqual(retrieval["weights"], "equal (preregistered "
                                                "starting point)")

    def test_sidecar_load_failure_degrades(self):
        self.assertIsNone(anchor_prior.load_library(
            os.path.join(ROOT, "tests", "data", "does-not-exist.json")))


class TestRetrieval(unittest.TestCase):
    def test_classic_hits_same_graph_anchor_replay(self):
        g = _graph(CLASSIC)
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        lib = anchor_prior.load_library()
        from stdraw.layout_auto import layout as auto
        baseline = auto(g, AutoConfig(), "straight")
        res = anchor_prior.retrieve(g, edges, baseline, lib)
        self.assertEqual(res["reason"], "hit")
        self.assertEqual(res["mode"], "anchor-replay")
        self.assertIsNotNone(res["anchor_hit"])

    def test_longtail_is_explicitly_unmatched(self):
        g = _graph(LONGTAIL)
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        lib = anchor_prior.load_library()
        from stdraw.layout_auto import layout as auto
        baseline = auto(g, AutoConfig(), "straight")
        res = anchor_prior.retrieve(g, edges, baseline, lib)
        self.assertIsNone(res["anchor_hit"])
        self.assertEqual(res["reason"], "family-unmatched")

    def test_library_unavailable_recorded(self):
        g = _graph(CLASSIC)
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        from stdraw.layout_auto import layout as auto
        baseline = auto(g, AutoConfig(), "straight")
        res = anchor_prior.retrieve(g, edges, baseline, None)
        self.assertIsNone(res["anchor_hit"])
        self.assertEqual(res["reason"], "library-unavailable")


class TestAnchorSeedTransplant(unittest.TestCase):
    def test_deterministic_and_grid(self):
        adj_i = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
        adj_a = {"x": {"y"}, "y": {"x", "z"}, "z": {"y"}}
        anchor = {"x": (100, 100), "y": (300, 100), "z": (200, 300)}
        p1 = anchor_seed.transplant(anchor, adj_i, adj_a)
        p2 = anchor_seed.transplant(anchor, adj_i, adj_a)
        self.assertEqual(p1, p2)
        self.assertEqual(set(p1), set(adj_i))
        for x, y in p1.values():
            self.assertEqual(x % anchor_seed.DELIVERY_GRID_PX, 0)
            self.assertEqual(y % anchor_seed.DELIVERY_GRID_PX, 0)
        # exact role match -> anchor coordinates verbatim
        self.assertEqual(p1["a"], (100, 100))
        self.assertEqual(p1["b"], (300, 100))
        self.assertEqual(p1["c"], (200, 300))

    def test_size_mismatch_stays_total_and_deterministic(self):
        adj_i = {"a": {"b"}, "b": {"a"}, "c": {"d"}, "d": {"c"},
                 "e": {"a", "c"}}
        adj_a = {"x": {"y"}, "y": {"x"}}
        anchor = {"x": (100, 100), "y": (300, 100)}
        p1 = anchor_seed.transplant(anchor, adj_i, adj_a)
        p2 = anchor_seed.transplant(anchor, adj_i, adj_a)
        self.assertEqual(p1, p2)
        self.assertEqual(set(p1), set(adj_i))
        self.assertEqual(len({p1[v] for v in p1}), len(p1),
                         "collision pass must free every cell")


class TestAnchorSources(unittest.TestCase):
    def test_source_order_registers_anchor_sources(self):
        for s in ANCHOR_SOURCES:
            self.assertIn(s, SOURCE_ORDER)
        self.assertLess(SOURCE_ORDER.index("anchor-replay"),
                        SOURCE_ORDER.index("layered-v082"))

    def test_sources_disarmed_without_hit(self):
        g = _graph(CLASSIC)
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        from stdraw.candidate_sources import SourceContext, template_enabled
        from stdraw.candidate_pipeline import _card_metrics, _dense_hub
        from stdraw.structure_analyzer import analyze_graph
        cfg = AutoConfig()
        widths, _h, card_h = _card_metrics(g, cfg)
        adj = g.adj_undirected()
        hub, _ = _dense_hub(g, adj)
        ctx = SourceContext(graph=g, cfg=cfg, widths=widths, card_h=card_h,
                            edges=edges, adj=adj, dense_hub=hub,
                            analysis=analyze_graph(g))
        for s in ANCHOR_SOURCES:
            self.assertFalse(template_enabled(s, ctx))
            from stdraw.candidate_sources import SourceUnavailable
            with self.assertRaises(SourceUnavailable):
                generate_from_source(s, ctx, seq=0)

    def test_zero_scoring_static_lint_anchor_seed(self):
        import ast
        path = os.path.join(ROOT, "stdraw", "anchor_seed.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        banned_mods = ("metrics", "check", "certificate", "gates",
                       "candidate_selection", "routing")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(
                        any(b in alias.name for b in banned_mods),
                        f"banned import in anchor_seed: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertFalse(any(b in mod for b in banned_mods),
                                 f"banned import in anchor_seed: {mod}")


class TestPipelineProvenance(unittest.TestCase):
    def test_classic_pipeline_records_hit_and_replay_source(self):
        g = _graph(CLASSIC)
        v4 = cand_layout(g, AutoConfig(), "straight")
        cp = v4["meta"]["candidate_pool"]
        ret = cp["anchor_retrieval"]
        self.assertEqual(ret["reason"], "hit")
        self.assertIsNotNone(ret["anchor_hit"])
        srcs = {r["source"]: r["outcome"]
                for r in cp["orchestration"]["source_records"]}
        self.assertEqual(srcs["anchor-replay"], "generated")
        self.assertEqual(srcs["anchor-seeded"], "disabled_by_rule")
        blob = json.dumps(cp, sort_keys=True)
        self.assertNotIn("timestamp", blob)
        self.assertNotIn(os.getcwd(), blob)

    def test_longtail_records_family_unmatched(self):
        g = _graph(LONGTAIL)
        v4 = cand_layout(g, AutoConfig(), "straight")
        ret = v4["meta"]["candidate_pool"]["anchor_retrieval"]
        self.assertIsNone(ret["anchor_hit"])
        self.assertEqual(ret["reason"], "family-unmatched")

    def test_double_run_byte_identical(self):
        g = _graph(CLASSIC)
        self.assertEqual(_json(cand_layout(g, AutoConfig(), "straight")),
                         _json(cand_layout(g, AutoConfig(), "straight")))

    def test_library_absence_degrades_pipeline_honestly(self):
        import stdraw.candidate_pipeline as cp_mod
        g = _graph(CLASSIC)
        with mock.patch("stdraw.anchor_prior.load_library",
                        return_value=None):
            v4 = cand_layout(g, AutoConfig(), "straight")
        ret = v4["meta"]["candidate_pool"]["anchor_retrieval"]
        self.assertIsNone(ret["anchor_hit"])
        self.assertEqual(ret["reason"], "library-unavailable")
        self.assertIn(v4["meta"]["candidate_pool"]["delivery"]["mode"],
                      ("candidate", "incumbent-fallback"))

    def test_negative_protection_auto_untouched(self):
        from stdraw.recipes import run as recipes_run
        g = _graph(CLASSIC)
        before = _json(recipes_run("auto-v2", g, AutoConfig(), "straight"))
        cand_layout(g, AutoConfig(), "straight")
        after = _json(recipes_run("auto-v2", g, AutoConfig(), "straight"))
        self.assertEqual(before, after)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
