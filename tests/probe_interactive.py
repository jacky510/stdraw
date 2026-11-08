#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interactive-layer regression probe (ref-scrubbed drag closed loop;
ref-scrubbed viewport fix; ref-scrubbed rerouting + bend handles):

  drag a node -> top-bar live metrics change -> edges/arrows/polarity marks
  follow -> full refresh on release -> "export layout" really downloads JSON
  -> "reset" restores the initial layout -> zero page errors throughout;
  ref-scrubbed: after v0.5.0 ring placement the rendered svg height can reach
  ~1140px, which a 1000px viewport cannot hold, so node screen coordinates
  fall outside the viewport -> pointer events miss (root cause of the old
  probe's 9/12 FAIL). Fix = 1600x1500 viewport +
  scroll_into_view_if_needed, all coordinates measured live;
  ref-scrubbed:
  - vg polyline fixture (third node pressing an edge -> --from-layout yields
    a vg polyline): handle rendering; while dragging an endpoint node the
    polyline cross-checks frame by frame against the preview routing
    independently recomputed in Python (proving recomputation, not pinning);
    while dragging the obstacle node all vertices move;
  - handle drag -> user pinning -> export carries waypoints -> CLI
    --from-layout recompute (kind=waypoints + via read back identical +
    identical-pinning geometry fail=0);
  - arc-graph drag: all Bezier vertices follow.

SKIP (exit 2, same caliber as rendercheck) when playwright is unavailable;
otherwise exit 0/1. Usage: python tests/probe_interactive.py
[demo-2d.html path (built by default)]
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP  probe_interactive: playwright unavailable (optional layer)")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")
PY = sys.executable


def _pin_local_stdraw():
    """ref-scrubbed same-tree self-check (same as probe_drag_follow): when running
    in script mode with sys.path[0]=tests/, the in-process import hits the
    site-packages editable install (pointing at the shared main tree), so
    rendering uses this tree while the cross-check uses the main tree -- out
    of sync, the cross-check distorts. Strip the editable hooks and force
    loading from this tree."""
    if not os.path.isfile(os.path.join(ROOT, "stdraw", "__init__.py")):
        print("SKIP  probe_interactive: stdraw package not found in this tree: %s" % ROOT)
        sys.exit(2)
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
        print("SKIP  probe_interactive: stdraw not loaded from this tree: %s"
              % stdraw.__file__)
        sys.exit(2)


_pin_local_stdraw()

result = {"checks": []}


def chk(name, ok, detail=""):
    result["checks"].append({"check": name, "pass": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + "  " + str(detail)[:200])


def run_cli(args):
    return subprocess.run([PY, "-m", "stdraw"] + args,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ROOT)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# -- ref-scrubbed cross-check baseline: same math caliber as the _interactive_js preview routing (Python side) --
def _expected_preview_route(nodes_px, a, b):
    """nodes_px: {id: (x,y,hw,hh)} (half width/height). Returns the expected polyline, or None (fallback)."""
    from stdraw.routing import border_point
    from stdraw.visibility import seg_rect_distance, shortest_path, _shortcut
    A, B = nodes_px[a], nodes_px[b]
    pa = border_point(A[0], A[1], A[2], A[3], B[0] - A[0], B[1] - A[1])
    pb = border_point(B[0], B[1], B[2], B[3], A[0] - B[0], A[1] - B[1])
    rects = [tuple(nodes_px[v]) for v in nodes_px if v not in (a, b)]
    if all(seg_rect_distance(pa, pb, r) >= 16 - 1e-6 for r in rects):
        return [list(pa), list(pb)]
    if not rects:
        return [list(pa), list(pb)]
    path = shortest_path(tuple(pa), tuple(pb), rects, 17.5)
    if path is None:
        return None
    return [list(p) for p in _shortcut(path, rects, 17.5)]


def _routes_match(js_pts, expect, tol=0.6):
    if expect is None or len(js_pts) != len(expect):
        return False
    for p, q in zip(js_pts, expect):
        if math.hypot(p[0] - q[0], p[1] - q[1]) > tol:
            return False
    return True


def _nodes_px_from_page(pg, lay):
    pos = {r[0]: (r[1], r[2]) for r in pg.evaluate("window.__stdrawNodePos()")}
    card_h = lay["meta"]["cardH"]
    return {v: (p[0], p[1], lay["nodes"][v]["w"] / 2.0, card_h / 2.0)
            for v, p in pos.items()}


def _node_center(pg, vid):
    loc = pg.locator(f'[data-node="{vid}"]')
    loc.scroll_into_view_if_needed()
    bb = loc.bounding_box()
    return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2


def _to_screen(pg, vx, vy):
    return pg.evaluate(
        "([vx,vy]) => { const s=document.getElementById('stdraw-svg');"
        " const r=s.getBoundingClientRect(); const VB=s.viewBox.baseVal;"
        " return [r.x+(vx-VB.x)/VB.width*r.width, r.y+(vy-VB.y)/VB.height*r.height]; }",
        [vx, vy])


def _drag(pg, sx, sy, dx, dy, steps=4, settle=40):
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    for k in range(1, steps + 1):
        pg.mouse.move(sx + dx * k / steps, sy + dy * k / steps, steps=1)
        pg.wait_for_timeout(settle)
    pg.mouse.up()
    pg.wait_for_timeout(120)


def main():
    tmp = tempfile.mkdtemp(prefix="stdraw-probe-")
    try:
        if len(sys.argv) > 1:
            demo = os.path.abspath(sys.argv[1])
        else:
            out = os.path.join(tmp, "out")
            r = run_cli(["layout", EX, "--outdir", out, "--skip-3d"])
            if r.returncode != 0:
                print("FAIL self-built demo failed:", r.stderr[-300:])
                return 1
            demo = os.path.join(out, "demo-2d.html")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="msedge", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            # ref-scrubbed: after ring placement the rendered svg is ~1140px tall; the viewport must hold it,
            # otherwise node screen coordinates sit outside the viewport and pointer events miss (root cause of 9/12 FAIL)
            ctx = browser.new_context(viewport={"width": 1600, "height": 1500},
                                accept_downloads=True, has_touch=True)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror",
                 lambda e: errors.append(getattr(e, "stack", "") or str(e)))
            pg.goto("file://" + demo.replace("\\", "/"))
            pg.wait_for_timeout(300)

            m0 = pg.evaluate("window.__stdrawMetrics()")
            chk("interactive layer loaded", bool(m0), f"metrics={m0}")
            toolbar0 = pg.evaluate(
                "document.getElementById('stdraw-metrics').textContent")
            chk("toolbar metrics visible", "crossings" in toolbar0, toolbar0)

            cx, cy = _node_center(pg, "rate")
            pos0 = pg.evaluate("window.__stdrawNodePos('rate')")
            _drag(pg, cx, cy, 45, 25, steps=3, settle=0)
            mid_toolbar = pg.evaluate(
                "document.getElementById('stdraw-metrics').textContent")
            _drag(pg, cx, cy, 70, 55, steps=5, settle=0)
            pg.wait_for_timeout(200)

            pos1 = pg.evaluate("window.__stdrawNodePos('rate')")
            m1 = pg.evaluate("window.__stdrawMetrics()")
            tr = pg.evaluate("document.querySelector('[data-node=\\'rate\\']')"
                             ".getAttribute('transform')")
            d0 = pg.evaluate("document.querySelector('[data-edge=\\'0\\'] path')"
                             ".getAttribute('d')")
            # ref-scrubbed: R/B letter badges removed (loop polarity now expressed by edge coloring) --
            # the probe now verifies edge coloring/dash survive the drag (static stroke attributes are not lost on reroute)
            stroke0 = pg.evaluate(
                "document.querySelector('[data-edge=\\'0\\'] path')"
                ".getAttribute('stroke')")
            chk("drag moved node",
               abs(pos1[0] - pos0[0]) > 20 and abs(pos1[1] - pos0[1]) > 20,
               f"pos {pos0} -> {pos1}, transform={tr}")
            chk("live metrics changed mid-drag", mid_toolbar != toolbar0,
                f"mid: {mid_toolbar!r}")
            chk("edge followed as polyline", "L " in d0, d0[:100])
            stroke1 = pg.evaluate(
                "document.querySelector('[data-edge=\\'0\\'] path')"
                ".getAttribute('stroke')")
            no_pol = pg.evaluate(
                "!document.querySelector('[data-pol]')")
            chk("edge color preserved, letter badges gone",
                stroke1 == stroke0 and stroke0 is not None and no_pol,
                f"stroke {stroke0!r} -> {stroke1!r}, data-pol absent={no_pol}")
            chk("metrics changed after drag", m1 != m0, f"{m0} -> {m1}")

            # touch usability (tap raises no error in a hasTouch context)
            tb = pg.locator('[data-node="adopters"]').bounding_box()
            pg.touchscreen.tap(tb["x"] + tb["width"] / 2, tb["y"] + tb["height"] / 2)
            pg.wait_for_timeout(100)
            chk("touch events processed without error", not errors, errors)

            with pg.expect_download() as dl_info:
                pg.click("#stdraw-export")
            dl = dl_info.value
            path = os.path.join(tmp, dl.suggested_filename)
            dl.save_as(path)
            exported = json.load(open(path, encoding="utf-8"))
            chk("export download real",
               exported.get("kind") == "manual-layout" and
               all(isinstance(v["x"], int) and isinstance(v["y"], int)
                   for v in exported["nodes"].values()),
               f"{dl.suggested_filename} rate={exported['nodes'].get('rate')}")
            chk("export reflects dragged pos",
               abs(exported["nodes"]["rate"]["x"] - pos1[0]) < 1.5,
               f"{exported['nodes']['rate']} vs {pos1}")
            chk("export no waypoints when unpinned", "edges" not in exported,
                str(exported.get("edges"))[:120])

            pg.click("#stdraw-reset")
            pos2 = pg.evaluate("window.__stdrawNodePos('rate')")
            chk("reset restores initial layout", pos2 == pos0, f"{pos2} vs {pos0}")

            # == ref-scrubbed hit gate: edge interactions via REAL hit-testing ==
            # 2026-11-08 8777 incident: .stdraw-hit shipped stroke:transparent +
            # pointer-events:stroke; Chromium treats an unpainted stroke as
            # unhittable, so every edge interaction (double-click style cycle /
            # free-point insert / edge drag) was dead on real machines while
            # synthetic dispatchEvent probes stayed green (dispatch bypasses
            # hit-testing = false positive). These gates go through the real
            # hit path only: elementFromPoint along each edge + CDP real-mouse
            # (pointerType mouse) input. Synthetic events prove nothing here.
            JS_HIT_PROBE = """([i]) => {
              const svg = document.getElementById('stdraw-svg');
              const r = svg.getBoundingClientRect();
              const VB = svg.viewBox.baseVal;
              const h = svg.querySelector('.stdraw-hit[data-edge="' + i + '"]');
              if (!h) return null;
              const len = h.getTotalLength();
              const out = [];
              for (const t of [0.1, 0.3, 0.5, 0.7, 0.9]) {
                const p = h.getPointAtLength(t * len);
                const p2 = h.getPointAtLength(Math.min(len, t * len + 1.5));
                let nx = -(p2.y - p.y), ny = p2.x - p.x;
                const nl = Math.hypot(nx, ny) || 1; nx /= nl; ny /= nl;
                for (const off of [0, 4, -4]) {
                  const vx = p.x + nx * off, vy = p.y + ny * off;
                  const cx = r.x + (vx - VB.x) / VB.width * r.width;
                  const cy = r.y + (vy - VB.y) / VB.height * r.height;
                  const el = document.elementFromPoint(cx, cy);
                  out.push({t: t, off: off,
                    inEdge: !!(el && el.closest && el.closest('[data-edge]')),
                    isHit: !!(el && el.classList &&
                              el.classList.contains('stdraw-hit')),
                    tag: el ? el.tagName + '.' + (el.getAttribute('class') || '')
                            : String(el)});
                }
              }
              return out;
            }"""
            n_edges_hit = pg.evaluate(
                "document.querySelectorAll('.stdraw-hit').length")
            per_edge = {i: pg.evaluate(JS_HIT_PROBE, [i])
                        for i in range(min(n_edges_hit, 6))}
            bad = {i: [p for p in (pts or []) if not p["inEdge"]]
                   for i, pts in per_edge.items()}
            chk("elementFromPoint on/beside every sampled edge point "
                "resolves into the edge interaction layer",
                n_edges_hit > 0 and all(not v for v in bad.values()),
                f"edges_probed={len(per_edge)} miss={ {k: len(v) for k, v in bad.items() if v} }")
            hit_only = {i: [p for p in (pts or [])
                            if p["off"] and not p["isHit"]]
                        for i, pts in per_edge.items()}
            chk("off-line band points resolve to the hit path itself",
                n_edges_hit > 0 and all(not v for v in hit_only.values()),
                f"miss={ {k: len(v) for k, v in hit_only.items() if v} }")
            # paintedness self-calibration: the shipped stroke must be painted
            # (alpha > 0) and pointer-events:all must also hit. NOTE (measured
            # 2026-11-08, Edge 157.0.4341.42 headless = the user's own Edge
            # install): current Chromium hit-tests pointer-events:stroke
            # regardless of paint (stroke:none / transparent all hit), so a
            # hard "transparent FAIL" assertion is environment-dependent and
            # would go red on modern builds -- the painted stroke is kept
            # because older Chromium builds gate `stroke` hit-testing on
            # paintedness (diagram-js ships painted white hit strokes for the
            # same reason). We assert what must hold everywhere: painted PASS
            # + all PASS + CSS restore PASS; the transparent outcome is
            # recorded in the detail string only.
            dt = pg.evaluate("""() => {
              const svg = document.getElementById('stdraw-svg');
              const h = svg.querySelector('.stdraw-hit');
              const r = svg.getBoundingClientRect();
              const VB = svg.viewBox.baseVal;
              const p = h.getPointAtLength(0.5 * h.getTotalLength());
              const p2 = h.getPointAtLength(
                Math.min(h.getTotalLength(), 0.5 * h.getTotalLength() + 1.5));
              let nx = -(p2.y - p.y), ny = p2.x - p.x;
              const nl = Math.hypot(nx, ny) || 1; nx /= nl; ny /= nl;
              const vx = p.x + nx * 4, vy = p.y + ny * 4;
              const cx = r.x + (vx - VB.x) / VB.width * r.width;
              const cy = r.y + (vy - VB.y) / VB.height * r.height;
              const hitAt = () => {
                const el = document.elementFromPoint(cx, cy);
                return !!(el && el.classList &&
                          el.classList.contains('stdraw-hit'));
              };
              const out = {};
              h.style.stroke = 'transparent'; out.transparent = hitAt();
              h.style.stroke = 'rgba(255,255,255,0.01)'; out.painted = hitAt();
              h.style.stroke = 'transparent';
              h.style.pointerEvents = 'all'; out.all = hitAt();
              h.style.stroke = ''; h.style.pointerEvents = '';
              out.restored = hitAt();
              return out;
            }""")
            chk("hit self-check: painted PASS / all PASS / CSS restore PASS "
                "(transparent outcome recorded, see detail)",
                dt.get("painted") is True and dt.get("all") is True
                and dt.get("restored") is True, str(dt))
            # pick a probe edge: on-line hit + open canvas at the midpoint
            E = None
            for i, pts in per_edge.items():
                if pts and all(p["inEdge"] for p in pts):
                    mid = [p for p in pts if p["t"] == 0.5 and p["off"] == 0]
                    if mid and mid[0]["isHit"]:
                        E = i
                        break
            chk("probe edge selected via real hit", E is not None,
                f"per_edge on-line isHit={[k for k, v in per_edge.items() if v and any(p['isHit'] and p['off'] == 0 for p in v)]}")
            if E is not None:
                # fresh midpoint per input: switching the style re-renders the
                # edge (straight chord -> arc sagitta moves the curve away from
                # the old midpoint), so each real-mouse input must re-aim at
                # the CURRENT hit-path geometry, like a user following the line
                def _edge_mid_screen(pg, eidx):
                    mid = pg.evaluate(
                        "([i]) => { const svg=document.getElementById('stdraw-svg');"
                        " const h=svg.querySelector('.stdraw-hit[data-edge=\\\"'+i+'\\\"]');"
                        " const p=h.getPointAtLength(0.5*h.getTotalLength());"
                        " return [p.x, p.y]; }", [eidx])
                    return _to_screen(pg, mid[0], mid[1])
                sx, sy = _edge_mid_screen(pg, E)
                st0 = pg.evaluate(f"window.__stdrawEdgeStyle({E})")
                cycle = [st0]
                for _ in range(3):
                    pg.mouse.dblclick(sx, sy)
                    pg.wait_for_timeout(120)
                    sx, sy = _edge_mid_screen(pg, E)
                    cycle.append(pg.evaluate(f"window.__stdrawEdgeStyle({E})"))
                chk("CDP real-mouse double-click on edge cycles style "
                    "auto->straight->arc->free",
                    cycle == ["auto", "straight", "arc", "free"],
                    f"edge {E}: {'->'.join(cycle)}")
                # free mode: single click on the edge inserts a fold point
                sx, sy = _edge_mid_screen(pg, E)
                pg.mouse.click(sx, sy)
                pg.wait_for_timeout(200)
                wps = pg.evaluate(f"window.__stdrawFreePoints({E})")
                n_free_handles = pg.evaluate(
                    "document.querySelectorAll('.stdraw-wp[data-free=\"1\"]').length")
                chk("free-mode click inserts fold point + free handle appears",
                    len(wps) == 1 and n_free_handles == 1,
                    f"wps={wps} freeHandles={n_free_handles}")
                if len(wps) == 1:
                    pg.wait_for_timeout(600)  # > 450ms dblclick window
                    hx, hy = _to_screen(pg, wps[0][0], wps[0][1])
                    pg.mouse.move(hx, hy)
                    pg.mouse.down()
                    pg.mouse.move(hx + 30, hy + 20, steps=4)
                    pg.wait_for_timeout(40)
                    pg.mouse.up()
                    pg.wait_for_timeout(200)
                    wps2 = pg.evaluate(f"window.__stdrawFreePoints({E})")
                    chk("fold-point handle draggable (waypoint follows mouse)",
                        len(wps2) == 1 and
                        abs(wps2[0][0] - wps[0][0]) > 15 and
                        abs(wps2[0][1] - wps[0][1]) > 10,
                        f"{wps} -> {wps2}")
                    exp = json.loads(
                        pg.evaluate("window.__stdrawExportJSON()"))
                    e_entries = [e for e in exp.get("edges", [])]
                    wp_entry = [e for e in e_entries if e.get("waypoints")]
                    chk("export layout carries waypoints for the free edge",
                        bool(wp_entry) and
                        any(any(abs(p[0] - wps2[0][0]) < 2 and
                                abs(p[1] - wps2[0][1]) < 2
                                for p in e["waypoints"])
                            for e in wp_entry),
                        f"edges={str(e_entries)[:200]}")
                    wp_free = os.path.join(tmp, "wp-free.json")
                    with open(wp_free, "w", encoding="utf-8") as f:
                        json.dump(exp, f, ensure_ascii=False)
                    out_free = os.path.join(tmp, "wp-free")
                    r_free = run_cli(["layout", EX, "--outdir", out_free,
                                      "--skip-3d", "--from-layout", wp_free])
                    geo_free = (load(os.path.join(out_free,
                                                  "geometry_report.json"))
                                if r_free.returncode == 0 else {"fail": -1})
                    # The pipeline must consume the exported free-edge layout.
                    # Outcome is honestly graded: rc=0 = gates pass; rc=1 =
                    # hard-gate fail on the user-dragged waypoint (the CLI
                    # exits 1 when geometry_report fail>0 -- honest boundary,
                    # by design). A crash / schema refusal is the only failure.
                    ok_rc = r_free.returncode in (0, 1)
                    honest = (r_free.returncode == 0 and
                              geo_free["fail"] == 0) or \
                             (r_free.returncode == 1 and
                              "uncertified" in r_free.stdout)
                    chk("exported free-edge layout replays through the CLI "
                        "pipeline (persistence chain closes; honest grade "
                        "on user-dragged waypoint accepted)",
                        ok_rc and honest,
                        f"rc={r_free.returncode} fail={geo_free['fail']} "
                        f"err={r_free.stderr[-200:]!r} "
                        f"out={r_free.stdout[-300:]!r}")

            # == ref-scrubbed: vg polyline follow + bend handles + full waypoints chain ==
            out_a = os.path.join(tmp, "auto")
            run_cli(["layout", EX, "--outdir", out_a, "--skip-3d"])
            lay = load(os.path.join(out_a, "layout.json"))
            # fixture: a straight/arc edge (a,b) + third node c pressed onto the segment midpoint -> CLI yields vg
            found = None
            for e0 in lay["edges"]:
                if e0["route"]["kind"] not in ("line", "arc"):
                    continue
                fa, fb = e0["a"], e0["b"]
                for c in lay["nodes"]:
                    if c in (fa, fb):
                        continue
                    manual = {"viewBox": lay["viewBox"],
                              "nodes": {v: {"x": q["x"], "y": q["y"]}
                                        for v, q in lay["nodes"].items()}}
                    mx = (lay["nodes"][fa]["x"] + lay["nodes"][fb]["x"]) / 2
                    my = (lay["nodes"][fa]["y"] + lay["nodes"][fb]["y"]) / 2
                    manual["nodes"][c] = {"x": int(mx) - int(mx) % 2,
                                          "y": int(my) - int(my) % 2}
                    mpth = os.path.join(tmp, "fixture.json")
                    with open(mpth, "w", encoding="utf-8") as f:
                        json.dump(manual, f, ensure_ascii=False)
                    out_m = os.path.join(tmp, "fixture")
                    run_cli(["layout", EX, "--outdir", out_m, "--skip-3d",
                             "--from-layout", mpth])
                    lay_m = load(os.path.join(out_m, "layout.json"))
                    vg = [(i, x) for i, x in enumerate(lay_m["edges"])
                          if x["route"]["kind"] == "vg"]
                    if vg:
                        # ref-scrubbed: the cross-check pairing must use the vg edge's own endpoints -- under
                        # v0.6.x layouts the blocked target edge may switch to poly (bend-kind cost
                        # vg+120 > poly+40, router picks the better), so the first vg can land on a different
                        # edge (observed (rate,adopters)); also c must not be a vg edge endpoint
                        # (the blocker leg drags the obstacle, not an endpoint).
                        for i_vg, x_vg in vg:
                            va, vb = x_vg["a"], x_vg["b"]
                            if c not in (va, vb):
                                found = (i_vg, va, vb, c, out_m, manual, mpth)
                                break
                    if found:
                        break
                if found:
                    break
            chk("vg fixture built (blocker forces vg fold line)", found is not None,
                str(found[:4]) if found else "")
            if found:
                EIDX, a, b, c, out_m, manual, mpth = found
                vg = load(os.path.join(out_m, "layout.json"))["edges"][EIDX]
                pg.goto("file://" +
                        os.path.join(out_m, "demo-2d.html").replace("\\", "/"))
                pg.wait_for_timeout(300)
                hs = pg.evaluate("window.__stdrawHandles()")
                via = vg["route"]["via"]
                chk("handles rendered at via corners",
                   len(hs) == len(via) - 2 and
                   all(any(abs(h[2] - q[0]) < 0.6 and abs(h[3] - q[1]) < 0.6
                           for q in via) for h in hs),
                   f"{len(hs)} handles vs {len(via) - 2} corners")

                # Drag the endpoint node: cross-check frame by frame against the Python recompute (proof of
                # recomputation, not pinning). The initial pts are CLI dense geometry (incl. fillet arc samples); JS
                # switches to the preview-routing polyline only from the first pointermove -- checks start there.
                acx, acy = _node_center(pg, a)
                pg.mouse.move(acx, acy)
                pg.mouse.down()
                frame_ok, frame_n, first_ok = True, 0, None
                for k in range(1, 5):
                    pg.mouse.move(acx + 14 * k, acy - 9 * k, steps=1)
                    pg.wait_for_timeout(40)
                    pts = pg.evaluate(f"window.__stdrawEdgePts({EIDX})")
                    npx = _nodes_px_from_page(pg, lay)
                    ex = _expected_preview_route(npx, a, b)
                    good = _routes_match(pts, ex)
                    if first_ok is None:
                        first_ok = good
                    frame_n += 1
                    if not good:
                        frame_ok = False
                        print("  mismatch frame", k, "pts", pts[:3],
                              "expect", (ex[:3] if ex else None))
                        break
                pg.mouse.up()
                pg.wait_for_timeout(120)
                chk("first reroute frame matches independent recompute",
                   bool(first_ok), f"n={frame_n}")
                chk("mid-drag polyline == independent recompute each frame",
                   frame_ok, f"{frame_n} frames checked")
                last = pg.evaluate(f"window.__stdrawEdgePts({EIDX})")
                npx = _nodes_px_from_page(pg, lay)
                chk("post-drag polyline still recomputed",
                   _routes_match(last, _expected_preview_route(npx, a, b)),
                   f"n={len(last)}")

                # Drag the obstacle node: main assertion = recomputation cross-check; any residual same-position
                # points must be exactly inflated corners of unmoved obstacles (+/-0.15px) -- geometrically legal stillness, not a pinned stale waypoint
                pg.click("#stdraw-reset")
                pg.wait_for_timeout(120)
                base2 = pg.evaluate(f"window.__stdrawEdgePts({EIDX})")
                ccx, ccy = _node_center(pg, c)
                _drag(pg, ccx, ccy, 36, 24, steps=3, settle=40)
                last2 = pg.evaluate(f"window.__stdrawEdgePts({EIDX})")
                npx2 = _nodes_px_from_page(pg, lay)
                ex2 = _expected_preview_route(npx2, a, b)
                corners_ok = True
                stuck_detail = []
                # check only interior vertices: endpoint anchors follow their endpoint nodes (not moving during an obstacle drag is legal)
                for q in last2[1:-1]:
                    if min(math.hypot(q[0] - r[0], q[1] - r[1])
                           for r in base2) >= 1.0:
                        continue
                    on_corner = any(
                        abs(q[0] - (npx2[v][0] - npx2[v][2] - 17.5)) < 0.15 and
                        abs(q[1] - (npx2[v][1] - npx2[v][3] - 17.5)) < 0.15 or
                        abs(q[0] - (npx2[v][0] + npx2[v][2] + 17.5)) < 0.15 and
                        abs(q[1] - (npx2[v][1] - npx2[v][3] - 17.5)) < 0.15 or
                        abs(q[0] - (npx2[v][0] + npx2[v][2] + 17.5)) < 0.15 and
                        abs(q[1] - (npx2[v][1] + npx2[v][3] + 17.5)) < 0.15 or
                        abs(q[0] - (npx2[v][0] - npx2[v][2] - 17.5)) < 0.15 and
                        abs(q[1] - (npx2[v][1] + npx2[v][3] + 17.5)) < 0.15
                        for v in npx2 if v != c)
                    if not on_corner:
                        corners_ok = False
                        stuck_detail.append(q)
                chk("drag blocker: polyline recomputed, no stale waypoint",
                   _routes_match(last2, ex2) and corners_ok,
                   f"n={len(last2)} recompute={_routes_match(last2, ex2)} "
                   f"stale={stuck_detail[:3]}")

                # handle drag -> pinning -> export -> CLI recompute (identical pinning, fail=0)
                pg.click("#stdraw-reset")
                pg.wait_for_timeout(120)
                hs = [h for h in pg.evaluate("window.__stdrawHandles()")
                      if h[0] == EIDX]
                chk("handles restorable after reset", len(hs) >= 1, str(hs[:2]))
                # identical pinning: press then release immediately (waypoints = original corners, geometry unchanged)
                sx, sy = _to_screen(pg, hs[0][2], hs[0][3])
                pg.mouse.move(sx, sy)
                pg.mouse.down()
                pg.mouse.up()
                pg.wait_for_timeout(100)
                pinned = pg.evaluate("window.__stdrawPinned()")
                exp = json.loads(pg.evaluate("window.__stdrawExportJSON()"))
                chk("handle click pins edge + export carries waypoints",
                   pinned == [EIDX] and exp.get("edges") and
                   len(exp["edges"][0]["waypoints"]) >= 1,
                   f"pinned={pinned} wps={exp.get('edges')}")
                wp_out = os.path.join(tmp, "wp.json")
                with open(wp_out, "w", encoding="utf-8") as f:
                    json.dump(exp, f, ensure_ascii=False)
                out_wp = os.path.join(tmp, "wp")
                r_wp = run_cli(["layout", EX, "--outdir", out_wp, "--skip-3d",
                                "--from-layout", wp_out])
                geo_wp = load(os.path.join(out_wp, "geometry_report.json"))
                lay_wp = load(os.path.join(out_wp, "layout.json"))
                e_wp = next(x for x in lay_wp["edges"]
                            if (x["a"], x["b"]) == (a, b))
                want = [[int(round(q[0])), int(round(q[1]))]
                        for q in exp["edges"][0]["waypoints"]]
                got = e_wp["route"].get("via")
                chk("CLI --from-layout re-computes waypoints route",
                   r_wp.returncode == 0 and geo_wp["fail"] == 0 and
                   e_wp["route"]["kind"] == "waypoints" and
                   got == [[float(qx), float(qy)] for qx, qy in want],
                   f"rc={r_wp.returncode} fail={geo_wp['fail']} "
                   f"kind={e_wp['route']['kind']} via={got} want={want}")

                # reset clears pins and restores handles
                pg.click("#stdraw-reset")
                pg.wait_for_timeout(120)
                chk("reset clears pins and restores handles",
                   pg.evaluate("window.__stdrawPinned()") == [] and
                   len(pg.evaluate("window.__stdrawHandles()")) >= 1)

            # == ref-scrubbed: segment drag / floating bendpoint / merge lifecycle ==
            # CDP real mouse only (pointerType mouse via Playwright input).
            # UX caliber: drawio/bpmn-io segment-move + .djs-bendpoint.floating.
            # On the dense demo the node layer paints ABOVE the 12px hit band,
            # so every press/hover point is picked by scanning the polyline
            # with elementFromPoint (real hit path) -- never assumed from
            # geometry alone.
            JS_PICK = """([i, interiorOnly]) => {
              const svg = document.getElementById('stdraw-svg');
              const pts = window.__stdrawEdgePts(i);
              if (!pts || pts.length < 2) return null;
              const r = svg.getBoundingClientRect();
              const VB = svg.viewBox.baseVal;
              const toC = (vx, vy) => [r.x + (vx - VB.x) / VB.width * r.width,
                                       r.y + (vy - VB.y) / VB.height * r.height];
              const hitEdge = (cx, cy) => {
                const el = document.elementFromPoint(cx, cy);
                const g = el && el.closest && el.closest('[data-edge]');
                // must be THIS edge's interaction layer: demo edge bands overlap
                return !!(g && g.getAttribute('data-edge') === String(i));
              };
              const segs = pts.length - 1;
              let midHit = null, offHit = null;
              for (let s = 0; s < segs; s++) {
                if (interiorOnly && (s === 0 || s === segs - 1)) continue;
                const mx = (pts[s][0] + pts[s + 1][0]) / 2;
                const my = (pts[s][1] + pts[s + 1][1]) / 2;
                const [cx, cy] = toC(mx, my);
                if (!midHit && hitEdge(cx, cy)) midHit = {x: mx, y: my, seg: s};
                if (!offHit) {
                  const px = pts[s][0] + (pts[s + 1][0] - pts[s][0]) * 0.3;
                  const py = pts[s][1] + (pts[s + 1][1] - pts[s][1]) * 0.3;
                  const [cx2, cy2] = toC(px, py);
                  if (hitEdge(cx2, cy2) && Math.hypot(px - mx, py - my) > 8)
                    offHit = {x: px, y: py, seg: s};
                }
                if (midHit && offHit) break;
              }
              return (midHit && offHit) ? {mid: midHit, off: offHit} : null;
            }"""
            picked = None
            ek0 = None
            n_edges = pg.evaluate("window.__stdrawEdgePts().length")
            for cand in range(n_edges):
                pg.evaluate("window.__stdrawApplyLayout({nodes:{}, waypoints:{}})")
                key = pg.evaluate(
                    "(function(){var d=JSON.parse(document.getElementById("
                    "'stdraw-data').textContent);var e=d.edges[%d];"
                    "return e.a + '->' + e.b;})()" % cand)
                if pg.evaluate("window.__stdrawArcFlag(%d)" % cand):
                    continue
                p = pg.evaluate(JS_PICK, [cand])
                if p:
                    picked, ek0, EIDX = p, key, cand
                    break
            chk("interaction edge picked via real elementFromPoint scan "
                "(arc-flagged edges skipped)",
               picked is not None and ek0 is not None,
               "edges=%d picked=%s key=%s" % (n_edges, picked, ek0))
            pg.wait_for_timeout(650)   # clear the 450ms manual-dblclick window
            # -- floating bendpoint on the PRISTINE (auto) edge: preview-only --
            hx, hy = _to_screen(pg, picked["mid"]["x"], picked["mid"]["y"])
            pg.mouse.move(hx, hy)
            pg.wait_for_timeout(60)
            pg.mouse.move(hx + 1, hy)   # jiggle: guarantee a fresh mousemove
            pg.wait_for_timeout(120)
            fl = pg.evaluate("window.__stdrawFloating()")
            dirty = pg.evaluate("JSON.stringify([window.__stdrawUserWps(),"
                                "window.__stdrawPinned(),window.__stdrawStyles()])")
            chk("floating handle parks at hovered segment mid",
               fl and fl.get("edge") == EIDX and
               abs(fl.get("cx") - picked["mid"]["x"]) < 2.5 and
               abs(fl.get("cy") - picked["mid"]["y"]) < 2.5, fl)
            chk("hover writes NO user state (no waypoints/pins/styles)",
               json.loads(dirty) == [{}, [], []], dirty)
            pg.mouse.move(10, 10)
            pg.wait_for_timeout(350)
            chk("floating handle hides off-edge",
               pg.evaluate("window.__stdrawFloating()") is None)

            # floating drag-away >=4px: adopt geometry + create exactly one point
            pg.mouse.move(hx, hy)
            pg.wait_for_timeout(100)
            pg.mouse.down()
            pg.wait_for_timeout(40)
            for t in (0.25, 0.5, 0.75, 1.0):
                pg.mouse.move(hx, hy - 55 * t)
                pg.wait_for_timeout(20)
            pg.mouse.up()
            pg.wait_for_timeout(150)
            pg.wait_for_timeout(600)   # clear dblclick window
            w1 = pg.evaluate("window.__stdrawUserWps()[%d] || []" % EIDX)
            chk("floating drag-away adopts geometry + creates exactly one "
                "fold point (auto -> free)",
               pg.evaluate("window.__stdrawEdgeStyle(%d)" % EIDX) == "free" and
               len(w1) == 1, json.dumps(w1))

            # segment drag on the anchor-adjacent segment (inserts ONE jog)
            # re-pick: the fold point created above re-routed the edge, so the
            # previous coordinates may now sit under a card
            picked1 = pg.evaluate(JS_PICK, [EIDX, False])
            chk("fresh hittable point for anchor-adjacent segment drag",
               picked1 is not None, json.dumps(picked1))
            pts1 = pg.evaluate("window.__stdrawEdgePts(%d)" % EIDX)
            if picked1 is None:
                chk("segment drag anchor-adjacent inserts 1 (1->2 waypoints)",
                    False, "no hittable point on the target edge after adopt")
                chk("segment cursor reflects orientation on the hit path",
                    False, "no hittable point")
            base = picked1["off"] if picked1 else pts1[0]
            d30 = [base["x"], base["y"]] if picked1 else [base[0], base[1]]
            sx, sy = _to_screen(pg, d30[0], d30[1])
            pg.mouse.move(sx, sy)
            pg.wait_for_timeout(60)
            pg.mouse.move(sx + 1, sy)   # jiggle: first move after a drag is
            pg.wait_for_timeout(100)    # swallowed (measured); force a fresh one
            cur = pg.evaluate(
                "([x, y]) => { const el = document.elementFromPoint(x, y);"
                " return el && el.style ? el.style.cursor : null; }",
                [sx + 1, sy])
            chk("segment cursor reflects orientation on the hit path",
               cur in ("ns-resize", "ew-resize"), cur)
            pg.mouse.down()
            pg.wait_for_timeout(40)
            for t in (0.25, 0.5, 0.75, 1.0):
                pg.mouse.move(sx, sy - 30 * t)
                pg.wait_for_timeout(20)
            pg.mouse.up()
            pg.wait_for_timeout(150)
            pg.wait_for_timeout(600)
            w2 = pg.evaluate("window.__stdrawUserWps()[%d] || []" % EIDX)
            head_ok = bool(w2) and abs(w2[0][0] - w1[0][0]) < 2.5 and \
                abs(w2[0][1] - w1[0][1]) < 2.5
            chk("segment drag anchor-adjacent inserts 1 (1->2 waypoints)",
               len(w2) == 2 and head_ok,
               json.dumps([w1[:1], w2]))

            # interior segment (inserts TWO jog bendpoints). The first edge's
            # interior segments are too short/covered on the dense demo, so
            # pick a dedicated edge with a hittable interior point.
            picked2 = None
            ek2 = None
            E2 = None
            for cand in range(n_edges):
                if pg.evaluate("window.__stdrawArcFlag(%d)" % cand):
                    continue
                key2 = pg.evaluate(
                    "(function(){var d=JSON.parse(document.getElementById("
                    "'stdraw-data').textContent);var e=d.edges[%d];"
                    "return e.a + '->' + e.b;})()" % cand)
                pg.evaluate("window.__stdrawApplyLayout({nodes:{}, waypoints:"
                            "{'" + key2 + "': [[300,150],[450,150],[600,150]]}})")
                pg.wait_for_timeout(120)
                p2i = pg.evaluate(JS_PICK, [cand, True])
                if p2i and p2i["off"]["seg"] not in (0, None):
                    picked2, ek2, E2 = p2i, key2, cand
                    break
            chk("fresh hittable point for interior segment drag",
               picked2 is not None and picked2["off"]["seg"] not in (0, None),
               json.dumps({"picked": picked2, "edge": E2, "key": ek2}))
            sx, sy = _to_screen(pg, picked2["off"]["x"], picked2["off"]["y"]) if picked2 else (10, 10)
            pg.mouse.move(sx, sy)
            pg.wait_for_timeout(60)
            pg.mouse.move(sx + 1, sy)   # jiggle (see above)
            pg.wait_for_timeout(100)
            pg.mouse.down()
            pg.wait_for_timeout(40)
            for t in (0.25, 0.5, 0.75, 1.0):
                pg.mouse.move(sx + 24 * t, sy)
                pg.wait_for_timeout(20)
            pg.mouse.up()
            pg.wait_for_timeout(150)
            if picked2 is None:
                chk("segment drag interior inserts 2 (3->5 waypoints)",
                    False, "no hittable interior segment")
                chk("export carries the drag-built waypoints",
                    False, "skipped")
            else:
                w3 = pg.evaluate(
                    "window.__stdrawUserWps()[%d] || []" % E2)
                chk("segment drag interior inserts 2 (3->5 waypoints)",
                    len(w3) == 5, json.dumps(w3))
                exp_json = json.loads(pg.evaluate("window.__stdrawExportJSON()"))
                e0 = [x for x in exp_json.get("edges", [])
                      if x["a"] + "->" + x["b"] == ek2]
                chk("export carries the drag-built waypoints",
                    bool(e0) and e0[0].get("style") == "free" and
                    len(e0[0].get("waypoints", [])) == 5, e0)

            # drag-back-to-line merge (finalized deletion semantics): pull a
            # real fold-point handle (hittable per elementFromPoint) onto the
            # polyline through its neighbors
            JS_HANDLE = """([i]) => {
              const svg = document.getElementById('stdraw-svg');
              const r = svg.getBoundingClientRect();
              const VB = svg.viewBox.baseVal;
              const toC = (vx, vy) => [r.x + (vx - VB.x) / VB.width * r.width,
                                       r.y + (vy - VB.y) / VB.height * r.height];
              const out = [];
              document.querySelectorAll('.stdraw-wp[data-free="1"]')
                .forEach(function (c) {
                  if (+c.getAttribute('data-edge') !== i) return;
                  const cx = +c.getAttribute('cx'), cy = +c.getAttribute('cy');
                  const [sx, sy] = toC(cx, cy);
                  const el = document.elementFromPoint(sx, sy);
                  if (el && el.classList && el.classList.contains('stdraw-wp'))
                    out.push({wp: +c.getAttribute('data-wp'), x: cx, y: cy});
                });
              return out;
            }"""
            ok_b = pg.evaluate(
                "window.__stdrawApplyLayout({nodes:{}, waypoints:{'%s': "
                "[[300,150],[450,150],[600,150],[750,150]]}})" % ek0)
            pg.wait_for_timeout(650)

            def _proj(p, a, b2):
                vx, vy = b2[0] - a[0], b2[1] - a[1]
                L2 = vx * vx + vy * vy
                t = 0 if L2 < 1e-12 else max(0.0, min(1.0,
                    ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
                return [a[0] + t * vx, a[1] + t * vy]

            def _dist_to_rest(p, rest):
                return min(math.hypot(p[0] - _proj(p, rest[k], rest[k + 1])[0],
                                      p[1] - _proj(p, rest[k], rest[k + 1])[1])
                           for k in range(len(rest) - 1))

            handle = pg.evaluate(JS_HANDLE, [EIDX])
            pts3 = pg.evaluate("window.__stdrawEdgePts(%d)" % EIDX)
            h0 = None
            for h in handle:
                rest = pts3[:h["wp"]] + pts3[h["wp"] + 1:]
                if _dist_to_rest([h["x"], h["y"]], rest) <= 6:
                    h0 = h
                    break
            chk("hittable fold-point handle available for merge",
               ok_b and h0 is not None, json.dumps(handle))
            w4 = []
            if h0 is not None:
                idx = h0["wp"]
                pts3 = pg.evaluate("window.__stdrawEdgePts(%d)" % EIDX)
                rest = pts3[:idx] + pts3[idx + 1:]
                if _dist_to_rest([h0["x"], h0["y"]], rest) < 3:
                    # already on the line: park 4px off first (still a real
                    # drag), staying within MERGE_TOL=6 of the rest path
                    target = [h0["x"] + 4, h0["y"] + 4]
                else:
                    best = None
                    for k in range(len(rest) - 1):
                        q = _proj([h0["x"], h0["y"]], rest[k], rest[k + 1])
                        d = math.hypot(q[0] - h0["x"], q[1] - h0["y"])
                        if best is None or d < best[0]:
                            best = (d, q)
                    target = best[1]
                    if math.hypot(target[0] - h0["x"], target[1] - h0["y"]) < 3:
                        target = [h0["x"] + 4, h0["y"] + 4]
                sx, sy = _to_screen(pg, h0["x"], h0["y"])
                tx, ty = _to_screen(pg, target[0], target[1])
                pg.mouse.move(sx, sy)
                pg.wait_for_timeout(100)
                pg.mouse.down()
                pg.wait_for_timeout(40)
                for t in (0.25, 0.5, 0.75, 1.0):
                    pg.mouse.move(sx + (tx - sx) * t, sy + (ty - sy) * t)
                    pg.wait_for_timeout(20)
                pg.mouse.up()
                pg.wait_for_timeout(150)
                w4 = pg.evaluate("window.__stdrawUserWps()[%d] || []" % EIDX)
            chk("drag-back-to-line merges (4->3 waypoints)", len(w4) == 3,
               json.dumps(w4))

            # legacy free-mode click-insert survives the parked preview
            ok_c = pg.evaluate(
                "window.__stdrawApplyLayout({nodes:{}, waypoints:{'%s': "
                "[[400, 150]]}})" % ek0)
            pg.wait_for_timeout(650)
            p2 = pg.evaluate(JS_PICK, [EIDX])
            if p2 is None:
                chk("parked-handle click on a free edge inserts (legacy path "
                    "preserved)", False, "no hittable point after re-seed")
            mx, my = _to_screen(pg, p2["mid"]["x"], p2["mid"]["y"]) if p2 else (10, 10)
            pg.mouse.move(mx, my)
            pg.wait_for_timeout(60)
            pg.mouse.move(mx + 1, my)   # jiggle: preview parks at mid
            pg.wait_for_timeout(150)
            fl2 = pg.evaluate("window.__stdrawFloating()")
            pg.mouse.click(mx, my)      # press + release without drag
            pg.wait_for_timeout(200)
            w5 = pg.evaluate("window.__stdrawUserWps()[%d] || []" % EIDX)
            chk("parked-handle click on a free edge inserts (legacy path "
                "preserved)", ok_c and fl2 is not None and len(w5) == 2,
               [fl2, json.dumps(w5)])

            # == arc graph: all Bezier vertices follow (arcFollow) ==
            out_arc = os.path.join(tmp, "arc")
            r_arc = run_cli(["layout", EX, "--outdir", out_arc, "--skip-3d",
                             "--linestyle", "arc"])
            if r_arc.returncode == 0:
                pg.goto("file://" +
                        os.path.join(out_arc, "demo-2d.html").replace("\\", "/"))
                pg.wait_for_timeout(300)
                allpts0 = pg.evaluate("window.__stdrawEdgePts()")
                ei = max(range(len(allpts0)),
                         key=lambda i: len(allpts0[i]))
                ae = json.loads(pg.evaluate(
                    "JSON.stringify(JSON.parse(document.getElementById("
                    "'stdraw-data').textContent).edges[%d])" % ei))
                vid = ae["a"] if ae.get("arc") else None
                base_arc = allpts0[ei]
                vcx, vcy = _node_center(pg, vid)
                _drag(pg, vcx, vcy, 40, 28, steps=3, settle=40)
                after_arc = pg.evaluate(f"window.__stdrawEdgePts({ei})")
                stuck_arc = [q for q in after_arc
                             if min(math.hypot(q[0] - r0[0], q[1] - r0[1])
                                    for r0 in base_arc) < 1.0]
                chk("arc bezier: all sampled vertices follow drag",
                   ae.get("arc") and not stuck_arc,
                   f"edge {ei} arc={ae.get('arc')} n={len(after_arc)} "
                   f"stuck={stuck_arc[:2]}")
            else:
                chk("arc demo built", False, r_arc.stderr[-150:])

            chk("zero page errors", not errors, errors)
            browser.close()

        ok = all(c["pass"] for c in result["checks"])
        print("\n==", "ALL PASS" if ok else "HAS FAILURES",
              f"({sum(c['pass'] for c in result['checks'])}/{len(result['checks'])})")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
