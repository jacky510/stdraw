#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop-direction arc default (CLD drawing quality: loop-member lines are
arcs by default, straight / polyline are scored fallbacks).

Coverage:
  1. loop_arc_sides: preferred bulge points AWAY from the loop centroid
     (union of the declared loops the line belongs to), non-member lines
     and mutual pairs are absent, a loop declared against the edge
     direction still maps to its line, loops shorter than 3 nodes ignored;
  2. Router candidate order inside the scope: loop-side arc (penalty 0)
     -> other-side arc (25) -> straight (30); outside the scope and for
     non-member lines the legacy order / tuple shape is unchanged;
  3. layout() integration: a ring-cycle figure delivers every loop-member
     line as a loop-side arc, layout.json meta + certificate carry the
     honest loop_arcs record, the report item is on, grade stays best,
     deterministic across two runs;
  4. a graph without declared loops and the manual (--from-layout) path
     carry no record (bytes unaffected by the default);
  5. loop_arc_audit: a line delivered straight is reported with a measured
     reason for the preferred arc, template-delivered lines are labelled;
  6. edge placement rules v1 amend: a loop-member R line is preset as an
     arc on the loop side (rule 3 amendment), a non-member R line stays a
     straight line.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import edgerules
from stdraw import routing as R
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw.metrics import certificate_auto, scene_from_auto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RING = os.path.join(ROOT, "tests", "golden", "limits-to-growth.cld")

NO_LOOP = 'graph "noloop"\nvar a "A"\nvar b "B"\nvar c "C"\na -> + b\nb -> + c\n'


def _boxes():
    # a, b on one row, c below the chord a->b (y grows downwards)
    return {"a": (0.0, 0.0, 100.0, 40.0), "b": (200.0, 0.0, 100.0, 40.0),
            "c": (100.0, 140.0, 100.0, 40.0)}


def _loop(*nodes):
    return types.SimpleNamespace(nodes=list(nodes), kind="R", id="R1")


# -- 1. side assignment -------------------------------------------------------
def test_pref_bulges_away_from_loop_centroid():
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    pref = R.loop_arc_sides({"a": (50.0, 20.0), "b": (250.0, 20.0),
                             "c": (150.0, 160.0)}, edges, [_loop("a", "b", "c")])
    assert set(pref) == {0, 1, 2}
    # the loop centroid sits below the a->b chord: the preferred arc ctrl
    # point is on the opposite side (above the chord, y < 20)
    pa, pb = (50.0, 20.0), (250.0, 20.0)
    assert R._bulge_sign(pa, pb, (150.0, 0.0)) == pref[0]
    assert pref[0] != 0


def test_non_member_mutual_and_short_loops_absent():
    edges = [("a", "b"), ("b", "a"), ("b", "c"), ("c", "d")]
    centers = {"a": (50.0, 20.0), "b": (250.0, 20.0), "c": (150.0, 160.0),
               "d": (400.0, 160.0)}
    pref = R.loop_arc_sides(centers, edges,
                            [_loop("a", "b", "c"), _loop("a", "b")])
    # a<->b is a mutual pair (lens contract), d is in no loop
    assert set(pref) == {2}


def test_loop_declared_against_edge_direction_maps_to_the_line():
    edges = [("a", "b"), ("c", "b"), ("c", "a")]
    pref = R.loop_arc_sides({"a": (50.0, 20.0), "b": (250.0, 20.0),
                             "c": (150.0, 160.0)}, edges,
                            [_loop("a", "b", "c")])
    assert set(pref) == {0, 1, 2}


# -- 2. candidate order -------------------------------------------------------
def _router(scope):
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    loops = [_loop("a", "b", "c")] if scope else None
    return R.Router(_boxes(), edges, 16.0, 56.0, loop_arcs=loops), edges


def test_candidate_order_arc_first_then_fallbacks():
    rtr, edges = _router(True)
    assert set(rtr.arc_pref) == {0, 1, 2}
    cands = rtr._candidates("a", "b", 0)
    pref = rtr.arc_pref[0]
    # loop-side arcs: legacy 5-tuples (rule penalty 0); other-side arcs: 25;
    # the straight line: 30 -- per anchor variant the ks ladder alternates
    # sides and the line closes the group
    assert cands[0][0] == "arc" and len(cands[0]) == 5
    assert R._bulge_sign(cands[0][2], cands[0][3], cands[0][4]) == pref
    arcs = [c for c in cands if c[0] == "arc"]
    lines = [c for c in cands if c[0] == "line"]
    assert arcs and lines
    for c in arcs:
        side = R._bulge_sign(c[2], c[3], c[4])
        if side == pref:
            assert len(c) == 5
        else:
            assert side == -pref and c[5] == R.ARC_NEAR_PENALTY
    assert all(c[5] == R.STRAIGHT_FALLBACK_PENALTY for c in lines)
    assert len(lines) * 11 == len(arcs) + len(lines)   # 5 ks x 2 sides + 1 line
    assert R.STRAIGHT_FALLBACK_PENALTY < 40.0      # polyline kind cost


def test_outside_scope_legacy_order_and_shape():
    rtr, edges = _router(False)
    assert rtr.arc_pref == {}
    cands = rtr._candidates("a", "b", 0)
    assert cands[0][0] == "line"
    for c in cands:
        if c[0] in ("line", "arc"):
            # legacy line/arc candidates carry no T10 rule penalty
            assert not (len(c) > 5 and c[5] in (R.ARC_NEAR_PENALTY,
                                                R.STRAIGHT_FALLBACK_PENALTY))
    other, _ = _router(True)
    assert other._candidates("a", "b", 0)[0][0] == "arc"


def test_context_var_feeds_every_router_in_scope():
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    assert R.Router(_boxes(), edges).arc_pref == {}
    with R.loop_arc_context([_loop("a", "b", "c")]):
        assert set(R.Router(_boxes(), edges).arc_pref) == {0, 1, 2}
    assert R.Router(_boxes(), edges).arc_pref == {}


# -- 3. layout integration ----------------------------------------------------
def _ring_layout():
    g = parse(open(RING, encoding="utf-8").read())
    v4 = layout(g)
    return g, v4, certificate_auto(scene_from_auto(v4), graph_name="ring",
                                   graph=g)


def test_ring_cycle_loop_lines_are_arcs_with_record():
    g, v4, cert = _ring_layout()
    rec = v4["meta"]["loop_arcs"]
    assert rec["preferred"] >= 2
    assert rec["arced"] == rec["preferred"]
    assert rec["fallbacks"] == [] and rec["opposite_side_arcs"] == 0
    assert rec["mutual_pair_non_arc"] == 0
    assert cert["grade"] == "best"
    assert cert["loop_arcs"] == rec
    assert cert["reports"]["loop_edges_arced"] is True
    assert "loop_arcs_note" in cert["reports"]
    assert cert["metrics"]["line_kind_counts"].get("line", 0) == 0
    assert cert["metrics"]["line_kind_counts"]["arc"] == len(g.edges)


def test_ring_cycle_deterministic_two_runs():
    _, a, _ = _ring_layout()
    _, b, _ = _ring_layout()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# -- 4. no-loop graph / manual path carry no record ---------------------------
def test_no_loop_graph_has_no_record():
    g = parse(NO_LOOP)
    v4 = layout(g)
    assert "loop_arcs" not in v4["meta"]
    cert = certificate_auto(scene_from_auto(v4), graph_name="noloop", graph=g)
    assert "loop_arcs" not in cert
    assert "loop_edges_arced" not in cert["reports"]


def test_manual_path_is_outside_the_scope():
    g = parse(open(RING, encoding="utf-8").read())
    manual = {"nodes": {"action": [80, 60], "state": [320, 60],
                        "limit": [320, 220]},
              "viewBox": [0, 0, 480, 320], "source": "test"}
    v4 = layout(g, manual=manual)
    assert "loop_arcs" not in v4["meta"]


# -- 5. audit -----------------------------------------------------------------
def test_audit_reports_measured_reason_for_a_straight_delivery():
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    nodes = _boxes()
    rtr = R.Router(nodes, edges, 16.0, 56.0, loop_arcs=[_loop("a", "b", "c")])
    routes = rtr.route_all()
    i = 0
    straight = [c for c in rtr._candidates("a", "b", i) if c[0] == "line"][0]
    routes[i] = {"kind": "line", "points": [list(p) for p in straight[1]],
                 "press": 0, "min_clear": None, "cross": 0,
                 "cross_edges": 0, "ang_a": 0.0, "ang_b": 0.0}
    rec = R.loop_arc_audit(nodes, edges, [_loop("a", "b", "c")], routes,
                           clearance=16.0, pitch=56.0)
    assert rec["preferred"] == 3 and rec["arced"] == 2
    assert rec["opposite_side_arcs"] == 0 and rec["templated"] == 0
    assert len(rec["fallbacks"]) == 1
    fb = rec["fallbacks"][0]
    assert fb["edge"] == "a->b" and fb["delivered"] == "line"
    assert fb["preferred_arc"]                       # a measured string
    assert "straight_line" not in fb                 # line delivery: no detour diagnosis
    templ = R.loop_arc_audit(nodes, edges, [_loop("a", "b", "c")], routes,
                             clearance=16.0, pitch=56.0, templated=[0])
    assert templ["templated"] == 1 and templ["arced"] == 2
    assert len(templ["fallbacks"]) == 1
    assert templ["fallbacks"][0]["delivered"] == "line (mode template)"
    assert "not scored" in templ["fallbacks"][0]["preferred_arc"]


def test_audit_is_none_without_loop_member_lines():
    edges = [("a", "b"), ("b", "a"), ("b", "c")]
    rtr = R.Router(_boxes(), edges, 16.0, 56.0, loop_arcs=[_loop("a", "b")])
    assert rtr.arc_pref == {}
    assert R.loop_arc_audit(_boxes(), edges, [_loop("a", "b")],
                            rtr.route_all()) is None


# -- 7. mutual-pair loop members are accounted for -----------------------------
def test_mutual_pair_non_arc_members_are_listed_in_fallbacks():
    """A loop member of a mutual pair (a <-> b) is outside the arc default's
    scoring scope (its geometry belongs to the lens / rule-8 contract), but
    when it is delivered as a non-arc the record still lists it: every
    non-arc loop-member route of line_kind_counts has a fallback entry."""
    path = os.path.join(os.path.dirname(RING), "growth-and-underinvestment.cld")
    g = parse(open(path, encoding="utf-8").read())
    v4 = layout(g)
    cert = certificate_auto(scene_from_auto(v4), graph_name="gau", graph=g)
    rec = cert["loop_arcs"]
    member_pairs = {(u, v) for lp in g.loops
                    for u, v in zip(lp.nodes, lp.nodes[1:] + lp.nodes[:1])}
    non_arc = sorted("%s->%s" % (e["a"], e["b"]) for e in v4["edges"]
                     if e["route"]["kind"] != "arc"
                     and (e["a"], e["b"]) in member_pairs)
    assert len(non_arc) == 2, non_arc        # a polyline + a straight line
    assert sorted(f["edge"] for f in rec["fallbacks"]) == non_arc
    assert rec["mutual_pair_non_arc"] == len(non_arc)
    assert rec["arced"] == rec["preferred"]          # scoring scope unchanged
    assert rec["opposite_side_arcs"] == 0 and rec["templated"] == 0
    assert all("not scored: mutual pair" in f["preferred_arc"]
               for f in rec["fallbacks"])
    assert {f["delivered"] for f in rec["fallbacks"]} == {"poly", "line"}
    note = cert["reports"]["loop_arcs_note"]
    assert "0 straight/detour fallback" in note
    assert "2 mutual-pair loop member(s) delivered as a non-arc" in note


# -- 6. edge placement rules v1 amend ------------------------------------------
def test_edgerules_presets_loop_member_r_line_as_arc():
    nodes = {"a": (0.0, 0.0, 100.0, 40.0), "b": (200.0, 0.0, 100.0, 40.0),
             "c": (100.0, 140.0, 100.0, 40.0)}
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    loops = [_loop("a", "b", "c")]
    pref = R.loop_arc_sides({v: (p[0], p[1]) for v, p in nodes.items()},
                            edges, loops)
    presets, _ = edgerules.assign(nodes, edges, ["R", "R", "R"], loop_arcs=loops)
    for i in range(3):
        assert presets[i]["style"] == "arc"
        assert presets[i]["arc_side"] == pref[i]
    legacy, _ = edgerules.assign(nodes, edges, ["R", "R", "R"])
    for i in range(3):
        assert legacy[i]["style"] == "line"
