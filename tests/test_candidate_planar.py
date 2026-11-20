# -*- coding: utf-8 -*-
"""M1-B planarization candidate source tests: construction core (deletion
enumeration / dual-variant re-insertion keys / straight-segment crossings),
source integration (enable rule / emission contract / determinism),
pipeline L1-scope integration, longtail acceptance corpus integrity.
"""
import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.candidate_planar import (LOOP_WEIGHT_OTHER, LOOP_WEIGHT_PRIMARY,
                                     PLANAR_MAX_DELETION_SETS,
                                     PlanarProbeUnavailable,
                                     core_is_planar,
                                     planar_deletion_sets,
                                     planarized_candidates,
                                     primary_loop_edge_set,
                                     reinsertion_crossings, variant_keys)
from stdraw.candidate_pipeline import _card_metrics, layout
from stdraw.candidate_sources import (SOURCE_ORDER, SourceContext,
                                      SourceConstructionError,
                                      SourceUnavailable, generate_from_source,
                                      template_enabled)
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig
from stdraw.model import Edge, Graph, Node
from stdraw.structure_analyzer import analyze_graph

LONGTAIL_DIR = os.path.join(ROOT, "benchmarks", "corpus", "longtail")


def _graph(nodes, edges, name="t"):
    return Graph(name=name, nodes=[Node(id=v, label=v) for v in nodes],
                 edges=[Edge(a=a, b=b, polarity="+") for a, b in edges])


def k5():
    vs = [f"v{i}" for i in range(5)]
    return vs, [(vs[i], vs[j]) for i in range(5)
                for j in range(i + 1, 5)]


def k6():
    vs = [f"w{i}" for i in range(6)]
    return vs, [(vs[i], vs[j]) for i in range(6)
                for j in range(i + 1, 6)]


def _ctx(nodes, edges):
    from stdraw.candidate_pipeline import _dense_hub
    g = _graph(nodes, edges)
    cfg = AutoConfig()
    e = tuple(sorted((x.a, x.b) for x in g.edges))
    widths, heights, card_h = _card_metrics(g, cfg)
    adj = g.adj_undirected()
    hub, _ = _dense_hub(g, adj)
    return SourceContext(graph=g, cfg=cfg, widths=widths, card_h=card_h,
                         edges=e, adj=adj, dense_hub=hub,
                         analysis=analyze_graph(g))


def _json(v4):
    return json.dumps(v4, sort_keys=True, ensure_ascii=False)


# ------------------------------------------------------- construction core

class TestDeletionSets(unittest.TestCase):
    def test_k5_single_edge_sets_exist(self):
        nodes, edges = k5()
        sets, capped = planar_deletion_sets(edges)
        self.assertTrue(sets)
        for d in sets:
            self.assertLessEqual(len(d), 2)
        self.assertTrue(capped)          # 10 single sets > cap 4
        self.assertEqual(len(sets), PLANAR_MAX_DELETION_SETS)

    def test_k6_needs_more_than_two_deletions_not_triggered(self):
        nodes, edges = k6()
        sets, capped = planar_deletion_sets(edges)
        self.assertEqual(sets, [])
        self.assertFalse(capped)

    def test_primary_loop_edges_protected(self):
        # C4 plus a chord making a non-planar core is impossible; instead
        # verify the protection filter directly: mark one K5 edge as the
        # "primary" edge and check it never appears in any deletion set.
        nodes, edges = k5()
        protected = {frozenset(edges[0])}
        sets, _ = planar_deletion_sets(edges, protected)
        for d in sets:
            for e in d:
                self.assertNotEqual(frozenset(e), frozenset(edges[0]))

    def test_primary_loop_edge_set_from_analysis(self):
        g = _graph(["a", "b", "c"],
                   [("a", "b"), ("b", "c"), ("c", "a")])
        analysis = analyze_graph(g)
        prot = primary_loop_edge_set(analysis)
        self.assertEqual(prot, {frozenset(("a", "b")),
                                frozenset(("b", "c")),
                                frozenset(("c", "a"))})

    def test_core_is_planar_probe(self):
        nodes, edges = k5()
        self.assertFalse(core_is_planar(edges))
        self.assertTrue(core_is_planar(edges[:1]))


class TestReinsertionMetrics(unittest.TestCase):
    POS = {"a": (0, 0), "b": (100, 100), "c": (100, 0), "d": (0, 100)}

    def test_proper_crossing_counted(self):
        hits = reinsertion_crossings(
            self.POS, [("a", "b"), ("c", "d")], [("c", "d")])
        self.assertEqual(hits, [(("a", "b"), ("c", "d"))])

    def test_shared_endpoint_exempt(self):
        hits = reinsertion_crossings(
            self.POS, [("a", "b"), ("a", "c")], [("a", "c")])
        self.assertEqual(hits, [])

    def test_kept_kept_pairs_ignored(self):
        hits = reinsertion_crossings(
            self.POS, [("a", "b"), ("c", "d")], [])
        self.assertEqual(hits, [])

    def test_collinear_overlap_not_a_crossing(self):
        pos = {"a": (0, 0), "b": (100, 0), "c": (40, 0), "d": (60, 0)}
        hits = reinsertion_crossings(pos, [("a", "b"), ("c", "d")],
                                     [("c", "d")])
        self.assertEqual(hits, [])

    def test_variant_keys_loop_weight(self):
        hits = [(("a", "b"), ("c", "d"))]
        self.assertEqual(variant_keys(hits, set()),
                         ((1, tuple(hits)), 1))
        a_key, j = variant_keys(hits, {frozenset(("a", "b"))})
        self.assertEqual(j, LOOP_WEIGHT_PRIMARY)
        self.assertEqual(LOOP_WEIGHT_PRIMARY, 2)
        self.assertEqual(LOOP_WEIGHT_OTHER, 1)
        a_key2, j2 = variant_keys(hits, {frozenset(("x", "y"))})
        self.assertEqual(j2, LOOP_WEIGHT_OTHER)


# ------------------------------------------------------- source integration

class TestPlanarizedSource(unittest.TestCase):
    def test_enabled_rule_topology_only(self):
        # non-planar: enabled; planar: disabled (topology rule)
        nodes, edges = k5()
        ctx = _ctx(nodes, edges)
        self.assertTrue(template_enabled("planarized", ctx))
        planar_ctx = _ctx(["a", "b", "c"],
                          [("a", "b"), ("b", "c"), ("c", "a")])
        self.assertFalse(template_enabled("planarized", planar_ctx))

    def test_k5_emission_contract(self):
        nodes, edges = k5()
        ctx = _ctx(nodes, edges)
        cands = generate_from_source("planarized", ctx)
        self.assertTrue(cands)
        seen_ids = []
        for c in cands:
            self.assertEqual(c.source, "planarized")
            self.assertEqual(c.metadata["internal_filter"], "none")
            self.assertEqual(c.metadata["engine"], "planarized-visibility")
            self.assertIn(c.metadata["variant"], ("A", "B"))
            self.assertLessEqual(len(c.metadata["deleted_edges"]), 2)
            self.assertEqual(set(c.node_positions), set(nodes))
            for v, (x, y) in c.node_positions.items():
                self.assertIsInstance(x, int)
                self.assertIsInstance(y, int)
            seen_ids.append(c.candidate_id)
        self.assertEqual(seen_ids, sorted(seen_ids))
        self.assertTrue(all(i.startswith("planarized:") for i in seen_ids))

    def test_k6_not_triggered_is_honest(self):
        nodes, edges = k6()
        ctx = _ctx(nodes, edges)
        with self.assertRaises(SourceUnavailable):
            generate_from_source("planarized", ctx)

    def test_planar_graph_not_triggered(self):
        ctx = _ctx(["a", "b", "c", "d"],
                   [("a", "b"), ("b", "c"), ("c", "d")])
        with self.assertRaises(SourceUnavailable):
            generate_from_source("planarized", ctx)

    def test_double_run_identical_candidate_set(self):
        nodes, edges = k5()
        c1 = [_json({"id": c.candidate_id, "pos": c.node_positions,
                     "meta": c.metadata, "cost": c.generation_cost})
              for c in generate_from_source("planarized", _ctx(nodes, edges))]
        c2 = [_json({"id": c.candidate_id, "pos": c.node_positions,
                     "meta": c.metadata, "cost": c.generation_cost})
              for c in generate_from_source("planarized", _ctx(nodes, edges))]
        self.assertEqual(c1, c2)

    def test_in_source_order(self):
        # preregistered order: templates, planarized, layered incumbent
        self.assertEqual(SOURCE_ORDER[-1], "layered-v082")
        self.assertEqual(SOURCE_ORDER[-2], "planarized")

    def test_zero_scoring_static_lint(self):
        import ast
        path = os.path.join(ROOT, "stdraw", "candidate_planar.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        banned_mods = ("metrics", "check", "certificate", "gates",
                       "candidate_selection", "routing")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(
                        any(b in alias.name for b in banned_mods),
                        f"banned import in candidate_planar: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertFalse(
                    any(b in mod for b in banned_mods),
                    f"banned import in candidate_planar: {mod}")


# ------------------------------------------------------- construction caliber
# (rework: the construction's LayoutConfig must match the evaluation caliber
#  -- ctx.card_h + cfg.min_gap -- so candidates are never STRUCTURALLY
#  eliminated by the stage-1 card-gap gate; the pre-fix reuse of the ortho
#  face defaults produced min_card_gap=12 < 16 on every trigger graph)

class TestConstructionCaliber(unittest.TestCase):
    LONGTAIL = ("longtail-nonplanar-k5.cld", "longtail-nonplanar-k33.cld",
                "longtail-nonplanar-petersen.cld")

    def _corpus_ctx(self, fname):
        with open(os.path.join(LONGTAIL_DIR, fname), encoding="utf-8") as f:
            g = parse(f.read())
        from stdraw.candidate_pipeline import _card_metrics, _dense_hub
        cfg = AutoConfig()
        e = tuple(sorted((x.a, x.b) for x in g.edges))
        widths, heights, card_h = _card_metrics(g, cfg)
        adj = g.adj_undirected()
        hub, _ = _dense_hub(g, adj)
        return SourceContext(graph=g, cfg=cfg, widths=widths,
                             card_h=card_h, edges=e, adj=adj,
                             dense_hub=hub, analysis=analyze_graph(g))

    def test_emitted_candidates_pass_card_gap_gate(self):
        # rect-gap caliber identical to the stage-1 gate: no emitted
        # planarized candidate may be structurally eliminated
        for fname in self.LONGTAIL:
            ctx = self._corpus_ctx(fname)
            min_gap = ctx.cfg.min_gap
            for c in planarized_candidates(ctx):
                pos = c.node_positions
                nodes = sorted(pos)
                gap = None
                for i in range(len(nodes)):
                    for j in range(i + 1, len(nodes)):
                        a, b = nodes[i], nodes[j]
                        gx = (abs(pos[a][0] - pos[b][0])
                              - (ctx.widths[a] + ctx.widths[b]) / 2)
                        gy = abs(pos[a][1] - pos[b][1]) - ctx.card_h
                        g = max(gx, gy)
                        gap = g if gap is None else min(gap, g)
                self.assertGreaterEqual(
                    gap, min_gap - 2,
                    f"{fname} {c.candidate_id}: min_card_gap={gap}")

    def test_dual_variant_split_covered_in_corpus(self):
        # MINOR-4 disposition: at least one acceptance-corpus graph emits a
        # variant B that picks a DIFFERENT construction than its set's A
        # (positions distinct) -- A/B discriminative power is covered
        # in-corpus, not only out-of-corpus.
        ctx = self._corpus_ctx("longtail-nonplanar-petersen.cld")
        cands = planarized_candidates(ctx)
        by_set = {}
        for c in cands:
            by_set.setdefault(c.metadata["deletion_set_index"],
                              []).append(c)
        splits = [lst for lst in by_set.values() if len(lst) == 2
                  and {c.metadata["variant"] for c in lst} == {"A", "B"}
                  and len({json.dumps(c.node_positions, sort_keys=True)
                           for c in lst}) == 2]
        self.assertTrue(splits, "no in-corpus A/B split with distinct "
                                "constructions")


# ------------------------------------------------------- pipeline (L1 scope)

class TestPipelineL1Scope(unittest.TestCase):
    def test_nonplanar_pool_runs_and_guard_floor_is_l1(self):
        nodes, edges = k5()
        g = _graph(nodes, edges, name="k5")
        cfg = AutoConfig()
        v4 = layout(g, cfg, "straight")
        cp = v4["meta"]["candidate_pool"]
        # the pool ran inside the L1 scope
        self.assertIn("planarized",
                      [r["source"] for r in
                       cp["orchestration"]["source_records"]])
        self.assertIn(cp["delivery"]["mode"],
                      ("candidate", "incumbent-fallback"))
        # the delivery floor is still the L1 witness drawing
        self.assertEqual(cp["delivery"]["incumbent_planarization_mode"],
                         "L1")
        # delivery is guard-guarded either way: never worse than the L1
        # incumbent on the delivered certificate tuple
        self.assertIn("incumbent_guard_tuple", cp["delivery"])

    def test_nonplanar_double_run_identical(self):
        nodes, edges = k5()
        g = _graph(nodes, edges, name="k5")
        a = _json(layout(g, AutoConfig(), "straight"))
        b = _json(layout(g, AutoConfig(), "straight"))
        self.assertEqual(a, b)

    def test_planar_graph_pool_unchanged_shape(self):
        g = _graph(["a", "b", "c", "d"],
                   [("a", "b"), ("b", "c"), ("c", "d")], name="path")
        v4 = layout(g, AutoConfig(), "straight")
        cp = v4["meta"]["candidate_pool"]
        rec = {r["source"]: r for r in cp["orchestration"]["source_records"]}
        self.assertEqual(rec["planarized"]["outcome"], "disabled_by_rule")
        # negative protection: no L1 annotation on planar graphs — the
        # delivery provenance carries no new key vs M1-A
        self.assertNotIn("incumbent_planarization_mode", cp["delivery"])


# ------------------------------------------------------- longtail corpus

class TestLongtailCorpus(unittest.TestCase):
    def test_corpus_files_present_and_labelled(self):
        files = sorted(glob.glob(os.path.join(LONGTAIL_DIR, "*.cld")))
        self.assertGreaterEqual(len(files), 12)
        families = {}
        for p in files:
            with open(p, encoding="utf-8") as f:
                head = f.readline()
            self.assertIn("topology family:", head, p)
            fam = head.split("topology family:")[1].split("|")[0].strip()
            families.setdefault(fam, []).append(p)
        for fam, want in (("chain", 3), ("star", 3), ("nonplanar", 3),
                          ("mixed", 3)):
            self.assertEqual(len(families.get(fam, [])), want,
                             f"family {fam}")

    def test_corpus_parses_and_n_cap(self):
        files = sorted(glob.glob(os.path.join(LONGTAIL_DIR, "*.cld")))
        for p in files:
            with open(p, encoding="utf-8") as f:
                g = parse(f.read())
            self.assertLessEqual(len(list(g.node_ids())), 10, p)

    def test_nonplanar_members_actually_nonplanar(self):
        for name in ("longtail-nonplanar-k5.cld", "longtail-nonplanar-k33.cld",
                     "longtail-nonplanar-petersen.cld"):
            with open(os.path.join(LONGTAIL_DIR, name),
                      encoding="utf-8") as f:
                g = parse(f.read())
            e = sorted(tuple(sorted((x.a, x.b))) for x in g.edges)
            self.assertFalse(core_is_planar(e), name)

    def test_planar_members_planar(self):
        files = sorted(glob.glob(os.path.join(LONGTAIL_DIR, "*.cld")))
        for p in files:
            if "nonplanar" in p:
                continue
            with open(p, encoding="utf-8") as f:
                g = parse(f.read())
            e = sorted(tuple(sorted((x.a, x.b))) for x in g.edges)
            self.assertTrue(core_is_planar(e), p)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
