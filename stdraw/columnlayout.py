# -*- coding: utf-8 -*-
"""Column placement for long-chain / few-ring graphs (2026-11-06 jacky
layout aesthetics v2, ref-scrubbed).

> "If the box placement can follow a pattern, make it so — e.g. align
> into a vertical column... Draw the lines to follow the box
> arrangement. Regularity makes the figure nicer and easier to
> understand."

Trigger detection (graph-theoretic metrics, fully deterministic;
decided after ringlayout.detect_ring's pure-cycle and ratio branches,
before the cover branch):
  1. Small graph: 3 <= n <= MAX_COLUMN_N (n includes isolated nodes);
  2. Few rings: the longest simple loop k satisfies 3 <= k <=
     MAX_RING_K (a small main ring -> "ring" does not dominate, strong
     chain feel; a big ring with k = n belongs to ring placement);
  3. Long chain: nodes outside the main ring hang as "branches" beside
     their spine neighbors (residuals <= n - k).

Spine selection (isomorphism consistency: structural-signature driven,
not dependent on declared loop id order):
  candidates = declared loops (those forming simple loops, direction
  kept) ∪ graph-theoretically enumerated simple loops;
  chosen deterministically by "longest ring -> fewest negative edges
  (all-positive growth loops preferred as spine) -> WL structural
  color signature lexicographic order".

Placement (place_column):
  - Spine nodes align into one central column (x = column axis,
    y = top + i·pitch);
  - The spine closing edge (last->first) is constructed as a large
    left arc (quadratic bezier, control point extrapolated left of
    the column axis on a deterministic ladder, analytically verified
    to keep clearance >= `clearance` from every box) — the
    column-form realization of "loop cohesion / ring feel";
  - Branches (residuals) hang beside their spine neighbors: right
    column first (opposite the closing arc), aligned to the anchor
    row or to the cross-row midpoint; multi-branch structures go
    right column -> left column (the left column is extrapolated
    further out beyond the closing arc);
  - Isolated nodes park in the top parking strip (same as existing
    patterns).

Routing/certificate: delegated to the existing Router and
certificate_auto; the column-mode metric criteria (spine column
alignment + uniform row pitch + loop cohesion) switch inside
metrics/check on meta.placement == "column-chain". The closing arc
is injected as a constructed route (same override mechanism as
--from-layout waypoints; translated by dx/dy before coordinate
delivery).
"""
import math
from collections import defaultdict

MAX_COLUMN_N = 12          # trigger upper bound: small graphs
MAX_RING_K = 4             # main ring <= 4 counts as "few rings" (5+ goes to ring placement)
SIDE_GAP = 36              # horizontal clearance between branch columns and the spine (breathing-room tier)
ARC_MARGIN = 20            # extra margin of the closing arc beyond the leftmost obstacle
ARC_LADDER = (0, 24, 48, 72, 96, 128, 160)   # arc control-point extrapolation ladder (px)


class InfeasibleColumn(Exception):
    """Column slot infeasible (no solution for the closing arc / branch slot) — the caller falls back to the existing path."""


def _adjacency(edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _wl_colors(nodes, adj):
    """WL-style structural colors (2 refine rounds): {v: tuple}. Corresponding
    nodes of isomorphic graphs share a color (structural signature, id
    independent) — the mechanism behind "isomorphic skeleton -> same layout template"."""
    color = {v: (len(adj[v]),) for v in nodes}
    for _ in range(2):
        nxt = {}
        for v in nodes:
            nxt[v] = (color[v],
                      tuple(sorted(color[w] for w in sorted(adj[v]))))
        # compress to ranks (deterministic: index by sorted signature order)
        order = {sig: i for i, sig in enumerate(sorted(set(nxt.values())))}
        color = {v: (order[nxt[v]],) for v in nodes}
    return color


def _edge_signs(edges):
    """Undirected key -> set of polarities (one-to-many when bidirectional edges exist)."""
    signs = defaultdict(set)
    for a, b, pol in edges:
        signs[(a, b) if a < b else (b, a)].add(pol)
    return signs


def _neg_count(seq, edges, adj):
    """Number of negative directed edges along the ring order (segments adjacent only undirected count 0)."""
    esign = {}
    for a, b, pol in edges:
        esign[(a, b)] = pol
        esign.setdefault((b, a), pol)
    neg = 0
    for i in range(len(seq)):
        a, b = seq[i], seq[(i + 1) % len(seq)]
        if esign.get((a, b)) == "-":
            neg += 1
    return neg


def _declared_loop_cycles(graph, adj):
    out = []
    for lp in graph.loops:
        seq = list(lp.nodes)
        if len(seq) < 3 or len(set(seq)) != len(seq):
            continue
        if not all(seq[(i + 1) % len(seq)] in adj[seq[i]] for i in range(len(seq))):
            continue
        out.append((lp.id, seq))
    return out


def _enumerate_cycles(nodes, adj, cap=2_000_000):
    """Simple-loop enumeration with the same criteria as ringlayout (canonical-form dedup, step cap)."""
    steps = [0]
    found = {}

    def canon(seq):
        best = None
        for s in (list(seq), list(seq)[::-1]):
            for i in range(len(s)):
                rot = s[i:] + s[:i]
                if best is None or rot < best:
                    best = rot
        return tuple(best)

    class _Cap(Exception):
        pass

    def dfs(start, v, path, seen):
        steps[0] += 1
        if steps[0] > cap:
            raise _Cap
        for w in sorted(adj[v]):
            if w == start and len(path) >= 3:
                c = canon(path)
                found[c] = c
            elif w not in seen:
                seen.add(w)
                dfs(start, w, path + [w], seen)
                seen.remove(w)

    try:
        for s in sorted(nodes):
            dfs(s, s, [s], {s})
    except _Cap:
        pass
    return [list(c) for c in found.values()]


def detect_column(graph, why=None):
    """Trigger detection + spine selection. Returns a column plan dict or None.

    plan = {"spine": [spine order (directed, start = structurally most
            salient node)], "k": int, "declared_loop": id|None,
            "residuals": [non-spine non-isolated nodes], "deg0": [isolated
            nodes], "closing": (last, first) spine closing edge}

    why: optional dict — receives a deterministic one-line reason for the
    outcome (mode decision trace, certificate mode_decision_trace field).
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 3 or n > MAX_COLUMN_N:
        if why is not None:
            why["reason"] = (f"n={n} (need 3..{MAX_COLUMN_N})")
        return None
    edges = [(e.a, e.b, getattr(e, "polarity", "+")) for e in graph.edges]
    adj = _adjacency([(a, b) for a, b, _ in edges])
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if not core:
        if why is not None:
            why["reason"] = "no core nodes (no edges)"
        return None

    cands = []                                   # [(ring order, loop_id, negative-edge count)]
    for lid, seq in _declared_loop_cycles(graph, adj):
        cands.append((seq, lid, _neg_count(seq, edges, adj)))
    for seq in _enumerate_cycles(core, adj):
        cands.append((seq, None, _neg_count(seq, edges, adj)))
    if not cands:
        if why is not None:
            why["reason"] = ("no simple loop (declared or enumerated) — "
                             "nothing to close the main chain")
        return None

    kmax = max(len(s) for s, _, _ in cands)
    if kmax < 3 or kmax > MAX_RING_K:
        if why is not None:
            why["reason"] = (f"longest simple loop k={kmax} "
                             f"(need 3..{MAX_RING_K})")
        return None
    # Pure ring (single component, all degree 2, k=n) goes to ring placement
    if kmax == n and all(len(adj[v]) == 2 for v in core):
        if why is not None:
            why["reason"] = (f"pure ring k=n={n} — belongs to ring-cycle "
                             "(pure-cycle trigger)")
        return None
    # Main ring covers the whole graph (k=n) -> ring-dominated, not column
    if kmax >= n:
        if why is not None:
            why["reason"] = (f"main ring covers the whole graph (k={kmax} "
                             f">= n={n}) — ring-dominated, not column")
        return None

    colors = _wl_colors(core, adj)
    eligible = [(s, lid, neg) for s, lid, neg in cands if len(s) == kmax]
    # Selection: fewest negative edges (all-positive loop as spine) -> structural-color signature -> declared first -> canonical form
    best = None
    for seq, lid, neg in eligible:
        key = (neg, tuple(sorted(tuple(colors[v]) for v in seq)),
               0 if lid is not None else 1, _canon(seq))
        if best is None or key < best[0]:
            best = (key, seq, lid)
    _, spine0, lid = best
    spine = _orient_spine(spine0, adj, colors, edges)
    residuals = [v for v in core if v not in set(spine)]
    if why is not None:
        why["reason"] = (f"main ring k={len(spine)} < n={n} "
                         "(small main ring -> strong chain reading)")
    return {"spine": spine, "k": len(spine), "declared_loop": lid,
            "residuals": residuals, "deg0": deg0,
            "closing": (spine[-1], spine[0])}


def _canon(seq):
    best = None
    for s in (list(seq), list(seq)[::-1]):
        for i in range(len(s)):
            rot = s[i:] + s[:i]
            if best is None or rot < best:
                best = rot
    return tuple(best)


def _orient_spine(seq, adj, colors, edges):
    """Ring order -> directed spine order: start = structurally most salient node
    (WL color -> degree -> id); direction = along directed edges (the ring
    adjacency direction that directed edge a->b follows)."""
    esign = set()
    for a, b, _ in edges:
        esign.add((a, b))
    n = len(seq)
    # Candidate start: take the first by (structural color max lexicographically = most salient, degree, -id order)
    start = max(seq, key=lambda v: (tuple(colors[v]), len(adj[v]),
                                    tuple(-ord(c) for c in str(v))))
    # Of the two ring orientations take the one with more "directed-edge follows"; tie -> smaller canonical order
    def directed_follows(order):
        c = 0
        for i in range(len(order)):
            if (order[i], order[(i + 1) % len(order)]) in esign:
                c += 1
        return c
    o1 = [seq[(seq.index(start) + i) % n] for i in range(n)]
    o2 = [seq[(seq.index(start) - i) % n] for i in range(n)]
    c1, c2 = directed_follows(o1), directed_follows(o2)
    if c1 != c2:
        return o1 if c1 > c2 else o2
    return o1 if _canon(o1) <= _canon(o2) else o2


def _quad_points(p0, ctrl, p1, seg=24):
    """Quadratic bezier sampling (same criteria as routing.quad_points)."""
    return [[(1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * p1[1]]
            for t in (i / seg for i in range(seg + 1))]


def _pt_rect_dist(px, py, cx, cy, hw, hh):
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def _arc_clear(pts, nodes_px, a, b, clearance):
    """Arc clearance verification (same criteria as check3): dense sampling via
    sample_polyline step=4 — the bezier chord-tangent effect reaches ~4px at
    the high-curvature ends; sparse sampling would miss it."""
    from .routing import sample_polyline
    dense = sample_polyline([tuple(p) for p in pts], step=4.0)
    for v, (nx, ny, nw, nh) in nodes_px.items():
        if v in (a, b):
            continue
        for px, py in dense:
            if _pt_rect_dist(px, py, nx, ny, nw / 2, nh / 2) < clearance + 2:
                return False
    return True


def _closing_arc(nodes_px, spine, widths, card_h, clearance, side_cols):
    """Spine closing edge (last->first): a large left-side arc.

    The bulge of a quadratic bezier at t=0.5 = |ctrl - chord midpoint| /
    2 — the control point is solved directly from "target bulge line =
    left edge of the leftmost obstacle - (clearance + margin)", then
    verified analytically against every box; on failure it is
    extrapolated on a 48px ladder (up to 6 rungs); still infeasible ->
    Infeasible.

    side_cols: {side(-1 left/+1 right): [(cx, hw), ...]} branch boxes
    already placed on that side (the arc must avoid them).
    Returns {"kind": "arc", "points": [...], "ctrl": [x, y],
             "anchors": {...}, "min_clear": float}
    """
    a_last, a_first = spine[-1], spine[0]
    xa, ya = nodes_px[a_last][0], nodes_px[a_last][1]
    xb, yb = nodes_px[a_first][0], nodes_px[a_first][1]
    ha = widths[a_last] / 2
    hb = widths[a_first] / 2
    pa = [xa - ha, ya]                      # midpoint of the lower card's left edge
    pb = [xb - hb, yb]                      # midpoint of the upper card's left edge
    ymid = (ya + yb) / 2
    # Target bulge line: left edge of every box to avoid - (clearance + 4px conservative margin)
    target = None
    for v, (nx, ny, nw, nh) in nodes_px.items():
        if v in (a_last, a_first):
            continue
        t = nx - nw / 2 - clearance - 4
        target = t if target is None else min(target, t)
    if target is None:
        target = (pa[0] + pb[0]) / 2 - clearance - ARC_MARGIN
    chord_mid = (pa[0] + pb[0]) / 2
    base_ctrl = 2.0 * target - chord_mid    # the t=0.5 bulge exactly reaches target
    for step in (0, 48, 96, 144, 192, 240):
        ctrl = [base_ctrl - step, ymid]
        pts = _quad_points(pa, ctrl, pb)
        ok = _arc_clear(pts, nodes_px, a_last, a_first, clearance)
        if ok:
            return {"kind": "arc", "points": pts, "ctrl": ctrl,
                    "min_clear": None}
    raise InfeasibleColumn("no feasible extrapolation tier for the closing arc")


def _side_arc(nodes_px, a, b, side, widths, card_h, clearance):
    """A spine cross-row chord edge (spine node pair with |row diff| >= 2) is
    constructed as a large arc on `side`.

    Same math as _closing_arc: t=0.5 bulge = |ctrl - chord midpoint| / 2;
    the control point is solved from the target bulge line + verified per
    box + extrapolated on a 48px ladder (6 rungs); returns None if
    infeasible (the caller falls back to the Router candidate pool).
    side=+1 right / -1 left."""
    xa, ya = nodes_px[a][0], nodes_px[a][1]
    xb, yb = nodes_px[b][0], nodes_px[b][1]
    pa = [xa + side * widths[a] / 2, ya]
    pb = [xb + side * widths[b] / 2, yb]
    ymid = (ya + yb) / 2
    target = None
    for v, (nx, ny, nw, nh) in nodes_px.items():
        if v in (a, b):
            continue
        t = (nx + side * nw / 2) + side * (clearance + 4)
        target = t if target is None else (max(target, t) if side > 0
                                           else min(target, t))
    chord_mid = (pa[0] + pb[0]) / 2
    if target is None:
        target = chord_mid + side * (clearance + ARC_MARGIN)
    base_ctrl = 2.0 * target - chord_mid
    for step in (0, 48, 96, 144, 192, 240):
        ctrl = [base_ctrl + side * step, ymid]
        pts = _quad_points(pa, ctrl, pb)
        ok = _arc_clear(pts, nodes_px, a, b, clearance)
        if ok:
            return {"kind": "arc", "points": pts, "ctrl": ctrl,
                    "min_clear": None}
    return None


def place_column(plan, widths, card_h, cfg, adj, edges):
    """Column placement -> ({v: x}, {v: y}, meta, closing_routes). All on the
    2px grid, deterministic.

    Branch columns: right column first (+1); extra branches overflow to
    the left column (-1, the closing arc yields by extrapolating further
    out). A single-anchor branch sits on the anchor's row; a two-anchor
    branch sits at the midpoint of the two anchor rows (half-pitch
    offset).
    """
    spine = plan["spine"]
    k = len(spine)
    x0 = 0                                     # column axis (uniformly translated at the delivery layer)
    pitch = cfg.pitch
    pos, y = {}, {}
    for i, v in enumerate(spine):
        pos[v] = x0
        y[v] = cfg.top + i * pitch
    spine_w_max = max(widths[v] for v in spine)

    # Group residuals (mutually adjacent residuals = one branch structure); anchors = the group's spine neighbors
    spine_set = set(spine)
    res_set = set(plan["residuals"])
    groups = []                                # [(anchor tuple, [residual nodes] (id order))]
    seen = set()
    for v in sorted(plan["residuals"]):
        if v in seen:
            continue
        comp, stack = [], [v]
        seen.add(v)
        while stack:
            u = stack.pop()
            comp.append(u)
            for w in sorted(adj[u] & res_set):
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        anch = tuple(sorted(set().union(*[adj[u] & spine_set for u in comp])))
        groups.append((anch, sorted(comp)))
    # Deterministic group order: anchor row positions on the spine -> anchor tuple -> member ids
    def _group_key(g):
        anch, comp = g
        rows = tuple(sorted(spine.index(a) for a in anch))
        return (rows, anch, tuple(comp))
    groups.sort(key=_group_key)

    # Column geometry: right column (+1) first; the closing arc occupies the left, overflow groups go left (arc yields)
    closing_side = -1
    wmax_side = max([widths[v] for _, comp in groups for v in comp] or [10])
    side_x = int((spine_w_max / 2 + SIDE_GAP + wmax_side / 2) / 2) * 2
    col_slots = {1: [], -1: []}                # occupied row positions [y]
    side_cols = {1: [], -1: []}                # (cx, hw) for the closing arc to avoid

    def _base_y(anch):
        """Group row position: single anchor = the anchor's row; multiple anchors = midpoint of the first/last anchor rows."""
        if len(anch) == 1:
            return y[anch[0]]
        return (y[anch[0]] + y[anch[-1]]) / 2

    def _try_place(anch, comp, side):
        """Place the whole group into the `side` column: members expand from base
        by whole pitches downward/upward (pitch >= card_h+SIDE_GAP,
        guaranteeing in-group clearance); slot conflict -> None."""
        base = _base_y(anch)
        offsets = []
        for i in range(len(comp)):
            offsets.append(((i + 1) // 2) * pitch * (1 if i % 2 == 0 else -1))
        ys = [base + off for off in offsets]
        for yy in ys:
            if any(abs(yy - q) < card_h + SIDE_GAP for q in col_slots[side]):
                return None
        out = {}
        for v, yy in zip(comp, ys):
            out[v] = (int((side * side_x) / 2) * 2, int(round(yy / 2) * 2))
        return out

    for anch, comp in groups:
        placed = None
        for side in (1, -1):
            cand = _try_place(anch, comp, side)
            if cand is not None:
                placed = cand
                break
        if placed is None:
            # Fallback: same-group row-shifting ladder (probe rungs downward/upward in the right column, whole-pitch steps)
            base = _base_y(anch)
            for dy in (pitch, -pitch, pitch * 2, -pitch * 2,
                       pitch * 3 / 2, -pitch * 3 / 2):
                ys = [base + dy + off for off in
                      [((i + 1) // 2) * pitch * (1 if i % 2 == 0 else -1)
                       for i in range(len(comp))]]
                if all(not any(abs(yy - q) < card_h + SIDE_GAP
                               for q in col_slots[1]) for yy in ys):
                    placed = {v: (int(side_x / 2) * 2, int(round(yy / 2) * 2))
                              for v, yy in zip(comp, ys)}
                    break
        if placed is None:
            raise InfeasibleColumn(f"branch group {comp} has no feasible column slots")
        for v, (px, py) in placed.items():
            pos[v], y[v] = px, py
            col_slots[1 if px > x0 else -1].append(py)
            side_cols[1 if px > x0 else -1].append((px, widths[v]))

    # Isolated-node parking strip
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = x0 - total / 2
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in pos}
    closing = _closing_arc(nodes_px, spine, widths, card_h,
                           cfg.clearance, side_cols)

    # Spine cross-row chord edges (non-adjacent spine pairs): constructed as right-side
    # arcs for loop-cohesion in-chord routing (opposite the closing arc); infeasible -> Router pool
    constructed = {plan["closing"]: closing}
    row_of = {v: i for i, v in enumerate(spine)}
    eset = set(edges)
    for (a, b) in sorted(eset):
        if a not in row_of or b not in row_of:
            continue
        if (a, b) == plan["closing"] or (b, a) == plan["closing"]:
            continue
        if abs(row_of[a] - row_of[b]) < 2:
            continue
        sa = _side_arc(nodes_px, a, b, 1, widths, card_h, cfg.clearance)
        if sa is not None:
            constructed[(a, b)] = sa

    meta = {
        "placement": "column-chain",
        "column": {
            "spine": list(spine),
            "pitch": pitch,
            "axis_x": x0,
            "declared_loop": plan.get("declared_loop"),
            "closing": list(plan["closing"]),
            "closing_side": "left",
            "side_columns": {s: [v for v in sorted(pos)
                                 if v not in spine_set
                                 and (pos[v] > x0) == (s == 1)]
                             for s in (1, -1) if any(
                                 v not in spine_set and
                                 (pos[v] > x0) == (s == 1) for v in pos)},
            "residuals": list(plan["residuals"]),
        },
    }
    return pos, y, meta, constructed
