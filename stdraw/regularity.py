# -*- coding: utf-8 -*-
"""Placement regularity (WS2 item 6): structure detection + computable mathematical definitions.

"Regularity" in this module is given entirely as **computable mathematical
definitions** (docs/crossing-exact.md §6,
same source as this file's docstring); no eyeball judgment:

1. Structure detection detect_structure:
   cycle   — connected and every vertex degree = 2 (single-cycle graph)
   chain   — connected, degrees <= 2 with exactly two degree-1 vertices (chain graph)
   general — everything else

2. Cycle regular-polygon deviation D_poly (range [0,1), 0 = a perfect regular k-gon):
   Let the k drawn center points be p_1..p_k, centroid c = mean(p_i), radii
   r_i = |p_i - c|, adjacent polar-angle gaps
   delta_i = (theta_{i+1} - theta_i) mod 2pi (theta in cycle order).
     radial_cv   = std(r) / mean(r)
     angular_cv  = std(delta) / mean(delta)
     D_poly      = 1 - exp(-(radial_cv + angular_cv))
   The exp form guarantees monotonicity, boundedness and a differentiable
   interpretation: both CVs are 0 <=> D_poly = 0.

3. Chain straightness S_straight (range [0,1], 1 = fully collinear/monotone polyline):
   Chain vertices in chain order p_1..p_k, interior turn angle alpha_i = the
   angle between the two adjacent segments
   (cos-normalized, in [-1,1], collinear same-direction = 1).
     S_straight = mean_i (alpha_i + 1) / 2
   Perfectly straight = 1; a random zigzag ~= 0.5; many reversals ~= 0.

4. Symmetry-axis alignment A_sym (range [0,1], 1 = a vertical axis exists such
   that all nodes pair up as mirror images):
   Candidate axes = the x coordinates of all nodes (plus all pairwise midpoints,
   on a 24px-tolerance slot grid).
   For each candidate axis c, the mirror-partner hit rate:
     hit(c) = |{i : exists j != i, y_j = y_i, |x_j - (2c - x_i)| <= 24}| / k
   A_sym = max_c hit(c). The vertical-axis convention matches the row
   structure (y rows).

5. Full report regularity_report: the dominant item is picked by structure
   detection, every metric is computed,
   and all enter the certificate (structure only decides which one is the
   "dominant metric"; nothing else is hidden).
"""
import math
from collections import defaultdict


def detect_structure(graph):
    """Structure detection (see module docstring §1). Returns {kind, cycle_nodes, chain_nodes}."""
    nodes = graph.node_ids()
    adj = graph.adj_undirected()
    comps = _components(nodes, adj)
    cycle_nodes, chain_nodes = [], []
    for comp in comps:
        degs = [len(adj[v]) for v in comp]
        if degs and all(d == 2 for d in degs):
            cycle_nodes.append(sorted(comp))
        elif all(d <= 2 for d in degs) and degs.count(1) == 2:
            chain_nodes.append(sorted(comp))
    kind = "general"
    if len(comps) == 1:
        if cycle_nodes:
            kind = "cycle"
        elif chain_nodes:
            kind = "chain"
    return {"kind": kind, "cycle_nodes": cycle_nodes, "chain_nodes": chain_nodes}


def _components(nodes, adj):
    seen, comps = set(), []
    for v in nodes:
        if v in seen:
            continue
        stack, comp = [v], []
        seen.add(v)
        while stack:
            x = stack.pop()
            comp.append(x)
            for w in adj[x]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        comps.append(comp)
    return comps


def cycle_polygon_deviation(positions, cycle):
    """Cycle regular-polygon deviation D_poly (see §2). positions: {node: (x, y)}."""
    k = len(cycle)
    if k < 3:
        return 0.0
    pts = [positions[v] for v in cycle]
    cx = sum(p[0] for p in pts) / k
    cy = sum(p[1] for p in pts) / k
    rs = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    mr = sum(rs) / k
    radial_cv = (math.sqrt(sum((r - mr) ** 2 for r in rs) / k) / mr) if mr else 0.0
    angles = [math.atan2(p[1] - cy, p[0] - cx) for p in pts]
    deltas = []
    for i in range(k):
        d = (angles[(i + 1) % k] - angles[i]) % (2 * math.pi)
        deltas.append(d)
    md = sum(deltas) / k
    angular_cv = (math.sqrt(sum((d - md) ** 2 for d in deltas) / k) / md) if md else 0.0
    return 1.0 - math.exp(-(radial_cv + angular_cv))


def chain_straightness(positions, chain):
    """Chain straightness S_straight in [0,1] (see §3). chain: node list in chain order."""
    if len(chain) < 3:
        return 1.0
    seq = chain if len(chain) >= 2 else []
    s = 0.0
    cnt = 0
    for i in range(1, len(seq) - 1):
        p0, p1, p2 = (positions[seq[i - 1]], positions[seq[i]],
                      positions[seq[i + 1]])
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        s += (cosang + 1.0) / 2.0
        cnt += 1
    return s / cnt if cnt else 1.0


def symmetry_axis_alignment(positions, tol=24.0):
    """Symmetry-axis alignment A_sym in [0,1] (see §4)."""
    items = list(positions.items())
    if len(items) < 2:
        return 1.0
    xs = [p[0] for _, p in items]
    cands = set()
    for x in xs:
        cands.add(round(x / tol) * tol)
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            cands.add(round((xs[i] + xs[j]) / 2 / tol) * tol)
    best = 0.0
    for c in cands:
        hits = 0
        for v, (x, y) in items:
            mirror = 2 * c - x
            if any(abs(yy - y) <= 1e-6 and abs(xx - mirror) <= tol
                   for vv, (xx, yy) in items if vv != v):
                hits += 1
        best = max(best, hits / len(items))
    return best


def regularity_report(graph, positions):
    """Full regularity report (the dominant metric is decided by structure detection; the rest are still computed and reported)."""
    st = detect_structure(graph)
    out = {
        "structure": st["kind"],
        "cycle_polygon_deviation": None,
        "chain_straightness": None,
        "symmetry_axis_alignment": round(
            symmetry_axis_alignment(positions), 3),
    }
    if st["cycle_nodes"]:
        vals = [cycle_polygon_deviation(positions, cyc)
                for cyc in st["cycle_nodes"]]
        out["cycle_polygon_deviation"] = round(max(vals), 3)
    if st["chain_nodes"]:
        vals = [chain_straightness(positions, ch) for ch in st["chain_nodes"]]
        out["chain_straightness"] = round(min(vals), 3)
    out["dominant"] = {
        "cycle": "cycle_polygon_deviation",
        "chain": "chain_straightness",
        "general": "symmetry_axis_alignment",
    }[st["kind"] if st["kind"] in ("cycle", "chain") else "general"]
    return out
