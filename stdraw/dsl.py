# -*- coding: utf-8 -*-
"""stdraw DSL v0.1（草案）解析器 —— 最小闭环。

语法（行导向，# 起注释，空行忽略）：

    graph "图名"
    var <id> "<标签>" [@value "<数值文本>"] [@group <gid>] [@w <补余量px>]
    <a> -> <+|-> <b> [@loops <id1>,<id2>]
    loop <id> "<标签>" "<R|B>" [<n1>, <n2>, ...]
    group <gid> "<分组标签>"

- 变量必须先声明后引用；极性边二元组是布局与证书的输入；
- 回路标签（loop）声明语义回路，由 loops.lint 做闭合性 + R/B 极性数边验证；
- 分组（group）可选，M0 不参与布局（张力处理见 model.py 模块注释）。

解析是确定性的：同一文本永远得到同一 Graph。
"""
import re
from .model import Graph, Node, Edge, Loop, Group

_VAR_RE = re.compile(
    r'^var\s+(\w+)\s+"([^"]*)"(?:\s+@value\s+"([^"]*)")?'
    r'(?:\s+@group\s+(\w+))?(?:\s+@w\s+(\d+))?\s*$')
_EDGE_RE = re.compile(
    r'^(\w+)\s*->\s*([+\-])\s*(\w+)(?:\s+@loops\s+([\w,\s]+))?\s*$')
_LOOP_RE = re.compile(
    r'^loop\s+(\w+)\s+"([^"]*)"\s+"?([RB])"?\s*\[([^\]]*)\]\s*$')
_GROUP_RE = re.compile(r'^group\s+(\w+)\s+"([^"]*)"\s*$')
_GRAPH_RE = re.compile(r'^graph\s+"([^"]*)"\s*$')


def parse(text: str) -> Graph:
    g = Graph(nodes=[], edges=[], loops=[], groups=[], name="")
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _GRAPH_RE.match(line)
        if m:
            g.name = m.group(1)
            continue
        m = _VAR_RE.match(line)
        if m:
            g.nodes.append(Node(id=m.group(1), label=m.group(2),
                                value=m.group(3) or "",
                                group=m.group(4) or None,
                                extra_w=int(m.group(5) or 0)))
            continue
        m = _EDGE_RE.match(line)
        if m:
            loops = [x.strip() for x in (m.group(4) or "").split(",") if x.strip()]
            g.edges.append(Edge(a=m.group(1), b=m.group(3),
                                polarity=m.group(2), loops=loops))
            continue
        m = _LOOP_RE.match(line)
        if m:
            ns = [x.strip() for x in m.group(4).split(",") if x.strip()]
            g.loops.append(Loop(id=m.group(1), label=m.group(2),
                                nodes=ns, kind=m.group(3)))
            continue
        m = _GROUP_RE.match(line)
        if m:
            g.groups.append(Group(id=m.group(1), label=m.group(2)))
            continue
        raise ValueError(f"DSL 第 {lineno} 行无法解析: {raw.strip()!r}")
    problems = g.validate()
    if problems:
        raise ValueError("DSL 结构校验失败:\n  " + "\n  ".join(problems))
    return g


def dumps(g: Graph) -> str:
    """Graph → DSL 文本（往返一致：parse(dumps(g)) == g）。"""
    out = []
    if g.name:
        out.append(f'graph "{g.name}"')
    out.append("")
    for n in g.nodes:
        parts = [f'var {n.id} "{n.label}"']
        if n.value:
            parts.append(f'@value "{n.value}"')
        if n.group:
            parts.append(f"@group {n.group}")
        if n.extra_w:
            parts.append(f"@w {n.extra_w}")
        out.append(" ".join(parts))
    out.append("")
    for e in g.edges:
        tail = f" @loops {','.join(e.loops)}" if e.loops else ""
        out.append(f"{e.a} -> {e.polarity} {e.b}{tail}")
    out.append("")
    for lp in g.loops:
        out.append(f'loop {lp.id} "{lp.label}" "{lp.kind}" [{", ".join(lp.nodes)}]')
    for gr in g.groups:
        out.append(f'group {gr.id} "{gr.label}"')
    return "\n".join(out) + "\n"
