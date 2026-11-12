#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drag-follow sweep probe (ref-scrubbed acceptance): headless CDP real drags
reproduce jacky's observed scenario graph by graph.

Data sources (priority):
  1. the 19 jacky manual layouts under <user-home>/Downloads/stdraw-manual/
     (layout.json node coordinates re-rendered at HEAD via --from-layout; the
     interactive layer is this card's new version);
  2. default fallback: the 19 auto layouts from benchmarks/corpus/classic/.

Per-graph assertions (real pointer events, not direct JS calls):
  A. drag each node in turn: at every step, cross-check all non-arc polyline
     edges against a "preview routing independently recomputed in Python"
     (visible straight -> straight; blocked -> inflated-corner visibility
     graph shortest path + shortcut, same caliber c=16/17.5), proving the
     bend points are recomputed frame by frame rather than pinned (the
     regression gate for jacky issue 2);
     endpoints use the delivery-caliber anchor: ray border exit clamped into
     the edge-midpoint +/- half-card band (mirror of the interactive layer's
     borderPoint = routing.border_point + Router.midband_reanchor) on
     per-node DOM geometry (window.__stdrawNodeGeom; v0.7.9 per-card height
     replaced the global cardH, so the delivered layout.json no longer
     describes node boxes);
  B. forced vg scenario: drag a third node onto the midpoint of some straight
     edge -> that edge becomes a polyline (preview obstacle avoidance) and
     matches the recompute; keep dragging away -> still consistent (the old
     detour leaves no stale residue);
  C. zero page errors throughout.

SKIP exit 2 when playwright is unavailable. Usage:
  python tests/probe_drag_follow.py [graph-name filter substring]
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
    print("SKIP  probe_drag_follow: playwright unavailable (optional layer)")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def _pin_local_stdraw():
    """ref-scrubbed same-tree self-check: in script mode sys.path[0]=tests/, so an
    in-process import hits the site-packages editable install
    (__editable__.stdraw-*.pth pointing at the shared main tree), while the demo
    render subprocess uses this tree's code with cwd=ROOT -- when the two trees
    are out of sync the cross-check is always red (root cause of the stock 0/19).
    Strip the editable meta_path hooks and force stdraw to load from the tree
    this probe lives in."""
    if not os.path.isfile(os.path.join(ROOT, "stdraw", "__init__.py")):
        print("SKIP  probe_drag_follow: stdraw package not found in this tree: %s" % ROOT)
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
        print("SKIP  probe_drag_follow: stdraw not loaded from this tree: %s"
              % stdraw.__file__)
        sys.exit(2)


_pin_local_stdraw()
# jacky's manual-layout export directory (local acceptance source); fall back to corpus auto layouts when unset/absent.
# Injected via an environment variable to avoid hard-coding machine-specific paths into the repo: STDRAW_MANUAL_SWEEP_DIR=...
MANUAL_DIR = os.environ.get("STDRAW_MANUAL_SWEEP_DIR", "")


def _border_point_midband(cx, cy, hw, hh, toward):
    """Delivery-caliber border anchor (mirror of the interactive layer's
    borderPoint, which documents itself as 'routing.border_point +
    Router.midband_reanchor'): ray-determined border exit, then the anchor is
    clamped along that border's tangent into the edge-midpoint +/- half-card
    band (orthogonal exits land on the midpoint, diagonal exits pulled back
    into the band, corners excluded). The planning-layer stdraw.routing
    .border_point used here previously does NOT clamp, so the probe's
    expected anchors drifted from the delivered preview anchors the moment
    the midband caliber landed."""
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return (cx, cy)
    if dx == 0:
        return (cx, cy + (hh if dy > 0 else -hh))
    if dy == 0:
        return (cx + (hw if dx > 0 else -hw), cy)
    t = min(hw / abs(dx), hh / abs(dy))
    px, py = cx + dx * t, cy + dy * t
    if abs(abs(px - cx) - hw) <= abs(abs(py - cy) - hh):
        lim = hh / 2.0
        return (px, cy + max(-lim, min(lim, py - cy)))
    lim = hw / 2.0
    return (cx + max(-lim, min(lim, px - cx)), py)


def _expected_preview_route(nodes_px, a, b):
    from stdraw.visibility import seg_rect_distance, shortest_path, _shortcut
    A, B = nodes_px[a], nodes_px[b]
    pa = _border_point_midband(A[0], A[1], A[2], A[3], B)
    pb = _border_point_midband(B[0], B[1], B[2], B[3], A)
    rects = [tuple(nodes_px[v]) for v in nodes_px if v not in (a, b)]
    if not rects or all(seg_rect_distance(pa, pb, r) >= 16 - 1e-6 for r in rects):
        return [list(pa), list(pb)]
    path = shortest_path(tuple(pa), tuple(pb), rects, 17.5)
    if path is None:
        return None
    return [list(p) for p in _shortcut(path, rects, 17.5)]


def _match(js_pts, expect, tol=0.6):
    if expect is None or len(js_pts) != len(expect):
        return False
    return all(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
               for p, q in zip(js_pts, expect))


def _fallback_keeps_shape(js_pts, prev_pts, tol=0.6):
    """Honest fallback caliber when expected is unreachable (None): JS keeps
    the shape and re-anchors -- bend points match the previous frame
    (endpoints may move via re-anchoring). Not judged when prev_pts=None
    (first frame / initial CLI geometry)."""
    if not prev_pts or len(js_pts) != len(prev_pts):
        return False
    return all(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
               for p, q in zip(js_pts[1:-1], prev_pts[1:-1]))


def _nodes_px(pg):
    """Live interactive geometry straight from the drag layer
    (window.__stdrawNodeGeom): per-node x/y/w/h, where h is DOM-synced
    (v0.7.9 per-card height). The delivered layout.json's global cardH no
    longer describes node boxes, so reading geometry from `lay` made every
    expected anchor wrong for nodes whose label height differs from cardH."""
    return {r[0]: (r[1], r[2], r[3] / 2.0, r[4] / 2.0)
            for r in pg.evaluate("window.__stdrawNodeGeom()")}


def _center(pg, vid):
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


def _check_all_edges(pg, payload, tag, failures, prev=None, fallbacks=None,
                    drag_node=None):
    """prev: {edge_idx: previous frame pts} (for the fallback-caliber check);
    fallbacks: counter table.

    Assertion scope = the drag promise surface: (1) edges incident to the
    dragged node (unconditionally rerouted every frame); (2) currently
    polyline-shaped edges (recomputed whenever obstacles change, incl. the
    dense vg/poly baseline). Non-incident two-point straight lines (CLI
    anchor variants / not triggered) are outside the "live follow" promise
    and are skipped.
    """
    npx = _nodes_px(pg)
    allpts = pg.evaluate("window.__stdrawEdgePts()")
    for i, e in enumerate(payload["edges"]):
        if e.get("arc"):
            continue
        incident = drag_node is not None and drag_node in (e["a"], e["b"])
        poly = len(allpts[i]) > 2
        if not (incident or poly):
            continue
        ex = _expected_preview_route(npx, e["a"], e["b"])
        if ex is not None:
            ok = _match(allpts[i], ex)
        else:
            # visibility graph unreachable: honest fallback = shape-preserving re-anchor (or initial CLI geometry)
            ok = (prev is None) or _fallback_keeps_shape(allpts[i], prev.get(i))
            if ok and fallbacks is not None:
                fallbacks[i] = fallbacks.get(i, 0) + 1
        if not ok:
            failures.append(f"{tag}: edge {e['a']}->{e['b']} not recomputed on drag "
                            f"(n={len(allpts[i])} expect_n="
                            f"{len(ex) if ex else 'unreachable'})")
            return False, allpts
    return True, allpts


def sweep_graph(browser, src_dir, tmp, filt):
    name = os.path.basename(src_dir.rstrip("/\\"))
    if filt and filt not in name:
        return None
    lay_src = os.path.join(src_dir, "layout.json")
    cld = os.path.join(src_dir, "graph.cld")
    with open(lay_src, encoding="utf-8") as f:
        lay0 = json.load(f)
    manual = {"viewBox": lay0["viewBox"],
              "nodes": {v: {"x": p["x"], "y": p["y"]}
                        for v, p in lay0["nodes"].items()}}
    mp = os.path.join(tmp, name + "-manual.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manual, f, ensure_ascii=False)
    out = os.path.join(tmp, name)
    r = subprocess.run([PY, "-m", "stdraw", "layout", cld, "--outdir", out,
                        "--skip-3d", "--from-layout", mp],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    if r.returncode not in (0, 1):
        return (name, False, f"CLI exit {r.returncode}: {r.stderr[-200:]}")
    demo = os.path.join(out, "demo-2d.html")
    payload = json.loads(open(demo, encoding="utf-8").read()
                         .split('<script id="stdraw-data" type="application/json">')[1]
                         .split("</script>")[0].replace("<\\/", "</"))
    failures = []
    ctx = browser.new_context(viewport={"width": 1600, "height": 1500})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("file://" + demo.replace("\\", "/"))
    pg.wait_for_timeout(300)

    # A. drag node by node (each node independent: reset after dragging)
    dragged = 0
    fallbacks = {}
    for v in [n["id"] for n in payload["nodes"]]:
        cx, cy = _center(pg, v)
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        ok = True
        prev = None          # first frame prev=None: accept initial CLI geometry / first-compute result
        for k in range(1, 4):
            pg.mouse.move(cx + 14 * k, cy + 9 * k, steps=1)
            pg.wait_for_timeout(40)
            ok, prev = _check_all_edges(pg, payload, f"drag {v} step{k}",
                                        failures, prev, fallbacks, drag_node=v)
            if not ok:
                break
        pg.mouse.up()
        pg.wait_for_timeout(80)
        if ok:
            dragged += 1
        pg.click("#stdraw-reset")
        pg.wait_for_timeout(80)
        if failures:
            break

    # B. forced vg: a third node presses onto a straight edge midpoint -> polyline appears and cross-checks -> still matches after dragging away.
    # Pre-screen on the Python side first (the expected route after c presses the midpoint is a polyline) to pick a viable
    # combination, so "visibility graph unreachable -> honest straight line kept" is not misjudged as a failure.
    vg_forced = None
    if not failures:
        straight = [e for e in payload["edges"]
                    if not e.get("arc") and len(e["pts"]) == 2]
        picked = None
        for e in straight:
            a, b = e["a"], e["b"]
            na = next(n for n in payload["nodes"] if n["id"] == a)
            nb = next(n for n in payload["nodes"] if n["id"] == b)
            mx = (na["x"] + nb["x"]) / 2
            my = (na["y"] + nb["y"]) / 2
            for c in [n["id"] for n in payload["nodes"] if n["id"] not in (a, b)]:
                npx_try = _nodes_px(pg)
                npx_try[c] = (mx, my, npx_try[c][2], npx_try[c][3])
                ex_try = _expected_preview_route(npx_try, a, b)
                if ex_try and len(ex_try) > 2:
                    picked = (e, a, b, c, mx, my)
                    break
            if picked:
                break
        if picked:
            e, a, b, c, mx, my = picked
            sx, sy = _to_screen(pg, mx, my)
            if 0 < sx < 1600 and 0 < sy < 1500:
                ccx, ccy = _center(pg, c)
                pg.mouse.move(ccx, ccy)
                pg.mouse.down()
                pg.mouse.move(sx, sy, steps=3)
                pg.wait_for_timeout(60)
                ei = payload["edges"].index(e)
                pts = pg.evaluate(f"window.__stdrawEdgePts({ei})")
                npx = _nodes_px(pg)
                ex = _expected_preview_route(npx, a, b)
                became_poly = len(pts) > 2 and _match(pts, ex)
                pg.mouse.move(sx + 30, sy - 22, steps=2)
                pg.wait_for_timeout(60)
                pts2 = pg.evaluate(f"window.__stdrawEdgePts({ei})")
                npx = _nodes_px(pg)
                ex2 = _expected_preview_route(npx, a, b)
                # when unreachable, accept the honest fallback (shape-preserving re-anchor: bend points match the pressed frame)
                still = (_match(pts2, ex2) if ex2 is not None
                         else _fallback_keeps_shape(pts2, pts))
                pg.mouse.up()
                pg.wait_for_timeout(80)
                vg_forced = (a, b, c, became_poly, still,
                             len(pts), len(pts2))
                if not became_poly:
                    failures.append(f"force-vg: {a}->{b} no polyline after pressing "
                                    f"(n={len(pts)} expect_n="
                                    f"{len(ex) if ex else '?'})")
                if not still:
                    failures.append(f"force-vg: {a}->{b} not recomputed after dragging away (n2={len(pts2)})")
            else:
                vg_forced = ("screen coordinates out of range, combination skipped",)
        else:
            vg_forced = ("no feasible press combination (all unreachable / no straight edges)",)
        pg.click("#stdraw-reset")
        pg.wait_for_timeout(80)

    if errors:
        failures.append(f"page errors: {errors[:2]}")
    ctx.close()
    return (name, not failures,
            f"dragged {dragged}/{len(payload['nodes'])} nodes, "
            f"force-vg {vg_forced}" + ("; " + "; ".join(failures[:2])
                                       if failures else ""))


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    if os.path.isdir(MANUAL_DIR):
        srcs = sorted(os.path.join(MANUAL_DIR, d)
                      for d in os.listdir(MANUAL_DIR)
                      if os.path.isdir(os.path.join(MANUAL_DIR, d))
                      and os.path.exists(os.path.join(MANUAL_DIR, d, "layout.json")))
        src_label = f"jacky manual layout {MANUAL_DIR}"
    else:
        import glob
        srcs = sorted(glob.glob(os.path.join(ROOT, "benchmarks/corpus/classic/*.cld")))
        src_label = "corpus auto layout"
    tmp = tempfile.mkdtemp(prefix="stdraw-sweep-")
    passed = failed = skipped = 0
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="msedge", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            print(f"== drag-follow sweep ({src_label}, {len(srcs)} graphs) ==")
            for src in srcs:
                if not src.endswith(".cld"):
                    res = sweep_graph(browser, src, tmp, filt)
                else:  # corpus fallback: wrap it (use the auto-rendered directory)
                    out = os.path.join(tmp, "auto-" + os.path.basename(src)[:-4])
                    subprocess.run([PY, "-m", "stdraw", "layout", src,
                                    "--outdir", out, "--skip-3d"],
                                   capture_output=True, cwd=ROOT)
                    res = sweep_graph(browser, out, tmp, filt)
                if res is None:
                    skipped += 1
                    continue
                name, ok, detail = res
                print(("PASS " if ok else "FAIL ") + name + "  " + detail)
                if ok:
                    passed += 1
                else:
                    failed += 1
            browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n== {passed} PASS / {failed} FAIL / {skipped} skipped ==")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
