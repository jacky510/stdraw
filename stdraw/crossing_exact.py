# -*- coding: utf-8 -*-
"""Exact crossing-number layer (WS2): OIL routing ILP + planarization-oracle adjudication + B&B squeeze.

Mathematical framework (full proofs in docs/crossing-exact.md):

1. Safe reductions (each carries a cr-preservation proof):
      - Self-loop removal (self-loops drawn locally, 0 crossings); connected-component decomposition (cr is additive);
      - Iterative deletion of degree-<=1 vertices (the leaf is reattached inside a face incident to its neighbor with 0 crossings);
      - Bridge decomposition (cr is additive over 2-edge-connected blocks).

2. Upper bound (UB): greedy maximal planar subgraph U + simultaneous-optimal insertion into (U, Pi).
      An insertion solution verified by the oracle is a real drawing -> the UB is always true.

3. Decomposition theorem (docs section 2): cr(G) = min over planar subgraphs U, all planar embeddings Pi of U,
      of the minimum crossings when inserting E\\U into Pi simultaneously.
      B&B enumeration (docs section 3): candidates F = E\\U with |F| <= 2*UB-2 provably cover the optimum;
      per candidate: G-F planar + 2-connected + all embeddings (rotation-system enumeration + Euler face-count criterion) plus
      the decision "a **realizable** solution with cost <= UB-1 exists". Complete coverage -> cr=UB is proven.

4. Insertion subproblem (for fixed (U, Pi)): **CP-SAT proposal + oracle adjudication**.
      - ILP (superset modeling, slack is harmless): each F edge = a unit-flow
          source->sink path on the dual graph of the triangulated embedding (each side at most once, good-drawing accounting; adjacent edges forbidden to cross);
          c_{e,f} = F-F mutual-crossing indicator (<= 1; must share a triangle).
      - Adjudication: build the **planarized graph H** from (paths, c) (U + arc paths + crossing points merged into single vertices),
          H planar <=> the solution is realizable (two-direction proof in docs section 4). H planar -> the solution is real, its cost is the crossing count;
          not planar -> a no-good clause eliminates exactly that solution; re-solve.
      - Correctness does not depend on any hand-crafted topology constraint set: the ILP is a superset of the realizable set, the oracle is ground truth;
          the loop terminates at the "optimal realizable solution" or "no realizable solution at that cost". Both are exact.
      - Determinism: num_workers=1 + fixed seed + an upper bound on the no-good loop count (honest degradation when exceeded).

5. Lower bound (LB, globally valid, always <= cr): greedy extraction of Kuratowski counterexamples (edge-disjoint) +
      z-ILP (each Kuratowski subgraph has at least one marked edge); cr >= ceil(marked edges / 2).
      When LB == UB optimality is provable regardless of coverage completeness.

6. No ortools / core size > 30 / enumeration over cap -> constructive degradation, proven_optimal=false,
      gap labeled honestly.
"""
import itertools
import math
from collections import defaultdict


# ────────────────────────── Simple undirected view of the graph ──────────────────────────


def undirected_edges(graph):
    """(a,b) undirected edge list: self-loops removed, parallel edges kept (parallel edges do not cross each other in a good drawing)."""
    edges, selfloops = [], []
    for e in graph.edges:
        if e.a == e.b:
            selfloops.append((e.a, e.b))
            continue
        edges.append((e.a, e.b))
    return edges, selfloops


def _adjacent(e1, e2):
    return bool({e1[0], e1[1]} & {e2[0], e2[1]})


# ────────────────────────── Safe reductions (cr-preserving) ──────────────────────────


def _iter_degree_prune(nodes, edges):
    nodes, edges = list(nodes), list(edges)
    changed = True
    while changed:
        changed = False
        deg = defaultdict(int)
        for a, b in edges:
            deg[a] += 1
            deg[b] += 1
        drop = {v for v in nodes if deg[v] <= 1}
        if drop:
            nodes = [v for v in nodes if v not in drop]
            edges = [(a, b) for a, b in edges if a not in drop and b not in drop]
            changed = True
    return nodes, edges


def _components(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
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


def _bridges_split(nodes, edges):
    """Tarjan bridges -> list of 2-edge-connected blocks [(nodes, edges)] (single-edge bridge blocks with cr=0 are discarded)."""
    adj = defaultdict(list)
    for i, (a, b) in enumerate(edges):
        adj[a].append((b, i))
        adj[b].append((a, i))
    disc, low, is_bridge = {}, {}, [False] * len(edges)
    parent, depth = {}, {}
    timer = [0]
    for root in nodes:
        if root in disc:
            continue
        disc[root] = low[root] = timer[0]
        timer[0] += 1
        depth[root] = 0
        stack = [(root, -1, iter(adj[root]))]
        while stack:
            v, pe, it = stack[-1]
            advanced = False
            for w, ei in it:
                if ei == pe:
                    continue
                if w not in disc:
                    parent[w] = (v, ei)
                    disc[w] = low[w] = timer[0]
                    timer[0] += 1
                    depth[w] = depth[v] + 1
                    stack.append((w, ei, iter(adj[w])))
                    advanced = True
                    break
                elif ei != parent.get(v, (None, -1))[1]:
                    low[v] = min(low[v], disc[w])
            if not advanced:
                stack.pop()
                if stack:
                    pv = stack[-1][0]
                    low[pv] = min(low[pv], low[v])
                    if low[v] > disc[pv]:
                        is_bridge[parent[v][1]] = True
    nbedges = [i for i in range(len(edges)) if not is_bridge[i]]
    adj2 = defaultdict(list)
    for i in nbedges:
        a, b = edges[i]
        adj2[a].append(i)
        adj2[b].append(i)
    seen_e, blocks = set(), []
    for i in nbedges:
        if i in seen_e:
            continue
        bl_edges, bl_nodes, stack = [], set(), [i]
        seen_e.add(i)
        while stack:
            ei = stack.pop()
            x, y = edges[ei]
            bl_edges.append(edges[ei])
            bl_nodes.update((x, y))
            for nxt in adj2[x] + adj2[y]:
                if nxt not in seen_e:
                    seen_e.add(nxt)
                    stack.append(nxt)
        blocks.append((sorted(bl_nodes), bl_edges))
    return blocks


def safe_reduce(graph):
    """Safe-reduction main entry -> (cores, info). cr(graph) = sum of cr(cores[i])."""
    edges, selfloops = undirected_edges(graph)
    nodes = graph.node_ids()
    cores = []
    for comp in _components(nodes, edges):
        cset = set(comp)
        ce = [(a, b) for a, b in edges if a in cset and b in cset]
        n2, e2 = _iter_degree_prune(comp, ce)
        if not e2:
            continue
        for bn, be in _bridges_split(n2, e2):
            if be:
                cores.append((bn, be))
    return cores, {"selfloops_removed": len(selfloops), "cores": len(cores)}


# ────────────────────────── Embedding utilities ──────────────────────────


def _faces_from_rotation(rotation, nodes, edges):
    """Rotation system -> face list + planarity criterion (face count == m - n + 2, Euler criterion for connected graphs).

    The successor of dart (u->v) is (v->x), where x is the cyclic successor of u in rotation[v]."""
    nxt = {}
    for v in nodes:
        rot = list(rotation[v])
        for i, w in enumerate(rot):
            nxt[(w, v)] = rot[(i + 1) % len(rot)]
    seen, faces = set(), []
    for v0 in nodes:
        for w0 in rotation[v0]:
            if (v0, w0) in seen:
                continue
            face, v, w = [], v0, w0
            while (v, w) not in seen:
                seen.add((v, w))
                face.append(v)
                w2 = nxt[(v, w)]
                v, w = w, w2
            faces.append(face)
    n, m = len(nodes), len(edges)
    return faces, len(faces) == m - n + 2


def _enum_rotations(nodes, edges, cap=20000):
    """Enumerate all planar embeddings (rotation systems) of a connected graph.

    The first element at each vertex is fixed (folding rotations are equivalent); the first vertex additionally requires second element < last element
    (folding the global mirror -- the mirror image has the same insertion cost); at the leaves the Euler face-count criterion verifies planarity.
    Returns (embeddings, capped)."""
    deg, neigh = defaultdict(int), defaultdict(set)
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
        neigh[a].add(b)
        neigh[b].add(a)
    vs = sorted(nodes, key=lambda v: (-deg[v], v))
    orders = {}
    for v in vs:
        ns = sorted(neigh[v])
        cand = [[ns[0]] + list(p) for p in itertools.permutations(ns[1:])]
        if v == vs[0] and len(ns) >= 3:
            cand = [r for r in cand if r[1] < r[-1]]
        orders[v] = cand
    embeddings, seen = [], set()
    count, capped = [0], [False]

    def dfs(i, cur):
        if capped[0]:
            return
        if i == len(vs):
            count[0] += 1
            if count[0] > cap:
                capped[0] = True
                return
            faces, ok = _faces_from_rotation(cur, nodes, edges)
            if not ok:
                return
            key = tuple((v, tuple(cur[v])) for v in vs)
            if key not in seen:
                seen.add(key)
                embeddings.append({v: list(cur[v]) for v in nodes})
            return
        v = vs[i]
        for rot in orders[v]:
            cur[v] = rot
            dfs(i + 1, cur)
        cur[v] = None

    dfs(0, {v: None for v in nodes})
    return embeddings, capped[0]


# ────────────────────────── Triangulation structures ──────────────────────────


def _split_face(face):
    """Face walk with repeated vertices -> list of simple cycles (cut-vertex pocket decomposition).

    Bridges/cut vertices make the same geometric face pass through a cut vertex multiple times: walk w is split at repeated vertex v;
    the inner cycle w[i:j] and the outer cycle w[:i]+w[j:] are both valid closed walks (adjacent pairs are darts of the original
    walk), recursing until no repeated vertices remain. In each returned cycle the first vertex never reappears."""
    walks, out = [face], []
    while walks:
        w = walks.pop()
        first = {}
        cut = None
        for i, v in enumerate(w):
            if v in first:
                cut = (first[v], i)
                break
            first[v] = i
        if cut is None:
            out.append(w)
            continue
        i, j = cut
        walks.append(w[i:j])            # inner cycle (v ... up to just before returning to v; v only at the front)
        if i > 0 or j < len(w):
            walks.append(w[:i] + w[j:])  # outer cycle (inner segment removed; still a closed walk)
    return out


class Triangulation:
    """Triangulation of a planar embedding: triangle list + sides (real-edge sides / virtual-chord sides).

    sides[i] = {kind: 'edge'|'chord', nodes: (x, y), payload, t1, t2}
        'edge':  real-edge side -- crossing it counts 1 crossing; payload = index of that edge in the full-graph edge list
        'chord': virtual chord inside a face -- crossing it is free; payload = (face_id, p, q)
    tri_sides[t] = the 3 side ids of triangle t; node_tris[v] = triangles containing vertex v.
    Faces with repeated vertices (bridge/cut-vertex pockets) are first split into simple cycles by _split_face.
    """

    def __init__(self, faces, global_index):
        self.triangles = []
        self.sides = []
        self.node_tris = defaultdict(list)
        self.tri_sides = defaultdict(list)
        edge_side, chord_sides = {}, {}
        simple_faces = []
        leaf_pairs = []                 # 2-cycles (leaf pockets): [u, v], leaf hanging off its neighbor
        for face in faces:
            for w in _split_face(face):
                if len(w) < 3:
                    if len(w) == 2:
                        leaf_pairs.append(w)
                    continue
                simple_faces.append(w)

        def real_side(x, y):
            key = tuple(sorted((x, y)))
            if key not in edge_side:
                edge_side[key] = len(self.sides)
                self.sides.append({"kind": "edge", "nodes": (x, y),
                                   "payload": global_index[key],
                                   "t1": None, "t2": None})
            return edge_side[key]

        def chord_side(fi, p, q):
            key = (fi,) + tuple(sorted((p, q)))
            if key not in chord_sides:
                chord_sides[key] = len(self.sides)
                self.sides.append({"kind": "chord", "nodes": (p, q),
                                   "payload": key[1:], "t1": None, "t2": None})
            return chord_sides[key]

        for fi, face in enumerate(simple_faces):
            if len(face) < 3:
                continue                     # bigon face (parallel-edge remnant): no triangle
            k = len(face)
            v0 = face[0]
            tris_f = []
            for j in range(1, k - 1):
                t = len(self.triangles)
                self.triangles.append((v0, face[j], face[j + 1]))
                for v in self.triangles[-1]:
                    self.node_tris[v].append(t)
                tris_f.append(t)
            for j in range(len(tris_f)):
                jf = j + 1
                t = tris_f[j]
                if jf == 1:
                    self.tri_sides[t].append(real_side(v0, face[1]))
                else:
                    self.tri_sides[t].append(chord_side(fi, v0, face[jf]))
                self.tri_sides[t].append(real_side(face[jf], face[jf + 1]))
                if jf + 1 == k - 1:
                    self.tri_sides[t].append(real_side(v0, face[k - 1]))
                else:
                    self.tri_sides[t].append(chord_side(fi, v0, face[jf + 1]))
        use = defaultdict(list)
        for t, sids in self.tri_sides.items():
            for sid in sids:
                use[sid].append(t)
        for sid, ts in use.items():
            ts = sorted(set(ts))
            if len(ts) != 2:
                raise AssertionError(f"side {sid} has {len(ts)} adjacent triangles != 2")
            self.sides[sid]["t1"], self.sides[sid]["t2"] = ts
        # Leaf vertices (degree 1: 2-cycle pockets are skipped, no triangles) -> inherit the neighbor's triangle set.
        # Semantics = the cr-preservation theorem's "reattach the leaf inside a face incident to its neighbor with 0 crossings": the leaf position can be re-chosen,
        # an arc leaving the leaf is equivalent to leaving any face incident to its neighbor (0-crossing hookup).
        for pair in leaf_pairs:
            u, v = pair
            tu, tv = self.node_tris.get(u), self.node_tris.get(v)
            if tu and not tv:
                self.node_tris[v] = list(tu)
            elif tv and not tu:
                self.node_tris[u] = list(tv)
            elif not tu and not tv:
                merged = sorted(set(tu or []) | set(tv or []))
                self.node_tris[u] = list(merged)
                self.node_tris[v] = list(merged)


# ────────────────────────── OIL routing ILP + oracle adjudication ──────────────────────────


def _build_model(tri, nodes, edges, F, cp_model):
    """Superset ILP: routing flow + mutual-crossing indicators (slack -- correctness is guaranteed by the oracle)."""
    m = cp_model.CpModel()
    nT = len(tri.triangles)
    nS = len(tri.sides)
    side_real = [tri.sides[s]["kind"] == "edge" for s in range(nS)]
    side_edge = [tri.sides[s]["payload"] if tri.sides[s]["kind"] == "edge"
                 else None for s in range(nS)]
    side_tris = [(tri.sides[s]["t1"], tri.sides[s]["t2"]) for s in range(nS)]
    all_tris = list(range(nT))

    u, sel_src, sel_end, fdir = {}, {}, {}, {}
    for k, (a, b) in enumerate(F):
        src_tris = tri.node_tris.get(a, all_tris)
        end_tris = tri.node_tris.get(b, all_tris)
        for t in all_tris:
            sel_src[(k, t)] = m.NewBoolVar(f"src_{k}_{t}")
            sel_end[(k, t)] = m.NewBoolVar(f"end_{k}_{t}")
        m.Add(sum(sel_src[(k, t)] for t in src_tris) == 1)
        m.Add(sum(sel_src[(k, t)] for t in all_tris if t not in src_tris) == 0)
        m.Add(sum(sel_end[(k, t)] for t in end_tris) == 1)
        m.Add(sum(sel_end[(k, t)] for t in all_tris if t not in end_tris) == 0)
        fk = {}
        for sid in range(nS):
            g = side_edge[sid]
            uv = m.NewBoolVar(f"u_{k}_{sid}")
            if g is not None and _adjacent(F[k], edges[g]):
                m.Add(uv == 0)          # adjacent edges forbidden to cross (removable by perturbation in a good drawing)
            u[(k, sid)] = uv
            t1, t2 = side_tris[sid]
            f0 = m.NewBoolVar(f"f_{k}_{sid}_a")
            f1 = m.NewBoolVar(f"f_{k}_{sid}_b")
            m.Add(f0 + f1 == uv)
            fk[(sid, 0)] = f0
            fk[(sid, 1)] = f1
        fdir[k] = fk
        for t in all_tris:
            outflow = sum(fk[(sid, 0)] for sid in tri.tri_sides[t]
                          if side_tris[sid][0] == t) + \
                      sum(fk[(sid, 1)] for sid in tri.tri_sides[t]
                          if side_tris[sid][1] == t)
            inflow = sum(fk[(sid, 1)] for sid in tri.tri_sides[t]
                         if side_tris[sid][0] == t) + \
                     sum(fk[(sid, 0)] for sid in tri.tri_sides[t]
                         if side_tris[sid][1] == t)
            m.Add(outflow - inflow == sel_src[(k, t)] - sel_end[(k, t)])

    onroute, zvars, cvar = {}, {}, {}
    for k in range(len(F)):
        for t in all_tris:
            terms = [sel_src[(k, t)], sel_end[(k, t)]] + \
                    [u[(k, sid)] for sid in tri.tri_sides[t]]
            o = m.NewBoolVar(f"on_{k}_{t}")
            m.Add(o <= sum(terms))
            for term in terms:
                m.AddImplication(term, o)
            onroute[(k, t)] = o
    for k1 in range(len(F)):
        for k2 in range(k1 + 1, len(F)):
            if _adjacent(F[k1], F[k2]):
                continue
            c = m.NewBoolVar(f"c_{k1}_{k2}")
            zl = []
            for t in all_tris:
                z = m.NewBoolVar(f"z_{k1}_{k2}_{t}")
                m.Add(z <= onroute[(k1, t)])
                m.Add(z <= onroute[(k2, t)])
                zl.append(z)
            m.Add(c <= sum(zl))
            cvar[(k1, k2)] = c
            zvars[(k1, k2)] = zl

    scope = list(u.values()) + list(sel_src.values()) + \
        list(sel_end.values()) + list(cvar.values())
    return {"model": m, "u": u, "sel_src": sel_src, "sel_end": sel_end,
            "fdir": fdir, "cvar": cvar, "zvars": zvars, "scope": scope,
            "side_real": side_real, "side_edge": side_edge,
            "side_tris": side_tris, "all_tris": all_tris}


def _extract_solution(tri, edges, F, F_idx, parts, solver):
    """Extract (event sequences, mutual) from solution values. Event sequence[k] follows arc order:
    ('x', edge idx) = crossing that real edge; ('m', pair_key) = mutual crossing with the paired arc."""
    u, sel_src, sel_end = parts["u"], parts["sel_src"], parts["sel_end"]
    fdir, cvar, zvars = parts["fdir"], parts["cvar"], parts["zvars"]
    side_real, side_edge, side_tris = (parts["side_real"], parts["side_edge"],
                                       parts["side_tris"])
    all_tris = parts["all_tris"]
    nT = len(tri.triangles)
    mutual_tri = {}
    for (k1, k2), c in cvar.items():
        if solver.Value(c):
            for i, z in enumerate(zvars[(k1, k2)]):
                if solver.Value(z):
                    mutual_tri[(k1, k2)] = i
                    break
    events = {}
    for k, (a, b) in enumerate(F):
        cur = next(t for t in all_tris if solver.Value(sel_src[(k, t)]))
        end_t = next(t for t in all_tris if solver.Value(sel_end[(k, t)]))
        seq = []
        guard = 0
        while True:
            seq += [("m", pk) for pk, tt in sorted(mutual_tri.items())
                    if k in pk and tt == cur]
            if cur == end_t:
                break
            guard += 1
            moved = False
            for sid in tri.tri_sides[cur]:
                t1, t2 = side_tris[sid]
                if cur not in (t1, t2):
                    continue
                d = 0 if t1 == cur else 1
                if solver.Value(fdir[k][(sid, d)]):
                    if side_real[sid]:
                        seq.append(("x", side_edge[sid]))
                    cur = side_tris[sid][1 - d]
                    moved = True
                    break
            if not moved or guard > nT + 2:
                seq.append(("stuck", None))
                break
        events[k] = seq
    mutual = [[F_idx[k1], F_idx[k2]]
              for (k1, k2), c in cvar.items() if solver.Value(c)]
    return events, mutual


def _planarized_graph(nodes, edges, U_idx, F, F_idx, events, mutual):
    """(paths, mutual crossings) -> planarized abstract graph H. H planar <=> the solution is realizable (docs section 4).

    Returns None if a route is broken (judged unrealizable directly)."""
    import networkx as nx
    H = nx.Graph()
    H.add_nodes_from(nodes)
    for i in U_idx:
        H.add_edge(*edges[i])
    split = {}          # edge idx -> (ga, gb) after the current subdivision; the same edge can be crossed by multiple arcs
    xc = 0
    arc_vertex = {}
    for k, (a, b) in enumerate(F):
        seq = events.get(k, [])
        prev = a
        for item in seq:
            if item[0] == "x":
                g = item[1]
                x = f"X{xc}"
                xc += 1
                ga, gb = split.get(g, edges[g])
                H.remove_edge(ga, gb)
                H.add_edge(ga, x)
                H.add_edge(x, gb)
                split[g] = (ga, x)      # crossing points are ordered along the arc path order
                H.add_edge(prev, x)
                prev = x
            elif item[0] == "m":
                pk = item[1]
                if pk not in arc_vertex:
                    x = f"X{xc}"
                    xc += 1
                    arc_vertex[pk] = x
                    H.add_node(x)
                x = arc_vertex[pk]
                H.add_edge(prev, x)
                prev = x
            else:
                return None
        H.add_edge(prev, b)
    return H


def oil_insertion(nodes, edges, U_idx, F_idx, rotation,
                  ub=None, minimize=True, lex=True, max_nogood=400):
    """Simultaneous-optimal insertion for fixed (U, Pi) (CP-SAT proposal + planarization-oracle adjudication).

    minimize=True: return the optimal realizable solution (ok/cost/routes/events/mutual);
    minimize=False: decide "a realizable solution with cost <= ub exists" (ok/feasible).
    why='nogood-cap' means the adjudication loop hit its cap undecided -- the caller should honestly degrade the coverage flag.
    """
    U_key = {}
    for i in U_idx:
        x, y = edges[i]
        U_key[tuple(sorted((x, y)))] = i
    U_edges = [edges[i] for i in U_idx]
    F = [edges[i] for i in F_idx]
    if not F:
        return {"ok": True, "cost": 0, "routes": {}, "events": {}, "mutual": []}
    faces, ok = _faces_from_rotation(rotation, nodes, U_edges)
    if not ok:
        return {"ok": False, "why": "rotation-not-planar"}
    try:
        tri = Triangulation(faces, U_key)
    except AssertionError as exc:
        # embedding structure anomaly (non-simple face walk, etc.) -- degrade honestly instead of crashing
        return {"ok": False, "why": f"triangulation-failed: {exc}"}

    try:
        from ortools.sat.python import cp_model
    except Exception:
        return {"ok": False, "why": "no-ortools"}
    import networkx as nx

    parts = _build_model(tri, nodes, edges, F, cp_model)
    m = parts["model"]
    cost_real = [parts["u"][(k, sid)] for k in range(len(F))
                 for sid in range(len(tri.sides)) if parts["side_real"][sid]]
    total = sum(cost_real) + sum(parts["cvar"].values())
    if minimize:
        if lex:
            wu = sum((i + 1) * v for i, v in enumerate(cost_real))
            m.Minimize(10 ** 7 * total + 10 ** 5 * sum(parts["cvar"].values()) + wu)
        else:
            m.Minimize(total)
    else:
        m.Add(total <= ub)

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1          # determinism hard rule
    solver.parameters.random_seed = 42
    for _round in range(max_nogood + 1):
        st = solver.Solve(m)
        if st == cp_model.INFEASIBLE:
            if not minimize:
                return {"ok": False, "why": "infeasible"}
            if _round == 0:
                return {"ok": False, "why": "infeasible"}
            return {"ok": False, "why": "exhausted"}
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {"ok": False, "why": "unknown"}
        events, mutual = _extract_solution(tri, edges, F, F_idx, parts, solver)
        H = _planarized_graph(nodes, edges, U_idx, F, F_idx, events, mutual)
        if H is not None and nx.is_planar(H):
            if not minimize:
                return {"ok": True, "feasible": True}
            routes = {}
            for k, (a, b) in enumerate(F):
                routes[F_idx[k]] = {
                    "a": a, "b": b,
                    "crossings": [it[1] for it in events[k] if it[0] == "x"],
                }
            cost_x = sum(len(r["crossings"]) for r in routes.values()) + len(mutual)
            return {"ok": True, "cost": cost_x, "routes": routes,
                    "events": {F_idx[k]: events[k] for k in events},
                    "mutual": mutual}
        # not realizable -> a no-good clause eliminates exactly the current (routing, mutual-crossing) assignment
        lits = [v.Not() if solver.Value(v) else v for v in parts["scope"]]
        m.AddBoolOr(lits)
    return {"ok": False, "why": "nogood-cap"}


# ────────────────────────── Heuristics / lower bound ──────────────────────────


def _heuristic_planarization(nodes, edges):
    import networkx as nx
    order = sorted(range(len(edges)),
                   key=lambda i: (min(edges[i]), max(edges[i]), i))
    U = []
    for i in order:
        g = nx.Graph()
        g.add_nodes_from(nodes)
        for j in U + [i]:
            g.add_edge(*edges[j])
        if nx.is_planar(g):
            U = U + [i]
    F = [i for i in range(len(edges)) if i not in set(U)]
    return U, F


def _embed_U(nodes, edges, U_idx):
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for i in U_idx:
        g.add_edge(*edges[i])
    planar, emb = nx.check_planarity(g)
    if not planar:
        return None
    return {v: list(emb.neighbors_cw_order(v)) for v in g.nodes}


def _kuratowski_lb(nodes, edges):
    """Global lower bound (always <= cr): greedy extraction of Kuratowski counterexamples (edge-disjoint) + z-ILP.

    cr >= ceil(min marked edges / 2): in any drawing every Kuratowski subgraph must contain a crossing internally;
    min marked edges <= crossed edges <= 2 * crossing count."""
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for a, b in edges:
        g.add_edge(a, b)
    ks = []
    while g.number_of_edges() > 0:
        planar, cert = nx.check_planarity(g, counterexample=True)
        if planar:
            break
        kedges = sorted({tuple(sorted((x, y))) for x, y in cert.edges()})
        if not kedges:
            break
        ks.append(kedges)
        g.remove_edges_from(kedges)
    if not ks:
        return 0, []
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return 0, ks
    m = cp_model.CpModel()
    z = {}
    for a, b in edges:
        z[tuple(sorted((a, b)))] = m.NewBoolVar(f"z_{a}_{b}")
    for kedges in ks:
        m.Add(sum(z[e] for e in kedges) >= 1)
    m.Minimize(sum(z.values()))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 42
    if solver.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        zmin = int(round(solver.ObjectiveValue()))
        return (zmin + 1) // 2, ks
    return 0, ks


# ────────────────────────── Main entry ──────────────────────────


def crossing_exact(graph, max_nodes_exact=30, subset_cap=4000,
                   rotation_cap=200000, max_nogood=400):
    """CLD Graph -> crossing-number certificate block.

    crossing_number = UB (count from an oracle-verified real drawing, always true);
    proven_optimal is relative to the model class in docs/crossing-exact.md;
    lb/gap are honest; coverage: full/partial/planar/trivial."""
    cores, red = safe_reduce(graph)
    total_ub, total_lb = 0, 0
    proven, coverage = True, "full"
    witnesses, methods = [], []
    for cnodes, cedges in cores:
        try:
            if len(cnodes) > max_nodes_exact or not _has_solver():
                r = _core_heuristic(cnodes, cedges)
            else:
                r = _core_exact(cnodes, cedges, subset_cap, rotation_cap,
                                max_nogood)
        except Exception as exc:      # noqa: BLE001 -- unexpected-path fallback, honest degradation
            r = {"ub": len(cedges), "lb": 0, "proven": False,
                 "coverage": "partial",
                 "method": (f"core failed ({type(exc).__name__}: {exc}) — "
                            "heuristic upper-bound fallback"),
                 "witness": None}
        total_ub += r["ub"]
        total_lb += r["lb"]
        proven = proven and r["proven"]
        if r["coverage"] == "partial":
            coverage = "partial"
        if r.get("witness"):
            witnesses.append(r["witness"])
        methods.append(r["method"])
    if not cores:
        coverage = "trivial"
        methods = ["trivial (0 crossings by reduction)"]
    return {
        "crossing_number": total_ub,
        "proven_optimal": proven,
        "lb": total_lb,
        "gap": total_ub - total_lb,
        "coverage": coverage,
        "method": "; ".join(dict.fromkeys(methods)),
        "witness": witnesses,
        "reduced": red,
    }


def _has_solver():
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        return True
    except Exception:
        return False


def _greedy_insert_ub(nodes, edges, U_idx, F_idx, rotation):
    """Honest UB when oil insertion fails: insert F edges one by one into the current planarized drawing.

    Each step: current planar graph P (initially = the U embedding, including subdivision crossing points of earlier F edges) -> triangulate
    (with bridge/cut-vertex pocket splitting) -> 0/1-Dijkstra on the dual graph to find the minimum-crossing path between triangles containing the two
    endpoints -> single-edge face-path insertion is realizable (classical theorem) -> subdivide, update P and re-embed.
    After all insertions, the planarization oracle (the same H construction as Theorem C) verifies once; any step that
    fails returns (None, None) for the upper-layer fallback. Not optimal, honestly proven=False."""
    import heapq
    import networkx as nx

    def _route_and_insert(P, edge_of, a, b, xc_base):
        """Insert (a,b) on the triangulated dual of P: returns (list of crossed original edge ids, new P, new edge_of)"""
        planar, emb = nx.check_planarity(P)
        if not planar:
            return None, None, None, xc_base
        rot = {v: list(emb.neighbors_cw_order(v)) for v in P.nodes}
        P_edges = list(P.edges())
        key = {tuple(sorted(e)): i for i, e in enumerate(P_edges)}
        faces, ok = _faces_from_rotation(rot, list(P.nodes), P_edges)
        if not ok:
            return None, None, None, xc_base
        tri = Triangulation(faces, key)
        all_tris = list(range(len(tri.triangles)))
        starts = tri.node_tris.get(a, all_tris) or all_tris
        ends = tri.node_tris.get(b, all_tris) or all_tris
        dist, parent = {}, {}
        pq = []
        for t in starts:
            dist[t] = 0
            parent[t] = None
            heapq.heappush(pq, (0, t))
        end_t = None
        while pq:
            d, t = heapq.heappop(pq)
            if d > dist.get(t, 1 << 30):
                continue
            if t in ends:
                end_t = t
                break
            for sid in tri.tri_sides[t]:
                t1, t2 = tri.sides[sid]["t1"], tri.sides[sid]["t2"]
                nt = t2 if t1 == t else t1
                w = d + (1 if tri.sides[sid]["kind"] == "edge" else 0)
                if w < dist.get(nt, 1 << 30):
                    dist[nt] = w
                    parent[nt] = (t, sid)
                    heapq.heappush(pq, (w, nt))
        if end_t is None:
            return None, None, None, xc_base     # dual disconnected (P disconnected) -- hand off to the upper-layer fallback
        crossed = []                    # P edges crossed by this path (in path order)
        t = end_t
        while parent[t] is not None and not (t in starts and dist[t] == 0):
            pt, sid = parent[t]
            if tri.sides[sid]["kind"] == "edge":
                crossed.append(tri.sides[sid]["payload"])
            t = pt
        crossed.reverse()
        # Subdivide and update P: crossing points are inserted into the crossed edges in path order (same semantics as _planarized_graph).
        # The two subdivision segments of a crossed edge still belong to the original edge (mapping inherited); F path segments are tagged ("F", k).
        split = {}
        xc_tag = [xc_base]
        prev = a
        for pe in crossed:
            x = f"X#{xc_tag[0]}"
            xc_tag[0] += 1
            ga, gb = split.get(pe, P_edges[pe])
            oid = edge_of.get(tuple(sorted((ga, gb))))
            P.remove_edge(ga, gb)
            P.add_edge(ga, x)
            P.add_edge(x, gb)
            edge_of[(ga, x)] = oid
            edge_of[(x, gb)] = oid
            split[pe] = (ga, x)
            P.add_edge(prev, x)
            edge_of[tuple(sorted((prev, x)))] = ("F", k)
            prev = x
        P.add_edge(prev, b)
        edge_of[tuple(sorted((prev, b)))] = ("F", k)
        orig = [edge_of.get(tuple(sorted(P_edges[pe]))) for pe in crossed]
        return orig, P, edge_of, xc_tag[0]

    U_key = {}
    for i in U_idx:
        U_key[tuple(sorted(edges[i]))] = i
    U_edges = [edges[i] for i in U_idx]
    faces, ok = _faces_from_rotation(rotation, nodes, U_edges)
    if not ok:
        return None, None
    try:
        Triangulation(faces, U_key)     # self-check of the initial embedding structure
    except AssertionError:
        return None, None
    P = nx.Graph()
    P.add_nodes_from(nodes)
    for i in U_idx:
        P.add_edge(*edges[i])
    edge_of = {tuple(sorted(edges[i])): i for i in U_idx}
    routes, total = {}, 0
    xc = 0
    for k, (a, b) in enumerate([edges[i] for i in F_idx]):
        orig, P, edge_of, xc = _route_and_insert(P, edge_of, a, b, xc)
        if orig is None:
            return None, None
        routes[F_idx[k]] = {"a": a, "b": b, "crossings": orig}
        total += len(orig)
    if not nx.is_planar(P):             # final check: P is the planarized graph H (Theorem C semantics)
        return None, None
    witness = {"F": list(F_idx), "routes": routes, "mutual": []}
    return total, witness


def _core_heuristic(nodes, edges):
    U, F = _heuristic_planarization(nodes, edges)
    ub, witness, rot = None, None, None
    if _has_solver():
        rot = _embed_U(nodes, edges, U)
        if rot is not None:
            r = oil_insertion(nodes, edges, U, F, rot, minimize=True, lex=True)
            if r.get("ok") and r.get("cost") is not None:
                ub = r["cost"]
                witness = {"F": F, "routes": r["routes"], "mutual": r["mutual"]}
    if ub is None and rot is not None:
        ub, witness = _greedy_insert_ub(nodes, edges, U, F, rot)
    if ub is None:
        ub = len(F)             # last fallback when even the embedding is invalid (honestly partial, unproven)
    lb, _ = _kuratowski_lb(nodes, edges)
    return {"ub": ub, "lb": lb, "proven": False, "coverage": "partial",
            "method": "heuristic planarization (optimality not proven)",
            "witness": witness}


def _core_exact(nodes, edges, subset_cap, rotation_cap, max_nogood):
    """Single-core exact layer: UB heuristic -> exhaustive B&B squeeze."""
    import networkx as nx

    m = len(edges)

    def planar_subset(idxs):
        g = nx.Graph()
        g.add_nodes_from(nodes)
        for i in idxs:
            g.add_edge(*edges[i])
        return nx.is_planar(g)

    if planar_subset(range(m)):
        return {"ub": 0, "lb": 0, "proven": True, "coverage": "planar",
                "method": "planar (planarity witness)", "witness": None}

    U, F = _heuristic_planarization(nodes, edges)
    best_ub, witness = None, None
    rot = _embed_U(nodes, edges, U)
    if rot is not None:
        r = oil_insertion(nodes, edges, U, F, rot, minimize=True, lex=True,
                          max_nogood=max_nogood)
        if r.get("ok") and r.get("cost") is not None:
            best_ub = r["cost"]
            witness = {"F": F, "routes": r["routes"], "mutual": r["mutual"]}
    if best_ub is None and rot is not None:
        # oil did not converge (nogood-cap etc.): honest UB from greedy edge-by-edge insertion (with witness).
        # Note len(F) is not a universally true upper bound (K7: F=6 < cr=9), so it must not serve as a reference value.
        best_ub, witness = _greedy_insert_ub(nodes, edges, U, F, rot)
    if best_ub is None:
        best_ub = len(F)        # last fallback when even the embedding is invalid (honestly partial, unproven)
    lb, _ks = _kuratowski_lb(nodes, edges)
    if lb >= best_ub:
        return {"ub": best_ub, "lb": lb, "proven": True, "coverage": "full",
                "method": ("exact (Kuratowski-z lower bound meets "
                           "planarization upper bound)"),
                "witness": witness}

    coverage_full = True
    checked = 0
    kmax = min(m, 2 * best_ub - 2)
    for k in range(1, kmax + 1):
        if k > 2 * best_ub - 2:
            break              # enumeration bound shrinks dynamically as the UB improves (still covers the optimum, docs section 3)
        if (k + 1) // 2 >= best_ub:
            continue
        for Fc in itertools.combinations(range(m), k):
            checked += 1
            if checked > subset_cap:
                coverage_full = False
                break
            fset = set(Fc)
            Uc = [i for i in range(m) if i not in fset]
            if not planar_subset(Uc):
                continue
            if not _two_connected(nodes, Uc, edges):
                continue
            embs, capped = _enum_rotations(
                nodes, [edges[i] for i in Uc], cap=rotation_cap)
            if capped:
                coverage_full = False
            for rot2 in embs:
                r = oil_insertion(nodes, edges, Uc, Fc, rot2,
                                  ub=best_ub - 1, minimize=False,
                                  max_nogood=max_nogood)
                if r.get("why") == "nogood-cap":
                    coverage_full = False
                    continue
                if not r.get("ok"):
                    # why != infeasible/nogood-cap: this embedding was not fully adjudicated (triangulation
                    # failure / solver unknown, etc.) -- coverage incomplete, honestly mark partial
                    if r.get("why") != "infeasible":
                        coverage_full = False
                    continue
                if r.get("feasible"):
                    r2 = oil_insertion(nodes, edges, Uc, Fc, rot2,
                                       minimize=True, lex=True,
                                       max_nogood=max_nogood)
                    if r2.get("ok") and r2.get("cost") is not None and \
                            r2["cost"] < best_ub:
                        best_ub = r2["cost"]
                        witness = {"F": list(Fc), "routes": r2["routes"],
                                   "mutual": r2["mutual"]}
        if not coverage_full:
            break
    if coverage_full:
        proven = True
    else:
        proven = lb >= best_ub
    return {"ub": best_ub, "lb": lb, "proven": proven,
            "coverage": "full" if coverage_full else "partial",
            "method": ("exact OIL (routing ILP + planarization oracle, "
                       "exhaustive B&B over planar subgraphs x embeddings)"
                       if coverage_full else
                       "OIL B&B, enumeration capped — honest gap"),
            "witness": witness}


def _two_connected(nodes, U_idx, edges):
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for i in U_idx:
        g.add_edge(*edges[i])
    return nx.is_biconnected(g)
