# -*- coding: utf-8 -*-
"""Anchor-seeded construction (anchors-as-prior candidate generation, S1
case B: same family, different graph).

The hit anchor's layout carries the shape prior (role grouping: endpoint
columns / mid band / wing columns; ring radius band; comb columns).  This
module transfers that shape onto the input graph DETERMINISTICALLY:

  1. node correspondence by Weisfeiler-Lehman color refinement (degree ->
     three sorted-neighborhood refinement rounds) -- pure topology, no
     geometry, no thresholds; colors pair up input nodes and anchor nodes
     deterministically (sorted-id order within a color class, equal counts
     only; leftover nodes stay unmatched);
  2. matched input nodes take their anchor partner's coordinates verbatim
     (the anchor's endpoint columns / bands / radius band ARE the prior);
  3. unmatched input nodes are placed at the barycenter of their already
     placed neighbors (three deterministic passes over sorted ids), or at
     the anchor bbox center when they have no placed neighbor;
  4. a final collision pass quantizes to the 2px delivery grid and walks
     sorted nodes to free cells (the delivered candidate still faces the
     same routing + hard gates as every other candidate -- this source
     carries zero scoring power, exactly like the template sources).

Deviation disclosure (proposal section 1.3 case B says "inject structural
regularity parameters into place_*"): v1 transfers the shape at the
coordinate level instead of editing the place_* construction cores --
injecting knobs into the template cores would touch behavior shared with
the frozen auto path, while the coordinate transplant is a NEW source with
zero effect on any existing construction.  The registered structural
regularities (benchmarks/manual/README.md) are what the anchor coordinates
carry; the transplant preserves them through the matched-role mapping.
"""
from typing import Dict, Tuple

WL_ROUNDS = 3
DELIVERY_GRID_PX = 2


def _adjacency(edges):
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _wl_colors(adj, rounds=WL_ROUNDS):
    """Deterministic WL color refinement (ints, stable across runs)."""
    ids = sorted(adj)
    color = {v: len(adj[v]) for v in ids}
    for _ in range(rounds):
        sig = {v: (color[v], tuple(sorted(color[n] for n in adj[v])))
               for v in ids}
        uniq = sorted(set(sig.values()))
        idx = {s: i for i, s in enumerate(uniq)}
        color = {v: idx[sig[v]] for v in ids}
    return color


def _match_nodes(input_adj, anchor_adj):
    """WL-color pairing: {input_id: anchor_id} for equal-count color
    classes, deterministic (sorted ids on both sides)."""
    ci = _wl_colors(input_adj)
    ca = _wl_colors(anchor_adj)
    by_i, by_a = {}, {}
    for v in sorted(ci):
        by_i.setdefault(ci[v], []).append(v)
    for v in sorted(ca):
        by_a.setdefault(ca[v], []).append(v)
    mapping = {}
    for c in sorted(set(by_i) & set(by_a)):
        ins, ans = by_i[c], by_a[c]
        if len(ins) != len(ans):
            continue          # ambiguous class: honest no-match, not a guess
        mapping.update(zip(sorted(ins), sorted(ans)))
    return mapping


def transplant(anchor_nodes: Dict[str, Tuple[int, int]],
               input_adj, anchor_adj) -> Dict[str, Tuple[int, int]]:
    """Shape-prior transfer: returns {input_id: (x, y)} delivery positions.

    ``anchor_nodes``: {anchor_node_id: (x, y)} from the hit anchor's stored
    layout.  ``input_adj`` / ``anchor_adj``: undirected adjacency dicts.
    """
    mapping = _match_nodes(input_adj, anchor_adj)

    xs = [p[0] for p in anchor_nodes.values()]
    ys = [p[1] for p in anchor_nodes.values()]
    cx = (min(xs) + max(xs)) // 2
    cy = (min(ys) + max(ys)) // 2

    pos: Dict[str, Tuple[int, int]] = {}
    for v in sorted(input_adj):
        a = mapping.get(v)
        if a is not None:
            x, y = anchor_nodes[a]
            pos[v] = (int(x), int(y))
        else:
            pos[v] = (int(cx), int(cy))
    # barycenter relaxation for unmatched nodes (deterministic order)
    for _ in range(3):
        for v in sorted(input_adj):
            if v in mapping:
                continue
            placed = [pos[n] for n in sorted(input_adj[v])
                      if n in pos and n != v]
            if placed:
                pos[v] = (int(round(sum(p[0] for p in placed)
                                 / len(placed))),
                          int(round(sum(p[1] for p in placed)
                                    / len(placed))))
    # collision pass: 2px grid, sorted walk to free cells
    occupied = {}
    for v in sorted(pos, key=lambda k: (pos[k][0], pos[k][1], k)):
        x, y = pos[v]
        x -= x % DELIVERY_GRID_PX
        y -= y % DELIVERY_GRID_PX
        while (x, y) in occupied:
            x += DELIVERY_GRID_PX
            y += DELIVERY_GRID_PX
        occupied[(x, y)] = v
        pos[v] = (x, y)
    return pos
