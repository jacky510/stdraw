# -*- coding: utf-8 -*-
"""Negative self-check for the unified feature extractor.

Every case injects a layout defect and asserts the corresponding feature goes
"red" (detects the defect).  If a defect passes undetected, pytest fails with
exit code 1.  A standalone runner with the same contract lives at
scripts/selfcheck_features_negative.py.
"""
from stdraw.features import extract_features

from test_features import _doc, _e, _n, _square_loop_doc


def _bowtie_doc():
    # positions are the square's; the cycle a->c->b->d->a draws an hourglass
    pos = {"a": (100, 100), "b": (300, 100), "c": (300, 300), "d": (100, 300)}
    nodes = {k: _n(*pos[k]) for k in "abcd"}
    edges = [_e("a", "c", loops=("L",)), _e("c", "b", loops=("L",)),
             _e("b", "d", loops=("L",)), _e("d", "a", loops=("L",))]
    return _doc(nodes, edges)


def test_neg_inject_self_intersecting_loop():
    clean = extract_features(_square_loop_doc())
    bad = extract_features(_bowtie_doc())
    assert clean["features"]["loop_self_intersections"]["total"] == 0
    assert bad["features"]["loop_self_intersections"]["total"] == 1, \
        "defect undetected: hourglass loop must self-intersect"


def test_neg_inject_foreign_node_into_loop():
    clean = extract_features(_square_loop_doc())
    bad = extract_features(_square_loop_doc(extra_nodes={"x": _n(200, 200)}))
    assert clean["features"]["loop_foreign_node_count"]["total"] == 0
    assert bad["features"]["loop_foreign_node_count"]["total"] == 1, \
        "defect undetected: node planted inside the loop"


def test_neg_inject_edge_crossing():
    nodes = {"p": _n(20, 200), "q": _n(380, 200), "r": _n(200, 20), "s": _n(200, 380)}
    bad = extract_features(_doc(nodes, [_e("p", "q"), _e("r", "s")]))
    assert bad["features"]["crossing_count"]["total"] == 1, \
        "defect undetected: perpendicular route crossing"
    assert bad["features"]["min_crossing_angle_deg"]["min"] is not None


def test_neg_inject_clearance_violation():
    nodes = {"p": _n(100, 100), "q": _n(100, 300), "z": _n(100, 200)}
    bad = extract_features(_doc(nodes, [_e("p", "q")]))
    f = bad["features"]["bend_curvature_soft_clearance"]
    assert f["min_gap_px"] == 0.0 and f["soft_margin_px"] < 0.0, \
        "defect undetected: route crossing a foreign card"


def test_neg_inject_alignment_break():
    nodes = {"p": _n(50, 100), "q": _n(150, 100), "r": _n(250, 100), "s": _n(350, 100)}
    edges = [_e("p", "q"), _e("q", "r"), _e("r", "s")]
    clean = extract_features(_doc(nodes, edges))
    bad_nodes = dict(nodes)
    bad_nodes["s"] = _n(350, 140)
    bad = extract_features(_doc(bad_nodes, edges))
    assert clean["features"]["alignment_coverage"]["max_coverage"] == 1.0
    assert bad["features"]["alignment_coverage"]["max_coverage"] < 1.0, \
        "defect undetected: one anchor knocked off the shared row"


def test_neg_break_symmetry():
    clean = extract_features(_square_loop_doc())
    bad = extract_features(_square_loop_doc(jitter=("a", 60, 80)))
    assert clean["features"]["automorphism_symmetry_residual"]["residual"] < 1e-6
    assert bad["features"]["automorphism_symmetry_residual"]["residual"] > 1.0, \
        "defect undetected: square symmetry destroyed"


def test_neg_inject_loop_overlap():
    sq1 = [(100, 100), (300, 100), (300, 300), (100, 300)]
    sq2 = [(200, 200), (400, 200), (400, 400), (200, 400)]
    nodes = {}
    edges = []
    for tag, sq, kind in (("A", sq1, "L1"), ("B", sq2, "L2")):
        ids = [tag + str(i) for i in range(4)]
        nodes.update({nid: _n(*p) for nid, p in zip(ids, sq)})
        for i in range(4):
            edges.append(_e(ids[i], ids[(i + 1) % 4], loops=(kind,)))
    bad = extract_features(_doc(nodes, edges))
    assert bad["features"]["loop_overlap_area"]["total"] > 9000.0, \
        "defect undetected: two overlapping loop polygons"
