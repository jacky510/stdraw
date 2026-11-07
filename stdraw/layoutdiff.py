# -*- coding: utf-8 -*-
"""Layout diff (aesthetics-collection loop, ref-scrubbed): three-layer comparison of the auto layout vs the manual layout.

Human drags -> machine diff -> AI distills aesthetic rules -> feeds back into the objective function; this module is the "machine diff" stage,
outputting both machine-readable (JSON) and human-readable (stdout table) formats:

    1) Node level: per-node displacement vector (dx,dy,|d|) + direction classification (toward loop center / toward column alignment /
          toward symmetry; |d| < 4px counts as "not moved");
    2) Structural level: before/after table of key metrics -- crossings / card presses (1px accounting) / row alignment rate /
          minimum card gap / spacing CV / average edge length / symmetry-axis error / loop cohesion
          (auto vs manual columns + delta);
    3) Semantic level (when --cld/.json carries a graph): loops and roles (on-ring / branch) of moved nodes,
          whether they end up closer to their main ring after the move; per-loop cohesion changes.

Accounting (all reproducible; definitions are also written into the output definitions block):
    - Edge geometry: polylines take route.points; arcs (arc+ctrl) are discretized into 24 quadratic Bezier segments;
    - Crossings: for edge pairs sharing no endpoint, any segment intersection counts as 1 pair (same accounting as certificate crossings);
    - Card presses: edge sample points (4px step) entering unrelated card rectangles (+1px margin), deduplicated by edge x card;
    - Row alignment rate: grouped by y difference <= 4px, in-group count / n (metrics.ROW_EPS accounting);
    - Spacing CV: std/mean of nearest-neighbor center distances (same accounting as the certificate);
    - Symmetry-axis error: vertical axis x = mean(x_i); for node i, the distance from its mirror point (2a-x_i, y_i) to the nearest
        other node is err_i; symmetry-axis error = mean(err_i) (smaller means more mirror symmetry);
    - Loop cohesion: average pairwise distance of on-ring nodes / ring diameter (largest pairwise distance); smaller means more compact.
"""
import argparse
import json
import math
import os
import sys


# ── Geometry primitives (independent recomputation, same accounting as metrics.py/routing.py) ──
EPS = 1e-9
ROW_EPS = 4


def _seg_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < EPS else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    if d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0:
        return True
    if d1 == 0 and d2 == 0 and d3 == 0 and d4 == 0:
        def on(a, b, c):
            return (min(a[0], b[0]) - EPS <= c[0] <= max(a[0], b[0]) + EPS and
                    min(a[1], b[1]) - EPS <= c[1] <= max(a[1], b[1]) + EPS)
        if on(p3, p4, p1) or on(p3, p4, p2) or on(p1, p2, p3) or on(p1, p2, p4):
            near = [q for q in (p3, p4) for p in (p1, p2)
                    if abs(q[0] - p[0]) < EPS and abs(q[1] - p[1]) < EPS]
            return len(near) == 0
    return False


def _dist_point_rect(px, py, cx, cy, hw, hh):
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def _quad_points(p0, ctrl, p1, n=24):
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p1[1]))
    return out


def _sample(pts, step=4.0):
    out = []
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(d / step))
        for k in range(n):
            t = k / n
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    out.append(tuple(pts[-1]))
    return out


# ── Layout loading and metrics ──
def _load_layout(path):
    with open(path, encoding="utf-8") as f:
        lay = json.load(f)
    if "nodes" not in lay or "edges" not in lay:
        raise SystemExit(f"{path}: not a layout.json (missing nodes/edges)")
    return lay


def _edge_polys(lay):
    """Edge list [(a,b)] and discretized polylines (arcs as 24 Bezier segments)."""
    edges, polys = [], []
    for e in lay["edges"]:
        r = e.get("route", {})
        pts = [tuple(p) for p in r.get("points", [])]
        if r.get("arc") and r.get("ctrl") and len(pts) >= 2:
            pts = _quad_points(pts[0], tuple(r["ctrl"]), pts[-1], 24)
        edges.append((e["a"], e["b"]))
        polys.append(pts)
    return edges, polys


def _symmetry_err(pos):
    """Symmetry-axis error: vertical axis x=mean(x); mean_i min_{j!=i} dist(mirror_i, p_j)."""
    if len(pos) < 2:
        return 0.0
    axis = sum(p[0] for p in pos.values()) / len(pos)
    errs = []
    for v, (x, y) in pos.items():
        mx = 2 * axis - x
        best = min(math.hypot(mx - q[0], y - q[1])
                   for w, q in pos.items() if w != v)
        errs.append(best)
    return sum(errs) / len(errs)


def _node_sym_err(pos, v):
    axis = sum(p[0] for p in pos.values()) / len(pos)
    x, y = pos[v]
    mx = 2 * axis - x
    return min(math.hypot(mx - q[0], y - q[1]) for w, q in pos.items() if w != v)


def layout_metrics(lay, graph=None):
    """Key metrics of a single layout (independent recomputation with certificate accounting + symmetry/cohesion extensions)."""
    nodes = lay["nodes"]
    card_h = lay.get("meta", {}).get("cardH", 44)
    ids = list(nodes)
    pos = {v: (nodes[v]["x"], nodes[v]["y"]) for v in ids}
    boxes = {v: (nodes[v]["x"], nodes[v]["y"],
                 nodes[v].get("w", 140) / 2, card_h / 2) for v in ids}
    edges, polys = _edge_polys(lay)

    crossings = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a1, b1 = edges[i]
            a2, b2 = edges[j]
            if a1 in (a2, b2) or b1 in (a2, b2):
                continue
            hit = False
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if _seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                crossings += 1

    occ = 0
    for i, (a, b) in enumerate(edges):
        pts = _sample(polys[i])
        for v in ids:
            if v in (a, b):
                continue
            cx, cy, hw, hh = boxes[v]
            if any(_dist_point_rect(px, py, cx, cy, hw + 1, hh + 1) <= 0
                   for (px, py) in pts):
                occ += 1

    total_len = 0.0
    for pts in polys:
        total_len += sum(math.dist(pts[k], pts[k + 1])
                         for k in range(len(pts) - 1))
    avg_len = total_len / len(polys) if polys else 0.0

    ysorted = sorted(p[1] for p in pos.values())
    aligned, i = 0, 0
    while i < len(ysorted):
        j = i
        while j + 1 < len(ysorted) and ysorted[j + 1] - ysorted[j] <= ROW_EPS:
            j += 1
        if j > i:
            aligned += j - i + 1
        i = j + 1
    row_rate = aligned / len(ids) if ids else 0.0

    gaps = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            va, vb = boxes[ids[a]], boxes[ids[b]]
            dx = abs(va[0] - vb[0]) - (va[2] + vb[2])
            dy = abs(va[1] - vb[1]) - (va[3] + vb[3])
            gaps.append(math.hypot(max(dx, 0.0), max(dy, 0.0)))
    min_gap = min(gaps) if gaps else 0.0

    nn = []
    for a in ids:
        nn.append(min(math.dist(pos[a], pos[b]) for b in ids if b != a))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn
          if nn and mean_nn else 0.0)

    m = {
        "crossings": crossings,
        "edge_card_press_1px": occ,
        "row_align_rate": round(row_rate, 3),
        "min_card_gap": round(min_gap, 1),
        "spacing_cv": round(cv, 3),
        "avg_edge_length": round(avg_len, 1),
        "symmetry_axis_err_px": round(_symmetry_err(pos), 1),
    }

    # loop cohesion (when a graph is given): average pairwise distance of on-ring nodes / ring diameter
    if graph is not None:
        loops = {}
        for lp in graph.loops:
            members = [v for v in lp.nodes if v in pos]
            if len(members) < 2:
                continue
            ds = [math.dist(pos[a], pos[b])
                  for ii, a in enumerate(members) for b in members[ii + 1:]]
            dia = max(ds)
            loops[lp.id] = {
                "cohesion": round((sum(ds) / len(ds)) / dia, 3) if dia > EPS else None,
                "mean_pairwise_px": round(sum(ds) / len(ds), 1),
                "diameter_px": round(dia, 1),
            }
        m["loops"] = loops
    return m


# ── Three-layer diff ──
def diff_layouts(auto, manual, graph=None, auto_path="", manual_path=""):
    an, mn = auto["nodes"], manual["nodes"]
    missing = [v for v in an if v not in mn]
    extra = [v for v in mn if v not in an]
    if missing or extra:
        raise SystemExit(f"layout node sets do not match: missing {missing}, extra {extra}")
    apos = {v: (an[v]["x"], an[v]["y"]) for v in an}
    mpos = {v: (mn[v]["x"], mn[v]["y"]) for v in mn}

    loops_of = {}
    if graph is not None:
        for lp in graph.loops:
            for v in lp.nodes:
                loops_of.setdefault(v, []).append(lp.id)

    # column-alignment reference: an x shared by >= 3 nodes (within +/-2px) in manual counts as a column
    def _columns(pos):
        xs = sorted(p[0] for p in pos.values())
        cols, cur = [], [xs[0]]
        for x in xs[1:]:
            if x - cur[-1] <= 2:
                cur.append(x)
            else:
                cols.append(cur)
                cur = [x]
        cols.append(cur)
        return [sum(c) / len(c) for c in cols if len(c) >= 3]

    mcols = _columns(mpos)

    node_level = []
    for v in sorted(an):
        dx = mpos[v][0] - apos[v][0]
        dy = mpos[v][1] - apos[v][1]
        d = math.hypot(dx, dy)
        item = {"node": v, "dx": dx, "dy": dy, "|d|": round(d, 1),
                "tags": []}
        if d < 4:
            item["tags"] = ["not moved (<4px)"]
            node_level.append(item)
            continue
        # toward loop center: the angle between the displacement and (loop center (auto) - original position) is small (projection ratio >= 0.6)
        for lid in loops_of.get(v, []):
            members = [w for w in
                       next(l for l in graph.loops if l.id == lid).nodes
                       if w in apos]
            c = (sum(apos[w][0] for w in members) / len(members),
                 sum(apos[w][1] for w in members) / len(members))
            vec = (c[0] - apos[v][0], c[1] - apos[v][1])
            proj = (dx * vec[0] + dy * vec[1]) / (d * math.hypot(*vec)) \
                if math.hypot(*vec) > EPS else 0.0
            if proj >= 0.6:
                item["tags"].append(f"toward loop center ({lid})")
            elif proj <= -0.6:
                item["tags"].append(f"away from loop center ({lid})")
        # toward column alignment: manual x falls into some column (within +/-2px) while auto x does not
        if any(abs(mpos[v][0] - col) <= 2 for col in mcols) and \
           not any(abs(apos[v][0] - col) <= 2 for col in mcols):
            item["tags"].append("toward column alignment")
        # toward symmetry: the node's symmetry error drops significantly (below 70%)
        if _node_sym_err(mpos, v) < 0.7 * _node_sym_err(apos, v):
            item["tags"].append("toward symmetric position")
        if not item["tags"]:
            item["tags"] = ["free displacement"]
        node_level.append(item)

    ma, mm = layout_metrics(auto, graph), layout_metrics(manual, graph)
    structural = {}
    for k in ("crossings", "edge_card_press_1px", "row_align_rate",
              "min_card_gap", "spacing_cv", "avg_edge_length",
              "symmetry_axis_err_px"):
        structural[k] = {"auto": ma[k], "manual": mm[k],
                         "delta": round(mm[k] - ma[k], 3)}

    semantic = None
    if graph is not None:
        sem_nodes = []
        for it in node_level:
            v = it["node"]
            if it["tags"] == ["not moved (<4px)"] or not loops_of.get(v):
                if it["tags"] != ["not moved (<4px)"] and not loops_of.get(v):
                    sem_nodes.append({"node": v, "role": "branch",
                                      "loops": []})
                continue
            entries = []
            for lid in loops_of[v]:
                members = [w for w in
                           next(l for l in graph.loops if l.id == lid).nodes
                           if w in apos]
                peers_a = [w for w in members if w != v]
                peers_m = peers_a
                da = (sum(math.dist(apos[v], apos[w]) for w in peers_a)
                      / len(peers_a)) if peers_a else 0.0
                dm = (sum(math.dist(mpos[v], mpos[w]) for w in peers_m)
                      / len(peers_m)) if peers_m else 0.0
                entries.append({"loop": lid,
                                "closer_to_loop_center_after": dm < da,
                                "dist_auto_px": round(da, 1),
                                "dist_manual_px": round(dm, 1)})
            sem_nodes.append({"node": v, "role": "on-ring",
                              "loops": loops_of[v], "loop_moves": entries})
        semantic = {
            "nodes": sem_nodes,
            "loops": {
                lid: {"cohesion_auto": ma["loops"].get(lid, {}).get("cohesion"),
                      "cohesion_manual": mm["loops"].get(lid, {}).get("cohesion"),
                      "mean_pairwise_delta_px": round(
                          (mm["loops"].get(lid, {}).get("mean_pairwise_px", 0) -
                           ma["loops"].get(lid, {}).get("mean_pairwise_px", 0)), 1)}
                for lid in ma.get("loops", {})}

        }

    return {
        "tool": "stdraw layout-diff",
        "auto": auto_path,
        "manual": manual_path,
        "node_level": node_level,
        "structural": structural,
        "semantic": semantic,
        "definitions": {
            "moved": "|d| >= 4px; everything else counts as not moved",
            "crossings": "edge pairs sharing no endpoint count 1 per any segment intersection (same caliber as the certificate); "
                         "arcs discretized as 24 quadratic Bezier segments",
            "edge_card_press_1px": "edge sample points (4px) entering unrelated card rectangles (+1px), deduplicated per edge x card",
            "row_align_rate": "grouped counting with y difference <= 4px / n",
            "symmetry_axis_err_px": "axis x=mean(x_i); mean_i min_{j!=i} dist(mirror_i, p_j), "
                                    "smaller means more mirror-symmetric",
            "loop_cohesion": "average pairwise distance of on-ring nodes / ring diameter (smaller means more cohesive)",
            "delta": "manual - auto",
        },
    }


def _human(diff):
    out = []
    out.append(f"layout diff: {diff['auto']} (auto) vs {diff['manual']} (manual)")
    out.append("")
    out.append("-- node level (displacement vectors + orientation) --")
    for it in diff["node_level"]:
        out.append(f"  {it['node']:<24} dx={it['dx']:>5} dy={it['dy']:>5} "
                   f"|d|={it['|d|']:>6}  {'; '.join(it['tags'])}")
    out.append("")
    out.append("-- structural level (auto -> manual, delta = manual - auto) --")
    for k, v in diff["structural"].items():
        out.append(f"  {k:<22} {v['auto']:>10} → {v['manual']:>10}  Δ={v['delta']}")
    if diff.get("semantic"):
        out.append("")
        out.append("-- semantic level (loop membership and cohesion) --")
        for n in diff["semantic"]["nodes"]:
            if not n.get("loops") and n["role"] != "branch":
                continue
            moves = "; ".join(
                f"{m['loop']}:{m['dist_auto_px']}→{m['dist_manual_px']}px"
                f"({'closer' if m['closer_to_loop_center_after'] else 'farther'})"
                for m in n.get("loop_moves", [])) or "-"
            out.append(f"  {n['node']:<24} [{n['role']}] {moves}")
        for lid, lp in diff["semantic"]["loops"].items():
            out.append(f"  loop {lid}: cohesion {lp['cohesion_auto']} -> "
                       f"{lp['cohesion_manual']}, mean pairwise distance delta="
                       f"{lp['mean_pairwise_delta_px']}px")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="stdraw layout-diff",
        description="three-layer diff of the auto layout vs the manual layout (data source of the aesthetics-collection loop)")
    ap.add_argument("auto", help="automatic layout layout.json")
    ap.add_argument("manual", help="manual layout layout.json (or an exported subset)")
    ap.add_argument("--cld", default=None,
                    help="graph source (.cld/.json), enables the semantic layer (loop membership / cohesion)")
    ap.add_argument("--out", default="layout-diff.json",
                    help="machine-readable JSON output path (default ./layout-diff.json; "
                         "empty string skips writing)")
    a = ap.parse_args(argv)

    graph = None
    if a.cld:
        from .__main__ import load_graph
        graph = load_graph(a.cld)

    auto = _load_layout(a.auto)
    manual = _load_layout(a.manual)
    d = diff_layouts(auto, manual, graph, a.auto, a.manual)
    print(_human(d))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"\nmachine-readable JSON -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
