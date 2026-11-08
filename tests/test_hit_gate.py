"""Deterministic guard for the edge hit-path CSS (ref-scrubbed).

2026-11-08 8777 incident: the .stdraw-hit rule shipped `stroke:transparent`
with `pointer-events:stroke`; Chromium treats an unpainted stroke as
unhittable, so every edge interaction was dead on real machines. The rule
must keep a painted (alpha > 0) stroke; `pointer-events:all` is also
forbidden here because with fill:none the implicit-closed fill polygon of an
open polyline would hit-test its interior and steal empty-canvas clicks.
The full behavioral gates live in tests/probe_interactive.py (elementFromPoint
+ CDP real-mouse); this test pins the CSS caliber cheaply in every pytest run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import _interactive_js  # noqa: E402


def _hit_rule_lines():
    return [ln for ln in _interactive_js._INTERACTIVE_JS.splitlines()
            if "path.stdraw-hit{" in ln]


def test_hit_rule_present_and_single():
    lines = _hit_rule_lines()
    assert len(lines) == 1, f"expected exactly one .stdraw-hit rule: {lines}"


def test_hit_rule_keeps_pointer_events_stroke():
    (line,) = _hit_rule_lines()
    assert "pointer-events:stroke" in line, line


def test_hit_rule_stroke_is_painted_not_transparent():
    (line,) = _hit_rule_lines()
    assert "stroke:transparent" not in line, line
    assert "stroke:rgba(255,255,255,0.01)" in line, line


def test_hit_rule_has_wide_hit_band_and_pointer_cursor():
    (line,) = _hit_rule_lines()
    assert "stroke-width:12" in line and "cursor:pointer" in line, line
