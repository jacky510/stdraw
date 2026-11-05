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
from .routing import Router, CLEARANCE, SIDE_MARGIN


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

    返回 {v: x_px}（框心）。y 由 rows 决定。
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

    if _has_solver():
        snap = cfg.snap_regular if len(nodes) <= 10 else cfg.grid
        res = _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, snap)
        if res is None and snap != cfg.grid:      # 24px 吸附不可行 → 退 8px 网格
            res = _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, cfg.grid)
        if res is not None:
            return res, "cp-sat"
    return _construct_positions(nodes, rows, widths, cfg), "construct"


EDGES_REF = [()]   # 模块级引用坑位——由 layout() 注入，避免长参表


def _cpsat_positions(nodes, rows, widths, cfg, einfo, max_x, grid):
    """CP-SAT：决策变量 = 框心 x；目标 = 交叉数 + Σ|Δx|；约束 = 净距/网格/边界。"""
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return None
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
    # 不设墙钟时限：时限截断会随机器负载漂移（破坏确定性）；小模型求到最优本来就快
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {v: int(solver.Value(xs[v])) for v in nodes}


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


def _route_total(nodes_px, edges, cfg):
    """路由真值总成本：压线/净距/交叉/边长的加权和（布局层真目标函数）。"""
    router = Router(nodes_px, edges, cfg.clearance, cfg.pitch)
    routes = router.route_all()
    total = 0.0
    for info in routes.values():
        clr = info.get("min_clear")
        clr_pen = (30 * max(0.0, cfg.clearance - clr)) if clr is not None else 30 * cfg.clearance
        total += (4000 * info.get("press", 0) + 40 * info.get("cross", 0) +
                  clr_pen +
                  0.01 * sum(math.dist(info["points"][k], info["points"][k + 1])
                             for k in range(len(info["points"]) - 1)))
    return total, routes, router


def _polish(nodes, edges, rows, pos, y, widths, card_h, cfg, rounds=2):
    """局部搜索：逐节点 ±24/±48 横移（保同行净距），以路由真值总成本择优。

    CP-SAT 全局定位的补充精化——把「布线可行性」显式喂回定位层。
    确定性：固定遍历序 + 固定扰动集。
    """
    def nodes_px(p):
        return {v: (p[v], y[v], widths[v], card_h) for v in nodes}

    best_pos = dict(pos)
    best_score, best_routes, _ = _route_total(nodes_px(best_pos), edges, cfg)
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
                sc, routes, _ = _route_total(nodes_px(cand), edges, cfg)
                if sc < best_score - 1e-6:
                    best_pos, best_score, best_routes = cand, sc, routes
                    improved = True
        # 行内相邻交换（「人工可见更优解」类搬移的机械化）
        for vs in rows:
            for i in range(len(vs) - 1):
                u, w = vs[i], vs[i + 1]
                cand = dict(best_pos)
                cand[u], cand[w] = best_pos[w], best_pos[u]
                sc, routes, _ = _route_total(nodes_px(cand), edges, cfg)
                if sc < best_score - 1e-6:
                    best_pos, best_score, best_routes = cand, sc, routes
                    improved = True
        if not improved:
            break
    return best_pos, best_score, best_routes


def layout(graph, config: AutoConfig = None, linestyle: str = "straight"):
    """auto 配方入口：图 → v4 兼容布局 dict（含折线/弧线路由 + 元数据）。"""
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

    # ② 分层（破环 + 最长路 + 空层压缩）
    _, dag = _cycle_break(core, EDGES_REF[0])
    layer = _layers(core, dag)
    nrow = max(layer.values()) + 1 if core else 1
    rows = [[v for v in core if layer[v] == r] for r in range(nrow)]
    rows = [r for r in rows if r]

    # ③ 定位
    pos, engine = _solve_positions(core, rows, widths, cfg, linestyle)

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

    # ④ 布线（直线/弧线一等，框不压线）+ WS3 理论口径（最终路线交叉对数）
    nodes_px = {v: (pos[v], y[v], widths[v], card_h) for v in nodes}
    router = Router(nodes_px, EDGES_REF[0], cfg.clearance, cfg.pitch)
    routes = router.route_all()
    router_pairs = router.final_crossing_pairs(routes)

    edges_out = []
    for i, (a, b) in enumerate(EDGES_REF[0]):
        info = routes[i]
        e = {"a": a, "b": b, "polarity": getattr(graph.edges[i], "polarity", "+"),
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
        edges_out.append(e)

    xs_all = [pos[v] - widths[v] / 2 for v in nodes] + [pos[v] + widths[v] / 2 for v in nodes]
    ys_all = [y[v] - card_h / 2 for v in nodes] + [y[v] + card_h / 2 for v in nodes]
    W = int(math.ceil(max(xs_all))) + cfg.margin
    H = int(math.ceil(max(ys_all))) + cfg.margin
    W = ((W + 7) // 8) * 8
    H = ((H + 7) // 8) * 8
    min_x = min(xs_all) - cfg.margin / 2
    dx = max(0, int(math.ceil(cfg.margin / 2 - min_x)))
    dx = ((dx + 23) // 24) * 24          # 平移量对齐 24px，保持列吸附/网格不变
    if dx:
        for e in edges_out:
            e["route"]["points"] = [[px + dx, py] for px, py in e["route"]["points"]]
            e["anchors"] = {"a": [e["anchors"]["a"][0] + dx, e["anchors"]["a"][1]],
                            "b": [e["anchors"]["b"][0] + dx, e["anchors"]["b"][1]]}
            e["arrow"][0] += dx
            if "ctrl" in e["route"]:      # bugfix：弧线控制点必须随 dx 平移
                e["route"]["ctrl"][0] += dx
        for v in nodes:
            pos[v] += dx

    # WS3 finalize：vg 路线在平移后的交付坐标上生成精确 SVG path（L+A 命令）
    from .visibility import route_svg_d as _route_svg_d
    for e in edges_out:
        vg = e.pop("_vg", None)
        if vg:
            corners, fillets = vg
            corners = [[p[0] + dx, p[1]] for p in corners]
            fillets = [dict(f, ta=[f["ta"][0] + dx, f["ta"][1]],
                            tb=[f["tb"][0] + dx, f["tb"][1]],
                            center=[f["center"][0] + dx, f["center"][1]])
                       for f in fillets]
            e["route"]["path_d"] = _route_svg_d(corners, fillets)
            e["route"]["via"] = [[round(px, 1), round(py, 1)] for px, py in corners]

    v4 = {
        "viewBox": [0, 0, W, H],
        "nodes": {v: {"x": pos[v], "y": y[v], "w": widths[v]} for v in nodes},
        "edges": edges_out,
        "bars": {},
        "meta": {
            "rows": len(rows),
            "rowY": [cfg.top + r * cfg.pitch for r in range(len(rows))],
            "pitch": cfg.pitch,
            "deg0": deg0,
            "cardH": card_h,
            "fs": [cfg.fs_title, cfg.fs_value],
            "recipe": "auto-v2",
            "line_style": linestyle,
            "position_engine": engine,
            "clearance": CLEARANCE,
            "router_cross_pairs": router_pairs,
            "solver_available": _has_solver(),
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
