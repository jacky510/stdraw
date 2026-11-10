"""T2 (plan A) regression: waypoint/free edge endpoints land on the standard
anchor set.

Caliber: a manual waypoint/free edge delivers endpoints = the nearest member
of the owning box's 16-anchor set (anchors.py) toward the first/last fold
point; when another edge holds that anchor, anchor_snap's give-way ladder
moves the waypoint endpoint along the same 16-set (nearest feasible). The JS
preview mirrors the rule via stdAnchorToward (nearest anchor not already
held by another edge's endpoint). Before this caliber, waypoint-kind edges
delivered border-point endpoints (3px outside the inset anchor rectangle),
so the certificate anchors_standard hard gate was unconditionally False and
a manually tweaked graph could never grade best.
"""

import json
import math
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import _interactive_js  # noqa: E402
from stdraw.anchors import ANCHOR_INSET, standard_anchors  # noqa: E402
from stdraw.routing import border_point  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")
PY = sys.executable


# ── JS caliber pins (cheap, every run) ──

def test_js_waypoint_endpoint_caliber_present():
    js = _interactive_js._INTERACTIVE_JS
    assert "function stdAnchorToward" in js, "waypoint endpoint snap helper missing"
    assert "function anchorOccupied" in js, "anchor occupancy check missing"
    assert "0.75" in js, "anchor occupancy tolerance must match the certificate gate"
    for site in ("stdAnchorToward(A, wps[0], i)", "stdAnchorToward(B, wps[wps.length - 1], i)",
                 "stdAnchorToward(A, via[0], i)", "stdAnchorToward(B, via[via.length - 1], i)",
                 "stdAnchorToward(nodes[e.a], wps[0], i)",
                 "stdAnchorToward(nodes[e.b], wps[wps.length - 1], i)"):
        assert site in js, f"call site missing: {site}"
    # the old border-facing caliber must be gone from the waypoint/free sites
    for legacy in ("anchor(A, wps[0])", "anchor(B, wps[wps.length - 1])",
                   "anchor(A, via[0])", "anchor(B, via[via.length - 1])"):
        assert legacy not in js, f"legacy border-facing endpoint caliber still present: {legacy}"


def test_python_std_anchor_inset_matches_waypoint_caliber():
    # sanity pin: the 16-set is inset by ANCHOR_INSET (3px), so a border-point
    # endpoint can never be a member -- this is exactly what plan A fixes.
    n = {"x": 400, "y": 300, "w": 96}
    hh = 22.0
    pts16 = standard_anchors(n["x"], n["y"], n["w"] / 2.0, hh)
    bp = border_point(n["x"], n["y"], n["w"] / 2.0, hh, 10.0, -50.0)
    on_border = (math.hypot(max(0.0, abs(bp[0] - n["x"]) - n["w"] / 2.0),
                            max(0.0, abs(bp[1] - n["y"]) - hh)) < 1e-9
                 and (abs(abs(bp[0] - n["x"]) - n["w"] / 2.0) < 1e-9 or
                      abs(abs(bp[1] - n["y"]) - hh) < 1e-9))
    assert on_border
    assert not any(abs(ax - bp[0]) <= 0.75 and abs(ay - bp[1]) <= 0.75
                   for _i, ax, ay in pts16), \
        "border_point must NOT be a 16-set member (inset caliber changed?)"


# ── end-to-end: drag-fold-point export -> --from-layout -> certificate ──

def _auto_layout(tmp_path):
    out = tmp_path / "auto"
    r = subprocess.run([PY, "-m", "stdraw", "layout", EX, "--outdir", str(out),
                        "--skip-3d"], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    return json.load(open(out / "layout.json", encoding="utf-8"))


def _membership(lay, vname, p):
    n = lay["nodes"][vname]
    pts16 = standard_anchors(n["x"], n["y"], n["w"] / 2.0,
                             lay["meta"]["cardH"] / 2.0)
    return [aid for aid, ax, ay in pts16
            if abs(ax - p[0]) <= 0.75 and abs(ay - p[1]) <= 0.75]


@pytest.mark.skipif(not os.path.exists(EX), reason="classic example missing")
def test_waypoints_endpoints_in_standard_anchor_set(tmp_path):
    lay_a = _auto_layout(tmp_path)
    e = next(x for x in lay_a["edges"] if x["route"]["kind"] in ("line", "arc"))
    a, b = e["a"], e["b"]
    na, nb = lay_a["nodes"][a], lay_a["nodes"][b]
    mx, my = (na["x"] + nb["x"]) / 2.0, (na["y"] + nb["y"]) / 2.0
    dx, dy = nb["x"] - na["x"], nb["y"] - na["y"]
    L = math.hypot(dx, dy) or 1.0
    wp = [int(round(mx - dy / L * 40)), int(round(my + dx / L * 40))]
    man = {"viewBox": lay_a["viewBox"],
           "nodes": {v: {"x": q["x"], "y": q["y"]}
                     for v, q in lay_a["nodes"].items()},
           "edges": [{"a": a, "b": b, "waypoints": [wp]}]}
    man_p = tmp_path / "manual.json"
    man_p.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "wp"
    r = subprocess.run([PY, "-m", "stdraw", "layout", EX, "--outdir", str(out),
                        "--skip-3d", "--from-layout", str(man_p)],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    lay = json.load(open(out / "layout.json", encoding="utf-8"))
    cert = json.load(open(out / "certificate.json", encoding="utf-8"))
    e_w = next(x for x in lay["edges"] if (x["a"], x["b"]) == (a, b))
    assert e_w["route"]["kind"] == "waypoints"
    p0, p1 = e_w["route"]["points"][0], e_w["route"]["points"][-1]
    assert _membership(lay, a, p0), f"a-end off the 16-anchor set: {p0}"
    assert _membership(lay, b, p1), f"b-end off the 16-anchor set: {p1}"
    assert cert["gates"]["anchors_standard"] is True
    assert cert["gates"]["anchors_smooth"] is True
    assert cert["grade"] != "uncertified"
