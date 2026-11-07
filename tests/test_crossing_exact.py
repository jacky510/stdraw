#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WS2: exact crossing-number layer tests (classic ground truths + brute-force cross-check + determinism + degradation).

Known ground truths (literature; all verifiable via mainstream textbooks/Wikipedia):
  cr(K5)=1, cr(K3,3)=1 (Kuratowski basic facts)
  cr(K6)=3 (Guy 1960 formula floor(6/2)*floor(5/2)*floor(4/2)*floor(3/2)/4 = 3;
      Saaty 1964 proved this formula optimal for n<=10 -- a proven truth.
      Wikipedia "Crossing number (graph theory)" S Complete graphs: formula
      values 1,3,9,... correspond to p=5,6,7,...)
  cr(Petersen)=2 (Wikipedia "Petersen graph" S Embeddings states verbatim
      "The Petersen graph has crossing number 2"; it also notes the most
      common five-pointed-star drawing has 5 crossings but is not optimal --
      "Petersen=5" is a well-known misreading)
  planar graph = 0 (planarity witness)
  subdivision does not change the crossing number (homeomorphism invariance)
  WARNING common misreading: "K6=15" is K6's edge count |E|=C(6,2)=15, not
  its crossing number.

Environment self-report: main() prints the interpreter version and ortools
availability up front -- proven/lb/coverage evidence must be cited together
with that environment line (without ortools, proven=False/lb=0/coverage=partial
across the board is the honest-degradation signature, see
docs/crossing-exact.md S9).
"""
import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx

from stdraw.model import Graph, Node, Edge
from stdraw import crossing_exact as cx


def mk(n, edge_pairs, name=""):
    g = Graph(name=name, nodes=[], edges=[])
    for i in range(n):
        g.nodes.append(Node(id=f"v{i+1}", label=f"x{i+1}"))
    for a, b in edge_pairs:
        g.edges.append(Edge(a=f"v{a}", b=f"v{b}", polarity="+"))
    return g


def _planarizable(edges, cross_pairs):
    """Set of crossing pairs (list of edge pairs) -> path-level planarized
    graph -> planarity. One edge may be shared by multiple crossing pairs
    (chained subdivision)."""
    g = nx.Graph()
    g.add_nodes_from(set(x for e in edges for x in e))
    for a, b in edges:
        g.add_edge(a, b)
    splits = {}       # edge idx -> [a, X1, ..., b] chain-segment endpoint sequence
    xc = 0
    for ei, ej in cross_pairs:
        X = f"X{xc}"
        xc += 1
        g.add_node(X)
        for idx in (ei, ej):
            a, b = edges[idx]
            chain = splits.get(idx)
            if chain is None:
                g.remove_edge(a, b)
                splits[idx] = [a, X, b]
                g.add_edge(a, X)
                g.add_edge(X, b)
            else:
                # insert into a mid-chain segment (between it and the previous crossing point)
                mid = chain[-2]
                g.remove_edge(mid, chain[-1])
                g.add_edge(mid, X)
                g.add_edge(X, chain[-1])
                chain.insert(-1, X)
    return nx.is_planar(g)


def brute_cr(graph, max_cross=2):
    """Independent ground truth: enumerate up to max_cross crossing pairs and
    test planarization. Returns (cr or None, complete)."""
    edges, _ = cx.undirected_edges(graph)
    g0 = nx.Graph()
    g0.add_nodes_from(graph.node_ids())
    for a, b in edges:
        g0.add_edge(a, b)
    if nx.is_planar(g0):
        return 0, True
    pairs = list(itertools.combinations(range(len(edges)), 2))
    good = [p for p in pairs if not cx._adjacent(edges[p[0]], edges[p[1]])]
    for p in good:
        if _planarizable(edges, [p]):
            return 1, True
    for p1, p2 in itertools.combinations(good, 2):
        if _planarizable(edges, [p1, p2]):
            return 2, True
    return None, False


def _rand_graph(rng, seed):
    n = rng.randint(5, 7)
    m = rng.randint(5, min(n * (n - 1) // 2, 11))
    pairs = rng.sample(list(itertools.combinations(range(1, n + 1), 2)), m)
    return mk(n, pairs, f"random-{seed}")


def main():
    failures = []
    try:
        import ortools
        env_line = (f"python {sys.version.split()[0]} | ortools "
                    f"{ortools.__version__} available -> exact paths armed")
    except Exception:
        env_line = (f"python {sys.version.split()[0]} | ortools NOT available "
                    f"-> honest degradation expected (proven=False, lb=0, "
                    f"coverage=partial)")
    print(f"== 0. Environment: {env_line}")
    print("   literature ground truth: K5=1, K3,3=1, Petersen=2, K4=0, K3,3-subdiv=1, "
          "K6=3 (Guy/Saaty n<=10)")
    petersen = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1)]
    petersen += [(i + 1, 6 + i) for i in range(5)]
    petersen += [(6 + i, 6 + (i + 2) % 5) for i in range(5)]
    k33sub = [(1, 4), (1, 5), (1, 7), (1, 6), (2, 4), (2, 5), (2, 6),
              (3, 4), (3, 5), (3, 6)]
    classics = [
        ("K5", mk(5, list(itertools.combinations(range(1, 6), 2)), "K5"), 1),
        ("K3,3", mk(6, [(1, 4), (1, 5), (1, 6), (2, 4), (2, 5), (2, 6),
                        (3, 4), (3, 5), (3, 6)], "K33"), 1),
        ("Petersen", mk(10, petersen, "Petersen"), 2),
        ("K4(planar)", mk(4, [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)],
                         "K4"), 0),
        ("K3,3-subdiv", mk(7, k33sub, "K33sub"), 1),
        ("K6", mk(6, list(itertools.combinations(range(1, 7), 2)), "K6"), 3),
    ]
    print("== A. classic graph ground truth ==")
    for name, g, expect in classics:
        r = cx.crossing_exact(g)
        ok = r["crossing_number"] == expect and r["proven_optimal"]
        if not ok:
            failures.append(f"{name}: cr={r['crossing_number']}(expected {expect}) "
                            f"proven={r['proven_optimal']}")
        print(f"{'OK ' if ok else 'FAIL'} {name}: cr={r['crossing_number']} "
              f"proven={r['proven_optimal']} lb={r['lb']} gap={r['gap']} "
              f"coverage={r['coverage']}")

    print("== B. random graph brute-force cross-check (full enumeration for cr<=2) ==")
    rng = random.Random(20261105)
    for seed in range(8):
        g = _rand_graph(rng, seed)
        truth, complete = brute_cr(g)
        r = cx.crossing_exact(g)
        if complete and truth is not None:
            ok = r["crossing_number"] == truth
            if not ok:
                failures.append(f"random-{seed}: engine={r['crossing_number']} "
                                f"brute={truth}")
            print(f"{'OK ' if ok else 'FAIL'} random-{seed}: "
                  f"engine={r['crossing_number']} brute={truth} "
                  f"proven={r['proven_optimal']}")
        else:
            print(f"--  random-{seed}: brute not exhaustive (cr>2), "
                  f"engine={r['crossing_number']} gap={r['gap']}")

    print("== C. determinism (two runs byte-identical) ==")
    g = mk(10, petersen, "Petersen")
    j1 = json.dumps(cx.crossing_exact(g), sort_keys=True, ensure_ascii=False)
    j2 = json.dumps(cx.crossing_exact(g), sort_keys=True, ensure_ascii=False)
    if j1 != j2:
        failures.append("Petersen: two runs differ")
        print("FAIL determinism")
    else:
        print("OK  determinism (byte-identical)")

    print("== D. graceful degradation without ortools ==")
    saved = {k: v for k, v in sys.modules.items() if "ortools" in k}
    for k in saved:
        del sys.modules[k]
    import builtins
    real_import = builtins.__import__

    def blocked(name, *a, **kw):
        if "ortools" in name:
            raise ImportError("blocked for test")
        return real_import(name, *a, **kw)
    builtins.__import__ = blocked
    try:
        r = cx.crossing_exact(g)
    finally:
        builtins.__import__ = real_import
        sys.modules.update(saved)
    if r["proven_optimal"] or r["coverage"] != "partial":
        failures.append(f"degradation path: proven={r['proven_optimal']} "
                        f"coverage={r['coverage']}")
        print("FAIL degradation: expected exact=False and coverage=partial")
    else:
        print(f"OK  degradation: cr={r['crossing_number']} proven=False "
              f"coverage=partial (honestly labeled)")

    # == E. bridge/cut-vertex face triangulation regression (ref-scrubbed) ==
    # With bridges/cut vertices in greedy planar subgraph U, face walks repeat
    # vertices and old Triangulation fan-triangulates -> AssertionError "side x
    # adjacent triangles 1 != 2" (random-n20-i00 crash at 1.3s). Case n8-m13-seed55:
    # trigger present + old count necessarily != 2 + post-fix (_split_face) crossing_exact returns gracefully.
    g55 = nx.gnm_random_graph(8, 13, seed=55)
    reg = mk(8, [(a + 1, b + 1) for a, b in sorted(g55.edges())], "reg-s55")
    cores, _red = cx.safe_reduce(reg)
    cnodes, cedges = cores[0]
    U, F = cx._heuristic_planarization(cnodes, cedges)
    Ue = [cedges[i] for i in U]
    rot = cx._embed_U(cnodes, cedges, U)
    faces, ok = cx._faces_from_rotation(rot, cnodes, Ue)
    rep = [f for f in faces if len(set(f)) != len(f)]
    e_ok = bool(rep)
    if not e_ok:
        failures.append("reg-s55: trigger condition gone (no face with repeated vertices) -- regression case void")
    print(f"{'OK ' if e_ok else 'FAIL'} reg-s55: UB embedding has repeated-vertex faces x{len(rep)} "
          f"(bridge/cut-vertex pocket trigger condition in place)")
    r = cx.crossing_exact(reg)
    ok2 = (isinstance(r.get("crossing_number"), int)
           and r.get("coverage") in ("full", "partial", "planar", "trivial"))
    if not ok2:
        failures.append(f"reg-s55: crossing_exact did not return gracefully cr={r.get('crossing_number')} "
                        f"coverage={r.get('coverage')}")
    print(f"{'OK ' if ok2 else 'FAIL'} reg-s55: cr={r['crossing_number']} "
          f"proven={r['proven_optimal']} coverage={r['coverage']} "
          f"(zero crashes after the ref-scrubbed fix)")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nAll crossing-exact tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
