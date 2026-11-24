#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lens-chain placement (auto-v2 structural tier, pure 2-cycle figures).

Coverage:
  1. trigger detection: two 2-node loops sharing a variable + a pendant
     link (the limits-to-growth figure), two disjoint pairs joined by a
     link (success-to-the-successful), a single mutual pair;
  2. negatives not misfired: no mutual pair / a loop of length >= 3 next
     to a pair / a node in three pairs / too many nodes;
  3. layout() integration: engine lens-construct, certificate grade best
     with every gate true, both lenses closed arc rings (bulge floor),
     every endpoint on the 16-anchor set, the pendant link a straight
     segment, rowY = the delivered rows, deterministic two runs;
  4. closed-ring caliber: arc_bulge flattening / same-side detection;
  5. CLI end-to-end: geometry report fail=0, demo carries the honest
     line-style caption.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import lenslayout
from stdraw.anchors import nearest_anchor
from stdraw.check import geometry_report
from stdraw.dsl import parse
from stdraw.gates import LENS_BULGE_MIN, arc_bulge
from stdraw.layout_auto import layout
from stdraw.metrics import certificate_auto, scene_from_auto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "data", "limits-to-growth-4n.cld")
S2S = os.path.join(ROOT, "tests", "golden", "success-to-the-successful.cld")

LTG4 = open(FIXTURE, encoding="utf-8").read()


def _cert(g, name):
    v4 = layout(g)
    return v4, certificate_auto(scene_from_auto(v4), graph_name=name, graph=g)


def _routes(v4):
    return {(e["a"], e["b"]): e["route"] for e in v4["edges"]}


# -- 1. trigger detection --
def test_detect_two_loops_sharing_a_variable():
    plan = lenslayout.detect_lens_chain(parse(LTG4))
    assert plan is not None
    assert plan["pairs"] == [("eff", "perf"), ("perf", "lim")]
    assert plan["chains"] == [[("eff", "perf"), ("perf", "lim")]]
    assert plan["trees"] == {"lim": ["cap"]} and plan["parents"] == {"cap": "lim"}
    assert plan["deg0"] == []


def test_detect_disjoint_pairs_joined_by_a_link():
    plan = lenslayout.detect_lens_chain(
        parse(open(S2S, encoding="utf-8").read()))
    assert plan is not None and len(plan["pairs"]) == 2
    assert len(plan["chains"]) == 2 and len(plan["chains"][0]) == 1


def test_detect_single_pair():
    g = parse('graph "p"\nvar a "A"\nvar b "B"\na -> + b\nb -> + a\n')
    plan = lenslayout.detect_lens_chain(g)
    assert plan is not None and plan["pairs"] == [("a", "b")]


# -- 2. negatives not misfired --
def test_negatives_not_misfired():
    why = {}
    # no mutual pair
    assert lenslayout.detect_lens_chain(parse(
        'graph "chain"\nvar a "A"\nvar b "B"\nvar c "C"\n'
        'a -> + b\nb -> + c\n'), why) is None
    assert "no mutual pair" in why["reason"]
    # a pair plus a 3-loop next to it (a higher structural tier owns it)
    assert lenslayout.detect_lens_chain(parse(
        'graph "pair+triangle"\nvar a "A"\nvar b "B"\nvar c "C"\nvar d "D"\n'
        'a -> + b\nb -> + a\nb -> + c\nc -> + d\nd -> + b\n'), why) is None
    assert "length >= 3" in why["reason"]
    # a node in three mutual pairs (lens fan not templated)
    assert lenslayout.detect_lens_chain(parse(
        'graph "fan"\nvar h "H"\nvar x "X"\nvar y "Y"\nvar z "Z"\n'
        'h -> + x\nx -> + h\nh -> + y\ny -> + h\nh -> + z\nz -> + h\n'),
        why) is None
    assert "more than two" in why["reason"]
    # too many nodes for the structural tier
    lines = ['graph "big"\nvar a "A"\nvar b "B"\na -> + b\nb -> + a\n']
    for i in range(11):
        lines += [f'var p{i} "P{i}"\n', f'a -> + p{i}\n']
    assert lenslayout.detect_lens_chain(parse("".join(lines)), why) is None
    assert "need 2.." in why["reason"]


# -- 3. layout() integration --
def test_ltg4_figure_is_best_on_the_lens_tier():
    g = parse(LTG4)
    v4, cert = _cert(g, "ltg4")
    assert v4["meta"]["position_engine"] == "lens-construct"
    assert v4["meta"]["placement"] == "lens-chain"
    assert cert["placement"] == "lens-chain"
    assert cert["grade"] == "best", cert["gates"]
    assert all(cert["gates"].values()), cert["gates"]
    assert cert["gates_passed"] == "15/15"     # 14 lens-tier gates + loop_labels_clear
    m = cert["metrics"]
    assert m["crossings"] == 0 and m["visual_crossings"] == 0
    assert m["box_press_1px"] == 0 and m["anchor_violations"] == 0
    assert m["anchor_standard_violations"] == 0
    assert m["spacing_cv"] <= 0.35
    # both lenses are closed rings (constructed bulge 0.30 >= the floor)
    assert m["lens_pair_min_bulge"] >= LENS_BULGE_MIN
    assert m["lens_pair_min_sep"] >= 12.0


def test_ltg4_endpoints_on_the_16_anchor_set():
    g = parse(LTG4)
    v4, _ = _cert(g, "ltg4")
    ch = v4["meta"]["cardH"]
    for (a, b), r in _routes(v4).items():
        for end, v in (("a", a), ("b", b)):
            p = v4["nodes"][v]
            px, py = r["points"][0] if end == "a" else r["points"][-1]
            aid, ax, ay = nearest_anchor(p["x"], p["y"], p["w"] / 2.0, ch / 2.0,
                                         px, py)
            assert abs(ax - px) <= 0.1 and abs(ay - py) <= 0.1, (a, b, end, aid)


def test_ltg4_lenses_are_rings_and_the_link_is_straight():
    g = parse(LTG4)
    v4, _ = _cert(g, "ltg4")
    rt = _routes(v4)
    pairs = v4["meta"]["lens"]["pairs"]
    assert pairs == [["eff", "perf", "E"], ["perf", "lim", "S"]]
    for A, B, d in pairs:
        fa, fb = rt[(A, B)], rt[(B, A)]
        assert fa["kind"] == "arc" and fb["kind"] == "arc"
        ra, sa = arc_bulge(fa["points"], fa.get("ctrl"))
        rb, sb = arc_bulge(fb["points"], fb.get("ctrl"), flip=True)
        assert ra >= LENS_BULGE_MIN and rb >= LENS_BULGE_MIN
        assert sa != 0 and sa != sb, "the two arcs must bow to opposite sides"
    link = rt[("cap", "lim")]
    assert link["kind"] == "line" and len(link["points"]) == 2
    assert "ctrl" not in link
    # pendant hangs in the SAME row as its parent (uniform row pitch)
    n = v4["nodes"]
    assert n["cap"]["y"] == n["lim"]["y"]
    rows = sorted({p["y"] for p in n.values()})
    assert len(rows) == 2
    # rowY mirrors the delivered rows (no double shift)
    assert v4["meta"]["rowY"] == rows
    assert v4["meta"]["pitch"] is None


def test_s2s_golden_figure_is_best_on_the_lens_tier():
    g = parse(open(S2S, encoding="utf-8").read())
    v4, cert = _cert(g, "success-to-the-successful")
    assert v4["meta"]["position_engine"] == "lens-construct"
    assert cert["grade"] == "best" and all(cert["gates"].values())
    m = cert["metrics"]
    assert m["spacing_cv"] == 0.0 and m["crossings"] == 0
    assert m["lens_pair_min_bulge"] >= LENS_BULGE_MIN


def test_layout_is_deterministic():
    g = parse(LTG4)
    a = json.dumps(layout(g), sort_keys=True, ensure_ascii=False)
    b = json.dumps(layout(g), sort_keys=True, ensure_ascii=False)
    assert a == b


def test_non_lens_figure_never_takes_the_lens_engine():
    g = parse('graph "tri"\nvar a "A"\nvar b "B"\nvar c "C"\n'
              'a -> + b\nb -> + c\nc -> - a\n')
    v4 = layout(g)
    assert v4["meta"]["placement"] != "lens-chain"
    assert v4["meta"].get("lens") is None


# -- 4. closed-ring caliber --
def test_arc_bulge_floor_and_sides():
    # flattened: ctrl on the chord -> ratio ~0 (not a ring)
    r, s = arc_bulge([(0, 0), (100, 0)], (50, 1))
    assert r < 0.01 and s != 0
    # constructed lens: ctrl offset 0.6 x chord -> apex ratio 0.30; the
    # arc above the chord (negative y) reads side +1
    r, s = arc_bulge([(0, 0), (100, 0)], (50, -60))
    assert abs(r - 0.30) < 1e-9 and s == 1
    # reverse arc (chord runs b -> a) bowing BELOW the chord: measured
    # along the pair direction it reads the opposite side
    r2, s2 = arc_bulge([(100, 0), (0, 0)], (50, 60), flip=True)
    assert abs(r2 - 0.30) < 1e-9 and s2 == -1
    # ... and the same reverse arc bowing above would be the SAME side
    r3, s3 = arc_bulge([(100, 0), (0, 0)], (50, -60), flip=True)
    assert abs(r3 - 0.30) < 1e-9 and s3 == 1
    # sampled polyline without ctrl
    r4, _ = arc_bulge([(0, 0), (50, 20), (100, 0)])
    assert abs(r4 - 0.20) < 1e-9
    # degenerate chord
    assert arc_bulge([(5, 5), (5, 5)], (5, 5)) == (None, 0)


# -- 5. CLI end-to-end --
def test_cli_ltg4_geometry_report_and_demo_caption():
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "-m", "stdraw", "layout", FIXTURE,
                            "--outdir", os.path.join(tmp, "out")],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stderr[-2000:]
        with open(os.path.join(tmp, "out", "geometry_report.json"),
                  encoding="utf-8") as f:
            geo = json.load(f)
        assert geo["fail"] == 0, geo
        text = [c.get("check", "") for c in geo["checks"]]
        assert any("lens-chain placement regularity" in t for t in text)
        with open(os.path.join(tmp, "out", "demo-2d.html"),
                  encoding="utf-8") as f:
            html = f.read()
        assert "lens arcs constructed" in html
        assert geometry_report(layout(parse(LTG4)))["fail"] == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
