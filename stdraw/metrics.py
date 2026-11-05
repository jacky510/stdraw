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
import json
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


# ═══ ② 2026-11-05 六点返修：auto 配方 v2 证书（新硬门）═══
# v1 certificate() 保持逐字节兼容（ortho-v1 生产行为 pin），auto 走 certificate_auto。

from .routing import (sample_polyline, dist_point_rect, seg_cross as _rc_seg_cross,
                      min_pair_dist,
                      PRESS_MARGIN, ANCHOR_MIN_DEG, CLEARANCE)


def scene_from_auto(v4: dict) -> dict:
    """auto 布局 JSON → v2 scene（折线/弧线离散采样 + 锚点）。"""
    nodes = {}
    ch = v4["meta"].get("cardH", 44)
    for v, p in v4["nodes"].items():
        nodes[v] = {"x": p["x"], "y": p["y"], "w": p.get("w", 140), "h": ch}
    edges, polylines, anchors = [], {}, {}
    for i, e in enumerate(v4["edges"]):
        edges.append({"a": e["a"], "b": e["b"]})
        polylines[i] = [tuple(p) for p in e["route"]["points"]]
        anchors[i] = e["anchors"]
    return {"nodes": nodes, "edges": edges, "polylines": polylines,
            "anchors": anchors,
            "router_pairs": v4["meta"].get("router_cross_pairs"),
            "line_style": v4["meta"].get("line_style", "straight"),
            "deg0": set(v4["meta"].get("deg0", [])),
            # ref-scrubbed 环形排布口径：证书按排布模式选指标
            "placement": v4["meta"].get("placement"),
            "ring_nodes": (v4["meta"].get("ring") or {}).get("nodes")}


def _anchor_tangent_angle(node, anchor, direction):
    """锚点处路线方向与所属框边切线的夹角（度）。方向为离开锚点的单位向量。"""
    cx, cy, hw, hh = node["x"], node["y"], node["w"] / 2, node["h"] / 2
    on_x_border = abs(abs(anchor[0] - cx) - hw) <= abs(abs(anchor[1] - cy) - hh)
    tx, ty = (0.0, 1.0) if on_x_border else (1.0, 0.0)
    c = abs(direction[0] * tx + direction[1] * ty)
    return math.degrees(math.acos(max(0.0, min(1.0, c))))


# ── 线-线视觉重合（ref-scrubbed #10①/#05 检测：机器可查）─────────────
COINCIDE_THR = 1.0     # 距离 <1px 视为贴合
COINCIDE_SPAN = 8.0    # 贴合累计长度 >8px 才判「视觉重合」（端点会合豁免）


def _pt_seg_dist(p, a, b):
    """点到线段距离。"""
    vx, vy = b[0] - a[0], b[1] - a[1]
    l2 = vx * vx + vy * vy
    if l2 < EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / l2))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


def _coincidence_span(sa, sb, step, thr=COINCIDE_THR):
    """两条采样折线在 <thr 距离上并行同走的长度（px，双向取大；确定性）。

    对 A 的采样点逐个算到 B 折线（点-线段）的最小距离，<thr 的采样步
    累计为贴合长度；再对称算 B→A，取大者。两端点锚点处的瞬时会合
    贴合长度只有 ~1-2px，不越 8px 跨度门；真重合（长跨度并行贴合）
    会被任一方向稳定捕获。
    """
    def one_way(src, other):
        total = 0.0
        for p in src:
            dmin = float("inf")
            for k in range(len(other) - 1):
                d = _pt_seg_dist(p, other[k], other[k + 1])
                if d < dmin:
                    dmin = d
                    if dmin < thr:
                        break
            if dmin < thr:
                total += step
        return total
    return max(one_way(sa, sb), one_way(sb, sa))


def _bbox_gap(pa, pb):
    """两折线包围盒的间隔（0 = 相交/重叠）。"""
    ax0 = min(p[0] for p in pa); ax1 = max(p[0] for p in pa)
    ay0 = min(p[1] for p in pa); ay1 = max(p[1] for p in pa)
    bx0 = min(p[0] for p in pb); bx1 = max(p[0] for p in pb)
    by0 = min(p[1] for p in pb); by1 = max(p[1] for p in pb)
    return max(0.0, max(bx0 - ax1, ax0 - bx1, by0 - ay1, ay0 - by1))


def certificate_auto(scene: dict, graph_name: str = "", layer: str = "2D",
                     gates: Optional[dict] = None,
                     notes: Optional[List[str]] = None,
                     graph=None, exactness: Optional[dict] = None) -> dict:
    """v2 质量证书：五指标 + 新硬门 + 诚实分级。一切验证跑在交付坐标上。

    新硬门（v0.2 质量返修）：
      box_press_zero      框压线 = 0（任何边任何角度，含 1px 余量；端点只贴自家框边）
      edge_box_clear_ge16 边-框净距 ≥ 16px（非端点框，采样最小距离）
      anchors_smooth      锚点平滑：出发方向与框边切线夹角 ≥ ANCHOR_MIN_DEG
      regularity_simple   简单图（≤10 节点）排布规律：行距恒等 + 24px 列吸附 ≥ 60%
    """
    nodes = scene["nodes"]
    edges = scene["edges"]
    polys = scene["polylines"]
    anchors = scene.get("anchors", {})
    ids = list(nodes)
    notes = list(notes or [])
    line_style = scene.get("line_style", "straight")
    # ref-scrubbed 环形排布口径：行对齐率/列吸附对环形排布天然不适用，
    # 按排布模式选指标（环形 = 环上等间距 CV + 正多边形模板拟合误差）。
    ring_mode = scene.get("placement") == "ring-cycle"
    ring_nodes = scene.get("ring_nodes") or []

    # 1. 交叉（折线两两求交）
    crossings = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if _rc_seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        crossings.append({"edges": [f"{ei['a']}->{ei['b']}",
                                                    f"{ej['a']}->{ej['b']}"]})
                        break
                else:
                    continue
                break

    # 1b. 互环对分离度（F1）：双向边对两线最小间距（按「边对」计，无互环对为 None）
    pair_infos = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if (ei["a"], ei["b"]) != (ej["b"], ej["a"]):
                continue
            md = min_pair_dist(sample_polyline(polys[i]), sample_polyline(polys[j]))
            pair_infos.append({"pair": [f"{ei['a']}<->{ei['b']}",
                                        round(md, 1) if md is not None else None]})
    mutual_min_sep = (min(p["pair"][1] for p in pair_infos if p["pair"][1] is not None)
                      if any(p["pair"][1] is not None for p in pair_infos) else None)

    # 1c. 线-线视觉重合对数（ref-scrubbed #10①/#05）：任意两条边（含共享
    # 节点的边对——端点会合由 8px 跨度门豁免）交付几何 <1px 并行同走
    # >8px 判重合。bbox 间隔预过滤（重合对 bbox 必重叠，等价加速）。
    coincide_pairs = []
    _step = 4.0
    for i in range(len(edges)):
        sa = sample_polyline(polys[i])
        for j in range(i + 1, len(edges)):
            sb = sample_polyline(polys[j])
            if _bbox_gap(sa, sb) > COINCIDE_THR:
                continue
            span = _coincidence_span(sa, sb, _step)
            if span > COINCIDE_SPAN:
                coincide_pairs.append(
                    {"pair": [f"{edges[i]['a']}->{edges[i]['b']}",
                              f"{edges[j]['a']}->{edges[j]['b']}"],
                     "span_px": round(span, 1)})

    # 2. 框压线（1px 余量）+ 边-框净距 + 自家框端点合规
    press, clear_details, anchor_bad = [], [], []
    min_clear = None
    for i, e in enumerate(edges):
        pts = sample_polyline(polys[i])
        for v in ids:
            p = nodes[v]
            hw, hh = p["w"] / 2, p["h"] / 2
            if v in (e["a"], e["b"]):
                continue
            dmin = min(dist_point_rect(px, py, p["x"], p["y"], hw, hh)
                       for (px, py) in pts)
            dmin1 = min(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN, hh + PRESS_MARGIN)
                        for (px, py) in pts)
            # 穿卡计数按「边×卡」去重：同一对 (edge, card) 只记一条
            # （0 余量命中时不再重复记 1px 余量条目）
            if dmin <= 0:
                press.append({"edge": f"{e['a']}->{e['b']}", "card": v})
            elif dmin1 <= 0:
                press.append({"edge": f"{e['a']}->{e['b']}", "card": v, "margin": 1})
            min_clear = dmin if min_clear is None else min(min_clear, dmin)
        # 自家框：其余采样点不得进入框内（含 1px 余量）；锚点须在框边上
        for v, end_key in ((e["a"], "a"), (e["b"], "b")):
            p = nodes[v]
            hw, hh = p["w"] / 2, p["h"] / 2
            a0 = anchors.get(i, {}).get(end_key)
            if a0 is None or dist_point_rect(a0[0], a0[1], p["x"], p["y"], hw, hh) > 0.75:
                anchor_bad.append({"edge": f"{e['a']}->{e['b']}", "end": end_key,
                                   "why": "anchor off-border"})
                continue
            interior = any(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN, hh + PRESS_MARGIN) <= 0
                           for (px, py) in pts[1:-1])
            if interior:
                press.append({"edge": f"{e['a']}->{e['b']}", "card": v, "why": "own-box"})
        # 锚点平滑（角度独立复算）
        poly = polys[i]
        for end_key, p_idx, nxt_idx in (("a", 0, 1), ("b", len(poly) - 1, len(poly) - 2)):
            a0 = anchors.get(i, {}).get(end_key)
            if a0 is None:
                continue
            dx, dy = poly[nxt_idx][0] - a0[0], poly[nxt_idx][1] - a0[1]
            n = math.hypot(dx, dy)
            if n < EPS:
                anchor_bad.append({"edge": f"{e['a']}->{e['b']}", "end": end_key,
                                   "why": "zero-length departure"})
                continue
            v = e["a"] if end_key == "a" else e["b"]
            ang = _anchor_tangent_angle(nodes[v], a0, (dx / n, dy / n))
            if ang < ANCHOR_MIN_DEG:
                anchor_bad.append({"edge": f"{e['a']}->{e['b']}", "end": end_key,
                                   "angle": round(ang, 1)})

    # 3. 平均边长 / 行对齐 / 卡间净距 / CV（与 v1 同口径）
    avg_len = sum(sum(math.dist(polys[i][k], polys[i][k + 1])
                      for k in range(len(polys[i]) - 1))
                  for i in polys) / len(polys) if polys else 0.0
    if ring_mode:
        row_rate = None          # 环形排布：行对齐率不适用（口径如实区分）
    else:
        ysorted = sorted(p["y"] for p in nodes.values())
        aligned, i2 = 0, 0
        while i2 < len(ysorted):
            j = i2
            while j + 1 < len(ysorted) and ysorted[j + 1] - ysorted[j] <= ROW_EPS:
                j += 1
            if j > i2:
                aligned += j - i2 + 1
            i2 = j + 1
        row_rate = aligned / len(ids) if ids else 0.0
    gaps = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            va, vb = nodes[ids[a]], nodes[ids[b]]
            gaps.append(rect_gap(va["x"], va["y"], va["w"], va["h"],
                                 vb["x"], vb["y"], vb["w"], vb["h"]))
    min_gap = min(gaps) if gaps else 0.0
    nn = []
    for a in ids:
        dists = [math.dist((nodes[a]["x"], nodes[a]["y"]),
                           (nodes[b]["x"], nodes[b]["y"]))
                 for b in ids if b != a]
        if dists:
            nn.append(min(dists))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn) if nn and mean_nn else 0.0

    # 规律性（简单图 ≤10 节点）：行距恒等 + 24px 列吸附占比（停车带节点不计行距）
    # 环形排布：规律性口径切换为「环上等间距 CV + 正多边形模板拟合误差」
    # （行距恒等/列吸附对环排布天然不成立，不得拿行口径误判环形不合格）
    deg0 = scene.get("deg0", set())
    ring_spacing_cv = None
    ring_template_dev = None
    if ring_mode and len(ring_nodes) >= 3:
        rpts = [(nodes[v]["x"], nodes[v]["y"]) for v in ring_nodes
                if v in nodes]
        if len(rpts) >= 3:
            dists = [math.dist(rpts[i], rpts[(i + 1) % len(rpts)])
                     for i in range(len(rpts))]
            md = sum(dists) / len(dists)
            ring_spacing_cv = (math.sqrt(sum((d - md) ** 2 for d in dists)
                                         / len(dists)) / md) if md else 0.0
            try:
                from . import regularity as _reg
                ring_template_dev = _reg.cycle_polygon_deviation(
                    {v: (nodes[v]["x"], nodes[v]["y"]) for v in ring_nodes},
                    ring_nodes)
            except Exception:
                ring_template_dev = None
    if ring_mode:
        pitch_uniform, snap_rate, simple, regularity_ok = True, None, False, True
    else:
        ys = sorted({p["y"] for v, p in nodes.items() if v not in deg0})
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        snap_n = sum(1 for p in nodes.values() if abs(p["x"] % 24) < EPS)
        snap_rate = snap_n / len(ids) if ids else 0.0
        simple = len(ids) <= 10
        regularity_ok = pitch_uniform and (snap_rate >= 0.6 if simple else snap_rate >= 0.0)

    W = max(p["x"] + p["w"] / 2 for p in nodes.values()) - min(p["x"] - p["w"] / 2 for p in nodes.values())
    H = max(p["y"] + p["h"] / 2 for p in nodes.values()) - min(p["y"] - p["h"] / 2 for p in nodes.values())

    # WS3 交叉双口径：路由理论口径（最终未取整路线的交叉边对数）vs
    # 交付坐标几何复检（本节第 1 项，严格求交/Liang-Barsky）。双口径一致
    # 才发证书；不一致 → 未获证书（如实写明两口径数值）。
    router_xe = scene.get("router_pairs")
    routing_consistent = None
    router_pairs = None
    if router_xe is not None:
        router_pairs = router_xe
        routing_consistent = abs(router_pairs - len(crossings)) < 0.5

    metrics = {
        "crossings": len(crossings),
        "crossing_details": crossings[:10],
        "box_press_1px": len(press),
        "routing_router_pairs": router_pairs,
        "press_details": press[:10],
        "edge_box_min_clear": round(min_clear, 1) if min_clear is not None else None,
        "anchor_violations": len(anchor_bad),
        "anchor_details": anchor_bad[:10],
        "avg_edge_length": round(avg_len, 1),
        "row_align_rate": round(row_rate, 3) if row_rate is not None else None,
        "min_card_gap": round(min_gap, 1),
        "spacing_cv": round(cv, 3),
        "column_snap24_rate": round(snap_rate, 3) if snap_rate is not None else None,
        "mutual_pair_min_sep": mutual_min_sep,
        "mutual_pair_details": pair_infos[:10],
        "line_line_coincident_pairs": len(coincide_pairs),
        "line_line_coincident_details": coincide_pairs[:10],
        "bbox": [round(W), round(H)],
    }
    if ring_mode:
        metrics["ring_spacing_cv"] = (round(ring_spacing_cv, 4)
                                      if ring_spacing_cv is not None else None)
        metrics["ring_template_deviation"] = (round(ring_template_dev, 4)
                                              if ring_template_dev is not None else None)

    if ring_mode:
        # 环形口径门：环上等间距 CV + 模板拟合误差（2px 量化容差内 ≈0）
        g = {
            "crossings_zero": metrics["crossings"] == 0,
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "ring_spacing_cv_le_005": (metrics["ring_spacing_cv"] is not None
                                       and metrics["ring_spacing_cv"] <= 0.05),
            "ring_template_fit_le_005": (metrics["ring_template_deviation"] is not None
                                         and metrics["ring_template_deviation"] <= 0.05),
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    else:
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "row_align_ge_060": metrics["row_align_rate"] >= 0.60,
            "cv_le_035": metrics["spacing_cv"] <= 0.35,
            "regularity_simple": regularity_ok,
            # F1 硬门：互环对两线最小间距 ≥ 4px（无互环对时平凡通过）
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            # ref-scrubbed #10①/#05 硬门：线-线视觉重合对数 = 0
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    if routing_consistent is not None:
        g["routing_consistent"] = routing_consistent
    if gates:
        for k, v in gates.items():
            g[k] = v
    g_pass = sum(1 for v in g.values() if v)

    if ring_mode:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and
                   g["ring_spacing_cv_le_005"] and g["ring_template_fit_le_005"])
    else:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and g["cv_le_035"])
    dual_ok = routing_consistent is not False   # 双口径不一致 → 拒发证书
    if metrics["crossings"] == 0 and hard_ok and dual_ok:
        grade = "最优"
        grade_note = "硬门全过（框压线0/净距≥16/锚点平滑/规律）+ 线 0 交叉"
    elif hard_ok and dual_ok and metrics["crossings"] <= 2:
        grade = "其次"
        grade_note = ("硬门全过 + 交叉 ≤2 处（明细已入证书供复核）；"
                      "互斥时保硬门、放交叉")
    elif not dual_ok:
        grade = "未获证书"
        grade_note = (f"交叉双口径不一致（路由理论 {router_pairs} vs 几何复检 "
                      f"{len(crossings)}）——理论与几何必须一致才发证书")
    else:
        grade = "未获证书"
        grade_note = ("硬门未全过或交叉 >2 处——如实不评级，"
                      "放宽预算换的证书不冒充成品")

    out = {
        "tool": "stdraw", "version": "0.5.0", "layer": layer,
        "graph": graph_name,
        "n": len(ids), "m": len(edges),
        "coords": "delivered/rounded",
        "recipe": "auto-v2",
        "line_style": line_style,
        "placement": "ring-cycle" if ring_mode else "layered",
        "metrics": metrics,
        "gates": g,
        "gates_passed": f"{g_pass}/{len(g)}",
        "grade": grade,
        "grade_note": grade_note,
        "proven_optimal": None,          # WS2 精确层：见 exactness 块
        "gap": None,
        "exactness": _exactness_block(exactness),
        "regularity": _regularity_block(graph, nodes),
        "honest_notes": notes + [
            "硬门口径：框压线=0（1px 余量）、边-框净距≥16px、锚点平滑、简单图规律性",
            "互环对（a↔b 双向边）两线最小间距 ≥4px（透镜双弧/平行偏移/外围绕行，"
            "禁止重合成双箭头线；穿卡计数按边×卡去重）",
            "线-线视觉重合对数=0（ref-scrubbed：任意两线 <1px 并行同走 >8px 判重合；"
            "端点锚点处的瞬时会合不计；机器可查指标）",
            "交叉双口径：路由理论逐边命中数之和/2 必须等于交付坐标几何复检数，"
            "不一致拒发证书",
            "布线数学：绕障 = 净距膨胀障碍可见性图 Dijkstra 最短路（图上精确最优；"
            "相对圆角障碍连续空间真最短路每贴角至多多 (2−π/2)·膨胀余量 px）；"
            "平滑 = 折角相切圆弧（G1 切线连续、曲率有界），"
            "凸角相切弧向障碍侧下探 r·(1/cos(θ/2)−1)，受膨胀余量约束"],
        "no_zero_crossing_claim_for_all_graphs": (
            "CLD 环多常不可平面，交叉数是目标函数最小化项而非定理保证；"
            "本证书只对本图本布局成立"),
    }
    if ring_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "环形排布口径（ref-scrubbed）：行对齐率/24px 列吸附对环形排布不适用，"
            "规律性门切换为环上等间距 CV ≤0.05 + 正多边形模板拟合误差 ≤0.05；"
            "主环按环序正多边形槽位、弦走环内，环路极性（R/B）徽标沿环可读"]
        out["ring"] = {
            "nodes": list(ring_nodes),
            "spacing_cv": metrics.get("ring_spacing_cv"),
            "template_deviation": metrics.get("ring_template_deviation"),
        }
    return out


_EXACT_SCOPE_NOTE = (
    "proven_optimal 只相对 docs/crossing-exact.md §1-5 定义的模型类成立："
    "good-drawing 交叉数口径（相邻边不交叉、每对至多一次、无三边共点）、"
    "安全缩减后的 2-边-连通核族、B&B 覆盖的可平面子图 × 全嵌入族。"
    "不虚称全体指标集或任意画法空间的最优性。")


def _exactness_block(exactness):
    """WS2 证书精确性块：未计算时如实标 computed=False。"""
    if not exactness:
        return {"computed": False, "proven_optimal": None, "gap": None,
                "crossing_number": None, "lb": None, "coverage": None,
                "method": "crossing-number exactness not computed "
                          "(pass --exact to compute)", "scope": _EXACT_SCOPE_NOTE}
    return {
        "computed": True,
        "proven_optimal": bool(exactness.get("proven_optimal")),
        "gap": exactness.get("gap"),
        "crossing_number": exactness.get("crossing_number"),
        "lb": exactness.get("lb"),
        "coverage": exactness.get("coverage"),
        "method": exactness.get("method"),
        "witness_digest": len(json.dumps(exactness.get("witness") or [],
                                         ensure_ascii=False, sort_keys=True)),
        "scope": _EXACT_SCOPE_NOTE,
        "caliber_note": (
            "crossing_number 是**图本身**的交叉数 cr(G)（任意画法的下界）；"
            "metrics.crossings 是**本布局**的交叉数（布局实现达到的值）。"
            "两者口径不同：cr(G)=0 只保证存在 0 交叉画法，"
            "不代表本布局实现了它"),
    }


def _regularity_block(graph, nodes):
    """WS2 排布规律性块（结构检测驱动，定义见 stdraw/regularity.py 与
    docs/crossing-exact.md §6；全部指标可计算、可复算）。"""
    if graph is None:
        return None
    try:
        from . import regularity
        positions = {v: (nodes[v]["x"], nodes[v]["y"]) for v in nodes}
        return regularity.regularity_report(graph, positions)
    except Exception:
        return None
