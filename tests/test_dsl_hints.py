# -*- coding: utf-8 -*-
"""DSL semantic hints (T14): grammar, round-trip property (T4-style), and
validation.

Property: parse(dumps(g)) == g for randomly generated hint combinations
(fixed seed — no RNG in delivered outputs, tests seed explicitly).
Validation: hints referencing undeclared loops/variables are rejected;
malformed directive lines raise a parse error.
"""
import random

import pytest

from stdraw.dsl import dumps, parse
from stdraw.model import Edge, Graph, Hints, Loop, Node

# fixed corpus of loop ids / var ids the property generator draws from
LOOP_IDS = ["R1", "B1", "R2"]
VAR_IDS = ["a", "b", "c", "d"]


def _base_graph(rng):
    nodes = [Node(id=v, label=f"V {v.upper()}") for v in VAR_IDS]
    edges = [Edge(a="a", b="b", polarity="+", loops=["R1"]),
             Edge(a="b", b="c", polarity="-", loops=["R1"]),
             Edge(a="c", b="a", polarity="+", loops=["R1"]),
             Edge(a="c", b="d", polarity="+", loops=["B1", "R2"]),
             Edge(a="d", b="a", polarity="-", loops=["B1", "R2"])]
    loops = [Loop(id="R1", label="main", nodes=["a", "b", "c"], kind="B"),
             Loop(id="B1", label="balance", nodes=["c", "d", "a"], kind="B"),
             Loop(id="R2", label="side", nodes=["c", "d", "a"], kind="B")]
    return Graph(name="prop", nodes=nodes, edges=edges, loops=loops)


def _random_hints(rng):
    h = Hints()
    if rng.random() < 0.7:
        k = rng.randint(1, len(LOOP_IDS))
        h.main = rng.sample(LOOP_IDS, k)
    if rng.random() < 0.7:
        h.order = rng.sample(LOOP_IDS, k=rng.randint(1, len(LOOP_IDS)))
    if rng.random() < 0.7:
        for _ in range(rng.randint(1, 2)):
            a, b = rng.sample(VAR_IDS, 2)
            h.pairs.append((a, b))
    return h


def test_property_round_trip_random_hint_combinations():
    """T4-style property: parse(dumps(g)) == g over 200 seeded hint combos."""
    rng = random.Random(20261126)
    for i in range(200):
        g = _base_graph(rng)
        g.hints = _random_hints(rng)
        text = dumps(g)
        g2 = parse(text)
        assert g2 == g, (i, text)


def test_round_trip_empty_hints_bytes_unchanged():
    g = _base_graph(random.Random(1))
    g.hints = Hints()
    text = dumps(g)
    assert "@main" not in text and "@order" not in text and "@pair" not in text
    assert parse(text) == g


def test_directives_any_order_parse_canonical_dump():
    raw = """
graph "t"
var a "A"
var b "B"
var c "C"
a -> + b @loops R1
b -> - c @loops R1
c -> + a @loops R1
loop R1 "r" "R" [a, b, c]
@pair a,b
@order R1
@main R1
"""
    g = parse(raw)
    assert g.hints.main == ["R1"]
    assert g.hints.order == ["R1"]
    assert g.hints.pairs == [("a", "b")]
    g2 = parse(dumps(g))
    assert g2 == g
    # canonical dump order: @main lines, then @order, then @pair
    tail = [ln for ln in dumps(g).splitlines() if ln.startswith("@")]
    assert tail == ["@main R1", "@order R1", "@pair a,b"]


def test_multi_main_and_pair_lines_accumulate():
    raw = """
graph "t"
var a "A"
var b "B"
var c "C"
a -> + b @loops R1
b -> - c @loops R1
a -> - c @loops B1
c -> + a @loops R1,B1
loop R1 "r" "R" [a, b, c]
loop B1 "b" "B" [a, c]
@main R1
@main B1
@pair a,b
@pair b,c
"""
    g = parse(raw)
    assert g.hints.main == ["R1", "B1"]
    assert g.hints.pairs == [("a", "b"), ("b", "c")]
    assert parse(dumps(g)) == g


def test_comma_list_directives():
    raw = """
graph "t"
var a "A"
var b "B"
var c "C"
a -> + b @loops R1
b -> - c @loops R1
c -> + a @loops R1
loop R1 "r" "R" [a, b, c]
@main R1
@order R1
"""
    g = parse(raw)
    assert g.hints.main == ["R1"] and g.hints.order == ["R1"]
    assert parse(dumps(g)) == g


def test_undeclared_references_rejected():
    base = """
graph "t"
var a "A"
var b "B"
a -> + b @loops R1
b -> - a @loops R1
loop R1 "r" "R" [a, b]
"""
    g = parse(base)
    g.hints.main = ["ZZ"]
    assert "@main references undeclared loop ZZ" in "\n".join(g.validate())
    g.hints.main = []
    g.hints.order = ["QQ"]
    assert "@order references undeclared loop QQ" in "\n".join(g.validate())
    g.hints.order = []
    g.hints.pairs = [("a", "zz")]
    assert "@pair references undeclared variable: a,zz" in "\n".join(g.validate())
    g.hints.pairs = [("a", "a")]
    assert "@pair names the same variable twice: a" in "\n".join(g.validate())


def test_malformed_directive_lines_rejected():
    base = """
graph "t"
var a "A"
var b "B"
a -> + b @loops R1
b -> - a @loops R1
loop R1 "r" "R" [a, b]
@pair a
"""
    with pytest.raises(ValueError):
        parse(base)
    with pytest.raises(ValueError):
        parse(base.replace("@pair a", "@unknown hint"))
    with pytest.raises(ValueError):
        parse(base.replace("@pair a", "@pair a,b,c"))


def test_json_model_round_trip_with_and_without_hints():
    g = _base_graph(random.Random(2))
    g.hints = Hints(main=["R1"], order=["B1", "R1"], pairs=[("a", "b")])
    d = g.to_dict()
    assert d["hints"] == {"main": ["R1"], "order": ["B1", "R1"],
                          "pairs": [["a", "b"]]}
    assert Graph.from_dict(d) == g
    g0 = _base_graph(random.Random(2))
    assert "hints" not in g0.to_dict()          # absent key = historical bytes
    assert Graph.from_dict(g0.to_dict()) == g0
