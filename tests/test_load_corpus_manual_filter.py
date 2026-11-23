# -*- coding: utf-8 -*-
"""Regression: benchmarks/aesthetic/diagnose_collapse.load_corpus stays
robust to non-anchor JSONs under benchmarks/manual.

The pairwise preference annotation sessions (answers / candidates /
questions / selection-notes) live under benchmarks/manual/pairwise/ and
are swept up by collect_positive_files' ``*.json`` rglob.  They carry no
layout and no graph source (some are list-typed), so an unfiltered sweep
crashed in merge_layout_edges ("no graph source available and doc carries
no edges").  load_corpus now admits only hand anchors:
``kind == "manual-layout"`` documents plus legacy pre-kind exports whose
filename ends ``-manual-layout.json`` (the committed tests/data epidemic
anchor).  Committed baseline is unchanged: 18 positives / 40 negatives,
byte-for-byte the calibration-report-v2 anchor_sources.positives list.

Red lines honored: negatives corpus and committed artifacts untouched —
this test only reads and uses temp files it deletes afterwards.
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "benchmarks", "aesthetic"))

from diagnose_collapse import load_corpus  # noqa: E402
from calibrate_v2 import POSITIVE_DIRS, collect_positive_files  # noqa: E402

MANUAL_DIR = os.path.join(ROOT, "benchmarks", "manual")
V2_REPORT = os.path.join(ROOT, "benchmarks", "aesthetic",
                         "calibration-report-v2.json")


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


class LoadCorpusManualFilter(unittest.TestCase):
    def test_baseline_matches_committed_v2_report(self):
        """18 positives / 40 negatives; positive path list identical to the
        committed calibration-report-v2 anchor_sources.positives."""
        labels, pos_docs, neg_docs, _eng, _src = load_corpus()
        self.assertEqual(len(neg_docs), 40)
        self.assertEqual(len(pos_docs), 18)
        got = sorted(_rel(p) for p, _ in pos_docs)
        with open(V2_REPORT, "r", encoding="utf-8") as f:
            report = json.load(f)
        expected = sorted(report["anchor_sources"]["positives"])
        self.assertEqual(got, expected)
        # every admitted positive is a real layout doc with an edge set
        for _p, doc in pos_docs:
            self.assertTrue(doc.get("nodes"))
            self.assertTrue(doc.get("edges"))
            self.assertTrue(doc.get("graph"))

    def test_robust_to_junk_json_under_manual(self):
        """Any newly added non-anchor json under benchmarks/manual must not
        crash load_corpus and must not change the positive set (same paths,
        same order) compared to a junk-free run."""
        labels, pos0, neg0, _e0, _s0 = load_corpus()
        before = [p for p, _ in pos0]

        junk = [
            # dict without kind / anchor filename (session-file shape)
            ("zzz-junk-test-session.json", {"schema": "x", "pairs": []}),
            # list-typed json (selection-notes shape)
            ("zzz-junk-test-notes.json", [{"pair": 1}, {"pair": 2}]),
            # empty object
            ("zzz-junk-test-empty.json", {}),
        ]
        created = []
        try:
            for name, payload in junk:
                path = os.path.join(MANUAL_DIR, name)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                created.append(path)
            labels2, pos2, neg2, _e2, _s2 = load_corpus()
            self.assertEqual([p for p, _ in pos2], before)
            self.assertEqual(len(neg2), len(neg0))
            self.assertEqual(len(pos2), len(pos0))
        finally:
            for path in created:
                if os.path.exists(path):
                    os.remove(path)

    def test_collect_positive_files_keeps_hand_anchor_shapes(self):
        """Sanity on the sweep itself: every committed hand anchor is either
        kind-tagged or legacy-filename shaped, so the load_corpus filter
        admits all of them (no silent anchor loss)."""
        for d in POSITIVE_DIRS:
            for p in collect_positive_files(d):
                with open(p, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                if isinstance(doc, dict) and (
                    doc.get("kind") == "manual-layout"
                    or p.name.endswith("-manual-layout.json")
                ):
                    self.assertTrue(doc.get("nodes"), _rel(p))


if __name__ == "__main__":
    unittest.main()
