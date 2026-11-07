# -*- coding: utf-8 -*-
"""auto 布局层（② 目标函数重构）：分层 + 序/位优化 + 交叉数进目标 + 规律性项。

与 ortho-v1（planar.py，平面嵌入构造法，生产行为 pin 用）的区别：
  - 不要求可平面化：任何 CLD 都可布局，交叉数作为**目标函数的一等项**被显式最小化；
  - 目标 = 交叉数（权重 60）+ Σ|Δx| 边长项（规律性/紧凑）+ 网格吸附（规律性）；
  - 定位可用 OR-Tools CP-SAT（`pip install stdraw[solver]`）精化；未安装时优雅降级
    为确定性构造法（重心序 + 均匀排布），功能齐全、质量退回构造档；
  - 布线交给 routing.Router（直线/弧线一等，框不压线、净距 16px 硬门）。

确定性：CP-SAT 固定 num_workers=1 + random_seed；构造法无 RNG。同输入同输出。
"""
import math
from collections import defaultdict

from . import textmetrics
from .routing import (Router, CLEARANCE, SIDE_MARGIN, PAIR_SEP_W,
                      ANCHOR_MIN_DEG, border_point)


class AutoConfig:
    fs_title: float = 12.5
    fs_value: float = 14.0
    card_min_w: int = 96
    card_h: int = 44
    pitch: int = 80            # 行距：卡 44 + 行间通道 36（绕行车道的净距来源）
    top: int = 92              # 首行中心 y（与停车带净距 ≥18px：28+22=50 → 92-22=70）
    park_y: int = 28           # 孤立节点停车带中心 y
    margin: int = 44
    min_gap: int = 18          # 卡间净距（≥16 门禁留余量）
    clearance: int = 16        # 边-框净距硬门（喂给路由评分）
    grid: int = 8
    snap_regular: int = 24     # 简单图（≤10 节点）正则吸附
    target_w: int = 1280
    target_h: int = 680
    aspect_min: float = 1.5
    park_y: int = 28           # 孤立节点停车带


def _cycle_break(nodes, edges):
    """DFS 破环（声明序确定性），返回 (反转为向后的边集合, DAG 边表)。"""
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
                reversed_idx.add(i)   # 回边：分层时视为 w→v
        state[v] = 2
    for v in nodes:
        if state.get(v, 0) == 0:
            dfs(v)
    dag = []
    for i, (a, b) in enumerate(edges):
        dag.append((b, a) if i in reversed_idx else (a, b))
    return reversed_idx, dag


def _layers(nodes, dag):
    """DAG 最长路分层 + 空层压缩。"""
    preds = defaultdict(list)
    outs = defaultdict(list)
    for a, b in dag:
        preds[b].append(a)
        outs[a].append(b)
    layer = {}
    def calc(v):
        if v in layer:
            return layer[v]
        layer[v] = 0                      # 防环（理论无环，保险）
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


def _solve_positions(nodes, rows, widths, cfg: AutoConfig, linestyle):
    """定位求解器：CP-SAT 可用 → 交叉数+边长+规律目标；否则构造法。

    返回 ({v: x_px}, engine, extra_meta)（框心）。y 由 rows 决定。
    """
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    # 每行最小总宽 → 内容宽度
    row_w = {r: sum(widths[v] for v in vs) + cfg.min_gap * (len(vs) + 1)
             for r, vs in enumerate(rows)}
    content_w = max(row_w.values()) + 2 * cfg.margin
    max_x = int(content_w)

    # 边端行号（用原 y 序比较交叉需要真实 y；用行号即可）
    einfo = []
    for (a, b) in EDGES_REF[0]:
        einfo.append((a, b, row_of[a], row_of[b]))

    # WS5 可扩展性：大图 CP-SAT 求到全局最优不可扩展（交叉对 O(m²) 布尔化后
    # 证明最优耗时随 n 爆炸——n20 实测 5min+ 无解完）。改用 **确定性时间预算**
    # （max_deterministic_time，OR-Tools 的可复现性专用口径：按操作计数而非
    # 墙钟，同版本同输入在任何机器上得到同一 incumbent）。预算取宽：小图
    # （≤10 节点，classic 全域）在预算内照常证到 OPTIMAL，输出与无预算版
    # 逐字节一致；仅 n>10 的新域受预算约束（FEASIBLE 如实标注，不冒充最优）。
    det_budget = CP_SAT_DET_BUDGET if len(nodes) > 10 else None

    if _has_solver():
        snap = cfg.snap_regular if len(nodes) <= 10 else cfg.grid
        res, status = _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, snap,
                                       det_budget)
        if res is None and snap != cfg.grid:      # 24px 吸附不可行 → 退 8px 网格
            res, status = _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x,
                                           cfg.grid, det_budget)
        if res is not None:
            extra = {}
            if det_budget is not None:
                # 仅预算路径（n>10）写入 meta：小图路径保持历史输出逐字节不变
                extra = {"solver_status": status,
                         "solver_det_budget": det_budget}
            return res, "cp-sat", extra
    return _construct_positions(nodes, rows, widths, cfg), "construct", {}


CP_SAT_DET_BUDGET = 8.0   # 确定性时间预算（det 单位；n20 实测 ≈17s 墙钟/8det）


EDGES_REF = [()]   # 模块级引用坑位——由 layout() 注入，避免长参表


def _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, grid, det_budget=None):
    """CP-SAT：决策变量 = 框心 x；目标 = 交叉数 + Σ|Δx|；约束 = 净距/网格/边界。

    det_budget：确定性时间预算（max_deterministic_time，操作计数口径）——
    超预算取当前最优 incumbent（FEASIBLE），不再证最优。None = 无预算（历史
    行为：求到最优为止）。返回 (解 or None, "optimal"/"feasible")。
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
    # 同行净距（中心距 ≥ 全宽和的一半 + 间隙）
    for vs in rows:
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                u, w = vs[i], vs[j]
                need = int(math.ceil((widths[u] + widths[w]) / 2.0) + cfg.min_gap)
                d = m.NewIntVar(0, max_x, "")
                m.AddAbsEquality(d, xs[u] - xs[w])
                m.Add(d >= need)
    # 交叉目标：两独立边行区间交错 → 端点序反转即交叉（保守：近距不算）
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
            # 比较两端点相对序（在两边的最低/最高行处）
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
    # 边长项 |Δx|
    lens = []
    for a, b, _, _ in einfo:
        d = m.NewIntVar(0, max_x, "")
        m.AddAbsEquality(d, xs[a] - xs[b])
        lens.append(d)
    m.Minimize(60 * sum(cross_vars) + sum(lens))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1        # 确定性铁律
    solver.parameters.random_seed = 42
    # 墙钟时限会随机器负载漂移（破坏确定性）——预算只用确定性时间口径；
    # 无预算 = 求到最优（历史行为，小图本来快）
    if det_budget is not None:
        solver.parameters.max_deterministic_time = det_budget
    st = solver.Solve(m)
    if st == cp_model.OPTIMAL:
        return {v: int(solver.Value(xs[v])) for v in nodes}, "optimal"
    if st == cp_model.FEASIBLE:
        return {v: int(solver.Value(xs[v])) for v in nodes}, "feasible"
    return None, "no-solution"


def _construct_positions(nodes, rows, widths, cfg):
    """构造法：重心序 + 行内均匀排布 + 行居中（确定性）。"""
    pos = {}
    order = {}
    for r, vs in enumerate(rows):
        order[r] = sorted(vs)
    # 简单重心扫（3 轮上下交替）
    row_of = {v: r for r, vs in enumerate(rows) for v in vs}
    neigh = defaultdict(list)
    for (a, b) in EDGES_REF[0]:
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
    """路由真值总成本：压线/净距/交叉/重合/边长的加权和（布局层真目标函数）。

    hard_gates：净距/锚点硬罚（1500/条）。默认 False——历史评分口径不变
    （classic 与既有通过实例的 polish 轨迹逐字节保持）；仅在布线质量返修的
    门控重排路径启用。quality：Router 扩充 stair 候选池，同样仅门控路径。
    ref-scrubbed 呼吸感（14 张手动样本：min_card_gap 平均 +35.8px）：新增
    卡间净距目标 36px 的软惩罚（缺多少罚多少 ×8），间距权重升第一梯队；
    不设硬门（挤了由既有净距门兜底）。
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
        if (b, a) in eset:      # F1：互环对净距加严与 _evaluate 同口径
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
    # CI 硬门回喂：交叉边对数 > 2 时重罚（证书 gate crossings ≤ 2）
    total += 1500.0 * max(0, router.final_crossing_pairs(routes) - 2)
    total += 1500.0 * clr_hard
    total += 1500.0 * ang_hard
    # ref-scrubbed 呼吸感：卡间净距 ≥36px 目标（软惩罚，第一梯队）
    ids = list(nodes_px)
    if len(ids) > 1:
        mg = min(rect_gap(*nodes_px[u], *nodes_px[v])
                 for i2, u in enumerate(ids) for v in ids[i2 + 1:])
        total += 8.0 * max(0.0, GAP_TARGET - mg)
    return total, routes, router


GAP_TARGET = 36.0        # 呼吸感：卡间净距目标（jacky 14 张手动样本均值 +35.8px）


def _interleave_count(edges, order):
    """拓扑交错对数（固定行分配下布线不可回避的交叉下界代理）。

    两独立边（无共享端点）的行区间重叠 ≥1 行，且两端点的行内序都反转 →
    交错对。行内序相等（同列）不计数。O(m²) 纯算术，确定性。
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
    """重排目标：交错对为主项，行距×列距边长为次项（并列时保紧凑）。"""
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
    """确定性 (行, 行内序) 局部搜索：最小化拓扑交错对（布线质量返修）。

    邻域 = 全部同row对交换 + 全部单节点跨行移动（保留每行 ≥1 节点）。
    最速下降至局部最优；随后确定性扰动（取当前最优非改进邻点）再下降，
    共 REORDER_CYCLES 轮，全程记录全局最优。无 RNG，同输入同输出。
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
        # 确定性扰动：当前邻域中得分最低的非改进邻点（含并列取首个）
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
    """按重排后的行内序重打包 x（24px 吸附，与 construct 同口径，确定性）。"""
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
    """局部搜索：逐节点 ±24/±48 横移（保同行净距），以路由真值总成本择优。

    CP-SAT 全局定位的补充精化——把「布线可行性」显式喂回定位层。
    确定性：固定遍历序 + 固定扰动集。
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
        # 行内相邻交换（「人工可见更优解」类搬移的机械化）
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
    """--from-layout 边级 waypoints（ref-scrubbed）：{(a,b): [[x,y],...]}。

    demo-2d 折点把手「用户锚定」的导出产物。校验：(a,b) 必须是图的边、
    每个点为二元数值；坐标取整（与节点口径一致）；相邻 <0.5px 的重复点
    去重；去重后为空则视为未锚定。确定性：同输入同输出。
    """
    out = {}
    raw = manual.get("edges")
    if raw is None:
        return out
    if not isinstance(raw, list):
        raise ValueError("手动布局 edges 须为 [{a,b,waypoints}] 列表")
    eset = set(edges)
    for it in raw:
        if not isinstance(it, dict):
            raise ValueError(f"手动布局 edge 项格式不识别：{it!r}")
        a, b = it.get("a"), it.get("b")
        if (a, b) not in eset:
            raise ValueError(f"手动布局 waypoints 引用了图中不存在的边：{a}->{b}")
        wps = it.get("waypoints")
        if wps is None:
            continue
        if not isinstance(wps, list):
            raise ValueError(f"边 {a}->{b} 的 waypoints 须为 [[x,y],...] 列表")
        pts = []
        for p in wps:
            if not isinstance(p, (list, tuple)) or len(p) < 2:
                raise ValueError(f"边 {a}->{b} 的 waypoint 格式不识别：{p!r}")
            try:
                x, y = float(p[0]), float(p[1])
            except (TypeError, ValueError):
                raise ValueError(f"边 {a}->{b} 的 waypoint 坐标非数值：{p!r}")
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"边 {a}->{b} 的 waypoint 坐标非有限值：{p!r}")
            q = (int(round(x)), int(round(y)))
            if not pts or math.dist(pts[-1], q) > 0.5:
                pts.append(q)
        if pts:
            out[(a, b)] = pts
    return out


def _manual_positions(nodes, widths, manual):
    """--from-layout：吃手动布局（layout.json 兼容子集），返回 (pos, y, rows, meta)。

    手动坐标取整并对齐 2px 网格（与几何自检 6b 口径一致，snap 影响如实记录）；
    卡宽按标签用 textmetrics 重算（与自动管线同口径）。id 集合必须与图完全
    一致（缺/多节点 → ValueError，CLI 转诚实报错）。
    """
    mn = manual.get("nodes") or {}
    if not isinstance(mn, dict) or not mn:
        raise ValueError("手动布局缺少 nodes（节点 id→x,y）")
    def _xy(entry):
        if isinstance(entry, dict):
            return entry.get("x"), entry.get("y")
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            return entry[0], entry[1]
        raise ValueError(f"手动布局节点格式不识别：{entry!r}")
    missing = [v for v in nodes if v not in mn]
    extra = [v for v in mn if v not in set(nodes)]
    if missing or extra:
        raise ValueError(f"手动布局与图节点集不一致：缺 {missing}，多 {extra}")
    pos, y, snapped = {}, {}, []
    for v in nodes:
        xv, yv = _xy(mn[v])
        try:
            xi, yi = int(round(float(xv))), int(round(float(yv)))
        except (TypeError, ValueError):
            raise ValueError(f"手动布局节点 {v} 坐标非数值：{xv!r},{yv!r}")
        if xi % 2 or yi % 2:
            snapped.append(v)
        pos[v] = xi - (xi % 2)      # 对齐 2px 网格（几何自检 6b 口径）
        y[v] = yi - (yi % 2)
    rows = [[v for v in nodes if y[v] == yy] for yy in sorted({y[v] for v in nodes})]
    meta = {"source": manual.get("source"),
            "manual_viewBox": manual.get("viewBox"),
            "snapped_to_2px": sorted(snapped)}
    return pos, y, rows, meta


def _ring_trial(plan, nodes, widths, card_h, cfg):
    """环形排布 + 布线试验：硬门代理全过才采纳；否则 None（回退分层，逐字节不变）。

    代理口径与交付证书同源：交叉（路由理论）≤2、框压线=0、边-框净距≥clearance、
    互环对分离 ≥4px、卡间净距 ≥16、锚点平滑 ≥20°。最终以 certificate_auto
    在交付坐标上的复检为准（本层只是采纳/回退的确定性闸门）。
    """
    from . import ringlayout
    from .routing import (min_pair_dist, sample_polyline, ANCHOR_MIN_DEG)
    adj, _ = ringlayout._adjacency(EDGES_REF[0])
    try:
        pos, y, meta = ringlayout.place_ring(plan, widths, card_h, cfg, adj,
                                             EDGES_REF[0])
    except ringlayout.InfeasibleRing:
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    # 卡间净距 ≥16（place_ring 按 18 放置，逐对复核兜底）
    vs = sorted(nodes)
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            a, b = vs[i], vs[j]
            gap_x = abs(pos[a] - pos[b]) - (widths[a] + widths[b]) / 2
            gap_y = abs(y[a] - y[b]) - card_h
            if max(gap_x, gap_y) < cfg.min_gap - 2:      # rect_gap 口径（≥16 门）
                return None
    router = Router(nodes_px, EDGES_REF[0], cfg.clearance, cfg.pitch)
    routes = router.route_all()
    if router.final_crossing_pairs(routes) > 2:
        return None
    eset = set(EDGES_REF[0])
    for i, info in routes.items():
        if info.get("press", 0):
            return None
        clr = info.get("min_clear")
        if clr is None or clr < cfg.clearance:
            return None
        # 锚点平滑代理（与 check 第 4 项同口径）
        pts = info["points"]
        for v, p_idx, n_idx in ((EDGES_REF[0][i][0], 0, 1),
                                (EDGES_REF[0][i][1], len(pts) - 1, len(pts) - 2)):
            p = nodes_px[v]
            a0 = pts[p_idx]
            if (abs(abs(a0[0] - p[0]) - p[2] / 2) > abs(abs(a0[1] - p[1]) - p[3] / 2) + 1e-9
                    and abs(abs(a0[1] - p[1]) - p[3] / 2) > 0.75):
                return None                      # 锚点不在框边
            dx, dy = pts[n_idx][0] - a0[0], pts[n_idx][1] - a0[1]
            n = math.hypot(dx, dy)
            if n < 1e-9:
                return None
            on_x = abs(abs(a0[0] - p[0]) - p[2] / 2) <= abs(abs(a0[1] - p[1]) - p[3] / 2)
            tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
            c = abs(dx * tx + dy * ty) / n
            if math.degrees(math.acos(max(0.0, min(1.0, c)))) < ANCHOR_MIN_DEG:
                return None
    # 互环对分离 ≥4px（F1 口径）
    for i in range(len(EDGES_REF[0])):
        for j in range(i + 1, len(EDGES_REF[0])):
            if EDGES_REF[0][i] != (EDGES_REF[0][j][1], EDGES_REF[0][j][0]):
                continue
            md = min_pair_dist(sample_polyline(routes[i]["points"]),
                               sample_polyline(routes[j]["points"]))
            if md is None or md < 4.0:
                return None
    plan = dict(plan)
    plan["placed"] = (pos, y, meta)
    return plan


def _constructed_gates(nodes_px, edges, routes, cfg, constructed):
    """构造路线（闭合弧/镜像弧）与路由路线的统一硬门代理（ref-scrubbed）。

    与 _ring_trial 同口径：压线=0、边-框净距≥clearance、锚点在框边且平滑
    ≥ANCHOR_MIN_DEG、卡间净距 ≥ min_gap-2、互环对分离 ≥4px、交叉 ≤2。
    返回 True=过门。"""
    from .routing import (dist_point_rect, min_pair_dist, sample_polyline,
                          ANCHOR_MIN_DEG)
    # 卡间净距（rect_gap 口径 ≥ min_gap-2）
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
        # 与 check3 同口径：加密采样复核净距（弦切效应兜底）
        dense = sample_polyline([tuple(p) for p in pts], step=4.0)
        for v, (cx, cy, w, h) in nodes_px.items():
            if v in (a, b):
                continue
            for px, py in dense:
                if dist_point_rect(px, py, cx, cy, w / 2, h / 2) < cfg.clearance:
                    return False
        # 锚点在框边 + 平滑
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
    # 互环对分离 ≥4px
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
    """合并构造路线后的交叉边对数（与 Router.final_crossing_pairs 同口径）。"""
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    return router.final_crossing_pairs(routes)


def _sym_trial(plan, nodes, widths, card_h, cfg):
    """领结对对称排布 + 布线试验闸门：过门才采纳；否则 None（回退，逐字节不变）。"""
    from . import symlayout
    edges = EDGES_REF[0]
    try:
        pos, y, meta, constructed = symlayout.place_bowtie(plan, widths,
                                                           card_h, cfg, edges)
    except symlayout.InfeasibleBowtie:
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    # 线型一致性硬规则：对称结构内不得出现 vg/poly 折线（弧线>直线>折线）
    for i, info in routes.items():
        if info["kind"] in ("vg", "poly", "wrap"):
            return None
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        return None
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def _bowtie_trial(plan, nodes, widths, card_h, cfg):
    """领结共点对称排布 + 布线试验闸门：过门才采纳；否则 None（回退，逐字节不变）。

    ref-scrubbed（美学 v3）：恰 2 个简单环恰共享 1 节点的图（wage-price-spiral
    类，jacky 手拉样本为基准）→ bowtie-vertex 对称排布；全直线构造，
    线型一致性硬规则同 symmetric（禁 vg/poly/wrap 折线）。
    """
    from . import bowtielayout
    edges = EDGES_REF[0]
    try:
        pos, y, meta, constructed = bowtielayout.place_bowtie_vertex(
            plan, widths, card_h, cfg, edges)
    except bowtielayout.InfeasibleBowtieVertex:
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    # 线型一致性硬规则：对称结构内不得出现 vg/poly 折线（弧线>直线>折线）
    for i, info in routes.items():
        if info["kind"] in ("vg", "poly", "wrap"):
            return None
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        return None
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def _spine_trial(plan, nodes, widths, card_h, cfg):
    """纵柱+翼位排布 + 布线试验闸门：过门才采纳；否则 None（回退，逐字节不变）。

    ref-scrubbed（v0.7.1）：中枢对纵柱 + 中线翼位带 + 翼外镜像簇
    （classic-cld-growth-and-burden 类，jacky 手拉样本为基准）；纵柱边
    构造竖直直线注入，其余走 Router 候选池。
    """
    from . import spinewinglayout
    edges = EDGES_REF[0]
    try:
        pos, y, meta, constructed = spinewinglayout.place_spine_wing(
            plan, widths, card_h, cfg, edges)
    except spinewinglayout.InfeasibleSpineWing:
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        return None
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def _column_trial(plan, nodes, widths, card_h, cfg):
    """纵列排布 + 布线试验闸门：过门才采纳；否则 None（回退分层，逐字节不变）。"""
    from . import columnlayout
    from .routing import min_pair_dist, sample_polyline
    edges = EDGES_REF[0]
    adj = columnlayout._adjacency(edges)
    try:
        pos, y, meta, constructed = columnlayout.place_column(
            plan, widths, card_h, cfg, adj, edges)
    except columnlayout.InfeasibleColumn:
        return None
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    for i, (a, b) in enumerate(edges):
        cr = constructed.get((a, b))
        if cr is not None:
            routes[i] = dict(cr)
    if not _constructed_gates(nodes_px, edges, routes, cfg, constructed):
        return None
    return {"placed": (pos, y, meta, constructed), "deg0": plan["deg0"]}


def layout(graph, config: AutoConfig = None, linestyle: str = "straight",
           manual: dict = None):
    """auto 配方入口：图 → v4 兼容布局 dict（含折线/弧线路由 + 元数据）。

    manual：--from-layout 手动布局（{nodes: {id: x,y}, viewBox, source}）。
    给定时跳过分层/定位/精化，按手动坐标走同一布线+交付管线（硬门口径
    不变、如实评分）。manual=None（默认）时代码路径与历史逐字节一致。

    ref-scrubbed 回路主导环形排布：manual=None 时先做确定性触发判定
    （ringlayout.detect_ring），命中且布线试验过门 → 主环正多边形槽位；
    不命中/试验不过 → 既有分层路径（逐字节不变）。
    """
    global EDGES_REF
    cfg = config or AutoConfig()
    EDGES_REF = [tuple((e.a, e.b) for e in graph.edges)]
    nodes = graph.node_ids()
    adj = graph.adj_undirected()
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]

    # ① 框界真值（布局侧）：真实字体度量 + 保守 padding
    widths, heights = {}, {}
    for v in nodes:
        nd = graph.id2node()[v]
        w, h = textmetrics.card_size(nd.label, nd.value, cfg.fs_title, cfg.fs_value,
                                     min_w=cfg.card_min_w)
        widths[v], heights[v] = w, h
    card_h = max(heights.values()) if heights else cfg.card_h

    # ②③ 定位：--from-layout 手动坐标，或自动分层+定位
    _routes_final = None
    constructed = {}
    from_meta = None
    if manual is not None:
        pos, y, rows, from_meta = _manual_positions(nodes, widths, manual)
        deg0 = []
        engine, pos_meta = "manual", {}
    else:
        # ②'' 布局美学 v2（ref-scrubbed，jacky 2026-11-05 全图定调）：模式优先级
        #  = 领结对对称（learning-flywheel 类）→ 纵列（长链/少环，主环 ≤4）
        #  → 环形（回路主导小图，ref-scrubbed）→ 既有分层路径。
        #  每个新模式都带试验闸门：不过门静默回退，回退路径逐字节不变。
        sym_plan = None
        bw_plan = None
        sw_plan = None
        column_plan = None
        ring_plan = None
        if len(nodes) <= 12:
            from . import symlayout as _symlayout
            _sym = _symlayout.detect_bowtie(graph)
            if _sym is not None:
                sym_plan = _sym_trial(_sym, nodes, widths, card_h, cfg)
        # ref-scrubbed（美学 v3）领结共点（双环共享单节点）：与共边领结
        # （symmetric）拓扑互斥、并列最高档；判定用枚举简单环（声明表
        # 混 2 节点伪环、漏派生环，不可用）。
        if sym_plan is None and len(nodes) <= 12:
            from . import bowtielayout as _bowtielayout
            _bw = _bowtielayout.detect_bowtie_vertex(graph)
            if _bw is not None:
                bw_plan = _bowtie_trial(_bw, nodes, widths, card_h, cfg)
        if bw_plan is None and sym_plan is None and len(nodes) <= 12:
            from . import spinewinglayout as _spinewinglayout
            _sw = _spinewinglayout.detect_spine_wing(graph)
            if _sw is not None:
                sw_plan = _spine_trial(_sw, nodes, widths, card_h, cfg)
        if (bw_plan is None and sym_plan is None and sw_plan is None
                and len(nodes) <= 12):
            from . import ringlayout as _ringlayout
            from . import columnlayout as _columnlayout
            _ring_detect = _ringlayout.detect_ring(graph)
            # 纵列只在「环形不走 pure-cycle/ratio 分支」时判定（cover 触发
            # 且主环 ≤4 的图归纵列；k≥5 的大环仍归环形）
            if _ring_detect is None or _ring_detect["trigger"] == "cover":
                _col = _columnlayout.detect_column(graph)
                if _col is not None:
                    column_plan = _column_trial(_col, nodes, widths, card_h, cfg)
            if column_plan is None and _ring_detect is not None:
                ring_plan = _ring_trial(_ring_detect, nodes, widths, card_h, cfg)
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
            # ② 分层（破环 + 最长路 + 空层压缩）
            _, dag = _cycle_break(core, EDGES_REF[0])
            layer = _layers(core, dag)
            nrow = max(layer.values()) + 1 if core else 1
            rows = [[v for v in core if layer[v] == r] for r in range(nrow)]
            rows = [r for r in rows if r]

            # ③ 定位
            pos, engine, pos_meta = _solve_positions(core, rows, widths, cfg, linestyle)

            # y 坐标（行均匀 → 规律性门禁的基座）
            y = {v: cfg.top + r * cfg.pitch for r, vs in enumerate(rows) for v in vs}
            # 孤立节点停车带：顶部均匀排布（小图 24px 列吸附，与正则门禁一致）
            if deg0:
                total = sum(widths[v] for v in deg0) + cfg.min_gap * (len(deg0) + 1)
                cw = _content_w(rows, widths, cfg)
                cur = max(cfg.margin, (cw - total) / 2)
                snap = cfg.snap_regular if len(nodes) <= 10 else cfg.grid
                for v in deg0:
                    pos[v] = int(round((cur + widths[v] / 2) / snap)) * snap
                    y[v] = cfg.park_y
                    cur += widths[v] + cfg.min_gap

            # ③b 局部精化（小图 ≤10 节点）：以路由真值总成本 hill-climb 横移，
            # 把布线可行性（压线/净距/交叉）显式喂回定位层
            if len(core) <= 10:
                pos, _sc, _rt = _polish(core, EDGES_REF[0], rows, pos, y,
                                        widths, card_h, cfg)
                # —— WS3 布线质量返修（随机稠密图 check1 交叉>2 / check3 净距<16）：
                #    布线硬门不过时，布局层瓶颈不在路由（图可平面而摆放把拓扑交错对
                #    顶到 3+，贪心路由只能躲掉一部分）而在「行分配 + 行内序」。触发
                #    确定性 (行,序) 重排 → 24px 重打包 → hard-gate polish，同一评估
                #    口径下与原摆放择优（不劣于基线）。门控触发：硬门本来达标的布局
                #    （classic 全域、既有通过实例）零扰动、输出逐字节不变。
                _r0 = Router({v: (pos[v], y[v], widths[v], card_h) for v in nodes},
                             EDGES_REF[0], cfg.clearance, cfg.pitch)
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
                    # 路由层第二手：交叉对联合重定线（打破互为最优僵局）。
                    # quality=True 才扩充 stair 候选池——门控路径专用，普通路径
                    # （含 polish 的 _route_total）保持历史候选池，通过实例零扰动。
                    _rq = Router({v: (pos[v], y[v], widths[v], card_h) for v in nodes},
                                 EDGES_REF[0], cfg.clearance, cfg.pitch, quality=True)
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
                    # 布局层第二手：确定性 (行,序) 重排 → 24px 重打包 → hard-gate
                    # polish → 路由 → 联合重定线
                    _order2 = _reorder_rows(EDGES_REF[0], rows)
                    _pos2 = _repack_x(_order2, widths, cfg)
                    _y2 = dict(y)
                    for _r, _vs in enumerate(_order2):
                        for _v in _vs:
                            _y2[_v] = cfg.top + _r * cfg.pitch
                    _pos2, _sc2, _rt2 = _polish(core, EDGES_REF[0], _order2, _pos2,
                                                _y2, widths, card_h, cfg,
                                                hard_gates=True)
                    # ref-scrubbed：孤立节点不在 rows（顶部停车带交付），门控重排
                    # 只重排 core——停车带坐标原样带回，Router 全节点键完备
                    # （存量缺口：门控路径在有孤立节点的图上首次触发即 KeyError）
                    for _v in deg0:
                        _pos2.setdefault(_v, pos[_v])
                    _r2 = Router({v: (_pos2[v], _y2[v], widths[v], card_h)
                                  for v in nodes}, EDGES_REF[0], cfg.clearance, cfg.pitch,
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
                        _routes_final = _best[4]      # 摆放未变但路线已换优
                    elif _best[0] < _gate0:
                        pos, y, rows = _best[1], _best[2], _best[3]
                        _routes_final = _best[4]

    # ④ 布线（直线/弧线一等，框不压线）+ WS3 理论口径（最终路线交叉对数）
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, EDGES_REF[0], cfg.clearance, cfg.pitch)
    routes = router.route_all()
    if _routes_final is not None:
        routes = _routes_final
    # ref-scrubbed 构造路线注入（纵列闭合弧/领结镜像弧）：该边不走候选池，
    # 按构造几何交付（试验闸门已复核硬门）；须在 final_crossing_pairs 之前
    # 注入，保证交叉双口径（check11）含构造路线。
    for i, (a, b) in enumerate(EDGES_REF[0]):
        cr = constructed.get((a, b))
        if cr is None:
            continue
        info = {"kind": cr["kind"], "points": [list(p) for p in cr["points"]],
                "press": 0, "min_clear": None, "cross": 0, "cross_edges": 0,
                "ang_a": 90.0, "ang_b": 90.0}
        if cr.get("ctrl") is not None:
            info["ctrl"] = list(cr["ctrl"])
        routes[i] = info
    # ref-scrubbed：用户锚定 waypoints 覆盖（demo-2d 折点把手导出）——该边不走
    # 候选池，按「锚点=框边朝向首/末 waypoint + waypoints 原样」构造交付路线，
    # 几何/证书复检按同一 points 如实评分（不放水）。覆盖须在
    # final_crossing_pairs 之前，保证交叉双口径（check11）含 waypoints。
    manual_wps = {}
    if manual is not None:
        manual_wps = _manual_waypoints(manual, EDGES_REF[0])
    for i, (a, b) in enumerate(EDGES_REF[0]):
        wps = manual_wps.get((a, b))
        if not wps:
            continue
        A, B = nodes_px[a], nodes_px[b]
        pa = border_point(A[0], A[1], A[2] / 2.0, A[3] / 2.0,
                          wps[0][0] - A[0], wps[0][1] - A[1])
        pb = border_point(B[0], B[1], B[2] / 2.0, B[3] / 2.0,
                          wps[-1][0] - B[0], wps[-1][1] - B[1])
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
    # ref-scrubbed：线-线视觉重合定向重定线——扇出边同走廊贴合（stair/lane
    # 共享车道）的兜底修复。构造路线与用户锚定 waypoints 边不动；只对重合
    # 对涉及边在硬门不回退（压线/净距/锚点/交叉数）前提下重定线。
    _frozen = set()
    for i, (a, b) in enumerate(EDGES_REF[0]):
        if constructed.get((a, b)) is not None or manual_wps.get((a, b)):
            _frozen.add(i)
    routes = router.coincide_reroute(routes, frozen=_frozen)
    # ref-scrubbed 连接点口径：交付层锚点钳制到边中点 ±1/4 带（转角排除，
    # 逐边硬门复核）；同节点同侧多锚点再按入射角均匀展开（不堆叠）。
    # ref-scrubbed：增强通道（ctrl 随动阶梯 + 互环对带内局部重定线）仅对
    # spine-wing 排布启用——ring/bowtie 基线存在在册带外锚点（互环对基线
    # 回退），修复会改动其交付字节（含 viewBox dx 平移连带），与本卡
    # 「其余 18 图逐字节零漂移」硬门冲突 → 本卡只修 spine-wing（classic-cld），
    # 其余引擎 CI 锚点门锁 v0.7.2 基线比例防回退，带外修复归后续卡。
    routes = router.midband_reanchor(routes, frozen=_frozen,
                                     enhanced=(engine == "spine-construct"))
    routes = router.fan_spread(routes, frozen=_frozen)
    # ref-scrubbed 返修①：互环对「直线可行」候选纳入代价分配（§WS3 折线=
    # 最后手段——直线可行时折线不抢分）。带内兜底（_reroute_pair_band）
    # 产出的 poly 侧车道在此复检：两框 4 边中点锚 × 直线候选可行且总评
    # 更优则替换（quickfix→crowding 实测 298px 折线→101px 自然直线）。
    # 仅 spine-construct 域启用（classic-cld 唯一命中）：其余引擎不进新
    # 代码路径，输出逐字节不变（结构性零漂移）。
    if engine == "spine-construct":
        routes = router.mutual_straight_reroute(routes, frozen=_frozen)
    router_pairs = router.final_crossing_pairs(routes)

    # ref-scrubbed R/B 回路着色：边 → 所属声明回路 kind 集合（确定性规则见
    # docs/layout-modes.md）：单环单色（R=琥珀/B=天蓝）；多环同色取该色；
    # 多环异色或无环 → 中性（渲染层 slate）；极性（+/-）数据不变。
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
    _LOOP_COLORS = {"R": "#d97706", "B": "#0284c7"}   # R=琥珀 B=天蓝（线上惯例）

    edges_out = []
    for i, (a, b) in enumerate(EDGES_REF[0]):
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
             "route_cross_edges": int(info.get("cross_edges", 0))}  # 评估期诊断值
        if info["kind"] == "arc":
            e["route"]["arc"] = True
            e["route"]["ctrl"] = [round(c, 1) for c in info.get("ctrl", info["points"][len(info["points"]) // 2])]
        if info["kind"] == "vg":
            # 暂存原始角点/弧参数，dx 平移后生成 SVG path（见下方 finalize）
            e["_vg"] = ([list(p) for p in info["vg_corners"]],
                        [dict(f) for f in info["vg_fillets"]])
        if info["kind"] == "waypoints":
            # ref-scrubbed：用户锚定折点（via 在 dx/dy 平移后的交付坐标上生成，
            # 见下方 finalize——与 vg 的 _vg 处理同构）
            e["_wp"] = [[float(px), float(py)] for px, py in info["points"]]
        edges_out.append(e)

    xs_all = [pos[v] - widths[v] / 2 for v in nodes] + [pos[v] + widths[v] / 2 for v in nodes]
    ys_all = [y[v] - card_h / 2 for v in nodes] + [y[v] + card_h / 2 for v in nodes]

    # F3 返修（ref-scrubbed，bullwhip check7 fail）：弧线鼓出可越过节点框外包络
    # （实测 inventory->forecast 向左鼓 7.5px 出 viewBox 左缘，而 viewBox 自
    # v0.2 起只按节点框计算）。边几何（采样点 ∪ 弧 ctrl——二次贝塞尔凸包上界，
    # 保守）必须与节点框一并纳入平移量与 W/H 计算；布线层决策不动，只在交付
    # 层扩 viewBox，与 check7「全部内容在 viewBox 内」的校验口径（直接取交付
    # route.points）构造性一致。
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
    dx = ((dx + 23) // 24) * 24          # 平移量对齐 24px，保持列吸附/网格不变
    min_y = min(ys_all + eys0) - cfg.margin / 2
    dy = max(0, int(math.ceil(cfg.margin / 2 - min_y)))
    dy = ((dy + 7) // 8) * 8             # 8px 对齐：保持 2px 网格与 H 取整口径
    if dx or dy:
        for e in edges_out:
            e["route"]["points"] = [[px + dx, py + dy] for px, py in e["route"]["points"]]
            e["anchors"] = {"a": [e["anchors"]["a"][0] + dx, e["anchors"]["a"][1] + dy],
                            "b": [e["anchors"]["b"][0] + dx, e["anchors"]["b"][1] + dy]}
            e["arrow"][0] += dx
            e["arrow"][1] += dy
            if "ctrl" in e["route"]:      # bugfix：弧线控制点必须随 dx/dy 平移
                e["route"]["ctrl"][0] += dx
                e["route"]["ctrl"][1] += dy
        for v in nodes:
            pos[v] += dx
            y[v] += dy
        # ref-scrubbed：排布元数据里的绝对轴坐标随平移同步（对称轴/纵列轴）
        if isinstance(pos_meta, dict):
            if isinstance(pos_meta.get("symmetry"), dict):
                pos_meta["symmetry"]["axis_x"] = \
                    pos_meta["symmetry"].get("axis_x", 0) + dx
                pos_meta["symmetry"]["axis_y"] = \
                    pos_meta["symmetry"].get("axis_y", 0) + dy
            if isinstance(pos_meta.get("column"), dict):
                pos_meta["column"]["axis_x"] = \
                    pos_meta["column"].get("axis_x", 0) + dx
            # ref-scrubbed 纵柱+翼位：竖直轴/中线轴随平移同步
            if isinstance(pos_meta.get("spine_wing"), dict):
                pos_meta["spine_wing"]["axis_x"] = \
                    pos_meta["spine_wing"].get("axis_x", 0) + dx
                pos_meta["spine_wing"]["axis_y"] = \
                    pos_meta["spine_wing"].get("axis_y", 0) + dy

    # W/H 必须在平移后的最终坐标上取。bugfix（CI 暴露的 v0.2.0 遗留）：
    # 原实现用平移前 xs_all 算 W，dx>0 时右移后内容溢出 viewBox
    # （无字体环境的解析式框宽窄 → min 左缘越界触发大 dx → 右缘超出）。
    # F3 返修补充：max 一并纳入边几何，弧/vg 鼓出不得越过右/下缘。
    xs_all = [pos[v] - widths[v] / 2 for v in nodes] + [pos[v] + widths[v] / 2 for v in nodes]
    ys_all = [y[v] - card_h / 2 for v in nodes] + [y[v] + card_h / 2 for v in nodes]
    exs1, eys1 = _edge_geom_bounds()
    W = int(math.ceil(max(xs_all + exs1))) + cfg.margin
    H = int(math.ceil(max(ys_all + eys1))) + cfg.margin
    W = ((W + 7) // 8) * 8
    H = ((H + 7) // 8) * 8

    # WS3 finalize：vg 路线在平移后的交付坐标上生成精确 SVG path（L+A 命令）
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
            # ref-scrubbed：用户锚定折点入交付（平移后坐标；渲染走折线）
            e["route"]["via"] = [[round(p[0] + dx, 1), round(p[1] + dy, 1)]
                                 for p in wp[1:-1]]

    if manual is not None:
        row_y_out = [yy + dy for yy in sorted({y[v] for v in nodes})]
        pitch_out = None
    elif engine == "ring-construct":
        # 环形排布无行结构语义：rowY 记实际 y 去重序，pitch 不适用
        row_y_out = [yy + dy for yy in sorted({y[v] for v in nodes})]
        pitch_out = None
    else:
        row_y_out = [dy + cfg.top + r * cfg.pitch for r in range(len(rows))]
        pitch_out = cfg.pitch
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
            # --from-layout 元数据（仅手动路径写入；auto 路径逐字节不变）
            **({} if from_meta is None else {"from_layout": from_meta}),
            "clearance": CLEARANCE,
            "router_cross_pairs": router_pairs,
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
    return v4
