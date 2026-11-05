# 统一评测器：任何工具的布局（节点框 + 边折线）→ 六指标（native 坐标口径）。
#
# 口径（REPORT.md §2 详述）：
#   所有工具吃同一输入（同标签、同框尺寸 w×h px，框宽由 stdraw textmetrics 统一给出，
#   Graphviz 以 inch=px/72、ELK/stdraw 直接 px 传入——各工具 native 坐标同为「物理 px」，
#   同一框在哪个工具里都是同一 px 尺寸）。
#   阈值型指标（净距违规 16px / 框压线 1px）在 native 坐标按绝对 px 判定，跨工具可比；
#   尺度不变指标（交叉/CV/行对齐）不受坐标尺度影响；另报 bbox 占用作画布效率参考。
#   不做强制缩放归一化——缩放会改变阈值的物理语义，谁被缩谁吃亏不是质量差异。
#
# 指标口径与 stdraw/metrics.py、stdraw/routing.py 同源（直接复用其函数）：
#   crossings        相邻边除外，折线严格求交（seg_cross）
#   box_press        边折线进入非端点框（含 1px 余量，dist_point_rect）
#   clear_violations 边-非端点框最小距离 < 16px 的 (边,框) 对数
#   spacing_cv       最近邻中心距 std/mean
#   row_align_rate   y 差 ≤4px 视觉同行占比
#   runtime_s        runner 计时传入
import math
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)

from stdraw.metrics import seg_cross                       # noqa: E402
from stdraw.routing import sample_polyline, dist_point_rect  # noqa: E402
from stdraw import textmetrics                             # noqa: E402

CLEARANCE = 16.0        # 净距阈值 px（与 stdraw 硬门同值）
PRESS_MARGIN = 1        # 框压线余量 px
ROW_EPS = 4.0           # 视觉同行判定 px
FS_TITLE = 15.0         # 与 stdraw auto 配方一致的字号


def box_size(label: str):
    """统一样式框宽（布局引擎无关）：stdraw textmetrics 解析宽度 + 保守 padding。"""
    w, h = textmetrics.card_size(label, "", FS_TITLE, FS_TITLE)
    return int(w), int(h)


def evaluate(nodes, routes, edges, runtime_s, tool, graph, extra=None):
    """nodes {id:(x,y,w,h)}, routes {edge_idx:[pts]}, edges [{a,b}]（与 routes 同序）。
    全部在 native 坐标上判定（见文件头口径说明）。"""
    ids = list(nodes)

    # 1. 交叉（相邻边共享端点不计）
    crossings = 0
    n_e = len(edges)
    for i in range(n_e):
        for j in range(i + 1, n_e):
            ei, ej = edges[i], edges[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            pi, pj = routes.get(i), routes.get(j)
            if not pi or not pj:
                continue
            for s1 in zip(pi[:-1], pi[1:]):
                hit = False
                for s2 in zip(pj[:-1], pj[1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    crossings += 1
                    break

    # 2. 框压线 / 净距违规（采样折线 vs 非端点框）
    press = 0
    clear_violations = 0
    min_clear = None
    for i, e in enumerate(edges):
        pts = sample_polyline(routes.get(i) or [])
        for v in ids:
            if v in (e["a"], e["b"]):
                continue
            p = nodes[v]
            d = min(dist_point_rect(px, py, p[0], p[1], p[2] / 2 + PRESS_MARGIN,
                                    p[3] / 2 + PRESS_MARGIN) for (px, py) in pts)
            if d <= 0:
                press += 1
            dmin = min(dist_point_rect(px, py, p[0], p[1], p[2] / 2, p[3] / 2)
                       for (px, py) in pts)
            if dmin < CLEARANCE:
                clear_violations += 1
            min_clear = dmin if min_clear is None else min(min_clear, dmin)

    # 3. CV（最近邻中心距 std/mean）
    nn = []
    for a in ids:
        (ax, ay, _, _) = nodes[a]
        ds = [math.dist((ax, ay), (nodes[b][0], nodes[b][1])) for b in ids if b != a]
        if ds:
            nn.append(min(ds))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn) \
        if nn and mean_nn else 0.0

    # 4. 行对齐率（y 差 ≤4px 成组）
    ys = sorted(p[1] for p in nodes.values())
    aligned, i = 0, 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] - ys[j] <= ROW_EPS:
            j += 1
        if j > i:
            aligned += j - i + 1
        i = j + 1
    row_rate = aligned / len(ids) if ids else 0.0

    W = (max(p[0] + p[2] / 2 for p in nodes.values()) -
         min(p[0] - p[2] / 2 for p in nodes.values()))
    H = (max(p[1] + p[3] / 2 for p in nodes.values()) -
         min(p[1] - p[3] / 2 for p in nodes.values()))

    return {
        "tool": tool, "graph": graph,
        "crossings": crossings,
        "box_press": press,
        "clear_violations": clear_violations,
        "min_edge_box_clear_px": round(min_clear, 1) if min_clear is not None else None,
        "spacing_cv": round(cv, 3),
        "row_align_rate": round(row_rate, 3),
        "runtime_s": round(runtime_s, 3),
        "bbox": [round(W), round(H)],
        "bbox_area": round(W * H),
        "status": "ok",
        **(extra or {}),
    }
