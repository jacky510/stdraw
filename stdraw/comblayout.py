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


def detect_comb(graph, why=None):
    """Trigger detection. Returns a comb plan dict or None (no trigger).

    plan = {"hubs": [left, right], "sources": [S in declaration order],
            "column": [ordered column, top -> bottom], "m": int,
            "components": {root: [tree nodes in column order]}, "deg0": [...]}

    why: optional dict — receives a deterministic one-line reason for the
    outcome (mode decision trace, certificate mode_decision_trace field).
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 2 * 1 + MIN_SOURCES or n > MAX_COMB_N:
        if why is not None:
            why["reason"] = (f"n={n} (need {2 * 1 + MIN_SOURCES}.."
                             f"{MAX_COMB_N})")
        return None
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj.get(v)]
    deg0 = [v for v in nodes if not adj.get(v)]
    if len(core) < 2 + MIN_SOURCES:
        if why is not None:
            why["reason"] = (f"core n={len(core)} "
                             f"(need >= {2 + MIN_SOURCES})")
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
        if why is not None:
            why["reason"] = ("no bilateral-hub pair: no two non-adjacent "
                             f"nodes with identical source-only neighborhoods "
                             f"(|S| >= {MIN_SOURCES})")
        return None
    _, h1, h2, sources, (comps, column) = best
    if why is not None:
        why["reason"] = (f"bilateral hubs {h1}/{h2} with identical "
                         f"source-only neighborhood |S|={len(sources)}")
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


def _side_anchor(box, other, y_override=None):
    """v0.7.8 wide-card fan anchor: the point where the center-to-center
    segment crosses the box's FACING VERTICAL border, clamped into the
    border segment (mirrors the +/-3px corner reserve of Router slides).

    Rationale (8777 wide-card root cause): for a wide column card the
    center-ray exits via the top/bottom border for almost any slope, and the
    near-horizontal fan line then grazes that horizontal border below
    ANCHOR_MIN_DEG — the global hub-span bracket can never fix it (widening
    makes the line flatter, i.e. the angle strictly worse). On the facing
    vertical border the same near-horizontal line is perpendicular (~90
    degrees) — smooth by construction. Returns [x, y] ints (x on the border
    plane, y on the 2px grid) or None when the boxes share an x-center.

    y_override: fan-spread resolver result for the hub-side anchor (the raw
    crossing clamps would stack several fan lines at the same border point
    when the column spans many rows)."""
    cx, cy, hw, hh = box
    ox = other[0]
    if abs(ox - cx) < 1e-9:
        return None
    t = hw / abs(ox - cx)
    yy = y_override if y_override is not None else cy + (other[1] - cy) * t
    lim = hh - 3
    yy = max(cy - lim, min(cy + lim, yy))
    yy = float(int(round(yy / 2.0)) * 2)
    yy = max(cy - lim, min(cy + lim, yy))
    return [int(cx + (hw if ox > cx else -hw)), int(yy)]


FAN_SEP_MIN = 8    # minimum px between distinct hub-border fan anchors


def _spread_border_ys(desired, lo, hi, sep=FAN_SEP_MIN):
    """Deterministic 1D separation of hub-border anchor slots (the
    fan_spread rule for constructed fans). The slot ORDER is fixed by the
    desired crossing y (= the source row order: keeping it is exactly the
    non-crossing condition for the fan segments); forward + backward sweeps
    then push clamped slots apart inside the border segment. Returns
    {key: final y} or None when the segment cannot host the anchors."""
    order = sorted(desired, key=lambda k: (desired[k], k))
    vals = [min(hi, max(lo, float(desired[k]))) for k in order]
    for _ in range(2 * len(vals) + 4):
        for i in range(1, len(vals)):
            if vals[i] < vals[i - 1] + sep:
                vals[i] = min(hi, vals[i - 1] + sep)
        for i in range(len(vals) - 2, -1, -1):
            if vals[i] > vals[i + 1] - sep:
                vals[i] = max(lo, vals[i + 1] - sep)
    vals = [float(int(round(v / 2.0)) * 2) for v in vals]
    for i in range(1, len(vals)):
        if vals[i] < vals[i - 1] + sep:
            vals[i] = min(hi, vals[i - 1] + sep)
    for i in range(len(vals) - 2, -1, -1):
        if vals[i] > vals[i + 1] - sep:
            vals[i] = max(lo, vals[i + 1] - sep)
    for i in range(len(vals) - 1):
        if vals[i + 1] - vals[i] < sep - 1e-9:
            return None
    return {k: v for k, v in zip(order, vals)}


def _side_fan_lines(pos, y, widths, card_h, plan, cfg, margin=4.0,
                    ang_margin=2.0):
    """Tier-1 straight-fan construction: every hub edge as the segment
    between the two facing-border anchors (_side_anchor on both boxes), with
    hub-side anchor slots spread along the border (no stacking).

    Acceptance (analytic self-checks, same caliber as _hub_fan_clear):
      - anchors exist and sit on the facing vertical border planes with a
        non-negative corridor between them (no own-box re-entry);
      - dense clearance vs every unrelated box >= clearance + margin;
      - both departure angles vs the vertical border tangent
        >= ANCHOR_MIN_DEG + ang_margin.
    Returns {(a, b): {"kind": "line", "points": [pa, pb]}} for the directed
    hub edges (both declaration directions), or None when any check fails
    (-> caller widens / gives up)."""
    import math as _m
    from .routing import ANCHOR_MIN_DEG
    from .visibility import seg_rect_distance
    boxes = {v: (pos[v], y[v], widths[v] / 2.0, card_h / 2.0) for v in pos}
    # hub-side anchor slots: raw crossing y per (hub, source), then a
    # deterministic spread inside the hub's facing border segment
    hub_ys = {}
    for h in plan["hubs"]:
        desired = {}
        for s in plan["sources"]:
            cx, cy, hw, hh = boxes[h]
            ox = boxes[s][0]
            t = hw / abs(ox - cx)
            desired[s] = cy + (boxes[s][1] - cy) * t
        spread = _spread_border_ys(desired, boxes[h][1] - (boxes[h][3] - 3),
                                   boxes[h][1] + (boxes[h][3] - 3))
        if spread is None:
            return None
        hub_ys.update({(h, s): v for s, v in spread.items()})
    out = {}
    for s in plan["sources"]:
        for h in plan["hubs"]:
            pa = _side_anchor(boxes[s], boxes[h])
            pb = _side_anchor(boxes[h], boxes[s],
                              y_override=hub_ys.get((h, s)))
            if pa is None or pb is None:
                return None
            # corridor sanity: both anchors sit on their facing border
            # planes with a non-negative gap between them (no own-box
            # re-entry: the segment's x-range stays outside both boxes)
            if boxes[h][0] < boxes[s][0]:
                if not (pb[0] + 1e-9 <= pa[0]):
                    return None
            else:
                if not (pa[0] + 1e-9 <= pb[0]):
                    return None
            for v, rect in boxes.items():
                if v not in (s, h):
                    if seg_rect_distance(pa, pb, rect) < cfg.clearance + margin:
                        return None
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            n = _m.hypot(dx, dy)
            if n < 1e-9:
                return None
            # both borders are vertical (tangent (0,1)): one check covers
            # both departure angles
            c = abs(dy) / n
            if _m.degrees(_m.acos(max(0.0, min(1.0, c)))) \
                    < ANCHOR_MIN_DEG + ang_margin:
                return None
            out[(s, h)] = {"kind": "line", "points": [list(pa), list(pb)]}
            # reverse declaration direction carries the same geometry with
            # mirrored point order (the delivery channel keys exact tuples)
            out[(h, s)] = {"kind": "line", "points": [list(pb), list(pa)]}
    # analytic self-check: fan segments converging on the same hub border
    # must not properly intersect (the fixed desired-order spread should
    # guarantee it — verify, never assume)
    from .routing import seg_cross
    for h in plan["hubs"]:
        lines = [out[(s, h)]["points"] for s in plan["sources"]]
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                if seg_cross(lines[i][0], lines[i][1],
                             lines[j][0], lines[j][1]):
                    return None
    return out


def place_comb(plan, widths, card_h, cfg):
    """Comb template -> ({v: x}, {v: y}, meta, constructed). All integers, 2px grid.

    v0.7.8: a two-tier fan realization. Tier 0 (unchanged v0.7.7 semantics)
    widens the hub half-span until the router-pool border_point anchors
    realize the all-straight fan — narrow cards stop here, byte-identical to
    v0.7.7. Only when that bracket is exhausted (wide column cards: the
    center-ray anchors graze their horizontal borders below ANCHOR_MIN_DEG
    and widening is anti-correlated with the angle) does tier 1 kick in:
    hub edges are CONSTRUCTED between facing-vertical-border anchors and
    delivered through the constructed-route channel (kind=line), with the
    same analytic self-checks; the caller's trial gate re-runs the router
    for the non-hub edges and the unified hard gates over the whole set."""

    col = plan["column"]
    k = len(col)
    pitch = cfg.pitch
    top = cfg.top
    # v0.7.11 deterministic constraint #1 (P1, 8777 HDD chain): explicit
    # source-column internal order. Components stay contiguous (a pendant
    # tree never splits); the relative order of LISTED nodes is the hard
    # constraint (component level AND inside a component), everything
    # unlisted keeps engine order after the listed ones.
    col_order = getattr(cfg, "column_order", None)
    if col_order:
        comps = plan.get("components") or {}
        rank = {v: i for i, v in enumerate(col_order)}
        engine_rank = {v: i for i, v in enumerate(col)}
        def _comp_key(root):
            members = comps.get(root) or [root]
            rs = [rank[v] for v in members if v in rank]
            return (min(rs) if rs else len(col_order), engine_rank[root])
        ordered: list = []
        for root in sorted(comps.keys(), key=_comp_key):
            members = comps[root]
            # within a component the LISTED nodes' relative order is also a
            # hard constraint (e.g. a pendant listed after its source root):
            # sort by rank first, engine DFS order as the tiebreak
            engine_pos = {v: i for i, v in enumerate(members)}
            members_sorted = sorted(members,
                                    key=lambda v: (rank.get(v, len(col_order)
                                                            + engine_pos[v]),
                                                   engine_pos[v]))
            ordered.extend(members_sorted)
        seen = set(ordered)
        ordered.extend(v for v in col if v not in seen)
        col = ordered
    axis_x = int(round((cfg.margin + max(widths[v] for v in col) / 2.0) / 2) * 2)
    y = {v: top + i * pitch for i, v in enumerate(col)}
    hub_y_raw = top + (k - 1) * pitch / 2.0
    hub_y = int(round(hub_y_raw / 2) * 2)
    hl, hr = plan["hubs"]
    # v0.7.11 deterministic constraint #2 (P1): explicit hub side assignment.
    # One explicit side is enough to fix the bilateral assignment; a
    # contradicting spec degrades deterministically (first left wins, then
    # first right) instead of raising — the fan-clearance gates downstream
    # still hold the geometry honest.
    _side = getattr(cfg, "hub_side", None) or {}
    _want = {v: s for v, s in _side.items()
             if s in ("left", "right") and v in (hl, hr)}
    _lefts = [v for v in (hl, hr) if _want.get(v) == "left"]
    _rights = [v for v in (hl, hr) if _want.get(v) == "right"]
    if (_lefts and _lefts[0] != hl) or (not _lefts and _rights and _rights[0] != hr):
        hl, hr = hr, hl
    hub_w = max(widths[hl], widths[hr])
    wmax = max(widths[v] for v in col)
    hub_dx = max(HUB_DX_MIN,
                 int((wmax + hub_w) / 2 + cfg.clearance + HUB_CORRIDOR))
    hub_dx = int(math.ceil(hub_dx / 2) * 2)
    hub_dx_floor = hub_dx
    pos = {v: axis_x for v in col}
    pos[hl] = axis_x - hub_dx
    pos[hr] = axis_x + hub_dx
    y[hl] = y[hr] = hub_y
    constructed = {}
    # Tier 0 — deterministic widening with the router-pool border_point
    # anchors (unchanged v0.7.7 semantics): the hub half-span must let the
    # straight fan clear every column box (steep lines from the column ends
    # cut across intermediate boxes when the wings are too close). 24px
    # steps, bounded. Narrow cards stop here.
    for _ in range(16):
        if _hub_fan_clear(pos, y, widths, card_h, plan, cfg):
            break
        hub_dx += 24
        pos[hl] = axis_x - hub_dx
        pos[hr] = axis_x + hub_dx
    else:
        # Tier 1 — v0.7.8 wide-card path: the tier-0 bracket is exhausted
        # (angle-bound: wider spans only flatten the fan and worsen the
        # horizontal-border departure angles). Re-run the bracket with
        # CONSTRUCTED facing-vertical-border anchors: inside the empty
        # corridor left/right of the column band both the clearance and the
        # border angle improve monotonically with the span, so the window
        # that was empty in tier 0 is searched again under a geometry where
        # the two constraints no longer conflict.
        hub_dx = hub_dx_floor
        pos[hl] = axis_x - hub_dx
        pos[hr] = axis_x + hub_dx
        fan = None
        for _ in range(16):
            fan = _side_fan_lines(pos, y, widths, card_h, plan, cfg)
            if fan is not None:
                break
            hub_dx += 24
            pos[hl] = axis_x - hub_dx
            pos[hr] = axis_x + hub_dx
        if fan is None:
            raise InfeasibleComb(
                "hub half-span cannot realize an all-straight fan "
                f"within +{16 * 24}px widening (tier-0 pool anchors and "
                "tier-1 facing-border anchors both exhausted)")
        constructed = fan
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
    # v0.7.11 constraint provenance — only stamped when a constraint was
    # actually applied, so unconstrained layouts stay byte-identical to the
    # pre-0.7.11 deterministic contract (baselines/digests untouched).
    if col_order:
        meta["comb"]["column_order"] = list(col_order)
    if _want:
        meta["comb"]["hub_side"] = {hl: "left", hr: "right"}
    if constructed:
        # tier-1 (wide-card) fan: certificate-caliber note only — the gate
        # set and semantics are unchanged (hub_edges_straight still reads
        # the delivered line kinds)
        meta["comb"]["fan"] = "facing-border"
    return pos, y, meta, constructed
