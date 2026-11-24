# -*- coding: utf-8 -*-
"""stdraw DSL v0.1 (draft) parser — the minimal closed loop.

Syntax (line-oriented, # starts a comment, blank lines ignored):

    graph "graph name"
    var <id> "<label>" [@value "<value text>"] [@group <gid>] [@w <extra px>]
    <a> -> <+|-> <b> [@loops <id1>,<id2>] [@delay]
    loop <id> "<label>" "<R|B>" [<n1>, <n2>, ...]
    group <gid> "<group label>"

- Variables must be declared before use; polarity edge pairs are the input to
  layout and certificates;
- Loop declarations state semantic loops, validated by loops.lint for closure
  + R/B polarity edge counting;
- Edge tags may follow in either order (@loops ... / @delay), each at most
  once; dumps() always writes @loops first, then @delay (the canonical order
  that keeps parse(dumps(g)) == g);
- Groups are optional and do not participate in layout (tension handling is
  discussed in the model.py module docstring).

Parsing is deterministic: the same text always yields the same Graph.
"""
import re
from .model import Graph, Node, Edge, Loop, Group

# A quoted field carries \" and \\ escapes; other backslash pairs are kept
# verbatim (unknown escapes are not interpreted).
_QSTR = r'"((?:[^"\\]|\\.)*)"'
_VAR_RE = re.compile(
    r'^var\s+(\w+)\s+' + _QSTR +
    r'(?:\s+@value\s+' + _QSTR + r')?'
    r'(?:\s+@group\s+(\w+))?(?:\s+@w\s+(\d+))?\s*$')
_EDGE_RE = re.compile(r'^(\w+)\s*->\s*([+\-])\s*(\w+)(.*)$')
# one edge tag: "@loops <ids>" or "@delay" (a whole word), followed by
# whitespace or end of line
_EDGE_TAG_RE = re.compile(r'^@(?:loops\s+([\w,\s]+)|delay)(?=\s|$)')
_LOOP_RE = re.compile(
    r'^loop\s+(\w+)\s+' + _QSTR + r'\s*"?([RB])"?\s*\[([^\]]*)\]\s*$')
_GROUP_RE = re.compile(r'^group\s+(\w+)\s+' + _QSTR + r'\s*$')
_GRAPH_RE = re.compile(r'^graph\s+' + _QSTR + r'\s*$')


def _unescape(s: str) -> str:
    """Undo the DSL escapes: \\\" -> \" and \\\\ -> backslash (verbatim otherwise)."""
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in ('"', "\\"):
            out.append(s[i + 1])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _escape(s: str) -> str:
    """Escape a field for DSL output: backslash first, then quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _strip_comment(line: str) -> str:
    """Drop a trailing # comment, but only outside quoted fields.

    A '#' inside a quoted field is data (e.g. var a "C# dev"), not a comment.
    """
    out = []
    inq = False
    i = 0
    while i < len(line):
        c = line[i]
        if inq and c == "\\" and i + 1 < len(line):
            out.append(c)
            out.append(line[i + 1])
            i += 2
            continue
        if c == '"':
            inq = not inq
            out.append(c)
            i += 1
            continue
        if c == "#" and not inq:
            break
        out.append(c)
        i += 1
    return "".join(out)


def parse(text: str) -> Graph:
    g = Graph(nodes=[], edges=[], loops=[], groups=[], name="")
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        m = _GRAPH_RE.match(line)
        if m:
            g.name = _unescape(m.group(1))
            continue
        m = _VAR_RE.match(line)
        if m:
            g.nodes.append(Node(id=m.group(1), label=_unescape(m.group(2)),
                                value=_unescape(m.group(3)) if m.group(3) is not None else "",
                                group=m.group(4) or None,
                                extra_w=int(m.group(5) or 0)))
            continue
        m = _EDGE_RE.match(line)
        if m:
            loops, delay, tail, bad = [], False, m.group(4), False
            while tail.strip():
                rest = tail.lstrip()
                t = _EDGE_TAG_RE.match(rest)
                if not t:
                    bad = True          # unknown tag / stray text after the edge
                    break
                if t.group(1) is not None:
                    if loops:
                        bad = True      # a second @loops tag
                        break
                    loops = [x.strip() for x in t.group(1).split(",") if x.strip()]
                else:
                    if delay:
                        bad = True      # a second @delay tag
                        break
                    delay = True
                tail = rest[t.end():]
            if bad:
                raise ValueError(f"DSL line {lineno} cannot be parsed: {raw.strip()!r}")
            g.edges.append(Edge(a=m.group(1), b=m.group(3),
                                polarity=m.group(2), loops=loops, delay=delay))
            continue
        m = _LOOP_RE.match(line)
        if m:
            ns = [x.strip() for x in m.group(4).split(",") if x.strip()]
            g.loops.append(Loop(id=m.group(1), label=_unescape(m.group(2)),
                                nodes=ns, kind=m.group(3)))
            continue
        m = _GROUP_RE.match(line)
        if m:
            g.groups.append(Group(id=m.group(1), label=_unescape(m.group(2))))
            continue
        raise ValueError(f"DSL line {lineno} cannot be parsed: {raw.strip()!r}")
    problems = g.validate()
    if problems:
        raise ValueError("DSL structural validation failed:\n  " + "\n  ".join(problems))
    return g


def dumps(g: Graph) -> str:
    """Graph -> DSL text (round-trip consistent: parse(dumps(g)) == g).

    Quoted fields escape backslash first, then double quotes (\\\" / \\\\).
    """
    out = []
    if g.name:
        out.append(f'graph "{_escape(g.name)}"')
    out.append("")
    for n in g.nodes:
        parts = [f'var {n.id} "{_escape(n.label)}"']
        if n.value:
            parts.append(f'@value "{_escape(n.value)}"')
        if n.group:
            parts.append(f"@group {n.group}")
        if n.extra_w:
            parts.append(f"@w {n.extra_w}")
        out.append(" ".join(parts))
    out.append("")
    for e in g.edges:
        tail = f" @loops {','.join(e.loops)}" if e.loops else ""
        if e.delay:
            tail += " @delay"
        out.append(f"{e.a} -> {e.polarity} {e.b}{tail}")
    out.append("")
    for lp in g.loops:
        out.append(f'loop {lp.id} "{_escape(lp.label)}" "{lp.kind}" [{", ".join(lp.nodes)}]')
    for gr in g.groups:
        out.append(f'group {gr.id} "{_escape(gr.label)}"')
    return "\n".join(out) + "\n"
