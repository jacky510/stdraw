# -*- coding: utf-8 -*-
"""领结共点（双环共享单节点）对称排布（2026-11-06 jacky 美学 v3，ref-scrubbed）。

> jacky 亲手拉了 wage-price-spiral 手动布局：共享节点放图正中心、两环其余
> 节点放四对称位，全图上下左右轴对称——「拓扑该决定布局」。

触发判定（确定性规则写死；与 symlayout 的共**边**领结拓扑互斥）：
  - 枚举无向简单环（长度 ≥3，规范形去重；**不用声明 loops**——声明表混
    2 节点伪环、漏派生环），恰 **2** 个环、两环节点集恰共享 **1** 个节点、
    且两环并集 = 全部非孤立节点（存在悬挂节点时不触发，保守回退）。
  - 语料命中：{eroding-goals, shifting-the-burden, wage-price-spiral}
    （有向同构家族）。不误伤：08/10/17 虽也只有 2 个简单环但共享 2 节点
    （共边型，归 symlayout 口径的判据域之外、由既有模式处理）。

排布（place_bowtie_vertex，对拍 jacky 手拉样本的相对几何）：
  - 共享节点居画布中心（布局层轴 x=0,y=0，交付层统一平移居中）；
  - 两环各占一个半平面（第一环上 / 第二环下；环序按 kind R<B<其他 →
    canon 序确定性打破）；环上其余节点放同半平面的水平行上，左右镜像位
    （三角形 = ±D 等高，外边水平直线——同样本「顶边近水平」）；
  - 左右指派 = 从共享节点沿「有向边跟随」方向遍历环，后继放左、次后放右
    （样本实测：wages 左/cost 右、real_income 左/demand 右，两环同规则）；
  - 两环同 D、同 H → 全图严格上下镜像（样本竖直镜像轴 x≈293 的理想化，
    误差 0px ≤ 2px 验收门）。

布线（place_bowtie_vertex 构造式注入，不走候选池）：
  - 全直线（线型一致性硬规则：6 条边全 line，无直/弧/折混杂）；
  - 外边（环内不经过共享节点的边）= 水平直线；4 条辐条 = 直线；
  - 共享节点同一侧的两条辐条锚点在边中点两侧对称展开 ±SPREAD（同一节点
    多条出线不堆叠在同一点——2026-11-06 连接点口径硬规则 3）。

试验闸门：复用 layout_auto._constructed_gates（压线/净距/锚点平滑/卡距/
互环分离/交叉≤2），任一不过静默回退既有模式链（负例逐字节不变）。
"""
import math

from . import columnlayout
from .routing import border_point, seg_cross

SYM_GAP = 36              # 呼吸感目标净距（与 SYM_GAP/SIDE_GAP 同档）
MAX_BOWTIE_N = 12         # 触发上限：小图


class InfeasibleBowtieVertex(Exception):
    pass


def _adjacency(edges):
    adj = {v: set() for a, b in edges for v in (a, b)}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _canon(seq):
    best = None
    for s in (list(seq), list(seq)[::-1]):
        for i in range(len(s)):
            rot = s[i:] + s[:i]
            if best is None or rot < best:
                best = rot
    return tuple(best)


def detect_bowtie_vertex(graph):
    """领结共点判定。返回 plan dict 或 None。

    plan = {"shared": 共享节点, "loops": [(kind, [c1..ck]), ...]（上环在前）,
            "deg0": [孤立节点]}
    """
    nodes = list(graph.node_ids())
    edges = [(e.a, e.b) for e in graph.edges]
    adj = _adjacency(edges)
    core = [v for v in nodes if adj[v]]
    deg0 = [v for v in nodes if not adj[v]]
    if len(core) < 5 or len(core) > MAX_BOWTIE_N:
        return None
    cycles = columnlayout._enumerate_cycles(core, adj)
    if len(cycles) != 2:
        return None
    s0, s1 = set(cycles[0]), set(cycles[1])
    shared_set = s0 & s1
    if len(shared_set) != 1:
        return None
    if s0 | s1 != set(core):
        return None            # 存在环外悬挂节点 → 保守不触发
    shared = sorted(shared_set)[0]
    eset = set(edges)

    def _oriented(seq):
        """环序 → 从 shared 起、有向边跟随数多的环向；平局取 canon 小者。"""
        n = len(seq)
        i = seq.index(shared)

        def follows(o):
            return sum(1 for k in range(n)
                       if (o[k], o[(k + 1) % n]) in eset)
        o1 = [seq[(i + k) % n] for k in range(n)]
        o2 = [seq[(i - k) % n] for k in range(n)]
        c1, c2 = follows(o1), follows(o2)
        if c1 != c2:
            return o1 if c1 > c2 else o2
        return o1 if _canon(o1) <= _canon(o2) else o2

    kind_rank = {"R": 0, "B": 1}
    entries = []
    for seq in cycles:
        kind = None
        for lp in graph.loops:
            if set(lp.nodes) == set(seq):
                kind = getattr(lp, "kind", None)
                break
        entries.append((kind_rank.get(kind, 2), _canon(seq), kind,
                        _oriented(seq)[1:]))
    entries.sort(key=lambda t: (t[0], t[1]))
    loops = [(kind, rest) for _r, _c, kind, rest in entries]
    return {"shared": shared, "loops": loops, "deg0": deg0}


def place_bowtie_vertex(plan, widths, card_h, cfg, edges):
    """领结共点对称排布 → ({v: x}, {v: y}, meta, constructed_routes)。

    constructed_routes: {(a,b): route dict}——全直线构造（外边水平 +
    辐条直连，共享侧锚点 ±SPREAD 对称展开），构造式注入。
    """
    shared = plan["shared"]
    loops = plan["loops"]
    ws = widths[shared]
    # D：左右顶点距轴——左右两卡半宽和 + 净距（各环取大）
    D = max((widths[seq[0]] + widths[seq[-1]]) / 2 + SYM_GAP
            for _k, seq in loops)
    D = int(round(D / 2) * 2)
    # H：环行与共享行的半距——上下行呼吸净距 ≥ SYM_GAP 且 ≥ D（近方形，
    # 对拍样本半径 ~196 / x 偏 ~135-150 / y 偏 ~123-145 的近对称几何）
    H = max(2 * card_h + SYM_GAP, D)
    H = int(round(H / 2) * 2)

    pos = {shared: 0}
    y = {shared: 0}
    for idx, (_kind, seq) in enumerate(loops):
        s = -1 if idx == 0 else 1          # 第一环上半平面，第二环下半
        k = len(seq)
        for j, v in enumerate(seq):
            if k > 1:
                x = -D + (2.0 * D) * j / (k - 1)
            else:
                x = 0.0
            pos[v] = int(round(x / 2) * 2)
            y[v] = s * H

    if plan["deg0"]:
        total = sum(widths[v] for v in plan["deg0"]) + 18 * (len(plan["deg0"]) + 1)
        cur = -total / 2
        for v in plan["deg0"]:
            pos[v] = int(round((cur + widths[v] / 2) / 2) * 2)
            y[v] = cfg.park_y
            cur += widths[v] + 18

    def _np(v):
        return (pos[v], y[v], widths[v], card_h)

    constructed = {}
    eset = set(edges)
    # 共享节点辐条：锚点 = 共享卡对应侧边中点 ±SPREAD（上下环对称展开，
    # 同一节点多条出线不堆叠——2026-11-06 连接点口径硬规则 3）。
    # 领结家族实测：4 条辐条均为互环对（双向边）——单线构造两方向逐点重合，
    # 互环分离门必 FAIL。互环走廊：每方向一条平行线，锚点沿框边切向
    # ±PAIR_T 偏移（U 线=向左行进方向，L 线=反向；两环同规则 → 镜像一致），
    # 侧边总展开 ≤ hh−3（钳制在框边内）。同侧存在互环走廊时 SPREAD 收窄。
    PAIR_T = 12
    spoke_dirs = {}      # endv -> [(a,b), ...] 该辐条上的有向边
    for _kind, seq in loops:
        for endv in (seq[0], seq[-1]):
            spoke_dirs[endv] = [e for e in ((shared, endv), (endv, shared))
                                if e in eset]
    side_mutual = {side: any(len(spoke_dirs.get(v, [])) == 2
                             for _k, seq in loops for v in (seq[0], seq[-1])
                             if (1 if pos[v] > 0 else -1) == side)
                   for side in (-1, 1)}
    spoke_anchor = {}
    for endv, dirs in spoke_dirs.items():
        side = -1 if pos[endv] < 0 else 1
        s = -1 if any(endv in seq for _k, seq in loops[:1]) else 1
        spread = 7 if side_mutual[side] else 14
        spoke_anchor[endv] = [side * ws / 2, s * spread]
    hh3 = card_h / 2 - 3
    for endv, dirs in spoke_dirs.items():
        if not dirs:
            continue
        nb = _np(endv)
        base_sa = spoke_anchor[endv]
        base_cb = border_point(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                               base_sa[0] - nb[0], base_sa[1] - nb[1])
        on_x = abs(abs(base_cb[0] - nb[0]) - nb[2] / 2) <= \
            abs(abs(base_cb[1] - nb[1]) - nb[3] / 2)
        if len(dirs) == 2:
            # 互环走廊：U 线（−t）= 向左行进方向；L 线（+t）= 反向。
            # 卡端锚 = 走廊中心锚沿所属框边切向真实展开 ±PAIR_T（两线平行
            # 级分离 ≥4px 门）；卡端在横边时按「上→近 / 下→远」配对——
            # 下线起点更低，若再更陡会翻到上线上方（实测交叉），远端配对
            # 使间隙单调不缩；两环同规则 → 上下/左右镜像一致。
            leftward = dirs[0] if pos[dirs[0][0]] > pos[dirs[0][1]] else dirs[1]
            backward = dirs[1] if leftward == dirs[0] else dirs[0]
            sa_u = [base_sa[0], max(-hh3, min(hh3, base_sa[1] - PAIR_T))]
            sa_l = [base_sa[0], max(-hh3, min(hh3, base_sa[1] + PAIR_T))]
            on_x = abs(abs(base_cb[0] - nb[0]) - nb[2] / 2) <= \
                abs(abs(base_cb[1] - nb[1]) - nb[3] / 2)
            if on_x:
                half = nb[3] / 2 - 3
                y_l = max(nb[1] - half, min(nb[1] + half, base_cb[1] - PAIR_T))
                y_h = max(nb[1] - half, min(nb[1] + half, base_cb[1] + PAIR_T))
                cb_u = [base_cb[0], y_l]      # 平移 ±t：恒平行，不交叉
                cb_l = [base_cb[0], y_h]
            else:
                half = nb[2] / 2 - 3
                x_a = max(nb[0] - half, min(nb[0] + half,
                                            base_cb[0] - PAIR_T))
                x_b = max(nb[0] - half, min(nb[0] + half,
                                            base_cb[0] + PAIR_T))
                # 配对防交叉：上/下线的竖直序须全程保持——目标卡在上半平面
                # 时上→近、下半平面时上→远（统一用「相交则换位」确定性判定）
                cb_a, cb_b = [x_a, base_cb[1]], [x_b, base_cb[1]]
                if seg_cross(sa_u, cb_a, sa_l, cb_b):
                    cb_a, cb_b = cb_b, cb_a
                cb_u, cb_l = cb_a, cb_b
            constructed[leftward] = {
                "kind": "line",
                "points": ([sa_u, cb_u] if leftward[0] == shared
                           else [cb_u, sa_u])}
            constructed[backward] = {
                "kind": "line",
                "points": ([sa_l, cb_l] if backward[0] == shared
                           else [cb_l, sa_l])}
        else:
            e = dirs[0]
            a, b = e
            pa = base_sa if a == shared else base_cb
            pb = base_cb if a == shared else base_sa
            constructed[e] = {"kind": "line", "points": [pa, pb]}
    # 外边（环内不经过共享节点的边）：水平直线（k=2）或同弦直线（k>2）
    for _kind, seq in loops:
        for j in range(len(seq) - 1):
            a, b = seq[j], seq[j + 1]
            for e in ((a, b), (b, a)):
                if e not in eset:
                    continue
                na, nb = _np(a), _np(b)
                pa = border_point(na[0], na[1], na[2] / 2, na[3] / 2,
                                  nb[0] - na[0], nb[1] - na[1])
                pb = border_point(nb[0], nb[1], nb[2] / 2, nb[3] / 2,
                                  na[0] - nb[0], na[1] - nb[1])
                constructed[e] = {"kind": "line", "points": [pa, pb]}
                break
    mirror_pairs = []
    if len(loops) == 2 and len(loops[0][1]) == len(loops[1][1]):
        mirror_pairs = [[loops[0][1][j], loops[1][1][j]]
                        for j in range(len(loops[0][1]))]
    meta = {
        "placement": "bowtie-vertex",
        "symmetry": {
            "axis": "vertical",
            "axis_x": 0,
            "axis_y": 0,
            "shared_node": shared,
            "loops": [[shared] + list(seq) for _k, seq in loops],
            "mirror_pairs": mirror_pairs,
            "gap": SYM_GAP,
            "line_style_rule": "all-straight (horizontal outer edges + spokes)",
        },
    }
    return pos, y, meta, constructed
