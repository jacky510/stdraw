# -*- coding: utf-8 -*-
"""Comb-bilateral placement (v0.7.7): K_{m,2}-family graphs.

Ground truth = jacky's hand-pulled HDD supply-chain layout (2026-11-07):
6 source nodes in one vertical column (column x spread <= 10px in the hand
pull; the engine delivers exact alignment), two non-adjacent hubs in
symmetric left/right slots at the column middle row, every hub edge a
straight line forming a near-horizontal fan, and the single in-column edge
a vertical straight line.

Structure detection (deterministic, graph-theoretic):
  - exactly two hub candidates h1, h2, non-adjacent, whose neighbor sets
    are identical and equal to the common-neighbor source set S (|S| = m >= 3);
  - every remaining core node lives in the induced subgraph on S + rest as
    pendant trees, each tree containing exactly one source node (the root);
  - detection sits in the auto-v2 priority chain before ring (a K_{m,2}
    graph scores a high non-bridge ratio and a 4-cycle "main ring", which
    historically misfired the ring ratio branch).

Geometry (all coordinates on the 2px grid):
  - sources + pendant trees in one vertical column, constant pitch,
    pendant descendants placed above their root (post-order DFS, children
    first, declaration-order tie-break) so pendants sit at the column end;
  - components ordered by the declaration index of their root;
  - hubs at (axis_x -+ hub_dx, hub_y) with hub_y at the column middle row;
    mirror symmetry is exact by construction (hub_symmetry_err = 0);
  - hub edges are NOT constructed here: the standard Router routes them and
    the trial gate requires every route to be a straight line (the comb
    contract); any deviation falls back to the next tier untouched.
"""
import math


class InfeasibleComb(Exception):
    """Raised when the comb template cannot be realized (e.g. deg0 strip)."""


MAX_COMB_N = 12   # trigger upper bound, same caliber as the other small-graph modes
MIN_SOURCES = 3   # K_{3,2} minimum: below this the pair is not a bilateral hub pair
HUB_CORRIDOR = 110    # extra corridor px beyond the clearance reserve in hub_dx
HUB_DX_MIN = 200      # aesthetic floor for the hub half-span


def _adjacency(edges):
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def detect_comb(graph):
    """Trigger detection. Returns a comb plan dict or None (no trigger).

    plan = {"hubs": [left, right], "sources": [S in declaration order],
            "column": [ordered column, top -> bottom], "m": int,
            "components": {root: [tree nodes in column order]}, "deg0": [...]}
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 2 * 1 + MIN_SOURCES or n > MAX_COMB_N:
        return None
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj.get(v)]
    deg0 = [v for v in nodes if not adj.get(v)]
    if len(core) < 2 + MIN_SOURCES:
        return None

    decl = {v: i for i, v in enumerate(nodes)}
    best = None
    for i in range(len(core)):
        for j in range(i + 1, len(core)):
            h1, h2 = core[i], core[j]
            if h2 in adj[h1]:
                continue                       # hubs must be non-adjacent
            S = adj[h1] & adj[h2]
            if len(S) < MIN_SOURCES:
                continue
            if adj[h1] != S or adj[h2] != S:
                continue                       # hubs connect exactly to the sources
            rest = [v for v in core if v not in S and v not in (h1, h2)]
            plan = _pendant_trees(nodes, S, rest, adj)
            if plan is None:
                continue
            key = (-len(S), decl[h1], decl[h2])
            if best is None or key < best[0]:
                best = (key, h1, h2, sorted(S, key=lambda v: decl[v]), plan)
    if best is None:
        return None
    _, h1, h2, sources, (comps, column) = best
    return {"hubs": [h1, h2], "sources": sources, "column": column,
            "components": comps, "m": len(sources), "deg0": deg0}


def _pendant_trees(nodes, S, rest, adj):
    """Induced subgraph on S + rest must be a forest of trees, each holding
    exactly one source node (the root). Returns ({root: column order}, full
    column order) or None."""
    Sset = set(S)
    inside = set(S) | set(rest)
    tree_adj = {v: set() for v in inside}
    for v in inside:
        for w in adj[v]:
            if w in inside:
                tree_adj[v].add(w)
    # connected components (deterministic, declaration-order traversal)
    decl = {v: i for i, v in enumerate(nodes)}
    seen = set()
    comps = []
    for v in sorted(inside, key=lambda x: decl[x]):
        if v in seen:
            continue
        stack, comp = [v], []
        seen.add(v)
        while stack:
            u = stack.pop()
            comp.append(u)
            for w in sorted(tree_adj[u], key=lambda x: decl[x]):
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        comps.append(comp)
    roots = {}
    for comp in comps:
        srcs = [v for v in comp if v in Sset]
        if len(srcs) != 1:
            return None                        # a tree must hang off exactly one source
        if len(comp) > 1:
            # tree check: connected + edges == nodes-1 (a cycle fails this)
            ecount = sum(len(tree_adj[v]) for v in comp) // 2
            if ecount != len(comp) - 1:
                return None                    # cycle among sources/pendants
        roots[comp[0]] = srcs[0]
    # column order: components by root declaration index; inside a tree,
    # post-order DFS (children before the node, pendant chains at the top)
    column, comp_order = [], {}
    def post(v, parent):
        for w in sorted(tree_adj[v], key=lambda x: decl[x]):
            if w != parent:
                post(w, v)
        column.append(v)
        comp_order.setdefault(roots_root[v], []).append(v)
    # map node -> its component root
    roots_root = {}
    for comp in comps:
        r = roots[comp[0]]
        for v in comp:
            roots_root[v] = r
    for comp in sorted(comps, key=lambda c: decl[roots[c[0]]]):
        r0 = roots[comp[0]]
        post(r0, None)
        # ensure the whole component got appended contiguously in this pass
    return {roots[comp[0]]: [v for v in comp_order.get(roots[comp[0]], [])]
            for comp in comps}, column


def _hub_fan_clear(pos, y, widths, card_h, plan, cfg, margin=4.0,
                   ang_margin=2.0):
    """Conservative straight-fan feasibility proxy. For every hub edge
    (anchored via border_point facing the other box): every unrelated box
    must be cleared by clearance + margin AND both anchor departure angles
    must be >= ANCHOR_MIN_DEG + ang_margin (the Router soft-rejects shallow
    anchor exits, which hands the edge to a polyline — the comb contract
    needs the straight candidate to actually win).

    Wider hub spans improve box clearance but flatten the fan angles, so the
    two conditions bracket an admissible window; the caller widens from the
    aesthetic floor and stops at the first admissible span."""
    import math as _m
    from .routing import border_point, ANCHOR_MIN_DEG
    from .visibility import seg_rect_distance
    boxes = {v: (pos[v], y[v], widths[v] / 2.0, card_h / 2.0) for v in pos}

    def _ang(v, anchor, other):
        cx, cy, hw, hh = boxes[v]
        on_x = abs(abs(anchor[0] - cx) - hw) <= abs(abs(anchor[1] - cy) - hh)
        dx, dy = other[0] - anchor[0], other[1] - anchor[1]
        n = _m.hypot(dx, dy)
        if n < 1e-9:
            return 0.0
        tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
        c = abs(dx * tx + dy * ty) / n
        return _m.degrees(_m.acos(max(0.0, min(1.0, c))))

    def _slide(v, anchor, off):
        """Slide an anchor along its border tangent by off px (clamped to the
        border segment) — mirrors Router._offset_anchors; the router's
        candidate pool uses +/-10/20/30 slides, so the proxy must too."""
        cx, cy, hw, hh = boxes[v]
        on_x = abs(abs(anchor[0] - cx) - hw) <= abs(abs(anchor[1] - cy) - hh)
        if on_x:
            t = max(-hh + 3, min(hh - 3, anchor[1] + off - cy))
            return [anchor[0], cy + t]
        t = max(-hw + 3, min(hw - 3, anchor[0] + off - cx))
        return [cx + t, anchor[1]]

    def _edge_ok(s, h):
        A, B = boxes[s], boxes[h]
        base_a = border_point(A[0], A[1], A[2], A[3],
                              B[0] - A[0], B[1] - A[1])
        base_b = border_point(B[0], B[1], B[2], B[3],
                              A[0] - B[0], A[1] - B[1])
        for off in (0, 10, 20, 30):
            for sign in (1, -1):
                pa = base_a if off == 0 else _slide(s, base_a, off * sign)
                pb = base_b if off == 0 else _slide(h, base_b, off * sign)
                clear_ok = True
                for v, rect in boxes.items():
                    if v in (s, h):
                        continue
                    if seg_rect_distance(pa, pb, rect) < cfg.clearance + margin:
                        clear_ok = False
                        break
                if not clear_ok:
                    continue
                if min(_ang(s, pa, pb), _ang(h, pb, pa)) < ANCHOR_MIN_DEG + ang_margin:
                    continue
                return True                    # some router-pool variant works
        return False

    for s in plan["sources"]:
        for h in plan["hubs"]:
            if not _edge_ok(s, h):
                return False
    return True


def place_comb(plan, widths, card_h, cfg):
    """Comb template -> ({v: x}, {v: y}, meta). All integers, 2px grid."""
    col = plan["column"]
    k = len(col)
    pitch = cfg.pitch
    top = cfg.top
    axis_x = int(round((cfg.margin + max(widths[v] for v in col) / 2.0) / 2) * 2)
    y = {v: top + i * pitch for i, v in enumerate(col)}
    hub_y_raw = top + (k - 1) * pitch / 2.0
    hub_y = int(round(hub_y_raw / 2) * 2)
    hl, hr = plan["hubs"]
    hub_w = max(widths[hl], widths[hr])
    wmax = max(widths[v] for v in col)
    hub_dx = max(HUB_DX_MIN,
                 int((wmax + hub_w) / 2 + cfg.clearance + HUB_CORRIDOR))
    hub_dx = int(math.ceil(hub_dx / 2) * 2)
    pos = {v: axis_x for v in col}
    pos[hl] = axis_x - hub_dx
    pos[hr] = axis_x + hub_dx
    y[hl] = y[hr] = hub_y
    # Deterministic widening: the hub half-span must let the straight fan
    # clear every column box (steep lines from the column ends cut across
    # intermediate boxes when the wings are too close). 24px steps, bounded;
    # exhausted -> the comb template is infeasible for these card widths.
    for _ in range(16):
        if _hub_fan_clear(pos, y, widths, card_h, plan, cfg):
            break
        hub_dx += 24
        pos[hl] = axis_x - hub_dx
        pos[hr] = axis_x + hub_dx
    else:
        raise InfeasibleComb(
            "hub half-span cannot realize an all-straight fan "
            f"within +{16 * 24}px widening")
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = max(cfg.margin, axis_x - total / 2)
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18
    meta = {
        "placement": "comb-bilateral",
        "comb": {
            "column": list(col),
            "hubs": [hl, hr],
            "sources": list(plan["sources"]),
            "axis_x": axis_x,
            "hub_dx": hub_dx,
            "hub_y": hub_y,
            "m": plan["m"],
        },
    }
    return pos, y, meta
