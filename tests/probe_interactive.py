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
            pg.on("pageerror", lambda e: errors.append(str(e)))
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
