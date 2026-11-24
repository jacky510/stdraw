# -*- coding: utf-8 -*-
"""Regression: loop R/B parity must be directional (cycle_kind).

Pre-fix bug: cycle_kind matched both (a,b) and (b,a) when counting
negative-polarity edges per hop, so opposite-direction edges were folded
into the same hop and R/B parity came out wrong on mixed-direction loops.
"""
from stdraw.dsl import parse
from stdraw.loops import loops_audit


def _cycles_by_nodes(rep):
    # extra_cycles carries sorted(cyc) as the display key
    return {tuple(c["nodes"]): (c["kind"], c["neg_edges"])
            for c in rep["extra_cycles"]}


def test_cycle_kind_is_directional_two_node_loop():
    g = parse("""
graph "t1"
var a "a"
var b "b"
var c "c"
a -> + b @loops L1
b -> - a @loops L1
b -> + c @loops L1
c -> + a @loops L1
loop L1 "L1" "R" [a, b, c]
""")
    rep = loops_audit(g)
    cyc = _cycles_by_nodes(rep)
    # a->b->a walks + then -: 1 negative = B (pre-fix: R with negs=2)
    assert cyc[("a", "b")] == ("B", 1)
    # a->b->c->a walks + + +: 0 negatives = R (pre-fix: B with negs=1)
    assert cyc[("a", "b", "c")] == ("R", 0)


def test_cycle_kind_fixes_that_fail_subgraph():
    # Source-doc reproduction: p->f->c->q->p must grade R (2 negatives:
    # c->-q and q->-p); pre-fix it graded B because hop p->f also folded in
    # the opposite-direction f->-p edge.
    g = parse("""
graph "ftf"
var p "problem"
var f "fix"
var c "consequence"
var q "side effect"
p -> + f @loops FTF
f -> - p @loops PF
f -> + c @loops FTF
c -> - q @loops FTF
q -> - p @loops FTF
loop FTF "fixes that fail" "R" [p, f, c, q]
loop PF "pf" "B" [p, f]
""")
    rep = loops_audit(g)
    cyc = _cycles_by_nodes(rep)
    assert cyc[("c", "f", "p", "q")] == ("R", 2)
    assert cyc[("f", "p")] == ("B", 1)


def test_cycle_kind_all_negative_directions():
    # every edge negative along the walked direction: parity odd -> B
    g = parse("""
graph "allneg"
var a "a"
var b "b"
var c "c"
a -> - b @loops L
b -> - c @loops L
c -> - a @loops L
loop L "L" "B" [a, b, c]
""")
    rep = loops_audit(g)
    cyc = _cycles_by_nodes(rep)
    assert cyc[("a", "b", "c")] == ("B", 3)
