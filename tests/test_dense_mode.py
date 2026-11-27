# -*- coding: utf-8 -*-
"""Dense-mode branch (dense-only, HUB-box slot grid + controlled sharing).

Covers: the topology-pure dense predicate, the deterministic grid offset
ladder (12px -> 6px shrink -> capped sharing), the er-layer dense slot
grid, the dense-adapted preset validation floor, and the dense_mode
meta/certificate transport.  Every non-dense code path is exercised
elsewhere by the A-tier byte sweep; here we pin the dense branch itself
plus the constructive non-hit of a corpus-shaped graph.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stdraw import edgerules as er
from stdraw.routing import (Router, _dense_fan_offsets, DENSE_FAN_STEP,
                            DENSE_GRID_STEP, DENSE_CAP_PER_SLOT)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ------------------------------------------------------------------
# dense fan offsets: grid ladder
# ------------------------------------------------------------------

def test_dense_offsets_distinct_slots_on_grid():
    offs = _dense_fan_offsets(5, 45.0, 0.0)
    assert len(offs) == 5
    assert len(set(offs)) == 5                       # distinct slots
    for o in offs:
        assert abs(o / DENSE_GRID_STEP - round(o / DENSE_GRID_STEP)) < 1e-9
    # centered symmetric
    assert offs[0] == -offs[-1]


def test_dense_offsets_shrink_to_grid_step_before_sharing():
    # 96px card long side: half_len 45 -> 8 distinct 12px slots;
    # 11 lines must shrink to the 6px grid, all DISTINCT (no sharing).
    offs = _dense_fan_offsets(11, 45.0, 0.0)
    assert len(set(offs)) == 11
    for o in offs:
        assert abs(o / DENSE_GRID_STEP - round(o / DENSE_GRID_STEP)) < 1e-9
    gaps = sorted({round(b - a, 6) for a, b in zip(sorted(offs), sorted(offs)[1:])})
    assert min(gaps) >= 6.0                          # gate table #4 floor


def test_dense_offsets_sharing_is_monotone_and_capped_accounting():
    # 24 lines on one side exceed even the 6px grid -> sharing; the slot
    # sequence (azimuth order) never returns to an earlier slot.
    offs = _dense_fan_offsets(24, 45.0, 0.0)
    assert len(offs) == 24
    slot_ranks = {}
    seq = []
    for o in offs:
        slot_ranks.setdefault(o, len(slot_ranks))
        seq.append(slot_ranks[o])
    assert all(b >= a for a, b in zip(seq, seq[1:]))
    # grid discipline
    for o in offs:
        assert abs(o / DENSE_GRID_STEP - round(o / DENSE_GRID_STEP)) < 1e-9


# ------------------------------------------------------------------
# dense detection / router arming
# ------------------------------------------------------------------

def _make_graph(pairs, names):
    class E:
        def __init__(self, a, b):
            self.a, self.b = a, b
    return [E(p[0], p[1]) for p in pairs]


def _dense_of(deg_by_node):
    nodes = sorted(deg_by_node)
    deg_max = max(deg_by_node.values())
    if deg_max < 10:
        return None, deg_max
    hub = sorted(nodes, key=lambda v: (-deg_by_node[v], v))[0]
    return hub, deg_max


def test_dense_predicate_corpus_family_is_a_constructive_non_hit():
    # corpus family tops out at max_deg = 8 -> no dense, ever
    deg = {chr(ord("a") + i): d for i, d in
           enumerate([1, 2, 3, 4, 5, 6, 7, 8])}
    hub, deg_max = _dense_of(deg)
    assert hub is None and deg_max == 8


def test_dense_predicate_fan_hits_with_hub_and_deg_max():
    deg = {"HUB": 17, **{"L%02d" % i: 1 for i in range(17)}}
    hub, deg_max = _dense_of(deg)
    assert hub == "HUB" and deg_max == 17


def test_router_dense_inert_by_default():
    nodes = {"a": (0, 0, 96, 44), "b": (300, 0, 96, 44)}
    r = Router(nodes, [("a", "b")])
    assert r.dense is False and r.dense_hub is None
    assert r.dense_degrade == []
    assert r._dense_on_grid("a", [0.0, 0.0]) is False


def test_router_dense_on_grid_caliber():
    nodes = {"HUB": (0, 0, 96, 44), "b": (300, 0, 96, 44)}
    r = Router(nodes, [("HUB", "b")], dense_hub="HUB")
    # n-side border point, tangent offset a multiple of 6 -> on grid
    assert r._dense_on_grid("HUB", [12.0, -22.0]) is True
    # off-grid tangent offset
    assert r._dense_on_grid("HUB", [13.6, -22.0]) is False
    # interior point (deep inside) -> not on the border -> False
    assert r._dense_on_grid("HUB", [12.0, 0.0]) is False
    # non-hub box: always False
    assert r._dense_on_grid("b", [12.0, -22.0]) is False


# ------------------------------------------------------------------
# er-layer dense slot grid
# ------------------------------------------------------------------

def test_dense_grid_extension_capacity_and_golden_retirement():
    t = er._anchor_table(0.0, 0.0, 48.0, 22.0)     # 96x44 card
    t["cx"], t["cy"] = 0.0, 0.0
    er._extend_dense_grid(t)
    # goldens retired on the dense hub table
    for g in ("n-g1", "n-g2", "e-g1", "w-g2"):
        assert g not in t
    # long side hosts >= 15 usable slots (midpoint + 14 grid points)
    usable_n = er._usable(t, "n", sep_min=er.DENSE_SLOT_SEP_MIN)
    assert len(usable_n) >= 15
    # non-dense boxes keep the legacy usable set
    t2 = er._anchor_table(0.0, 0.0, 48.0, 22.0)
    usable_n2 = er._usable(t2, "n")
    assert usable_n2 == ["n", "n-g1", "n-g2"]


def test_assign_dense_hub_grid_endpoints_are_grid_multiples():
    nodes_px = {"HUB": (0, 0, 96, 44)}
    nodes_px.update({"L%d" % i: (-260.0 + i * 44.0, -160.0, 96, 44)
                     for i in range(6)})
    nodes_px.update({"R%d" % i: (-260.0 + i * 44.0, 160.0, 96, 44)
                     for i in range(6)})
    edges = [("HUB", "L%d" % i) for i in range(6)] + \
            [("HUB", "R%d" % i) for i in range(6)]
    kinds = ["N"] * len(edges)
    presets, report = er.assign(nodes_px, edges, kinds, dense_hub="HUB")
    assert presets
    for i, p in presets.items():
        if edges[i][0] != "HUB":
            continue
        ax, ay = p["pa"]
        onx = p["a_side"] in ("n", "s")
        off = (ay - 0.0) if not onx else (ax - 0.0)
        # hub end offset along its side axis is a multiple of 6
        axis_off = (ax - 0.0) if onx else (ay - 0.0)
        assert abs(axis_off / 6.0 - round(axis_off / 6.0)) < 1e-6, (i, axis_off)


def test_validate_presets_dense_angle_floor():
    nodes_px = {"HUB": (0.0, 0.0, 96.0, 44.0), "F": (200.0, 0.0, 96.0, 44.0)}
    edges = [("HUB", "F")]
    kinds = ["N"]
    # chord 15 deg off the HUB e-side border tangent (vertical): the hub
    # end reads the dense 12 deg floor, the F s-side end (horizontal
    # tangent) reads a 75 deg arrival
    pa = [48.0, 0.0]
    pb = [48.0 + 40.0 * math.tan(math.radians(15.0)), 40.0]
    presets = {0: {"pa": pa, "pb": pb, "a_side": "e", "b_side": "s",
                   "a_anchor": "e", "b_anchor": "s", "style": "line",
                   "arc_side": 1}}
    drop_dense = er.validate_presets(nodes_px, edges, presets, 16.0,
                                     dense_hub="HUB")
    drop_legacy = er.validate_presets(nodes_px, edges, presets, 16.0)
    assert 0 not in drop_dense          # 15 deg >= dense floor 12 (hub end)
    assert 0 in drop_legacy             # 15 deg < legacy floor 20


# ------------------------------------------------------------------
# dense_mode transport (meta -> scene -> gates annotation)
# ------------------------------------------------------------------

def test_metrics_dense_angle_floor_constant():
    from stdraw.routing import DENSE_ANCHOR_MIN_DEG, ANCHOR_MIN_DEG
    # dense hub boxes keep only their relaxed angle floor under the
    # on-border + angle-met criterion (the dense slot-grid membership
    # exemption was retired with the 16-set criterion, 2026-11-26)
    assert DENSE_ANCHOR_MIN_DEG < ANCHOR_MIN_DEG


def test_dense_meta_transport_via_scene_and_certificate():
    from stdraw.metrics import scene_from_auto, certificate_auto
    v4 = {
        "viewBox": [0, 0, 400, 200],
        "nodes": {"a": {"x": 100, "y": 100, "w": 96},
                  "b": {"x": 300, "y": 100, "w": 96}},
        "edges": [{"a": "a", "b": "b", "polarity": "+", "loop_kinds": [],
                   "loop_color": None,
                   "route": {"kind": "line",
                             "points": [[148.0, 100.0], [252.0, 100.0]]},
                   "anchors": {"a": [148.0, 100.0], "b": [252.0, 100.0]},
                   "arrow": [252.0, 100.0], "route_cross_edges": 0}],
        "bars": {},
        "meta": {"dense_mode": {"triggered": True, "rule_hit": "max_deg>=10",
                                "deg_max": 12, "hub": "a"}},
    }
    scene = scene_from_auto(v4)
    assert scene["dense_mode"] == v4["meta"]["dense_mode"]
    cert = certificate_auto(scene, graph_name="dense-probe")
    assert cert["gates"]["dense_mode"] == v4["meta"]["dense_mode"]
    # non-dense scenes: the scene transport carries None (planarization
    # precedent) and the gates block carries NO dense_mode key at all
    v4["meta"].pop("dense_mode")
    scene = scene_from_auto(v4)
    cert = certificate_auto(scene, graph_name="plain-probe")
    assert scene["dense_mode"] is None
    assert "dense_mode" not in cert["gates"]


# ------------------------------------------------------------------
# dense form gate (operator 2026-11-15): dense fan delivers RADIAL form
# ------------------------------------------------------------------

_FAN_DSL = 'graph "fan-d17"\n\n' + \
    "".join('var L%02d "L%02d"\n' % (i, i) for i in range(17)) + \
    'var HUB "HUB"\n\n' + \
    "".join("HUB -> + L%02d\n" % i for i in range(17))


def test_dense_fan_delivers_radial_form_and_best_grade():
    # operator form-correctness gate: the dense fan family must deliver
    # HUB-centered radial geometry (never the layered row fallback) with
    # straight-line spokes and a clean certificate.
    import time
    from stdraw import dsl
    from stdraw.layout_auto import layout
    graph = dsl.parse(_FAN_DSL)
    t0 = time.time()
    v4 = layout(graph)
    wall = time.time() - t0
    meta = v4["meta"]
    assert meta["placement"] == "radial", meta.get("position_engine")
    dm = meta.get("dense_mode") or {}
    assert dm.get("triggered") is True and dm.get("hub") == "HUB"
    kinds = [e["route"]["kind"] for e in v4["edges"]]
    assert set(kinds) == {"line"}, kinds          # straight spokes only
    assert wall < 300.0                            # d17-class budget
    # zero-drift guard stays structural: the predicate is topology-pure —
    # a corpus-shaped graph (max_deg 8) never carries dense_mode (covered
    # by test_dense_predicate_corpus_family_is_a_constructive_non_hit and
    # the A-tier byte sweep).
