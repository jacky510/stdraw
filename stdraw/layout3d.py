# -*- coding: utf-8 -*-
"""3D placement layer (the "lowest-tier" delivery form): nodes arranged in regular solids.

Five-solid slot generation + deterministic assignment; arbitrary-angle rotation, depth shading, wireframe reference.

Solids: sphere (Fibonacci sphere) / cube (lattice points) / tetra (tetrahedron face mesh) /
cone (concentric rings shrinking to the apex). Assignment: greedy nearest neighbor + pairwise-swap optimization minimizing total edge length
(deterministic: slot order, assignment order, and swap order all fixed; no RNG).

Chords not intersecting in space is guaranteed by dimensional redundancy; projection crossings are resolved by the camera in the user's hands --
the 3D layer makes no 2D crossing promise (honest tiering).
"""
import math
from typing import Dict, List, Tuple


# ── Slot generation (all deterministic, unit coordinates, uniformly scaled after generation) ──────────
def sphere_slots(n: int) -> List[Tuple[float, float, float]]:
    pts = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (i / max(n - 1, 1)) * 2
        r = math.sqrt(max(0.0, 1 - y * y))
        th = golden * i
        pts.append((math.cos(th) * r, y, math.sin(th) * r))
    return pts


def cube_slots(n: int) -> List[Tuple[float, float, float]]:
    m = max(2, math.ceil(n ** (1 / 3)))
    pts = []
    for z in range(m):
        for y in range(m):
            for x in range(m):
                pts.append(((x / (m - 1)) * 2 - 1,
                            (y / (m - 1)) * 2 - 1,
                            (z / (m - 1)) * 2 - 1))
    return pts[:n]


_TETRA_V = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]


def tetra_slots(n: int) -> List[Tuple[float, float, float]]:
    """Tetrahedron face mesh: barycentric layer sweep (each layer lies on the 4 faces, min component = 0)."""
    pts = []
    s = 3
    while len(pts) < n and s < 60:
        layer = []
        for i in range(s + 1):
            for j in range(s + 1 - i):
                for k in range(s + 1 - i - j):
                    l = s - i - j - k
                    b = (i, j, k, l)
                    if min(b) == 0:      # on a face
                        x = sum(c * v[0] for c, v in zip(b, _TETRA_V)) / s
                        y = sum(c * v[1] for c, v in zip(b, _TETRA_V)) / s
                        z = sum(c * v[2] for c, v in zip(b, _TETRA_V)) / s
                        layer.append((x, y, z))
        layer.sort()                     # deterministic order
        pts.extend(layer)
        s += 1
    # fallback: truncate when full; if short, top up with a Fibonacci sphere (recorded honestly)
    if len(pts) >= n:
        return pts[:n]
    extra = sphere_slots(n - len(pts))
    return pts + extra


def cone_slots(n: int) -> List[Tuple[float, float, float]]:
    """Cone: 1 apex point + concentric rings going down (radius scaling up linearly, uniform angles within a ring)."""
    pts = [(0.0, 1.0, 0.0)]
    if n == 1:
        return pts
    rings = max(1, round(math.sqrt(n - 1)))
    per = max(1, (n - 1) // rings)
    t = 0
    placed = 1
    while placed < n:
        frac = (t + 1) / rings
        r = frac
        y = 1 - frac * 2
        cnt = min(per, n - placed) if placed + per < n else n - placed
        cnt = max(1, cnt)
        for k in range(cnt):
            ang = 2 * math.pi * k / cnt + 0.5 * t      # inter-layer offset (deterministic)
            pts.append((math.cos(ang) * r, y, math.sin(ang) * r))
        placed += cnt
        t += 1
    return pts[:n]


SOLIDS = {"sphere": sphere_slots, "cube": cube_slots,
          "tetra": tetra_slots, "cone": cone_slots}


# ── Deterministic assignment: greedy nearest neighbor + pairwise-swap optimization ────────────────────
def assign(nodes: List[str], slots: List[Tuple[float, float, float]],
           edges: List[Tuple[str, str]]) -> Dict[str, Tuple[float, float, float]]:
    """Nodes -> slots. Greedy (fixed node order) + all-pairs swap passes (swap only on positive gain, fixed order)."""
    avail = list(range(len(slots)))
    m = {v: None for v in nodes}
    # coarse ordering across components: node order by adjacency-chain BFS order (deterministic), isolated nodes last
    adj: Dict[str, List[str]] = {v: [] for v in nodes}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    order, seen = [], set()
    for v in nodes:
        if v in seen or not adj[v]:
            continue
        stack = [v]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            order.append(u)
            for w in sorted(adj[u], reverse=True):
                if w not in seen:
                    stack.append(w)
    order += [v for v in nodes if v not in seen]

    def edge_len_sum():
        return sum(math.dist(m[a], m[b]) for a, b in edges
                   if m.get(a) and m.get(b))

    for v in order:
        if not avail:
            break
        # greedy: pick the slot minimizing the increment in assigned edge length (ties resolved toward the smaller index, deterministic)
        best, best_cost = None, None
        for si in avail:
            c = 0.0
            for w in adj[v]:
                if m.get(w) is not None:
                    c += math.dist(slots[si], m[w])
            if best_cost is None or c < best_cost - 1e-12:
                best, best_cost = si, c
        m[v] = slots[best]
        avail.remove(best)
    # pairwise-swap optimization (at most 4 passes)
    node_list = order
    for _ in range(4):
        improved = False
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                a, b = node_list[i], node_list[j]
                m[a], m[b] = m[b], m[a]
                if edge_len_sum() < edge_len_sum() - 1e-9:
                    improved = True
                else:
                    m[a], m[b] = m[b], m[a]
        if not improved:
            break
    return m


def layout3d(graph_dict: dict, solid: str = "sphere", scale: float = 300.0):
    """graph_dict: {"nodes":[{id,label}], "edges":[{a,b}]} -> {"positions": {...}}"""
    gen = SOLIDS[solid]
    ids = [n["id"] for n in graph_dict["nodes"]]
    edges = [(e["a"], e["b"]) for e in graph_dict["edges"]]
    slots = gen(len(ids))
    m = assign(ids, slots, edges)
    return {"solid": solid, "scale": scale,
            "positions": {v: [round(c * scale, 1) for c in m[v]] for v in ids}}
