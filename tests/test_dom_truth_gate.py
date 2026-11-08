"""Deterministic guards for the v0.7.11 edge-update fix (ref-scrubbed).

2026-11-08 regression: updateEdge/hlEdge/reset resolved the visible edge via
a bare `svg.querySelector('[data-edge=i]')` — document order matches the HIT
path first (#stdraw-hits sits at svg.firstChild and hit paths carry
data-edge), so the visible line never redrew after drags/applyLayout while
internal state re-anchored (silent, zero exceptions). The full behavioral
gates live in tests/probe_dom_truth.py (DOM truth via getPointAtLength);
these pins keep the selector caliber cheaply green in every pytest run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import _interactive_js  # noqa: E402


def _js():
    return _interactive_js._INTERACTIVE_JS


def test_visible_edge_selector_is_type_scoped():
    js = _js()
    # no bare [data-edge=...] svg-wide lookups left (they resolve to the hit
    # path first); visible groups must go through g[data-edge] (visG)
    assert "svg.querySelector('[data-edge=" not in js, \
        "bare [data-edge] selector regressed: resolves to the hit path first"
    assert "svg.querySelector('g[data-edge=" in js


def test_update_edge_uses_visg():
    js = _js()
    assert "var e = edges[i], g = visG(i);" in js
    assert "var h = hitP(i);" in js


def test_per_edge_isolation_helpers_present():
    js = _js()
    for needle in ("function safeRerouteUpdate", "function markDegraded",
                   "function clearDegraded", "stdraw-degraded"):
        assert needle in js, f"missing: {needle}"


def test_fault_injection_hook_present():
    js = _js()
    assert "__stdrawProbeBreakEdge" in js
    assert "_probeThrow" in js
