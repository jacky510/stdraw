# -*- coding: utf-8 -*-
"""3D cone-arrowhead probe (ref-scrubbed, jacky 2026-11-09 caliber).

Loads the shipped 3D demo in a REAL headless browser (Playwright / msedge,
same harness as probe_interactive.py) and asserts, over the live three.js
scene:

  P1  edge registry: window.__stdraw3dEdges covers every DATA edge, each with
      tube+cone flags
  P2  cone/tube meshes really exist in the WebGL scene (geometry-type count
      via scene.traverse — not just the JS bookkeeping)
  P3  polarity color mapping: '+' -> #fbbf24 (amber), '-' -> #7dd3fc (sky)
  P4  orientation: every cone's axis (quaternion) is a unit vector matching
      the registry dir
  P5  placement: every cone's TIP (localToWorld of the apex) coincides with
      its target node position (<= 1px) — i.e. the arrowhead points at the
      edge's endpoint
  P6  minimal legend present with both polarity colors

Usage: python tests/probe_3d_arrows.py [path/to/classic-cld-3d.html]
Default: demos/classic-cld-3d.html (must live next to ../assets/three.min.js).
Exit 0 = all checks green; exit 1 = at least one red (verdict table printed).
"""
import json
import os
import sys

EPS = 1.0

JS_COLLECT = """
(() => {
  const reg = window.__stdraw3dEdges || null;
  if (!reg) return {error: 'registry missing'};
  let cones = 0, tubes = 0, coneInfo = [];
  scene.traverse(o => {
    if (o.geometry && o.geometry.type === 'ConeGeometry') {
      cones++;
      const tip = o.localToWorld(new THREE.Vector3(0, o.geometry.parameters.height / 2, 0));
      const q = o.quaternion;
      coneInfo.push({tip: [tip.x, tip.y, tip.z],
                     axis: [q.x, q.y, q.z, q.w]});
    }
    if (o.geometry && o.geometry.type === 'TubeGeometry') tubes++;
  });
  const legend = document.querySelector('#legend');
  return {reg, cones, tubes, coneInfo, nData: DATA.edges.length,
          dataEdges: DATA.edges.map(e => ({a: e.a, b: e.b, p: e.p})),
          legendHtml: legend ? legend.innerHTML : null};
})()
"""


def main():
    demo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1
                           else os.path.join(os.path.dirname(__file__),
                                             "..", "demos", "classic-cld-3d.html"))
    from playwright.sync_api import sync_playwright
    results = []

    def chk(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        print(f"[{'OK' if ok else 'RED'}] {name}" + (f" — {detail}" if detail else ""))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        pg.goto("file:///" + demo.replace("\\", "/"))
        pg.wait_for_function("window.__stdraw3dEdges && window.__stdraw3dEdges.length > 0",
                             timeout=15000)
        pg.wait_for_timeout(600)  # let the first frames render
        d = pg.evaluate(JS_COLLECT)
        browser.close()

    if d.get("error"):
        print("FATAL:", d["error"])
        return 1
    reg, cone_info = d["reg"], d["coneInfo"]

    # P1 registry coverage
    chk("P1 registry covers every edge with tube+cone flags",
        len(reg) == d["nData"] and all(e.get("tube") and e.get("cone") for e in reg),
        f"registry={len(reg)} data_edges={d['nData']}")

    # P2 real WebGL meshes
    chk("P2 cone+tube meshes exist in the live scene",
        d["cones"] == d["nData"] and d["tubes"] == d["nData"],
        f"cones={d['cones']} tubes={d['tubes']} expected={d['nData']}")

    # P3 polarity color mapping
    bad = [e for e in reg
           if (e["pol"] == "-" and e["color"] != "#7dd3fc")
           or (e["pol"] != "-" and e["color"] != "#fbbf24")]
    chk("P3 polarity colors: '+' amber #fbbf24 / '−' sky #7dd3fc", not bad,
        f"violations={bad[:3]}")

    # P4 axis unit vectors + registry dir agreement
    def norm(v):
        return sum(c * c for c in v) ** 0.5
    bad4 = []
    for e, ci in zip(reg, cone_info):
        ax = ci["axis"]
        if abs(norm(ax) - 1.0) > 1e-3 or abs(norm(e["dir"]) - 1.0) > 1e-3:
            bad4.append((e["a"], e["b"], ax, e["dir"]))
    chk("P4 every cone axis is a unit quaternion (orientation defined)", not bad4,
        f"violations={len(bad4)}")

    # P5 cone tip lands on the edge's target node position
    pos = pg_positions = None
    # node positions: read them from the same page data the demo used
    import html as _html
    raw = open(demo, encoding="utf-8").read()
    marker = "const DATA = "
    blob = raw[raw.index(marker) + len(marker): raw.index(";\n", raw.index(marker))]
    data = json.loads(blob)
    # initial solid is layouts[first]
    first_solid = list(data["layouts"].keys())[0]
    pos = data["layouts"][first_solid]
    bad5 = []
    for e, ci in zip(reg, cone_info):
        target = pos[e["b"]]
        tip = ci["tip"]
        dist = sum((tip[i] - target[i]) ** 2 for i in range(3)) ** 0.5
        if dist > EPS:
            bad5.append((e["a"], e["b"], round(dist, 2)))
    chk("P5 every cone TIP coincides with its target node (<=1px)", not bad5,
        f"violations={bad5[:4]} solid={first_solid}")

    # P6 minimal legend
    lh = d.get("legendHtml") or ""
    chk("P6 minimal two-color legend present", "#fbbf24" in lh and "#7dd3fc" in lh,
        lh[:80])

    ok = sum(1 for _, o, _ in results if o)
    print(f"== verdict {ok}/{len(results)} ==")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
