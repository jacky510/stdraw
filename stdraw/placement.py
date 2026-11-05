# -*- coding: utf-8 -*-
"""槽位离散化放置层（WS2 第 6 项）：结构检测驱动的规律槽位。

设计（docs/crossing-exact.md §6 同源）：

- **结构驱动槽型**：
    cycle 图 → 正 k 边形槽位（角度均分 i·2π/k；环序指派使环边全在凸包上
               → 交叉按构造 = 0；正多边形偏差按构造 = 0）——构造法，无需求解器；
    chain 图 → 共线等距槽位（直线度按构造 = 1；相邻边几何重叠由下游布线层
               以弧线消解，中心口径的交叉/规律指标不受影响）——构造法；
    general  → 分层行槽位 + CP-SAT（唯一需要求解器的分支）。
- **CP-SAT 分支硬约束**（违反即不可行）：
    1) 行内卡净距 ≥ min_gap（≥16px 门留余量）；
    2) 框不压线（含 1px 余量）：跨行边在中间行处的插值 x 与无关框缘
       距离 ≥ CLEARANCE（t ∈ {1/2,1/3,2/3,3/4,1/4} 精确线性化，
       其余插值系数用保守双端约束）；
    3) viewBox 内：槽位域限定。
- **CP-SAT 目标**：min 60·Σ交叉 + Σ|Δx|（交叉为主、行内均匀为辅——
   与 auto-v2 定位目标同构）。
- **确定性**：num_workers=1 + seed 42；不设墙钟时限（时限随负载漂移）。
- **交付纪律**：返回坐标后由调用方跑 metrics/check 硬门复核，任何违例
  回退 auto-v2 构造法——本层绝不带伤交付。
- **诚实边界**：cycle/chain 分支的「规律最优」是相对槽位模型类而言
  （正多边形槽 + 声明环序指派），不是全排列最优性证明；general 分支的
  交叉目标是行槽保守口径（近距不算），求解到 OPTIMAL 才是该口径最优。
"""
import math

SLOT = 24
CLEARANCE = 16 + 1     # 16px 硬门 + 1px 余量


def has_solver():
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        return True
    except Exception:
        return False


def place(graph, widths, rows=None, card_h=44, pitch=80, top=92, margin=44,
          min_gap=18, target_w=1280):
    """槽位放置入口。返回 {x, y, viewBox, structure, engine} 或 None（回退）。

    graph: stdraw.model.Graph；widths: {v: 卡宽}；rows: 分层行（general 用）。
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
    """正 k 边形槽位（角度均分，环序指派）。交叉 0、偏差 0 按构造成立。

    量化用 2px 网格（交付坐标口径）：24px 粗量化会显著扭曲正多边形，
    抬高 radial/angular CV——规律指标跑在交付坐标上，量化必须够细。"""
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
    """共线等距槽位（声明链序）。直线度 1 按构造成立。"""
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
    """分层行槽位 + CP-SAT（唯一需要求解器的分支）。"""
    if not rows:
        return None
    from ortools.sat.python import cp_model
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    n_slots = int(target_w // SLOT) + 1
    m = cp_model.CpModel()
    xs = {v: m.NewIntVar(margin // SLOT, n_slots - 1, f"sx_{v}") for v in nodes}

    # 硬约束 1：行内卡净距（槽位尺度）
    for vs in rows:
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                u, w = vs[i], vs[j]
                need = int(math.ceil((widths[u] + widths[w]) / 2.0 + min_gap)
                           / SLOT) + 1
                d = m.NewIntVar(0, n_slots, "")
                m.AddAbsEquality(d, xs[u] - xs[w])
                m.Add(d >= need)

    # 硬约束 2：跨行边不压无关框（含 1px 余量）
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
                # x_at = xa + (xb − xa)·p_/denom；约束两边乘 denom 整数化
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

    # 目标：交叉（行区间交错 + 端点相对序相反，保守近距不算）+ Σ|Δx|
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
    solver.parameters.num_workers = 1      # 确定性铁律
    solver.parameters.random_seed = 42     # 不设墙钟：时限随负载漂移
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
