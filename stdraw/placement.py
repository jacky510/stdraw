# -*- coding: utf-8 -*-
"""Slot-discretized placement layer (WS2 item 6): structure-detection-driven regular slots.

Design (same source as docs/crossing-exact.md §6):

- **Structure-driven slot shapes**:
    cycle graph -> regular k-gon slots (angles evenly split as i*2pi/k;
               cycle-order assignment puts all ring edges on the convex hull
               -> crossings = 0 by construction; regular-polygon deviation = 0
               by construction) — constructive, no solver needed;
    chain graph -> collinear equidistant slots (straightness = 1 by
               construction; geometric overlap of adjacent edges is resolved
               downstream by the routing layer with arcs; the center-caliber
               crossing/regularity metrics are unaffected) — constructive;
    general  -> layered row slots + CP-SAT (the only branch that needs a solver).
- **CP-SAT branch hard constraints** (violation = infeasible):
    1) in-row card gap >= min_gap (headroom over the >=16px gate);
    2) boxes must not press lines (with 1px headroom): the interpolated x of a
       cross-row edge at intermediate rows stays >= CLEARANCE from unrelated
       box edges (exact linearization for t in {1/2,1/3,2/3,3/4,1/4},
       conservative two-sided constraints for the other interpolation factors);
    3) inside the viewBox: slot-domain bounding.
- **CP-SAT objective**: min 60*sum(crossings) + sum(|dx|) (crossings primary,
   in-row evenness secondary — isomorphic to the auto-v2 placement objective).
- **Determinism**: num_workers=1 + seed 42; no wall-clock limit (a wall-clock
   limit drifts with load).
- **Delivery discipline**: after coordinates are returned the caller re-runs the
  metrics/check hard gates; any violation
  falls back to the auto-v2 constructive path — this layer never delivers
  while injured.
- **Honest boundary**: "regularity-optimal" for the cycle/chain branches is
  relative to the slot-model class
  (regular-polygon slots + the declared cycle-order assignment), not a proof
  of optimality over all permutations; the crossing objective of the general
  branch is the conservative row-slot caliber (close proximity not counted),
  and only solving to OPTIMAL makes it optimal for that caliber.
"""
import math

SLOT = 24
CLEARANCE = 16 + 1     # 16px hard gate + 1px headroom


def has_solver():
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        return True
    except Exception:
        return False


def place(graph, widths, rows=None, card_h=44, pitch=80, top=92, margin=44,
          min_gap=18, target_w=1280):
    """Slot placement entry point. Returns {x, y, viewBox, structure, engine} or None (fallback).

    graph: stdraw.model.Graph; widths: {v: card width}; rows: layered rows (used by general).
    """
    from . import regularity
    nodes = graph.node_ids()
    edges = [(e.a, e.b) for e in graph.edges]
    st = regularity.detect_structure(graph)
    n = len(nodes)

    if st["kind"] == "cycle" and len(st["cycle_nodes"]) == 1 \
            and n == len(st["cycle_nodes"][0]) and n >= 3:
        return _place_cycle(st["cycle_nodes"][0], target_w)
    if st["kind"] == "chain" and len(st["chain_nodes"]) == 1 \
            and n == len(st["chain_nodes"][0]) and n >= 2:
        return _place_chain(st["chain_nodes"][0], widths, margin)
    if has_solver():
        return _place_layered(graph, nodes, edges, widths, rows, pitch,
                              top, margin, min_gap, target_w)
    return None


def _place_cycle(cyc, target_w):
    """Regular k-gon slots (angles evenly split, cycle-order assignment).
    Crossings 0 and deviation 0 hold by construction.

    Quantization uses a 2px grid (the delivered-coordinate caliber): coarse
    24px quantization visibly distorts the regular polygon and inflates
    radial/angular CV — regularity metrics run on delivered coordinates, so
    the quantization must be fine enough."""
    k = len(cyc)
    radius = max(150, min(420, k * 34))
    cx = max(k * 48, target_w) // 2
    cy = radius + 90
    x, y = {}, {}
    for i, v in enumerate(cyc):
        ang = 2 * math.pi * i / k - math.pi / 2
        x[v] = int(round((cx + radius * math.cos(ang)) / 2) * 2)
        y[v] = int(round((cy + radius * math.sin(ang)) / 2) * 2)
    allv = list(x.values()) + list(y.values())
    W = max(allv) + 48
    H = max(y.values()) + 48
    return {"x": x, "y": y, "viewBox": [0, 0, W, H],
            "structure": "cycle", "engine": "construct-regular-polygon"}


def _place_chain(chain, widths, margin):
    """Collinear equidistant slots (declared chain order). Straightness 1 holds by construction."""
    cur = max(margin, SLOT * 2)
    xs, ys = {}, {}
    for v in chain:
        xs[v] = cur
        ys[v] = 120
        cur += max(SLOT * 4, int((widths.get(v, 96) + 48) / SLOT) * SLOT)
    return {"x": xs, "y": ys, "viewBox": [0, 0, cur + 48, 240],
            "structure": "chain", "engine": "construct-collinear"}


def _place_layered(graph, nodes, edges, widths, rows, pitch, top, margin,
                   min_gap, target_w):
    """Layered row slots + CP-SAT (the only branch that needs a solver)."""
    if not rows:
        return None
    from ortools.sat.python import cp_model
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    n_slots = int(target_w // SLOT) + 1
    m = cp_model.CpModel()
    xs = {v: m.NewIntVar(margin // SLOT, n_slots - 1, f"sx_{v}") for v in nodes}

    # Hard constraint 1: in-row card gap (slot scale)
    for vs in rows:
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                u, w = vs[i], vs[j]
                need = int(math.ceil((widths[u] + widths[w]) / 2.0 + min_gap)
                           / SLOT) + 1
                d = m.NewIntVar(0, n_slots, "")
                m.AddAbsEquality(d, xs[u] - xs[w])
                m.Add(d >= need)

    # Hard constraint 2: cross-row edges must not press unrelated boxes (with 1px headroom)
    for (a, b) in edges:
        ra, rb = row_of[a], row_of[b]
        if ra == rb:
            continue
        lo, hi = min(ra, rb), max(ra, rb)
        for v in nodes:
            rv = row_of[v]
            if rv <= lo or rv >= hi:
                continue
            t = (rv - ra) / (rb - ra)
            xv = xs[v]
            denom = None
            for q in (2, 3, 4):
                if abs(t * q - round(t * q)) < 1e-9:
                    denom, p_ = q, round(t * q)
                    break
            slack = int(math.ceil(CLEARANCE / SLOT)) + 1
            if denom:
                # x_at = xa + (xb - xa)*p_/denom; multiply both sides of the constraint by denom to integerize
                left = m.NewBoolVar("")
                right = m.NewBoolVar("")
                expr = denom * xs[a] + p_ * (xs[b] - xs[a])
                m.Add(expr <= denom * (xv - slack)).OnlyEnforceIf(left)
                m.Add(expr >= denom * (xv + slack)).OnlyEnforceIf(right)
                m.AddBoolOr([left, right])
            else:
                left_a = m.NewBoolVar("")
                right_a = m.NewBoolVar("")
                m.Add(xs[a] <= xv - slack).OnlyEnforceIf(left_a)
                m.Add(xs[a] >= xv + slack).OnlyEnforceIf(right_a)
                m.AddBoolOr([left_a, right_a])
                left_b = m.NewBoolVar("")
                right_b = m.NewBoolVar("")
                m.Add(xs[b] <= xv - slack).OnlyEnforceIf(left_b)
                m.Add(xs[b] >= xv + slack).OnlyEnforceIf(right_b)
                m.AddBoolOr([left_b, right_b])

    # Objective: crossings (row-interval interleaving + reversed endpoint relative order, conservative, close proximity not counted) + sum(|dx|)
    einfo = []
    for (a, b) in edges:
        ra, rb = row_of[a], row_of[b]
        einfo.append((a, b, min(ra, rb), max(ra, rb)))
    cross_terms = []
    for i in range(len(einfo)):
        a1, b1, l1, h1 = einfo[i]
        for j in range(i + 1, len(einfo)):
            a2, b2, l2, h2 = einfo[j]
            if {a1, b1} & {a2, b2}:
                continue
            if min(h1, h2) - max(l1, l2) < 1:
                continue
            top_a = a1 if row_of[a1] < row_of[b1] else b1
            bot_a = b1 if row_of[a1] < row_of[b1] else a1
            top_b = a2 if row_of[a2] < row_of[b2] else b2
            bot_b = b2 if row_of[a2] < row_of[b2] else a2
            if row_of[top_a] == row_of[top_b] or row_of[bot_a] == row_of[bot_b]:
                continue
            p = m.NewBoolVar("")
            q = m.NewBoolVar("")
            m.Add(xs[top_a] <= xs[top_b] - 1).OnlyEnforceIf(p)
            m.Add(xs[top_a] >= xs[top_b]).OnlyEnforceIf(p.Not())
            m.Add(xs[bot_a] <= xs[bot_b] - 1).OnlyEnforceIf(q)
            m.Add(xs[bot_a] >= xs[bot_b]).OnlyEnforceIf(q.Not())
            c = m.NewBoolVar("")
            m.Add(p + q == 1).OnlyEnforceIf(c)
            m.Add(p + q != 1).OnlyEnforceIf(c.Not())
            cross_terms.append(c)
    lens = []
    for (a, b) in edges:
        d = m.NewIntVar(0, n_slots, "")
        m.AddAbsEquality(d, xs[a] - xs[b])
        lens.append(d)
    m.Minimize(60 * sum(cross_terms) + sum(lens))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1      # determinism iron rule
    solver.parameters.random_seed = 42     # no wall-clock limit: time limits drift with load
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    x = {v: int(solver.Value(xs[v])) * SLOT for v in nodes}
    y = {v: top + row_of[v] * pitch for v in nodes}
    W = max(x.values()) + max(widths.values()) // 2 + 48
    H = top + (max(row_of.values()) + 1) * pitch + 48
    return {"x": x, "y": y, "viewBox": [0, 0, W, H],
            "structure": "layered", "engine": "cp-sat",
            "status": solver.StatusName(st)}
