# -*- coding: utf-8 -*-
"""图数据模型：变量 / 极性边 / 回路标签 / 分组。

与「关系决定布局、零人工意图」的张力处理：
分组只是可选的语义标注，布局层默认**不消费**分组——分组由社区检测自动推导
属于路线图后续里程碑；当前阶段分组仅进入证书元数据与环路审计上下文。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Node:
    id: str
    label: str
    value: str = ""          # 可选：卡片第二行数值文本（影响卡宽估算）
    group: Optional[str] = None
    extra_w: int = 0         # 可选：混排标题实测补余量（px，2 的倍数）


@dataclass
class Edge:
    a: str
    b: str
    polarity: str            # "+" 同向 / "-" 反向
    loops: List[str] = field(default_factory=list)   # 该边参与的回路标签


@dataclass
class Loop:
    id: str
    label: str
    nodes: List[str]         # 声明的节点序列（闭合性按序列验证）
    kind: str = ""           # "R" 增强 / "B" 平衡（可空，审计时按极性奇偶核对）


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

    # ── 便捷视图 ──
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
        """结构校验：返回问题列表（空 = 通过）。"""
        problems = []
        ids = self.node_ids()
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            problems.append(f"重复节点 id: {sorted(dup)}")
        idset = set(ids)
        for e in self.edges:
            if e.a not in idset or e.b not in idset:
                problems.append(f"边端点未声明: {e.a}->{e.b}")
            if e.polarity not in ("+", "-"):
                problems.append(f"极性非法: {e.a}->{e.b} {e.polarity!r}")
        id2loop = {lp.id: lp for lp in self.loops}
        for e in self.edges:
            for lid in e.loops:
                if lid not in id2loop:
                    problems.append(f"边 {e.a}->{e.b} 引用未声明回路 {lid}")
        for lp in self.loops:
            for v in lp.nodes:
                if v not in idset:
                    problems.append(f"回路 {lp.id} 引用未声明节点 {v}")
        for n in self.nodes:
            if n.group and n.group not in {g.id for g in self.groups}:
                problems.append(f"节点 {n.id} 引用未声明分组 {n.group}")
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
