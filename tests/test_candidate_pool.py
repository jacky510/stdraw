# -*- coding: utf-8 -*-
"""Candidate-pool pipeline tests (M1 minimal loop: contract / structure
analyzer / sources / orchestrator / selection / pipeline wiring).

Scope guards baked in:
  - zero-scoring-power static lint: candidate source modules must not import
    metrics / certificate / gate modules (sources emit, they never judge);
  - orchestrator quality-blindness: it must not import the selection module;
  - negative protection: the auto-v2 recipe output is byte-identical whether
    or not the candidate pipeline ran in the same process;
  - determinism: candidate-v1 library output is byte-identical across runs;
  - failure paths: loop-analysis failure, source construction failure, zero
    candidates, delivery failure, planarized-L1 precedence.
"""
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.candidate_contract import (LayoutCandidate, SCORE_TIE_EPS,
                                       structural_signature,
                                       structural_tiebreak_key,
                                       coordinate_sequence_key)
from stdraw.candidate_orchestrator import Orchestrator, SourceRecord
from stdraw.candidate_pipeline import (_card_metrics, _cert_guard, _dense_hub,
                                       layout)
from stdraw.candidate_selection import (CandidateReport, pareto_and_diversity,
                                        rank_candidates, route_and_evaluate,
                                        heuristic_score)
from stdraw.candidate_sources import (SourceConstructionError,
                                      SourceContext, SourceUnavailable,
                                      SOURCE_ORDER)
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig
from stdraw.model import Edge, Graph, Node
from stdraw.recipes import run as recipes_run
from stdraw.structure_analyzer import (analyze_graph, analyze_loop_structure)

LIMITS = os.path.join(ROOT, "examples", "limits-to-growth.cld")
LONGTAIL = os.path.join(ROOT, "examples", "longtail-coupled-loops.cld")


def _graph(path=LIMITS):
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def _ctx(graph=None, cfg=None):
    from stdraw.candidate_pipeline import _card_metrics, _dense_hub
    from stdraw.structure_analyzer import analyze_graph
    graph = graph or _graph()
    cfg = cfg or AutoConfig()
    edges = tuple(sorted((e.a, e.b) for e in graph.edges))
    widths, heights, card_h = _card_metrics(graph, cfg)
    adj = graph.adj_undirected()
    dense_hub, _ = _dense_hub(graph, adj)
    return SourceContext(graph=graph, cfg=cfg, widths=widths,
                         card_h=card_h, edges=edges, adj=adj,
                         dense_hub=dense_hub,
                         analysis=analyze_graph(graph))


def _cand(cid, positions, source="test"):
    return LayoutCandidate(candidate_id=cid, source=source,
                           node_positions=positions)


def _json(v4):
    return json.dumps(v4, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------- contract

class TestCandidateContract(unittest.TestCase):
    POS = {"a": (24, 48), "b": (240, 48), "c": (240, 216), "d": (24, 216)}

    def test_signature_deterministic(self):
        s1 = structural_signature(self.POS)
        s2 = structural_signature(dict(reversed(list(self.POS.items()))))
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 16)

    def test_signature_distinguishes_forms(self):
        moved = dict(self.POS)
        moved["a"] = (24, 480)          # one quantization cell away
        self.assertNotEqual(structural_signature(self.POS),
                            structural_signature(moved))

    def test_candidate_autosignature(self):
        c = _cand("t:000", self.POS)
        self.assertEqual(c.structural_signature,
                         structural_signature(self.POS))
        d = c.to_dict()
        self.assertEqual(list(d["node_positions"]), ["a", "b", "c", "d"])
        self.assertNotIn("timestamp", json.dumps(d))

    def test_tiebreak_chain(self):
        a = _cand("t:000", self.POS)
        b = _cand("t:001", self.POS)     # same shape, same coords
        # -> signature equal, coords equal, candidate_id decides
        self.assertEqual(a.structural_signature, b.structural_signature)
        self.assertLess(structural_tiebreak_key(a),
                        structural_tiebreak_key(b))
        # different coords, same signature bucket order by coordinate seq
        c = _cand("t:000", {v: (x + 2, y) for v, (x, y) in self.POS.items()})
        self.assertLess(structural_tiebreak_key(a),
                        structural_tiebreak_key(c))
        self.assertEqual(coordinate_sequence_key(a),
                         tuple(self.POS[v] for v in sorted(self.POS)))

    def test_float_never_sole_tiebreaker(self):
        """Chained eps bucketing (MINOR-7 fix): two scores within the
        SCORE_TIE_EPS band land in the SAME bucket even when a floor
        boundary at an integer eps multiple sits between them (the old
        floor(score/eps) form split 0.9999999e-6 / 1.0000001e-6 — a 2e-13
        gap — across bucket 0/1)."""
        import stdraw.candidate_selection as cs

        class _R:
            def __init__(self, s):
                self._s = s

        scores = [0.9999999e-6, 1.0000001e-6, 5e-6]
        with mock.patch.object(cs, "heuristic_score",
                               side_effect=lambda r: r._s):
            buckets = cs._score_buckets([_R(s) for s in scores])
        self.assertEqual(buckets[0.9999999e-6], buckets[1.0000001e-6])
        self.assertNotEqual(buckets[0.9999999e-6], buckets[5e-6])
        # declared band is honored: identical scores are always one bucket
        self.assertEqual(buckets[scores[0]], buckets[scores[0]])


# -------------------------------------------------------- structure model

class TestStructureAnalyzer(unittest.TestCase):
    def test_limits_to_growth_loops(self):
        analysis = analyze_graph(_graph())
        self.assertEqual(analysis.loop_model.status, "ok")
        self.assertGreaterEqual(analysis.loop_count, 3)
        kinds = {lp.kind for lp in analysis.loop_model.loops}
        self.assertIn("R", kinds)
        self.assertIn("B", kinds)
        # three-layer model: exactly one primary tier
        self.assertEqual(analysis.loop_model.primary_loop.tier, "primary")
        primaries = [lp for lp in analysis.loop_model.loops
                     if lp.tier == "primary"]
        self.assertEqual(len(primaries), 1)

    def test_acyclic_graph_no_cycles_is_ok(self):
        g = Graph(name="chain", nodes=[Node(id=v, label=v) for v in "abc"],
                  edges=[Edge(a="a", b="b", polarity="+"),
                         Edge(a="b", b="c", polarity="+")])
        model = analyze_loop_structure(g)
        self.assertEqual(model.status, "no-cycles")
        self.assertEqual(model.loops, [])

    def test_cap_degradation_is_honest(self):
        # K7: far more than MAX_SIMPLE_CYCLES simple cycles -> degraded, and
        # the kept set respects the cap
        from stdraw.structure_analyzer import MAX_SIMPLE_CYCLES
        ids = [f"v{i}" for i in range(7)]
        g = Graph(name="k7", nodes=[Node(id=v, label=v) for v in ids],
                  edges=[Edge(a=ids[i], b=ids[j], polarity="+")
                         for i in range(7) for j in range(i + 1, 7)])
        model = analyze_loop_structure(g)
        self.assertEqual(model.status, "degraded")
        self.assertLessEqual(len(model.loops), MAX_SIMPLE_CYCLES)
        self.assertTrue(model.reason)

    def test_failure_path_reported_not_raised(self):
        class Boom:
            def node_ids(self):
                raise RuntimeError("topology exploded")
        model = analyze_loop_structure(Boom())
        self.assertEqual(model.status, "failed")
        self.assertIn("RuntimeError", model.reason)

    def test_polarity_preserved(self):
        # one negative edge on the triangle -> B loop
        g = Graph(name="tri", nodes=[Node(id=v, label=v) for v in "abc"],
                  edges=[Edge(a="a", b="b", polarity="+"),
                         Edge(a="b", b="c", polarity="+"),
                         Edge(a="c", b="a", polarity="-")])
        model = analyze_loop_structure(g)
        self.assertEqual(len(model.loops), 1)
        self.assertEqual(model.loops[0].kind, "B")
        self.assertEqual(model.loops[0].neg_edges, 1)


# ---------------------------------------------------------------- sources

class TestCandidateSources(unittest.TestCase):
    def test_every_source_yields_or_records_nontrigger(self):
        ctx = _ctx()
        ran = []
        for source in SOURCE_ORDER:
            from stdraw.candidate_sources import generate_from_source
            try:
                cands = generate_from_source(source, ctx, seq=0)
            except SourceUnavailable:
                ran.append((source, "not_triggered"))
                continue
            self.assertEqual(len(cands), 1, source)
            c = cands[0]
            self.assertEqual(set(c.node_positions),
                             set(ctx.graph.node_ids()), source)
            self.assertEqual(c.metadata.get("internal_filter"), "none",
                             "zero-scoring marker must be present")
            ran.append((source, "generated"))
        # the layered incumbent ALWAYS generates (fallback contract)
        self.assertIn(("layered-v082", "generated"), ran)

    def test_construction_failure_recorded(self):
        ctx = _ctx()
        import stdraw.ringlayout as rl
        with mock.patch.object(rl, "place_ring",
                               side_effect=ValueError("boom")):
            from stdraw.candidate_sources import generate_from_source
            with self.assertRaises(SourceConstructionError):
                generate_from_source("ring-cycle", ctx, seq=0)

    def test_zero_scoring_static_lint(self):
        """AST-based import lint: sources must not import metric/certificate
        gate modules (zero scoring power); docstrings may mention them."""
        import ast
        path = os.path.join(ROOT, "stdraw", "candidate_sources.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        banned_mods = ("metrics", "check", "certificate", "gates",
                       "candidate_selection", "routing")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(
                        any(b in alias.name for b in banned_mods),
                        f"banned import in candidate_sources: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertFalse(
                    any(b in mod for b in banned_mods),
                    f"banned import in candidate_sources: {mod}")


# ----------------------------------------------------------- orchestrator

class TestOrchestrator(unittest.TestCase):
    def test_budgets_and_skips(self):
        import stdraw.candidate_orchestrator as co
        ctx = _ctx()
        orch = co.Orchestrator(max_total=2, max_per_source=1)
        fake = [_cand("x:000", {"a": (0, 0)}), _cand("x:001", {"a": (2, 0)})]
        with mock.patch.object(co, "SOURCE_ORDER",
                               ["s1", "s2", "s3"]), \
             mock.patch.object(co, "generate_from_source",
                               return_value=fake):
            result = orch.run(ctx)
        self.assertEqual(len(result.candidates), 2)          # total budget
        outcomes = {r.source: r.outcome for r in result.records}
        self.assertEqual(outcomes["s1"], "generated")
        self.assertEqual(outcomes["s2"], "generated")
        self.assertEqual(outcomes["s3"], "budget_skipped")
        # per-source quota: only 1 of the 2 fakes kept per source
        self.assertTrue(all(r.candidates == 1 for r in result.records
                            if r.outcome == "generated"))
        self.assertTrue(result.exhausted)

    def test_total_budget_clips_batch_no_overrun(self):
        """MINOR-4 fix: a whole source batch may no longer cross the total
        ceiling (max_total=3 with per-source 2 used to keep 4)."""
        import stdraw.candidate_orchestrator as co
        ctx = _ctx()
        orch = co.Orchestrator(max_total=3, max_per_source=2)
        fake = [_cand("x:000", {"a": (0, 0)}), _cand("x:001", {"a": (2, 0)})]
        with mock.patch.object(co, "SOURCE_ORDER",
                               ["s1", "s2", "s3"]), \
             mock.patch.object(co, "generate_from_source",
                               return_value=fake):
            result = orch.run(ctx)
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(result.candidates[-1].candidate_id, "x:000")
        by_source = {r.source: r for r in result.records}
        self.assertEqual(by_source["s1"].candidates, 2)
        self.assertEqual(by_source["s2"].candidates, 1)
        self.assertIn("clipped by the total budget",
                      by_source["s2"].detail)
        self.assertEqual(by_source["s3"].outcome, "budget_skipped")

    def test_failure_path_continues(self):
        import stdraw.candidate_orchestrator as co
        ctx = _ctx()
        orch = co.Orchestrator()
        calls = []

        def gen(source, ctx, seq=0):
            calls.append(source)
            if source == "ring-cycle":
                raise SourceConstructionError("construction exploded")
            return [_cand(f"{source}:000", {"a": (0, 0)})]
        with mock.patch.object(co, "SOURCE_ORDER",
                               ["ring-cycle", "symmetric", "layered-v082"]), \
             mock.patch.object(co, "generate_from_source", side_effect=gen):
            result = orch.run(ctx)
        outcomes = {r.source: (r.outcome, r.detail) for r in result.records}
        self.assertEqual(outcomes["ring-cycle"][0], "failed")
        self.assertIn("construction exploded", outcomes["ring-cycle"][1])
        # the other sources still ran (failure is per-source, never fatal)
        self.assertEqual(outcomes["symmetric"][0], "generated")
        self.assertEqual(outcomes["layered-v082"][0], "generated")
        self.assertEqual(calls, ["ring-cycle", "symmetric", "layered-v082"])

    def test_quality_blindness_static_lint(self):
        with open(os.path.join(ROOT, "stdraw", "candidate_orchestrator.py"),
                  encoding="utf-8") as f:
            src = f.read()
        for banned in ("candidate_selection", "Router", "crossing",
                       "heuristic_score"):
            self.assertNotIn(banned, src,
                             "orchestrator must stay quality-blind")

    def test_loop_analysis_failure_disarms_ring_source(self):
        ctx = _ctx()
        ctx.analysis.loop_model.status = "failed"
        ctx.analysis.loop_model.loops = []
        from stdraw.candidate_sources import template_enabled
        self.assertFalse(template_enabled("ring-cycle", ctx))
        self.assertTrue(template_enabled("layered-v082", ctx))
        self.assertTrue(template_enabled("symmetric", ctx))


# -------------------------------------------------------------- selection

class TestSelection(unittest.TestCase):
    def test_hard_filter_flags_card_gap_violation(self):
        ctx = _ctx()
        overlapping = _cand("bad:000", {v: (24, 24) for v in
                                        ctx.graph.node_ids()})
        reports = route_and_evaluate([overlapping], ctx, op_budget=10_000)
        self.assertFalse(reports[0].hard_pass)
        self.assertIn("card_gap_lt_16", reports[0].hard_failures)

    def test_rank_deterministic_under_input_shuffle(self):
        ctx = _ctx()
        c1 = _cand("z:000", {v: (24 + i * 160, 48) for i, v in
                             enumerate(sorted(ctx.graph.node_ids()))})
        c2 = _cand("a:001", {v: (48 + i * 160, 96) for i, v in
                             enumerate(sorted(ctx.graph.node_ids()))})
        reports = route_and_evaluate([c1, c2], ctx)
        r1 = rank_candidates(reports)
        r2 = rank_candidates(list(reversed(reports)))
        self.assertEqual([r.cand.candidate_id for r in r1],
                         [r.cand.candidate_id for r in r2])

    def test_diversity_beats_cross_group_domination(self):
        """MINOR-3 fix: a metric-dominant candidate from one structural
        group may not eliminate a different structural form — grouping by
        signature precedes the Pareto sweep, so every form keeps its
        representative."""
        good = CandidateReport(cand=_cand("a:000", {"a": (0, 0)}))
        worse_form = CandidateReport(cand=_cand("b:000", {"a": (240, 240)}))
        for r, cv, co in ((good, 0.1, 0.1), (worse_form, 0.5, 0.5)):
            r.routed, r.hard_pass = True, True
            r.crossings, r.press_count = 0, 0
            r.edge_length_cv, r.center_offset_norm = cv, co
        worse_form.crossings = 4          # dominated everywhere beyond eps
        kept = pareto_and_diversity([good, worse_form])
        sigs = {r.cand.structural_signature for r in kept}
        self.assertEqual(len(sigs), 2)    # both forms survive
        self.assertEqual({r.cand.candidate_id for r in kept},
                         {"a:000", "b:000"})

    def test_diversity_keeps_representatives_per_signature(self):
        r1 = CandidateReport(cand=_cand("a:000", {"a": (0, 0)}))
        r2 = CandidateReport(cand=_cand("a:001", {"a": (2, 0)}))
        r3 = CandidateReport(cand=_cand("b:000", {"a": (240, 0)}))
        for r in (r1, r2, r3):
            r.routed, r.hard_pass = True, True
            r.crossings, r.press_count = 0, 0
            r.edge_length_cv, r.center_offset_norm = 0.3, 0.1
        r2.edge_length_cv = 0.31        # near-duplicate of r1 (same sig)
        kept = pareto_and_diversity([r1, r2, r3])
        sigs = {r.cand.structural_signature for r in kept}
        self.assertEqual(len(sigs), 2)   # both structural forms survive
        self.assertNotIn(r2.cand.candidate_id,
                         {r.cand.candidate_id for r in kept})
        # the group-best of the near-duplicate pair wins deterministically
        best = next(r for r in kept
                    if r.cand.structural_signature
                    == r1.cand.structural_signature)
        self.assertEqual(best.cand.candidate_id, r1.cand.candidate_id)

    def test_operation_budget_exhaustion_honest(self):
        ctx = _ctx()
        cands = [_cand(f"s{i}:000",
                       {v: (24 + i * 8 + j * 160, 48) for j, v in
                        enumerate(sorted(ctx.graph.node_ids()))})
                 for i in range(4)]
        reports = route_and_evaluate(cands, ctx, op_budget=2 * len(ctx.edges))
        routed = [r for r in reports if r.routed]
        skipped = [r for r in reports if r.budget_exhausted]
        self.assertEqual(len(routed), 2)
        self.assertEqual(len(skipped), 2)
        self.assertTrue(all(not r.hard_pass is None for r in routed))

    def test_heuristic_score_preregistered_weights(self):
        rep = CandidateReport(cand=_cand("x:000", {"a": (0, 0)}))
        rep.crossings, rep.edge_length_cv, rep.center_offset_norm = 0, 0, 0
        self.assertEqual(heuristic_score(rep), 0.0)


# --------------------------------------------------------------- pipeline

class TestPipeline(unittest.TestCase):
    def test_end_to_end_provenance_and_contract_keys(self):
        v4 = layout(_graph(), AutoConfig(), "straight")
        meta = v4["meta"]
        self.assertEqual(meta.get("recipe_requested"), "candidate-v1")
        self.assertEqual(meta.get("recipe"), "auto-v2")   # caliber key intact
        cp = meta["candidate_pool"]
        self.assertIn("analysis", cp)
        self.assertIn("orchestration", cp)
        self.assertIn("selection", cp)
        # MINOR-2 fix: a candidate delivery that is not-worse only on the
        # hard triple but worse on soft certificate metrics (limits-to-growth
        # CV / card gap) now honestly falls back to the incumbent
        self.assertIn(cp["delivery"]["mode"],
                      ("candidate", "incumbent-fallback"))
        self.assertEqual(cp["candidate_contract_keys"],
                         ["candidate_id", "source", "node_positions",
                          "metadata", "generation_cost",
                          "structural_signature"])
        sel = cp["selection"]
        self.assertIsInstance(sel["op_budget"], dict)   # MINOR-4: backfilled
        self.assertGreater(sel["op_budget"]["total"], 0)
        self.assertGreaterEqual(sel["op_budget"]["consumed"], 0)
        self.assertGreaterEqual(sel["evaluated"], 2)
        self.assertGreaterEqual(sel["hard_pass"], 1)
        blob = json.dumps(cp, sort_keys=True)
        self.assertNotIn("timestamp", blob)
        self.assertNotIn(os.getcwd(), blob)

    def test_double_run_byte_identical(self):
        v4a = layout(_graph(), AutoConfig(), "straight")
        v4b = layout(_graph(), AutoConfig(), "straight")
        self.assertEqual(_json(v4a), _json(v4b))

    def test_negative_protection_auto_untouched_in_process(self):
        g = _graph()
        before = _json(recipes_run("auto-v2", g, AutoConfig(), "straight"))
        layout(g, AutoConfig(), "straight")           # candidate pipeline runs
        after = _json(recipes_run("auto-v2", g, AutoConfig(), "straight"))
        self.assertEqual(before, after)

    def test_zero_candidates_falls_back_to_incumbent(self):
        import stdraw.candidate_pipeline as cp_mod
        g = _graph()
        incumbent = recipes_run("auto-v2", g, AutoConfig(), "straight")
        with mock.patch.object(cp_mod, "Orchestrator") as fake_cls:
            fake_cls.return_value.run.return_value = mock.Mock(
                candidates=[], records=[], budget_total=12,
                budget_per_source=2, exhausted=False,
                to_dict=lambda: {})
            v4 = cp_mod.layout(g, AutoConfig(), "straight")
        cp = v4["meta"]["candidate_pool"]
        self.assertEqual(cp["delivery"]["mode"], "incumbent-fallback")
        self.assertIn("no candidate", cp["delivery"]["reason"])
        # fallback delivery IS the incumbent output (coordinates identical)
        strip = lambda d: _json({k: v for k, v in d.items() if k != "meta"})
        self.assertEqual(strip(v4), strip(incumbent))

    def test_all_delivery_failures_fall_back_to_incumbent(self):
        import stdraw.candidate_pipeline as cp_mod
        g = _graph()
        with mock.patch.object(cp_mod, "_auto_layout",
                               side_effect=RuntimeError("delivery blew up")):
            v4 = cp_mod.layout(g, AutoConfig(), "straight")
        cp = v4["meta"]["candidate_pool"]
        self.assertEqual(cp["delivery"]["mode"], "incumbent-fallback")
        self.assertIn("raised an error", cp["delivery"]["reason"])

    def test_guard_uses_delivered_certificate_caliber(self):
        """MAJOR-1/MINOR-1 acceptance: the guard compares DELIVERED
        certificate metrics, and the recorded guard values are exactly what
        the delivered certificate reports (the consistency assertion)."""
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = _graph()
        cfg = AutoConfig()
        v4 = layout(g, cfg, "straight")
        cp = v4["meta"]["candidate_pool"]
        self.assertEqual(cp["delivery"]["guard_caliber"],
                         "delivered-certificate-metrics")
        cert = certificate_auto(scene_from_auto(v4))
        m = cert["metrics"]
        if cp["delivery"]["mode"] == "candidate":
            delivered = cp["delivery"]["delivered_metrics"]
        else:
            # fallback: the delivered artifact IS the incumbent; the recorded
            # incumbent metrics must match the delivered certificate
            incumbent = recipes_run("auto-v2", g, cfg, "straight")
            m = certificate_auto(scene_from_auto(incumbent))["metrics"]
            delivered = cp["delivery"]["incumbent_delivered_metrics"]
        self.assertEqual(delivered["crossings"], m["crossings"])
        self.assertEqual(delivered["box_press_1px"], m["box_press_1px"])
        self.assertEqual(delivered["spacing_cv"], m["spacing_cv"])
        # incumbent side: its guard tuple derives from the same certificate
        # caliber (NOT a Router proxy) — guard crossings == cert crossings
        incumbent = recipes_run("auto-v2", g, cfg, "straight")
        inc_tup, inc_mets = _cert_guard(incumbent, cfg)
        self.assertEqual(inc_mets["crossings"],
                         certificate_auto(
                             scene_from_auto(incumbent))["metrics"]["crossings"])
        self.assertEqual(cp["delivery"]["incumbent_guard_tuple"],
                         list(inc_tup))

    def test_guard_rejects_worse_delivery(self):
        """A candidate whose DELIVERED metrics regress on any guard component
        is rejected and the untouched incumbent is delivered (the i04
        pathology: proxy tie -> delivered-worse can no longer happen)."""
        import stdraw.candidate_pipeline as cp_mod
        g = _graph()
        cfg = AutoConfig()
        incumbent = recipes_run("auto-v2", g, cfg, "straight")
        inc_tup, inc_mets = _cert_guard(incumbent, cfg)
        calls = {"n": 0}

        def fake_guard(v4, cfg_):
            calls["n"] += 1
            if calls["n"] == 1:
                return inc_tup, inc_mets          # incumbent side
            worse = (inc_tup[0], inc_tup[1], inc_tup[2], inc_tup[3],
                     inc_tup[4], inc_tup[5], inc_tup[6], inc_tup[7],
                     inc_tup[8], inc_tup[9] + 99, inc_tup[10],
                     inc_tup[11], inc_tup[12])
            return worse, inc_mets                # every candidate worse
        with mock.patch.object(cp_mod, "_cert_guard",
                               side_effect=fake_guard):
            v4 = cp_mod.layout(g, cfg, "straight")
        cp = v4["meta"]["candidate_pool"]
        self.assertEqual(cp["delivery"]["mode"], "incumbent-fallback")
        self.assertIn("not-worse guard", cp["delivery"]["reason"])
        strip = lambda d: _json({k: v for k, v in d.items() if k != "meta"})
        self.assertEqual(strip(v4), strip(incumbent))

    def test_hard_filter_rejection_reason_is_honest(self):
        """MINOR-5 fix: Stage-1 rejections must not be reported as budget
        exhaustion."""
        import stdraw.candidate_pipeline as cp_mod
        g = _graph()
        real = cp_mod.route_and_evaluate

        def all_rejected(candidates, ctx, op_budget=None):
            reports = real(candidates, ctx, op_budget=10_000)
            for r in reports:
                r.hard_pass = False
                r.hard_failures = ["box_press_nonzero"]
            return reports
        with mock.patch.object(cp_mod, "route_and_evaluate",
                               side_effect=all_rejected):
            v4 = cp_mod.layout(g, AutoConfig(), "straight")
        reason = v4["meta"]["candidate_pool"]["delivery"]["reason"]
        self.assertEqual(reason, "no candidate survived the Stage-1 hard filter")

    def test_planarized_l1_scope_pool_runs_with_l1_floor(self):
        """M1-B: the L1 short-circuit is retired — the candidate pool now
        runs inside the L1 planarization scope, with the L1 witness drawing
        as the delivery floor (the not-worse guard's incumbent side)."""
        import stdraw.candidate_pipeline as cp_mod
        nodes = [f"v{i}" for i in range(5)]
        edges = [(nodes[i], nodes[j]) for i in range(5)
                 for j in range(i + 1, 5)]
        g = Graph(name="k5", nodes=[Node(id=v, label=v) for v in nodes],
                  edges=[Edge(a=a, b=b, polarity="+") for a, b in edges])
        v4 = cp_mod.layout(g, AutoConfig(), "straight")
        cp = v4["meta"]["candidate_pool"]
        self.assertEqual(cp["delivery"]["incumbent_planarization_mode"],
                         "L1")
        self.assertIn(cp["delivery"]["mode"],
                      ("candidate", "incumbent-fallback"))
        self.assertNotIn("planarized-l1-incumbent",
                         cp["delivery"]["mode"])

    def test_manual_passthrough_keeps_user_intent(self):
        g = _graph()
        nodes = sorted(g.node_ids())
        manual = {"nodes": {v: {"x": 100 + i * 160, "y": 100} for i, v in
                            enumerate(nodes)}, "source": "user"}
        v4 = layout(g, AutoConfig(), "straight", manual=manual)
        self.assertNotIn("candidate_pool", v4["meta"])
        self.assertEqual(v4["meta"]["position_engine"], "manual")


class TestLongTailSmoke(unittest.TestCase):
    """M1 acceptance: on the layered-fallback long-tail topology the
    candidate pipeline is not worse than the v0.8.2 incumbent path."""

    def test_not_worse_than_incumbent(self):
        g = _graph(LONGTAIL)
        cfg = AutoConfig()
        from stdraw.metrics import certificate_auto, scene_from_auto
        auto = recipes_run("auto-v2", g, cfg, "straight")
        cand = recipes_run("candidate-v1", g, cfg, "straight")
        cert_auto = certificate_auto(scene_from_auto(auto), graph_name="lt",
                                     layer="2D", graph=g)
        cert_cand = certificate_auto(scene_from_auto(cand), graph_name="lt",
                                     layer="2D", graph=g)
        self.assertLessEqual(cert_cand["metrics"]["crossings"],
                             cert_auto["metrics"]["crossings"])
        self.assertLessEqual(cert_cand["metrics"]["box_press_1px"],
                             cert_auto["metrics"]["box_press_1px"])
        cp = cand["meta"]["candidate_pool"]
        self.assertIn(cp["delivery"]["mode"], ("candidate",
                                               "incumbent-fallback"))
        # the not-worse guard tuple: candidate never regresses on the tuple
        tup_cand = _cert_guard(cand, cfg)[0]
        tup_auto = _cert_guard(auto, cfg)[0]
        self.assertLessEqual(tup_cand, tup_auto)

    def test_longtail_double_run_identical(self):
        g = _graph(LONGTAIL)
        v4a = recipes_run("candidate-v1", g, AutoConfig(), "straight")
        v4b = recipes_run("candidate-v1", g, AutoConfig(), "straight")
        self.assertEqual(_json(v4a), _json(v4b))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
