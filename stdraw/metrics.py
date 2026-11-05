# -*- coding: utf-8 -*-
"""质量证书（本项目的护城河）—— 五指标 + 排布指标 + 诚实分级。

一切验证跑在**交付坐标**上（取整/导出后的那份），这是纪律不是优化项。
指标实现：seg_cross / Liang-Barsky seg_hits_rect / rect_gap / 行对齐率。
另加排布第一优先指标：间距变异系数 CV。

诚实分级（绝不冒充成品）：
  最优 = 排布要求满足 + 线 0 交叉
  其次 = 排布要求满足 + 1~2 处交叉（证书标注交叉坐标供人复核）
  未获证书 = 其余情况（如实写明，不降格冒充）
3D 层不在本模块范围（3D 指标属 M2，M0 的 3D demo 只报告排布与边长）。
"""
import math
from typing import Dict, List, Optional

EPS = 1e-9
ROW_EPS = 4          # 视觉同行判定：y 差 ≤ 4px 算同排
INFLATE = 4          # 穿卡口径：卡尺寸外扩 px（16px 膨胀口径的软化替代）


def seg_cross(p1, p2, p3, p4):
    """严格相交判定（含共线重叠；端点相触不算）。"""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < EPS else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    if d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0:
        return True
    if d1 == 0 and d2 == 0 and d3 == 0 and d4 == 0:
        def on(a, b, c):
            return (min(a[0], b[0]) - EPS <= c[0] <= max(a[0], b[0]) + EPS and
                    min(a[1], b[1]) - EPS <= c[1] <= max(a[1], b[1]) + EPS)
        if on(p3, p4, p1) or on(p3, p4, p2) or on(p1, p2, p3) or on(p1, p2, p4):
            near = [q for q in (p3, p4) for p in (p1, p2)
                    if abs(q[0] - p[0]) < EPS and abs(q[1] - p[1]) < EPS]
            if len(near) >= 1:
                return False
            return True
    return False


def seg_hits_rect(x1, y1, x2, y2, cx, cy, hw, hh):
    """Liang-Barsky：线段是否穿过矩形（含正长度进入才算，贴边不算）。"""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - (cx - hw)), (dx, (cx + hw) - x1),
                 (-dy, y1 - (cy - hh)), (dy, (cy + hh) - y1)):
        if abs(p) < EPS:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return t1 - t0 > EPS


def rect_gap(x1, y1, w1, h1, x2, y2, w2, h2):
    """两卡片的矩形净距（hypot 分量，重叠为 0）。"""
    dx = abs(x1 - x2) - (w1 + w2) / 2
    dy = abs(y1 - y2) - (h1 + h2) / 2
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def scene_from_planar(v4: dict, card_h: int = None) -> dict:
    """planar 布局 JSON → 通用 scene（segments=竖线，y 为行中心）。"""
    nodes = {}
    ch = card_h or v4["meta"].get("cardH", 42)
    for v, p in v4["nodes"].items():
        nodes[v] = {"x": p["x"], "y": p["y"], "w": p.get("w", 140), "h": ch}
    edges = [{"a": e["a"], "b": e["b"]} for e in v4["edges"]]
    segs = {}
    for i, e in enumerate(v4["edges"]):
        segs[i] = ((e["x"], e["y1"]), (e["x"], e["y2"]))
    return {"nodes": nodes, "edges": edges, "segments": segs}


def scene_from_grid(nodes: dict, edges: list, card_h: int) -> dict:
    """中心坐标图（viewer 网格/环形形态）→ 通用 scene（segments=心连线）。"""
    segs = {}
    for i, e in enumerate(edges):
        a, b = nodes[e["a"]], nodes[e["b"]]
        segs[i] = ((a["x"], a["y"]), (b["x"], b["y"]))
    return {"nodes": {v: dict(p, h=card_h) for v, p in nodes.items()},
            "edges": edges, "segments": segs}


def certificate(scene: dict, graph_name: str = "", layer: str = "2D",
                gates: Optional[dict] = None,
                notes: Optional[List[str]] = None) -> dict:
    nodes: Dict[str, dict] = scene["nodes"]
    edges: List[dict] = scene["edges"]
    segs: dict = scene["segments"]
    ids = list(nodes)
    notes = list(notes or [])

    # 1. 直线交叉
    crossings = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            si, sj = segs[i], segs[j]
            if seg_cross(si[0], si[1], sj[0], sj[1]):
                crossings.append({"edges": [f"{ei['a']}->{ei['b']}",
                                            f"{ej['a']}->{ej['b']}"],
                                  "at": si[1] if si[0] == sj[0] and si[1] == sj[1]
                                  else _interpolate(si, sj)})

    # 2. 线穿无关卡（Liang-Barsky）：外扩 INFLATE 口径 + 0px 真穿口径
    occ_inflated, occ_true = [], []
    for i in range(len(edges)):
        s = segs[i]
        for v in ids:
            if v in (edges[i]["a"], edges[i]["b"]):
                continue
            p = nodes[v]
            if seg_hits_rect(s[0][0], s[0][1], s[1][0], s[1][1],
                             p["x"], p["y"], p["w"] / 2 + INFLATE, p["h"] / 2 + INFLATE):
                occ_inflated.append({"edge": f"{edges[i]['a']}->{edges[i]['b']}", "card": v})
            if seg_hits_rect(s[0][0], s[0][1], s[1][0], s[1][1],
                             p["x"], p["y"], p["w"] / 2, p["h"] / 2):
                occ_true.append({"edge": f"{edges[i]['a']}->{edges[i]['b']}", "card": v})

    # 3. 平均边长（中心距）
    avg_len = (sum(math.dist(segs[i][0], segs[i][1]) for i in segs) / len(segs)) if segs else 0.0

    # 4. 行对齐率（视觉同行：y 差 ≤ ROW_EPS 成组计数）
    ysorted = sorted(p["y"] for p in nodes.values())
    aligned, i = 0, 0
    while i < len(ysorted):
        j = i
        while j + 1 < len(ysorted) and ysorted[j + 1] - ysorted[j] <= ROW_EPS:
            j += 1
        if j > i:
            aligned += j - i + 1
        i = j + 1
    row_rate = aligned / len(ids) if ids else 0.0

    # 5. 卡间净距（全对最小）
    gaps = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            va, vb = nodes[ids[a]], nodes[ids[b]]
            gaps.append(rect_gap(va["x"], va["y"], va["w"], va["h"],
                                 vb["x"], vb["y"], vb["w"], vb["h"]))
    min_gap = min(gaps) if gaps else 0.0

    # 排布第一优先：间距变异系数 CV（最近邻中心距 std/mean）
    nn = []
    for a in ids:
        dists = [math.dist((nodes[a]["x"], nodes[a]["y"]),
                           (nodes[b]["x"], nodes[b]["y"]))
                 for b in ids if b != a]
        if dists:
            nn.append(min(dists))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn) if nn and mean_nn else 0.0

    W = max(p["x"] + p["w"] / 2 for p in nodes.values()) - min(p["x"] - p["w"] / 2 for p in nodes.values())
    H = max(p["y"] + p["h"] / 2 for p in nodes.values()) - min(p["y"] - p["h"] / 2 for p in nodes.values())

    metrics = {
        "crossings": len(crossings),
        "crossing_details": crossings[:10],
        "occlusions_inflated4px": len(occ_inflated),
        "occlusions_true_0px": len(occ_true),
        "occlusion_details_true": occ_true[:10],
        "avg_edge_length": round(avg_len, 1),
        "row_align_rate": round(row_rate, 3),
        "min_card_gap": round(min_gap, 1),
        "spacing_cv": round(cv, 3),
        "bbox": [round(W), round(H)],
    }

    g = {
        "crossings_zero": metrics["crossings"] == 0,
        "min_gap_ge_16": metrics["min_card_gap"] >= 16,
        "row_align_ge_060": metrics["row_align_rate"] >= 0.60,
        "cv_le_035": metrics["spacing_cv"] <= 0.35,
    }
    if gates:
        for k, v in gates.items():
            g[k] = v
    g_pass = sum(1 for v in g.values() if v)

    # 诚实分级
    arrangement_ok = g["min_gap_ge_16"] and g["cv_le_035"]
    if metrics["crossings"] == 0 and arrangement_ok:
        grade = "最优"
        grade_note = "排布要求满足 + 线 0 交叉"
    elif arrangement_ok and metrics["crossings"] <= 2:
        grade = "其次"
        grade_note = ("排布要求满足 + 交叉 ≤2 处（坐标已入证书供复核）；"
                      "互斥时保排布、放交叉")
    else:
        grade = "未获证书"
        grade_note = ("排布要求未满足或交叉 >2 处——如实不评级，"
                      "放宽预算换的证书不冒充成品")

    return {
        "tool": "stdraw", "version": "0.1.0", "layer": layer,
        "graph": graph_name,
        "n": len(ids), "m": len(edges),
        "coords": "delivered/rounded",     # 一切验证跑在交付坐标上
        "metrics": metrics,
        "gates": g,
        "gates_passed": f"{g_pass}/{len(g)}",
        "grade": grade,
        "grade_note": grade_note,
        "honest_notes": notes,
        "no_zero_crossing_claim_for_all_graphs": (
            "CLD 环多常不可平面，0 交叉有数学边界；本证书只对本图本布局成立"),
    }


def _interpolate(si, sj):
    """两线段交点的近似坐标（竖线/直线通用：解两直线方程）。"""
    (x1, y1), (x2, y2) = si
    (x3, y3), (x4, y4) = sj
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < EPS:
        return [round(si[1][0]), round(si[1][1])]
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return [round(px), round(py)]
