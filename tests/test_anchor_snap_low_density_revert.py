"""anchor_snap degradation-revert probe at low density (all-density revert).

Caliber (docs/layout-modes.md, density-threshold probe section):
  - below ANCHOR_SNAP_DENSE_E_OVER_N = 1.6 the snap still runs unconditionally,
    but a measured crossings / line-line-coincidence worsening reverts the
    whole snap (T5: silent-worsening hole closed at every density);
  - endpoint snap failures alone neither revert nor defer at low density
    (deferral semantics stay dense-only).

The revert mechanics are exercised with a controlled degrading snap (a
monkeypatched Router.anchor_snap that applies the REAL snap and then forces a
guaranteed +1 crossing by straddling another edge's segment): a natural
low-density degradation has never been observed in the corpus (that is exactly
why the bug stayed silent), so the degradation is constructed,
deterministic and self-verifying (the monkeypatch asserts the worsening it
injects is really measured before returning).
"""
import copy
import io
import json
import math
import sys

import pytest

from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig, ANCHOR_SNAP_DENSE_E_OVER_N
from stdraw.recipes import run as recipes_run
from stdraw.routing import Router

real_snap = Router.anchor_snap

# Low density (E/N = 11/8 = 1.375 < 1.6): a ring plus three chords -- enough
# edges for the snap to have candidates, small enough to stay fast.
CLD = """
graph "t5-low-density-revert"
var A "A"
var B "B"
var C "C"
var D "D"
var E "E"
var F "F"
var G "G"
var H "H"
A -> + B
B -> + C
C -> + D
D -> + E
E -> + F
F -> + G
G -> + H
H -> + A
A -> + D
B -> + E
C -> + F
"""


def _run(cld_text, manual=None):
    """Drive the pipeline.  Default: the MANUAL path (--from-layout
    equivalent) -- since edge placement rules v1 the AUTO path assigns
    standard anchors by construction and never runs anchor_snap (spec §8),
    so the snap revert mechanics (retained for manual layouts) are
    exercised on the manual path."""
    g = parse(cld_text)
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        if manual is None:
            from stdraw.layout_auto import layout as _layout
            v4 = _layout(g, AutoConfig(), "straight")
            nodes = {k: {"x": p["x"], "y": p["y"]}
                     for k, p in v4["nodes"].items()}
            manual = {"nodes": nodes, "viewBox": None, "source": "t5-test"}
        from stdraw.layout_auto import layout
        v4 = layout(g, AutoConfig(), "straight", manual=manual)
    finally:
        sys.stderr = old
    return v4, err.getvalue()


def _seg_cross(p1, p2, p3, p4):
    def d(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = d(p3, p4, p1), d(p3, p4, p2)
    d3, d4 = d(p1, p2, p3), d(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _pairs_cross(i_pts, j_pts):
    for s1 in zip(i_pts[:-1], i_pts[1:]):
        for s2 in zip(j_pts[:-1], j_pts[1:]):
            if _seg_cross(s1[0], s1[1], s2[0], s2[1]):
                return True
    return False


def _crossing_pairs(router, routes):
    idx = sorted(routes.keys())
    total = 0
    for x in range(len(idx)):
        for y in range(x + 1, len(idx)):
            ia, ib = idx[x], idx[y]
            ea, eb = router.edges[ia], router.edges[ib]
            if ea[0] in eb or ea[1] in eb:
                continue
            total += 1 if _pairs_cross(routes[ia]["points"],
                                       routes[ib]["points"]) else 0
    return total


def _inject_guaranteed_crossing(router, routes):
    """Straddle another edge's segment: the endpoint and its neighbour point
    land on opposite sides of the mid-segment of some disjoint edge -> the
    connecting segment provably crosses it.  Returns True iff a worsening was
    really measured (self-verifying fixture)."""
    pre = _crossing_pairs(router, routes)
    keys = sorted(routes.keys())
    for i in keys:
        pts = routes[i]["points"]
        if len(pts) < 2:
            continue
        for j in keys:
            if j == i:
                continue
            ei, ej = router.edges[i], router.edges[j]
            if ei[0] in ej or ei[1] in ej:
                continue
            jp = routes[j]["points"]
            mid = len(jp) // 2 - 1
            a, b = jp[mid], jp[mid + 1]
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 8.0:
                continue
            nx_, ny_ = -(b[1] - a[1]), (b[0] - a[0])
            norm = math.hypot(nx_, ny_)
            nx_, ny_ = nx_ / norm, ny_ / norm
            q = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
            old0, old1 = list(pts[0]), list(pts[1])
            pts[0] = [q[0] - 3.0 * nx_, q[1] - 3.0 * ny_]
            pts[1] = [q[0] + 3.0 * nx_, q[1] + 3.0 * ny_]
            post = _crossing_pairs(router, routes)
            if post > pre:
                return True
            pts[0], pts[1] = old0, old1
    return False


def test_probe_threshold_unchanged():
    assert ANCHOR_SNAP_DENSE_E_OVER_N == 1.6


def _run_auto(cld_text):
    """The AUTO path under edge placement rules v1 (snap skipped)."""
    g = parse(cld_text)
    from stdraw.layout_auto import layout
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        v4 = layout(g, AutoConfig(), "straight")
    finally:
        sys.stderr = old
    return v4, err.getvalue()


def test_auto_path_skips_snap_by_construction(monkeypatch):
    """Edge placement rules v1: on the LAYERED auto path anchor_snap is
    never called (endpoints pre-assigned to standard anchors by edgerules);
    on the constructed engines (v1-exempt, e.g. this ring graph) the legacy
    snap keeps running.  Either way every delivered endpoint lands on the
    16-anchor set."""
    calls = []
    monkeypatch.setattr(Router, "anchor_snap",
                        lambda self, routes, max_sweeps=4:
                        calls.append(1) or real_snap(self, routes, max_sweeps))
    v4, err = _run_auto(CLD)
    placement = v4["meta"].get("placement")
    if placement == "layered":
        assert not calls
    else:                      # constructed engine: v1-exempt, legacy snap
        assert calls
    from stdraw.anchors import standard_anchors
    for e in v4["edges"]:
        for end, node in (("a", e["a"]), ("b", e["b"])):
            p = v4["nodes"][node]
            pts = {(ax, ay) for _, ax, ay in
                   standard_anchors(p["x"], p["y"], p["w"] / 2.0,
                                    v4["meta"].get("cardH", 42) / 2.0)}
            ep = e["anchors"][end]
            assert any(abs(ep[0] - ax) < 0.6 and abs(ep[1] - ay) < 0.6
                       for ax, ay in pts), \
                f"endpoint {ep} not on {node}'s standard anchor set"


def test_low_density_revert_on_degrading_snap(monkeypatch):
    """A degrading snap must be reverted wholesale: the delivered layout is
    identical to the honest pre-snap delivery and the measured reason is on
    stderr."""
    def degrading_snap(self, routes, max_sweeps=4):
        degrading_snap.pre = {i: copy.deepcopy(routes[i]) for i in routes}
        report = real_snap(self, routes, max_sweeps)
        assert _inject_guaranteed_crossing(self, routes), \
            "fixture failed to inject a measured worsening"
        report = dict(report)
        report["moved"] = report["moved"] + 1
        return report

    monkeypatch.setattr(Router, "anchor_snap", degrading_snap)
    v4_deg, err_deg = _run(CLD)

    assert "REVERTED" in err_deg
    assert "pre-snap routes kept" in err_deg
    # the measured reason is exactly the probe's crossings recount
    assert "crossings" in err_deg
    # revert contract: the delivered geometry is the honest pre-snap state
    # (routes only ever leave layout() with one global dx/dy delivery shift,
    # so all per-edge deltas must collapse to a single constant offset)
    pre = degrading_snap.pre
    dx0 = dy0 = None
    for k in sorted(pre.keys()):
        dp = v4_deg["edges"][k]["route"]["points"]
        pp = pre[k]["points"]
        assert len(dp) == len(pp)
        for d, p in zip(dp, pp):
            dx, dy = d[0] - p[0], d[1] - p[1]
            if dx0 is None:
                dx0, dy0 = dx, dy
            assert abs(dx - dx0) <= 0.11 and abs(dy - dy0) <= 0.11


def test_low_density_no_revert_without_degradation(monkeypatch):
    """A snap-report change that does NOT worsen crossings/coincidence is
    kept: the probe must not over-trigger."""
    def shifting_snap(self, routes, max_sweeps=4):
        report = real_snap(self, routes, max_sweeps)
        for i in sorted(routes.keys()):
            pts = routes[i]["points"]
            if len(pts) > 3:
                pts[len(pts) // 2][1] += 0.6   # sub-gate interior nudge
                break
        return report

    monkeypatch.setattr(Router, "anchor_snap", shifting_snap)
    v4_shift, err_shift = _run(CLD)
    monkeypatch.setattr(Router, "anchor_snap",
                        lambda self, routes, max_sweeps=4:
                        real_snap(self, routes, max_sweeps))
    v4_ref, _ = _run(CLD)
    assert "REVERTED" not in err_shift
    assert _layout_json(v4_shift) != _layout_json(v4_ref)


def test_low_density_endpoint_failures_do_not_revert(monkeypatch):
    """Unplaceable endpoints at low density: honest stderr report, no revert,
    no deferral record (deferral stays dense-only)."""
    def failing_snap(self, routes, max_sweeps=4):
        report = real_snap(self, routes, max_sweeps)
        report = dict(report)
        report["failures"] = sorted(
            report["failures"] + [{"edge": "A->D", "end": "a"}])
        return report

    monkeypatch.setattr(Router, "anchor_snap", failing_snap)
    v4_fail, err_fail = _run(CLD)
    monkeypatch.setattr(Router, "anchor_snap",
                        lambda self, routes, max_sweeps=4:
                        real_snap(self, routes, max_sweeps))
    v4_ref, _ = _run(CLD)
    assert "REVERTED" not in err_fail
    assert "could not be placed" in err_fail
    assert v4_fail["meta"].get("anchor_snap_deferred") is None
    # failures alone keep the snapped state (identical to the normal run)
    assert _layout_json(v4_fail) == _layout_json(v4_ref)


def _layout_json(v4):
    return json.dumps({"nodes": v4["nodes"], "edges": v4["edges"],
                       "meta": {k: v for k, v in v4["meta"].items()
                                if k != "timing"}},
                      sort_keys=True, ensure_ascii=True)
