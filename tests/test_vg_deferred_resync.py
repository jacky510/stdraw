"""vg route dual geometry: measured polyline must equal the rendered path_d.

A vg route carries ``points`` (the dense polyline the certificate metrics,
``edges[].anchors`` and geometry check 13 measure) AND ``vg_corners`` +
``vg_fillets`` (what ``path_d`` is rendered from).  The inline endpoint
relocation passes (midband / fan) move ``points[0]`` / ``points[-1]`` in
place without writing the corner back, and ``Router.anchor_snap`` is what
normally re-derives ``points`` from the corners.  When the snap probe is
DEFERRED (dense, E/N >= 1.6) or REVERTED the pre-snap routes are restored
and the two geometries used to ship inconsistent: check 13 then failed on
13 tier-A graphs (2.4-32 px, random-n10-i12 .. random-n20-*).

Fix (docs/routing-gates.md section 3 item 7): the restore paths re-derive
``points`` of every vg route from its own corners ("measure where you
draw").  This module pins (1) the helper mechanics, (2) the real corpus
trigger end to end through the CLI deliverables.
"""
import io
import json
import os
import re
import subprocess
import sys

import pytest

from stdraw.dsl import parse
from stdraw.layout_auto import _resync_vg_points
from stdraw.routing import Router
from stdraw.visibility import dense_geometry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I12 = os.path.join(ROOT, "benchmarks", "corpus", "random", "random-n10-i12.cld")


def _vg_route(shift=(0.0, 0.0), corner_shift=None):
    """A vg route as the candidate pool creates it (points ==
    dense_geometry(corners, fillets)), optionally with the first dense
    point displaced by ``shift`` (what midband does in place)."""
    corners = [(10.0, 10.0), (50.0, 10.0), (50.0, 40.0)]
    fillets = []           # sharp corners: dense == corners exactly
    if corner_shift is not None:
        corners = [tuple(c + d for c, d in zip(corners[0], corner_shift))] + corners[1:]
    pts = [[px, py] for px, py in dense_geometry(corners, fillets)]
    pts[0] = [pts[0][0] + shift[0], pts[0][1] + shift[1]]
    return {"kind": "vg", "points": pts,
            "vg_corners": [list(c) for c in corners], "vg_fillets": fillets}


def test_resync_rewrites_inconsistent_vg_route_to_rendered_corners():
    rt = _vg_route(shift=(2.4, 0.0))
    assert rt["points"][0] != rt["vg_corners"][0]
    assert _resync_vg_points({0: rt}) == 1
    assert rt["points"] == [[10.0, 10.0], [50.0, 10.0], [50.0, 40.0]]
    assert rt["points"][0] == rt["vg_corners"][0]


def test_resync_untouched_when_geometries_already_agree():
    rt = _vg_route()
    before = [list(p) for p in rt["points"]]
    assert _resync_vg_points({0: rt}) == 0
    assert rt["points"] == before


def test_resync_ignores_non_vg_routes_and_missing_corners():
    poly = {"kind": "poly", "points": [[0.0, 0.0], [9.0, 9.0]]}
    vg_no_corners = {"kind": "vg", "points": [[0.0, 0.0], [9.0, 9.0]],
                     "vg_corners": None, "vg_fillets": None}
    shifted = _vg_route(shift=(0.0, -3.0))
    assert _resync_vg_points({0: poly, 1: vg_no_corners, 2: shifted}) == 1
    assert poly["points"] == [[0.0, 0.0], [9.0, 9.0]]
    assert vg_no_corners["points"] == [[0.0, 0.0], [9.0, 9.0]]
    assert shifted["points"][0] == shifted["vg_corners"][0]


def _has_solver():
    try:
        import ortools  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_solver(),
                    reason="corpus trigger random-n10-i12 defers anchor_snap "
                           "only under the cp-sat-layered engine caliber "
                           "(CI installs the [solver] layer)")
def test_dense_deferral_delivers_measured_equals_rendered(tmp_path):
    """random-n10-i12: anchor_snap DEFERRED (E/N=1.60, 1 endpoint unanchored)
    with one vg route whose pre-snap polyline had been shifted by 2.4 px.
    Before the fix the delivered path_d started 2.4 px away from the
    measured polyline (check 13 fail); now both are the corner geometry."""
    out = tmp_path / "i12"
    r = subprocess.run([sys.executable, "-m", "stdraw", "layout", I12,
                        "--outdir", str(out), "--skip-3d"],
                       capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert "anchor_snap DEFERRED" in r.stderr, r.stderr[-800:]
    assert "vg polyline(s) resynced" in r.stderr, r.stderr[-800:]

    with open(out / "layout.json", encoding="utf-8") as f:
        layout = json.load(f)
    deferred = layout["meta"]["anchor_snap_deferred"]
    assert deferred is not None and deferred["vg_resynced"] >= 1

    vg_edges = [e for e in layout["edges"] if e["route"].get("kind") == "vg"]
    assert vg_edges, "the trigger graph is expected to deliver vg routes"
    for e in vg_edges:
        m = re.match(r"M (-?[\d.]+) (-?[\d.]+)", e["route"]["path_d"])
        assert m, e["route"]["path_d"][:40]
        assert e["anchors"]["a"] == [float(m.group(1)), float(m.group(2))]
        assert e["route"]["points"][0] == e["anchors"]["a"]

    with open(out / "geometry_report.json", encoding="utf-8") as f:
        rep = json.load(f)
    check13 = [c for c in rep["checks"] if c["check"].startswith("13.")]
    assert len(check13) == 1
    assert check13[0]["pass"] in (True, "True"), check13[0]["detail"]


# --- REVERTED path (low-density branch): same restore path, same resync -------
# The corpus never degrades naturally at low density (that is why the revert
# stayed silent), so the probe's own criterion is forced deterministically:
# Router.final_crossing_pairs reports one pair more after every anchor_snap
# call than before it, so the low-density branch measures
# ``post > pre`` right after the snap and MUST take the revert branch on every
# platform.  (Injecting a geometric regression into the snapped routes and
# re-measuring it with the engine counter is platform fragile: the wall-time
# budgeted cp-sat incumbent yields a different layout in CI, where the real
# chain no longer saw the injected worsening.)  The real snap still runs, so
# the restored pre-snap routes are the genuine chain output, including the
# vg route whose polyline midband had shifted away from its rendered corners.
# The dense trigger graph is pushed into the low-density branch by raising
# the density threshold for the test only.

@pytest.mark.skipif(not _has_solver(),
                    reason="random-n10-i12 delivers a shifted vg route only "
                           "under the cp-sat-layered engine caliber")
def test_low_density_revert_resyncs_vg_route(monkeypatch):
    import stdraw.layout_auto as la
    real_snap = Router.anchor_snap
    real_fcp = Router.final_crossing_pairs
    snaps = {"n": 0}

    def growing_fcp(self, out):
        # probe input forced to worsen by one pair per snap call
        return real_fcp(self, out) + snaps["n"]

    def counting_snap(self, routes, max_sweeps=4):
        rep = real_snap(self, routes, max_sweeps)
        snaps["n"] += 1
        return rep

    monkeypatch.setattr(Router, "final_crossing_pairs", growing_fcp)
    monkeypatch.setattr(Router, "anchor_snap", counting_snap)
    monkeypatch.setattr(la, "ANCHOR_SNAP_DENSE_E_OVER_N", 99.0)
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        v4 = la.layout(parse(open(I12, encoding="utf-8").read()), la.AutoConfig(), "straight")
    finally:
        sys.stderr = old
    text = err.getvalue()
    m = re.search(r"anchor_snap REVERTED \(E/N=[\d.]+\): crossings (\d+)->(\d+)", text)
    assert m, text[-600:]
    assert int(m.group(2)) == int(m.group(1)) + 1
    assert "vg polyline(s) resynced" in text, text[-600:]
    assert snaps["n"] >= 1
    assert v4["meta"].get("anchor_snap_deferred") is None
    vg = [e for e in v4["edges"] if e["route"].get("path_d")]
    assert vg, "expected the trigger graph's vg route"
    for e in vg:
        mm = re.match(r"M (-?[\d.]+) (-?[\d.]+)", e["route"]["path_d"])
        assert mm, e["route"]["path_d"][:40]
        assert e["route"]["points"][0] == [float(mm.group(1)), float(mm.group(2))]
        assert e["anchors"]["a"] == e["route"]["points"][0]
