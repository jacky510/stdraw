# -*- coding: utf-8 -*-
"""M0-gate + anchor-similarity ranking (anchors-as-prior S3).

Guards baked in:
  - the M0 gate is RELATIVE and paired (epsilon = committed P75 58.6, only
    ever compared within one graph's pool; no absolute threshold);
  - not-evaluable scores are THREE-STATE: never eliminated as 0, never
    sorted as 0;
  - when the committed model cannot be resolved the pipeline degrades to
    the previous ranking caliber with an explicit provenance record (no
    silent swap, no crash);
  - the scorer is numerically pinned to the committed diagnose-collapse
    caliber (one committed negative doc, exact score);
  - a pool fully eliminated by the gate falls back honestly with the
    M0-gate reason in the delivery provenance.
"""
import io
import contextlib
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.candidate_rank_m0 import (NOT_EVALUABLE_SENTINEL,
                                      rank_candidates_m0)
from stdraw.candidate_pipeline import layout as cand_layout, _cert_guard
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig
from stdraw.m0_gate import M0_EPS_P75, load_model, relative_gate, score_doc

LIMITS = os.path.join(ROOT, "examples", "limits-to-growth.cld")
ARMS_RACE = os.path.join(ROOT, "benchmarks", "raw", "aesthetic-v1-negatives",
                         "arms-race.json")


def _json(v4):
    return json.dumps(v4, sort_keys=True, ensure_ascii=False)


class TestRelativeGate(unittest.TestCase):
    def test_eliminates_only_below_epsilon(self):
        scores = {"a": 90.0, "b": 60.0, "c": 20.0, "d": None}
        kept, rec = relative_gate(scores, eps=58.6)
        # d (not evaluable) is never eliminated by the gate
        self.assertEqual(rec["eliminated"], ["c"])
        self.assertIn("d", kept)
        self.assertEqual(rec["pool_best"], 90.0)

    def test_all_not_evaluable_keeps_everything(self):
        kept, rec = relative_gate({"a": None, "b": None}, eps=58.6)
        self.assertEqual(sorted(kept), ["a", "b"])
        self.assertIsNone(rec["pool_best"])
        self.assertIn("no evaluable", rec["note"])

    def test_epsilon_is_the_committed_p75(self):
        self.assertEqual(M0_EPS_P75, 58.6)


class TestScorerParity(unittest.TestCase):
    def test_committed_negative_doc_pinned_score(self):
        """arms-race routes through the family-label caliber; the score is
        pinned to the committed diagnose-collapse reading (41.7)."""
        m0 = load_model()
        self.assertIsNotNone(m0, "committed model + labels must resolve")
        with open(ARMS_RACE, encoding="utf-8") as f:
            doc = json.load(f)
        score, shape = score_doc(doc, "arms-race", m0)
        self.assertEqual((score, shape), (41.7, "ring"))


class TestRankingFallback(unittest.TestCase):
    def test_model_unavailable_degrades_with_record(self):
        from stdraw.candidate_selection import rank_candidates
        from stdraw.candidate_pipeline import (_card_metrics, _dense_hub)
        from stdraw.candidate_sources import SourceContext
        from stdraw.structure_analyzer import analyze_graph
        g = parse(open(LIMITS, encoding="utf-8").read())
        cfg = AutoConfig()
        edges = tuple(sorted((e.a, e.b) for e in g.edges))
        widths, _h, card_h = _card_metrics(g, cfg)
        adj = g.adj_undirected()
        hub, _ = _dense_hub(g, adj)
        ctx = SourceContext(graph=g, cfg=cfg, widths=widths, card_h=card_h,
                            edges=edges, adj=adj, dense_hub=hub,
                            analysis=analyze_graph(g))
        reports = []        # empty shortlist: the record path is what counts
        ranked, record = rank_candidates_m0(reports, ctx, None, None, None)
        self.assertFalse(record["active"])
        self.assertEqual(record["reason"], "model-unavailable")
        self.assertEqual(ranked, [])

    def test_pipeline_records_active_m0_ranking(self):
        g = parse(open(LIMITS, encoding="utf-8").read())
        with contextlib.redirect_stdout(io.StringIO()):
            v4 = cand_layout(g, AutoConfig(), "straight")
        sel = v4["meta"]["candidate_pool"]["selection"]
        rec = sel["m0_ranking"]
        self.assertTrue(rec["active"])
        self.assertEqual(rec["epsilon"], M0_EPS_P75)
        for cid, s in rec["scores"].items():
            self.assertIsNotNone(s, "three-state: only None is three-state")
        # three-state distances recorded (None allowed, never missing)
        self.assertEqual(set(rec["anchor_distances"]),
                         set(rec["scores"]))
        self.assertIn("not_evaluable_note", rec)

    def test_double_run_byte_identical_with_m0(self):
        g = parse(open(LIMITS, encoding="utf-8").read())
        with contextlib.redirect_stdout(io.StringIO()):
            a = cand_layout(g, AutoConfig(), "straight")
            b = cand_layout(g, AutoConfig(), "straight")
        self.assertEqual(_json(a), _json(b))

    def test_full_elimination_falls_back_honestly(self):
        """Every shortlisted candidate below the gate -> incumbent with the
        M0-gate fallback reason (never a crash, never a silent swap)."""
        import stdraw.candidate_rank_m0 as crm
        real = crm.relative_gate

        def elim_all(scores, eps=None):
            kept, rec = real(scores, eps)
            return [], dict(rec, eliminated=sorted(scores))
        g = parse(open(LIMITS, encoding="utf-8").read())
        with mock.patch.object(crm, "relative_gate", side_effect=elim_all):
            with contextlib.redirect_stdout(io.StringIO()):
                v4 = cand_layout(g, AutoConfig(), "straight")
        cp = v4["meta"]["candidate_pool"]
        self.assertEqual(cp["delivery"]["mode"], "incumbent-fallback")
        self.assertEqual(cp["delivery"]["reason"],
                         "every shortlisted candidate was eliminated by "
                         "the M0 gate")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
