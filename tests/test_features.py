# -*- coding: utf-8 -*-
"""Unit tests for the unified feature extractor (stdraw.features).

One positive known-value test per feature, all on deterministic synthetic
layouts (no RNG, no timestamps).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from stdraw.features import FEATURE_KEYS, extract_features, features_to_json

REPO = Path(__file__).resolve().parents[1]


def _doc(nodes, edges, viewBox=(0, 0, 400, 400), meta=None):
    return {
        "viewBox": list(viewBox),
        "nodes": nodes,
        "edges": edges,
        "meta": meta or {},
    }


def _n(x, y, w=40, h=30):
    return {"x": x, "y": y, "w": w, "h": h}


def _e(a, b, pol="+", loops=(), pts=None):
    e = {"a": a, "b": b, "polarity": pol, "loop_kinds": list(loops)}
    if pts:
        e["route"] = {"kind": "line", "points": pts}
    return e


SQUARE = [(100, 100), (300, 100), (300, 300), (100, 300)]


def _square_loop_doc(extra_nodes=None, extra_edges=None, jitter=None):
    ids = ["a", "b", "c", "d"]
    pos = dict(zip(ids, SQUARE))
    if jitter:
        pos = dict(pos)
        x, y = pos[jitter[0]]
        pos[jitter[0]] = (x + jitter[1], y + jitter[2])
    nodes = {k: _n(*pos[k]) for k in ids}
    edges = [
        _e("a", "b", loops=("L",)),
        _e("b", "c", loops=("L",)),
        _e("c", "d", loops=("L",)),
        _e("d", "a", loops=("L",)),
    ]
    nodes.update(extra_nodes or {})
    edges.extend(extra_edges or [])
    return _doc(nodes, edges)


# ── 1/2/3/5: loop geometry ──

def test_loop_self_intersections_clean_square():
    out = extract_features(_square_loop_doc())
    assert out["features"]["loop_self_intersections"]["total"] == 0


def test_loop_self_intersections_bowtie():
    # cycle order a->c->b->d forms an hourglass polygon => 1 self-intersection
    nodes = {k: _n(*p) for k, p in zip("abcd", SQUARE)}
    edges = [_e("a", "c", loops=("L",)), _e("c", "b", loops=("L",)),
             _e("b", "d", loops=("L",)), _e("d", "a", loops=("L",))]
    out = extract_features(_doc(nodes, edges))
    assert out["features"]["loop_self_intersections"]["total"] == 1


def test_loop_foreign_node_count():
    out = extract_features(_square_loop_doc())
    assert out["features"]["loop_foreign_node_count"]["total"] == 0
    out = extract_features(_square_loop_doc(extra_nodes={"x": _n(200, 200)}))
    assert out["features"]["loop_foreign_node_count"]["total"] == 1
    # outside the loop -> stays 0
    out = extract_features(_square_loop_doc(extra_nodes={"x": _n(380, 380)}))
    assert out["features"]["loop_foreign_node_count"]["total"] == 0


def test_loop_isoperimetric_compactness_square():
    out = extract_features(_square_loop_doc())
    f = out["features"]["loop_isoperimetric_compactness"]
    # square side 200: 4*pi*A/P^2 = pi/4
    assert f["mean"] == pytest.approx(3.141592654 / 4, abs=1e-6)
    assert f["worst"] == pytest.approx(3.141592654 / 4, abs=1e-6)
    assert f["valid_loops"] == 1


def test_loop_edge_length_cv_square():
    out = extract_features(_square_loop_doc())
    f = out["features"]["loop_edge_length_cv"]
    assert f["mean"] == pytest.approx(0.0, abs=1e-9)  # all sides equal


# ── 4: loop overlap area ──

def test_loop_overlap_area_two_squares():
    nodes = {k: _n(*p) for k, p in zip("abcd", SQUARE)}
    ids2 = ["e", "f", "g", "h"]
    sq2 = [(200, 200), (400, 200), (400, 400), (200, 400)]
    nodes.update({k: _n(*p) for k, p in zip(ids2, sq2)})
    edges = [_e("a", "b", loops=("L1",)), _e("b", "c", loops=("L1",)),
             _e("c", "d", loops=("L1",)), _e("d", "a", loops=("L1",)),
             _e("e", "f", loops=("L2",)), _e("f", "g", loops=("L2",)),
             _e("g", "h", loops=("L2",)), _e("h", "e", loops=("L2",))]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["loop_overlap_area"]
    assert f["total"] == pytest.approx(10000.0, abs=1.0)  # 100x100 intersection


def test_loop_overlap_area_shared_nodes_excluded():
    out = extract_features(_square_loop_doc())
    assert out["features"]["loop_overlap_area"]["total"] == 0.0


# ── 6/7/8: crossings ──

def test_crossings_two_perpendicular_edges():
    nodes = {"p": _n(20, 200), "q": _n(380, 200), "r": _n(200, 20), "s": _n(200, 380)}
    edges = [_e("p", "q"), _e("r", "s", loops=("L",))]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]
    assert f["crossing_count"]["total"] == 1
    assert f["loop_edge_crossing_count"]["total"] == 1  # second edge carries a loop
    assert f["min_crossing_angle_deg"]["min"] == pytest.approx(90.0)


def test_crossings_adjacent_edges_not_counted():
    out = extract_features(_square_loop_doc())
    assert out["features"]["crossing_count"]["total"] == 0
    assert out["features"]["min_crossing_angle_deg"]["min"] is None


def test_min_crossing_angle_diagonal():
    nodes = {"p": _n(20, 300), "q": _n(380, 100), "r": _n(20, 100), "s": _n(380, 300)}
    edges = [_e("p", "q"), _e("r", "s")]
    out = extract_features(_doc(nodes, edges))
    ang = out["features"]["min_crossing_angle_deg"]["min"]
    # each edge slopes atan(200/360)=29.05 deg -> angle between = 58.11 deg
    assert ang == pytest.approx(58.109, abs=0.2)


# ── 9/10: symmetry (RFC §15.1) ──

def test_automorphism_symmetry_square_cycle():
    out = extract_features(_square_loop_doc())
    f = out["features"]["automorphism_symmetry_residual"]
    assert f["residual"] is not None
    assert f["residual"] < 1e-6
    ff = f["five_fields"]
    for key in ("deleted_edge_costs", "coverage", "dir_keep_ratio",
                "polarity_keep_ratio", "confidence"):
        assert key in ff, "RFC §15.1 five-field struct incomplete"
    assert f["automorphisms_found"] >= 1


def test_automorphism_symmetry_broken():
    out = extract_features(_square_loop_doc(jitter=("a", 50, 70)))
    f = out["features"]["automorphism_symmetry_residual"]
    assert f["residual"] > 1.0  # moved node forces a positive residual


def test_mirror_axis_residual_square():
    out = extract_features(_square_loop_doc())
    m = out["features"]["mirror_axis_residual"]
    assert m is not None
    assert m["residual"] < 1e-6
    assert "axis_deg" in m and "pivot" in m


# ── 11/12/13: edge CV / angular resolution / spacing CV ──

def test_edge_length_cv():
    nodes = {"p": _n(20, 200), "q": _n(220, 200), "r": _n(320, 200)}
    edges = [_e("p", "q"), _e("q", "r")]  # lengths 200, 100
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["edge_length_cv"]
    # mean 150, population sd 50 -> cv = 1/3
    assert f["cv"] == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_max_min_edge_ratio():
    nodes = {"p": _n(20, 200), "q": _n(220, 200), "r": _n(320, 200)}
    edges = [_e("p", "q"), _e("q", "r")]
    out = extract_features(_doc(nodes, edges))
    assert out["features"]["max_min_edge_ratio"]["ratio"] == pytest.approx(2.0)


def test_angular_resolution_perpendicular_corner():
    nodes = {"o": _n(200, 200), "p": _n(20, 200), "q": _n(200, 20)}
    edges = [_e("o", "p"), _e("o", "q")]
    out = extract_features(_doc(nodes, edges))
    assert out["features"]["angular_resolution_deg"]["min"] == pytest.approx(90.0)


def test_node_spacing_cv_and_min_ratio():
    nodes = {"p": _n(100, 100), "q": _n(110, 100)}
    edges = [_e("p", "q")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]
    # two nodes -> both nearest-neighbour distances are 10 -> cv = 0
    assert f["node_spacing_cv"]["cv"] == pytest.approx(0.0, abs=1e-9)
    diag = (400 ** 2 + 400 ** 2) ** 0.5
    assert f["min_spacing_diagonal_ratio"]["ratio"] == pytest.approx(10.0 / diag, abs=1e-6)
    assert f["min_spacing_diagonal_ratio"]["min_spacing_px"] == pytest.approx(10.0)


# ── 14/21: bends / soft clearance ──

def test_bend_count_total_curvature():
    nodes = {"p": _n(100, 100), "q": _n(300, 300)}
    edges = [_e("p", "q", pts=[[100, 100], [300, 100], [300, 300]])]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["bend_count_total_curvature"]
    assert f["bend_count"] == 1
    assert f["total_curvature_deg"] == pytest.approx(90.0)


def test_soft_clearance_margin():
    nodes = {"p": _n(100, 100), "q": _n(100, 300), "z": _n(300, 300)}
    edges = [_e("p", "q")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["bend_curvature_soft_clearance"]
    assert f["clearance_threshold_px"] == 16.0
    # segment x=100 vs card rect x in [280,320] -> gap 180, margin 164
    assert f["min_gap_px"] == pytest.approx(180.0, abs=0.5)
    assert f["soft_margin_px"] == pytest.approx(164.0, abs=0.5)


def test_soft_clearance_violation_detected():
    nodes = {"p": _n(100, 100), "q": _n(100, 300), "z": _n(100, 200)}
    edges = [_e("p", "q")]  # passes straight through z's card
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["bend_curvature_soft_clearance"]
    assert f["min_gap_px"] == 0.0
    assert f["soft_margin_px"] == pytest.approx(-16.0)


# ── 15/16/17/18/19/20: canvas family ──

def test_visual_centroid_offset_and_hub():
    nodes = {"p": _n(100, 100), "q": _n(300, 100), "r": _n(200, 300)}
    edges = [_e("p", "q"), _e("q", "r"), _e("r", "p"), _e("p", "r")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]
    # equal-area cards -> centroid = mean of centers = (200, 166.67)
    assert f["visual_centroid_offset"]["area_centroid"][0] == pytest.approx(200.0, abs=0.1)
    # p and r tie at degree 3 -> deterministic tie-break picks the smallest id
    assert f["hub_centroid_distance"]["hub"] == "p"
    assert f["hub_centroid_distance"]["hub_degree"] == 3
    diag = (400 ** 2 + 400 ** 2) ** 0.5
    exp_off = ((200 - 200) ** 2 + (500 / 3 - 200) ** 2) ** 0.5
    assert f["visual_centroid_offset"]["offset_px"] == pytest.approx(exp_off, abs=0.1)
    assert f["visual_centroid_offset"]["ratio"] == pytest.approx(exp_off / diag, abs=1e-6)


def test_voronoi_two_nodes_equal_cells():
    nodes = {"p": _n(100, 200), "q": _n(300, 200)}
    edges = [_e("p", "q")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["voronoi_cell_area_cv"]
    assert f["cv"] == pytest.approx(0.0, abs=1e-6)
    areas = [d["cell_area"] for d in f["per_node"]]
    assert areas[0] == pytest.approx(areas[1], abs=1.0)  # 400x400 bisected


def test_canvas_fill_and_aspect():
    out = extract_features(_square_loop_doc())
    f = out["features"]["canvas_fill_and_aspect"]
    # 4 cards of 40x30 at the square corners, no overlap -> union 4800
    assert f["fill_rate"] == pytest.approx(4800.0 / 160000.0, abs=1e-6)
    # content bbox spans card extents: x 80..320 (240), y 85..315 (230)
    assert f["content_bbox"] == [pytest.approx(240.0), pytest.approx(230.0)]
    assert f["aspect_ratio"] == pytest.approx(240.0 / 230.0, abs=1e-6)


# ── RFC §15.2 alignment ──

def test_alignment_coverage_full_row():
    nodes = {"p": _n(50, 100), "q": _n(150, 100), "r": _n(250, 100), "s": _n(350, 100)}
    edges = [_e("p", "q"), _e("q", "r"), _e("r", "s")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["alignment_coverage"]
    assert f["max_coverage"] == pytest.approx(1.0)
    assert f["tolerance_px"] == pytest.approx(0.04 * 400)
    assert "groups_ge3" in f["per_axis"][0]


def test_alignment_coverage_broken_row():
    nodes = {"p": _n(50, 100), "q": _n(150, 100), "r": _n(250, 100), "s": _n(350, 140)}
    edges = [_e("p", "q"), _e("q", "r"), _e("r", "s")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["alignment_coverage"]
    assert f["max_coverage"] < 1.0


def test_alignment_min_group_enforced():
    # only 2 anchors share a row -> no group counts
    nodes = {"p": _n(50, 100), "q": _n(350, 100), "r": _n(200, 300)}
    edges = [_e("p", "q")]
    out = extract_features(_doc(nodes, edges))
    f = out["features"]["alignment_coverage"]
    assert f["max_coverage"] < 1.0


# ── stability slot + schema contract ──

def test_layout_stability_slot_static():
    out = extract_features(_square_loop_doc())
    f = out["features"]["layout_stability"]
    assert f["value"] is None and f["applicable"] is False


def test_all_feature_keys_present():
    assert len(FEATURE_KEYS) >= 21
    out = extract_features(_square_loop_doc(extra_nodes={"x": _n(200, 200)}))
    for key in FEATURE_KEYS:
        assert key in out["features"], key


def test_determinism_same_document():
    doc = _square_loop_doc(extra_nodes={"x": _n(200, 200)},
                           extra_edges=[_e("x", "a", pts=[[200, 200], [120, 100], [100, 100]])])
    j1 = features_to_json(extract_features(doc))
    j2 = features_to_json(extract_features(doc))
    assert j1 == j2
    assert j1.encode("utf-8") == j2.encode("utf-8")


# ── CLI + real-repo layout ──

REAL_LAYOUT = REPO / "tests" / "data" / "epidemic-feedback-manual-layout.json"


@pytest.mark.skipif(not REAL_LAYOUT.exists(), reason="real layout fixture not found")
def test_cli_on_real_layout(tmp_path):
    out1 = tmp_path / "f1.json"
    out2 = tmp_path / "f2.json"
    for out in (out1, out2):
        r = subprocess.run(
            [sys.executable, "-m", "stdraw.features", str(REAL_LAYOUT), "--out", str(out)],
            capture_output=True, text=True, cwd=str(REPO))
        assert r.returncode == 0, r.stderr
    assert out1.read_bytes() == out2.read_bytes(), "double run must be byte-identical"
    doc = json.loads(out1.read_text(encoding="utf-8"))
    for key in FEATURE_KEYS:
        assert key in doc["features"], key
