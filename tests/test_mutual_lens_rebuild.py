#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Closed-ring rebuild of mutual pairs on non-lens engines + arrow tips on
the rounded frame (the two legacy drawing defects of the golden set).

Coverage:
  1. anchors.rounded_tip: a corner anchor lands on the r=14 outline along
     the last-segment ray, straight-side tips unchanged, ray-miss fallback
     radial, JS mirror (interactive layer) equal to Python;
  2. delivered arrow tips of the golden graphs never hang outside the
     rounded frame (the 1.56px corner sagitta is gone);
  3. Router.mutual_lens_construct: fixes-that-fail / limits-to-growth /
     growth-and-underinvestment mutual pairs delivered as closed double
     arcs >= 12px apart, certificate gate mutual_pairs_closed True with
     the accounting rows; the lens engine answers N/A (no rebuild pass);
  4. the chord-tilt exemption is accounted (shifting-the-burden ring
     diagonals) and re-measured by the certificate;
  5. column-chain residual order: the member with a spine neighbour takes
     the anchor row (growth-and-underinvestment: performance faces limit,
     route detour <= 1.2, arrow tips of performance->limit and
     capacity->limit >= 8px apart).
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.anchors import rounded_tip, standard_anchors  # noqa: E402
from stdraw.dsl import parse  # noqa: E402
from stdraw.gates import LENS_BULGE_MIN, arc_bulge  # noqa: E402
from stdraw.layout_auto import layout  # noqa: E402
from stdraw.metrics import certificate_auto, scene_from_auto  # noqa: E402
from stdraw.routing import (LENS_PAIR_MIN_SEP, min_pair_dist,  # noqa: E402
                            sample_polyline)
from stdraw.themes import DEFAULT_STATIC_THEME, get as theme_get  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden")
R = float(theme_get(DEFAULT_STATIC_THEME)["card_radius"])
assert R == 14.0


def _golden(name):
    return open(os.path.join(GOLDEN, name + ".cld"), encoding="utf-8").read()


def _run(text, name):
    g = parse(text)
    v4 = layout(g)
    return g, v4, certificate_auto(scene_from_auto(v4), graph_name=name, graph=g)


def _signed_outside(tip, n, hh):
    """Distance of a point from the rounded-rectangle outline; > 0 outside."""
    x, y = tip
    cx, cy, hw = n["x"], n["y"], n["w"] / 2.0
    a = max(abs(x - cx) - (hw - R), 0.0)
    b = max(abs(y - cy) - (hh - R), 0.0)
    return math.hypot(a, b) - R


def _outside_tips(v4):
    hh = v4["meta"].get("cardH", 44) / 2.0
    return [(e["a"], e["b"], round(_signed_outside(e["arrow"], v4["nodes"][e["b"]], hh), 2))
            for e in v4["edges"] if _signed_outside(e["arrow"], v4["nodes"][e["b"]], hh) > 0.05]


def _pair_state(v4, a, b):
    routes = {(e["a"], e["b"]): e["route"] for e in v4["edges"]}
    pa, pb = routes[(a, b)]["points"], routes[(b, a)]["points"]
    ba, sa = arc_bulge(pa, routes[(a, b)].get("ctrl"))
    bb, sb = arc_bulge(pb, routes[(b, a)].get("ctrl"), flip=True)
    sep = min_pair_dist(sample_polyline(pa), sample_polyline(pb))
    return ba, sa, bb, sb, sep


def _polyline_len(pts):
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(pts[:-1], pts[1:]))


# -- 1. rounded_tip geometry --

def test_rounded_tip_corner_anchor_lands_on_outline_along_ray():
    cx, cy, hw, hh = 240.0, 120.0, 48.0, 22.0
    anchors = {aid: (x, y) for aid, x, y in standard_anchors(cx, cy, hw, hh)}
    for aid in ("ne", "nw", "se", "sw"):
        tip = anchors[aid]
        prev = (tip[0] + 30.0, tip[1] - 12.0)       # heading down-left into the corner
        out = rounded_tip(prev, tip, cx, cy, hw, hh, R)
        assert _signed_outside(out, {"x": cx, "y": cy, "w": 2 * hw}, hh) == pytest.approx(0.0, abs=1e-6)
        # on the last-segment ray (the arrowhead keeps its heading); the
        # slide along the ray is bounded by the anchor's offset from the
        # corner centre (sqrt(15.56^2 - 14^2) = 6.8 for the extreme heading)
        ux, uy = tip[0] - prev[0], tip[1] - prev[1]
        cross = (out[0] - prev[0]) * uy - (out[1] - prev[1]) * ux
        ccx = cx + (hw - R) * (1.0 if tip[0] >= cx else -1.0)
        ccy = cy + (hh - R) * (1.0 if tip[1] >= cy else -1.0)
        radial = (out[0] - ccx) * (tip[1] - ccy) - (out[1] - ccy) * (tip[0] - ccx)
        # on the last-segment ray when the ray meets the arc, else radial
        assert abs(cross) < 1e-6 or abs(radial) < 1e-6
        assert math.hypot(out[0] - tip[0], out[1] - tip[1]) <= 7.0
        # the corner anchor itself hangs outside: that is the defect being fixed
        assert _signed_outside(tip, {"x": cx, "y": cy, "w": 2 * hw}, hh) > 1.0


def test_rounded_tip_straight_side_and_degenerate_inputs_unchanged():
    cx, cy, hw, hh = 0.0, 0.0, 48.0, 22.0
    for tip in ((48.0, 0.0), (10.6, 22.0), (-48.0, -8.0), (0.0, -22.0)):
        assert rounded_tip((0.0, 0.0), tip, cx, cy, hw, hh, R) == tip
    corner = (45.0, 19.0)
    assert rounded_tip((0.0, 0.0), corner, cx, cy, hw, hh, 0.0) == corner   # square frame
    assert rounded_tip((0.0, 0.0), corner, cx, cy, 14.0, 10.0, R) == corner  # radius too big
    # ray that misses the arc (heading straight into the card centre from the
    # corner anchor: the arc lies behind) -> radial projection from the corner centre
    out = rounded_tip((90.0, 44.0), corner, cx, cy, hw, hh, R)
    ccx, ccy = hw - R, hh - R
    assert math.hypot(out[0] - ccx, out[1] - ccy) == pytest.approx(R, abs=1e-9)


def _js_mirror():
    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable (interactive-layer mirror check)")
    src = open(os.path.join(ROOT, "stdraw", "_interactive_js.py"), encoding="utf-8").read()
    m = re.search(r"function nHH\(n\).*?\nfunction anchor\(", src, re.S)
    assert m, "roundedTip mirror not found in the interactive layer"
    cases = []
    cx, cy, hw, hh = 240.0, 120.0, 48.0, 22.0
    for aid, x, y in standard_anchors(cx, cy, hw, hh):
        for prev in ((x + 30.0, y - 12.0), (x - 30.0, y + 12.0), (cx + 60.0, cy + 60.0)):
            cases.append({"prev": prev, "tip": [x, y], "py": rounded_tip(prev, (x, y), cx, cy, hw, hh, R)})
    js = ("var nodes={v:{x:%r,y:%r,w:%r,h:%r}}; var CARD_R=%r; var cardH=%r;\n" % (cx, cy, 2 * hw, 2 * hh, R, 2 * hh))
    chunk = m.group(0)
    chunk = chunk[:chunk.rfind("\nfunction anchor(")] + "\n"
    js += chunk
    js += "\nvar out=%s.map(function(c){var t=roundedTip(c.prev,c.tip,'v');return [t[0],t[1]];});console.log(JSON.stringify(out));\n" % json.dumps(cases)
    p = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    return cases, json.loads(p.stdout)


def test_rounded_tip_js_mirror_equals_python():
    if os.environ.get("STDRAW_SKIP_NODE"):
        pytest.skip("STDRAW_SKIP_NODE set")
    cases, out = _js_mirror()
    assert len(out) == len(cases) == 48
    for c, o in zip(cases, out):
        assert o == pytest.approx(c["py"], abs=1e-9)


# -- 2. delivered arrow tips on the golden graphs --

@pytest.mark.parametrize("name", ["fixes-that-fail", "limits-to-growth",
                                  "growth-and-underinvestment", "success-to-the-successful",
                                  "shifting-the-burden"])
def test_golden_arrow_tips_on_the_rounded_frame(name):
    _, v4, cert = _run(_golden(name), name)
    assert _outside_tips(v4) == []
    assert cert["grade"] == "best"


def test_golden_arrow_tips_follow_the_route_end():
    """The tip moves only on corner anchors (the measured golden slide is
    the 1.56px sagitta) and the route end itself is untouched -- the
    certificate caliber reads the route."""
    _, v4, _ = _run(_golden("growth-and-underinvestment"), "g")
    moved = 0
    for e in v4["edges"]:
        end, tip = e["route"]["points"][-1], e["arrow"]
        d = math.hypot(tip[0] - end[0], tip[1] - end[1])
        assert d <= 2.5
        if d > 0.05:
            moved += 1
            assert _signed_outside(end, v4["nodes"][e["b"]], 22.0) > 1.0
    assert moved >= 2


# -- 3. closed-ring rebuild --

@pytest.mark.parametrize("name,pair,closed", [
    ("fixes-that-fail", ("problem", "fix"), 1),
    ("limits-to-growth", ("action", "state"), 1),
    ("growth-and-underinvestment", ("limit", "performance"), 2)])
def test_mutual_pair_delivered_as_closed_lens(name, pair, closed):
    g, v4, cert = _run(_golden(name), name)
    ba, sa, bb, sb, sep = _pair_state(v4, *pair)
    assert ba is not None and bb is not None
    assert ba >= LENS_BULGE_MIN and bb >= LENS_BULGE_MIN
    assert sa != 0 and sa != sb
    assert sep >= LENS_PAIR_MIN_SEP
    assert cert["gates"]["mutual_pairs_closed"] is True
    m = cert["metrics"]
    assert m["mutual_pairs_open"] == []
    assert m["mutual_pairs_closed_count"] == closed
    assert cert["grade"] == "best"
    # the rebuild is accounted in the layout meta
    rows = {frozenset(r["pair"]): r for r in v4["meta"]["mutual_lens"]["pairs"]}
    row = rows[frozenset(pair)]
    assert row["closed"] is True and row["sep"] >= LENS_PAIR_MIN_SEP
    assert row["width_over_chord"] >= 0.2


def test_fixes_that_fail_lens_width_over_chord():
    _, v4, _ = _run(_golden("fixes-that-fail"), "fixes-that-fail")
    routes = {(e["a"], e["b"]): e["route"] for e in v4["edges"]}
    pts = routes[("problem", "fix")]["points"]
    chord = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    row = v4["meta"]["mutual_lens"]["pairs"][0]
    assert frozenset(row["pair"]) == frozenset(("problem", "fix"))
    assert chord == pytest.approx(row["chord"], abs=0.1)
    assert row["sep"] / chord >= 0.2          # acceptance caliber of the card


def test_lens_engine_answers_na_and_runs_no_rebuild():
    _, v4, cert = _run(_golden("success-to-the-successful"), "success-to-the-successful")
    assert v4["meta"]["position_engine"] == "lens-construct"
    assert "mutual_lens" not in v4["meta"]
    assert cert["gates"]["mutual_pairs_closed"] == "N/A"
    assert cert["gates"]["lens_pairs_closed"] is True


# -- 4. chord-tilt exemption accounting --

def test_tilt_exemption_is_accounted_and_remeasured():
    _, v4, cert = _run(_golden("shifting-the-burden"), "shifting-the-burden")
    assert v4["meta"]["position_engine"] == "ring-construct"
    rows = v4["meta"]["mutual_lens"]["pairs"]
    assert [r["status"] for r in rows] == ["tilt", "tilt"]
    assert all(r["chord_tilt_deg"] > 37.4 for r in rows)
    m = cert["metrics"]
    assert m["mutual_pairs_open"] == []
    assert {frozenset(r["pair"]) for r in m["mutual_pairs_exempt"]} == {
        frozenset(r["pair"]) for r in rows}
    assert len(m["mutual_pairs_exempt"]) == 2
    assert all(r["tilt_deg"] > 37.4 for r in m["mutual_pairs_exempt"])
    assert cert["gates"]["mutual_pairs_closed"] is True
    assert cert["grade"] == "best"


def test_gate_fails_when_a_delivered_pair_is_not_closed():
    """Fault injection on the certificate caliber: a pair reported as built
    whose delivered lines are parallel straight lines is an open pair."""
    g, v4, _ = _run(_golden("fixes-that-fail"), "fixes-that-fail")
    scene = scene_from_auto(v4)
    for i, e in enumerate(scene["edges"]):
        if {e["a"], e["b"]} == {"problem", "fix"}:
            pts = scene["polylines"][i]
            scene["polylines"][i] = [pts[0], pts[-1]]
            scene["ctrls"][i] = None
    cert = certificate_auto(scene, graph_name="x", graph=g)
    assert cert["gates"]["mutual_pairs_closed"] is False
    open_rows = cert["metrics"]["mutual_pairs_open"]
    assert len(open_rows) == 1
    assert frozenset(open_rows[0]["pair"]) == frozenset(("problem", "fix"))


# -- 5. column-chain residual order (B1) --

def test_column_residual_with_spine_neighbour_takes_the_anchor_row():
    _, v4, cert = _run(_golden("growth-and-underinvestment"), "growth-and-underinvestment")
    n = v4["nodes"]
    assert v4["meta"]["position_engine"] == "column-construct"
    assert n["performance"]["y"] == n["limit"]["y"]
    routes = {(e["a"], e["b"]): e["route"] for e in v4["edges"]}
    pts = routes[("performance", "limit")]["points"]
    chord = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    assert _polyline_len(pts) / chord <= 1.2
    tips = {(e["a"], e["b"]): e["arrow"] for e in v4["edges"]}
    d = math.hypot(tips[("performance", "limit")][0] - tips[("capacity", "limit")][0],
                   tips[("performance", "limit")][1] - tips[("capacity", "limit")][1])
    assert d >= 8.0
    assert cert["grade"] == "best" and cert["gates"]["visual_crossings_zero"] is True
