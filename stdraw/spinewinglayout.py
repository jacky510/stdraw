# -*- coding: utf-8 -*-
"""纵柱+中线翼位（spine-wing）排布（2026-11-06 jacky 拍板 B-限定版，ref-scrubbed）。

> jacky 亲手拉了 classic-cld-growth-and-burden 手动布局：中央纵柱
> adopters(顶)/rate(底) 严格垂直压画布中心线；左翼 word/potential 与右簇
> crowding 压同一水平中线（y 完全相等）；右上 quickfix / 右下 sideeffect
> 近镜像（x 差 6px）；fundamental 右下内侧与 rate 同行。「拓扑该决定布局」
> 的第二种形态——中枢对纵柱 + 翼位水平带 + 翼外镜像簇。

触发判定（确定性拓扑度量，写进 docs/layout-modes.md 优先级链；本模块是正本）：
  - **主链（spine）**：枚举有向边，取「端点公共邻居数」最大者为中枢对
    （平局：声明环共现数多者 → 规范形 (u,v) 小者）。经典 CLD 的
    「rate→adopters」型扩散中枢对天然胜出（classic-cld 实测公共邻居 3，
    其余语料最高 2）。
  - **翼位（wings）**：中枢对的公共邻居——它们与中枢对各构成一条
    3-环（左翼 word∈R1 / potential∈B1，右翼 crowding∈B2），压中线水平带。
  - **触发条件（全部满足才触发）**：
    ① 3 ≤ |wings| ≤ 4（中线翼位带需 ≥3 位才成「带」，>4 中枢对过载）；
    ② 1 ≤ |rest| ≤ 6 ∧ rest 的全部邻接 ⊆ spine∪wings∪rest（次级簇只挂
       翼位/中枢——双轴对称可构性；limits-to-growth 同构 spine 但 rest=0，
       属纯增长核，不触发）；
    ③ 主链长度占比 = |spine| / n ≤ 0.5（中枢是紧凑节点对；长链形态归
       column-chain 口径）；
    ④ rest 可配对：按「限制邻域键（对 wings∪spine 的邻接集）→ 规范形」
       排序后两两配对、落单 ≤1（镜像可构性——quickfix/sideeffect 成对、
       fundamental 落单内侧）。
  - 语料命中（19 张全量 sweep 实测）：仅 classic-cld-growth-and-burden。
    纯环族（arms-race 等 maxCN≤1）、共点领结三张（maxCN=1）、共边领结
    两张（maxCN=2）、纵列族（maxCN≤2）全部不命中——见卡片证据清单。

排布（place_spine_wing，构造约束——对拍样本相对几何，非全局目标函数项）：
  - 纵柱：中枢对沿布局轴 x=0 严格垂直，边 head（adopters）在上
    y=−Hs、tail（rate）在下 y=+Hs，Hs = 2·(card_h+GAP)（=160 @card_h 44，
    与样本纵柱半距 160 一致）；
  - 中线翼位：全部翼位 y=0 压中线。rest 簇锚翼（对 rest 邻接最多者，
    样本=crowding）放右侧最近位；其余翼按（回路 kind R<B<其他 → 规范形）
    排序放左侧、由内到外（样本：word 内 / potential 外）；
  - rest 镜像对：配对首者放上翼位 y=−(card_h+GAP)、次者放下翼位
    y=+(card_h+GAP)（=±80，与样本 ±82 的理想化），同列 x=锚翼右侧
    整距堆叠；落单者放右下内侧 y=+2·(card_h+GAP)（=+160，与 rate 同行，
    样本 fundamental y=532 vs rate 534 同一行带）；
  - 全部坐标取偶（2px 网格）；交付层统一平移居中由 layout_auto 负责。

布线（构造约束注入，不走候选池）：
  - 纵柱边（tail→head）构造为竖直直线（顶卡底边中点 → 底卡顶边中点）；
  - 其余边走同一 Router 候选池（直线/弧线一等），对称带内线型由
    Router 层级代价（vg+120/poly+40）压向直线——对拍样本全直线；
  - 互环对（crowding↔quickfix、crowding↔fundamental）由 Router 互环
    走廊机制分离（≥4px 门）。

试验闸门：复用 layout_auto._constructed_gates（压线/净距/锚点平滑/卡距/
互环分离/交叉≤2），任一不过静默回退既有模式链（负例逐字节不变）。
"""
import math

from . import columnlayout
from .routing import border_point

SYM_GAP = 36              # 呼吸感目标净距（与 bowtie/symmetric 同档）
MAX_SPINE_WING_N = 12     # 触发上限：小图
MIN_WINGS, MAX_WINGS = 3, 4
MAX_REST = 6


class InfeasibleSpineWing(Exception):
    pass


def _adjacency(edges):
    adj = {v: set() for a, b in edges for v in (a, b)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _canon(seq):
    return columnlayout._canon(seq)


def detect_spine_wing(graph):
    """纵柱+翼位判定。返回 plan dict 或 None。

    plan = {"spine_tail", "spine_head", "wings": {"left": [...], "anchor": w},
            "rest_pairs": [[up, down], ...], "rest_single": [v] or [],
            "deg0": [孤立节点]}
    """
    nodes = list(graph.node_ids())
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if len(core) < 6 or len(core) > MAX_SPINE_WING_N:
        return None

    # 主链候选：端点公共邻居数最大的有向边（确定性平局链）
    loop_sets = []
    for lp in graph.loops:
        loop_sets.append((getattr(lp, "kind", None), set(lp.nodes)))
    best = None
    for e in sorted(set(edges)):
        u, v = e
        cn = adj[u] & adj[v]
        if not (MIN_WINGS <= len(cn) <= MAX_WINGS):
            continue
        co_loops = sum(1 for _k, s in loop_sets if {u, v} <= s)
        key = (-len(cn), -co_loops, _canon((u, v)))
        if best is None or key < best[0]:
            best = (key, u, v, cn)
    if best is None:
        return None
    _key, u, v, wings_set = best
    wings = sorted(wings_set)
    rest = sorted(set(core) - {u, v} - wings_set)
    # ① 翼位带 + ② 次级簇（rest 空的纯增长核不触发——limits-to-growth）
    if not (1 <= len(rest) <= MAX_REST):
        return None
    # ③ 主链长度占比：中枢对节点数 / 核心节点数 ≤ 0.5——紧凑中枢对
    #    （长链形态归 column-chain 口径；2 节点中枢对全语料实测 0.22-0.33）
    if len({u, v}) / max(1, len(core)) > 0.5:
        return None
    # ②' 双轴可构性：rest 只挂 spine∪wings∪rest（无外挂）
    allowed = {u, v} | wings_set | set(rest)
    if not all(adj[r] <= allowed for r in rest):
        return None
    # ④ rest 镜像可构性：优先配「共享声明环」的 rest 对（样本 quickfix/
    #    sideeffect 同属 R2 成镜像对、fundamental 只与锚翼共环 → 落单内侧），
    #    其余按「限制邻域键（对 wings∪spine 的邻接集）→ 规范形」配对，
    #    落单 ≤1（镜像可构性）。
    def _restrict_key(r):
        return (tuple(sorted(adj[r] & (wings_set | {u, v}))),
                _canon((r,)))
    shared_loop = {}
    for i, r1 in enumerate(rest):
        for r2 in rest[i + 1:]:
            sl = [set(lp.nodes) for lp in graph.loops
                  if r1 in set(lp.nodes) and r2 in set(lp.nodes)]
            if sl:
                shared_loop[(r1, r2)] = tuple(sorted(
                    s for s in sl for x in (r1, r2) if x in s))
    pairs, used = [], set()
    for (r1, r2) in sorted(shared_loop,
                           key=lambda p: (_canon(p),)):
        if r1 in used or r2 in used:
            continue
        pairs.append((r1, r2))
        used |= {r1, r2}
    rest_left = sorted((r for r in rest if r not in used),
                       key=_restrict_key)
    for i in range(0, len(rest_left) - 1, 2):
        pairs.append((rest_left[i], rest_left[i + 1]))
        used |= {rest_left[i], rest_left[i + 1]}
    single = sorted((r for r in rest if r not in used), key=_restrict_key)
    if len(pairs) > 3 or len(single) > 1:
        return None

    # 翼位指派：rest 簇锚翼（对 rest 邻接最多者；平局取 canon 小）→ 右侧
    def _canon1(w):
        return _canon((w,))
    anchor = sorted(wings, key=lambda w: (-len(adj[w] & set(rest)),
                                          _canon1(w)))[0]
    left_wings = [w for w in wings if w != anchor]

    def _wing_kind(w):
        kind_rank = {"R": 0, "B": 1}
        k = 2
        for lp in graph.loops:
            s = set(lp.nodes)
            if w in s and {u, v} <= s:
                kind = getattr(lp, "kind", None)
                if kind is not None:
                    k = kind_rank.get(kind, 2)
                break
        return k
    left_wings.sort(key=lambda w: (_wing_kind(w), _canon1(w)))
    # 配对首者上翼、次者下翼；落单者下内侧（样本 fundamental）
    rest_pairs = [[p[0], p[1]] for p in pairs]
    return {"spine_tail": u, "spine_head": v,
            "wings_left": left_wings, "wing_anchor": anchor,
            "rest_pairs": rest_pairs, "rest_single": single,
            "deg0": deg0}


def place_spine_wing(plan, widths, card_h, cfg, edges):
    """纵柱+翼位构造排布 → ({v: x}, {v: y}, meta, constructed_routes)。

    构造约束（对拍 jacky 手拉样本 classic-cld 的相对几何，见模块 docstring）。
    """
    u, v = plan["spine_tail"], plan["spine_head"]
    GAP = SYM_GAP
    row = card_h + GAP                        # 翼位行距（=80 @card_h 44）
    Hs = 2 * row                              # 纵柱半距（=160，样本 160）

    def _r2(x):
        return int(round(x / 2) * 2)

    pos, y = {}, {}
    pos[v], y[v] = 0, -Hs                     # head 顶（样本 adopters）
    pos[u], y[u] = 0, Hs                      # tail 底（样本 rate）

    # 右侧锚翼（样本 crowding x=+134≈半柱宽+半翼宽+36）
    anchor = plan["wing_anchor"]
    x_anchor = (widths[u] + widths[anchor]) / 2 + GAP
    pos[anchor], y[anchor] = _r2(x_anchor), 0

    # 左翼：由内到外（样本 word 内 / potential 外）
    prev_half = widths[u] / 2
    cur = -(prev_half + GAP)
    for w in plan["wings_left"]:
        xw = cur - widths[w] / 2
        pos[w], y[w] = _r2(xw), 0
        cur = xw - widths[w] / 2 - GAP

    # rest 镜像对：锚翼右侧整距堆列，上/下翼位 ±row（样本 quickfix/sideeffect
    # y=±82≈±row；x 同列近镜像——引擎理想化取严格同列，误差 0px）
    pair_col_x = x_anchor + widths[anchor] / 2 + GAP
    mirror_pairs = []
    for up, down in plan["rest_pairs"]:
        pair_x = pair_col_x + widths[up] / 2      # 以首者宽定列
        pos[up], y[up] = _r2(pair_x), -row
        pos[down], y[down] = _r2(pair_x), row
        mirror_pairs.append([up, down])
    # 落单者：右下内侧（样本 fundamental 与 rate 同行 y=+2row；x 至少与
    # 纵柱底卡保持 GAP 净距——样本 x=594 vs rate 右缘 460 的同带错位）
    if plan["rest_single"]:
        s = plan["rest_single"][0]
        xs = widths[u] / 2 + GAP + widths[s] / 2
        pos[s], y[s] = _r2(xs), 2 * row

    if plan["deg0"]:
        total = sum(widths[w] for w in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur0 = -total / 2
        for w in plan["deg0"]:
            pos[w] = int(round((cur0 + widths[w] / 2) / 2) * 2)
            y[w] = cfg.park_y
            cur0 += widths[w] + 18

    # 构造路线：纵柱边竖直直线（不走候选池）；其余边走 Router
    constructed = {}
    eset = set(edges)
    for e in ((u, v), (v, u)):
        if e in eset:
            a, b = e
            na = (pos[a], y[a], widths[a], card_h)
            nb = (pos[b], y[b], widths[b], card_h)
            pa = border_point(na[0], na[1], na[2] / 2, na[3] / 2,
                              nb[0] - na[0], nb[1] - na[1])
            pb = border_point(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                              na[0] - nb[0], na[1] - nb[1])
            constructed[e] = {"kind": "line", "points": [pa, pb]}
            break

    meta = {
        "placement": "spine-wing",
        "spine_wing": {
            "axis_x": 0,
            "axis_y": 0,
            "spine": [v, u],
            "wings_left": list(plan["wings_left"]),
            "wing_anchor": anchor,
            "wings": [w for w in plan["wings_left"]] + [anchor],
            "mirror_pairs": mirror_pairs,
            "rest_single": list(plan["rest_single"]),
            "row_pitch": row,
            "spine_half": Hs,
            "gap": GAP,
            "line_style_rule": "spine vertical straight + router lines/arcs",
        },
    }
    return pos, y, meta, constructed
