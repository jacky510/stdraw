# -*- coding: utf-8 -*-
"""Lens-chain placement (auto-v2 structural tier, small graphs).

Trigger family: every loop of the graph is a 2-cycle (mutual pair a<->b)
and the simple undirected graph (edge multiplicity ignored) is a forest --
the classic CLD "reinforcing loop + balancing loop sharing a variable"
figure (limits-to-growth, fixes-that-fail, success-to-the-successful).
The existing structural tiers all need a loop of length >= 3 (symmetric /
bowtie-vertex / spine-wing / column / ring / comb), so these graphs fell
through to the generic layered path, whose midline lens is cramped on a
44px card (both arcs attach within +-12px of the border midpoint) and
whose spacing regularity failed the CV gate.

Placement: each pair of the chain becomes a LENS -- the two boxes face each
other across LENS_GAP (border to border) and the two directed edges are
constructed as Q arcs bowing to opposite sides of the chord (lens
half-width = LENS_K/2 x chord), so each 2-node loop reads as one closed
"ring".  The chain turns right at every shared node (E -> S -> W -> N),
so consecutive lenses are perpendicular and never compete for a border.
Non-lens nodes hang off the chain in the SAME row as their parent
(pendant links, LINK_GAP), which keeps the row pitch uniform (one row per
chain link).  Multiple pair chains stack vertically, left-aligned.

Anchor caliber (16 standard anchor set, anchors.py):
  - horizontal lens (chord along x): facing CORNER anchors (ne/nw and
    se/sw) -- on a 44px card the golden pair would put both arcs within
    7.6px of each other at the box;
  - vertical lens (chord along y): facing GOLDEN anchors (s-g1/n-g2 east
    chord, n-g1/s-g2 west chord) -- corner anchors would make the lens
    wider than the boxes themselves.
Arc side rule: the edge leaving the earlier-declared node of the pair
takes the LEFT side of the travel direction (screen coordinates), the
reverse edge takes the right side -- deterministic, geometry independent.

Delivery: the whole figure is by-construction -- lens pairs as the arc
pairs above, every non-lens edge as one straight segment between facing
standard edge-midpoint anchors (link_line), so every endpoint sits on the
16-anchor set and the delivery-layer snap / arrival passes have nothing
to move (layout_auto skips them for engine lens-construct).

Trial gate (layout_auto._lens_trial): the unified constructed hard-gate
proxy passes, and the certificate-grade regularity proxies hold (spacing
CV <= 0.35, 24px column snap >= 0.6, uniform row pitch).  Any failure
falls back to the existing chain (layered), byte-for-byte unchanged.
"""
import math

from .anchors import standard_anchors
from .metrics import rect_gap
from .routing import quad_points

LENS_GAP = 150          # border-to-border gap between the two boxes of a lens (px)
LENS_K = 0.6            # Q-arc curvature coefficient x chord (lens half-width = LENS_K/2 x chord)
LINK_GAP = 48           # border-to-border gap for pendant (non-lens) links
MAX_LENS_N = 12         # trigger upper bound: small graphs (structural-tier caliber)
X_GRID = 24             # column snap grid of the auto pipeline
Y_GRID = 2              # delivery grid
CV_MAX = 0.35           # certificate cv_le_035 caliber
SNAP_MIN = 0.6          # certificate column_snap24_ge_060 caliber

DIRS = {"E": (1.0, 0.0), "S": (0.0, 1.0), "W": (-1.0, 0.0), "N": (0.0, -1.0)}
RIGHT_TURN = {"E": "S", "S": "W", "W": "N", "N": "E"}
LEFT_TURN = {"E": "N", "N": "W", "W": "S", "S": "E"}
OPPOSITE = {"E": "W", "W": "E", "N": "S", "S": "N"}
# side vector (screen coordinates, y down) the arc bows toward
SIDE_VEC = {"N": (0.0, -1.0), "S": (0.0, 1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}

# anchor ids on the facing borders, per chain direction d (A -> B):
# ((left-side chord A id, B id), (right-side chord A id, B id))
_LENS_ANCHORS = {
    # horizontal lens: facing corner anchors
    "E": (("ne", "nw"), ("se", "sw")),
    "W": (("sw", "se"), ("nw", "ne")),
    # vertical lens: facing GOLDEN anchors (not corners) -- at a node
    # shared by a horizontal and a vertical lens the corner would be
    # claimed by both lenses' arcs (measured: the horizontal lens' lower
    # arc and the vertical lens' arc meet on the shared corner and cross
    # under it); the golden pair keeps the two lenses' anchors apart on
    # the shared edge
    "S": (("s-g1", "n-g2"), ("s-g2", "n-g1")),
    "N": (("n-g1", "s-g2"), ("n-g2", "s-g1")),
}


class InfeasibleLensChain(Exception):
    """Raised when the chain template cannot be realized (no free pendant slot)."""


def _adjacency(edges):
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def detect_lens_chain(graph, why=None):
    """Trigger detection. Returns a plan dict or None (no trigger).

    plan = {"decl": {node: declaration index},
            "pairs": [(A, B) ...] (A declared before B),
            "chains": [[(A1, B1), (A2, B2), ...], ...]  (B_i == A_{i+1}),
            "trees": {chain node: [non-pair nodes in BFS order]},
            "parents": {non-pair node: its parent (chain node or pendant)},
            "deg0": [isolated nodes]}

    why: optional dict -- receives a deterministic one-line reason for the
    outcome (mode decision trace, certificate mode_decision_trace field).
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 2 or n > MAX_LENS_N:
        if why is not None:
            why["reason"] = f"n={n} (need 2..{MAX_LENS_N})"
        return None
    edges = [(e.a, e.b) for e in graph.edges]
    eset = set(edges)
    decl = {v: i for i, v in enumerate(nodes)}
    pairs = sorted({(a, b) if decl[a] < decl[b] else (b, a)
                    for a, b in edges if (b, a) in eset},
                   key=lambda p: (decl[p[0]], decl[p[1]]))
    if not pairs:
        if why is not None:
            why["reason"] = "no mutual pair (a<->b bidirectional edges)"
        return None
    adj = _adjacency(edges)
    for v in nodes:
        adj.setdefault(v, set())
    # forest test on the simple graph (mutual pairs deduped): a loop of
    # length >= 3 means a higher structural tier owns the figure
    parent = {v: v for v in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    seen = set()
    for a, b in edges:
        key = (a, b) if decl[a] < decl[b] else (b, a)
        if key in seen:
            continue
        seen.add(key)
        ra, rb = find(a), find(b)
        if ra == rb:
            if why is not None:
                why["reason"] = ("simple graph has a loop of length >= 3 "
                                 "(not a pure 2-cycle figure)")
            return None
        parent[ra] = rb
    # every node sits in at most two pairs (chain middle); three lenses on
    # one node is not templated
    npair = {}
    for a, b in pairs:
        for v in (a, b):
            npair[v] = npair.get(v, 0) + 1
    if max(npair.values()) > 2:
        if why is not None:
            why["reason"] = ("a node sits in more than two mutual pairs "
                             "(lens fan not templated)")
        return None
    # chains: walk the pair graph from each end (declaration order)
    by_node = {}
    for p in pairs:
        by_node.setdefault(p[0], []).append(p)
        by_node.setdefault(p[1], []).append(p)
    used = set()
    chains = []
    ends = sorted((v for v in by_node if len(by_node[v]) == 1),
                  key=lambda v: decl[v])
    for start in ends:
        if all(p in used for p in by_node[start]):
            continue
        cur = start
        chain = []
        while True:
            nxt = [p for p in by_node[cur] if p not in used]
            if not nxt:
                break
            p = min(nxt, key=lambda q: (decl[q[0]], decl[q[1]]))
            used.add(p)
            a, b = p
            chain.append((a, b) if a == cur else (b, a))
            cur = b if a == cur else a
        if chain:
            chains.append(chain)
    if len(used) != len(pairs):
        # unreachable by construction (a pair-graph cycle is a simple loop
        # of length >= 3, rejected above) -- honest guard
        if why is not None:
            why["reason"] = "pair graph is not a set of chains"
        return None
    # pendant trees: the simple graph is a forest, so every non-pair node
    # reaches the chain only through other non-pair nodes; BFS from the
    # earliest-declared chain node gives a deterministic tree
    pair_nodes = set(npair)
    others = [v for v in nodes if v not in pair_nodes and adj[v]]
    trees, parents = {}, {}
    assigned = set()
    for root in sorted(pair_nodes, key=lambda v: decl[v]):
        queue = [(w, root) for w in sorted(adj[root], key=lambda v: decl[v])
                 if w not in pair_nodes]
        order = []
        while queue:
            w, par = queue.pop(0)
            if w in assigned:
                continue
            assigned.add(w)
            parents[w] = par
            order.append(w)
            for u in sorted(adj[w], key=lambda v: decl[v]):
                if u not in pair_nodes and u not in assigned:
                    queue.append((u, w))
        if order:
            trees[root] = order
    if len(assigned) != len(others):
        if why is not None:
            why["reason"] = "non-pair node not reachable from a chain node"
        return None
    if why is not None:
        why["reason"] = (f"{len(pairs)} mutual pair(s) over a forest "
                         f"({len(chains)} chain(s))")
    return {"decl": decl, "pairs": pairs, "chains": chains, "trees": trees,
            "parents": parents, "edges": list(edges),
            "deg0": [v for v in nodes if not adj[v]]}


def _snap(v, grid):
    return int(round(v / float(grid))) * int(grid)


def _anchor_point(cx, cy, hw, hh, aid):
    for a in standard_anchors(cx, cy, hw, hh):
        if a[0] == aid:
            return [a[1], a[2]]
    raise InfeasibleLensChain(f"anchor {aid} not on the 16-set")


def _facing_sides(dx, dy):
    """Standard edge-midpoint anchor ids facing each other along the
    dominant axis of the center offset (a -> b, b -> a)."""
    if abs(dx) >= abs(dy):
        return ("e" if dx > 0 else "w"), ("w" if dx > 0 else "e")
    return ("s" if dy > 0 else "n"), ("n" if dy > 0 else "s")


def link_line(a, b, pos, y, widths, card_h):
    """Constructed straight link (non-lens edge): the facing standard
    edge-midpoint anchors joined by one segment (anchors_standard holds
    by construction)."""
    sa, sb = _facing_sides(pos[b] - pos[a], y[b] - y[a])
    pa = _anchor_point(pos[a], y[a], widths[a] / 2.0, card_h / 2.0, sa)
    pb = _anchor_point(pos[b], y[b], widths[b] / 2.0, card_h / 2.0, sb)
    if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 1e-6:
        raise InfeasibleLensChain(f"link {a}->{b} has zero length")
    return {"kind": "line", "points": [list(pa), list(pb)]}


def lens_arcs(A, B, d, pos, y, widths, card_h):
    """Constructed Q arcs for the pair (A -> B along chain direction d).

    Returns {(A, B): arc, (B, A): arc}, arc = {"kind": "arc",
    "points": [...], "ctrl": [x, y]}; the edge leaving A bows to the LEFT
    side of d, the reverse edge to the right side.
    """
    (la, lb), (ra, rb) = _LENS_ANCHORS[d]
    out = {}
    for (src, dst), (aid_s, aid_d), side in (((A, B), (la, lb), LEFT_TURN[d]),
                                             ((B, A), (rb, ra), RIGHT_TURN[d])):
        ps = _anchor_point(pos[src], y[src], widths[src] / 2.0, card_h / 2.0, aid_s)
        pd = _anchor_point(pos[dst], y[dst], widths[dst] / 2.0, card_h / 2.0, aid_d)
        chord = math.hypot(pd[0] - ps[0], pd[1] - ps[1])
        mid = [(ps[0] + pd[0]) / 2.0, (ps[1] + pd[1]) / 2.0]
        sv = SIDE_VEC[side]
        ctrl = [mid[0] + sv[0] * LENS_K * chord, mid[1] + sv[1] * LENS_K * chord]
        out[(src, dst)] = {"kind": "arc",
                           "points": [list(p) for p in quad_points(ps, ctrl, pd)],
                           "ctrl": ctrl}
    return out


def _slot_free(cx, cy, w, card_h, placed, min_gap):
    for (px, py, pw) in placed:
        if rect_gap(cx, cy, w, card_h, px, py, pw, card_h) < min_gap:
            return False
    return True


def _pendant_slots(parent, w, pair_dir, pos, y, widths, card_h, parents, placed, min_gap):
    """Free in-row slot centers for pendant w next to its parent (preference order)."""
    dx = widths[parent] / 2.0 + LINK_GAP + widths[w] / 2.0
    occ = set()
    travel = None
    for (A, B), d in pair_dir.items():
        if A == parent:
            occ.add(d)
            travel = travel or d
        elif B == parent:
            occ.add(OPPOSITE[d])
            travel = travel or d          # arrival direction at a chain end
    if travel is None:
        # pendant parent: travel = direction from its own parent
        pp = parents.get(parent)
        if pp is not None and y[pp] == y[parent]:
            travel = "E" if pos[parent] > pos[pp] else "W"
    if travel is None:
        travel = "E"
    pref = [LEFT_TURN[travel], RIGHT_TURN[travel], OPPOSITE[travel]]
    for d in ("E", "W"):
        if d not in pref:
            pref.append(d)
    for d in pref:
        if d not in ("E", "W") or d in occ:
            continue
        sx = pos[parent] + (dx if d == "E" else -dx)
        sy = y[parent]
        if _slot_free(sx, sy, widths[w], card_h, placed, min_gap):
            return sx, sy
    return None


def place_lens_chain(plan, widths, card_h, cfg):
    """Place the lens chains. Returns (pos, y, meta, constructed).

    pos/y: node center coordinates (relative; the delivery layer shifts
    them into the viewBox).  meta: {"placement": "lens-chain", "lens": {...}}.
    constructed: {(a, b): arc} for every lens edge.
    """
    row_pitch = card_h + LENS_GAP
    pos, y = {}, {}
    pair_dir = {}
    placed = []            # (cx, cy, w) of every placed box
    next_row = 0
    comp_left = None
    parents = plan["parents"]
    trees = plan["trees"]
    for chain in plan["chains"]:
        comp = []
        d = "E"
        cur = chain[0][0]
        pos[cur], y[cur] = 0, 0
        comp.append(cur)
        for (A, B) in chain:
            if d == "E":
                nx, ny = pos[A] + widths[A] / 2.0 + LENS_GAP + widths[B] / 2.0, y[A]
            elif d == "W":
                nx, ny = pos[A] - widths[A] / 2.0 - LENS_GAP - widths[B] / 2.0, y[A]
            elif d == "S":
                nx, ny = pos[A], y[A] + card_h + LENS_GAP
            else:
                nx, ny = pos[A], y[A] - card_h - LENS_GAP
            pos[B], y[B] = _snap(nx, X_GRID), _snap(ny, Y_GRID)
            comp.append(B)
            pair_dir[(A, B)] = d
            cur = B
            d = RIGHT_TURN[d]
        # chains that climb (N legs): the top row becomes the component's first row
        dy = next_row - min(y[v] for v in comp)
        if dy:
            for v in comp:
                y[v] += dy
        comp_placed = [(pos[v], y[v], widths[v]) for v in comp]
        # pendants: same row as the parent, first free in-row slot
        for root in [chain[0][0]] + [B for (A, B) in chain]:
            for w in trees.get(root, []):
                slot = _pendant_slots(parents[w], w, pair_dir, pos, y, widths, card_h,
                                      parents, comp_placed, cfg.min_gap)
                if slot is None:
                    raise InfeasibleLensChain(f"no free in-row slot for pendant {w}")
                pos[w], y[w] = _snap(slot[0], X_GRID), slot[1]
                comp.append(w)
                comp_placed.append((pos[w], y[w], widths[w]))
        # left-align components on the 24px grid
        left = min(pos[v] - widths[v] / 2.0 for v in comp)
        if comp_left is None:
            comp_left = left
        else:
            shift = int(round((comp_left - left) / X_GRID)) * X_GRID
            for v in comp:
                pos[v] += shift
        # template sanity: the chain boxes themselves must not crowd each
        # other (a 4-leg chain returns to its first row; wide cards could
        # overlap there) -- infeasible -> the caller falls back
        for i, (px, py, pw) in enumerate(comp_placed):
            for (qx, qy, qw) in comp_placed[i + 1:]:
                if rect_gap(px, py, pw, card_h, qx, qy, qw, card_h) < cfg.min_gap:
                    raise InfeasibleLensChain(
                        "chain boxes crowd each other "
                        f"(gap < {cfg.min_gap}px)")
        placed.extend((pos[v], y[v], widths[v]) for v in comp)
        next_row = max(y[v] for v in comp) + row_pitch
    constructed = {}
    for (A, B), d in pair_dir.items():
        constructed.update(lens_arcs(A, B, d, pos, y, widths, card_h))
    # non-lens links are constructed too (facing standard edge-midpoint
    # anchors, one segment): the whole figure is by-construction, every
    # endpoint sits on the 16-anchor set and the delivery-layer snap /
    # arrival passes have nothing to move
    for (a, b) in plan.get("edges", []):
        if (a, b) in constructed:
            continue
        constructed[(a, b)] = link_line(a, b, pos, y, widths, card_h)
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = max(cfg.margin, comp_left if comp_left is not None else 0)
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2.0) / 2.0) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18
    meta = {"placement": "lens-chain",
            "lens": {"pairs": [[A, B, d] for (A, B), d in pair_dir.items()],
                     "gap": LENS_GAP, "k": LENS_K, "link_gap": LINK_GAP}}
    return pos, y, meta, constructed


def regularity(pos, y, nodes, deg0):
    """Certificate-grade regularity proxies on placed centers (pre-shift).

    Returns (cv, snap_rate, pitch_ok) with the metrics.py formulas
    (nearest-neighbor center-distance CV, 24px column snap rate,
    uniform row pitch over the non-parked nodes).
    """
    core = [v for v in nodes if v not in deg0]
    nn = []
    for a in core:
        dists = [math.dist((pos[a], y[a]), (pos[b], y[b]))
                 for b in core if b != a]
        if dists:
            nn.append(min(dists))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((dd - mean_nn) ** 2 for dd in nn) / len(nn)) / mean_nn) \
        if nn and mean_nn else 0.0
    snap = (sum(1 for v in core if pos[v] % X_GRID == 0) / len(core)) if core else 1.0
    rows = sorted({y[v] for v in core})
    pitch_ok = len({b - a for a, b in zip(rows, rows[1:])}) <= 1
    return cv, snap, pitch_ok
