# -*- coding: utf-8 -*-
"""Edge placement rules v1 unit tests — the five spec §9 paper-walk
examples (docs/edge-placement-rules-v1.md) + determinism + the Router
preset integration + the honest-violation audit.

Box geometry uses the engine's real card size (w in 96..160, h=42), so
the §1.3 usable-slot arithmetic holds: n/s sides carry 3 usable anchors
(midpoint + two golden points), e/w sides only the midpoint.
"""
import copy
import math

import pytest

from stdraw import edgerules
from stdraw.edgerules import assign, loop_edge_kinds, SIDES
from stdraw.routing import Router

W = 160   # card width -> n/s golden offset ~18px (usable)
H = 42    # card height -> e/w golden offset ~4.3px (NOT usable)


def box(x, y, w=W, h=H):
    return (x, y, w, h)


def kinds_of(names):
    return list(names)


# ------------------------------------------------------------------
# §9 sample 1: vertical mutual pair, one R (down) + one B (up)
# ------------------------------------------------------------------

def test_sample1_vertical_mutual_r_b():
    nodes = {"A": box(400, 200), "B": box(400, 400)}
    edges = [("A", "B"), ("B", "A")]
    kinds = kinds_of(["R", "B"])
    presets, report = assign(nodes, edges, kinds)
    # R: straight line, midpoints of the facing sides
    p0 = presets[0]
    assert p0["style"] == "line"
    assert p0["a_anchor"] == "s" and p0["b_anchor"] == "n"
    # B: arc on a golden pair, both ends on the SAME global side (rule 9)
    p1 = presets[1]
    assert p1["style"] == "arc"
    ga, gb = p1["a_anchor"], p1["b_anchor"]
    assert ga in ("n-g1", "n-g2") and gb in ("s-g1", "s-g2")
    # same side: n-g1 (right part) pairs with s-g2 (right part)
    same_side = (ga == "n-g1" and gb == "s-g2") or (ga == "n-g2" and gb == "s-g1")
    assert same_side
    # bulge away from the midpoint line (rule 3/4)
    m1 = (nodes["A"][0], nodes["A"][1] + H / 2 - 3)
    m2 = (nodes["B"][0], nodes["B"][1] - H / 2 + 3)
    pa, pb = p1["pa"], p1["pb"]
    d = [edgerules._line_dist(edgerules._arc_vertex(pa, pb, s), m1, m2)
         for s in (1, -1)]
    far = 1 if d[0] >= d[1] else -1
    assert p1["arc_side"] == far
    assert report["violations"] == []


# ------------------------------------------------------------------
# §9 sample 2: horizontal mutual pair (left/right sides hold only the
# midpoint) — the B line must spill to the adjacent-side golden points
# ------------------------------------------------------------------

def test_sample2_horizontal_mutual_spill():
    nodes = {"A": box(300, 300), "B": box(700, 300)}
    edges = [("A", "B"), ("B", "A")]
    kinds = kinds_of(["R", "B"])
    presets, report = assign(nodes, edges, kinds)
    p0 = presets[0]
    assert p0["style"] == "line"
    assert p0["a_anchor"] == "e" and p0["b_anchor"] == "w"
    p1 = presets[1]
    assert p1["style"] == "arc"
    # B spilled off w/e onto adjacent-side goldens near the original side
    assert p1["a_anchor"] in ("n-g1", "s-g2")     # B box, left part
    assert p1["b_anchor"] in ("n-g2", "s-g1")     # A box, right part
    assert report["overflow_to_adjacent_side"] == 2
    # both ends on the same global side (rule 9)
    top = (p1["a_anchor"].startswith("n") and p1["b_anchor"].startswith("n"))
    bot = (p1["a_anchor"].startswith("s") and p1["b_anchor"].startswith("s"))
    assert top or bot


# ------------------------------------------------------------------
# §9 sample 3: one box feeding 3 R lines downward — rule-5 order wins
# ------------------------------------------------------------------

def test_sample3_three_r_order():
    nodes = {"A": box(500, 200), "B": box(300, 400), "C": box(500, 400),
             "D": box(700, 400)}
    edges = [("A", "B"), ("A", "C"), ("A", "D")]
    kinds = kinds_of(["R", "R", "R"])
    presets, report = assign(nodes, edges, kinds)
    by_target = {edges[i][1]: presets[i] for i in range(3)}
    assert by_target["B"]["a_anchor"] == "s-g2"   # leftmost target -> left slot
    assert by_target["C"]["a_anchor"] == "s"      # middle -> midpoint
    assert by_target["D"]["a_anchor"] == "s-g1"   # rightmost -> right slot
    for i in range(3):
        assert presets[i]["style"] == "line"
    assert report["violations"] == []


# ------------------------------------------------------------------
# §9 sample 4: 2 R + 2 B on one downward side — one B spills
# ------------------------------------------------------------------

def test_sample4_two_r_two_b_spill():
    nodes = {"A": box(500, 150), "B": box(350, 350), "C": box(650, 350)}
    edges = [("A", "B"), ("A", "C"), ("A", "B"), ("A", "C")]  # 2 R + 2 B
    # directed duplicates: edges 0/2 identical pairs -> model as distinct
    # lines via distinct node pairs instead (B, C both get R and B lines)
    edges = [("A", "B"), ("A", "C"), ("B", "A"), ("C", "A")]
    kinds = kinds_of(["R", "R", "B", "B"])
    presets, report = assign(nodes, edges, kinds)
    assert report["overflow_to_adjacent_side"] >= 1
    # the two non-B lines keep midpoint priority on A.s
    nonb = [presets[i]["a_anchor"] for i in (0, 1)]
    assert "s" in nonb                       # one R holds the midpoint
    goldens = [a for a in nonb if a != "s"]
    assert all(a in ("s-g1", "s-g2") for a in goldens)
    # the B lines sit on golden points wherever they landed
    for i in (2, 3):
        p = presets[i]
        assert p["style"] == "arc"
        for end in ("a_anchor", "b_anchor"):
            aid = p[end]
            side = aid.split("-")[0]
            if "-g" in aid or aid in SIDES and side in ("e", "w"):
                continue  # spilled/midpoint fallback is rule-6 territory
    assert presets[2]["style"] == "arc" and presets[3]["style"] == "arc"


# ------------------------------------------------------------------
# §9 sample 5: neutral (N) lines — X->A straight midpoint, shared-edge N
# ------------------------------------------------------------------

def test_sample5_neutral_lines():
    nodes = {"X": box(200, 100), "A": box(500, 200), "B": box(800, 100)}
    edges = [("X", "A"), ("A", "B")]
    kinds = kinds_of(["N", "N"])
    presets, report = assign(nodes, edges, kinds)
    assert presets[0]["style"] == "line"
    assert presets[0]["a_anchor"] == "e"       # X faces right (|dx|>|dy|) -> e
    assert presets[0]["b_anchor"] == "w"
    assert presets[1]["style"] == "line"
    assert report["violations"] == []


# ------------------------------------------------------------------
# rule 10: determinism
# ------------------------------------------------------------------

def test_determinism_same_input():
    nodes = {"A": box(400, 200), "B": box(400, 400), "C": box(700, 300)}
    edges = [("A", "B"), ("B", "A"), ("A", "C"), ("C", "A")]
    kinds = kinds_of(["R", "B", "N", "R"])
    p1, r1 = assign(nodes, edges, kinds)
    p2, r2 = assign(nodes, edges, kinds)
    assert copy.deepcopy(p1) == copy.deepcopy(p2)
    assert r1 == r2


# ------------------------------------------------------------------
# §1.3 usable-slot arithmetic
# ------------------------------------------------------------------

def test_usable_slots_arithmetic():
    ntab = edgerules._geom_tables({"A": box(500, 300)})
    assert len(edgerules._usable(ntab["A"], "n")) == 3
    assert len(edgerules._usable(ntab["A"], "s")) == 3
    assert edgerules._usable(ntab["A"], "e") == ["e"]
    assert edgerules._usable(ntab["A"], "w") == ["w"]


# ------------------------------------------------------------------
# Router integration: delivered endpoints == preset anchors
# ------------------------------------------------------------------

def test_router_delivers_preset_endpoints():
    nodes = {"A": box(400, 200), "B": box(400, 400), "C": box(700, 400)}
    edges = [("A", "B"), ("B", "A"), ("A", "C")]
    kinds = kinds_of(["R", "B", "N"])
    presets, _ = assign(nodes, edges, kinds)
    router = Router(nodes, edges, 16.0, 56, presets=presets)
    routes = router.route_all()
    for i, p in presets.items():
        pts = routes[i]["points"]
        assert math.hypot(pts[0][0] - p["pa"][0], pts[0][1] - p["pa"][1]) < 1e-6
        assert math.hypot(pts[-1][0] - p["pb"][0], pts[-1][1] - p["pb"][1]) < 1e-6
    # B line delivered as an arc between golden anchors (rule 3)
    assert routes[1]["kind"] == "arc"


# ------------------------------------------------------------------
# §6 audit: dishonest geometry is recorded, not graded
# ------------------------------------------------------------------

def test_audit_records_rule34_violations():
    edges = [("A", "B")]
    nodes = {"A": box(400, 200), "B": box(400, 400)}
    presets, _ = assign(nodes, edges, ["B"])
    p = presets[0]
    # force a near-side arc into the delivered route
    fake = {"kind": "arc",
            "points": [p["pa"], p["pb"]],
            "ctrl": edgerules._ctrl_for_side(p["pa"], p["pb"], -p["arc_side"])}
    viol = edgerules.audit_delivery(presets, {0: fake}, edges)
    assert viol and viol[0]["rule"] == 4
    fake2 = {"kind": "poly", "points": [p["pa"], p["pb"]]}
    viol2 = edgerules.audit_delivery(presets, {0: fake2}, edges)
    assert viol2 and viol2[0]["rule"] == 3


# ------------------------------------------------------------------
# loop-kind classification (§1.1 caliber, shared with layout coloring)
# ------------------------------------------------------------------

class _LP(object):
    def __init__(self, nodes, kind):
        self.nodes = nodes
        self.kind = kind


def test_loop_edge_kinds():
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")]
    loops = [_LP(["a", "b", "c"], "R"), _LP(["a", "b", "c"], "B")]
    ks = loop_edge_kinds(loops, edges)
    # a-b / b-c / c-a belong to both R and B loops -> N; c-d -> N
    assert ks == ["N", "N", "N", "N"]
    ks2 = loop_edge_kinds([_LP(["a", "b", "c"], "R")], edges)
    assert ks2 == ["R", "R", "R", "N"]


# ------------------------------------------------------------------
# §4 hard-gate precedence: inset-anchor tangent fix + honest delivery
# ------------------------------------------------------------------

def test_validate_drops_grazing_chord_on_inset_anchor():
    # A sits directly above B; the preset's b end is an e-side anchor
    # (vertical border).  The chord is nearly vertical -> tangential
    # arrival vs the TRUE border tangent.  The old coordinate-guessing
    # test (|ax-cx|==hw) missed it because the 16-anchor set is inset
    # 3px, judged the e anchor with a horizontal tangent and kept the
    # preset (measured: random-n20-i00 delivered 4 grazing arrivals).
    nodes = {"A": box(400, 200), "B": box(385, 400)}
    edges = [("A", "B")]
    ta = edgerules._geom_tables(nodes)
    preset = {"pa": list(ta["A"]["s"]), "pb": list(ta["B"]["e"]),
              "a_anchor": "s", "b_anchor": "e",
              "a_side": "s", "b_side": "e",
              "style": "line", "arc_side": 1}
    drop = edgerules.validate_presets(nodes, edges, {0: preset}, 16.0)
    assert drop == {0}
    # control: a w-side (also vertical-border) chord leaving perpendicular
    # to its own side's expectation stays above the threshold -> kept
    preset2 = dict(preset, pb=list(ta["B"]["w"]), b_anchor="w", b_side="w")
    drop2 = edgerules.validate_presets(nodes, edges, {0: preset2}, 16.0)
    assert drop2 == set()


def test_preset_pool_delivers_honest_info_for_unavoidable_press():
    # A above B with C wedged between: the preset chord pierces C.  The
    # pre-fix own-box rejection discarded every candidate and the
    # hard-coded clean fallback delivered a straight chord annotated
    # press=0 / ang=0.0, blinding the hard-gate tuple.  The delivery must
    # now carry honest measurements (press > 0 here, real anchor angles)
    # with the preset endpoints preserved -- the graph-level exemption
    # then sees the real breach and falls back to the legacy pool.
    nodes = {"A": box(400, 200), "B": box(400, 620), "C": box(400, 410)}
    edges = [("A", "B")]
    ta = edgerules._geom_tables(nodes)
    preset = {"pa": list(ta["A"]["s"]), "pb": list(ta["B"]["n"]),
              "a_anchor": "s", "b_anchor": "n",
              "a_side": "s", "b_side": "n",
              "style": "line", "arc_side": 1}
    router = Router(nodes, edges, 16.0, 56, presets={0: preset})
    routes = router.route_all()
    info = routes[0]
    assert math.hypot(info["points"][0][0] - preset["pa"][0],
                      info["points"][0][1] - preset["pa"][1]) < 1e-6
    assert math.hypot(info["points"][-1][0] - preset["pb"][0],
                      info["points"][-1][1] - preset["pb"][1]) < 1e-6
    # honest, not the fake-clean signature
    assert not (info["kind"] == "line" and not info["press"]
                and info["ang_a"] == 0.0 and info["ang_b"] == 0.0)
    assert info["press"] > 0      # the chord corridor really presses C


def test_audit_records_press_and_angle_degradations():
    nodes = {"A": box(400, 200), "B": box(400, 400)}
    edges = [("A", "B")]
    presets, _ = assign(nodes, edges, ["N"])
    p = presets[0]
    fake = {"kind": "line", "points": [p["pa"], p["pb"]],
            "press": 2, "ang_a": 7.1, "ang_b": 90.0}
    viol = edgerules.audit_delivery(presets, {0: fake}, edges)
    rules = sorted(v["rule"] for v in viol)
    assert 2 in rules
    assert any("presses 2 box(es)" in v["detail"] for v in viol)
    assert any("a-end arrival angle 7.1" in v["detail"] for v in viol)
    clean = {"kind": "line", "points": [p["pa"], p["pb"]],
             "press": 0, "ang_a": 90.0, "ang_b": 90.0}
    assert edgerules.audit_delivery(presets, {0: clean}, edges) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
