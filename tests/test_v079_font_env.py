#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Font-environment robustness regression (ref-scrubbed, v0.7.9).

Defect: the interactive delivery face anchored edge endpoints on the PLANNED
card geometry (engine-side text metrics, invisible to browser font settings),
while the browser can inflate the DOM text (minimum font size / user font
scale) -> rendered cards overflow the plan, arrows float 30~70px off the
frame (jacky's Edge outage, 11 edges / 9 floating).

Fix under test: the interactive layer measures the ACTUAL DOM text geometry
post-render (getComputedTextLength/getBBox), grows the card rect (grow-only)
to fit with the textmetrics.py padding discipline, and re-anchors / re-routes
every edge on the new borders at 0px.

Layers:
  A. no-op determinism: in the default (matching) font environment the initial
     sync must be a strict no-op (rect attrs byte-equal to the static render,
     edge endpoints untouched) -- the deterministic delivery contract holds;
  B. inflated-font environment: force font-size via injected CSS (simulating
     Edge's minimum font size clamp), sync, then EVERY edge endpoint must sit
     on its (grown) card border at 0px -- 11/11 on the HDD wide-ticker graph;
  C. reset keeps the contract: reset() re-syncs, endpoints stay 0px.

SKIP (exit 2 via pytest skip) when playwright is unavailable.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
CLD = os.path.join(ROOT, "tests", "data", "hdd-wide-tickers.cld")
INFLATE_CSS = ("#stdraw-svg [data-node] text{font-size:20px !important;"
               "font-weight:bold !important}")


def _pin_local_stdraw():
    """Same-tree self-check (ref-scrubbed pattern): force stdraw from this tree."""
    if not os.path.isfile(os.path.join(ROOT, "stdraw", "__init__.py")):
        pytest.skip("stdraw package not found in this tree")
    for f in [m for m in sys.meta_path
              if "__editable__" in str(getattr(m, "__module__", ""))]:
        sys.meta_path.remove(f)
    for m in list(sys.modules):
        if m == "stdraw" or m.startswith("stdraw."):
            del sys.modules[m]
    sys.path.insert(0, ROOT)
    import stdraw
    if os.path.realpath(os.path.dirname(stdraw.__file__)) != \
            os.path.realpath(os.path.join(ROOT, "stdraw")):
        pytest.skip("stdraw not loaded from this tree")


def _render_demo(tmp):
    out = os.path.join(tmp, "hdd-wide")
    r = subprocess.run([PY, "-m", "stdraw", "layout", CLD,
                        "--outdir", out, "--skip-3d"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    assert r.returncode in (0, 1), f"CLI exit {r.returncode}: {r.stderr[-400:]}"
    demo = os.path.join(out, "demo-2d.html")
    assert os.path.isfile(demo), "demo-2d.html not produced"
    with open(demo, encoding="utf-8") as f:
        html = f.read()
    payload = json.loads(
        html.split('<script id="stdraw-data" type="application/json">')[1]
            .split("</script>")[0].replace("<\\/", "</"))
    rect_list = re.findall(
        r'<g data-node="([^"]+)"><rect x="(-?[\d.]+)" y="(-?[\d.]+)"'
        r' width="([\d.]+)" height="([\d.]+)"', html)
    rects = {m[0]: tuple(float(x) for x in m[1:]) for m in rect_list}
    # associate rects with nodes via the group order (same order as payload)
    node_ids = [n["id"] for n in payload["nodes"]]
    assert len(rects) == len(node_ids), "rect/node count mismatch"
    assert set(rects) == set(node_ids), "rect/node id mismatch"
    return demo, payload, rects


def _dist_rect(px, py, cx, cy, hw, hh):
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def _endpoint_violations(pg, tol=0.5):
    """All edge endpoints off their card border (dist > tol) using the LIVE
    node geometry (post-sync) -- the honest 0px-on-frame assertion."""
    geoms = {g[0]: g for g in pg.evaluate("window.__stdrawNodeGeom()")}
    pts = pg.evaluate("window.__stdrawEdgePts()")
    edges_ab = pg.evaluate(
        "(function(){ var d=JSON.parse("
        "document.getElementById('stdraw-data').textContent);"
        " return d.edges.map(function(e){return [e.a, e.b];}); })()")
    bad = []
    for i, (a, b) in enumerate(edges_ab):
        for v, p in ((a, pts[i][0]), (b, pts[i][-1])):
            g = geoms[v]
            d = _dist_rect(p[0], p[1], g[1], g[2], g[3] / 2.0, g[4] / 2.0)
            if d > tol:
                bad.append((i, a, b, v, round(d, 2)))
    return bad


def test_font_env_robustness():
    _pin_local_stdraw()
    tmp = tempfile.mkdtemp(prefix="stdraw-v079-fontenv-")
    try:
        demo, payload, static_rects = _render_demo(tmp)
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1600, "height": 1500})
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto("file://" + demo.replace("\\", "/"))
            pg.wait_for_timeout(400)

            # ── A. baseline: initial sync is a strict no-op ──
            assert pg.evaluate("window.__stdrawSyncDomGeometry()") is False, \
                "initial sync mutated geometry in the matching environment"
            live_rects = pg.evaluate(
                "(function(){ var o={};"
                " document.querySelectorAll('[data-node]').forEach(function(g){"
                "  var r=g.querySelector('rect'); var b=r.getBBox();"
                "  o[g.getAttribute('data-node')]=[b.x,b.y,b.width,b.height];"
                " }); return o; })()")
            for v, (x, y, w, h) in static_rects.items():
                lv = live_rects[v]
                assert abs(lv[2] - w) <= 0.51 and abs(lv[3] - h) <= 0.51, \
                    f"{v}: baseline rect drifted {lv} vs static {(x, y, w, h)}"
            base_pts = pg.evaluate("window.__stdrawEdgePts()")
            payload_pts = [e["pts"] for e in payload["edges"]]
            for i, (lp, pp) in enumerate(zip(base_pts, payload_pts)):
                if len(lp) == 2 and len(pp) == 2:
                    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) <= 0.51
                               for a, b in zip(lp, pp)), \
                        f"edge {i}: baseline endpoints moved"

            # ── B. inflated DOM font (Edge minimum-font-size simulation) ──
            pg.add_style_tag(content=INFLATE_CSS)
            pg.wait_for_timeout(100)
            grew = pg.evaluate("window.__stdrawSyncDomGeometry()")
            assert grew is True, "inflated font env: sync must resize+re-anchor"
            bad = _endpoint_violations(pg)
            assert not bad, f"inflated env: endpoints off frame: {bad}"
            n_edges = len(payload["edges"])
            geoms = pg.evaluate("window.__stdrawNodeGeom()")
            grew_cards = [g[0] for g in geoms
                          if g[4] > payload["cardH"] + 0.5
                          or abs(g[3] - static_rects[g[0]][2]) > 0.51]
            assert grew_cards, "inflated env: no card actually grew"
            # every card must now cover its rendered text (no overflow)
            overflow = pg.evaluate(
                "(function(){ var out=[];"
                " document.querySelectorAll('[data-node]').forEach(function(g){"
                "  var r=g.querySelector('rect').getBBox();"
                "  g.querySelectorAll('text').forEach(function(t){"
                "    var b=t.getBBox();"
                "    if (b.x < r.x - 0.5 || b.x + b.width > r.x + r.width + 0.5"
                "        || b.y < r.y - 0.5 || b.y + b.height > r.y + r.height + 0.5)"
                "      out.push(g.getAttribute('data-node'));"
                "  });"
                " }); return out; })()")
            assert not overflow, f"text overflows card after sync: {overflow}"

            # ── C. reset keeps the contract ──
            pg.click("#stdraw-reset")
            pg.wait_for_timeout(150)
            bad = _endpoint_violations(pg)
            assert not bad, f"after reset: endpoints off frame: {bad}"
            assert not errors, f"page errors: {errors}"
            browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
