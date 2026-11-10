# -*- coding: utf-8 -*-
"""auto layout layer (② objective-function rework): layering + order/position optimization + crossing count in the objective + regularity terms.

Differences from ortho-v1 (planar.py, plane-embedding construction, used to pin
production behavior):
  - No planarity requirement: any CLD can be laid out, and the crossing count
    is explicitly minimized as a **first-class term of the objective function**;
  - Objective = crossing count (weight 60) + sum(|dx|) edge-length term
    (regularity/compactness) + grid snapping (regularity);
  - Placement can be refined with OR-Tools CP-SAT (`pip install stdraw[solver]`);
    when not installed it degrades gracefully
    to the deterministic constructive method (barycenter order + even
    placement) - full functionality, quality falls back to the constructive tier;
  - Routing is delegated to routing.Router (straight/arc first-class, boxes do
    not press lines, 16px clearance hard gate).

Determinism: CP-SAT fixed at num_workers=1 + random_seed; the constructive
method has no RNG. Same input, same output.
"""
import math
import sys
from collections import defaultdict

from . import textmetrics
from . import timing as _timing
from .visibility import reset_caches as _reset_route_caches
from .anchors import ANCHOR_IDS, standard_anchors as _standard_anchors
from .routing import (Router, CLEARANCE, SIDE_MARGIN, PAIR_SEP_W,
                      ANCHOR_MIN_DEG, border_point)
from .anchors import nearest_anchor as _nearest_anchor

# ref-scrubbed finalize (approved 2026-11-09): edge/node density at or
# above which anchor_snap's revert probe also counts unplaceable endpoints
# as a regression (whole-snap deferral, recorded on the certificate).  Below
# the threshold the probe still reverts on a measured crossings/coincidence
# worsening (T5, all densities), but endpoint failures neither revert nor
# defer -- see the snap block in layout().
# Measured basis: random n10 corpus E/N = 1.60 (dense; n10-i05
# regresses: crossings 0->2 / coincidence / 1 endpoint unanchored), classic
# corpus <= 1.62 (classic-cld snaps clean) -- the probe keeps snapping any
# dense graph that passes the hard gates with zero regressions.
ANCHOR_SNAP_DENSE_E_OVER_N = 1.6


def _clone_route(rt):
    """Deep copy of one route dict (points/ctrl/vg_corners/vg_fillets only --
    the fields anchor_snap mutates; used by the probe revert path)."""
    c = dict(rt)
    c["points"] = [list(p) for p in rt["points"]]
    if rt.get("ua_ends") is not None:
        c["ua_ends"] = dict(rt["ua_ends"])
    if rt.get("ctrl") is not None:
        c["ctrl"] = list(rt["ctrl"])
    if rt.get("vg_corners") is not None:
        c["vg_corners"] = [list(q) for q in rt["vg_corners"]]
    if rt.get("vg_fillets") is not None:
        c["vg_fillets"] = [dict(f) for f in rt["vg_fillets"]]
    return c


class AutoConfig:
    fs_title: float = 12.5
    fs_value: float = 14.0
    card_min_w: int = 96
    card_h: int = 44
    pitch: int = 80            # row pitch: card 44 + inter-row corridor 36 (the source of clearance for detour lanes)
    top: int = 92              # first-row center y (clearance from the parking strip >=18px: 28+22=50 -> 92-22=70)
    park_y: int = 28           # parking-strip center y for isolated nodes
    margin: int = 44
    min_gap: int = 18          # card gap (headroom over the >=16 gate)
    clearance: int = 16        # edge-box clearance hard gate (fed into router scoring)
    grid: int = 8
    snap_regular: int = 24     # regular snap for simple graphs (<=10 nodes)
    # v0.7.7: extra per-side padding for the value (second) text line.
    # Default None = historical behavior (pad-4 baseline) byte-for-byte;
    # opt in for long ticker/price value strings via CLI --value-pad.
    value_pad_extra: float = None
    # v0.7.11 deterministic layout constraints (comb-bilateral; both default
    # None = engine-decided order/side byte-for-byte, the deterministic
    # initial-render contract is untouched):
    # - column_order: explicit node-id list fixing the source-column internal
    #   order (top -> bottom). Hard constraint applied at component level:
    #   components are ordered by the best (smallest) rank of their members,
    #   intra-component DFS order is preserved (pendant trees stay contiguous),
    #   unlisted column nodes keep engine order after the listed ones.
    # - hub_side: {node_id: "left"|"right"} for the comb's bilateral hubs;
    #   a single explicit side is enough to fix the assignment, contradicting
    #   specs degrade deterministically (first left wins, then first right).
    column_order: list = None
    hub_side: dict = None
    target_w: int = 1280
    target_h: int = 680
    aspect_min: float = 1.5


def _cycle_break(nodes, edges):
    """DFS cycle breaking (deterministic via declaration order). Returns (set of edges reversed to point backward, DAG edge list)."""
    adj = defaultdict(list)
    for i, (a, b) in enumerate(edges):
        adj[a].append((b, i))
    state = {}
    reversed_idx = set()
    def dfs(v):
        state[v] = 1
        for w, i in adj[v]:
            if state.get(w, 0) == 0:
                dfs(w)
            elif state.get(w, 0) == 1:
                reversed_idx.add(i)   # back edge: treated as w->v during layering
        state[v] = 2
    for v in nodes:
        if state.get(v, 0) == 0:
            dfs(v)
    dag = []
    for i, (a, b) in enumerate(edges):
        dag.append((b, a) if i in reversed_idx else (a, b))
    return reversed_idx, dag


def _layers(nodes, dag):
    """DAG longest-path layering + empty-layer compression."""
    preds = defaultdict(list)
    outs = defaultdict(list)
    for a, b in dag:
        preds[b].append(a)
        outs[a].append(b)
    layer = {}
    def calc(v):
        if v in layer:
            return layer[v]
        layer[v] = 0                      # cycle guard (theoretically acyclic, just in case)
        lv = 0 if not preds[v] else 1 + max(calc(u) for u in preds[v])
        layer[v] = lv
        return lv
    for v in nodes:
        calc(v)
    return layer


def _has_solver():
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        return True
    except Exception:
        return False


def _solve_positions(nodes, rows, widths, cfg: AutoConfig, linestyle, edges):
    """Placement solver: CP-SAT available -> crossing-count + edge-length + regularity objective; otherwise the constructive method.

    Returns ({v: x_px}, engine, extra_meta) (box centers). y is decided by rows.
    """
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    # minimal total width per row -> content width
    row_w = {r: sum(widths[v] for v in vs) + cfg.min_gap * (len(vs) + 1)
             for r, vs in enumerate(rows)}
    content_w = max(row_w.values()) + 2 * cfg.margin
    max_x = int(content_w)

    # edge endpoint row numbers (comparing crossings on the original y order would need real y; row numbers suffice)
    einfo = []
    for (a, b) in edges:
        einfo.append((a, b, row_of[a], row_of[b]))

    # WS5 scalability: proving CP-SAT global optimality does not scale to large graphs (after O(m^2) booleanization of crossing pairs, proof
    # time explodes with n - measured on n20: 5min+ without completing the proof). Switched to a **deterministic time budget**
    # (max_deterministic_time, OR-Tools' dedicated reproducibility caliber: counts operations instead of wall clock, so the same version
    # and input reach the same incumbent on any machine). The budget is generous: small graphs (<=10 nodes, the entire classic domain)
    # still prove OPTIMAL within budget, output byte-for-byte identical to the unbudgeted version; only the new n>10 domain is budget-bound
    # (FEASIBLE labeled honestly, never passed off as optimal).
    det_budget = CP_SAT_DET_BUDGET if len(nodes) > 10 else None

    if _has_solver():
        snap = cfg.snap_regular if len(nodes) <= 10 else cfg.grid
        res, status = _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, snap,
                                       det_budget)
        if res is None and snap != cfg.grid:      # 24px snap infeasible -> fall back to the 8px grid
            res, status = _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x,
                                           cfg.grid, det_budget)
        if res is not None:
            extra = {}
            if det_budget is not None:
                # only the budgeted path (n>10) writes meta: the small-graph path keeps historical output byte-for-byte unchanged
                extra = {"solver_status": status,
                         "solver_det_budget": det_budget}
            return res, "cp-sat", extra
    return _construct_positions(nodes, rows, widths, cfg, edges), "construct", {}


CP_SAT_DET_BUDGET = 8.0   # deterministic time budget (det units; measured on n20: ~=17s wall clock per 8 det)




def _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, grid, det_budget=None):
    """CP-SAT: decision variables = box-center x; objective = crossing count + sum(|dx|); constraints = clearance/grid/bounds.

    det_budget: deterministic time budget (max_deterministic_time, the
    operation-count caliber) - past budget, take the current best incumbent
    (FEASIBLE) and stop proving optimality. None = no budget (the historical
    behavior: solve to optimality). Returns (solution or None, "optimal"/"feasible").
    """
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return None, "no-solver"
    m = cp_model.CpModel()
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    xs = {v: m.NewIntVar(cfg.margin, max_x - cfg.margin, f"x_{v}") for v in nodes}
    for v in nodes:
        m.AddModuloEquality(0, xs[v], grid)
    # same-row clearance (center distance >= half the summed widths + gap)
    for vs in rows:
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                u, w = vs[i], vs[j]
                need = int(math.ceil((widths[u] + widths[w]) / 2.0) + cfg.min_gap)
                d = m.NewIntVar(0, max_x, "")
                m.AddAbsEquality(d, xs[u] - xs[w])
                m.Add(d >= need)
    # crossing objective: two independent edges with interleaved row intervals -> reversed endpoint order means a crossing (conservative: close proximity not counted)
    cross_vars = []
    for i in range(len(einfo)):
        a1, b1, r11, r12 = einfo[i]
        for j in range(i + 1, len(einfo)):
            a2, b2, r21, r22 = einfo[j]
            if {a1, b1} & {a2, b2}:
                continue
            lo1, hi1 = min(r11, r12), max(r11, r12)
            lo2, hi2 = min(r21, r22), max(r21, r22)
            if min(hi1, hi2) - max(lo1, lo2) < 1:
                continue
            # compare the relative order of the two endpoints (at the lowest/highest row of each side)
            top_e = a1 if r11 < r12 else b1
            bot_e = b1 if r11 < r12 else a1
            top_f = a2 if r21 < r22 else b2
            bot_f = b2 if r21 < r22 else a2
            if row_of[top_e] == row_of[top_f] or row_of[bot_e] == row_of[bot_f]:
                continue
            p = m.NewBoolVar("")
            q = m.NewBoolVar("")
            m.Add(xs[top_e] <= xs[top_f] - 4).OnlyEnforceIf(p)
            m.Add(xs[top_e] >= xs[top_f]).OnlyEnforceIf(p.Not())
            m.Add(xs[bot_e] <= xs[bot_f] - 4).OnlyEnforceIf(q)
            m.Add(xs[bot_e] >= xs[bot_f]).OnlyEnforceIf(q.Not())
            c = m.NewBoolVar("")
            m.Add(p + q == 1).OnlyEnforceIf(c)
            m.Add(p + q != 1).OnlyEnforceIf(c.Not())
            cross_vars.append(c)
    # edge-length term |dx|
    lens = []
    for a, b, _, _ in einfo:
        d = m.NewIntVar(0, max_x, "")
        m.AddAbsEquality(d, xs[a] - xs[b])
        lens.append(d)
    m.Minimize(60 * sum(cross_vars) + sum(lens))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1        # determinism iron rule
    solver.parameters.random_seed = 42
    # A wall-clock limit drifts with machine load (breaking determinism) - the budget uses only the deterministic-time caliber;
    # no budget = solve to optimality (historical behavior; small graphs were fast anyway)
    if det_budget is not None:
        solver.parameters.max_deterministic_time = det_budget
    st = solver.Solve(m)
    if st == cp_model.OPTIMAL:
        return {v: int(solver.Value(xs[v])) for v in nodes}, "optimal"
    if st == cp_model.FEASIBLE:
        return {v: int(solver.Value(xs[v])) for v in nodes}, "feasible"
    return None, "no-solution"


def _construct_positions(nodes, rows, widths, cfg, edges):
    """Constructive method: barycenter order + even in-row placement + row centering (deterministic)."""
    pos = {}
    order = {}
    for r, vs in enumerate(rows):
        order[r] = sorted(vs)
    # simple barycenter sweeps (3 rounds, alternating up/down)
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    neigh = defaultdict(list)
    for (a, b) in edges:
        neigh[a].append(b)
        neigh[b].append(a)
    for _ in range(3):
        for r in list(range(len(rows))) + list(range(len(rows) - 1, -1, -1)):
            vs = rows[r]
            key = {}
            for v in vs:
                ups = [order[row_of[u]].index(u) if u in order[row_of[u]] else 0
                       for u in neigh[v]]
                key[v] = (sum(ups) / len(ups)) if ups else order[r].index(v)
            order[r] = sorted(vs, key=lambda v: (key[v], v))
    for r, vs in enumerate(rows):
        xs, cursor = [], 0
        for v in order[r]:
            xs.append(cursor + widths[v] / 2 + cfg.min_gap)
            cursor += widths[v] + cfg.min_gap * 2
        total = xs[-1] + widths[vs[-1]] / 2 + cfg.min_gap
        shift = (max(0, _content_w(rows, widths, cfg)) - total) / 2
        for v, x in zip(vs, xs):
            pos[v] = int(round((x + shift) / cfg.grid)) * cfg.grid
    return pos


def _content_w(rows, widths, cfg):
    return max((sum(widths[v] for v in vs) + cfg.min_gap * (len(vs) + 1))
               for vs in rows) + 2 * cfg.margin


def _route_total(nodes_px, edges, cfg, hard_gates=False, quality=False):
    """Routing ground-truth total cost: a weighted sum of press/clearance/crossing/coincidence/edge length (the layout layer's true objective function).

    hard_gates: hard clearance/anchor penalties (1500 per violation). Default
    False - the historical scoring caliber stays unchanged
    (polish trajectories of the classic domain and existing passing cases stay
    byte-for-byte); enabled only on the gated reorder path of routing-quality
    rework. quality: the Router expands the stair candidate pool, likewise
    gated path only.
    ref-scrubbed breathing room (14 hand-drawn samples: min_card_gap averaged
    +35.8px): adds a soft penalty targeting a 36px
    card gap (penalized 8x by the shortfall), raising the gap weight to the
    first tier;
    no hard gate (crowding is caught by the existing clearance gate).
    """
    from .metrics import rect_gap
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch, quality=quality)
    routes = router.route_all()
    eset = set(edges)
    total = 0.0
    clr_hard = 0
    ang_hard = 0
    for i, info in routes.items():
        a, b = edges[i]
        clr = info.get("min_clear")
        clr_pen = (30 * max(0.0, cfg.clearance - clr)) if clr is not None else 30 * cfg.clearance
        if (b, a) in eset:      # F1: tightened mutual-pair clearance, same caliber as _evaluate
            clr_pen += 120 * (max(0.0, cfg.clearance - clr) if clr is not None
                              else cfg.clearance)
        if hard_gates and clr is not None and clr < cfg.clearance - 1e-6:
            clr_hard += 1
        if hard_gates and min(info.get("ang_a", ANCHOR_MIN_DEG),
                              info.get("ang_b", ANCHOR_MIN_DEG)) < ANCHOR_MIN_DEG - 1e-9:
            ang_hard += 1
        total += (4000 * info.get("press", 0) + 40 * info.get("cross", 0) +
                  PAIR_SEP_W * info.get("sep_def", 0.0) +
                  (200.0 if info.get("kind") == "wrap" else 0.0) +
                  clr_pen +
                  0.01 * sum(math.dist(info["points"][k], info["points"][k + 1])
                             for k in range(len(info["points"]) - 1)))
    # CI hard-gate feedback: heavy penalty when crossing pairs > 2 (certificate gate: crossings <= 2)
    total += 1500.0 * max(0, router.final_crossing_pairs(routes) - 2)
    total += 1500.0 * clr_hard
    total += 1500.0 * ang_hard
    # ref-scrubbed breathing room: card gap >=36px target (soft penalty, first tier)
    ids = list(nodes_px)
    if len(ids) > 1:
        mg = min(rect_gap(*nodes_px[u], *nodes_px[v])
                 for i2, u in enumerate(ids) for v in ids[i2 + 1:])
        total += 8.0 * max(0.0, GAP_TARGET - mg)
    return total, routes, router


GAP_TARGET = 36.0        # breathing room: card-gap target (jacky's 14 hand-drawn samples averaged +35.8px)


def _interleave_count(edges, order):
    """Topological interleaving-pair count (a proxy for the crossing lower bound that routing cannot avoid under a fixed row assignment).

    Two independent edges (no shared endpoint) whose row intervals overlap by
    >=1 row and whose in-row orders are reversed at both endpoints ->
    an interleaving pair. Equal in-row order (same column) is not counted.
    O(m^2) pure arithmetic, deterministic.
    """
    pos, row_of = {}, {}
    for r, vs in enumerate(order):
        for k, v in enumerate(vs):
            pos[v] = k
            row_of[v] = r
    f = 0
    for i in range(len(edges)):
        a1, b1 = edges[i]
        for j in range(i + 1, len(edges)):
            a2, b2 = edges[j]
            if {a1, b1} & {a2, b2}:
                continue
            r11, r12 = row_of[a1], row_of[b1]
            r21, r22 = row_of[a2], row_of[b2]
            lo1, hi1 = min(r11, r12), max(r11, r12)
            lo2, hi2 = min(r21, r22), max(r21, r22)
            if min(hi1, hi2) - max(lo1, lo2) < 1:
                continue
            t1 = a1 if r11 < r12 else b1
            q1 = b1 if r11 < r12 else a1
            t2 = a2 if r21 < r22 else b2
            q2 = b2 if r21 < r22 else a2
            if pos[t1] == pos[t2] or pos[q1] == pos[q2]:
                continue
            if (pos[t1] > pos[t2]) != (pos[q1] > pos[q2]):
                f += 1
    return f


def _order_score(edges, order):
    """Reorder objective: interleaving pairs primary, row-distance*column-distance edge length secondary (keeps things compact on ties)."""
    pos, row_of = {}, {}
    for r, vs in enumerate(order):
        for k, v in enumerate(vs):
            pos[v] = k
            row_of[v] = r
    lensum = 0
    for a, b in edges:
        lensum += abs(pos[a] - pos[b]) + abs(row_of[a] - row_of[b])
    return _interleave_count(edges, order) * 1000.0 + lensum


def _reorder_rows(edges, rows):
    """Deterministic (row, in-row order) local search: minimizes topological interleaving pairs (routing-quality rework).

    Neighborhood = all same-row swaps + all single-node cross-row moves
    (keeping >=1 node per row).
    Steepest descent to a local optimum; then a deterministic perturbation
    (take the best non-improving neighbor) and descend again,
    REORDER_CYCLES rounds in total, tracking the global best throughout.
    No RNG; same input, same output.
    """
    REORDER_CYCLES = 16
    order = [list(vs) for vs in rows]

    def neighbors(cur):
        out = []
        for r, vs in enumerate(cur):
            for i in range(len(vs)):
                for j in range(i + 1, len(vs)):
                    c2 = [list(v) for v in cur]
                    c2[r][i], c2[r][j] = c2[r][j], c2[r][i]
                    out.append(c2)
        for r, vs in enumerate(cur):
            for i, v in enumerate(vs):
                for r2, vs2 in enumerate(cur):
                    if r2 == r or len(cur[r]) < 2:
                        continue
                    for p in range(len(vs2) + 1):
                        c2 = [list(v) for v in cur]
                        c2[r].pop(i)
                        c2[r2].insert(p, v)
                        out.append(c2)
        return out

    def descend(cur):
        cur_sc = _order_score(edges, cur)
        while True:
            best, best_sc = None, cur_sc
            for cand in neighbors(cur):
                sc = _order_score(edges, cand)
                if sc < best_sc - 1e-9:
                    best, best_sc = cand, sc
            if best is None:
                return cur, cur_sc
            cur, cur_sc = best, best_sc

    best, best_sc = descend(order)
    cur = order
    for _ in range(REORDER_CYCLES):
        # deterministic perturbation: the lowest-scoring non-improving neighbor of the current solution (first one on ties)
        cur_sc = _order_score(edges, cur)
        best_n, best_nsc = None, None
        for cand in neighbors(cur):
            sc = _order_score(edges, cand)
            if best_n is None or sc < best_nsc - 1e-9:
                best_n, best_nsc = cand, sc
        if best_n is None:
            break
        cur, cur_sc = descend(best_n)
        if cur_sc < best_sc - 1e-9:
            best, best_sc = cur, cur_sc
    return best


def _repack_x(order, widths, cfg):
    """Repack x in the reordered in-row order (24px snap, same caliber as construct, deterministic)."""
    snap = cfg.snap_regular
    pos = {}
    for vs in order:
        xs, cursor = [], 0
        for v in vs:
            xs.append(cursor + widths[v] / 2 + cfg.min_gap)
            cursor += widths[v] + cfg.min_gap * 2
        total = xs[-1] + widths[vs[-1]] / 2 + cfg.min_gap
        shift = (max(0, _content_w(order, widths, cfg)) - total) / 2
        for v, x in zip(vs, xs):
            pos[v] = int(round((x + shift) / snap)) * snap
    return pos


def _polish(nodes, edges, rows, pos, y, widths, card_h, cfg, rounds=2,
            hard_gates=False):
    """Local search: per-node +/-24/+/-48 horizontal shifts (preserving same-row clearance), scored by routing ground-truth total cost.

    A supplementary refinement over CP-SAT global placement - it explicitly
    feeds "routing feasibility" back into the placement layer.
    Deterministic: fixed traversal order + fixed perturbation set.
    """
    def nodes_px(p):
        return {v: (p[v], y[v], widths[v], card_h) for v in nodes}

    best_pos = dict(pos)
    best_score, best_routes, _ = _route_total(nodes_px(best_pos), edges, cfg,
                                              hard_gates, quality=hard_gates)
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    for _ in range(rounds):
        improved = False
        for v in sorted(nodes):
            row = [u for u in rows[row_of[v]] if u != v]
            for dx in (24, -24, 48, -48, 72, -72):
                nx = best_pos[v] + dx
                if any(abs(nx - best_pos[u]) <
                       (widths[v] + widths[u]) / 2 + cfg.min_gap for u in row):
                    continue
                if nx < cfg.margin or nx > _content_w(rows, widths, cfg) - cfg.margin:
                    continue
                cand = dict(best_pos)
                cand[v] = nx
                sc, routes, _ = _route_total(nodes_px(cand), edges, cfg,
                                             hard_gates, quality=hard_gates)
                if sc < best_score - 1e-6:
                    best_pos, best_score, best_routes = cand, sc, routes
                    improved = True
        # adjacent in-row swaps (mechanizing the "a human can see a better spot" class of moves)
        for vs in rows:
            for i in range(len(vs) - 1):
                u, w = vs[i], vs[i + 1]
                cand = dict(best_pos)
                cand[u], cand[w] = best_pos[w], best_pos[u]
                sc, routes, _ = _route_total(nodes_px(cand), edges, cfg,
                                             hard_gates, quality=hard_gates)
                if sc < best_score - 1e-6:
                    best_pos, best_score, best_routes = cand, sc, routes
                    improved = True
        if not improved:
            break
    return best_pos, best_score, best_routes


def _manual_waypoints(manual, edges):
    """--from-layout per-edge waypoints (ref-scrubbed): {(a,b): [[x,y],...]}.

    The export artifact of the demo-2d bend handles ("user anchoring").
    Validation: (a,b) must be an edge of the graph and
    every point a pair of numbers; coordinates are rounded (same caliber as
    nodes); consecutive duplicate points <0.5px apart are
    deduplicated; if empty after dedup it counts as not anchored.
    Deterministic: same input, same output.
    """
    out = {}
    raw = manual.get("edges")
    if raw is None:
        return out
    if not isinstance(raw, list):
        raise ValueError("manual layout edges must be a [{a,b,waypoints}] list")
    eset = set(edges)
    for it in raw:
        if not isinstance(it, dict):
            raise ValueError(f"unrecognized manual layout edge entry: {it!r}")
        a, b = it.get("a"), it.get("b")
        if (a, b) not in eset:
            raise ValueError(f"manual layout waypoints reference an edge not in the graph: {a}->{b}")
        wps = it.get("waypoints")
        if wps is None:
            continue
        if not isinstance(wps, list):
            raise ValueError(f"waypoints of edge {a}->{b} must be a [[x,y],...] list")
        pts = []
        for p in wps:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise ValueError(f"unrecognized waypoint format for edge {a}->{b}: {p!r}")
            try:
                x, y = float(p[0]), float(p[1])
            except (TypeError, ValueError):
                raise ValueError(f"waypoint coordinates of edge {a}->{b} are not numeric: {p!r}")
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"waypoint coordinates of edge {a}->{b} are not finite: {p!r}")
            q = (int(round(x)), int(round(y)))
            if not pts or math.dist(pts[-1], q) > 0.5:
                pts.append(q)
        if pts:
            out[(a, b)] = pts
    return out


def _manual_positions(nodes, widths, manual):
    """--from-layout: consume a manual layout (a layout.json-compatible subset), returns (pos, y, rows, meta).

    Manual coordinates are rounded and aligned to the 2px grid (matching the
    geometry self-check 6b caliber; snap effects are recorded honestly);
    card widths are recomputed from labels via textmetrics (same caliber as the
    automatic pipeline). The id set must match the graph exactly
    (missing/extra nodes -> ValueError, which the CLI turns into an honest error).
    """
    mn = manual.get("nodes") or {}
    if not isinstance(mn, dict) or not mn:
        raise ValueError("manual layout is missing nodes (node id -> x,y)")
    def _xy(entry):
        if isinstance(entry, dict):
            return entry.get("x"), entry.get("y")
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            return entry[0], entry[1]
        raise ValueError(f"unrecognized manual layout node format: {entry!r}")
    missing = [v for v in nodes if v not in mn]
    extra = [v for v in mn if v not in set(nodes)]
    if missing or extra:
        raise ValueError(f"manual layout node set does not match the graph: missing {missing}, extra {extra}")
    pos, y, snapped = {}, {}, []
    for v in nodes:
        xv, yv = _xy(mn[v])
        try:
            xi, yi = int(round(float(xv))), int(round(float(yv)))
        except (TypeError, ValueError):
            raise ValueError(f"manual layout node {v} coordinates are not numeric: {xv!r},{yv!r}")
        if xi % 2 or yi % 2:
            snapped.append(v)
        pos[v] = xi - (xi % 2)      # align to the 2px grid (geometry self-check 6b caliber)
        y[v] = yi - (yi % 2)
    rows = [[v for v in nodes if y[v] == yy] for yy in sorted({y[v] for v in nodes})]
    meta = {"source": manual.get("source"),
            "manual_viewBox": manual.get("viewBox"),
            "snapped_to_2px": sorted(snapped)}
    return pos, y, rows, meta


def _manual_edge_styles(manual, edges):
    """--from-layout per-edge forced line styles (v0.7.7): {(a,b): style}.

    The export artifact of the demo-2d per-edge style cycle
    (auto/straight/arc/free). Validation mirrors _manual_waypoints: (a,b)
    must be a graph edge; style must be one of the four tokens; "auto"
    entries are dropped (engine default). "free" is carried by waypoints
    (kind=waypoints path), not by this dict.
    """
    out = {}
    raw = manual.get("edges")
    if raw is None:
        return out
    if not isinstance(raw, list):
        raise ValueError("manual layout edges must be a [{a,b,style}] list")
    eset = set(edges)
    for it in raw:
        if not isinstance(it, dict):
            raise ValueError(f"unrecognized manual layout edge entry: {it!r}")
        a, b = it.get("a"), it.get("b")
        if (a, b) not in eset:
            raise ValueError(f"manual layout styles reference an edge not in the graph: {a}->{b}")
        st = it.get("style")
        if st is None:
            continue
        if st not in ("auto", "straight", "arc", "free"):
            raise ValueError(f"unrecognized line style for edge {a}->{b}: {st!r}")
        if st in ("straight", "arc"):
            out[(a, b)] = st
    return out


def _manual_arc_ctrls(manual, edges):
    """--from-layout final-form arc ctrl (export edges[].ctrl): {(a,b): [x,y]}.

    Only meaningful together with style "arc": the exported ctrl is the
    viewer's LIVE arc control point (already endpoint-translated to final
    form), so the replay uses it as-is instead of re-deriving a forced arc
    (the forced-arc family cannot clear an interposed box on a short chord
    that the baseline lens/adaptive arc clears). Validation mirrors
    _manual_edge_styles; entries without a valid [x, y] are dropped.
    Deterministic: same input, same output.
    """
    out = {}
    raw = manual.get("edges")
    if raw is None:
        return out
    if not isinstance(raw, list):
        raise ValueError("manual layout edges must be a [{a,b,style}] list")
    eset = set(edges)
    for it in raw:
        if not isinstance(it, dict):
            raise ValueError(f"unrecognized manual layout edge entry: {it!r}")
        a, b = it.get("a"), it.get("b")
        if (a, b) not in eset:
            raise ValueError(f"manual layout styles reference an edge not in the graph: {a}->{b}")
        if it.get("style") != "arc":
            continue
        ctrl = it.get("ctrl")
        if ctrl is None:
            continue
        if (not isinstance(ctrl, (list, tuple)) or len(ctrl) != 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v)
                           for v in ctrl)):
            raise ValueError(f"ctrl of edge {a}->{b} must be an [x, y] pair of finite numbers")
        out[(a, b)] = [float(ctrl[0]), float(ctrl[1])]
    return out


def _manual_anchors(manual, edges):
    """--from-layout per-edge user anchor designations (T1): {(a,b): sel}.

    sel = {"src": aid | (absent), "dst": aid | (absent)} — the export
    artifact of the demo-2d endpoint drag / anchor click (edges[].anchors,
    viewer userAnchored semantics). Validation mirrors _manual_waypoints:
    (a,b) must be a graph edge and every anchor id must be in
    anchors.ANCHOR_IDS; entries with neither src nor dst are dropped.
    Deterministic: same input, same output.
    """
    out = {}
    raw = manual.get("edges")
    if raw is None:
        return out
    if not isinstance(raw, list):
        raise ValueError("manual layout edges must be a [{a,b,anchors}] list")
    eset = set(edges)
    for it in raw:
        if not isinstance(it, dict):
            raise ValueError(f"unrecognized manual layout edge entry: {it!r}")
        a, b = it.get("a"), it.get("b")
        if (a, b) not in eset:
            raise ValueError(f"manual layout anchors reference an edge not in the graph: {a}->{b}")
        anc = it.get("anchors")
        if anc is None:
            continue
        if not isinstance(anc, dict):
            raise ValueError(f"anchors of edge {a}->{b} must be an object {{src, dst}}")
        sel = {}
        for end_key in ("src", "dst"):
            aid = anc.get(end_key)
            if aid is None:
                continue
            if aid not in ANCHOR_IDS:
                raise ValueError(f"unknown anchor id for edge {a}->{b} ({end_key}): {aid!r}")
            sel[end_key] = aid
        if sel:
            out[(a, b)] = sel
    return out


def _forced_arc_route(nodes_px, a, b, clearance):
    """Deterministic forced-arc geometry (v0.7.7 style replay, Python side).

    Same rule as the demo-2d drag layer: anchors = box borders facing each
    other; curvature = chord-adaptive k (routing.adaptive_arc_k); side = the
    sign whose sampled arc keeps more distance from unrelated boxes (tie ->
    +1). Returns (points, ctrl)."""
    from .routing import border_point, quad_points, adaptive_arc_k, dist_point_rect
    A, B = nodes_px[a], nodes_px[b]
    pa = border_point(A[0], A[1], A[2] / 2.0, A[3] / 2.0, B[0] - A[0], B[1] - A[1])
    pb = border_point(B[0], B[1], B[2] / 2.0, B[3] / 2.0, A[0] - B[0], A[1] - B[1])
    vx, vy = pb[0] - pa[0], pb[1] - pa[1]
    dist = math.hypot(vx, vy)
    k = adaptive_arc_k(dist)
    n = max(dist, 1e-6)
    ux, uy = -vy / n, vx / n
    best = None
    for s in (1, -1):
        ctrl = [(pa[0] + pb[0]) / 2 + ux * k * dist * s,
                (pa[1] + pb[1]) / 2 + uy * k * dist * s]
        pts = quad_points(pa, ctrl, pb)
        mclr = None
        for v, rect in nodes_px.items():
            if v in (a, b):
                continue
            for (px, py) in pts:
                d = dist_point_rect(px, py, rect[0], rect[1],
                                    rect[2] / 2.0, rect[3] / 2.0)
                mclr = d if mclr is None else min(mclr, d)
        key = (-(mclr if mclr is not None else 1e9), s)
        if best is None or key < best[0]:
            best = (key, pts, ctrl)
    return best[1], best[2]


def _ring_trial(plan, nodes, widths, card_h, cfg, edges, why=None):
    """Ring placement + routing trial: adopted only if every hard-gate proxy passes; otherwise None (fall back to layered, byte-for-byte unchanged).

    why: optional dict — receives the trial-gate outcome reason (mode
    decision trace).

    The proxy caliber shares its source with the delivered certificate:
    crossings (router theory) <=2, box press=0, edge-box clearance>=clearance,
    mutual-pair separation >=4px, card gap >=16, anchor smoothing >=20deg.
    The final word is certificate_auto's recheck on delivered coordinates (this
    layer is only the deterministic adopt/fallback trial gate).
    """
    from . import ringlayout
    from .routing import (min_pair_dist, sample_polyline, ANCHOR_MIN_DEG)

    def _why(reason):
        if why is not None:
            why["reason"] = reason
        return None
    adj, _ = ringlayout._adjacency(edges)
    try:
        pos, y, meta = ringlayout.place_ring(plan, widths, card_h, cfg, adj,
                                             edges)
    except ringlayout.InfeasibleRing:
        return _why("trial: constructed placement infeasible (InfeasibleRing)")
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    # card gap >=16 (place_ring places at 18; a pairwise recheck is the backstop)
    vs = sorted(nodes)
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            a, b = vs[i], vs[j]
            gap_x = abs(pos[a] - pos[b]) - (widths[a] + widths[b]) / 2
            gap_y = abs(y[a] - y[b]) - card_h
            if max(gap_x, gap_y) < cfg.min_gap - 2:      # rect_gap caliber (>=16 gate)
                return _why("trial gate: card gap < 16 (rect_gap caliber)")
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    if router.final_crossing_pairs(routes) > 2:
        return _why("trial gate: router-theory crossings > 2")
    eset = set(edges)
    for i, info in routes.items():
        if info.get("press", 0):
            return _why("trial gate: box press != 0")
        clr = info.get("min_clear")
        if clr is None or clr < cfg.clearance:
            return _why("trial gate: edge-box clearance < 16px")
        # anchor smoothing proxy (same caliber as check item 4)
        pts = info["points"]
        for v, p_idx, n_idx in ((edges[i][0], 0, 1),
                                (edges[i][1], len(pts) - 1, len(pts) - 2)):
            p = nodes_px[v]
            a0 = pts[p_idx]
            if (abs(abs(a0[0] - p[0]) - p[2] / 2) > abs(abs(a0[1] - p[1]) - p[3] / 2) + 1e-9
                    and abs(abs(a0[1] - p[1]) - p[3] / 2) > 0.75):
                return _why("trial gate: anchor not on the box edge")
            dx, dy = pts[n_idx][0] - a0[0], pts[n_idx][1] - a0[1]
            n = math.hypot(dx, dy)
            if n < 1e-9:
                return _why("trial gate: degenerate anchor segment")
            on_x = abs(abs(a0[0] - p[0]) - p[2] / 2) <= abs(abs(a0[1] - p[1]) - p[3] / 2)
            tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
            c = abs(dx * tx + dy * ty) / n
            if math.degrees(math.acos(max(0.0, min(1.0, c)))) < ANCHOR_MIN_DEG:
                return _why("trial gate: anchor smoothing < 20deg")
    # mutual-pair separation >=4px (F1 caliber)
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i] != (edges[j][1], edges[j][0]):
                continue
            md = min_pair_dist(sample_polyline(routes[i]["points"]),
                               sample_polyline(routes[j]["points"]))
            if md is None or md < 4.0:
                return _why("trial gate: mutual-pair separation < 4px")
    if why is not None:
        why["reason"] = "trial gate passed"
    plan = dict(plan)
    plan["placed"] = (pos, y, meta)
    return plan


def _constructed_gates(nodes_px, edges, routes, cfg, constructed):
    """Unified hard-gate proxy over constructed routes (closed arcs / mirror-symmetry arcs) and routed routes (ref-scrubbed).

    Same caliber as _ring_trial: press=0, edge-box clearance>=clearance,
    anchors on box edges with smoothing
    >=ANCHOR_MIN_DEG, card gap >= min_gap-2, mutual-pair separation >=4px,
    crossings <=2.
    Returns True = gate passed.
    """
    from .routing import (dist_point_rect, min_pair_dist, sample_polyline,
                          ANCHOR_MIN_DEG)
    # card gap (rect_gap caliber, >= min_gap-2)
    vs = sorted(nodes_px)
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            a, b = vs[i], vs[j]
            ax, ay, aw, ah = nodes_px[a]
            bx, by, bw, bh = nodes_px[b]
            gap_x = abs(ax - bx) - (aw + bw) / 2
            gap_y = abs(ay - by) - (ah + bh) / 2
            if max(gap_x, gap_y) < cfg.min_gap - 2:
                return False
    if _final_pairs(nodes_px, edges, routes, cfg) > 2:
        return False
    for i, info in routes.items():
        a, b = edges[i]
        pts = info["points"]
        # same caliber as check3: dense-sampled clearance recheck (a backstop for chord effects)
        dense = sample_polyline([tuple(p) for p in pts], step=4.0)
        for v, (cx, cy, w, h) in nodes_px.items():
            if v in (a, b):
                continue
            for px, py in dense:
                if dist_point_rect(px, py, cx, cy, w / 2, h / 2) < cfg.clearance:
                    return False
        # anchor on box edge + smoothing
        for v, p_idx, n_idx in ((a, 0, 1), (b, len(pts) - 1, len(pts) - 2)):
            cx, cy, w, h = nodes_px[v]
            a0 = pts[p_idx]
            if (abs(abs(a0[0] - cx) - w / 2) > abs(abs(a0[1] - cy) - h / 2) + 1e-9
                    and abs(abs(a0[1] - cy) - h / 2) > 0.75):
                return False
            dx, dy = pts[n_idx][0] - a0[0], pts[n_idx][1] - a0[1]
            n = math.hypot(dx, dy)
            if n < 1e-9:
                return False
            on_x = abs(abs(a0[0] - cx) - w / 2) <= abs(abs(a0[1] - cy) - h / 2)
            tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
            c = abs(dx * tx + dy * ty) / n
            if math.degrees(math.acos(max(0.0, min(1.0, c)))) < ANCHOR_MIN_DEG:
                return False
    # mutual-pair separation >=4px
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i] != (edges[j][1], edges[j][0]):
                continue
            md = min_pair_dist(sample_polyline(routes[i]["points"]),
                               sample_polyline(routes[j]["points"]))
            if md is None or md < 4.0:
                return False
    return True


def _final_pairs(nodes_px, edges, routes, cfg):
    """Crossing edge-pair count after merging constructed routes (same caliber as Router.final_crossing_pairs)."""
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    return router.final_crossing_pairs(routes)


def _sym_trial(plan, nodes, widths, card_h, cfg, edges, why=None):
    """Bowtie-pair symmetric placement + routing trial gate: adopted only if the gate passes; otherwise None (fallback, byte-for-byte unchanged).

    why: optional dict — receives the trial-gate outcome reason (mode
    decision trace).
    """
    from . import symlayout
    try:
        pos, y, meta, constructed = symlayout.place_bowtie(plan, widths,
                                                           card_h, cfg, edges)
    except symlayout.InfeasibleBowtie:
        if why is not None:
            why["reason"] = ("trial: constructed placement infeasible "
                             "(InfeasibleBowtie)")
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    # line-style consistency hard rule: no vg/poly polylines inside the symmetric structure (arc > straight > polyline)
    for i, info in routes.items():
        if info["kind"] in ("vg", "poly", "wrap"):
            if why is not None:
                why["reason"] = ("trial gate: polyline route inside the "
                                 "symmetric structure (line-type consistency "
                                 "hard rule)")
            return None
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        if why is not None:
            why["reason"] = ("trial gate: hard-gate proxy failed "
                             "(crossings<=2 / press=0 / clearance>=16 / "
                             "smooth anchors / mutual separation / card gap)")
        return None
    if why is not None:
        why["reason"] = "trial gate passed"
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def _bowtie_trial(plan, nodes, widths, card_h, cfg, edges, why=None):
    """Bowtie-vertex symmetric placement + routing trial gate: adopted only if the gate passes; otherwise None (fallback, byte-for-byte unchanged).

    why: optional dict — receives the trial-gate outcome reason (mode
    decision trace).

    ref-scrubbed (aesthetics v3): graphs with exactly 2 simple loops sharing
    exactly 1 node (the wage-price-spiral
    family, benchmarked on jacky's hand-drawn samples) -> bowtie-vertex
    symmetric placement; all-straight-line construction,
    line-style consistency hard rule same as symmetric (vg/poly/wrap polylines
    forbidden).
    """
    from . import bowtielayout
    try:
        pos, y, meta, constructed = bowtielayout.place_bowtie_vertex(
            plan, widths, card_h, cfg, edges)
    except bowtielayout.InfeasibleBowtieVertex:
        if why is not None:
            why["reason"] = ("trial: constructed placement infeasible "
                             "(InfeasibleBowtieVertex)")
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    # line-style consistency hard rule: no vg/poly polylines inside the symmetric structure (arc > straight > polyline)
    for i, info in routes.items():
        if info["kind"] in ("vg", "poly", "wrap"):
            if why is not None:
                why["reason"] = ("trial gate: polyline route inside the "
                                 "symmetric structure (line-type consistency "
                                 "hard rule)")
            return None
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        if why is not None:
            why["reason"] = ("trial gate: hard-gate proxy failed "
                             "(crossings<=2 / press=0 / clearance>=16 / "
                             "smooth anchors / mutual separation / card gap)")
        return None
    if why is not None:
        why["reason"] = "trial gate passed"
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def _spine_trial(plan, nodes, widths, card_h, cfg, edges, why=None):
    """Spine-wing placement + routing trial gate: adopted only if the gate passes; otherwise None (fallback, byte-for-byte unchanged).

    why: optional dict — receives the trial-gate outcome reason (mode
    decision trace).

    ref-scrubbed (v0.7.1): hub pair on the spine + midline wing band + mirrored
    clusters beyond the wings
    (the classic-cld-growth-and-burden family, benchmarked on jacky's
    hand-drawn samples); spine edges
    are injected as constructed vertical straight lines, the rest go through
    the Router candidate pool.
    """
    from . import spinewinglayout
    try:
        pos, y, meta, constructed = spinewinglayout.place_spine_wing(
            plan, widths, card_h, cfg, edges)
    except spinewinglayout.InfeasibleSpineWing:
        if why is not None:
            why["reason"] = ("trial: constructed placement infeasible "
                             "(InfeasibleSpineWing)")
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        if why is not None:
            why["reason"] = ("trial gate: hard-gate proxy failed "
                             "(crossings<=2 / press=0 / clearance>=16 / "
                             "smooth anchors / mutual separation / card gap)")
        return None
    if why is not None:
        why["reason"] = "trial gate passed"
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def _comb_trial(plan, nodes, widths, card_h, cfg, edges, why=None):
    """Comb-bilateral placement + routing trial gate: adopted only if every
    route is a straight line (the comb contract: column spine vertical +
    hub fan straight) AND the unified hard-gate proxy passes; otherwise None
    (fall back to the next tier, byte-for-byte unchanged).

    v0.7.7 (ref-scrubbed): K_{m,2} bilateral family — two non-adjacent hubs,
    every source connected to both, pendant trees on the source side.
    Geometric ground truth = jacky's hand-pulled HDD supply-chain layout.
    """
    from . import comblayout
    try:
        pos, y, meta, constructed = comblayout.place_comb(plan, widths,
                                                          card_h, cfg)
    except comblayout.InfeasibleComb:
        if why is not None:
            why["reason"] = ("trial: constructed placement infeasible "
                             "(InfeasibleComb — both fan tiers exhausted)")
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    # v0.7.8 tier-1 wide-card fan: hub edges constructed between
    # facing-vertical-border anchors replace the routed candidates here (the
    # same injection channel the delivery layer uses); the contract check
    # and the unified hard gates below then review the injected geometry
    # like any other route.
    if constructed:
        idx = {e: i for i, e in enumerate(edges)}
        for key, cr in constructed.items():
            i = idx.get(key)
            if i is None:
                continue        # mirrored direction key absent from the
                                # declared edge list — nothing to replace
            routes[i] = {"kind": cr["kind"],
                         "points": [list(p) for p in cr["points"]],
                         "press": 0, "min_clear": None, "cross": 0,
                         "cross_edges": 0, "ang_a": 90.0, "ang_b": 90.0}
    for i, info in routes.items():
        if info["kind"] != "line":
            if why is not None:
                why["reason"] = ("trial gate: comb contract broken — "
                                 f"non-straight route ({info['kind']}) in "
                                 "the hub fan")
            return None                      # comb contract: all-straight fan
    if not _constructed_gates(nodes_px, edges, routes, cfg, {}):
        if why is not None:
            why["reason"] = ("trial gate: hard-gate proxy failed "
                             "(crossings<=2 / press=0 / clearance>=16 / "
                             "smooth anchors / mutual separation / card gap)")
        return None
    if why is not None:
        why["reason"] = "trial gate passed (all-straight fan contract held)"
    plan = dict(plan)
    plan["placed"] = (pos, y, meta)
    plan["constructed"] = {k: dict(v) for k, v in constructed.items()}
    return plan


def _column_trial(plan, nodes, widths, card_h, cfg, edges, why=None):
    """Column placement + routing trial gate: adopted only if the gate passes; otherwise None (fall back to layered, byte-for-byte unchanged).

    why: optional dict — receives the trial-gate outcome reason (mode
    decision trace).
    """
    from . import columnlayout
    from .routing import min_pair_dist, sample_polyline
    adj = columnlayout._adjacency(edges)
    try:
        pos, y, meta, constructed = columnlayout.place_column(
            plan, widths, card_h, cfg, adj, edges)
    except columnlayout.InfeasibleColumn:
        if why is not None:
            why["reason"] = ("trial: constructed placement infeasible "
                             "(InfeasibleColumn)")
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        if why is not None:
            why["reason"] = ("trial gate: hard-gate proxy failed "
                             "(crossings<=2 / press=0 / clearance>=16 / "
                             "smooth anchors / mutual separation / card gap)")
        return None
    if why is not None:
        why["reason"] = "trial gate passed"
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def layout(graph, config: AutoConfig = None, linestyle: str = "straight",
           manual: dict = None):
    """auto recipe entry point: graph -> a v4-compatible layout dict (with polyline/arc routing + metadata).

    manual: a --from-layout manual layout ({nodes: {id: x,y}, viewBox, source}).
    When given, layering/placement/polish are skipped and the manual
    coordinates go through the same routing + delivery pipeline (hard-gate
    caliber unchanged, scored honestly). With manual=None (default) the code
    path is byte-for-byte identical to history.

    ref-scrubbed loop-dominant ring placement: with manual=None the deterministic
    trigger detection (ringlayout.detect_ring) runs first;
    a hit whose routing trial passes the gate -> regular-polygon slots for the
    main ring;
    no hit / trial failure -> the existing layered path (byte-for-byte
    unchanged).
    """
    cfg = config or AutoConfig()
    edges = tuple((e.a, e.b) for e in graph.edges)
    # Cache lifecycle: module-level route/corner caches must never carry
    # state across layouts (rounded-key aliasing would make batch results
    # order-dependent); Router caches are instance-scoped, fresh per call.
    _reset_route_caches()
    # T3: observational stage timing. No-op unless STDRAW_TIMING=1; the
    # report at the end goes to stderr only and never touches layout.json
    # (zero-behavior-change, ci_checks mark() style).
    _timing.start()
    nodes = graph.node_ids()
    adj = graph.adj_undirected()
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]

    # ① box-boundary ground truth (layout side): real font metrics + conservative padding
    widths, heights = {}, {}
    for v in nodes:
        nd = graph.id2node()[v]
        w, h = textmetrics.card_size(nd.label, nd.value, cfg.fs_title, cfg.fs_value,
                                     min_w=cfg.card_min_w,
                                     value_pad=cfg.value_pad_extra)
        widths[v], heights[v] = w, h
    card_h = max(heights.values()) if heights else cfg.card_h
    _timing.mark("card_metrics")

    # ②③ placement: --from-layout manual coordinates, or automatic layering + placement
    _routes_final = None
    constructed = {}
    from_meta = None
    # ref-scrubbed mode decision trace: every rule evaluation in the deterministic
    # priority chain is recorded (rule, tier, triggered, reason, trial gate) so
    # the certificate can show WHY a placement mode was picked (review report
    # item 5: reduce the trigger-template black-box feel). Recording only — the
    # decision logic below is untouched, so non-hit paths stay byte-identical.
    _mode_rules = []
    if manual is not None:
        pos, y, rows, from_meta = _manual_positions(nodes, widths, manual)
        deg0 = []
        engine, pos_meta = "manual", {}
        _timing.mark("manual_positions")
    else:
        # ②'' layout aesthetics v2 (ref-scrubbed, jacky's 2026-11-05 direction for the whole graph): mode priority =
        #  symmetric (shared-edge bowtie, the learning-flywheel family) -> bowtie-vertex (two loops sharing one node)
        #  -> spine-wing (hub pair + wings) -> comb-bilateral (bilateral hubs, tier 2 via the salience rule)
        #  -> column (long chains / few loops, main ring <=4) -> ring (loop-dominant small graphs, ref-scrubbed)
        #  -> the existing layered path.
        #  Every new mode carries a trial gate: silent fallback when the gate fails, and the fallback path is byte-for-byte unchanged.
        def _rule_hit(name, tier, det_ok, plan, det_why, trial_why=None):
            """Record one priority-chain rule evaluation (trace only)."""
            entry = {"tier": tier, "rule": name,
                     "triggered": plan is not None,
                     "reason": (det_why or {}).get("reason")}
            if det_ok and plan is None and trial_why is not None:
                entry["trial_gate"] = "fail"
                entry["reason"] = (entry["reason"] + " — " +
                                   (trial_why or {}).get("reason", ""))
            elif plan is not None:
                entry["trial_gate"] = "pass"
            else:
                entry["trial_gate"] = None
            _mode_rules.append(entry)
            return plan

        sym_plan = None
        bw_plan = None
        sw_plan = None
        comb_plan = None
        column_plan = None
        ring_plan = None
        _why_sym, _why_bw, _why_sw = {}, {}, {}
        _why_comb, _why_col, _why_ring = {}, {}, {}
        _tw_sym, _tw_bw, _tw_sw = {}, {}, {}
        _tw_comb, _tw_col, _tw_ring = {}, {}, {}
        _chain_cap = len(nodes) <= 12
        if not _chain_cap:
            _cap_reason = (f"n={len(nodes)} > 12 — structural modes cap at "
                           "12 nodes")
            for _nm in ("symmetric (shared-edge bowtie)", "bowtie-vertex",
                        "spine-wing", "column-chain", "comb-bilateral",
                        "ring-cycle"):
                _mode_rules.append({"tier": 0, "rule": _nm,
                                    "triggered": False,
                                    "reason": f"not evaluated: {_cap_reason}",
                                    "trial_gate": None})
        if _chain_cap:
            from . import symlayout as _symlayout
            _sym = _symlayout.detect_bowtie(graph, why=_why_sym)
            if _sym is not None:
                sym_plan = _sym_trial(_sym, nodes, widths, card_h, cfg, edges,
                                      why=_tw_sym)
            _rule_hit("symmetric (shared-edge bowtie)", 1, _sym is not None,
                      sym_plan, _why_sym, _tw_sym)
        # ref-scrubbed (aesthetics v3) bowtie-vertex (two loops sharing a single node): topologically mutually exclusive with the shared-edge bowtie
        # (symmetric) and tied with it at the top tier; detection enumerates simple loops (the declared table mixes in 2-node pseudo-loops
        # and misses derived loops, so it is unusable).
        if sym_plan is None and _chain_cap:
            from . import bowtielayout as _bowtielayout
            _bw = _bowtielayout.detect_bowtie_vertex(graph, why=_why_bw)
            if _bw is not None:
                bw_plan = _bowtie_trial(_bw, nodes, widths, card_h, cfg, edges,
                                        why=_tw_bw)
            _rule_hit("bowtie-vertex", 1, _bw is not None, bw_plan,
                      _why_bw, _tw_bw)
        if bw_plan is None and sym_plan is None and _chain_cap:
            from . import spinewinglayout as _spinewinglayout
            _sw = _spinewinglayout.detect_spine_wing(graph, why=_why_sw)
            if _sw is not None:
                sw_plan = _spine_trial(_sw, nodes, widths, card_h, cfg, edges,
                                       why=_tw_sw)
            _rule_hit("spine-wing", 2, _sw is not None, sw_plan,
                      _why_sw, _tw_sw)
        if (bw_plan is None and sym_plan is None and sw_plan is None
                and _chain_cap):
            from . import ringlayout as _ringlayout
            from . import columnlayout as _columnlayout
            from . import comblayout as _comblayout
            _ring_detect = _ringlayout.detect_ring(graph, why=_why_ring)
            # column is detected only when ring would not take the pure-cycle/ratio branch (cover-triggered graphs with a main ring <=4 go
            # to column; large rings with k>=5 still go to ring)
            if _ring_detect is None or _ring_detect["trigger"] == "cover":
                _col = _columnlayout.detect_column(graph, why=_why_col)
                if _col is not None:
                    column_plan = _column_trial(_col, nodes, widths, card_h,
                                                cfg, edges, why=_tw_col)
                _rule_hit("column-chain", 3, _col is not None, column_plan,
                          _why_col, _tw_col)
            else:
                _mode_rules.append({
                    "tier": 3, "rule": "column-chain", "triggered": False,
                    "reason": ("not evaluated: ring detection would take the "
                               f"{_ring_detect['trigger']} branch "
                               "(pure-cycle/ratio graphs go to ring-cycle)"),
                    "trial_gate": None})
            # v0.7.7 comb-bilateral (K_{m,2} bilateral hubs) sits between
            # column and ring (preempts ring: these graphs score a high
            # non-bridge ratio with a 4-cycle "main ring" and historically
            # misfired the ring ratio branch). Against column it applies a
            # salience rule: the bilateral reading wins only when the source
            # column is strictly longer than the best column spine (in the
            # established column-chain families the spine weaves
            # hub-source-hub-source and is at least as salient — zero drift).
            _comb = _comblayout.detect_comb(graph, why=_why_comb)
            if _comb is not None and _col is not None \
                    and len(_comb["column"]) <= len(_col.get("spine") or ()):
                _mode_rules.append({
                    "tier": 2, "rule": "comb-bilateral", "triggered": False,
                    "reason": ("detected, but not adopted: the comb source "
                               "column is not strictly longer than the best "
                               "column spine (salience rule — the column "
                               "reading wins)"),
                    "trial_gate": None})
                _comb = None
            if _comb is not None:
                comb_plan = _comb_trial(_comb, nodes, widths, card_h, cfg, edges,
                                        why=_tw_comb)
                _rule_hit("comb-bilateral", 2, True, comb_plan,
                          _why_comb, _tw_comb)
            if column_plan is None and comb_plan is None and _ring_detect is not None:
                ring_plan = _ring_trial(_ring_detect, nodes, widths, card_h,
                                        cfg, edges, why=_tw_ring)
                _rule_hit("ring-cycle", 4, True, ring_plan,
                          _why_ring, _tw_ring)
            elif _ring_detect is None:
                _mode_rules.append({"tier": 4, "rule": "ring-cycle",
                                    "triggered": False,
                                    "reason": _why_ring.get("reason"),
                                    "trial_gate": None})
            elif column_plan is not None or comb_plan is not None:
                _mode_rules.append({"tier": 4, "rule": "ring-cycle",
                                    "triggered": False,
                                    "reason": ("detected, but a higher-tier "
                                               "plan was adopted — trial not "
                                               "run"),
                                    "trial_gate": None})
        if not any(p is not None for p in (sym_plan, bw_plan, sw_plan,
                                           comb_plan, column_plan,
                                           ring_plan)):
            _mode_rules.append({"tier": 5, "rule": "layered (existing path)",
                                "triggered": True,
                                "reason": ("fallback: no structural mode "
                                           "triggered — layered layering + "
                                           "placement (byte-stable default)"),
                                "trial_gate": None})
        _timing.mark("mode_detection_trials")
        constructed = {}
        if sym_plan is not None:
            spos, sy, smeta, sconstructed = sym_plan["placed"]
            pos, y = spos, sy
            deg0 = list(sym_plan["deg0"])
            rows = [[v for v in nodes if y[v] == yy]
                    for yy in sorted({y[v] for v in nodes})]
            engine = "sym-construct"
            pos_meta = smeta
            constructed = sconstructed
        elif bw_plan is not None:
            bpos, by, bmeta, bconstructed = bw_plan["placed"]
            pos, y = bpos, by
            deg0 = list(bw_plan["deg0"])
            rows = [[v for v in nodes if y[v] == yy]
                    for yy in sorted({y[v] for v in nodes})]
            engine = "bowtie-construct"
            pos_meta = bmeta
            constructed = bconstructed
        elif sw_plan is not None:
            wpos, wy, wmeta, wconstructed = sw_plan["placed"]
            pos, y = wpos, wy
            deg0 = list(sw_plan["deg0"])
            rows = [[v for v in nodes if y[v] == yy]
                    for yy in sorted({y[v] for v in nodes})]
            engine = "spine-construct"
            pos_meta = wmeta
            constructed = wconstructed
        elif comb_plan is not None:
            cpos, cy, cmeta = comb_plan["placed"]
            pos, y = cpos, cy
            deg0 = list(comb_plan["deg0"]) if "deg0" in comb_plan else \
                [v for v in nodes if not adj[v]]
            rows = [[v for v in nodes if y[v] == yy]
                    for yy in sorted({y[v] for v in nodes})]
            engine = "comb-construct"
            pos_meta = cmeta
            # v0.7.8: tier-1 fan lines ride the generic constructed-route
            # injection channel (frozen out of coincide/midband/fan_spread,
            # hard gates already rechecked by the trial)
            constructed = comb_plan.get("constructed") or {}
        elif column_plan is not None:
            cpos, cy, cmeta, cconstructed = column_plan["placed"]
            pos, y = cpos, cy
            deg0 = list(column_plan["deg0"])
            rows = [[v for v in nodes if y[v] == yy]
                    for yy in sorted({y[v] for v in nodes})]
            engine = "column-construct"
            pos_meta = cmeta
            constructed = cconstructed
        elif ring_plan is not None:
            rpos, ry, rmeta = ring_plan["placed"]
            pos, y = rpos, ry
            deg0 = list(ring_plan["deg0"])
            rows = [[v for v in nodes if y[v] == yy]
                    for yy in sorted({y[v] for v in nodes})]
            engine = "ring-construct"
            pos_meta = rmeta
        else:
            # ② layering (cycle breaking + longest path + empty-layer compression)
            _, dag = _cycle_break(core, edges)
            layer = _layers(core, dag)
            nrow = max(layer.values()) + 1 if core else 1
            rows = [[v for v in core if layer[v] == r] for r in range(nrow)]
            rows = [r for r in rows if r]
            _timing.mark("layering")

            # ③ placement
            pos, engine, pos_meta = _solve_positions(core, rows, widths, cfg, linestyle, edges)

            # y coordinates (even rows -> the foundation of the regularity gate)
            y = {v: cfg.top + r * cfg.pitch for r, vs in enumerate(rows) for v in vs}
            # parking strip for isolated nodes: evenly laid out at the top (24px column snap for small graphs, consistent with the regularity gate)
            if deg0:
                total = sum(widths[v] for v in deg0) + cfg.min_gap * (len(deg0) + 1)
                cw = _content_w(rows, widths, cfg)
                cur = max(cfg.margin, (cw - total) / 2)
                snap = cfg.snap_regular if len(nodes) <= 10 else cfg.grid
                for v in deg0:
                    pos[v] = int(round((cur + widths[v] / 2) / snap)) * snap
                    y[v] = cfg.park_y
                    cur += widths[v] + cfg.min_gap
            _timing.mark("placement_cp_sat")

            # ③b local polish (small graphs <=10 nodes): hill-climbing horizontal shifts on routing ground-truth total cost, explicitly
            # feeding routing feasibility (press/clearance/crossings) back into the placement layer
            if len(core) <= 10:
                pos, _sc, _rt = _polish(core, edges, rows, pos, y,
                                        widths, card_h, cfg)
                # -- WS3 routing-quality rework (random dense graphs: check1 crossings>2 / check3 clearance<16): when a routing hard gate fails, the
                #    layout bottleneck is not the router (the graph is planar but the placement pushes topological interleaving pairs to 3+, and greedy
                #    routing can only dodge some of them) but the "row assignment + in-row order". Trigger a deterministic (row, order) reorder -> 24px
                #    repack -> hard-gate polish, and pick the better of it and the original placement under the same evaluation caliber (never worse
                #    than the baseline). Gated trigger: layouts whose hard gates already pass (the entire classic domain, existing passing cases) get
                #    zero perturbation, output byte-for-byte unchanged.
                _r0 = Router({v: (pos[v], y[v], widths[v], card_h) for v in nodes},
                             edges, cfg.clearance, cfg.pitch)
                _routes0 = _r0.route_all()
                _pairs0 = _r0.final_crossing_pairs(_routes0)
                _clrbad0 = sum(1 for _i in _routes0.values()
                               if _i.get("min_clear") is not None
                               and _i["min_clear"] < cfg.clearance - 1e-6)
                _angbad0 = sum(1 for _i in _routes0.values()
                               if min(_i.get("ang_a", ANCHOR_MIN_DEG),
                                      _i.get("ang_b", ANCHOR_MIN_DEG)) < ANCHOR_MIN_DEG - 1e-9)
                _pressbad0 = sum(1 for _i in _routes0.values() if _i.get("press", 0))
                if _pairs0 > 2 or _clrbad0 or _angbad0 or _pressbad0:
                    # The router layer's second move: joint rerouting of crossing pairs (breaks the mutual-local-optimum deadlock). quality=True is what
                    # expands the stair candidate pool - gated path only; the normal path (including polish's _route_total) keeps the historical
                    # candidate pool, zero perturbation for passing cases.
                    _rq = Router({v: (pos[v], y[v], widths[v], card_h) for v in nodes},
                                 edges, cfg.clearance, cfg.pitch, quality=True)
                    _routesA = _rq.joint_reroute(dict(_routes0))
                    _pairsA = _rq.final_crossing_pairs(_routesA)
                    _clrbadA = sum(1 for _i in _routesA.values()
                                   if _i.get("min_clear") is not None
                                   and _i["min_clear"] < cfg.clearance - 1e-6)
                    _angbadA = sum(1 for _i in _routesA.values()
                                   if min(_i.get("ang_a", ANCHOR_MIN_DEG),
                                          _i.get("ang_b", ANCHOR_MIN_DEG)) < ANCHOR_MIN_DEG - 1e-9)
                    _pressbadA = sum(1 for _i in _routesA.values() if _i.get("press", 0))
                    _gate0 = (_pairs0, _clrbad0, _angbad0, _pressbad0)
                    _best = (_gate0, None, None, None, _routes0)
                    if (_pairsA, _clrbadA, _angbadA, _pressbadA) < _best[0]:
                        _best = ((_pairsA, _clrbadA, _angbadA, _pressbadA), pos, y, rows, _routesA)
                    # The layout layer's second move: deterministic (row, order) reorder -> 24px repack -> hard-gate polish
                    # -> routing -> joint reroute
                    _order2 = _reorder_rows(edges, rows)
                    _pos2 = _repack_x(_order2, widths, cfg)
                    _y2 = dict(y)
                    for _r, _vs in enumerate(_order2):
                        for _v in _vs:
                            _y2[_v] = cfg.top + _r * cfg.pitch
                    _pos2, _sc2, _rt2 = _polish(core, edges, _order2, _pos2,
                                                _y2, widths, card_h, cfg,
                                                hard_gates=True)
                    # ref-scrubbed: isolated nodes are not in rows (delivered on the top parking strip); the gated reorder reorders only core -
                    # parking-strip coordinates are carried back as-is, so the Router's all-node keys stay complete (legacy gap: on graphs
                    # with isolated nodes the gated path raised KeyError on first trigger)
                    for _v in deg0:
                        _pos2.setdefault(_v, pos[_v])
                    _r2 = Router({v: (_pos2[v], _y2[v], widths[v], card_h)
                                  for v in nodes}, edges, cfg.clearance, cfg.pitch,
                                 quality=True)
                    _rt2 = _r2.route_all()
                    _rt2 = _r2.joint_reroute(dict(_rt2))
                    _pairs2 = _r2.final_crossing_pairs(_rt2)
                    _clrbad2 = sum(1 for _i in _rt2.values()
                                   if _i.get("min_clear") is not None
                                   and _i["min_clear"] < cfg.clearance - 1e-6)
                    _angbad2 = sum(1 for _i in _rt2.values()
                                   if min(_i.get("ang_a", ANCHOR_MIN_DEG),
                                          _i.get("ang_b", ANCHOR_MIN_DEG)) < ANCHOR_MIN_DEG - 1e-9)
                    _pressbad2 = sum(1 for _i in _rt2.values() if _i.get("press", 0))
                    if (_pairs2, _clrbad2, _angbad2, _pressbad2) < _best[0]:
                        _best = ((_pairs2, _clrbad2, _angbad2, _pressbad2),
                                 _pos2, _y2, _order2, _rt2)
                    if _best[1] is None:
                        _routes_final = _best[4]      # placement unchanged but the routes were swapped for better ones
                    elif _best[0] < _gate0:
                        pos, y, rows = _best[1], _best[2], _best[3]
                        _routes_final = _best[4]
            _timing.mark("polish_gated_reorder")

    # ④ routing (straight/arc first-class, boxes do not press lines) + WS3 theoretical caliber (final-route crossing pairs)
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    if _routes_final is not None:
        routes = _routes_final
    _timing.mark("route_final")
    # ref-scrubbed constructed-route injection (column closed arcs / bowtie mirror-symmetry arcs): these edges skip the candidate pool and are
    # delivered with the constructed geometry (the trial gate has already rechecked the hard gates); the injection must happen before
    # final_crossing_pairs so the dual crossing accounting (check11) includes the constructed routes.
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is None:
            continue
        info = {"kind": cr["kind"], "points": [list(p) for p in cr["points"]],
                "press": 0, "min_clear": None, "cross": 0, "cross_edges": 0,
                "ang_a": 90.0, "ang_b": 90.0}
        if cr.get("ctrl") is not None:
            info["ctrl"] = list(cr["ctrl"])
        routes[i] = info
    # ref-scrubbed: user-anchored waypoint override (demo-2d bend-handle export) - these edges skip the candidate pool; the delivered route is
    # built as "endpoint = standard anchor nearest to the border point aimed at the first/last waypoint + waypoints as-is" (the anchors_standard
    # hard gate holds by construction), and the geometry/certificate recheck scores the same points honestly (no leniency). The override must
    # happen before final_crossing_pairs, so the dual crossing accounting (check11) includes the waypoints.
    manual_wps = {}
    if manual is not None:
        manual_wps = _manual_waypoints(manual, edges)
    for i, (a, b) in enumerate(edges):
        wps = manual_wps.get((a, b))
        if not wps:
            continue
        A, B = nodes_px[a], nodes_px[b]
        # T2 caliber (plan A, jacky-approved): endpoint = the standard anchor
        # nearest to the border point aimed at the first/last waypoint
        # (anchors.py 16-point set). If a sibling edge needs the same anchor,
        # anchor_snap's give-way machinery moves the waypoint endpoint along
        # the same 16-set ladder -- so the delivered endpoint is always the
        # nearest FEASIBLE member of the set and the anchors_standard hard
        # gate holds wherever the drag is uncontested. The JS preview mirrors
        # the SAME rule for the common case (reanchorFree / pinEdge /
        # applyUserWps via stdAnchorToward: nearest standard anchor not
        # already held by another edge's endpoint), so preview and CLI
        # deliver identical endpoints on uncontested drags.
        pa_bp = border_point(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                             wps[0][0] - A[0], wps[0][1] - A[1])
        pa = _nearest_anchor(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                             pa_bp[0], pa_bp[1])[1:]
        pb_bp = border_point(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                             wps[-1][0] - B[0], wps[-1][1] - B[1])
        pb = _nearest_anchor(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                             pb_bp[0], pb_bp[1])[1:]
        pts = [list(pa)] + [[float(px), float(py)] for px, py in wps] + [list(pb)]
        dedup = [pts[0]]
        for q in pts[1:]:
            if math.dist(dedup[-1], q) > 0.5:
                dedup.append(q)
        routes[i] = {"kind": "waypoints", "points": dedup, "press": 0,
                     "min_clear": None, "cross": 0, "cross_edges": 0,
                     "ang_a": 0.0, "ang_b": 0.0}
    if manual_wps and from_meta is not None:
        from_meta["waypoint_edges"] = len(manual_wps)
    # v0.7.7 per-edge forced styles (demo-2d style cycle export): "straight"
    # = direct line between box-border anchors facing each other; "arc" =
    # the deterministic forced-arc rule (_forced_arc_route). "free" is
    # carried by waypoints above. These edges skip the candidate pool; the
    # geometry/certificate recheck scores them honestly (no leniency).
    manual_styles = {}
    arc_ctrls = {}
    if manual is not None:
        manual_styles = _manual_edge_styles(manual, edges)
        arc_ctrls = _manual_arc_ctrls(manual, edges)
    for i, (a, b) in enumerate(edges):
        if manual_wps.get((a, b)):
            continue
        st = manual_styles.get((a, b))
        if st == "straight":
            A, B = nodes_px[a], nodes_px[b]
            pa = border_point(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                              B[0] - A[0], B[1] - A[1])
            pb = border_point(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                              A[0] - B[0], A[1] - B[1])
            routes[i] = {"kind": "line", "points": [list(pa), list(pb)],
                         "press": 0, "min_clear": None, "cross": 0,
                         "cross_edges": 0, "ang_a": 0.0, "ang_b": 0.0}
        elif st == "arc":
            arc_ctrl = arc_ctrls.get((a, b))
            if arc_ctrl is not None:
                # final-form exported ctrl: replay the viewer's live quad
                # verbatim on the facing-border chord (the T1 pass below
                # re-projects the endpoints onto their resolved anchors and
                # keeps this ctrl untouched -- no further translation)
                from .routing import quad_points as _qp_ctrl
                A, B = nodes_px[a], nodes_px[b]
                pa = border_point(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                                  B[0] - A[0], B[1] - A[1])
                pb = border_point(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                                  A[0] - B[0], A[1] - B[1])
                pts = _qp_ctrl(pa, arc_ctrl, pb)
                routes[i] = {"kind": "arc", "points": [list(p) for p in pts],
                             "ctrl": [float(arc_ctrl[0]), float(arc_ctrl[1])],
                             "ctrl_final": True,
                             "press": 0, "min_clear": None, "cross": 0,
                             "cross_edges": 0, "ang_a": 0.0, "ang_b": 0.0}
            else:
                pts, ctrl = _forced_arc_route(nodes_px, a, b, cfg.clearance)
                routes[i] = {"kind": "arc", "points": [list(p) for p in pts],
                             "press": 0, "min_clear": None, "cross": 0,
                             "cross_edges": 0, "ang_a": 0.0, "ang_b": 0.0,
                             "ctrl": list(ctrl)}
    if manual_styles and from_meta is not None:
        from_meta["styled_edges"] = len(manual_styles)
    # T1: user-specified standard anchors (demo-2d endpoint
    # drag / anchor click export, edges[].anchors). A designated endpoint is
    # placed EXACTLY on the standard anchor coordinate (anchors.py caliber)
    # and the edge joins the frozen set below (same family as the manual-
    # waypoint freeze) so the later repair passes leave it untouched.
    # Straight / arc / waypoint routes all honor the designation; an arc ctrl
    # translates with the mean endpoint delta (viewer arcEpPts caliber); the
    # unspecified end keeps its existing route endpoint (viewer endPt
    # fallback caliber). A designated endpoint on a vg polyline collapses the
    # route to the straight line between the (possibly moved) endpoints --
    # corner/fillet geometry would be stale after an endpoint move, and the
    # recheck grades the result honestly. Same geometry/certificate recheck,
    # no leniency.
    manual_anchors = {}
    if manual is not None:
        manual_anchors = _manual_anchors(manual, edges)
    if manual_anchors:
        from .routing import quad_points as _quad_points

        def _anchor_xy(A, aid):
            for p in _standard_anchors(A[0], A[1], A[2] / 2.0, A[3] / 2.0):
                if p[0] == aid:
                    return (p[1], p[2])
            raise ValueError(f"anchor id not resolvable: {aid!r}")   # guarded by _manual_anchors

        for i, (a, b) in enumerate(edges):
            sel = manual_anchors.get((a, b))
            if not sel:
                continue
            A, B = nodes_px[a], nodes_px[b]
            r = routes[i]
            # T1: per-end user designation marker -- anchor_snap / lens joint
            # passes treat these ends as frozen (never re-anchored, never
            # counted as snap failures), same family as waypoint-kind edges.
            _ua = {}
            if "src" in sel:
                _ua[0] = sel["src"]
            if "dst" in sel:
                _ua[1] = sel["dst"]
            r["ua_ends"] = _ua
            pts = r["points"]
            pa0, pb0 = list(pts[0]), list(pts[-1])
            # Caliber: the designated end lands EXACTLY on its standard
            # anchor; the unspecified sibling end snaps to the standard
            # anchor nearest to the border point aimed at the designated
            # end (same 16-set nearest-anchor family as the waypoint/free
            # endpoint override -- anchors_standard then holds by
            # construction even when the underlying route is a raw
            # border-point lane polyline). Contested slots are resolved
            # downstream by anchor_snap's give-way ladder.
            pa = list(_anchor_xy(A, sel["src"])) if "src" in sel else None
            pb = list(_anchor_xy(B, sel["dst"])) if "dst" in sel else None
            if pa is None:
                pa_bp = border_point(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                                     (pb or pb0)[0] - A[0], (pb or pb0)[1] - A[1])
                pa = list(_nearest_anchor(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                                          pa_bp[0], pa_bp[1])[1:])
            if pb is None:
                pb_bp = border_point(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                                     pa[0] - B[0], pa[1] - B[1])
                pb = list(_nearest_anchor(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                                          pb_bp[0], pb_bp[1])[1:])
            if r["kind"] == "arc":
                if r.get("ctrl_final"):
                    # exported final-form ctrl: the viewer's live quad is
                    # replayed verbatim on the resolved anchor endpoints --
                    # no further translation (that is the preview==rerender
                    # contract)
                    ctrl = [float(c) for c in r["ctrl"]]
                    n = max(len(pts) - 1, 2)
                    r["points"] = [[float(x), float(y)]
                                   for x, y in _quad_points(pa, ctrl, pb, n)]
                    r["ctrl"] = ctrl
                else:
                    ctrl0 = r.get("ctrl") or [(pa0[0] + pb0[0]) / 2.0,
                                              (pa0[1] + pb0[1]) / 2.0]
                    ctrl = [ctrl0[0] + ((pa[0] - pa0[0]) + (pb[0] - pb0[0])) / 2.0,
                            ctrl0[1] + ((pa[1] - pa0[1]) + (pb[1] - pb0[1])) / 2.0]
                    n = max(len(pts) - 1, 2)
                    r["points"] = [[float(x), float(y)]
                                   for x, y in _quad_points(pa, ctrl, pb, n)]
                    r["ctrl"] = ctrl
            else:
                if r["kind"] == "vg":
                    r.pop("vg_corners", None)
                    r.pop("vg_fillets", None)
                    r["kind"] = "line"
                pts[0] = [float(pa[0]), float(pa[1])]
                pts[-1] = [float(pb[0]), float(pb[1])]
                if r["kind"] == "waypoints":
                    dedup = [pts[0]]
                    for q in pts[1:]:
                        if math.dist(dedup[-1], q) > 0.5:
                            dedup.append(q)
                    r["points"] = dedup
    if manual_anchors and from_meta is not None:
        from_meta["anchor_edges"] = len(manual_anchors)
        from_meta["user_anchors"] = {f"{a}->{b}": dict(sel)
                                     for (a, b), sel in sorted(manual_anchors.items())}
    _timing.mark("manual_injection")
    # ref-scrubbed: directed rerouting for line-line visual coincidence - a backstop fix for fan-out edges hugging the same corridor (stair/lane
    # shared lanes). Constructed routes and user-anchored waypoint edges are untouched; only edges involved in coincident pairs are rerouted,
    # on the condition that the hard gates do not regress (press/clearance/anchor/crossing count).
    _frozen = set()
    for i, (a, b) in enumerate(edges):
        if constructed.get((a, b)) is not None or manual_wps.get((a, b)) \
                or manual_styles.get((a, b)) or manual_anchors.get((a, b)):
            _frozen.add(i)
    routes = router.coincide_reroute(routes, frozen=_frozen)
    _timing.mark("repair:coincide")
    # ref-scrubbed connection-point caliber: delivery-layer anchors are clamped to the edge-midpoint +/-1/4 band (corners excluded, per-edge
    # hard-gate recheck); multiple anchors on the same side of the same node are then evenly spread by incidence angle (no stacking).
    # ref-scrubbed: the enhanced channel (ctrl-following stair + in-band local rerouting of mutual pairs) is enabled only for spine-wing
    # placement - the ring/bowtie baselines have registered out-of-band anchors (mutual-pair baseline fallback), and the fix would change
    # their delivered bytes (including the viewBox dx shift knock-on), conflicting with this card's "the other 18 graphs byte-for-byte zero
    # drift" hard gate -> this card fixes only spine-wing (classic-cld); the other engines get their CI anchor gate locked to the v0.7.2
    # baseline ratio against regression, and out-of-band fixes go to a later card.
    routes = router.midband_reanchor(routes, frozen=_frozen,
                                     enhanced=(engine == "spine-construct"))
    _timing.mark("repair:midband")
    routes = router.fan_spread(routes, frozen=_frozen)
    _timing.mark("repair:fan_spread")
    # ref-scrubbed rework (1): mutual-pair "straight-feasible" candidates join the cost allocation (§WS3 polyline = last resort - when a
    # straight line is feasible the polyline does not steal the score). The poly side lanes produced by the in-band backstop
    # (_reroute_pair_band) are rechecked here: if a straight candidate among the 4 edge-midpoint anchors of the two boxes is feasible and
    # scores better overall, replace it (quickfix->crowding measured: a 298px polyline -> a 101px natural straight line).
    # Enabled only in the spine-construct domain (classic-cld the only hit): the other engines never enter the new code path, output
    # byte-for-byte unchanged (structural zero drift).
    if engine == "spine-construct":
        routes = router.mutual_straight_reroute(routes, frozen=_frozen)
        _timing.mark("repair:mutual_straight")
    # ref-scrubbed: mutual-pair lens arrival channel -- flip the pair's shared
    # arc bulge when that turns both arrows into near-normal arrivals
    # (gate-guarded; untouched routes returned byte-for-byte otherwise).
    routes = router.mutual_arrival_flip(routes, frozen=_frozen)
    _timing.mark("repair:arrival_flip_pre")
    # ref-scrubbed: default endpoint snapping to the 16 standard per-box anchor
    # set (anchors.py caliber) -- jacky 2026-11-09: the standard connection
    # points are the DEFAULT attachment caliber of every rendered endpoint,
    # not only the interactive layer.  Gate-checked nearest-anchor assignment
    # with per-(node, anchor) occupancy + fixpoint sweeps (see
    # Router.anchor_snap for the algorithm path); runs across every auto
    # engine -- a static render may not show any off-grid endpoint.
    # Waypoint-kind edges (bend-handle exports) deliver their endpoints ON
    # the 16-anchor set by construction (snap-to-nearest-anchor caliber
    # shared with the JS preview layer), so anchor_snap has nothing to move
    # on them: they are neither re-anchored nor counted as snap failures
    # (their anchored state is the documented waypoints caliber).
    _density = len(edges) / max(len(nodes), 1)
    _snap_deferred = None
    _snap_reverted = False
    if _density >= ANCHOR_SNAP_DENSE_E_OVER_N:
        # ref-scrubbed finalize (approved 2026-11-09): density-gated
        # snap probe.  A static scalar density threshold cannot separate the
        # classic corpus (classic-cld E/N = 13/8 = 1.62, snaps clean -- 21/21
        # green) from the random dense n10 corpus (E/N = 16/10 = 1.60, snap
        # conflicts with the detour-poly routing: measured on n10-i05
        # visual_crossings 4 / 1 endpoint unanchored / line-line coincidence),
        # and the failing case's max degree (4) is LOWER than classic-cld's
        # (7).  So the density threshold switches snap into PROBE mode: apply
        # the snap on a working copy, re-evaluate the hard gates (visual
        # crossings + line-line coincidence + full anchor membership); keep
        # the snapped routes only at zero regressions, otherwise revert to
        # the pre-snap routes and record an honest deferral (the certificate
        # reports the deferral with its measured reason and the gate stays
        # measured -- no gate fudging; dense-snap specialization is a
        # follow-up card).  Low-density graphs run the same probe with a
        # lighter accounting: crossings / coincidence worsening still reverts,
        # but endpoint failures neither revert nor defer (see the else branch
        # below -- the deferral semantics stay dense-only).
        _pre_pairs = router.final_crossing_pairs(routes)
        _pre_coincide = len(router._route_coincide_pairs(routes))
        _pre_routes = {i: _clone_route(routes[i]) for i in routes}
        _timing.mark("anchor_snap.gate_eval_pre")
        _snap_report = router.anchor_snap(routes)
        _timing.mark("anchor_snap.snap")
        _regress = []
        _post_pairs = router.final_crossing_pairs(routes)
        if _post_pairs > _pre_pairs:
            _regress.append(f"crossings {_pre_pairs}->{_post_pairs}")
        _post_coincide = len(router._route_coincide_pairs(routes))
        if _post_coincide > _pre_coincide:
            _regress.append(f"line_coincidence {_pre_coincide}->{_post_coincide}")
        if _snap_report["failures"]:
            _regress.append(f"{len(_snap_report['failures'])} endpoint(s) unanchored")
        _timing.mark("anchor_snap.gate_eval_post")
        if _regress:
            routes = _pre_routes
            _snap_deferred = {"density_en": round(_density, 2),
                              "reason": _regress,
                              "moved_before_revert": _snap_report["moved"]}
            print(f"[stdraw] anchor_snap DEFERRED (dense, E/N={_density:.2f}): "
                  f"{'; '.join(_regress)} -- pre-snap routes kept", file=sys.stderr)
        else:
            print(f"[stdraw] anchor_snap: {_snap_report['moved']} endpoints snapped "
                  f"(dense probe, E/N={_density:.2f}, zero gate regressions)",
                  file=sys.stderr)
    else:
        # T5 (ref-scrubbed card): the degradation-revert probe now covers
        # EVERY density, not only E/N >= 1.6.  The low-density snap keeps its
        # unconditional character (same candidate ladder, same gates), but it
        # is no longer blind: crossings / line-line coincidence are recounted
        # on the snapped routes and any worsening reverts to the pre-snap
        # routes (measured reason on stderr).  Endpoint snap failures alone
        # do NOT trigger a revert or a deferral here: "unplaceable endpoints
        # defer the whole snap" stays a dense-only behavior (an honest
        # unanchored endpoint keeps being reported by the certificate's
        # anchors_standard gate instead).
        _pre_pairs = router.final_crossing_pairs(routes)
        _pre_coincide = len(router._route_coincide_pairs(routes))
        _pre_routes = {i: _clone_route(routes[i]) for i in routes}
        _timing.mark("anchor_snap.gate_eval_pre")
        _snap_report = router.anchor_snap(routes)
        _timing.mark("anchor_snap.snap")
        _regress = []
        _post_pairs = router.final_crossing_pairs(routes)
        if _post_pairs > _pre_pairs:
            _regress.append(f"crossings {_pre_pairs}->{_post_pairs}")
        _post_coincide = len(router._route_coincide_pairs(routes))
        if _post_coincide > _pre_coincide:
            _regress.append(f"line_coincidence {_pre_coincide}->{_post_coincide}")
        _timing.mark("anchor_snap.gate_eval_post")
        if _regress:
            routes = _pre_routes
            _snap_reverted = True
            print(f"[stdraw] anchor_snap REVERTED (E/N={_density:.2f}): "
                  f"{'; '.join(_regress)} -- pre-snap routes kept", file=sys.stderr)
        else:
            if _snap_report["failures"]:
                print(f"[stdraw] anchor_snap: {_snap_report['moved']} endpoints snapped, "
                      f"{len(_snap_report['failures'])} endpoint(s) could not be placed "
                      f"on a standard anchor: {_snap_report['failures'][:5]}",
                      file=sys.stderr)
    # ref-scrubbed: re-run the lens arrival channel AFTER snapping -- snap moves
    # lens arc endpoints/ctrl, so the arrival-normal caliber (<=10 deg) and the
    # pair separation may degrade.  The flip re-derives ctrl only (endpoints
    # stay on their anchors -> anchors_standard membership preserved) and is
    # strict-improvement + hard-gate guarded; enhanced_gates switches to the
    # anchor-snap gate accounting (see Router.mutual_arrival_flip).  Skipped
    # on deferral (dense) or revert (any density): the restored routes already
    # passed the pre-snap flip above, and re-flipping unsnapped routes under
    # the enhanced accounting would perturb the honest pre-snap state.
    if _snap_deferred is None and not _snap_reverted:
        # ref-scrubbed: joint anchor re-assignment for lens pairs whose
        # post-snap flip still exceeds the arrival target (non-mirrored
        # joint assignments; strict improvement only, else untouched).
        routes = router.lens_joint_reassign(
            routes, _snap_report.get("lens_pairs", []))
        _timing.mark("repair:lens_joint_reassign")
        routes = router.mutual_arrival_flip(routes, enhanced_gates=True)
        _timing.mark("repair:arrival_flip_post")
    router_pairs = router.final_crossing_pairs(routes)

    # ref-scrubbed R/B loop coloring: edge -> the set of declared-loop kinds it belongs to (deterministic rules in docs/layout-modes.md):
    # a single loop in a single color (R=amber/B=sky blue); multiple loops of the same color take that color; multiple loops of different
    # colors or no loop -> neutral (rendering layer slate); polarity (+/-) data unchanged.
    _eset_dir = {(e.a, e.b) for e in graph.edges}
    _edge_loops = defaultdict(set)
    for lp in getattr(graph, "loops", []):
        seq = list(lp.nodes)
        kind = getattr(lp, "kind", None)
        if not kind:
            continue
        for i in range(len(seq)):
            a, b = seq[i], seq[(i + 1) % len(seq)]
            if (a, b) in _eset_dir:
                _edge_loops[(a, b)].add(kind)
            elif (b, a) in _eset_dir:
                _edge_loops[(b, a)].add(kind)
    _LOOP_COLORS = {"R": "#d97706", "B": "#0284c7"}   # R=amber, B=sky blue (online convention)

    edges_out = []
    for i, (a, b) in enumerate(edges):
        info = routes[i]
        kinds = sorted(_edge_loops.get((a, b), ()))
        loop_color = (_LOOP_COLORS[kinds[0]] if len(set(kinds)) == 1
                      else None)
        e = {"a": a, "b": b, "polarity": getattr(graph.edges[i], "polarity", "+"),
             "loop_kinds": kinds,
             "loop_color": loop_color,
             "route": {"kind": info["kind"],
                       "points": [[round(px, 1), round(py, 1)]
                                  for px, py in info["points"]]},
             "anchors": {"a": list(info["points"][0]), "b": list(info["points"][-1])},
             "arrow": [round(info["points"][-1][0], 1), round(info["points"][-1][1], 1)],
             "route_cross_edges": int(info.get("cross_edges", 0))}  # diagnostic value from the evaluation period
        if info["kind"] == "arc":
            e["route"]["arc"] = True
            e["route"]["ctrl"] = [round(c, 1) for c in info.get("ctrl", info["points"][len(info["points"]) // 2])]
        if info["kind"] == "vg":
            # stash raw corner/arc parameters; the SVG path is generated after the dx shift (see finalize below)
            e["_vg"] = ([list(p) for p in info["vg_corners"]],
                        [dict(f) for f in info["vg_fillets"]])
        if info["kind"] == "waypoints":
            # ref-scrubbed: user-anchored bends (the via is generated on delivered coordinates after the dx/dy shift, see finalize below
            # - isomorphic to vg's _vg handling)
            e["_wp"] = [[float(px), float(py)] for px, py in info["points"]]
        edges_out.append(e)

    xs_all = [pos[v] - widths[v] / 2 for v in nodes] + [pos[v] + widths[v] / 2 for v in nodes]
    ys_all = [y[v] - card_h / 2 for v in nodes] + [y[v] + card_h / 2 for v in nodes]

    # F3 rework (ref-scrubbed, bullwhip check7 fail): an arc bulge can cross the node-box outer envelope (measured: inventory->forecast
    # bulged 7.5px left past the viewBox left edge, while since v0.2 the viewBox is computed from node boxes only). Edge geometry (sampled
    # points plus arc ctrl - a quadratic-Bezier convex-hull upper bound, conservative) must enter the shift amounts and the W/H
    # computation together with the node boxes; routing-layer decisions are untouched, the viewBox is only widened at the delivery layer,
    # constructively consistent with check7's "all content inside the viewBox" validation caliber (which reads the delivered route.points
    # directly).
    def _edge_geom_bounds():
        exs, eys = [], []
        for e in edges_out:
            for px, py in e["route"]["points"]:
                exs.append(px)
                eys.append(py)
            c = e["route"].get("ctrl")
            if c:
                exs.append(c[0])
                eys.append(c[1])
        return exs, eys

    exs0, eys0 = _edge_geom_bounds()
    min_x = min(xs_all + exs0) - cfg.margin / 2
    dx = max(0, int(math.ceil(cfg.margin / 2 - min_x)))
    dx = ((dx + 23) // 24) * 24          # shift aligned to 24px, keeping the column snap/grid unchanged
    min_y = min(ys_all + eys0) - cfg.margin / 2
    dy = max(0, int(math.ceil(cfg.margin / 2 - min_y)))
    dy = ((dy + 7) // 8) * 8             # 8px alignment: keeps the 2px grid and the H rounding caliber
    if dx or dy:
        for e in edges_out:
            e["route"]["points"] = [[px + dx, py + dy] for px, py in e["route"]["points"]]
            e["anchors"] = {"a": [e["anchors"]["a"][0] + dx, e["anchors"]["a"][1] + dy],
                            "b": [e["anchors"]["b"][0] + dx, e["anchors"]["b"][1] + dy]}
            e["arrow"][0] += dx
            e["arrow"][1] += dy
            if "ctrl" in e["route"]:      # bugfix: arc control points must shift with dx/dy
                e["route"]["ctrl"][0] += dx
                e["route"]["ctrl"][1] += dy
        for v in nodes:
            pos[v] += dx
            y[v] += dy
        # ref-scrubbed: absolute axis coordinates in the placement metadata shift in sync (symmetry axis / column axis)
        if isinstance(pos_meta, dict):
            if isinstance(pos_meta.get("symmetry"), dict):
                pos_meta["symmetry"]["axis_x"] = \
                    pos_meta["symmetry"].get("axis_x", 0) + dx
                pos_meta["symmetry"]["axis_y"] = \
                    pos_meta["symmetry"].get("axis_y", 0) + dy
            if isinstance(pos_meta.get("column"), dict):
                pos_meta["column"]["axis_x"] = \
                    pos_meta["column"].get("axis_x", 0) + dx
            # ref-scrubbed spine-wing: the vertical axis / midline axis shift in sync with the translation
            if isinstance(pos_meta.get("spine_wing"), dict):
                pos_meta["spine_wing"]["axis_x"] = \
                    pos_meta["spine_wing"].get("axis_x", 0) + dx
                pos_meta["spine_wing"]["axis_y"] = \
                    pos_meta["spine_wing"].get("axis_y", 0) + dy
            # v0.7.7 comb-bilateral: the column axis / hub row shift in sync
            if isinstance(pos_meta.get("comb"), dict):
                pos_meta["comb"]["axis_x"] = \
                    pos_meta["comb"].get("axis_x", 0) + dx
                pos_meta["comb"]["hub_y"] = \
                    pos_meta["comb"].get("hub_y", 0) + dy

    # W/H must be taken on the final post-shift coordinates. bugfix (a v0.2.0 leftover exposed by CI): the original implementation computed
    # W from the pre-shift xs_all; with dx>0 the content overflowed the viewBox after the right shift (analytic box widths are narrower
    # without fonts -> the min left edge violates and triggers a large dx -> the right edge spills). F3 rework addendum: max also includes
    # edge geometry, so arc/vg bulges must not cross the right/bottom edges.
    xs_all = [pos[v] - widths[v] / 2 for v in nodes] + [pos[v] + widths[v] / 2 for v in nodes]
    ys_all = [y[v] - card_h / 2 for v in nodes] + [y[v] + card_h / 2 for v in nodes]
    exs1, eys1 = _edge_geom_bounds()
    W = int(math.ceil(max(xs_all + exs1))) + cfg.margin
    H = int(math.ceil(max(ys_all + eys1))) + cfg.margin
    W = ((W + 7) // 8) * 8
    H = ((H + 7) // 8) * 8

    # WS3 finalize: vg routes generate the exact SVG path (L+A commands) on the delivered post-shift coordinates
    from .visibility import route_svg_d as _route_svg_d
    for e in edges_out:
        vg = e.pop("_vg", None)
        if vg:
            corners, fillets = vg
            corners = [[p[0] + dx, p[1] + dy] for p in corners]
            fillets = [dict(f, ta=[f["ta"][0] + dx, f["ta"][1] + dy],
                            tb=[f["tb"][0] + dx, f["tb"][1] + dy],
                            center=[f["center"][0] + dx, f["center"][1] + dy])
                       for f in fillets]
            e["route"]["path_d"] = _route_svg_d(corners, fillets)
            e["route"]["via"] = [[round(px, 1), round(py, 1)] for px, py in corners]
        wp = e.pop("_wp", None)
        if wp:
            # ref-scrubbed: user-anchored bends enter delivery (post-shift coordinates; rendering draws a polyline)
            e["route"]["via"] = [[round(p[0] + dx, 1), round(p[1] + dy, 1)]
                                 for p in wp[1:-1]]

    if manual is not None:
        row_y_out = [yy + dy for yy in sorted({y[v] for v in nodes})]
        pitch_out = None
    elif engine in ("ring-construct", "comb-construct"):
        # ring/comb placement have no uniform-row semantics: rowY records the
        # deduplicated order of actual y values; pitch does not apply
        row_y_out = [yy + dy for yy in sorted({y[v] for v in nodes})]
        pitch_out = None
    else:
        row_y_out = [dy + cfg.top + r * cfg.pitch for r in range(len(rows))]
        pitch_out = cfg.pitch
    # ref-scrubbed: assemble the mode decision trace (certificate mode_decision_trace).
    # The anchor-band legacy exemption (v0.7.3 registered baselines): the
    # enhanced mid-band re-anchor + mutual-straight reroute channels run only
    # for spine-wing; every other engine keeps its registered v0.7.2 baseline
    # in-band ratio (CI BASELINE_BAND lock) instead of the enhanced fix — that
    # registered exemption is disclosed here rather than silently applied.
    _engine_placement = {"sym-construct": "symmetric",
                         "bowtie-construct": "bowtie-vertex",
                         "spine-construct": "spine-wing",
                         "comb-construct": "comb-bilateral",
                         "column-construct": "column-chain",
                         "ring-construct": "ring-cycle",
                         "manual": "manual"}
    _final_placement = ((pos_meta.get("placement")
                         if isinstance(pos_meta, dict) else None)
                        or _engine_placement.get(engine, "layered"))
    if engine == "manual":
        _mode_trace = {"engine": "manual", "placement": None, "manual": True,
                       "rules": [],
                       "fallback": {"used": False, "reason": None},
                       "legacy_band_exemption": {
                           "triggered": False,
                           "detail": ("manual layout: the auto mode chain did "
                                      "not run; routing hard gates still "
                                      "apply, graded honestly")}}
    else:
        _legacy = engine != "spine-construct"
        _mode_trace = {
            "engine": engine, "placement": _final_placement, "manual": False,
            "rules": _mode_rules,
            "fallback": {"used": engine not in _engine_placement,
                         "reason": ("no structural mode triggered — layered "
                                    "path" if engine not in _engine_placement
                                    else None)},
            "legacy_band_exemption": {
                "triggered": _legacy,
                "detail": (f"{_final_placement}: keeps the registered v0.7.2 "
                           "anchor-band baseline ratios (CI BASELINE_BAND "
                           "lock); the enhanced mid-band re-anchor + "
                           "mutual-straight reroute channels are spine-wing "
                           "only"
                           if _legacy else
                           "spine-wing: 100% in-band enforced (enhanced "
                           "re-anchor channel active, no legacy exemption)")},
        }
    v4 = {
        "viewBox": [0, 0, W, H],
        "nodes": {v: {"x": pos[v], "y": y[v], "w": widths[v]} for v in nodes},
        "edges": edges_out,
        "bars": {},
        "meta": {
            "rows": len(row_y_out),
            "rowY": row_y_out,
            "pitch": pitch_out,
            "deg0": deg0,
            "cardH": card_h,
            "fs": [cfg.fs_title, cfg.fs_value],
            "recipe": "auto-v2",
            "line_style": linestyle,
            "position_engine": engine,
            # ref-scrubbed: deterministic mode-decision audit trail (which rule
            # hit, why, trial gate, legacy band exemption) — see the certificate
            # field of the same name.
            "mode_decision_trace": _mode_trace,
            # --from-layout metadata (written only on the manual path; the auto path is byte-for-byte unchanged)
            **({} if from_meta is None else {"from_layout": from_meta}),
            "clearance": CLEARANCE,
            "router_cross_pairs": router_pairs,
            # ref-scrubbed finalize: honest dense-snap deferral record (None
            # when snap applied) -- certificate annotates the gate with it.
            "anchor_snap_deferred": _snap_deferred,
            "solver_available": _has_solver(),
            **pos_meta,
            "routing_math": ("visibility-graph Dijkstra shortest path (clearance-"
                             "inflated obstacles) + tangent-arc fillet smoothing "
                             "(G1, clearance-verified); crossing dual-caliber: "
                             "router theory vs Liang-Barsky delivered geometry"),
            "method": ("layered + crossing-minimization (CP-SAT if available) "
                       "with straight/arc first-class routing and visibility-graph "
                       "detour; hard gates: box-over-line=0, edge-box clearance>=16px"),
        },
    }
    from .delivery import stamp_coordinates_only
    _timing.mark("delivery")
    _timing.finish()
    return stamp_coordinates_only(v4)
