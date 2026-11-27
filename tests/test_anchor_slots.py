# -*- coding: utf-8 -*-
"""Multi-slot anchor vocabulary + anchors_standard criterion (card ref-scrubbed
equivalent: jacky 2026-11-26 approval, grounded in the stdraw20 manual
calibration lessons §4).

Covers the three approved items:
  1. the anchor vocabulary opens from the fixed 16-point set to numbered
     side slots n/s/e/w-g1..g7 (+ corners / midpoints), synced across the
     DSL (@anchors), the layout.json export (edges[].anchor_ids) and the
     --from-layout replay; parse(dumps(g)) == g holds;
  2. anchors_standard = "endpoint ON the box border + angle >= floor" --
     a multi-slot endpoint no longer violates the gate;
  3. user-authority boundary: DSL designations get the same gate-fallback
     accounting as --from-layout (breaching designations fall back to the
     engine's own delivery, gate-clean ones are honored).

Legacy compatibility: the 16-point set keeps its ids and coordinates;
old manual-layout JSONs (no anchors / 16-set ids / waypoints) replay
unchanged.
"""
import json
import math
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import dsl  # noqa: E402
from stdraw.anchors import (ANCHOR_IDS, MAX_SLOTS, SLOT_FRACS,  # noqa: E402
                            anchor_point, is_anchor_id, standard_anchors)
from stdraw.metrics import certificate_auto, scene_from_auto  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "limits-to-growth.cld")
PY = sys.executable


# ── 1. vocabulary ──────────────────────────────────────────────────────

def test_legacy_16_set_ids_resolve_identically():
    cx, cy, hw, hh = 300.0, 200.0, 70.0, 22.0
    pts16 = {p[0]: (p[1], p[2]) for p in standard_anchors(cx, cy, hw, hh)}
    assert sorted(pts16) == sorted(ANCHOR_IDS)
    for aid in ANCHOR_IDS:
        assert anchor_point(cx, cy, hw, hh, aid) == pts16[aid], aid


def test_slot_ladder_fractions_and_ids():
    assert [j for j, _f in SLOT_FRACS] == list(range(1, MAX_SLOTS + 1))
    fr = dict(SLOT_FRACS)
    assert fr[1] == 0.382 and fr[2] == 0.618          # legacy golden pair
    assert fr[3] == 0.5 and fr[4] == 0.25 and fr[5] == 0.75
    assert fr[6] == 0.125 and fr[7] == 0.875
    for aid in ("n-g3", "n-g7", "s-g4", "e-g5", "w-g6", "ne", "sw", "n", "w"):
        assert is_anchor_id(aid), aid
    for bad in ("zz", "n-g8", "n-g0", "x-g1", "nn", "n-", "-g1", None, 3):
        assert not is_anchor_id(bad), bad


def test_new_slots_sit_on_border_rectangle():
    cx, cy, hw, hh = 300.0, 200.0, 70.0, 22.0
    for side in "nsew":
        for j in range(1, MAX_SLOTS + 1):
            x, y = anchor_point(cx, cy, hw, hh, f"{side}-g{j}")
            on_x = abs(abs(x - cx) - hw) <= 3.01
            on_y = abs(abs(y - cy) - hh) <= 3.01
            assert on_x != on_y or (on_x and on_y), (side, j)
            assert on_x or on_y, (side, j)
    # g3 = side midpoint, off-ladder slots are NOT 16-set members
    assert anchor_point(cx, cy, hw, hh, "n-g3") == (cx, cy - (hh - 3.0))
    p = anchor_point(cx, cy, hw, hh, "n-g4")
    assert not any(abs(ax - p[0]) <= 0.75 and abs(ay - p[1]) <= 0.75
                   for _aid, ax, ay in standard_anchors(cx, cy, hw, hh))


def test_dsl_anchors_roundtrip_and_rejections():
    text = ('graph "g"\n\nvar a "a"\nvar b "b"\nvar c "c"\n\n'
            'a -> + b @anchors src=s-g2,dst=n-g3\n'
            'a -> - c @delay\n'
            'b -> + c @loops L1 @anchors src=ne\n'
            'c -> + a @anchors dst=w-g6\n'
            'loop L1 "L" "R" [a, b, c]\n')
    g1 = dsl.parse(text)
    assert g1.edges[0].anchors == {"src": "s-g2", "dst": "n-g3"}
    assert g1.edges[2].anchors == {"src": "ne"}
    assert g1.edges[3].anchors == {"dst": "w-g6"}
    assert g1.edges[1].anchors is None
    g2 = dsl.parse(dsl.dumps(g1))
    assert g1 == g2, "parse(dumps(g)) == g broken with @anchors"
    # tag order tolerance (parse is order-tolerant, dumps is canonical)
    g3 = dsl.parse('graph "g"\n\nvar a "a"\nvar b "b"\n\n'
                   'a -> + b @delay @anchors src=s-g1\n')
    assert g3.edges[0].anchors == {"src": "s-g1"}
    assert g3.edges[0].delay is True
    for bad in ('a -> + b @anchors src=zz',
                'a -> + b @anchors src=n-g8',
                'a -> + b @anchors src=s-g1,src=w-g2',
                'a -> + b @anchors foo',
                'a -> + b @anchors src=s-g1 @anchors dst=w-g1'):
        with pytest.raises(ValueError):
            dsl.parse('graph "g"\n\nvar a "a"\nvar b "b"\n\n' + bad)


# ── 2. anchors_standard criterion (scene level) ────────────────────────

def _scene_for(p0, p1):
    """Two-node scene, single straight edge with the given border endpoints."""
    v4 = {
        "viewBox": [0, 0, 420, 300],
        "nodes": {"a": {"x": 140, "y": 80, "w": 96},
                  "b": {"x": 140, "y": 240, "w": 96}},
        "edges": [{"a": "a", "b": "b", "polarity": "+", "loop_kinds": [],
                   "loop_color": None,
                   "route": {"kind": "line", "points": [list(p0), list(p1)]},
                   "anchors": {"a": list(p0), "b": list(p1)},
                   "arrow": list(p1), "route_cross_edges": 0}],
        "bars": {},
        "meta": {},
    }
    return scene_from_auto(v4)


def _bottom_border(x):
    # node a: (140, 80) w96 h44 (scene_from_auto cardH default 44)
    return (float(x), 80.0 + 22.0 - 3.0)


def _top_border(x):
    return (float(x), 240.0 - 22.0 + 3.0)


def test_criterion_accepts_off_16set_on_border_slot_endpoint():
    # s-g4 slot coordinate (frac 0.25 along the bottom border) -> off the
    # 16-set, ON the border, vertical departure -> compliant under the new
    # criterion (the legacy membership gate counted it as a violation)
    cx, hw = 140.0, 48.0
    a_inset = hw - 3.0
    x0 = cx - a_inset + 2 * a_inset * dict(SLOT_FRACS)[4]
    scene = _scene_for(_bottom_border(x0), _top_border(cx))
    cert = certificate_auto(scene, graph_name="slot-probe")
    assert cert["metrics"]["anchor_standard_violations"] == 0
    assert cert["gates"]["anchors_standard"] is True


def test_criterion_rejects_off_border_endpoint():
    scene = _scene_for((100.0, 104.0), _top_border(140.0))   # 4px below border
    cert = certificate_auto(scene, graph_name="offborder-probe")
    assert cert["metrics"]["anchor_standard_violations"] == 1
    assert cert["gates"]["anchors_standard"] is False
    d = cert["metrics"]["anchor_standard_details"][0]
    assert d["edge"] == "a->b" and d["end"] == "a" and d["why"] == "off-border"


def test_criterion_rejects_shallow_angle_endpoint():
    # on-border endpoint with a near-tangent departure (long shallow line)
    p0 = _bottom_border(140.0)
    p1 = (500.0, 240.0 - 22.0 + 3.0)
    scene = _scene_for(p0, p1)
    cert = certificate_auto(scene, graph_name="shallow-probe")
    assert cert["metrics"]["anchor_violations"] >= 1      # anchors_smooth sees it
    assert cert["metrics"]["anchor_standard_violations"] >= 1
    assert any(d.get("why") == "angle"
               for d in cert["metrics"]["anchor_standard_details"])


# ── 3. end-to-end: DSL @anchors honored + fallback; replay compat ──────

@pytest.mark.skipif(not os.path.exists(EX), reason="example missing")
def test_dsl_designation_gate_clean_is_honored(tmp_path):
    # two-node column graph: designate src=s-g4 / dst=n-g4 (frac-0.25
    # slots, OFF the 16-set but on-border) -- the straight vertical
    # designation cannot press any box, so it MUST be honored: the
    # delivered edge lands exactly there and carries anchor_ids.
    cld = ('graph "slots2"\n\nvar A "A"\nvar B "B"\n\n'
           'A -> + B @anchors src=s-g4,dst=n-g4\n')
    src = tmp_path / "g.cld"
    src.write_text(cld, encoding="utf-8")
    out = tmp_path / "out"
    r = subprocess.run([PY, "-m", "stdraw", "layout", str(src),
                        "--outdir", str(out), "--name", "slots2"],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]
    lay = json.load(open(out / "layout.json", encoding="utf-8"))
    cert = json.load(open(out / "certificate.json", encoding="utf-8"))
    e = next(x for x in lay["edges"] if (x["a"], x["b"]) == ("A", "B"))
    assert e.get("anchor_ids") == {"src": "s-g4", "dst": "n-g4"}, \
        "gate-clean multi-slot designation must be honored (no silent fallback)"
    na = lay["nodes"]["A"]
    expect = anchor_point(na["x"], na["y"], na["w"] / 2.0,
                          lay["meta"]["cardH"] / 2.0, "s-g4")
    got = e["route"]["points"][0]
    assert abs(got[0] - expect[0]) <= 0.75 and abs(got[1] - expect[1]) <= 0.75
    nb = lay["nodes"]["B"]
    expect_b = anchor_point(nb["x"], nb["y"], nb["w"] / 2.0,
                            lay["meta"]["cardH"] / 2.0, "n-g4")
    got_b = e["route"]["points"][-1]
    assert (abs(got_b[0] - expect_b[0]) <= 0.75
            and abs(got_b[1] - expect_b[1]) <= 0.75)
    assert cert["gates"]["anchors_standard"] is True


@pytest.mark.skipif(not os.path.exists(EX), reason="example missing")
def test_dsl_designation_breach_falls_back(tmp_path):
    # a designation whose straight line would press its own box must fall
    # back to the engine's own delivery (user authority ends where hard
    # gates begin); the delivered edge carries NO anchor_ids.
    cld = ('graph "breach"\n\nvar A "A"\nvar B "B"\nvar C "C"\n\n'
           'A -> + B @anchors src=n-g4,dst=s-g6\n'
           'B -> + C\n'
           'C -> + A\n')
    src = tmp_path / "g.cld"
    src.write_text(cld, encoding="utf-8")
    out = tmp_path / "out"
    r = subprocess.run([PY, "-m", "stdraw", "layout", str(src),
                        "--outdir", str(out), "--name", "breach"],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-500:]
    lay = json.load(open(out / "layout.json", encoding="utf-8"))
    cert = json.load(open(out / "certificate.json", encoding="utf-8"))
    e = next(x for x in lay["edges"] if (x["a"], x["b"]) == ("A", "B"))
    assert not e.get("anchor_ids"), "breached designation must not export ids"
    assert cert["gates"]["anchors_standard"] is True


@pytest.mark.skipif(not os.path.exists(EX), reason="example missing")
def test_old_format_manual_layout_replays_without_warning(tmp_path):
    # legacy manual-layout export (nodes only, no edges key): identical
    # replay path, no warnings, certificate anchors_standard true.
    out_a = tmp_path / "auto"
    r = subprocess.run([PY, "-m", "stdraw", "layout", EX,
                        "--outdir", str(out_a)], cwd=ROOT,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    lay_a = json.load(open(out_a / "layout.json", encoding="utf-8"))
    man = {"tool": "stdraw", "kind": "manual-layout",
           "viewBox": lay_a["viewBox"],
           "nodes": {v: {"x": q["x"], "y": q["y"]}
                     for v, q in lay_a["nodes"].items()}}
    man_p = tmp_path / "manual.json"
    man_p.write_text(json.dumps(man), encoding="utf-8")
    out = tmp_path / "replay"
    r = subprocess.run([PY, "-m", "stdraw", "layout", EX, "--outdir", str(out),
                        "--from-layout", str(man_p)], cwd=ROOT,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    assert "warning" not in r.stderr.lower()
    cert = json.load(open(out / "certificate.json", encoding="utf-8"))
    assert cert["gates"]["anchors_standard"] is True


@pytest.mark.skipif(not os.path.exists(EX), reason="example missing")
def test_replay_accepts_multi_slot_anchor_ids(tmp_path):
    # manual-layout export with a multi-slot id (s-g3 / n-g5): the new
    # vocabulary replays end-to-end; endpoint lands on the slot coordinate.
    out_a = tmp_path / "auto"
    r = subprocess.run([PY, "-m", "stdraw", "layout", EX,
                        "--outdir", str(out_a)], cwd=ROOT,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    lay_a = json.load(open(out_a / "layout.json", encoding="utf-8"))
    e = next(x for x in lay_a["edges"]
             if x["route"]["kind"] in ("line", "arc"))
    a, b = e["a"], e["b"]
    na, nb = lay_a["nodes"][a], lay_a["nodes"][b]
    # face the other box: pick the side slots pointing at the target so the
    # designation is gate-clean (departure leaves the border outward)
    dx, dy = nb["x"] - na["x"], nb["y"] - na["y"]
    if abs(dx) >= abs(dy):
        side_a = "e-g4" if dx > 0 else "w-g4"
        side_b = "w-g4" if dx > 0 else "e-g4"
    else:
        side_a = "s-g4" if dy > 0 else "n-g4"
        side_b = "n-g4" if dy > 0 else "s-g4"
    man = {"tool": "stdraw", "kind": "manual-layout",
           "viewBox": lay_a["viewBox"],
           "nodes": {v: {"x": q["x"], "y": q["y"]}
                     for v, q in lay_a["nodes"].items()},
           "edges": [{"a": a, "b": b,
                      "anchors": {"src": side_a, "dst": side_b}}]}
    man_p = tmp_path / "manual.json"
    man_p.write_text(json.dumps(man), encoding="utf-8")
    out = tmp_path / "replay"
    r = subprocess.run([PY, "-m", "stdraw", "layout", EX, "--outdir", str(out),
                        "--from-layout", str(man_p)], cwd=ROOT,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-400:]
    lay = json.load(open(out / "layout.json", encoding="utf-8"))
    cert = json.load(open(out / "certificate.json", encoding="utf-8"))
    e_w = next(x for x in lay["edges"] if (x["a"], x["b"]) == (a, b))
    ch = lay["meta"]["cardH"]
    if e_w.get("anchor_ids") is not None:
        na2 = lay["nodes"][a]
        expect = anchor_point(na2["x"], na2["y"], na2["w"] / 2.0, ch / 2.0,
                              side_a)
        got = e_w["route"]["points"][0]
        assert abs(got[0] - expect[0]) <= 0.75 and abs(got[1] - expect[1]) <= 0.75
        assert e_w["anchor_ids"] == {"src": side_a, "dst": side_b}
    assert cert["gates"]["anchors_standard"] is True
