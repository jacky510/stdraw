# -*- coding: utf-8 -*-
"""Manual-layout calibration acceptance (jacky hand-drawn ground truth).

The two in-repo manual fixtures (benchmarks/manual/fan-d12/fan-d17, hand
dragged by the operator on the interactive page, 2026-11-15) are the
specification for the radial form family:

  acceptance = "manual fixtures PASS the new battery AND the rejected
  legacy form is rejected"  (jacky 2026-11-15 ruling: the thresholds are
  derived from the fixtures themselves, not negotiated by hand)

Batteries under test:
  - radellayout.form_metrics + its manual-band constants (single source
    with check.py gate 9 and the metrics.py certificate gates);
  - the reverse-form gate (layout_auto form_fallback -> certificate
    grade uncertified): a star/fan topology whose radial trial fails
    must NEVER grade best on the layered fallback geometry;
  - the box-aware minimal ring radius (fan-d17 delivers ONE ring at the
    closed-form minimum instead of the old +46% chord-based radius;
    the old row-align fan-d17 rendering is what the operator rejected).

fan-d20 was never hand-drawn ("couldn't be bothered to drag it") -- it
is covered as an honest extrapolation of the same calibers (single ring
+ battery PASS), explicitly labeled as derived, not ground truth.
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..")))

from stdraw import dsl, layout_auto  # noqa: E402
from stdraw.layout_auto import layout  # noqa: E402
from stdraw.metrics import certificate_auto, scene_from_auto  # noqa: E402
from stdraw import radellayout  # noqa: E402

MANUAL_DIR = os.path.join(os.path.dirname(__file__), "..",
                          "benchmarks", "manual")

# the hand-drawn fan fixtures live only in the git checkout (packaging T6
# auto-skip, see tests/conftest.py).
pytestmark = pytest.mark.repo("benchmarks/manual")


def _manual_fixture(tag):
    path = os.path.join(MANUAL_DIR, f"fan-{tag}-manual-layout.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _fan_dsl(k):
    s = 'graph "fan-d%d"\n\n' % (k + 1)
    s += "".join('var L%02d "L%02d"\n' % (i, i) for i in range(k))
    s += 'var HUB "HUB"\n\n'
    s += "".join("HUB -> + L%02d\n" % i for i in range(k))
    return s


def _radial_meta_from_coords(nodes, edges):
    """Derive the meta["radial"] block for an arbitrary coordinate set
    (the manual fixtures carry no meta; the hub/ring derivation mirrors
    radellayout.detect_radial so the SAME battery runs on both sides)."""
    deg = {v: 0 for v in nodes}
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
    hub = min(nodes, key=lambda v: (-deg[v], v))
    ring = []
    for a, b in edges:
        if a == hub and b not in ring:
            ring.append(b)
        elif b == hub and a not in ring:
            ring.append(a)
    hp = nodes[hub]
    return {"hub": hub, "center": [hp["x"], hp["y"]],
            "ring_nodes": ring, "ring_groups": [ring]}


def _battery(nodes, card_h, radial_meta, edges):
    fm = radellayout.form_metrics(nodes, card_h, radial_meta, edges)
    gates = {
        "hub_center_le_2px": fm["hub_center_dev"] <= 2.0,
        "centroid_dev_le_24px": (fm.get("centroid_dev") is not None
                                 and fm["centroid_dev"]
                                 <= radellayout.RADIAL_CENTROID_DEV_MAX),
        "azimuth_cv_le_050": (fm.get("azimuth_cv") is not None
                              and fm["azimuth_cv"]
                              <= radellayout.RADIAL_AZ_CV_MAX),
        "radius_cv_le_015": (fm.get("radius_cv") is not None
                             and fm["radius_cv"]
                             <= radellayout.RADIAL_RADIUS_CV_MAX),
        "long_edge_rate_zero": fm.get("long_edge_rate") == 0.0,
        "min_pair_gap_ge_6px": (fm.get("min_pair_gap") is not None
                                and fm["min_pair_gap"]
                                >= radellayout.RADIAL_MIN_PAIR_GAP),
        "total_edge_fit_le_125": (fm.get("fit_ratio") is not None
                                  and fm["fit_ratio"]
                                  <= radellayout.RADIAL_TOTAL_EDGE_FIT),
    }
    return fm, gates


# ------------------------------------------------------------------
# 1. acceptance leg: the manual ground truth PASSES the new battery
# ------------------------------------------------------------------

@pytest.mark.parametrize("tag", ["d12", "d17"])
def test_manual_fixture_passes_the_calibrated_battery(tag):
    fig = _manual_fixture(tag)
    nodes = {v: {"x": d["x"], "y": d["y"], "w": 96.0, "h": 44.0}
             for v, d in fig["nodes"].items()}
    edges = [(e["a"], e["b"]) for e in fig["edges"]]
    fm, gates = _battery(nodes, 44.0,
                         _radial_meta_from_coords(nodes, edges), edges)
    failed = [k for k, v in gates.items() if not v]
    assert not failed, (f"manual fan-{tag} rejected by the calibrated "
                        f"battery: {failed}; fm={fm}")
    # the numeric facts the thresholds were derived from (guard against
    # silent battery drift away from the fixtures)
    assert fm["long_edge_rate"] == 0.0
    assert fm["min_pair_gap"] >= radellayout.RADIAL_MIN_PAIR_GAP


# ------------------------------------------------------------------
# 2. engine leg: the fan family delivers the manual-calibrated form
# ------------------------------------------------------------------

def _engine_fan(tag, k):
    v4 = layout(dsl.parse(_fan_dsl(k)))
    nodes = {v: dict(d) for v, d in v4["nodes"].items()}
    edges = [(e["a"], e["b"]) for e in v4["edges"]]
    return v4, nodes, edges


@pytest.mark.parametrize("tag,k", [("d12", 11), ("d17", 17)])
def test_engine_delivers_manual_equivalent_radial_form(tag, k):
    v4, nodes, edges = _engine_fan(tag, k)
    meta = v4["meta"]
    rad = meta.get("radial") or {}
    # form first: HUB-centered radial, one ring, straight spokes only
    assert meta["placement"] == "radial"
    assert rad.get("rings") == 1, ("the fan family delivers a single "
                                   "ring (manual ground truth: no ring "
                                   "split)")
    assert {e["route"]["kind"] for e in v4["edges"]} == {"line"}
    fm, gates = _battery(nodes, meta.get("cardH", 44), rad, edges)
    failed = [kk for kk, vv in gates.items() if not vv]
    assert not failed, (f"engine fan-{tag} failed the calibrated battery: "
                        f"{failed}; fm={fm}")
    # total-edge fit: the engine must sit AT the closed-form minimum
    # (uniform ring), i.e. no return to the old chord-based radius
    assert fm["fit_ratio"] <= 1.01
    # the box-aware minimum beats the old chord caliber decisively on the
    # d17 shape (old engine: r=414 / total 7033; manual: mean spoke 282)
    if tag == "d17":
        manual = _manual_fixture("d17")
        manual_total = sum(
            math.hypot(manual["nodes"][e["a"]]["x"] - manual["nodes"][e["b"]]["x"],
                       manual["nodes"][e["a"]]["y"] - manual["nodes"][e["b"]]["y"])
            for e in manual["edges"])
        engine_total = sum(
            math.hypot(nodes[a]["x"] - nodes[b]["x"],
                       nodes[a]["y"] - nodes[b]["y"]) for a, b in edges)
        assert engine_total < 1.15 * manual_total


def test_engine_fan_d20_extrapolated_honestly():
    # fan-d20 was never hand-drawn -- derived caliber, labeled as such
    v4, nodes, edges = _engine_fan("d20", 19)
    meta = v4["meta"]
    rad = meta.get("radial") or {}
    assert meta["placement"] == "radial" and rad.get("rings") == 1
    fm, gates = _battery(nodes, meta.get("cardH", 44), rad, edges)
    assert all(gates.values()), {k: v for k, v in gates.items() if not v}


def test_engine_radial_determinism_double_run():
    a = layout(dsl.parse(_fan_dsl(17)))
    b = layout(dsl.parse(_fan_dsl(17)))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ------------------------------------------------------------------
# 3. rejection leg: the abandoned radial reading must cost the grade
# ------------------------------------------------------------------

def test_reverse_form_gate_rejects_layered_fan_fallback(monkeypatch):
    # simulates the pre-radial engine exactly: the radial form is
    # detected but the trial fails -> the engine used to silently fall
    # back to the layered row (the rejected fan-d17 rendering) and STILL
    # grade best.  The reverse-form gate must make that impossible.
    monkeypatch.setattr(layout_auto, "_radial_trial",
                        lambda *a, **k: None)
    graph = dsl.parse(_fan_dsl(17))
    v4 = layout(graph)
    meta = v4["meta"]
    ff = meta.get("form_fallback")
    assert ff, "layered fallback lost the form_fallback record"
    assert any(f.get("mode") == "radial" for f in ff)
    scene = scene_from_auto(v4)
    cert = certificate_auto(scene, graph_name="fan-d17-fallback-probe")
    assert cert["grade"] == "uncertified", cert["grade_note"]
    assert cert["gates"].get("topology_form_fallback") is False


def test_certificate_gate_block_carries_manual_battery():
    # delivered radial certificate gates carry the recalibrated keys
    v4, nodes, edges = _engine_fan("d17", 17)
    scene = scene_from_auto(v4)
    cert = certificate_auto(scene, graph_name="fan-d17")
    g = cert["gates"]
    for key in ("radial_min_gap_ge_pack_floor", "radial_hub_center_le_2px",
                "radial_centroid_dev_le_24px", "radial_azimuth_cv_le_050",
                "radial_radius_cv_le_015", "radial_long_edge_rate_zero",
                "radial_total_edge_fit_le_125"):
        assert key in g and g[key] is True, key
