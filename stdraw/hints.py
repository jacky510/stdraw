# -*- coding: utf-8 -*-
"""DSL semantic hints (T14) — pipeline consumption + delivered status.

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
            center (cp-sat path) / a centering shift (construct path); ring
            mode lets @main force the main-ring selection instead.
    @pair   recorded on AutoConfig.hints_pairs; same-row pairs gain an
            adjacency term in the placement objective (cp-sat) / are packed
            adjacently (construct path) / rotate the ring into consecutive
            slots (ring mode).

Declaring a hint is not a promise that the delivered layout changed. The
certificate therefore carries a per-hint ``status`` — ``applied`` or
``unapplied`` plus a reason code — and that status is MEASURED, not
asserted: :func:`measure_status` re-runs the same delivery with exactly one
hint entry removed and diffs the delivered artifacts against the delivered
layout: node centers + every route point for @main / @pair, and the
delivered loop-label sequence (the reading order itself) for @order. A hint
the engine reads but that does not move the delivery reports ``unapplied``
with ``no-effect-measured`` — the honest answer an agent needs in order to
stop retrying it. Cross-row ``@pair`` declarations (the two variables are
delivered on different rows, so they cannot be adjacent) report
``cross-row``; a template placement that never consumes the hint reports
``mode-not-eligible``.
"""
from .model import Graph, Hints

APPLIED = "applied"
UNAPPLIED = "unapplied"
UNMEASURED = "unmeasured"

REASON_CROSS_ROW = "cross-row"
REASON_MODE_NOT_ELIGIBLE = "mode-not-eligible"
REASON_NO_EFFECT = "no-effect-measured"
REASON_NOT_MEASURED = "measurement-not-run"

#: Delivered position engines that consume @main / @pair: the layered
#: placement objective (cp-sat) / constructive placement (construct), and
#: ring placement (selection by @main, rotation by @pair). Every other
#: delivered mode is a template placement outside the hint consumers — an
#: unapplied hint there reports ``mode-not-eligible`` instead of blaming the
#: declaration.
HINT_ENGINES = ("cp-sat", "construct", "ring-construct")

#: Measurement caliber recorded in the certificate status block.
STATUS_SIGNATURE = ("delivered node centers + every route point (0.1px); "
                    "@order additionally the delivered loop-label sequence")
STATUS_METHOD = "delivery-ablation"


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


# ── delivered-status measurement (ablation on the delivered geometry) ──

def hint_entries(graph: Graph):
    """Flatten the declared hints into the per-entry measurement units.

    One entry per declaration: each ``@main`` id, the single ``@order`` line
    (it is one declaration, whatever its length), each ``@pair``.
    """
    h = getattr(graph, "hints", None)
    if not h or h.empty():
        return []
    entries = []
    for hid in dict.fromkeys(h.main or []):
        entries.append(("main", hid))
    if h.order:
        entries.append(("order", tuple(dict.fromkeys(h.order))))
    for pair in dict.fromkeys(tuple(p) for p in (h.pairs or [])):
        entries.append(("pairs", pair))
    return entries


def without_entry(graph: Graph, kind: str, value) -> Graph:
    """A NEW Graph with exactly ONE hint declaration removed.

    Everything else (nodes, edges, loops — in the order the caller passed —
    groups, the other hint entries) is carried over unchanged. The caller
    passes a PRISTINE graph (as parsed, before :func:`apply_hints` reordered
    the loops) so the ablated run sees the as-declared state.
    """
    h = graph.hints
    if kind == "main":
        main = [hid for hid in (h.main or []) if hid != value]
        order, pairs = list(h.order or []), list(h.pairs or [])
    elif kind == "order":
        main, order, pairs = list(h.main or []), [], list(h.pairs or [])
    elif kind == "pairs":
        main, order = list(h.main or []), list(h.order or [])
        pairs = [p for p in (h.pairs or []) if tuple(p) != tuple(value)]
    else:                                    # pragma: no cover - internal
        raise ValueError("unknown hint kind: %r" % (kind,))
    return Graph(nodes=list(graph.nodes), edges=list(graph.edges),
                 loops=list(graph.loops), groups=list(graph.groups),
                 name=graph.name,
                 hints=Hints(main=main, order=order, pairs=pairs))


def geometry_signature(v4: dict) -> dict:
    """Delivered-geometry signature: node centers + every route point.

    Coordinates are rounded the way the certificate compares them (ints for
    centers, 0.1px for route points) so float formatting noise cannot
    fabricate an "applied" hint.
    """
    nodes = tuple((v, int(round(p["x"])), int(round(p["y"])))
                  for v, p in sorted((v4.get("nodes") or {}).items()))
    edges = []
    for e in v4.get("edges") or []:
        pts = (e.get("route") or {}).get("points") or []
        edges.append((e.get("a"), e.get("b"), e.get("polarity"),
                      tuple((round(float(q[0]), 1), round(float(q[1]), 1))
                            for q in pts)))
    return {"nodes": nodes, "edges": tuple(edges),
            "viewBox": tuple(v4.get("viewBox") or ())}


def loop_sequence_signature(v4: dict) -> tuple:
    """Delivered loop-label sequence: [(id, x, y)] in DELIVERED order.

    @order declares a reading order, not a geometry: its delivered observable
    is the order (and nudged placement) of the loop-label annotation layer in
    the shipped layout.json. Empty when the delivery carries no loop-label
    annotation — then there is no ordering observable in the artifacts and the
    hint honestly measures unapplied.
    """
    labels = ((v4.get("annotations") or {}).get("loop_labels") or [])
    return tuple((lb.get("id"), int(round(lb.get("x", 0))),
                  int(round(lb.get("y", 0)))) for lb in labels)


def delivery_signature(v4: dict, kind: str = "") -> dict:
    """Delivered observable the given hint kind is measured against.

    @main / @pair: the delivered geometry (node centers + route points).
    @order:      the delivered geometry AND the delivered loop-label
                 sequence (the reading order itself is @order's effect).
    """
    sig = {"geometry": geometry_signature(v4)}
    if kind == "order":
        sig["loop_labels"] = loop_sequence_signature(v4)
    return sig


def _unapplied_reason(kind, engine, rows, value):
    """Reason code for a measured-unapplied entry (classification only —
    the status itself always comes from the ablation)."""
    if kind == "pairs":
        a, b = value
        if a in rows and b in rows and rows[a] != rows[b]:
            return REASON_CROSS_ROW
    if kind in ("main", "pairs") and engine not in HINT_ENGINES:
        return REASON_MODE_NOT_ELIGIBLE
    return REASON_NO_EFFECT


def measure_status(graph: Graph, delivered: dict, run_layout) -> dict:
    """Measure each declared hint against the DELIVERED geometry.

    graph:      the pristine graph (hints as declared, loops as declared) —
                the ablation needs the as-declared state, not the
                @order-reordered pipeline state;
    delivered:  the delivered v4 layout (the artifact that ships);
    run_layout: callable(graph) -> v4, running the SAME delivery recipe the
                caller used (auto-v2 / candidate-v1 / manual replay).

    For every entry the layout is re-run with that single entry removed; the
    entry is ``applied`` iff the delivered observable changes — node centers
    or route points for @main / @pair, or the delivered loop-label sequence
    for @order (see :func:`delivery_signature`). Returns the certificate
    status block (see :func:`status_block`), including the measurement
    caliber.
    """
    entries = hint_entries(graph)
    if not entries:
        return {}
    base = {"main": delivery_signature(delivered, "main"),
            "order": delivery_signature(delivered, "order"),
            "pairs": delivery_signature(delivered, "pairs")}
    engine = (delivered.get("meta") or {}).get("position_engine")
    rows = {v: int(round(p["y"]))
            for v, p in (delivered.get("nodes") or {}).items()}
    out = {"main": [], "order": None, "pairs": [],
           "measurement": {"method": STATUS_METHOD,
                           "signature": STATUS_SIGNATURE,
                           "ablation_runs": 0}}
    applied = unapplied = 0
    for kind, value in entries:
        ablated = run_layout(without_entry(graph, kind, value))
        out["measurement"]["ablation_runs"] += 1
        changed = delivery_signature(ablated, kind) != base[kind]
        if kind == "main":
            rec = {"loop": value}
        elif kind == "order":
            rec = {"ids": list(value)}
        else:
            rec = {"pair": list(value)}
        if changed:
            rec["status"] = APPLIED
            applied += 1
        else:
            rec["status"] = UNAPPLIED
            rec["reason"] = _unapplied_reason(kind, engine, rows, value)
            unapplied += 1
        if kind == "order":
            out["order"] = rec
        else:
            out[kind].append(rec)
    out["measurement"]["applied"] = applied
    out["measurement"]["unapplied"] = unapplied
    return out


def status_block(graph: Graph, status=None) -> dict:
    """Certificate-facing ``hints.status`` block, one row per declaration.

    status: a dict returned by :func:`measure_status`. When it is absent —
    a certificate built outside the CLI delivery path, where no ablation ran
    — every entry is honestly ``unmeasured`` with reason
    ``measurement-not-run``. A status is never inferred from "the engine
    reads this field": that would be self-certification, exactly the T14
    gap this block closes.
    """
    if status:
        return status
    h = getattr(graph, "hints", None)
    if not h or h.empty():
        return {}
    out = {"main": [], "order": None, "pairs": [],
           "measurement": {"method": "none", "ablation_runs": 0}}
    for hid in dict.fromkeys(h.main or []):
        out["main"].append({"loop": hid, "status": UNMEASURED,
                            "reason": REASON_NOT_MEASURED})
    if h.order:
        out["order"] = {"ids": list(dict.fromkeys(h.order)),
                        "status": UNMEASURED,
                        "reason": REASON_NOT_MEASURED}
    for pair in dict.fromkeys(tuple(p) for p in (h.pairs or [])):
        out["pairs"].append({"pair": list(pair), "status": UNMEASURED,
                             "reason": REASON_NOT_MEASURED})
    return out
