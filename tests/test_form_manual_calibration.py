# -*- coding: utf-8 -*-
"""Manual-layout calibration for the spine-wing / ring-cycle form battery
and the widened reverse-form gate (silent-fallback governance, 2026-11-16).

The three in-repo manual fixtures (benchmarks/manual/, hand dragged by
the operator on the interactive page, 2026-11-16) are the specification:

  acceptance = "manual fixtures PASS the calibrated battery AND the
  rejected legacy gate is proven to have rejected the ground truth"
  (same discipline as tests/test_radial_manual_calibration.py: the
  thresholds are derived from the fixtures themselves, not negotiated
  by hand)

Legs under test:
  - ring form battery (ringlayout.RING_SPACING_CV_MAX /
    RING_TEMPLATE_FIT_MAX, single source with metrics.py certificate
    gates and check.py gate 9): brand-flywheel (good ring anchor) and
    random-n10-i05 (freehand ring reading, upper band) must PASS; the
    brand-flywheel measurement must stay ABOVE the retired 0.05 gate
    (guard against re-tightening to the uncalibrated caliber that
    rejected jacky's own good ring);
  - spine-wing constructed band: the 2px engine band is NOT widened to
    hand-pull bands -- the classic-cld sample measures <= its own 6px
    band, while the freehand i00 reading measures far outside (the
    human "shape is right" reading is not a constructed layout);
  - reverse-form gate widening (layout_auto._FORM_FALLBACK_MODES): a
    spine-wing/ring-cycle detection whose trial fails must record
    form_fallback and degrade the certificate instead of silently
    grading the layered fallback;
  - delivered ring certificates carry the recalibrated gate keys.
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..")))

from stdraw import dsl  # noqa: E402
from stdraw.layout_auto import layout  # noqa: E402
from stdraw.metrics import certificate_auto, scene_from_auto  # noqa: E402
from stdraw import ringlayout, spinewinglayout  # noqa: E402
from stdraw.regularity import cycle_polygon_deviation  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANUAL_DIR = os.path.join(ROOT, "benchmarks", "manual")
CORPUS_DIR = os.path.join(ROOT, "benchmarks", "corpus")

# the hand-drawn manual fixtures live only in the git checkout (packaging
# T6 auto-skip, see tests/conftest.py); benchmarks/corpus ships in the sdist.
pytestmark = pytest.mark.repo("benchmarks/manual")


def _manual_fixture(name):
    with open(os.path.join(MANUAL_DIR, f"{name}-manual-layout.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def _corpus_graph(rel):
    with open(os.path.join(CORPUS_DIR, rel), encoding="utf-8") as fh:
        return dsl.parse(fh.read())


def _ring_measures(fig, graph):
    """Chord spacing CV + polygon deviation, exactly the certificate
    formulas (metrics.py ring branch), on the fixture coordinates with
    the ring order from the graph-theoretic detection."""
    pts = {v: (p["x"], p["y"]) for v, p in fig["nodes"].items()}
    plan = ringlayout.detect_ring(graph)
    assert plan is not None, "ring detection must hit the fixture graph"
    ring = plan["ring"]
    rpts = [pts[v] for v in ring]
    dists = [math.dist(rpts[i], rpts[(i + 1) % len(rpts)])
             for i in range(len(rpts))]
    md = sum(dists) / len(dists)
    cv = (math.sqrt(sum((d - md) ** 2 for d in dists) / len(dists)) / md
          if md else 0.0)
    dev = cycle_polygon_deviation({v: pts[v] for v in ring}, ring)
    return cv, dev


# ------------------------------------------------------------------
# 1. acceptance leg: the manual rings PASS the calibrated battery
# ------------------------------------------------------------------

@pytest.mark.parametrize("cld,fixture", [
    ("classic/brand-flywheel.cld", "brand-flywheel"),
    ("random/random-n10-i05.cld", "random-n10-i05"),
])
def test_manual_ring_passes_calibrated_battery(cld, fixture):
    fig = _manual_fixture(fixture)
    cv, dev = _ring_measures(fig, _corpus_graph(cld))
    assert cv <= ringlayout.RING_SPACING_CV_MAX, (fixture, cv)
    assert dev <= ringlayout.RING_TEMPLATE_FIT_MAX, (fixture, dev)


def test_good_ring_anchor_stays_above_retired_gate():
    # the incident guard: the retired uncalibrated 0.05 gates rejected
    # jacky's hand-drawn good ring itself -- re-tightening the battery
    # to 0.05 would re-break the ground truth (radial azimuth incident,
    # same class)
    fig = _manual_fixture("brand-flywheel")
    cv, dev = _ring_measures(fig, _corpus_graph("classic/brand-flywheel.cld"))
    assert cv > 0.05 and dev > 0.05, (cv, dev)


# ------------------------------------------------------------------
# 2. spine-wing leg: the constructed band stays engine-side
# ------------------------------------------------------------------

def _spine_devs(fig, graph):
    pts = {v: (p["x"], p["y"]) for v, p in fig["nodes"].items()}
    plan = spinewinglayout.detect_spine_wing(graph)
    assert plan is not None, "spine-wing detection must hit the fixture graph"
    spine = [plan["spine_head"], plan["spine_tail"]]
    wings = list(plan["wings_left"]) + [plan["wing_anchor"]]
    axis_x = sum(pts[s][0] for s in spine) / 2
    axis_y = sum(pts[w][1] for w in wings) / len(wings)
    spine_dev = max(abs(pts[s][0] - axis_x) for s in spine)
    mid_dev = max(abs(pts[w][1] - axis_y) for w in wings)
    errs = [spine_dev, mid_dev]
    for up, dn in plan["rest_pairs"]:
        errs.append(abs(pts[up][0] - pts[dn][0]))
        errs.append(abs((pts[up][1] + pts[dn][1]) / 2 - axis_y))
    return spine_dev, mid_dev, max(errs)


def test_classic_cld_sample_fits_sample_band():
    # the calibration sample keeps its own band (README: wing pair |dx|
    # 6px; the sample spine/midline measure sub-pixel)
    fig = _manual_fixture("classic-cld")
    sd, md, mx = _spine_devs(
        fig, _corpus_graph("classic/classic-cld-growth-and-burden.cld"))
    assert sd <= 2.0 and md <= 2.0, (sd, md)
    assert mx <= 6.0, mx


def test_freehand_i00_reading_is_not_constructed_geometry():
    # the migration fixture documents WHY the 2px constructed band must
    # not be widened to hand-pull bands: a human "shape is right"
    # reading of a spine-detected graph sits far outside any constructed
    # alignment (measured 115/172px), so equivalence for this form stays
    # role-grouping based, not coordinate based
    fig = _manual_fixture("random-n10-i00")
    sd, md, mx = _spine_devs(fig, _corpus_graph("random/random-n10-i00.cld"))
    assert sd > 2.0 and md > 2.0, (sd, md)


# ------------------------------------------------------------------
# 3. rejection leg: widened reverse-form gate costs the grade
# ------------------------------------------------------------------

@pytest.mark.parametrize("cld,mode", [
    ("random/random-n10-i00.cld", "spine-wing"),
    ("random/random-n10-i05.cld", "ring-cycle"),
])
def test_detected_but_abandoned_form_degrades_certificate(cld, mode):
    # real engine path (no monkeypatch): the detection hits, the trial
    # gate fails, the layered fallback must carry the form_fallback
    # record and lose the grade (formerly a silent fallback)
    graph = _corpus_graph(cld)
    v4 = layout(graph)
    meta = v4["meta"]
    assert meta["mode_decision_trace"]["placement"] == "layered", \
        meta["mode_decision_trace"]["placement"]
    ff = meta.get("form_fallback")
    assert ff, "layered fallback lost the form_fallback record"
    assert any(f.get("mode") == mode for f in ff), ff
    trace_rule = next(r for r in (meta.get("mode_decision_trace") or {}).get("rules", [])
                      if r.get("rule") == mode)
    assert trace_rule.get("trial_gate") == "fail"
    scene = scene_from_auto(v4)
    cert = certificate_auto(scene, graph_name=f"{mode}-fallback-probe")
    assert cert["grade"] == "uncertified", cert["grade_note"]
    assert cert["gates"].get("topology_form_fallback") is False


def test_delivered_ring_carries_recalibrated_gate_keys():
    # a ring-cycle delivered graph certifies under the manual-band keys
    # (renamed from the retired 0.05 keys) with no fallback record
    graph = _corpus_graph("classic/arms-race.cld")
    v4 = layout(graph)
    meta = v4["meta"]
    assert meta["mode_decision_trace"]["placement"] == "ring-cycle", \
        meta["mode_decision_trace"]["placement"]
    assert not meta.get("form_fallback")
    scene = scene_from_auto(v4)
    cert = certificate_auto(scene, graph_name="arms-race")
    g = cert["gates"]
    for key in ("ring_spacing_cv_le_050", "ring_template_fit_le_070"):
        assert key in g and g[key] is True, (key, g.get(key))
    assert "ring_spacing_cv_le_005" not in g
    assert "ring_template_fit_le_005" not in g


def test_fallback_layout_determinism_double_run():
    graph = _corpus_graph("random/random-n10-i00.cld")
    a = layout(dsl.parse(open(os.path.join(CORPUS_DIR,
                                           "random/random-n10-i00.cld"),
                              encoding="utf-8").read()))
    b = layout(graph)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
