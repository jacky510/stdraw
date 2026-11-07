# -*- coding: utf-8 -*-
"""Loop semantic audit (lint layer) -- unique capability: catches "declared ring not closed" and "polarity mislabeled".

Consumes only the Graph model (does not parse HTML or any other host format).

Verifies three things:
    1. Closure of declared rings: using only that ring's tagged edges, can the walk start at the first node, pass through all ring nodes, and return to it;
    2. R/B polarity edge count: parity of negative-polarity tagged edges <-> declared kind (R = even / reinforcing, B = odd / balancing) consistency;
    3. Independent enumeration: all simple loops actually present in the graph (DFS depth cap), compared against the declared set --
          declared-but-nonexistent and existing-but-undeclared are both reported honestly.

Outputs a report dict (can go into the certificate JSON); the lint verdict does not affect layout, only the quality layer.
"""
from collections import defaultdict
from typing import Dict, List

from .model import Graph

MAX_DFS_DEPTH = 12     # DFS depth cap for declared-ring closure
MAX_ENUM_DEPTH = 10    # length cap for independently enumerated loops


def loops_audit(graph: Graph) -> dict:
    out_adj = defaultdict(list)   # a -> [(b, polarity)]
    edge_loops: Dict[tuple, List[str]] = {}
    for e in graph.edges:
        pol = "-" if e.polarity == "-" else "+"
        out_adj[e.a].append((e.b, pol))
        edge_loops.setdefault((e.a, e.b), []).extend(e.loops)

    declared = {lp.id: lp for lp in graph.loops}
    report = {"loops": [], "problems": [], "extra_cycles": []}

    # ── 1+2. Audit each declared ring ──
    for lid, lp in declared.items():
        sub = defaultdict(list)
        neg = 0
        for e in graph.edges:
            if lid in e.loops:
                sub[e.a].append((e.b, e.polarity))
                if e.polarity == "-":
                    neg += 1
        start = lp.nodes[0] if lp.nodes else None
        found = None

        def dfs(cur, path, seen_edges):
            nonlocal found
            if found or len(path) > MAX_DFS_DEPTH:
                return
            for (nxt, _pol) in sub[cur]:
                if (cur, nxt) in seen_edges:
                    continue
                if nxt == start and len(path) >= 2:
                    found = path + [start]
                    return
                if nxt in path:
                    continue
                dfs(nxt, path + [nxt], seen_edges | {(cur, nxt)})

        if start:
            dfs(start, [start], set())
        closed = found is not None
        parity_kind = "B" if neg % 2 else "R"
        kind_ok = (not lp.kind) or (lp.kind == parity_kind)
        item = {
            "id": lid, "label": lp.label, "declared_kind": lp.kind,
            "nodes": lp.nodes, "closed": closed,
            "walk": found,
            "neg_edges": neg, "parity_kind": parity_kind,
            "kind_consistent": kind_ok,
        }
        if not closed:
            report["problems"].append(
                f"loop {lid} ({lp.label}) not closed: tagged edges cannot walk from {start} back to itself")
        if not kind_ok:
            report["problems"].append(
                f"loop {lid} ({lp.label}) declares {lp.kind} but polarity parity is actually {parity_kind}"
                f" (negative edges {neg})")
        report["loops"].append(item)

    # case where a declared ring has no tagged edges
    for lid, lp in declared.items():
        tagged = sum(1 for e in graph.edges if lid in e.loops)
        if tagged == 0:
            report["problems"].append(f"loop {lid} ({lp.label}) has no edges tagged with it")

    # ── 3. Independently enumerate all simple loops ──
    # loops are stored as canonical directed tuples (path order with the smallest node rotated to the front): a frozenset would fold
    # "different directed loops with the same node set" into one, and its iteration order drifts with PYTHONHASHSEED,
    # which once caused neg_edges/kind to swap between two renders of loops_audit.json (ref-scrubbed).
    cycles = set()

    def canon_cycle(path):
        return min(tuple(path[i:] + path[:i]) for i in range(len(path)))

    def walk(cur, start, path, seen_e):
        if len(path) > MAX_ENUM_DEPTH:
            return
        for (nxt, _pol) in out_adj[cur]:
            if (cur, nxt) in seen_e:
                continue
            if nxt == start and len(path) >= 2:
                cycles.add(canon_cycle(path))
                continue
            if nxt in path:
                continue
            walk(nxt, start, path + [nxt], seen_e | {(cur, nxt)})

    for n in list(out_adj):
        walk(n, n, [n], set())

    def cycle_kind(cyc):
        negs = 0
        for i in range(len(cyc)):
            a, b = cyc[i], cyc[(i + 1) % len(cyc)]
            pols = [e.polarity for e in graph.edges
                    if (e.a, e.b) in ((a, b), (b, a))]
            if pols and "-" in pols:
                negs += 1
        return "B" if negs % 2 else "R", negs

    declared_node_sets = [frozenset(lp.nodes) for lp in graph.loops]
    for cyc in sorted(cycles):          # tuple order = deterministic total order, no tie ambiguity
        kind, negs = cycle_kind(cyc)
        cset = frozenset(cyc)
        match = next((lp.id for lp, s in zip(graph.loops, declared_node_sets)
                      if s == cset), None)
        report["extra_cycles"].append({
            "nodes": sorted(cyc), "kind": kind, "neg_edges": negs,
            "matches_declared": match})
        if match is None:
            report["problems"].append(
                f"undeclared cycle {'->'.join(cyc)} ({kind}, negative edges {negs})")

    report["summary"] = {
        "declared": len(declared),
        "closed": sum(1 for it in report["loops"] if it["closed"]),
        "kind_consistent": sum(1 for it in report["loops"] if it["kind_consistent"]),
        "enumerated": len(cycles),
        "undeclared": sum(1 for c in report["extra_cycles"]
                          if c["matches_declared"] is None),
        "problems": len(report["problems"]),
    }
    report["pass"] = report["summary"]["problems"] == 0
    return report
