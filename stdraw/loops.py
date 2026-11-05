# -*- coding: utf-8 -*-
"""环路语义审计（lint 层）—— 独有能力：抓「声明环不闭合」「极性标错」。

只吃 Graph 模型（不解析 HTML 或其他宿主格式）。

验证三件事：
  1. 声明环闭合性：只用该环 tagged 边，能否从首节点经全部环节点走回自身；
  2. R/B 极性数边：tagged 边负极性奇偶 ↔ 声明类型（R=偶/增强，B=奇/平衡）一致；
  3. 独立枚举：全图实际存在的全部简单回路（DFS 上限深度），与声明集对照——
     声明了但不存在 / 存在但未声明的都如实报。

输出 report dict（可入证书 JSON），lint 结论不影响布局，只进质量层。
"""
from collections import defaultdict
from typing import Dict, List

from .model import Graph

MAX_DFS_DEPTH = 12     # 声明环闭合性 DFS 深度上限
MAX_ENUM_DEPTH = 10    # 独立枚举回路长度上限


def loops_audit(graph: Graph) -> dict:
    out_adj = defaultdict(list)   # a -> [(b, polarity)]
    edge_loops: Dict[tuple, List[str]] = {}
    for e in graph.edges:
        pol = "-" if e.polarity == "-" else "+"
        out_adj[e.a].append((e.b, pol))
        edge_loops.setdefault((e.a, e.b), []).extend(e.loops)

    declared = {lp.id: lp for lp in graph.loops}
    report = {"loops": [], "problems": [], "extra_cycles": []}

    # ── 1+2. 逐声明环审计 ──
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
                f"环 {lid}（{lp.label}）不闭合：tagged 边无法从 {start} 走回自身")
        if not kind_ok:
            report["problems"].append(
                f"环 {lid}（{lp.label}）声明 {lp.kind} 但极性奇偶实为 {parity_kind}"
                f"（负边 {neg} 条）")
        report["loops"].append(item)

    # 声明环的边未打 tag 的情况
    for lid, lp in declared.items():
        tagged = sum(1 for e in graph.edges if lid in e.loops)
        if tagged == 0:
            report["problems"].append(f"环 {lid}（{lp.label}）没有任何边打该标签")

    # ── 3. 独立枚举全部简单回路 ──
    cycles = set()

    def walk(cur, start, path, seen_e):
        if len(path) > MAX_ENUM_DEPTH:
            return
        for (nxt, _pol) in out_adj[cur]:
            if (cur, nxt) in seen_e:
                continue
            if nxt == start and len(path) >= 2:
                cycles.add(frozenset(path))
                continue
            if nxt in path:
                continue
            walk(nxt, start, path + [nxt], seen_e | {(cur, nxt)})

    for n in list(out_adj):
        walk(n, n, [n], set())

    def cycle_kind(cyc):
        negs = 0
        members = list(cyc)
        for i in range(len(members)):
            a, b = members[i], members[(i + 1) % len(members)]
            if (a, b) in edge_loops or (b, a) in edge_loops:
                pols = [e.polarity for e in graph.edges
                        if (e.a, e.b) in ((a, b), (b, a))]
                if "-" in pols:
                    negs += 1
        return "B" if negs % 2 else "R", negs

    declared_node_sets = [frozenset(lp.nodes) for lp in graph.loops]
    for cyc in sorted(cycles, key=lambda c: sorted(c)):
        kind, negs = cycle_kind(cyc)
        match = next((lp.id for lp, s in zip(graph.loops, declared_node_sets)
                      if s == cyc), None)
        report["extra_cycles"].append({
            "nodes": sorted(cyc), "kind": kind, "neg_edges": negs,
            "matches_declared": match})
        if match is None:
            report["problems"].append(
                f"存在未声明回路 {'->'.join(sorted(cyc))}（{kind}，负边 {negs} 条）")

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
