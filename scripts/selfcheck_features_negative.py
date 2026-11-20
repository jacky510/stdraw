#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Standalone negative self-check for stdraw.features.

Contract: each case injects a layout defect into an otherwise clean layout
and asserts the corresponding feature detects it.  The clean layout must pass
the "clean" assertions first.  Any undetected defect => print + exit 1.

Run:  python scripts/selfcheck_features_negative.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stdraw.features import extract_features  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _square(clean=True):
    pos = {"a": (100, 100), "b": (300, 100), "c": (300, 300), "d": (100, 300)}
    if not clean:
        pos["a"] = (160, 180)  # symmetry broken
    nodes = {k: {"x": v[0], "y": v[1], "w": 40, "h": 30} for k, v in pos.items()}
    edges = [{"a": "a", "b": "b", "polarity": "+", "loop_kinds": ["L"]},
             {"a": "b", "b": "c", "polarity": "+", "loop_kinds": ["L"]},
             {"a": "c", "b": "d", "polarity": "+", "loop_kinds": ["L"]},
             {"a": "d", "b": "a", "polarity": "+", "loop_kinds": ["L"]}]
    return {"viewBox": [0, 0, 400, 400], "nodes": nodes, "edges": edges, "meta": {}}


@case("self-intersecting loop detected")
def _c1():
    clean = extract_features(_square())["features"]["loop_self_intersections"]["total"]
    doc = _square()
    # rewire the cycle into an hourglass: a->c->b->d->a
    order = [("a", "c"), ("c", "b"), ("b", "d"), ("d", "a")]
    doc["edges"] = [{"a": x, "b": y, "polarity": "+", "loop_kinds": ["L"]}
                    for (x, y) in order]
    bad = extract_features(doc)["features"]["loop_self_intersections"]["total"]
    assert clean == 0 and bad == 1, "hourglass loop not detected (clean=%s bad=%s)" % (clean, bad)


@case("foreign node inside loop detected")
def _c2():
    doc = _square()
    doc["nodes"]["x"] = {"x": 200, "y": 200, "w": 40, "h": 30}
    bad = extract_features(doc)["features"]["loop_foreign_node_count"]["total"]
    assert bad == 1, "planted node not detected (bad=%s)" % bad


@case("route crossing detected")
def _c3():
    nodes = {"p": {"x": 20, "y": 200, "w": 40, "h": 30},
             "q": {"x": 380, "y": 200, "w": 40, "h": 30},
             "r": {"x": 200, "y": 20, "w": 40, "h": 30},
             "s": {"x": 200, "y": 380, "w": 40, "h": 30}}
    edges = [{"a": "p", "b": "q", "polarity": "+", "loop_kinds": []},
             {"a": "r", "b": "s", "polarity": "+", "loop_kinds": []}]
    out = extract_features({"viewBox": [0, 0, 400, 400], "nodes": nodes,
                            "edges": edges, "meta": {}})
    assert out["features"]["crossing_count"]["total"] == 1, "crossing not detected"
    assert out["features"]["min_crossing_angle_deg"]["min"] is not None


@case("clearance violation detected")
def _c4():
    nodes = {"p": {"x": 100, "y": 100, "w": 40, "h": 30},
             "q": {"x": 100, "y": 300, "w": 40, "h": 30},
             "z": {"x": 100, "y": 200, "w": 40, "h": 30}}
    edges = [{"a": "p", "b": "q", "polarity": "+", "loop_kinds": []}]
    out = extract_features({"viewBox": [0, 0, 400, 400], "nodes": nodes,
                            "edges": edges, "meta": {}})
    f = out["features"]["bend_curvature_soft_clearance"]
    assert f["min_gap_px"] == 0.0 and f["soft_margin_px"] < 0.0, \
        "clearance violation not detected: %r" % f


@case("alignment break detected")
def _c5():
    def row(y_s):
        nodes = {"p": {"x": 50, "y": y_s[0], "w": 40, "h": 30},
                 "q": {"x": 150, "y": y_s[1], "w": 40, "h": 30},
                 "r": {"x": 250, "y": y_s[2], "w": 40, "h": 30},
                 "s": {"x": 350, "y": y_s[3], "w": 40, "h": 30}}
        edges = [{"a": "p", "b": "q", "polarity": "+", "loop_kinds": []},
                 {"a": "q", "b": "r", "polarity": "+", "loop_kinds": []},
                 {"a": "r", "b": "s", "polarity": "+", "loop_kinds": []}]
        return extract_features({"viewBox": [0, 0, 400, 400], "nodes": nodes,
                                 "edges": edges, "meta": {}})
    clean = row([100, 100, 100, 100])["features"]["alignment_coverage"]["max_coverage"]
    bad = row([100, 100, 100, 140])["features"]["alignment_coverage"]["max_coverage"]
    assert clean == 1.0 and bad < 1.0, "alignment break not detected (%s -> %s)" % (clean, bad)


@case("symmetry break detected")
def _c6():
    clean = extract_features(_square(True))["features"]["automorphism_symmetry_residual"]
    bad = extract_features(_square(False))["features"]["automorphism_symmetry_residual"]
    assert clean["residual"] < 1e-6 and bad["residual"] > 1.0, \
        "symmetry break not detected (%s -> %s)" % (clean["residual"], bad["residual"])


@case("loop overlap detected")
def _c7():
    sq = {"A": [(100, 100), (300, 100), (300, 300), (100, 300)],
          "B": [(200, 200), (400, 200), (400, 400), (200, 400)]}
    nodes, edges = {}, []
    for tag, pts in sq.items():
        ids = [tag + str(i) for i in range(4)]
        nodes.update({nid: {"x": p[0], "y": p[1], "w": 40, "h": 30}
                      for nid, p in zip(ids, pts)})
        for i in range(4):
            edges.append({"a": ids[i], "b": ids[(i + 1) % 4], "polarity": "+",
                          "loop_kinds": ["L" + tag]})
    out = extract_features({"viewBox": [0, 0, 400, 400], "nodes": nodes,
                            "edges": edges, "meta": {}})
    total = out["features"]["loop_overlap_area"]["total"]
    assert total > 9000.0, "loop overlap not detected (total=%s)" % total


def main():
    failures = 0
    for name, fn in CASES:
        try:
            fn()
            print("PASS  %s" % name)
        except AssertionError as exc:
            failures += 1
            print("FAIL  %s -- %s" % (name, exc))
    print("cases=%d failures=%d" % (len(CASES), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
