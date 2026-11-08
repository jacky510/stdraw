# -*- coding: utf-8 -*-
"""Bowtie-vertex (two rings sharing a single node) symmetric placement
(2026-11-06 jacky aesthetics v3, ref-scrubbed).

> jacky hand-laid the wage-price-spiral diagram: the shared node sits at the
> exact center of the figure, the remaining nodes of the two rings occupy
> four symmetric positions, and the whole figure is axis-symmetric up/down
> and left/right — "topology should decide the layout".

Trigger detection (deterministic hard-coded rules; mutually exclusive with
symlayout's shared-**edge** bowtie topology):
  - Enumerate undirected simple rings (length >= 3, deduplicated by
    canonical form; declared loops are **not** used — the declaration table
    mixes in 2-node pseudo-rings and misses derived rings); exactly **2**
    rings, the two ring node sets share exactly **1** node, and the union of
    the two rings = all non-isolated nodes (no trigger when dangling nodes
    exist — conservative fallback).
  - Corpus hits: {eroding-goals, shifting-the-burden, wage-price-spiral}
    (a directed-isomorphism family). No false positives: 08/10/17 also have
    exactly 2 simple rings but share 2 nodes (shared-edge type, outside the
    decision domain of symlayout's criteria, handled by existing patterns).

Placement (place_bowtie_vertex, cross-checked against the relative geometry
of jacky's hand-laid sample):
  - The shared node sits at the canvas center (layout-layer axis x=0, y=0;
    the delivery layer translates everything uniformly to center);
  - Each ring occupies one half-plane (first ring above / second ring below;
    ring order broken deterministically by kind R<B<other -> canonical
    order); the remaining nodes of each ring sit on a horizontal row in the
    same half-plane at mirrored left/right positions (triangle = +-D at
    equal height, outer edge a horizontal straight line — matching the
    sample's "top edge nearly horizontal");
  - Left/right assignment = walk the ring from the shared node in the
    "directed-edge-following" direction; the successor goes left, the next
    one right (measured on the sample: wages left / cost right,
    real_income left / demand right, same rule for both rings);
  - Both rings share D and H -> the whole figure is strictly mirrored
    up/down (an idealization of the sample's vertical mirror axis x~=293,
    deviation 0px <= the 2px acceptance gate).

Routing (constructively injected by place_bowtie_vertex, not via the
candidate pool):
  - All straight lines (line-style consistency hard rule: all 6 edges are
    lines, no mixing of straight/arc/bend);
  - Outer edges (ring edges that do not pass through the shared node) =
    horizontal straight lines; the 4 spokes = straight lines;
  - The two spoke anchors on the same side of the shared node spread
    symmetrically +-SPREAD about the edge midpoint (multiple outgoing lines
    of one node must not stack at a single point — 2026-11-06
    connection-point convention hard rule 3).

Trial gate: reuses layout_auto._constructed_gates (box press / clearance /
anchor smoothness / card gap / inter-loop separation / crossings <= 2); any
failure silently falls back to the existing pattern chain (negative cases
byte-for-byte unchanged).
"""
import math

from . import columnlayout
from .routing import border_point, seg_cross

SYM_GAP = 36              # breathing-room target clearance (same tier as SYM_GAP/SIDE_GAP)
MAX_BOWTIE_N = 12         # trigger upper bound: small graphs


class InfeasibleBowtieVertex(Exception):
    pass


def _adjacency(edges):
    adj = {v: set() for a, b in edges for v in (a, b)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _canon(seq):
    best = None
    for s in (list(seq), list(seq)[::-1]):
        for i in range(len(s)):
            rot = s[i:] + s[:i]
            if best is None or rot < best:
                best = rot
    return tuple(best)


def detect_bowtie_vertex(graph):
    """Bowtie-vertex detection. Returns a plan dict or None.

    plan = {"shared": shared node, "loops": [(kind, [c1..ck]), ...] (upper
            ring first), "deg0": [isolated nodes]}
    """
    nodes = list(graph.node_ids())
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if len(core) < 5 or len(core) > MAX_BOWTIE_N:
        return None
    cycles = columnlayout._enumerate_cycles(core, adj)
    if len(cycles) != 2:
        return None
    s0, s1 = set(cycles[0]), set(cycles[1])
    shared_set = s0 & s1
    if len(shared_set) != 1:
        return None
    if s0 | s1 != set(core):
        return None            # dangling nodes outside the rings -> conservatively no trigger
    shared = sorted(shared_set)[0]
    eset = set(edges)

    def _oriented(seq):
        """Ring order -> orientation starting at shared with more directed-edge follows; ties take the smaller canonical form."""
        n = len(seq)
        i = seq.index(shared)

        def follows(o):
            return sum(1 for k in range(n)
                       if (o[k], o[(k + 1) % n]) in eset)
        o1 = [seq[(i + k) % n] for k in range(n)]
        o2 = [seq[(i - k) % n] for k in range(n)]
        c1, c2 = follows(o1), follows(o2)
        if c1 != c2:
            return o1 if c1 > c2 else o2
        return o1 if _canon(o1) <= _canon(o2) else o2

    kind_rank = {"R": 0, "B": 1}
    entries = []
    for seq in cycles:
        kind = None
        for lp in graph.loops:
            if set(lp.nodes) == set(seq):
                kind = getattr(lp, "kind", None)
                break
        entries.append((kind_rank.get(kind, 2), _canon(seq), kind,
                        _oriented(seq)[1:]))
    entries.sort(key=lambda t: (t[0], t[1]))
    loops = [(kind, rest) for _r, _c, kind, rest in entries]
    return {"shared": shared, "loops": loops, "deg0": deg0}


def place_bowtie_vertex(plan, widths, card_h, cfg, edges):
    """Bowtie-vertex symmetric placement -> ({v: x}, {v: y}, meta, constructed_routes).

    constructed_routes: {(a,b): route dict} — all-straight construction
    (horizontal outer edges + direct spokes, shared-side anchors spread
    symmetrically at +-SPREAD), constructively injected.
    """
    shared = plan["shared"]
    loops = plan["loops"]
    ws = widths[shared]
    # D: distance of the left/right vertices from the axis — sum of the two cards' half-widths + clearance (max over rings)
    D = max((widths[seq[0]] + widths[seq[-1]]) / 2 + SYM_GAP
            for _k, seq in loops)
    D = int(round(D / 2) * 2)
    # H: half-distance between ring row and shared row — breathing clearance
    # >= SYM_GAP and >= D (near-square; sample radius ~196 / x ~135-150 / y ~123-145)
    H = max(2 * card_h + SYM_GAP, D)
    H = int(round(H / 2) * 2)

    pos = {shared: 0}
    y = {shared: 0}
    for idx, (_kind, seq) in enumerate(loops):
        s = -1 if idx == 0 else 1          # first ring upper half-plane, second lower
        k = len(seq)
        for j, v in enumerate(seq):
            if k > 1:
                x = -D + (2.0 * D) * j / (k - 1)
            else:
                x = 0.0
            pos[v] = int(round(x / 2) * 2)
            y[v] = s * H

    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = -total / 2
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    def _np(v):
        return (pos[v], y[v], widths[v], card_h)

    constructed = {}
    eset = set(edges)
    # Shared-node spokes: anchor = the shared card's side midpoint +-SPREAD (symmetric spread for the two rings; one
    # node's multiple outgoing lines never stack — 2026-11-06 connection-point convention hard rule 3). Measured on
    # the bowtie family: all 4 spokes are inter-loop pairs (bidirectional) — one line per pair would make both
    # directions coincide point-for-point and necessarily FAIL the inter-loop separation gate. Inter-loop corridor:
    # one parallel line per direction, anchors offset ±PAIR_T along the box edge tangent (U line = leftward travel,
    # L line = reverse; same rule for both rings -> mirror-consistent), total side spread <= hh-3 (clamped inside
    PAIR_T = 12
    spoke_dirs = {}      # endv -> [(a,b), ...] directed edges on that spoke
    for _kind, seq in loops:
        for endv in (seq[0], seq[-1]):
            spoke_dirs[endv] = [e for e in ((shared, endv), (endv, shared))
                                if e in eset]
    side_mutual = {side: any(len(spoke_dirs.get(v, [])) == 2
                             for _k, seq in loops for v in (seq[0], seq[-1])
                             if (1 if pos[v] > 0 else -1) == side)
                   for side in (-1, 1)}
    spoke_anchor = {}
    for endv, dirs in spoke_dirs.items():
        side = -1 if pos[endv] < 0 else 1
        s = -1 if any(endv in seq for _k, seq in loops[:1]) else 1
        spread = 7 if side_mutual[side] else 14
        spoke_anchor[endv] = [side * ws / 2, s * spread]
    # ref-scrubbed: on a side hosting BOTH rings' mutual pairs, the per-ring
    # slot pairs interleave when spread < PAIR_T (upper pair = {-spread-12,
    # -spread+12}, lower pair = {spread-12, spread+12}; for spread 7 the
    # merged slot order is -19, -5, +5, +19 while the per-ring assignment
    # put the upper ring's incoming line at +5 BELOW the lower ring's
    # outgoing line at -5 -- an incoming line landing below an outgoing line
    # that travels into the same half-plane crosses it mid-air at the shared
    # border; measured on shifting-the-burden problem box, visual_crossings
    # 1 -> 0 after this fix). Assign the merged slot offsets sorted ascending
    # in (upper-ring U, upper-ring L, lower-ring U, lower-ring L) order; for
    # spread >= PAIR_T sides the sorted merge reproduces the per-ring
    # assignment byte-for-byte (the pairs do not interleave), so non-mutual
    # bowtie figures keep their delivered geometry (eroding-goals /
    # wage-price-spiral sweep-verified byte-identical).
    pair_slots = {}
    _pside_endvs = {}
    for endv, dirs in spoke_dirs.items():
        if len(dirs) == 2:
            _side = -1 if pos[endv] < 0 else 1
            _pside_endvs.setdefault(_side, []).append(endv)
    for _side, _endvs in _pside_endvs.items():
        if len(_endvs) != 2:
            continue
        _spread = 7 if side_mutual[_side] else 14
        _offs = sorted([-_spread - PAIR_T, -_spread + PAIR_T,
                        _spread - PAIR_T, _spread + PAIR_T])
        _up = (_endvs[0] if any(_endvs[0] in seq for _k, seq in loops[:1])
               else _endvs[1])
        _low = _endvs[1] if _up == _endvs[0] else _endvs[0]
        pair_slots[_up] = (_offs[0], _offs[1])
        pair_slots[_low] = (_offs[2], _offs[3])
    hh3 = card_h / 2 - 3
    for endv, dirs in spoke_dirs.items():
        if not dirs:
            continue
        nb = _np(endv)
        base_sa = spoke_anchor[endv]
        base_cb = border_point(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                               base_sa[0] - nb[0], base_sa[1] - nb[1])
        on_x = abs(abs(base_cb[0] - nb[0]) - nb[2] / 2) <= \
            abs(abs(base_cb[1] - nb[1]) - nb[3] / 2)
        if len(dirs) == 2:
            # Inter-loop corridor: U line (-t) = leftward travel direction; L line (+t) = reverse. Card-side anchor =
            # the corridor center anchor truly spread ±PAIR_T along the owning box edge tangent (parallel separation
            # >= 4px gate); when the card end is on a horizontal edge, pair "upper->near / lower->far" — the lower
            # line starts lower and, if steeper, would flip above the upper line (crossing observed in practice);
            # far-end pairing keeps the gap monotone; same rule for both rings -> up/down and left/right mirrored.
            leftward = dirs[0] if pos[dirs[0][0]] > pos[dirs[0][1]] else dirs[1]
            backward = dirs[1] if leftward == dirs[0] else dirs[0]
            if endv in pair_slots:
                _ou, _ol = pair_slots[endv]
            else:
                _ou, _ol = base_sa[1] - PAIR_T, base_sa[1] + PAIR_T
            sa_u = [base_sa[0], max(-hh3, min(hh3, _ou))]
            sa_l = [base_sa[0], max(-hh3, min(hh3, _ol))]
            on_x = abs(abs(base_cb[0] - nb[0]) - nb[2] / 2) <= \
                abs(abs(base_cb[1] - nb[1]) - nb[3] / 2)
            if on_x:
                half = nb[3] / 2 - 3
                y_l = max(nb[1] - half, min(nb[1] + half, base_cb[1] - PAIR_T))
                y_h = max(nb[1] - half, min(nb[1] + half, base_cb[1] + PAIR_T))
                cb_u = [base_cb[0], y_l]      # shifted ±t: always parallel, never crossing
                cb_l = [base_cb[0], y_h]
            else:
                half = nb[2] / 2 - 3
                x_a = max(nb[0] - half, min(nb[0] + half,
                                            base_cb[0] - PAIR_T))
                x_b = max(nb[0] - half, min(nb[0] + half,
                                            base_cb[0] + PAIR_T))
                # Anti-crossing pairing: upper/lower lines must keep their vertical order throughout — upper->near in
                # the upper half-plane, upper->far in the lower (uniform deterministic "swap-if-intersecting" rule)
                cb_a, cb_b = [x_a, base_cb[1]], [x_b, base_cb[1]]
                if seg_cross(sa_u, cb_a, sa_l, cb_b):
                    cb_a, cb_b = cb_b, cb_a
                cb_u, cb_l = cb_a, cb_b
            constructed[leftward] = {
                "kind": "line",
                "points": ([sa_u, cb_u] if leftward[0] == shared
                           else [cb_u, sa_u])}
            constructed[backward] = {
                "kind": "line",
                "points": ([sa_l, cb_l] if backward[0] == shared
                           else [cb_l, sa_l])}
        else:
            e = dirs[0]
            a, b = e
            pa = base_sa if a == shared else base_cb
            pb = base_cb if a == shared else base_sa
            constructed[e] = {"kind": "line", "points": [pa, pb]}
    # Outer edges (ring edges not passing through the shared node): horizontal straight line (k=2) or same-chord straight line (k>2)
    for _kind, seq in loops:
        for j in range(len(seq) - 1):
            a, b = seq[j], seq[j + 1]
            for e in ((a, b), (b, a)):
                if e not in eset:
                    continue
                na, nb = _np(a), _np(b)
                pa = border_point(na[0], na[1], na[2] / 2, na[3] / 2,
                                  nb[0] - na[0], nb[1] - na[1])
                pb = border_point(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                                  na[0] - nb[0], na[1] - nb[1])
                constructed[e] = {"kind": "line", "points": [pa, pb]}
                break
    mirror_pairs = []
    if len(loops) == 2 and len(loops[0][1]) == len(loops[1][1]):
        mirror_pairs = [[loops[0][1][j], loops[1][1][j]]
                        for j in range(len(loops[0][1]))]
    meta = {
        "placement": "bowtie-vertex",
        "symmetry": {
            "axis": "vertical",
            "axis_x": 0,
            "axis_y": 0,
            "shared_node": shared,
            "loops": [[shared] + list(seq) for _k, seq in loops],
            "mirror_pairs": mirror_pairs,
            "gap": SYM_GAP,
            "line_style_rule": "all-straight (horizontal outer edges + spokes)",
        },
    }
    return pos, y, meta, constructed
