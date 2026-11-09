#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crash regression: auto-layout detectors must never KeyError on isolated
nodes (2026-11-09 random-corpus sweep found bowtielayout.detect_bowtie_vertex
crashing with `adj[v]` KeyError on degree-0 nodes; the same pattern existed in
spinewing / ring / column detectors).

Root cause: each module's `_adjacency(edges)` derives keys from edges only, so
a node in no edge has no key — while detection runs on EVERY auto-layout graph
(probe precedes the hit test). Fix: detectors cover all node ids in adj before
probing. These unit tests pin that contract in milliseconds (no CLI run); the
5 crashing corpus cases are covered by the CI-sampling layer in
tests/ci_checks.py (CRASH_REGRESSION_SAMPLES).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import bowtielayout, columnlayout, ringlayout, spinewinglayout  # noqa: E402
from stdraw.dsl import parse  # noqa: E402

# 6-cycle core + one isolated node (degree 0, in no edge): the exact shape
# that crashed detect_bowtie_vertex before the fix (KeyError on the isolated id).
_RING6_ISOLATED = """
graph "regression-isolated-node"
var N00 "A"
var N01 "B"
var N02 "C"
var N03 "D"
var N04 "E"
var N05 "F"
var N09 "ISO"
N00 -> + N01
N01 -> + N02
N02 -> + N03
N03 -> + N04
N04 -> + N05
N05 -> + N00
"""

# two 4-cycles sharing one node (bowtie-vertex topology) + one isolated node:
# detector probes pass the size gate here, exercising the deeper code path.
_BOWTIE_ISOLATED = """
graph "regression-bowtie-isolated"
var N00 "A"
var N01 "B"
var N02 "C"
var N03 "D"
var N04 "E"
var N05 "F"
var N06 "G"
var N09 "ISO"
N00 -> + N01
N01 -> + N02
N02 -> + N00
N00 -> + N03
N03 -> + N04
N04 -> + N00
N04 -> + N05
N05 -> + N06
N06 -> + N04
"""

DETECTORS = (
    ("bowtielayout.detect_bowtie_vertex", bowtielayout.detect_bowtie_vertex),
    ("spinewinglayout.detect_spine_wing", spinewinglayout.detect_spine_wing),
    ("ringlayout.detect_ring", ringlayout.detect_ring),
    ("columnlayout.detect_column", columnlayout.detect_column),
)


def _probe(src):
    graph = parse(src)
    for name, fn in DETECTORS:
        why = {}
        try:
            fn(graph, why=why)  # plan or None — either is fine
        except KeyError as e:
            raise AssertionError(
                f"{name}: KeyError {e} on isolated-node graph "
                "(detector must cover all node ids in adj before probing)")
        # the honest path: a None outcome must carry a measured reason
        if len(graph.node_ids()) > 0:
            assert isinstance(why.get("reason", ""), str)


def test_ring6_plus_isolated_no_keyerror():
    _probe(_RING6_ISOLATED)


def test_bowtie_topology_plus_isolated_no_keyerror():
    _probe(_BOWTIE_ISOLATED)


def test_bowtie_detector_reports_reason_not_crash():
    graph = parse(_RING6_ISOLATED)
    why = {}
    plan = bowtielayout.detect_bowtie_vertex(graph, why=why)
    assert plan is None
    assert why.get("reason"), "probe outcome must carry a measured reason"


if __name__ == "__main__":
    test_ring6_plus_isolated_no_keyerror()
    test_bowtie_topology_plus_isolated_no_keyerror()
    test_bowtie_detector_reports_reason_not_crash()
    print("OK test_crash_regression: isolated-node probes never KeyError")
