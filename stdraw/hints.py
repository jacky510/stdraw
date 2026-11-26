# -*- coding: utf-8 -*-
"""DSL semantic hints (T14) — pipeline consumption.

Hints are layout INTENT declared in the DSL (see stdraw/model.py Hints and
docs/agent-interface.md):

    @main R1        main loop(s) the engine should center
    @order R1,B1,R2 loop reading order
    @pair a,b       two variables that should sit adjacent

This module applies the hints to a Graph BEFORE the pipeline runs
(audit -> layout -> certificate). Applying is idempotent and returns a NEW
Graph — the input model is never mutated. Graphs without hints come back
unchanged (byte-identical pipeline output, by construction).

Effects (deterministic, gated on hint presence — a hints-free graph never
enters any hinted code path):

    @order  graph.loops is reordered to the declared sequence (loops not
            listed keep their relative order, appended after). The loop
            audit listing, the loop-arc scope and the annotation layer all
            follow this sequence, so this is the reading-order effect.
    @main   recorded on AutoConfig.hints_main; the placement objective adds
            a centering term pulling the main-loop nodes toward the canvas
            center (cp-sat path) / a centering shift (construct path).
    @pair   recorded on AutoConfig.hints_pairs; same-row pairs gain an
            adjacency term in the placement objective (cp-sat) / are packed
            adjacently (construct path). Cross-row pairs cannot be adjacent
            and are reported as unapplied (honest boundary).
"""
from .model import Graph


def has_hints(graph: Graph) -> bool:
    return bool(getattr(graph, "hints", None)) and not graph.hints.empty()


def apply_hints(graph: Graph):
    """Apply @order (loop reading order). Returns (graph2, applied dict).

    graph2 is a NEW Graph when hints exist, else the SAME object. Idempotent.
    """
    h = getattr(graph, "hints", None)
    if not h or h.empty():
        return graph, {}
    applied = {}
    loops = list(graph.loops)
    if h.order:
        by_id = {lp.id: lp for lp in loops}
        listed = [i for i in h.order if i in by_id]
        listed_set = set(listed)
        loops = [by_id[i] for i in listed] + \
                [lp for lp in loops if lp.id not in listed_set]
        applied["order"] = ("loops reordered to the @order reading sequence; "
                            "%d of %d declared loops listed" % (len(listed), len(loops)))
    g2 = Graph(nodes=list(graph.nodes), edges=list(graph.edges),
               loops=loops, groups=list(graph.groups), name=graph.name,
               hints=graph.hints)
    return g2, applied
