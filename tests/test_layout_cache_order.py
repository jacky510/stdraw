#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Same-process batch order independence + warm-cache rerun determinism.

layout() clears the module-level route/corner caches at entry (their keys
round coordinates to 0.001px -- a lossy map, so a cross-layout cache hit
could alias two different geometries and make batch output depend on the
processing order). These tests pin the guarantee: two different orders
over the same graphs inside one process, and a warm-cache rerun of the
same graph, must produce byte-identical layout payloads. Router-level
caches are instance-scoped (a fresh Router per layout/trial) and cannot
leak across layouts.

Stdlib only (tests the stdraw package in-process, unlike the CLI-level
sweeps in ci_checks.py).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.dsl import parse                    # noqa: E402
from stdraw import visibility                   # noqa: E402
from stdraw.layout_auto import layout           # noqa: E402

G1 = os.path.join(ROOT, "examples", "limits-to-growth.cld")
G2 = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")


def _layout_bytes(path):
    with open(path, encoding="utf-8") as f:
        g = parse(f.read())
    v4 = layout(g)
    return json.dumps(v4, sort_keys=True, ensure_ascii=False).encode("utf-8")


def test_reset_caches_clears_both():
    visibility._ROUTE_CACHE["probe-route"] = "sentinel"
    visibility._CORNER_VIS_CACHE["probe-corner"] = "sentinel"
    visibility.reset_caches()
    assert not visibility._ROUTE_CACHE
    assert not visibility._CORNER_VIS_CACHE


def test_warm_cache_rerun_byte_identical():
    first = _layout_bytes(G1)
    second = _layout_bytes(G1)   # caches are warm now (populated by run 1)
    assert first == second


def test_two_orders_same_process_byte_identical():
    # per-graph comparison: each graph's output must be independent of which
    # graph(s) ran before it in the same process (concatenated payloads would
    # differ by construction -- the two graphs' outputs are different bytes).
    a1 = _layout_bytes(G1)   # G1 runs first (cold caches)
    a2 = _layout_bytes(G2)   # G2 runs after G1
    b2 = _layout_bytes(G2)   # G2 runs first (cold caches)
    b1 = _layout_bytes(G1)   # G1 runs after G2
    assert a1 == b1
    assert a2 == b2
