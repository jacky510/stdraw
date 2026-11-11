# -*- coding: utf-8 -*-
"""Loop-dominated ring placement (2026-11-05 product decision, ref-scrubbed).

> "When a balancing loop forms, a ring helps people understand the cycle
> better, and the figure is more beautiful too."

Trigger detection (graph-theoretic metrics, not feelings; fully
deterministic):
  1. Small graph: 3 <= n <= 12 (n includes isolated nodes);
  2. Main ring: a simple loop covering >= n-2 nodes exists; or ring
     edges (non-bridge edges) make up >= 0.9 of undirected edges;
  3. Pure ring (single connected component, all degree 2): take that
     ring directly (reusing the WS2 cycle regular-polygon slot
     construction; the construction itself unchanged).

Main-ring selection: candidates = declared loops (DSL loops that form
a simple loop, keeping the declared order — R/B polarity badges stay
readable around the ring) ∪ graph-theoretically enumerated simple
loops (canonical-form dedup). Among candidates covering >= n-2,
selection is deterministic by "zero chord crossings first -> most
coverage -> canonical-form lexicographic order".

Placement (place_ring):
  - Main-ring nodes go into regular-polygon slots in ring order
    (same-source construction as placement._place_cycle: evenly
    divided angles i·2π/k − π/2, quantized to the 2px grid; radius
    adapts to adjacent card-width needs, upper bound constrained by
    the check8 1280x800 rendering-ratio tier);
  - Residual nodes (chord tails / external variables): toward the
    centroid direction of ring neighbors, a fixed fractional in-ring
    candidate order; on card-gap conflicts fall back to the near side
    outside the ring; isolated nodes park in the top parking strip;
  - Radius need above the upper bound -> InfeasibleRing (the caller
    falls back to the existing layered path, byte-for-byte
    unchanged).

Routing/certificate: delegated to the existing Router and
certificate_auto; the ring-mode metric criteria (equal-spacing CV on
the ring + regular-polygon template fitting error, replacing row
alignment / column snapping) switch inside metrics/check on
meta.placement == "ring-cycle".
"""
import math
from collections import defaultdict

MAX_RING_N = 12            # trigger upper bound: small graphs
COVER_SLACK = 2            # main ring covers >= n - 2
CYCLE_EDGE_RATIO = 0.90    # ring-edge (non-bridge) ratio threshold (OR branch)
DFS_STEP_CAP = 2_000_000   # simple-loop enumeration step cap (deterministic: operation-count criterion)
RADIUS_MIN = 150
RADIUS_MAX = 320           # radius upper bound for check8 rendering ratio >= 0.85 (2r+card+edge geometry <= ~780px)
ADJ_GAP = 60               # center-distance margin between adjacent ring cards (>= 16 gate + routing channel)


class InfeasibleRing(Exception):
    """Ring slot infeasible (radius need above the upper bound) — the caller falls back to the existing layered path."""


def _adjacency(edges):
    adj = defaultdict(set)
    pairs = set()
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
        pairs.add((a, b) if a < b else (b, a))
    return adj, pairs


def _canonical(seq):
    """Canonical form of a ring sequence: lexicographically smallest over all rotations x both directions (for dedup/ordering)."""
    best = None
    for s in (list(seq), list(seq)[::-1]):
        for i in range(len(s)):
            rot = s[i:] + s[:i]
            if best is None or rot < best:
                best = rot
    return tuple(best)


def _seg_cross(p1, p2, p3, p4):
    """Whether two segments properly cross (endpoint touching / collinear overlap excluded; straight-line proxy convention)."""

    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(v) < 1e-9:
            return 0
        return 1 if v > 0 else -1

    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def _crossing_count(segments):
    """Count of proper pairwise crossings (segments: (p1, p2, endpoint_ids); shared endpoints skipped)."""
    n = len(segments)
    c = 0
    for i in range(n):
        for j in range(i + 1, n):
            a1, b1, e1 = segments[i]
            a2, b2, e2 = segments[j]
            if e1[0] in e2 or e1[1] in e2:
                continue
            if _seg_cross(a1, b1, a2, b2):
                c += 1
    return c


class _CapExceeded(Exception):
    pass


def _enumerate_cycles(nodes, adj):
    """Enumerate all simple loops (canonical-form dedup; step-cap protection — stop at the cap and use what was found)."""
    steps = [0]
    found = {}

    def dfs(start, v, path, seen):
        steps[0] += 1
        if steps[0] > DFS_STEP_CAP:
            raise _CapExceeded
        for w in sorted(adj[v]):
            if w == start and len(path) >= 3:
                can = _canonical(path)
                if can not in found:
                    found[can] = can
            elif w not in seen:
                seen.add(w)
                dfs(start, w, path + [w], seen)
                seen.remove(w)

    try:
        for s in sorted(nodes):
            dfs(s, s, [s], {s})
    except _CapExceeded:
        pass
    return [list(c) for c in found.values()]


def _declared_loop_cycles(graph, adj):
    """Declared loops that form simple loops. Returns [(loop_id, kind, declared loop order)]."""
    out = []
    for lp in graph.loops:
        seq = list(lp.nodes)
        if len(seq) < 3 or len(set(seq)) != len(seq):
            continue
        if not all(seq[(i + 1) % len(seq)] in adj[seq[i]] for i in range(len(seq))):
            continue
        out.append((lp.id, getattr(lp, "kind", None), seq))
    return out


def _is_pure_cycle(nodes, adj):
    if len(nodes) < 3 or any(len(adj[v]) != 2 for v in nodes):
        return False
    seen, stack = {min(nodes)}, [min(nodes)]
    while stack:
        x = stack.pop()
        for w in adj[x]:
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return len(seen) == len(nodes)


def _pure_cycle_order(nodes, adj):
    """Pure-ring order: smallest id as start, first step toward the smaller neighbor (deterministic)."""
    start = min(nodes)
    order = [start]
    prev, cur = None, start
    while True:
        nxts = sorted(w for w in adj[cur] if w != prev)
        if not nxts:
            return None
        step = nxts[0]
        if step == start:
            break
        order.append(step)
        prev, cur = cur, step
        if len(order) > len(nodes):
            return None
    return order if len(order) == len(nodes) else None


def _non_bridge_ratio(nodes, adj, pairs):
    """Ring-edge ratio = non-bridge edges / undirected edge count (a bridge = removing it increases the component count)."""
    def ncomp(adj2):
        seen, c = set(), 0
        for s in nodes:
            if s in seen:
                continue
            c += 1
            st = [s]
            seen.add(s)
            while st:
                x = st.pop()
                for y in adj2[x]:
                    if y not in seen:
                        seen.add(y)
                        st.append(y)
        return c

    base = ncomp(adj)
    nb = 0
    for e in sorted(pairs):
        adj2 = defaultdict(set)
        for v in nodes:
            for w in adj[v]:
                if ((v, w) if v < w else (w, v)) != e:
                    adj2[v].add(w)
                    adj2[w].add(v)
        if ncomp(adj2) == base:
            nb += 1
    return nb / len(pairs) if pairs else 0.0


def _chord_segments(ring, edges):
    """Unit-circle straight segments of in-ring chord edges (ring-ring non-ring edges) (crossing proxy)."""
    rset = set(ring)
    rpos = {v: (math.cos(2 * math.pi * i / len(ring) - math.pi / 2),
                math.sin(2 * math.pi * i / len(ring) - math.pi / 2))
            for i, v in enumerate(ring)}
    cyc_pairs = {(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))}
    cyc_pairs |= {(b, a) for a, b in cyc_pairs}
    segs, seen = [], set()
    for a, b in edges:
        if a not in rset or b not in rset:
            continue
        p = (a, b) if a < b else (b, a)
        if p in cyc_pairs or p in seen:
            continue
        seen.add(p)
        segs.append((rpos[a], rpos[b], (a, b)))
    return segs


def detect_ring(graph, why=None):
    """Trigger detection + main-ring selection. Returns a ring plan dict or
    None (no trigger).

    plan = {"ring": [ring order], "k": int, "declared_loop": id|None,
            "polarity": "R"|"B"|None, "trigger": "pure-cycle"|"cover"|"ratio",
            "residuals": [non-ring non-isolated nodes], "deg0": [isolated nodes],
            "chord_crossings": int}

    why: optional dict — receives a deterministic one-line reason for the
    outcome (mode decision trace, certificate mode_decision_trace field).
    """
    nodes = list(graph.node_ids())
    n = len(nodes)
    if n < 3 or n > MAX_RING_N:
        if why is not None:
            why["reason"] = (f"n={n} (need 3..{MAX_RING_N})")
        return None
    edges = [(e.a, e.b) for e in graph.edges]
    adj, pairs = _adjacency(edges)
    # _adjacency keys derive from edges only: isolated nodes (degree 0, in no
    # edge) would KeyError below. Detection runs on every auto-layout graph
    # (probe precedes the hit test), so adj must cover ALL nodes.
    for v in nodes:
        adj.setdefault(v, set())
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]

    if _is_pure_cycle(core, adj):
        seq = _pure_cycle_order(core, adj)
        if seq:
            if why is not None:
                why["reason"] = f"pure cycle, all degree-2, k=n={n}"
            return {"ring": seq, "k": len(seq), "declared_loop": None,
                    "polarity": None, "trigger": "pure-cycle",
                    "residuals": [], "deg0": deg0,
                    "chord_crossings": 0}

    cands = []                                        # [(ring order, loop_id, kind)]
    for lid, kind, seq in _declared_loop_cycles(graph, adj):
        cands.append((seq, lid, kind))
    for seq in _enumerate_cycles(core, adj):
        cands.append((seq, None, None))
    if not cands:
        if why is not None:
            why["reason"] = ("no simple loop (declared or enumerated) — "
                             "not loop-dominated")
        return None

    ratio = _non_bridge_ratio(nodes, adj, pairs)
    cover_ok = any(len(s) >= n - COVER_SLACK for s, _, _ in cands)
    if not (cover_ok or ratio >= CYCLE_EDGE_RATIO):
        if why is not None:
            why["reason"] = (f"not loop-dominated: main-ring coverage < "
                             f"n-{COVER_SLACK} and non-bridge edge ratio "
                             f"{ratio:.2f} < {CYCLE_EDGE_RATIO}")
        return None

    eligible = [(s, lid, pol) for s, lid, pol in cands
                if len(s) >= n - COVER_SLACK] or cands
    if not cover_ok:
        # v0.7.7 ratio-branch guard (K_{m,2} misfire): a high non-bridge
        # ratio whose best ring is only k=4 is the bilateral-comb signature
        # (two hubs + two sources forming a 4-cycle, everything else hanging
        # off it) — that family belongs to comb-bilateral placement, not
        # ring. Non-comb graphs keep the historical ratio behavior (e.g.
        # classic-cld: ratio trigger with k=4 is legitimate). Probe with the
        # comb detector to draw the line structurally, not by k alone.
        kmax = max(len(s) for s, _, _ in eligible)
        if kmax <= 4:
            from .comblayout import detect_comb
            if detect_comb(graph) is not None:
                if why is not None:
                    why["reason"] = ("ratio branch with best ring k<=4 and "
                                     "the bilateral-comb signature — that "
                                     "family belongs to comb-bilateral")
                return None
    best = None
    cand_rows = []                    # D3 observability probe (S2-1)
    for seq, lid, pol in eligible:
        cross = _crossing_count(_chord_segments(seq, edges))
        # Main ring = max-coverage ring (the truly dominant loop); same coverage: zero chord crossings first -> lexicographic
        key = (-len(seq), cross, _canonical(seq))
        cand_rows.append({"k": len(seq), "chord_crossings": cross,
                          "declared_loop": lid, "ring": list(seq)})
        if best is None or key < best[0]:
            best = (key, seq, lid, pol, cross)
    _, ring, lid, pol, cross = best
    residuals = [v for v in core if v not in set(ring)]
    if why is not None:
        for row in cand_rows:
            row["selected"] = (row["ring"] == list(ring))
        why["candidates"] = cand_rows
        why["reason"] = (f"loop-dominated (trigger="
                         f"{'cover' if cover_ok else 'ratio'}), main ring "
                         f"k={len(ring)}, chord crossings={cross}")
    return {"ring": list(ring), "k": len(ring), "declared_loop": lid,
            "polarity": pol, "trigger": "cover" if cover_ok else "ratio",
            "residuals": residuals, "deg0": deg0, "chord_crossings": cross}


def _ring_radius(k, ring_widths, n_residuals=0):
    """Regular k-gon radius: adjacent card center distance >= (w_u+w_v)/2 +
    ADJ_GAP; above the upper bound is infeasible.

    With n_residuals > 0 the radius is raised to make room inside the
    ring (+40px per residual node, within the upper bound).
    """
    need = 0.0
    for i in range(k):
        wu = ring_widths.get(i, 96)
        wv = ring_widths.get((i + 1) % k, 96)
        need = max(need, (wu + wv) / 2 + ADJ_GAP)
    r = need / (2 * math.sin(math.pi / k))
    r = max(r, RADIUS_MIN + 40 * n_residuals)
    if r > RADIUS_MAX:
        raise InfeasibleRing(f"radius requirement {r:.0f}px exceeds the upper bound {RADIUS_MAX}")
    return max(RADIUS_MIN, int(math.ceil(r / 2) * 2))


# Deterministic residual candidate family: in-ring fractions x angle offsets (fixed order: near-center first, zero offset first)
_INNER_FS = (0.42, 0.34, 0.50, 0.26, 0.58, 0.18, 0.66)
_ANGLE_DS = (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0, 120.0, -120.0)


def place_ring(plan, widths, card_h, cfg, adj, edges):
    """Ring placement -> ({v: x}, {v: y}, meta). All-integer 2px grid,
    deterministic.

    Residual assignment: candidates = in-ring fraction x angle offset
    (ring-neighbor centroid at 0°); each residual (id order) takes the
    collision-free candidate with "fewest new straight-proxy crossings
    -> smallest angle offset -> fraction closest to 0.42"; if all
    in-ring candidates collide, try the near side outside the ring;
    still none -> InfeasibleRing. edges: used for straight-proxy
    crossing scoring (ring edges + chords + spokes of already-placed
    residuals).
    """
    ring, k = plan["ring"], plan["k"]
    ring_widths = {i: widths.get(v, 96) for i, v in enumerate(ring)}
    r = _ring_radius(k, ring_widths, len(plan["residuals"]))
    cx = int(r // 2) * 2
    cy = int((r + card_h // 2 + 40) // 2) * 2
    pos, y, angles = {}, {}, {}
    for i, v in enumerate(ring):
        ang = 2 * math.pi * i / k - math.pi / 2
        angles[v] = ang
        pos[v] = int(round((cx + r * math.cos(ang)) / 2) * 2)
        y[v] = int(round((cy + r * math.sin(ang)) / 2) * 2)

    def _rect(v, px, py):
        w = widths.get(v, 96)
        return (px - w / 2, py - card_h / 2, px + w / 2, py + card_h / 2)

    placed = {v: _rect(v, pos[v], y[v]) for v in ring}

    def _free(v, px, py, gap=18):
        rx0, ry0, rx1, ry1 = _rect(v, px, py)
        for ux0, uy0, ux1, uy1 in placed.values():
            if rx0 < ux1 + gap and ux0 < rx1 + gap and ry0 < uy1 + gap and uy0 < ry1 + gap:
                return False
        return True

    # Straight-proxy segments (for crossing scoring): ring edges + in-ring chords
    segs = []
    rpos = {v: (pos[v], y[v]) for v in ring}
    for i in range(k):
        a, b = ring[i], ring[(i + 1) % k]
        segs.append((rpos[a], rpos[b], frozenset((a, b))))
    cyc_pairs = {(ring[i], ring[(i + 1) % k]) for i in range(k)}
    cyc_pairs |= {(b, a) for a, b in cyc_pairs}
    rset = set(ring)
    seen_e = set()
    for a, b in edges:
        if a in rset and b in rset:
            p = (a, b) if a < b else (b, a)
            if p not in cyc_pairs and p not in seen_e:
                seen_e.add(p)
                segs.append((rpos[a], rpos[b], frozenset((a, b))))

    def _add_cross(px, py, v):
        """New straight-proxy crossings added by placing v at candidate (px,py) (against placed neighbors)."""
        c = 0
        for u in sorted(adj[v]):
            if u not in pos:
                continue
            seg = ((px, py), (pos[u], y[u]), frozenset((v, u)))
            for q1, q2, eids in segs:
                if v in eids or u in eids:
                    continue
                if _seg_cross(seg[0], seg[1], q1, q2):
                    c += 1
        return c

    residual_pos = {}
    for v in sorted(plan["residuals"]):
        nbrs = [angles[u] for u in sorted(adj[v]) if u in angles]
        ang0 = (math.atan2(sum(math.sin(a) for a in nbrs),
                           sum(math.cos(a) for a in nbrs))
                if nbrs else 0.0)
        best = None
        for zone in ("inner", "outer"):
            for f in (_INNER_FS if zone == "inner"
                      else (1.0 + (card_h / 2 + 40 + 40 * i) / r for i in range(3))):
                for d in _ANGLE_DS:
                    ang = ang0 + math.radians(d)
                    px = int(round((cx + f * r * math.cos(ang)) / 2) * 2)
                    py = int(round((cy + f * r * math.sin(ang)) / 2) * 2)
                    if not _free(v, px, py):
                        continue
                    cross = _add_cross(px, py, v)
                    key = (cross, abs(d), abs(f - 0.42) if zone == "inner" else 1.0 + abs(f - 1.3),
                           px, py)
                    if best is None or key < best[0]:
                        best = (key, px, py, zone, f)
                if best is not None and best[0][0] == 0 and zone == "inner":
                    break       # zero crossings inside the ring already; no need to scan further
            if best is not None:
                break
        if best is None:
            raise InfeasibleRing(f"residual node {v} has no collision-free candidate")
        _, px, py, zone, f = best
        pos[v], y[v] = px, py
        placed[v] = _rect(v, px, py)
        residual_pos[v] = [zone, round(f, 3)]
        for u in sorted(adj[v]):
            if u in pos:
                segs.append(((px, py), (pos[u], y[u]), frozenset((v, u))))
    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = max(cfg.margin, cx - total / 2)
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    meta = {
        "placement": "ring-cycle",
        "ring": {
            "nodes": list(ring),
            "radius": r,
            "center": [cx, cy],
            "declared_loop": plan.get("declared_loop"),
            "polarity": plan.get("polarity"),
            "trigger": plan.get("trigger"),
            "chord_crossings": plan.get("chord_crossings", 0),
            "residuals": {v: info for v, info in residual_pos.items()},
        },
    }
    return pos, y, meta
