# -*- coding: utf-8 -*-
"""Spine-wing (central spine + midline wings) placement (2026-11-06 jacky's
final call, B-limited edition, ref-scrubbed).

> jacky hand-laid the classic-cld-growth-and-burden diagram: the central
> spine adopters (top) / rate (bottom) sits strictly vertical on the canvas
> centerline; left wings word/potential and the right cluster crowding sit
> on the same horizontal midline (y exactly equal); quickfix upper-right /
> sideeffect lower-right are near-mirrored (x differs by 6px); fundamental
> sits lower-right inside, on the same row as rate. The second form of
> "topology should decide the layout" — a hub-pair spine + a horizontal
> wing band + mirrored clusters beyond the wings.

Trigger detection (deterministic topological metrics, written into the
docs/layout-modes.md priority chain; this module is the source of truth):
  - **Spine**: enumerate directed edges and take the pair with the most
    common neighbors of the endpoints as the hub pair (ties: more
    declared-loop co-occurrences -> smaller canonical (u,v)). The
    "rate->adopters" diffusion hub pair of a classic CLD wins naturally
    (measured 3 common neighbors in classic-cld; at most 2 in the rest of
    the corpus).
  - **Wings**: the common neighbors of the hub pair — each forms a 3-ring
    with the hub pair (left wings word in R1 / potential in B1, right wing
    crowding in B2), pressed onto the midline horizontal band.
  - **Trigger conditions (all must hold):
    (1) 3 <= |wings| <= 4 (the midline wing band needs >= 3 slots to be a
        "band"; > 4 overloads the hub pair);
    (2) 1 <= |rest| <= 6 AND all adjacencies of rest are within
        spine∪wings∪rest (secondary clusters hang only on wings/hub —
        double-axis symmetry constructibility; limits-to-growth has an
        isomorphic spine but rest=0, a pure growth core, no trigger);
    (3) spine length ratio = |spine| / n <= 0.5 (the hub is a compact
        node pair; long-chain shapes belong to the column-chain criteria);
    (4) rest is pairable: sorted by "restricted neighborhood key
        (adjacency set against wings∪spine) -> canonical form", then
        paired two by two with at most 1 leftover (mirror
        constructibility — quickfix/sideeffect pair up, fundamental is
        the leftover inside).
  - Corpus hits (measured on a full 19-diagram sweep): only
    classic-cld-growth-and-burden. Pure-ring family (arms-race etc.,
    maxCN<=1), the three bowtie-vertex diagrams (maxCN=1), the two
    bowtie-pair diagrams (maxCN=2), and the column family (maxCN<=2) all
    miss — see the card evidence list.

Placement (place_spine_wing, constructed constraints — cross-checked
against the sample's relative geometry, not global objective-function
terms):
  - Spine: the hub pair is strictly vertical along layout axis x=0, edge
    head (adopters) on top at y=-Hs and tail (rate) below at y=+Hs, with
    Hs = 2*(card_h+GAP) (=160 @card_h 44, matching the sample's spine
    half-distance 160);
  - Midline wings: all wings sit at y=0 on the midline. The rest
    cluster's anchor wing (the one with the most adjacencies to rest;
    crowding in the sample) takes the nearest right slot; the other wings
    are sorted by (loop kind R<B<other -> canonical form) and placed
    left, inside-out (sample: word inside / potential outside);
  - Rest mirror pairs: the first of each pair goes to the upper wing row
    y=-(card_h+GAP), the second to the lower wing row y=+(card_h+GAP)
    (=±80, idealized from the sample's ±82), stacked in one column at
    whole pitches right of the anchor wing; a leftover goes lower-right
    inside at y=+2*(card_h+GAP) (=+160, on rate's row; sample
    fundamental y=532 vs rate 534, the same row band);
  - All coordinates are even (2px grid); uniform translation to center at
    the delivery layer is handled by layout_auto.

Routing (constructed-constraint injection, not via the candidate pool):
  - The spine edge (tail->head) is constructed as a vertical straight
    line (bottom-edge midpoint of the top card -> top-edge midpoint of
    the bottom card);
  - All other edges go through the same Router candidate pool (straight
    and arc lines as equals); line styles inside the symmetric band are
    pressed toward straight lines by the Router tier costs (vg+120/
    poly+40) — cross-checked against the all-straight sample;
  - Inter-loop pairs (crowding<->quickfix, crowding<->fundamental) are
    separated by the Router inter-loop corridor mechanism (>= 4px gate).

Trial gate: reuses layout_auto._constructed_gates (box press / clearance /
anchor smoothness / card gap / inter-loop separation / crossings <= 2); any
failure silently falls back to the existing pattern chain (negative cases
byte-for-byte unchanged).
"""
import math

from . import columnlayout
from .routing import border_point

SYM_GAP = 36              # breathing-room target clearance (same tier as bowtie/symmetric)
MAX_SPINE_WING_N = 12     # trigger upper bound: small graphs
MIN_WINGS, MAX_WINGS = 3, 4
MAX_REST = 6


class InfeasibleSpineWing(Exception):
    pass


def _adjacency(edges):
    adj = {v: set() for a, b in edges for v in (a, b)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _canon(seq):
    return columnlayout._canon(seq)


def detect_spine_wing(graph, why=None):
    """Spine-wing detection. Returns a plan dict or None.

    plan = {"spine_tail", "spine_head", "wings": {"left": [...], "anchor": w},
            "rest_pairs": [[up, down], ...], "rest_single": [v] or [],
            "deg0": [isolated nodes]}

    why: optional dict — receives a deterministic one-line reason for the
    outcome (mode decision trace, certificate mode_decision_trace field).
    """
    nodes = list(graph.node_ids())
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if len(core) < 6 or len(core) > MAX_SPINE_WING_N:
        if why is not None:
            why["reason"] = (f"core n={len(core)} "
                             f"(need 6..{MAX_SPINE_WING_N})")
        return None

    # Spine candidates: the directed edge whose endpoints have the most common neighbors (deterministic tie-break chain)
    loop_sets = []
    for lp in graph.loops:
        loop_sets.append((getattr(lp, "kind", None), set(lp.nodes)))
    best = None
    for e in sorted(set(edges)):
        u, v = e
        cn = adj[u] & adj[v]
        if not (MIN_WINGS <= len(cn) <= MAX_WINGS):
            continue
        co_loops = sum(1 for _k, s in loop_sets if {u, v} <= s)
        key = (-len(cn), -co_loops, _canon((u, v)))
        if best is None or key < best[0]:
            best = (key, u, v, cn)
    if best is None:
        if why is not None:
            why["reason"] = ("no hub-pair candidate: no directed edge whose "
                             f"endpoints share {MIN_WINGS}..{MAX_WINGS} "
                             "common neighbors")
        return None
    _key, u, v, wings_set = best
    wings = sorted(wings_set)
    rest = sorted(set(core) - {u, v} - wings_set)
    # (1) wing band + (2) secondary clusters (a pure growth core with empty rest does not trigger — limits-to-growth)
    if not (1 <= len(rest) <= MAX_REST):
        if why is not None:
            why["reason"] = (f"rest cluster n={len(rest)} "
                             f"(need 1..{MAX_REST}; 0 = pure growth core, "
                             "e.g. limits-to-growth — no burden side)")
        return None
    # (3) spine length ratio: hub-pair nodes / core nodes <= 0.5 — a compact hub pair
    #     (long-chain shapes go to column-chain; 2-node hub pairs measured 0.22-0.33 corpus-wide)
    if len({u, v}) / max(1, len(core)) > 0.5:
        if why is not None:
            why["reason"] = (f"spine length ratio "
                             f"{len({u, v}) / max(1, len(core)):.2f} > 0.5 "
                             "(long-chain shapes go to column-chain)")
        return None
    # (2)' double-axis constructibility: rest hangs only on spine∪wings∪rest (no outsiders)
    allowed = {u, v} | wings_set | set(rest)
    if not all(adj[r] <= allowed for r in rest):
        if why is not None:
            why["reason"] = ("rest adjacency reaches outside "
                             "spine∪wings∪rest (double-axis "
                             "constructibility fails)")
        return None
    # (4) rest mirror constructibility: first pair rest nodes sharing a declared loop
    #     (sample quickfix/sideeffect both in R2 become a mirror pair, while
    #     fundamental shares a loop only with the anchor wing -> leftover inside);
    #     the rest pair by "restricted neighborhood key (against wings∪spine) -> canonical form", leftovers <= 1.
    def _restrict_key(r):
        return (tuple(sorted(adj[r] & (wings_set | {u, v}))),
                _canon((r,)))
    shared_loop = {}
    for i, r1 in enumerate(rest):
        for r2 in rest[i + 1:]:
            sl = [set(lp.nodes) for lp in graph.loops
                  if r1 in set(lp.nodes) and r2 in set(lp.nodes)]
            if sl:
                shared_loop[(r1, r2)] = tuple(sorted(
                    s for s in sl for x in (r1, r2) if x in s))
    pairs, used = [], set()
    for (r1, r2) in sorted(shared_loop,
                           key=lambda p: (_canon(p),)):
        if r1 in used or r2 in used:
            continue
        pairs.append((r1, r2))
        used |= {r1, r2}
    rest_left = sorted((r for r in rest if r not in used),
                       key=_restrict_key)
    for i in range(0, len(rest_left) - 1, 2):
        pairs.append((rest_left[i], rest_left[i + 1]))
        used |= {rest_left[i], rest_left[i + 1]}
    single = sorted((r for r in rest if r not in used), key=_restrict_key)
    if len(pairs) > 3 or len(single) > 1:
        if why is not None:
            why["reason"] = (f"rest mirror pairing infeasible: "
                             f"pairs={len(pairs)} (max 3), "
                             f"leftovers={len(single)} (max 1)")
        return None

    # Wing assignment: the rest cluster's anchor wing (most adjacencies to rest; ties -> smaller canon) -> right side
    def _canon1(w):
        return _canon((w,))
    anchor = sorted(wings, key=lambda w: (-len(adj[w] & set(rest)),
                                          _canon1(w)))[0]
    left_wings = [w for w in wings if w != anchor]

    def _wing_kind(w):
        kind_rank = {"R": 0, "B": 1}
        k = 2
        for lp in graph.loops:
            s = set(lp.nodes)
            if w in s and {u, v} <= s:
                kind = getattr(lp, "kind", None)
                if kind is not None:
                    k = kind_rank.get(kind, 2)
                break
        return k
    left_wings.sort(key=lambda w: (_wing_kind(w), _canon1(w)))
    # Pair first goes to the upper wing, second to the lower; a leftover goes lower-inside (sample fundamental)
    rest_pairs = [[p[0], p[1]] for p in pairs]
    if why is not None:
        why["reason"] = (f"hub pair {u}->{v} with W={len(wings_set)} common "
                         f"neighbors, rest n={len(rest)} mirror-pairable "
                         f"({len(pairs)} pairs / {len(single)} leftover)")
    return {"spine_tail": u, "spine_head": v,
            "wings_left": left_wings, "wing_anchor": anchor,
            "rest_pairs": rest_pairs, "rest_single": single,
            "deg0": deg0}


def place_spine_wing(plan, widths, card_h, cfg, edges):
    """Spine-wing constructed placement -> ({v: x}, {v: y}, meta, constructed_routes).

    Constructed constraints (relative geometry cross-checked against jacky's
    hand-laid classic-cld sample; see the module docstring).
    """
    u, v = plan["spine_tail"], plan["spine_head"]
    GAP = SYM_GAP
    row = card_h + GAP                        # wing row pitch (=80 @card_h 44)
    Hs = 2 * row                              # spine half-distance (=160, sample 160)

    def _r2(x):
        return int(round(x / 2) * 2)

    pos, y = {}, {}
    pos[v], y[v] = 0, -Hs                     # head on top (sample adopters)
    pos[u], y[u] = 0, Hs                      # tail at the bottom (sample rate)

    # Right-side anchor wing (sample crowding x=+134 ~= half spine width + half wing width + 36)
    anchor = plan["wing_anchor"]
    x_anchor = (widths[u] + widths[anchor]) / 2 + GAP
    pos[anchor], y[anchor] = _r2(x_anchor), 0

    # Left wings: inside-out (sample: word inside / potential outside)
    prev_half = widths[u] / 2
    cur = -(prev_half + GAP)
    for w in plan["wings_left"]:
        xw = cur - widths[w] / 2
        pos[w], y[w] = _r2(xw), 0
        cur = xw - widths[w] / 2 - GAP

    # Rest mirror pairs: whole-pitch stack right of the anchor wing at ±row (sample
    # y=±82~=±row; x near-mirrored, idealized to an exact column, 0px deviation)
    pair_col_x = x_anchor + widths[anchor] / 2 + GAP
    mirror_pairs = []
    for up, down in plan["rest_pairs"]:
        pair_x = pair_col_x + widths[up] / 2      # column set by the first member's width
        pos[up], y[up] = _r2(pair_x), -row
        pos[down], y[down] = _r2(pair_x), row
        mirror_pairs.append([up, down])
    # Leftover: lower-right inside (sample fundamental on rate's row y=+2row; x keeps
    # >= GAP clearance from the spine bottom card — sample x=594 vs rate right edge 460)
    if plan["rest_single"]:
        s = plan["rest_single"][0]
        xs = widths[u] / 2 + GAP + widths[s] / 2
        pos[s], y[s] = _r2(xs), 2 * row

    if plan["deg0"]:
        total = sum(widths[w] for w in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur0 = -total / 2
        for w in plan["deg0"]:
            pos[w] = int(round((cur0 + widths[w] / 2) / 2) * 2)
            y[w] = cfg.park_y
            cur0 += widths[w] + 18

    # Constructed routes: the spine edge as a vertical straight line (not via the candidate pool); other edges via the Router
    constructed = {}
    eset = set(edges)
    for e in ((u, v), (v, u)):
        if e in eset:
            a, b = e
            na = (pos[a], y[a], widths[a], card_h)
            nb = (pos[b], y[b], widths[b], card_h)
            pa = border_point(na[0], na[1], na[2] / 2, na[3] / 2,
                              nb[0] - na[0], nb[1] - na[1])
            pb = border_point(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                              na[0] - nb[0], na[1] - nb[1])
            constructed[e] = {"kind": "line", "points": [pa, pb]}
            break

    meta = {
        "placement": "spine-wing",
        "spine_wing": {
            "axis_x": 0,
            "axis_y": 0,
            "spine": [v, u],
            "wings_left": list(plan["wings_left"]),
            "wing_anchor": anchor,
            "wings": [w for w in plan["wings_left"]] + [anchor],
            "mirror_pairs": mirror_pairs,
            "rest_single": list(plan["rest_single"]),
            "row_pitch": row,
            "spine_half": Hs,
            "gap": GAP,
            "line_style_rule": "spine vertical straight + router lines/arcs",
        },
    }
    return pos, y, meta, constructed
