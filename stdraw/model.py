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
    delay: bool = False       # optional: a delay on this link (DSL @delay; rendered as the || mark, gated)
    anchors: Optional[Dict[str, str]] = None  # optional: per-end anchor designation (DSL @anchors; keys src/dst -> vocabulary id, anchors.py caliber)


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
class Hints:
    """DSL semantic hints (T14) — layout INTENT at the loop/variable level,
    replacing pixel-level CLI parameters (deprecated: --pitch / --hub-side /
    --column-order). See docs/agent-interface.md.

    - main:  loop ids the engine should center ("@main R1");
    - order: loop ids in reading order ("@order R1,B1,R2") — the pipeline
      reorders graph.loops to this sequence at entry (audit listing, loop-arc
      scope and annotation order follow);
    - pairs: variable id pairs that should sit adjacent ("@pair a,b").
    """

    main: List[str] = field(default_factory=list)
    order: List[str] = field(default_factory=list)
    pairs: List[Tuple[str, str]] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.main or self.order or self.pairs)

    def to_dict(self) -> dict:
        return {"main": list(self.main), "order": list(self.order),
                "pairs": [[a, b] for (a, b) in self.pairs]}

    @classmethod
    def from_dict(cls, d: dict) -> "Hints":
        return cls(
            main=list(d.get("main", [])),
            order=list(d.get("order", [])),
            pairs=[(p[0], p[1]) for p in d.get("pairs", [])
                   if isinstance(p, (list, tuple)) and len(p) == 2],
        )


@dataclass
class Graph:
    nodes: List[Node]
    edges: List[Edge]
    loops: List[Loop] = field(default_factory=list)
    groups: List[Group] = field(default_factory=list)
    name: str = ""
    hints: Hints = field(default_factory=Hints)

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
        return [d["reason"] for d in self.validate_details()]

    def validate_details(self) -> List[dict]:
        """Structural validation with provenance; ``validate()`` is its string view.

        Every entry is ``{"reason": <the exact string validate() returns>,
        "kind": "node" | "edge" | "loop" | "group" | "hint"}`` plus the
        identifiers a caller needs to point at the offending declaration
        (``a``/``b`` for edges, ``id`` for nodes/loops/groups, ``target`` +
        ``ids`` for semantic hints; ``occurrence`` = "last" marks the second
        of a duplicated declaration).  Ordering and reason texts are the
        historical ``validate()`` output verbatim, so the string view stays
        byte-identical for every existing caller; the extra keys let the DSL
        parser attach source lines and the CLI write a structured
        parse_error.json (docs/agent-interface.md).
        """
        details = []
        ids = self.node_ids()
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            _dup = sorted(dup)
            details.append({"reason": f"duplicate node ids: {_dup}",
                            "kind": "node", "id": _dup[0],
                            "occurrence": "last"})
        idset = set(ids)
        seen_dirs = set()
        for e in self.edges:
            if e.a not in idset or e.b not in idset:
                details.append({"reason": f"edge endpoint not declared: {e.a}->{e.b}",
                                "kind": "edge", "a": e.a, "b": e.b})
            if e.polarity not in ("+", "-"):
                details.append({"reason": f"invalid polarity: {e.a}->{e.b} {e.polarity!r}",
                                "kind": "edge", "a": e.a, "b": e.b})
            if e.a == e.b:
                details.append({"reason": f"self-loop edge: {e.a}->{e.b}",
                                "kind": "edge", "a": e.a, "b": e.b})
            if (e.a, e.b) in seen_dirs:
                details.append({"reason": f"duplicate edge: {e.a}->{e.b}",
                                "kind": "edge", "a": e.a, "b": e.b,
                                "occurrence": "last"})
            seen_dirs.add((e.a, e.b))
        id2loop = {lp.id: lp for lp in self.loops}
        for e in self.edges:
            for lid in e.loops:
                if lid not in id2loop:
                    details.append({"reason": f"edge {e.a}->{e.b} references undeclared loop {lid}",
                                    "kind": "edge", "a": e.a, "b": e.b})
        for lp in self.loops:
            for v in lp.nodes:
                if v not in idset:
                    details.append({"reason": f"loop {lp.id} references undeclared node {v}",
                                    "kind": "loop", "id": lp.id})
        for n in self.nodes:
            if n.group and n.group not in {g.id for g in self.groups}:
                details.append({"reason": f"node {n.id} references undeclared group {n.group}",
                                "kind": "node", "id": n.id})
        id2loop = {lp.id for lp in self.loops}
        for hid in self.hints.main:
            if hid not in id2loop:
                details.append({"reason": f"@main references undeclared loop {hid}",
                                "kind": "hint", "target": "main", "ids": [hid]})
        for hid in self.hints.order:
            if hid not in id2loop:
                details.append({"reason": f"@order references undeclared loop {hid}",
                                "kind": "hint", "target": "order", "ids": [hid]})
        for (a, b) in self.hints.pairs:
            if a not in idset or b not in idset:
                details.append({"reason": f"@pair references undeclared variable: {a},{b}",
                                "kind": "hint", "target": "pair", "ids": [a, b]})
            elif a == b:
                details.append({"reason": f"@pair names the same variable twice: {a}",
                                "kind": "hint", "target": "pair", "ids": [a]})
        return details

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "nodes": [
                {"id": n.id, "label": n.label, "value": n.value,
                 "group": n.group, "extra_w": n.extra_w}
                for n in self.nodes
            ],
            "edges": [
                # "delay" is emitted only when set: graphs without a delayed
                # edge keep their historical graph.json bytes
                {"a": e.a, "b": e.b, "polarity": e.polarity, "loops": e.loops,
                 **({"delay": True} if e.delay else {})}
                for e in self.edges
            ],
            "loops": [
                {"id": lp.id, "label": lp.label, "nodes": lp.nodes, "kind": lp.kind}
                for lp in self.loops
            ],
            "groups": [{"id": g.id, "label": g.label} for g in self.groups],
            # "hints" is emitted only when non-empty: graphs without hints
            # keep their historical graph.json bytes byte-for-byte
            **({"hints": self.hints.to_dict()} if not self.hints.empty() else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Graph":
        return cls(
            name=d.get("name", ""),
            nodes=[Node(**{k: v for k, v in nd.items()
                           if k in Node.__dataclass_fields__})
                   for nd in d.get("nodes", [])],
            edges=[Edge(a=e["a"], b=e["b"], polarity=e.get("polarity", "+"),
                        loops=list(e.get("loops", [])),
                        delay=bool(e.get("delay", False)))
                   for e in d.get("edges", [])],
            loops=[Loop(id=lp["id"], label=lp.get("label", ""),
                        nodes=list(lp.get("nodes", [])), kind=lp.get("kind", ""))
                   for lp in d.get("loops", [])],
            groups=[Group(id=g["id"], label=g.get("label", ""))
                    for g in d.get("groups", [])],
            hints=Hints.from_dict(d.get("hints", {}) or {}),
        )
