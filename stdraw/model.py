# -*- coding: utf-8 -*-
"""Graph data model: variables / polarity edges / loop tags / groups.

Handling the tension with "relations determine layout, zero manual intent":
groups are merely optional semantic annotations; the layout layer by default does **not** consume groups -- deriving groups automatically via community detection
belongs to later roadmap milestones; at the current stage groups only enter certificate metadata and the loop-audit context.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Node:
    id: str
    label: str
    value: str = ""          # optional: value text on the card's second line (affects card width estimation)
    group: Optional[str] = None
    extra_w: int = 0         # optional: extra measured margin for mixed-script titles (px, multiple of 2)


@dataclass
class Edge:
    a: str
    b: str
    polarity: str            # "+" same-sign (reinforcing) / "-" opposite-sign (balancing)
    loops: List[str] = field(default_factory=list)   # tags of loops this edge participates in


@dataclass
class Loop:
    id: str
    label: str
    nodes: List[str]         # declared node sequence (closure verified against the sequence)
    kind: str = ""           # "R" reinforcing / "B" balancing (may be empty; checked against polarity parity at audit time)


@dataclass
class Group:
    id: str
    label: str = ""


@dataclass
class Graph:
    nodes: List[Node]
    edges: List[Edge]
    loops: List[Loop] = field(default_factory=list)
    groups: List[Group] = field(default_factory=list)
    name: str = ""

    # ── Convenience views ──
    def node_ids(self) -> List[str]:
        return [n.id for n in self.nodes]

    def id2node(self) -> Dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def adj_undirected(self) -> Dict[str, set]:
        adj: Dict[str, set] = {n.id: set() for n in self.nodes}
        for e in self.edges:
            adj.setdefault(e.a, set()).add(e.b)
            adj.setdefault(e.b, set()).add(e.a)
        return adj

    def degree0(self) -> List[str]:
        adj = self.adj_undirected()
        return [n.id for n in self.nodes if not adj[n.id]]

    def core(self) -> List[str]:
        adj = self.adj_undirected()
        return [n.id for n in self.nodes if adj[n.id]]

    def validate(self) -> List[str]:
        """Structural validation: returns a list of problems (empty = passed)."""
        problems = []
        ids = self.node_ids()
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            problems.append(f"duplicate node ids: {sorted(dup)}")
        idset = set(ids)
        for e in self.edges:
            if e.a not in idset or e.b not in idset:
                problems.append(f"edge endpoint not declared: {e.a}->{e.b}")
            if e.polarity not in ("+", "-"):
                problems.append(f"invalid polarity: {e.a}->{e.b} {e.polarity!r}")
        id2loop = {lp.id: lp for lp in self.loops}
        for e in self.edges:
            for lid in e.loops:
                if lid not in id2loop:
                    problems.append(f"edge {e.a}->{e.b} references undeclared loop {lid}")
        for lp in self.loops:
            for v in lp.nodes:
                if v not in idset:
                    problems.append(f"loop {lp.id} references undeclared node {v}")
        for n in self.nodes:
            if n.group and n.group not in {g.id for g in self.groups}:
                problems.append(f"node {n.id} references undeclared group {n.group}")
        return problems

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "nodes": [
                {"id": n.id, "label": n.label, "value": n.value,
                 "group": n.group, "extra_w": n.extra_w}
                for n in self.nodes
            ],
            "edges": [
                {"a": e.a, "b": e.b, "polarity": e.polarity, "loops": e.loops}
                for e in self.edges
            ],
            "loops": [
                {"id": lp.id, "label": lp.label, "nodes": lp.nodes, "kind": lp.kind}
                for lp in self.loops
            ],
            "groups": [{"id": g.id, "label": g.label} for g in self.groups],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Graph":
        return cls(
            name=d.get("name", ""),
            nodes=[Node(**{k: v for k, v in nd.items()
                           if k in Node.__dataclass_fields__})
                   for nd in d.get("nodes", [])],
            edges=[Edge(a=e["a"], b=e["b"], polarity=e.get("polarity", "+"),
                        loops=list(e.get("loops", [])))
                   for e in d.get("edges", [])],
            loops=[Loop(id=lp["id"], label=lp.get("label", ""),
                        nodes=list(lp.get("nodes", [])), kind=lp.get("kind", ""))
                   for lp in d.get("loops", [])],
            groups=[Group(id=g["id"], label=g.get("label", ""))
                    for g in d.get("groups", [])],
        )
