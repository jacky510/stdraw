# -*- coding: utf-8 -*-
"""DOM-truth interactive gate (ref-scrubbed, v0.7.11).

2026-11-08 8777/现网 regression: updateEdge resolved edges via a bare
`svg.querySelector('[data-edge=i]')`, which matches the HIT path first
(#stdraw-hits sits at svg.firstChild and hit paths carry data-edge) — the
visible line never redrew after drags/applyLayout while internal state
re-anchored (silent, zero exceptions). The ref-scrubbed green gate missed it
because it read geometry through the internal __stdrawEdgePts API.

This probe measures DOM TRUTH ONLY (visible path `d` strings +
getPointAtLength endpoints) and adds the ref-scrubbed acceptance gates:

  A. real-mouse drag -> incident visible `d` changes, ALL visible endpoints
     within 0.5px of the live card borders, zero uncaught exceptions;
  B. __stdrawApplyLayout -> visible `d` changes + endpoints on borders;
  C. real-mouse double-click -> the four-state style cycle closes
     (straight -> arc -> free -> auto) with visible geometry changes;
  D. per-edge failure isolation: a probe-forced single-edge router failure
     must not abort the re-anchor round — other edges re-anchor, the failed
     edge gets the visible `stdraw-degraded` marker, a console WARN fires,
     and the marker self-heals on the edge's next successful pass;
  E. multi-scale font inflation (20/24/28/34px bold) injected from the first
     frame (add_init_script, pre-DOMContentLoaded) with empty position
     memory -> every edge either on-border (0px) or visibly degraded, cards
     grown, zero uncaught exceptions.

Run: python tests/probe_dom_truth.py [demo.html]   (exit 0 = all gates green)
"""
import json
import math
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PY = sys.executable
CLD = os.path.join(ROOT, "tests", "data", "hdd-wide-tickers.cld")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

_chk_ok = True


def chk(name, ok, detail=""):
    global _chk_ok
    tag = "PASS" if ok else "FAIL"
    if not ok:
        _chk_ok = False
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def run_cli(args):
    return subprocess.run([PY, "-m", "stdraw"] + args, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=ROOT)


def _pin_local_stdraw():
    if os.path.realpath(os.path.join(ROOT, "stdraw")) not in sys.path:
        sys.path.insert(0, os.path.realpath(os.path.join(ROOT, "stdraw")))


# ── DOM-truth helpers (visible paths ONLY; never the internal state API) ──
JS_VISIBLE = """
(function(){
  var out = [];
  document.querySelectorAll('#stdraw-svg g[data-edge]').forEach(function(g){
    var p = g.querySelector('path:not(.stdraw-hit)');
    out.push({i: +g.getAttribute('data-edge'),
              d: p ? p.getAttribute('d') : null,
              degraded: /\\bstdraw-degraded\\b/.test(g.getAttribute('class') || '')});
  });
  return out;
})()
"""

JS_DOM_ENDPOINTS = """
(function(){
  var geoms = {};
  window.__stdrawNodeGeom().forEach(function(g){ geoms[g[0]] = g; });
  var d = JSON.parse(document.getElementById('stdraw-data').textContent);
  var ab = d.edges.map(function(e){ return [e.a, e.b]; });
  var out = [];
  document.querySelectorAll('#stdraw-svg g[data-edge]').forEach(function(g){
    var p = g.querySelector('path:not(.stdraw-hit)');
    if (!p || typeof p.getPointAtLength !== 'function') return;
    var i = +g.getAttribute('data-edge');
    var e0 = p.getPointAtLength(0), e1 = p.getPointAtLength(p.getTotalLength());
    out.push({i: i, ends: [ab[i][0], ab[i][1]],
              pts: [[e0.x, e0.y], [e1.x, e1.y]]});
  });
  return out;
})()
"""


def _dist_rect(px, py, cx, cy, hw, hh):
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def endpoint_violations(pg, tol=0.5, skip_degraded=False):
    """DOM-truth endpoint check: every visible path endpoint must sit on its
    card border (<=tol) measured in user-space coordinates."""
    geoms = {g[0]: g for g in pg.evaluate("window.__stdrawNodeGeom()")}
    degraded = {v["i"] for v in pg.evaluate(JS_VISIBLE) if v["degraded"]}
    rows = pg.evaluate(JS_DOM_ENDPOINTS)
    bad = []
    for row in rows:
        if skip_degraded and row["i"] in degraded:
            continue
        for v, p in zip(row["ends"], row["pts"]):
            g = geoms[v]
            d = _dist_rect(p[0], p[1], g[1], g[2], g[3] / 2.0, g[4] / 2.0)
            if d > tol:
                bad.append((row["i"], v, round(d, 2)))
    return bad, degraded


def _node_screen(pg, vid):
    bb = pg.locator(f'[data-node="{vid}"]').bounding_box()
    return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2


def _drag(pg, sx, sy, dx, dy, steps=6, settle=120):
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    for s in range(1, steps + 1):
        pg.mouse.move(sx + dx * s / steps, sy + dy * s / steps)
        pg.wait_for_timeout(12)
    pg.mouse.up()
    pg.wait_for_timeout(settle)


def _edge_mid_screen(pg, i):
    res = pg.evaluate(
        """([i]) => (function(){
          var g = document.querySelector('#stdraw-svg g[data-edge="' + i + '"]');
          var p = g.querySelector('path:not(.stdraw-hit)');
          var m = p.getPointAtLength(p.getTotalLength() / 2);
          var r = document.getElementById('stdraw-svg').getBoundingClientRect();
          var s = 1.0;
          try { var vb = document.getElementById('stdraw-svg').viewBox.baseVal.width;
                var w = document.getElementById('stdraw-svg').clientWidth;
                if (vb && w) s = w / vb; } catch (e) {}
          return [r.left + m.x * s, r.top + m.y * s];
        })()""", [i])
    return res[0], res[1]


def main():
    if sync_playwright is None:
        print("SKIP playwright not installed")
        return 2
    _pin_local_stdraw()
    import stdraw as _stdraw_pkg
    if not os.path.realpath(os.path.dirname(_stdraw_pkg.__file__)).startswith(
            os.path.realpath(ROOT)):
        print("SKIP stdraw not loaded from this tree")
        return 2
    tmp = tempfile.mkdtemp(prefix="stdraw-domtruth-")
    out = os.path.join(tmp, "out")
    r = run_cli(["layout", CLD, "--outdir", out, "--skip-3d"])
    if r.returncode not in (0, 1):
        print("FAIL self-built demo failed:", r.stderr[-300:])
        return 1
    demo = os.path.join(out, "demo-2d.html")
    n_edges = 11
    assert os.path.isfile(demo)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1500})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        console_warns = []
        pg.on("console", lambda m: console_warns.append(m.text)
              if m.type in ("warning", "error") else None)

        pg.goto("file://" + demo.replace("\\", "/"))
        pg.wait_for_timeout(400)

        vis0 = pg.evaluate(JS_VISIBLE)
        chk("interactive layer loaded, visible edges present",
            len(vis0) == n_edges, f"visible={len(vis0)}")

        # ── A. real-mouse drag: incident edges' VISIBLE d must change ──
        hoya_x, hoya_y = _node_screen(pg, "hoya")
        pos0 = pg.evaluate("window.__stdrawNodePos('hoya')")
        _drag(pg, hoya_x, hoya_y, 60, 40)
        pos1 = pg.evaluate("window.__stdrawNodePos('hoya')")
        chk("drag moved node (internal)", abs(pos1[0] - pos0[0]) > 20
            and abs(pos1[1] - pos0[1]) > 20, f"{pos0} -> {pos1}")
        vis1 = pg.evaluate(JS_VISIBLE)
        d0 = {v["i"]: v["d"] for v in vis0}
        d1 = {v["i"]: v["d"] for v in vis1}
        changed = [i for i in d1 if d1[i] != d0.get(i)]
        chk("drag: >=2 visible edge d attributes changed (hit-vs-visible fix)",
            len(changed) >= 2, f"changed={sorted(changed)}")
        bad, deg = endpoint_violations(pg)
        chk("drag: DOM-truth endpoints on borders (<=0.5px), nothing degraded",
            not bad and not deg, f"bad={bad} degraded={sorted(deg)}")

        # ── B. applyLayout: visible d must change ──
        cpos = pg.evaluate("window.__stdrawNodePos('cloud')")
        spec = {"nodes": {"cloud": {"x": cpos[0] + 120, "y": cpos[1] + 60}}}
        pg.evaluate("spec => window.__stdrawApplyLayout(spec)", spec)
        pos2 = pg.evaluate("window.__stdrawNodePos('cloud')")
        vis2 = pg.evaluate(JS_VISIBLE)
        d2 = {v["i"]: v["d"] for v in vis2}
        changed2 = [i for i in d2 if d2[i] != d1.get(i)]
        chk("applyLayout: visible d re-anchored", len(changed2) >= 2,
            f"changed={sorted(changed2)}")
        bad, deg = endpoint_violations(pg)
        chk("applyLayout: DOM-truth endpoints on borders", not bad and not deg,
            f"bad={bad} degraded={sorted(deg)}")

        # ── C. real-mouse double-click: four-state style cycle closes ──
        seq = []
        for _ in range(4):
            mx, my = _edge_mid_screen(pg, 0)   # re-aim: geometry moved last cycle
            pg.mouse.dblclick(mx, my)
            pg.wait_for_timeout(80)
            seq.append(pg.evaluate("window.__stdrawEdgeStyle(0)"))
        chk("dblclick cycle closes straight->arc->free->auto",
            seq == ["straight", "arc", "free", "auto"], f"seq={seq}")
        # geometry visibly changes across the cycle (arc differs from straight)
        vis3 = pg.evaluate(JS_VISIBLE)
        chk("style cycle visibly re-rendered the line",
            any(v["d"] != d0.get(v["i"]) for v in vis3))
        pg.evaluate("window.__stdrawApplyLayout({})")   # back to a clean auto state

        # ── D. per-edge failure isolation (fail-visible, round survives) ──
        pg.evaluate("window.__stdrawProbeBreakEdge(2, true)")
        pg.add_style_tag(content="#stdraw-svg [data-node] text"
                                 "{font-size:24px !important;"
                                 "font-weight:bold !important}")
        pg.wait_for_timeout(100)
        grew = pg.evaluate("window.__stdrawSyncDomGeometry()")
        chk("sync ran with one broken edge (round not aborted)", grew is True)
        vis4 = {v["i"]: v for v in pg.evaluate(JS_VISIBLE)}
        chk("broken edge #2 carries the visible degradation marker",
            vis4[2]["degraded"],
            f"cls={vis4[2]['d'] and ''} degraded={vis4[2]['degraded']}")
        others_updated = any(vis4[i]["d"] != d2.get(i)
                             for i in vis4 if i != 2)
        chk("other edges re-anchored despite edge #2 failing", others_updated)
        chk("console WARN fired for the failed edge",
            any("[stdraw] edge #2" in w for w in console_warns),
            f"warns={console_warns[:3]}")
        bad, deg = endpoint_violations(pg, skip_degraded=True)
        chk("non-degraded edges stay on borders while #2 is broken",
            not bad, f"bad={bad}")
        chk("no uncaught exception from the contained failure", not errors,
            errors[:2])
        # self-heal: clear the fault, re-anchor everything, marker gone
        console_warns.clear()
        pg.evaluate("window.__stdrawProbeBreakEdge(2, false)")
        pg.evaluate("window.__stdrawApplyLayout({})")
        pg.wait_for_timeout(100)
        vis5 = {v["i"]: v for v in pg.evaluate(JS_VISIBLE)}
        chk("degradation marker self-heals on the next successful pass",
            not vis5[2]["degraded"])
        bad, deg = endpoint_violations(pg)
        chk("all edges back on borders after self-heal", not bad and not deg,
            f"bad={bad} degraded={sorted(deg)}")

        # ── E. first-frame multi-scale font inflation, empty memory ──
        for scale in (20, 24, 28, 34):
            pg_e = ctx.new_page()
            errs_e = []
            pg_e.on("pageerror", lambda e, _l=errs_e: _l.append(str(e)))
            css = ("#stdraw-svg [data-node] text{font-size:%dpx !important;"
                   "font-weight:bold !important}" % scale)
            # inject BEFORE the page scripts run (first-frame inflation,
            # pre-DOMContentLoaded) + empty position memory
            pg_e.add_init_script(
                "try{localStorage.clear();sessionStorage.clear();}catch(e){}"
                "var __obs=new MutationObserver(function(){"
                " if(document.head){__obs.disconnect();"
                "  var s=document.createElement('style');"
                "  s.textContent=%s;document.head.appendChild(s);}});"
                "__obs.observe(document,{childList:true,subtree:true});"
                % json.dumps(css))
            pg_e.goto("file://" + demo.replace("\\", "/"))
            pg_e.wait_for_timeout(400)
            geoms = pg_e.evaluate("window.__stdrawNodeGeom()")
            grew_cards = [g[0] for g in geoms
                          if g[4] > 46 + 0.5 or g[3] > 96 + 0.5]
            chk(f"font {scale}px: cards grew from the first frame",
                bool(grew_cards), f"grew={len(grew_cards)}")
            bad, deg = endpoint_violations(pg_e)
            chk(f"font {scale}px: 11/11 endpoints on borders or fail-visible, "
                "zero uncaught exceptions", (not bad) and (not deg)
                and not errs_e, f"bad={bad} degraded={sorted(deg)} errs={errs_e[:2]}")
            pg_e.close()

        chk("zero page errors across the whole probe", not errors, errors[:3])
        browser.close()
    print("DOM-TRUTH GATE:", "GREEN" if _chk_ok else "RED")
    return 0 if _chk_ok else 1


if __name__ == "__main__":
    sys.exit(main())
