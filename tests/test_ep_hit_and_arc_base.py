"""Caliber pins for the 2026-11-12 interactive hit-test / arc-base fixes.

jacky's hands-on report: (1) edge endpoint handles hard to grab — root
causes: DOM-order overlap arbitration (later edge wins instead of the
nearer one) + viewBox-unit 9px radius shrinking to ~5-6 screen px under
the max-width:1280px cap; (2) the line jumping while dragging — root
cause: arc ctrl/endpoints translated from a construction-time frozen base
(ctrl0/pa0/pb0) that went stale after any user gesture, so the first
pointermove applied the whole accumulated divergence at once.

Behavioral gates live in tests/probe_interactive.py (CDP real mouse);
this module pins the code calibers cheaply in every pytest run, same
discipline as test_hit_gate.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import _interactive_js  # noqa: E402


def _js():
    return _interactive_js._INTERACTIVE_JS


def test_nearest_wins_arbitration_present():
    js = _js()
    assert "function nearestEpHit(x, y)" in js, "nearestEpHit missing"
    # onDown must arbitrate by distance, not by the event target alone
    assert "var heN = peE ? nearestEpHit(peE.x, peE.y) : null;" in js
    assert ".closest('.stdraw-eps-hit, .stdraw-ep')" in js  # kept as fallback


def test_hit_radius_scale_floor_present():
    js = _js()
    assert "var EP_HIT_MIN_SCREEN = 10;" in js
    assert "function syncEpHitRadius()" in js
    assert "EP_HIT_MIN_SCREEN / scale" in js
    # floored at init and on window resize
    assert "syncEpHitRadius();             // 2026-11-12" in js
    assert "window.addEventListener('resize', syncEpHitRadius);" in js


def test_arc_ctrl_translates_from_live_state_not_frozen_base():
    js = _js()
    # arcEpPts must reference the LIVE ctrl and current endpoints
    body = js[js.index("function arcEpPts"):js.index("function freezeArcBase")]
    assert "e.ctrl0" not in body, \
        "arcEpPts still derives ctrl from the stale frozen base"
    assert "e.arc && e.ctrl && e.pts.length >= 2" in body


def test_finish_ua_designation_uses_live_ctrl_and_from_pt():
    js = _js()
    assert "function finishUaDesignation(i, end, coordEnd, fromPt)" in js
    assert "e.ctrl0" not in js[js.index("function finishUaDesignation"):
                               js.index("function assignAnchor")], \
        "finishUaDesignation still recomputes ctrl from the stale base"


def test_freeze_arc_base_re_syncs_at_every_finalize():
    js = _js()
    assert "function freezeArcBase(e)" in js
    # finalize sites: forcedStraight / forcedArc / release / designation
    for anchor in ("function forcedStraight", "function forcedArc"):
        seg = js[js.index(anchor):js.index(anchor) + 1600]
        assert "freezeArcBase(e)" in seg, f"{anchor} does not re-freeze"
    assert "if (eU.arc) freezeArcBase(eU);" in js, \
        "endpoint release path does not re-freeze the arc base"
