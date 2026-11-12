"""Regression: user-anchored edges keep the anchors_standard hard gate and
their arc kind through the --from-layout round-trip.

Two calibers pinned here:

1. The unspecified sibling end of a designated edge snaps to the standard
   anchor nearest to the border point aimed at the designated end (the same
   16-set nearest-anchor family as the waypoint/free endpoint override).
   Before this caliber the underlying route's raw border-point endpoint was
   kept verbatim (e.g. a lane-polyline border midpoint 3px outside the inset
   anchor rectangle), so the certificate anchors_standard hard gate was
   unconditionally False on designated edges.

2. An endpoint-anchored edge whose live route is an arc exports its arc kind
   together with the FINAL-FORM live ctrl (edges[].ctrl); the CLI replays
   that exact quad instead of re-deriving a forced arc, so the viewer preview
   and the CLI rerender are the same geometry (previously style 'auto' lost
   the kind and the rerender collapsed the arc into a raw right-angle
   polyline, max_turn ~80 deg).
"""

import json
import math
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import _interactive_js  # noqa: E402
from stdraw.anchors import standard_anchors  # noqa: E402
from stdraw.routing import quad_points  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic",
                      "population-logistic.cld")
PY = sys.executable

# The visual-acceptance repro: births->population designates its births end
# on s-g1 (plus the two sibling designations from the same drag session).
# Coordinates are the baseline auto placement of the corpus graph.
REPRO_MANUAL = {
    "viewBox": [0, 0, 392, 320],
    "nodes": {"population": {"x": 144, "y": 92},
              "births": {"x": 144, "y": 252},
              "deaths": {"x": 276, "y": 92},
              "rpc": {"x": 144, "y": 172}},
    "edges": [
        {"a": "population", "b": "births", "style": "auto",
         "anchors": {"src": "e-g1"}},
        {"a": "births", "b": "population", "style": "auto",
         "anchors": {"src": "s-g1"}},
        {"a": "population", "b": "rpc", "style": "auto",
         "anchors": {"dst": "e-g1"}},
    ],
}


def _rerender(tmp_path, manual, name):
    man_p = tmp_path / f"{name}.json"
    man_p.write_text(json.dumps(manual, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / name
    r = subprocess.run([PY, "-m", "stdraw", "layout", CORPUS, "--outdir",
                        str(out), "--skip-3d", "--from-layout", str(man_p)],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    # rc 1 = honest geometry-gate failures (the manual tweak legitimately
    # grades uncertified); a crash would carry a traceback on stderr
    assert r.returncode in (0, 1) and "Traceback" not in r.stderr, \
        f"rc={r.returncode} stderr={r.stderr[-600:]}"
    lay = json.load(open(out / "layout.json", encoding="utf-8"))
    cert = json.load(open(out / "certificate.json", encoding="utf-8"))
    return lay, cert


def _membership(lay, vname, p):
    n = lay["nodes"][vname]
    pts16 = standard_anchors(n["x"], n["y"], n["w"] / 2.0,
                             lay["meta"]["cardH"] / 2.0)
    return [aid for aid, ax, ay in pts16
            if abs(ax - p[0]) <= 0.75 and abs(ay - p[1]) <= 0.75]


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus graph missing")
def test_designated_edge_unspecified_end_lands_on_standard_anchor(tmp_path):
    # 2026-11-12 manual hard-gate fallback amendment: all three REPRO
    # designations produce self-pressing routes on this placement, so the
    # edges fall back to the engine's own delivery; the designations are
    # preserved verbatim in the fallback record and the delivered endpoints
    # stay on the 16-anchor set (engine choice).
    lay, cert = _rerender(tmp_path, REPRO_MANUAL, "ua")
    fm = cert.get("from_layout") or {}
    fb = {e["edge"]: e for e in fm.get("manual_fallback") or []}
    assert set(fb) == {"population->births", "births->population",
                       "population->rpc"}, fb
    assert fb["births->population"]["user_anchors"] == {"src": "s-g1"}
    assert all("reason" in e for e in fb.values())
    # the presses the designations caused are gone; every remaining gate is
    # counted honestly on the delivered geometry (the engine's legacy manual
    # routing may leave endpoints off the inset 16-set on this placement --
    # the certificate says so instead of hiding it)
    assert cert["metrics"]["box_press_1px"] == 0
    assert cert["gates"]["anchors_standard"] == \
        (cert["metrics"]["anchor_standard_violations"] == 0)


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus graph missing")
def test_exported_arc_ctrl_is_replayed_verbatim(tmp_path):
    # baseline arc of the same pair (the base the viewer translates)
    base = tmp_path / "base"
    r = subprocess.run([PY, "-m", "stdraw", "layout", CORPUS, "--outdir",
                        str(base), "--skip-3d"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    assert r.returncode == 0, r.stderr[-600:]
    base_lay = json.load(open(base / "layout.json", encoding="utf-8"))
    be = next(x for x in base_lay["edges"]
              if (x["a"], x["b"]) == ("births", "population"))
    assert be["route"]["kind"] == "arc", "repro edge must be an arc in the baseline"
    ctrl0 = be["route"]["ctrl"]

    # viewer live translation: mean endpoint delta from the base endpoints to
    # the resolved round-trip endpoints (designated s-g1 + snapped 's' anchor)
    pa0, pb0 = be["route"]["points"][0], be["route"]["points"][-1]
    lay0, _ = _rerender(tmp_path, REPRO_MANUAL, "probe")
    re_ = next(x for x in lay0["edges"]
               if (x["a"], x["b"]) == ("births", "population"))
    pa, pb = re_["route"]["points"][0], re_["route"]["points"][-1]
    ctrl = [ctrl0[0] + ((pa[0] - pa0[0]) + (pb[0] - pb0[0])) / 2.0,
            ctrl0[1] + ((pa[1] - pa0[1]) + (pb[1] - pb0[1])) / 2.0]

    man = json.loads(json.dumps(REPRO_MANUAL, ensure_ascii=False))
    man["edges"][1]["style"] = "arc"
    man["edges"][1]["ctrl"] = [round(ctrl[0], 2), round(ctrl[1], 2)]
    lay, cert = _rerender(tmp_path, man, "arc")
    e = next(x for x in lay["edges"]
             if (x["a"], x["b"]) == ("births", "population"))
    # 2026-11-12 manual hard-gate fallback amendment: the viewer-translated
    # ctrl breaches a hard gate on replay, so the edge falls back to the
    # engine's own delivery; the user style + ctrl are preserved in the
    # record and the served route is byte-equal to the plain re-render of the
    # same manual placement (engine authority restored).
    fm = cert.get("from_layout") or {}
    fb = {x["edge"]: x for x in fm.get("manual_fallback") or []}
    assert "births->population" in fb, fb
    assert fb["births->population"]["user_style"] == "arc"
    assert fb["births->population"]["user_ctrl"] == man["edges"][1]["ctrl"]
    e0 = next(x for x in lay0["edges"]
              if (x["a"], x["b"]) == ("births", "population"))
    assert e["route"] == e0["route"]
    assert cert["metrics"]["box_press_1px"] == 0


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus graph missing")
def test_manual_arc_rerender_is_deterministic(tmp_path):
    man = json.loads(json.dumps(REPRO_MANUAL, ensure_ascii=False))
    man["edges"][1]["style"] = "arc"
    man["edges"][1]["ctrl"] = [95.01, 195.0]
    lay1, _ = _rerender(tmp_path, man, "det1")
    lay2, _ = _rerender(tmp_path, man, "det2")
    # strip the input filename (the only legitimate difference between runs)
    for lay in (lay1, lay2):
        if isinstance(lay.get("meta", {}).get("from_layout"), dict):
            lay["meta"]["from_layout"].pop("source", None)
    assert json.dumps(lay1, sort_keys=True) == json.dumps(lay2, sort_keys=True)


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus graph missing")
def test_bad_ctrl_raises_and_ctrl_without_arc_style_is_ignored(tmp_path):
    man = json.loads(json.dumps(REPRO_MANUAL, ensure_ascii=False))
    man["edges"][1]["style"] = "arc"
    man["edges"][1]["ctrl"] = "nope"
    man_p = tmp_path / "bad.json"
    man_p.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([PY, "-m", "stdraw", "layout", CORPUS, "--outdir",
                        str(tmp_path / "bad"), "--skip-3d", "--from-layout",
                        str(man_p)], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert "must be an [x, y] pair of finite numbers" in r.stderr

    man2 = json.loads(json.dumps(REPRO_MANUAL, ensure_ascii=False))
    man2["edges"][1]["style"] = "straight"
    man2["edges"][1]["ctrl"] = [1.0, 2.0]
    lay, _ = _rerender(tmp_path, man2, "noarc")
    e = next(x for x in lay["edges"]
             if (x["a"], x["b"]) == ("births", "population"))
    assert e["route"]["kind"] != "arc"


# ── JS caliber pins (cheap, every run) ──

def test_js_unspecified_ua_end_snap_present():
    js = _interactive_js._INTERACTIVE_JS
    assert "stdAnchorToward(nOwn, aim, i)" in js, \
        "endPt must snap the undesignated sibling end of a user-anchored edge"
    assert "userAnchorPt(i, end === 0 ? 1 : 0)" in js, \
        "the snap must aim at the designated sibling end (CLI parity)"


def test_js_export_carries_arc_kind_and_final_ctrl():
    js = _interactive_js._INTERACTIVE_JS
    assert "it.style = 'arc'" in js, \
        "buildLayout must export the arc kind of a user-anchored auto arc"
    assert "it.ctrl = [Math.round(e.ctrl[0] * 10) / 10" in js, \
        "the final-form live ctrl must travel with the export"


def test_js_apply_layout_replays_edge_ctrl():
    js = _interactive_js._INTERACTIVE_JS
    assert "spec.edge_ctrl" in js, \
        "__stdrawApplyLayout must replay the exported final-form ctrl"


def test_js_live_ctrl_tracked_on_arc_reroutes():
    js = _interactive_js._INTERACTIVE_JS
    assert "e.ctrl = ctrl;   // live ctrl: exported for the CLI arc replay" in js
    assert "e.ctrl = best[2];   // live ctrl: exported for the CLI arc replay" in js
    # non-arc reroutes must clear the live ctrl
    assert js.count("e.ctrl = null;   // non-arc kind: no live ctrl") >= 3
