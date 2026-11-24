# -*- coding: utf-8 -*-
"""Regression: DSL parser robustness.

Pre-fix behavior: (a) '#' started a comment even inside a quoted field, so
`var a "C# dev"` truncated the label to `var a "C`; (b) quoted fields had no
escape support, so a label containing a quote or backslash could not round
trip; (c) validate() silently accepted self-loops and duplicate directed
edges.
"""
import random

import pytest

from stdraw.dsl import dumps, parse
from stdraw.model import Edge, Graph, Group, Loop, Node


# ── comments only outside quotes ──

def test_hash_inside_quoted_label_is_data():
    g = parse("""
graph "t"
var a "C# 开发" # trailing comment still works
var b "b # x"
a -> + b
b -> - a
""")
    assert g.nodes[0].label == "C# 开发"
    assert g.nodes[1].label == "b # x"


def test_trailing_comment_still_stripped():
    g = parse('graph "t" # comment\nvar a "a"\nvar b "b"\na -> + b # cmt\nb -> - a\n')
    assert g.name == "t"
    assert len(g.edges) == 2


# ── escapes in quoted fields ──

def test_escape_round_trip_fixed_labels():
    g = Graph(
        name='na"me\\',
        nodes=[Node(id="a", label='say "hi" C:\\path'),
               Node(id="b", label="#not a comment")],
        edges=[Edge(a="a", b="b", polarity="+"),
               Edge(a="b", b="a", polarity="-")],
        loops=[Loop(id="L", label='l"oop\\', nodes=["a", "b"], kind="R")],
        groups=[Group(id="g1", label='g"roup\\')],
    )
    text = dumps(g)
    # dumps must emit the escapes, not raw quotes/backslashes inside fields
    assert '\\"' in text and "\\\\" in text
    assert parse(text) == g


def test_unknown_escape_kept_verbatim():
    # only \" and \\ are escapes; other backslash pairs stay as written
    g = parse('graph "t"\nvar a "a\\nb"\nvar b "b"\na -> + b\nb -> - a\n')
    assert g.nodes[0].label == "a\\nb"


# ── validate: self-loops and duplicate directed edges rejected ──

def test_self_loop_rejected():
    text = 'graph "t"\nvar a "a"\na -> + a\n'
    with pytest.raises(ValueError, match="self-loop"):
        parse(text)


def test_duplicate_directed_edge_rejected():
    text = 'graph "t"\nvar a "a"\nvar b "b"\na -> + b\na -> - b\n'
    with pytest.raises(ValueError, match="duplicate edge"):
        parse(text)


def test_mutual_pair_still_legal():
    # opposite directions are a mutual pair, not duplicates
    g = parse('graph "t"\nvar a "a"\nvar b "b"\na -> + b\nb -> + a\n')
    assert len(g.edges) == 2


# ── property: random labels round trip ──

CHARS = ['"', "#", "\\", "中", "文", "+", "-", "@", "[", "]", ",", "a", "Z", "0"]


def test_random_label_round_trip_property():
    rng = random.Random(20261124)
    for it in range(400):
        def lab(minlen=0):
            return "".join(rng.choice(CHARS) for _ in range(rng.randint(minlen, 8)))

        n = rng.randint(2, 4)
        nodes = [Node(id=f"n{i}", label=lab()) for i in range(n)]
        edges = [Edge(a=f"n{i}", b=f"n{(i + 1) % n}", polarity=rng.choice("+-"))
                 for i in range(n)]
        g = Graph(
            name=lab(1) if rng.random() < 0.8 else "",
            nodes=nodes,
            edges=edges,
            loops=[Loop(id="L", label=lab(), nodes=[f"n{i}" for i in range(n)],
                        kind=rng.choice("RB"))],
            groups=[Group(id="g1", label=lab())] if rng.random() < 0.5 else [],
        )
        text = dumps(g)
        g2 = parse(text)
        assert g2 == g, f"iteration {it}: round trip mismatch\n{text}"
        # dumps is idempotent on its own output
        assert dumps(g2) == text, f"iteration {it}: dumps not idempotent\n{text}"
