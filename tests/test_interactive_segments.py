"""Deterministic guard for the segment-drag / floating-bendpoint contract
(ref-scrubbed).

The behavioral gates live in tests/probe_interactive.py (CDP real mouse);
this test pins the shipped JS caliber cheaply in every pytest run:

- MAX_FREE_PTS = 8 (segment-drag re-review: an interior segment drag inserts
  two jog bendpoints per gesture; drawio/bpmn-io set no hard cap at all —
  8 leaves headroom for two segment-drags on one edge while keeping export/
  applyLayout truncation sane; must NOT silently drop back to 3);
- the floating bendpoint preview is preview-only: it must never write user
  state, and it parks at the segment MID (a cursor-following handle would
  intercept every pointerdown and make segment drag unreachable);
- fold-point deletion semantics = drag-back-to-line merge (MERGE_TOL);
- the render hint must advertise the raised cap (max 8), not (max 3).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import _interactive_js  # noqa: E402


def test_segment_drag_and_floating_contract_strings():
    js = _interactive_js._INTERACTIVE_JS
    assert "var MAX_FREE_PTS = 8;" in js, "MAX_FREE_PTS must stay 8 (segment-drag headroom)"
    assert "segDragPlan" in js and "applyUserWps" in js, "segment drag helpers missing"
    assert "adoptFreeAndInsert" in js, "floating-bendpoint conversion missing"
    assert "var MERGE_TOL = 6;" in js, "merge-back deletion tolerance missing"
    assert "stdraw-wp floating" in js, "floating bendpoint CSS missing"
    assert "data-float" in js, "floating handle marker missing"
    assert "hideFloatSoon" not in js or "setInterval" in js  # visibility poll present


def test_floating_handle_is_preview_only_and_mid_parked():
    js = _interactive_js._INTERACTIVE_JS
    # showFloat must park at the segment midpoint, not at the cursor projection
    m = re.search(r"function showFloat\(i, p\) \{(.*?)\n\}", js, re.S)
    assert m, "showFloat missing"
    body = m.group(1)
    assert "sd.proj[0].toFixed(1)" not in body.replace(
        "//", "\n//"), "floating handle must not follow the cursor (intercepts segment drag)"
    assert "(a[0] + b2[0]) / 2" in body, "floating handle must park at the segment mid"


def test_render_hint_advertises_max8():
    import stdraw.render as render
    src = open(render.__file__, encoding="utf-8").read()
    assert "(max 3)" not in src, "stale hint: cap was raised to 8"
    assert "(max 8)" in src, "hint must advertise the raised fold-point cap"
