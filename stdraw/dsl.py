# -*- coding: utf-8 -*-
"""stdraw DSL v0.1 (draft) parser — the minimal closed loop.

Syntax (line-oriented, # starts a comment, blank lines ignored):

    graph "graph name"
    var <id> "<label>" [@value "<value text>"] [@group <gid>] [@w <extra px>]
    <a> -> <+|-> <b> [@loops <id1>,<id2>] [@anchors src=<aid>,dst=<aid>] [@delay]
    loop <id> "<label>" "<R|B>" [<n1>, <n2>, ...]
    group <gid> "<group label>"
    @main <loopid>[,<loopid>...]      # semantic hint (T14): main loop(s) to center
    @order <loopid>[,<loopid>...]     # semantic hint (T14): loop reading order
    @pair <var1>,<var2>               # semantic hint (T14): adjacent variables

- Variables must be declared before use; polarity edge pairs are the input to
  layout and certificates;
- Loop declarations state semantic loops, validated by loops.lint for closure
  + R/B polarity edge counting;
- Edge tags may follow in either order (@loops ... / @anchors ... / @delay),
  each at most once; dumps() always writes @loops first, then @anchors,
  then @delay (the canonical order that keeps parse(dumps(g)) == g);
- @anchors designates per-end connection points (keys src/dst; ids from the
  anchors.py vocabulary: n/e/s/w midpoints, ne/se/sw/nw corners, numbered
  side slots n-g1..n-g7 etc.); the layout honors them as user-designated
  anchors (same channel as the interactive export),
- Groups are optional and do not participate in layout (tension handling is
  discussed in the model.py module docstring).
- Semantic hints (T14) are line-oriented directives starting with "@";
  dumps() always emits them AFTER the groups in the canonical order
  @main lines, then @order, then @pair lines (the order that keeps
  parse(dumps(g)) == g; a hand-written file may list them in any order —
  parse is order-tolerant, dumps is canonical).

Parsing is deterministic: the same text always yields the same Graph.
"""
import re
from .model import Graph, Node, Edge, Loop, Group
from .anchors import is_anchor_id as _is_anchor_id, MAX_SLOTS as _MAX_SLOTS

# A quoted field carries \" and \\ escapes; other backslash pairs are kept
# verbatim (unknown escapes are not interpreted).
_QSTR = r'"((?:[^"\\]|\\.)*)"'
_VAR_RE = re.compile(
    r'^var\s+(\w+)\s+' + _QSTR +
    r'(?:\s+@value\s+' + _QSTR + r')?'
    r'(?:\s+@group\s+(\w+))?(?:\s+@w\s+(\d+))?\s*$')
_EDGE_RE = re.compile(r'^(\w+)\s*->\s*([+\-])\s*(\w+)(.*)$')
# one edge tag: "@loops <ids>" / "@delay" / "@anchors src=<id>[,dst=<id>]"
# (a whole word), followed by whitespace or end of line.  Anchor ids are
# the anchors.py vocabulary (side midpoint / corner / numbered side slot);
# syntax is validated here, resolvability is guaranteed by the vocabulary.
_EDGE_TAG_RE = re.compile(
    r'^@(?:loops\s+([\w,\s]+)|delay|anchors\s+([\w\-=,\s]+))(?=\s|$)')
_EDGE_ANCHOR_PAIR_RE = re.compile(r'^(src|dst)\s*=\s*([\w\-]+)\s*$')
_LOOP_RE = re.compile(
    r'^loop\s+(\w+)\s+' + _QSTR + r'\s*"?([RB])"?\s*\[([^\]]*)\]\s*$')
_GROUP_RE = re.compile(r'^group\s+(\w+)\s+' + _QSTR + r'\s*$')
_GRAPH_RE = re.compile(r'^graph\s+' + _QSTR + r'\s*$')
# Semantic hints (T14): line-oriented directives "@main/@order/@pair".
# ids are comma-separated word tokens; @pair takes exactly two variables.
_HINT_IDLIST_RE = re.compile(r'^@(main|order)\s+([\w]+(?:\s*,\s*[\w]+)*)\s*$')
_PAIR_RE = re.compile(r'^@pair\s+(\w+)\s*,\s*(\w+)\s*$')


class DSLParseError(ValueError):
    """A DSL parse or structural-validation failure carrying its source location.

    It subclasses ``ValueError`` deliberately: the library contract is
    "malformed input raises", so callers that already catch ``ValueError`` --
    and the message texts themselves -- keep working unchanged.  The
    structured fields exist for the CLI presentation layer, which renders them
    as ``parse_error.json`` instead of a Python traceback
    (docs/agent-interface.md, "error surface contract").
    """

    def __init__(self, message, *, kind, line=None, column=None,
                 snippet="", detail=None, problems=None):
        super().__init__(message)
        self.kind = kind                # "syntax" | "structure"
        self.line = line                # 1-based source line, None = unknown
        self.column = column            # 1-based column, None = unknown
        self.snippet = snippet          # the offending source line, stripped
        self.detail = detail            # specific cause, e.g. "unknown anchor id: 'n-g8'"
        self.problems = problems or []  # structure: [{line, reason}, ...]

    def to_dict(self) -> dict:
        """The parse_error.json payload (schema: docs/agent-interface.md)."""
        out = {"error": True, "kind": self.kind, "line": self.line,
               "column": self.column, "reason": str(self),
               "snippet": self.snippet}
        if self.detail:
            out["detail"] = self.detail
        if self.problems:
            out["problems"] = self.problems
        return out


def _column(raw: str, line: str, pos: int):
    """1-based column of offset ``pos`` in ``line``, mapped back into ``raw``."""
    off = raw.find(line) if line else -1
    if off < 0 or pos is None:
        return None
    return off + pos + 1


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
    lines = text.splitlines()
    # Source-line index for the structured error payload.  A declaration can
    # appear twice (duplicate node / duplicate edge), so each key keeps every
    # occurrence in file order and the locator picks first (or last, when the
    # problem *is* the duplication).
    node_line: dict = {}
    edge_line: dict = {}
    loop_line: dict = {}
    group_line: dict = {}
    hint_line: dict = {"main": [], "order": [], "pair": []}

    def _decl_line(detail):
        """Source line of one validate_details() entry, None when unattributable."""
        kind = detail.get("kind")
        hits = []
        if kind == "edge":
            hits = edge_line.get((detail.get("a"), detail.get("b")), [])
        elif kind == "node":
            hits = node_line.get(detail.get("id"), [])
        elif kind == "loop":
            hits = loop_line.get(detail.get("id"), [])
        elif kind == "group":
            hits = group_line.get(detail.get("id"), [])
        elif kind == "hint":
            want = set(detail.get("ids") or [])
            for ln, ids in hint_line.get(detail.get("target"), []):
                if want & set(ids):
                    hits.append(ln)
        if not hits:
            return None
        return hits[-1] if detail.get("occurrence") == "last" else hits[0]

    for lineno, raw in enumerate(lines, 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        snippet = raw.strip()
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
            node_line.setdefault(m.group(1), []).append(lineno)
            continue
        m = _EDGE_RE.match(line)
        if m:
            loops, delay, tail, bad, why = [], False, m.group(4), False, ""
            pos = m.start(4)          # offset of the tag tail inside `line`
            anchors_sel = {}
            while tail.strip():
                fragment = tail.lstrip()
                pos += len(tail) - len(fragment)
                t = _EDGE_TAG_RE.match(fragment)
                if not t:
                    bad = True          # unknown tag / stray text after the edge
                    why = ("unknown tag or stray text after the edge "
                           "(expected @loops <ids> / @anchors src=<id>[,dst=<id>] / @delay)")
                    break
                if t.group(1) is not None:
                    if loops:
                        bad = True      # a second @loops tag
                        why = "second @loops tag on one edge (each tag may appear once)"
                        break
                    loops = [x.strip() for x in t.group(1).split(",") if x.strip()]
                elif t.group(2) is not None:
                    if anchors_sel:
                        bad = True      # a second @anchors tag
                        why = "second @anchors tag on one edge (each tag may appear once)"
                        break
                    for piece in t.group(2).split(","):
                        p = _EDGE_ANCHOR_PAIR_RE.match(piece.strip())
                        if not p:
                            bad = True  # malformed @anchors pair
                            why = (f"malformed @anchors pair: {piece.strip()!r} "
                                   "(expected src=<id> or dst=<id>)")
                            break
                        end_key, aid = p.group(1), p.group(2)
                        if end_key in anchors_sel:
                            bad = True  # duplicate src/dst
                            why = f"@anchors names {end_key} twice"
                            break
                        if not _is_anchor_id(aid):
                            bad = True  # unknown anchor id syntax
                            why = (f"unknown anchor id: {aid!r} (vocabulary: "
                                   "n/e/s/w, ne/se/sw/nw, "
                                   f"<side>-g1..g{_MAX_SLOTS})")
                            break
                        anchors_sel[end_key] = aid
                    if bad:
                        break
                else:
                    if delay:
                        bad = True      # a second @delay tag
                        why = "second @delay tag on one edge (each tag may appear once)"
                        break
                    delay = True
                tail = fragment[t.end():]
                pos += t.end()
            if bad:
                raise DSLParseError(
                    f"DSL line {lineno} cannot be parsed: {snippet!r}",
                    kind="syntax", line=lineno,
                    column=_column(raw, line, pos),
                    snippet=snippet, detail=why)
            g.edges.append(Edge(a=m.group(1), b=m.group(3),
                                polarity=m.group(2), loops=loops, delay=delay,
                                anchors=anchors_sel or None))
            edge_line.setdefault((m.group(1), m.group(3)), []).append(lineno)
            continue
        m = _LOOP_RE.match(line)
        if m:
            ns = [x.strip() for x in m.group(4).split(",") if x.strip()]
            g.loops.append(Loop(id=m.group(1), label=_unescape(m.group(2)),
                                nodes=ns, kind=m.group(3)))
            loop_line.setdefault(m.group(1), []).append(lineno)
            continue
        m = _GROUP_RE.match(line)
        if m:
            g.groups.append(Group(id=m.group(1), label=_unescape(m.group(2))))
            group_line.setdefault(m.group(1), []).append(lineno)
            continue
        m = _HINT_IDLIST_RE.match(line)
        if m:
            ids = [x.strip() for x in m.group(2).split(",") if x.strip()]
            if m.group(1) == "main":
                g.hints.main.extend(ids)
            else:
                g.hints.order.extend(ids)
            hint_line[m.group(1)].append((lineno, ids))
            continue
        m = _PAIR_RE.match(line)
        if m:
            g.hints.pairs.append((m.group(1), m.group(2)))
            hint_line["pair"].append((lineno, [m.group(1), m.group(2)]))
            continue
        head = line.split(None, 1)[0]
        if head in ("graph", "var", "loop", "group"):
            why = f"{head} line does not match the documented syntax"
        else:
            why = ("line matches none of the documented forms: graph / var / "
                   "loop / group / '<a> -> <+|-> <b>' / @main / @order / @pair")
        raise DSLParseError(
            f"DSL line {lineno} cannot be parsed: {snippet!r}",
            kind="syntax", line=lineno,
            column=_column(raw, line, 0),
            snippet=snippet, detail=why)
    details = g.validate_details()
    if details:
        located = [{"line": _decl_line(d), "reason": d["reason"]} for d in details]
        first = next((p for p in located if p["line"]), located[0])
        snippet = lines[first["line"] - 1].strip() if first["line"] else ""
        raise DSLParseError(
            "DSL structural validation failed:\n  "
            + "\n  ".join(d["reason"] for d in details),
            kind="structure", line=first["line"], snippet=snippet,
            detail=details[0]["reason"], problems=located)
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
        if getattr(e, "anchors", None):
            # canonical pair order src,dst (keeps parse(dumps(g)) == g)
            pair = ",".join(f"{k}={e.anchors[k]}"
                            for k in ("src", "dst") if k in e.anchors)
            tail += f" @anchors {pair}"
        if e.delay:
            tail += " @delay"
        out.append(f"{e.a} -> {e.polarity} {e.b}{tail}")
    out.append("")
    for lp in g.loops:
        out.append(f'loop {lp.id} "{_escape(lp.label)}" "{lp.kind}" [{", ".join(lp.nodes)}]')
    for gr in g.groups:
        out.append(f'group {gr.id} "{_escape(gr.label)}"')
    # semantic hints (T14), canonical order: @main lines, then @order, then
    # @pair lines — emitted only when present (graphs without hints keep
    # their historical bytes byte-for-byte)
    for hid in g.hints.main:
        out.append(f"@main {hid}")
    if g.hints.order:
        out.append("@order " + ",".join(g.hints.order))
    for (a, b) in g.hints.pairs:
        out.append(f"@pair {a},{b}")
    return "\n".join(out) + "\n"
