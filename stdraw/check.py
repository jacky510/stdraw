# -*- coding: utf-8 -*-
"""几何自检（11 项）—— 只吃布局 JSON，通用。

检查跑在**交付坐标**上（取整/导出后的那份 JSON），这是纪律不是优化项。
输出 report JSON（可当 CI 门禁），fail>0 时 exit 1。
"""
import json
import math
import sys
from typing import List


# ── ref-scrubbed #13 检查辅助：SVG path d（M/L/A）解析与几何核对 ──
def _arc_points(x0, y0, rx, sweep, x1, y1, n=48):
    """SVG 圆弧（rot=0、正圆、rx=ry；本引擎 laf 恒 0=短弧）→ 采样点列。"""
    rx = abs(rx)
    if rx < 1e-9 or (abs(x1 - x0) < 1e-12 and abs(y1 - y0) < 1e-12):
        return [(x0, y0), (x1, y1)]
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = x1 - x0, y1 - y0
    chord = math.hypot(dx, dy)
    if chord < 1e-12:
        return [(x0, y0), (x1, y1)]
    if chord / 2.0 > rx:
        rx = chord / 2.0        # 退化保护：半径不足时取半圆
    h = math.sqrt(max(0.0, rx * rx - (chord / 2.0) ** 2))
    # 弦两侧两个候选圆心；短弧下扫过角 ∈(-π,π)，取扫向与 sweep 一致者
    for sgn in (1.0, -1.0):
        cx = mx - dy / chord * h * sgn
        cy = my + dx / chord * h * sgn
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        da = a1 - a0
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        if abs(da) > 1e-9 and (da > 0) == (sweep == 1):
            return [(cx + rx * math.cos(a0 + da * k / n),
                     cy + rx * math.sin(a0 + da * k / n)) for k in range(n + 1)]
    return [(x0, y0), (x1, y1)]


def _parse_path_d(d):
    """path d（仅 M/L/A，本引擎输出形态）→ 元素列表。

    ('L', (x0,y0), (x1,y1)) 或 ('A', [(采样点)...])。不识别的命令返回 None。
    """
    toks = d.replace(",", " ").split()
    elems, cur, i = [], None, 0
    try:
        while i < len(toks):
            t = toks[i]
            if t == "M":
                cur = (float(toks[i + 1]), float(toks[i + 2]))
                i += 3
            elif t == "L":
                p = (float(toks[i + 1]), float(toks[i + 2]))
                elems.append(("L", cur, p))
                cur = p
                i += 3
            elif t == "A":
                rx = float(toks[i + 1])
                sweep = int(float(toks[i + 5]))
                p = (float(toks[i + 6]), float(toks[i + 7]))
                elems.append(("A", _arc_points(cur[0], cur[1], rx, sweep,
                                               p[0], p[1])))
                cur = p
                i += 8
            else:
                return None
    except (ValueError, IndexError, TypeError):
        return None
    return elems


def _path_d_all_points(elems):
    out = []
    for el in elems:
        if el[0] == "L":
            out.append(el[1])
            out.append(el[2])
        else:
            out.extend(el[1])
    return out


def _max_poly_dev(pa, pb):
    """两折线（采样点列）的双向最大最小距（Hausdorff 采样口径）。"""
    from .routing import _pt_seg_dist
    def one_way(src, other):
        worst = 0.0
        for p in src:
            dmin = min(_pt_seg_dist(p, other[k], other[k + 1])
                       for k in range(len(other) - 1))
            worst = max(worst, dmin)
        return worst
    return max(one_way(pa, pb), one_way(pb, pa))


def _path_d_g1_max_deg(elems):
    """path_d 元素序列的最大切向不连续角（度）。L↔A 连接处解析切向。"""
    def line_dir(a, b):
        n = math.hypot(b[0] - a[0], b[1] - a[1])
        return ((b[0] - a[0]) / n, (b[1] - a[1]) / n) if n > 1e-12 else None

    def elem_dirs(el):
        if el[0] == "L":
            d = line_dir(el[1], el[2])
            return (d, d)
        pts = el[1]
        # 弧端切向 = 端点弦向（n=48 采样，弦向与真切向差 <0.1°）
        return (line_dir(pts[0], pts[1]), line_dir(pts[-2], pts[-1]))

    worst = 0.0
    for k in range(len(elems) - 1):
        d_out = elem_dirs(elems[k])[1]
        d_in = elem_dirs(elems[k + 1])[0]
        if d_out is None or d_in is None:
            continue
        ang = math.degrees(math.acos(max(-1.0, min(1.0,
                       d_out[0] * d_in[0] + d_out[1] * d_in[1]))))
        worst = max(worst, ang)
    return worst


def geometry_report(layout: dict) -> dict:
    meta = layout.get("meta", {})
    if meta.get("recipe") == "auto-v2":
        return auto_geometry_report(layout)
    nodes, edges, bars = layout["nodes"], layout["edges"], layout.get("bars", {})
    meta = layout["meta"]
    W, H = layout["viewBox"][2], layout["viewBox"][3]
    CARD_H = meta.get("cardH", 42)
    CW = {v: p.get("w", 140) for v, p in nodes.items()}
    report = {"checks": [], "fail": 0}

    def chk(name, ok, detail=""):
        report["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            report["fail"] += 1
        print(("PASS " if ok else "FAIL ") + name + ("  " + detail if detail else ""))

    # 1. 逐边 0 相交（含共线重叠/近距粘连）
    bad = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a, b = edges[i], edges[j]
            lo1, hi1 = sorted((a["y1"], a["y2"]))
            lo2, hi2 = sorted((b["y1"], b["y2"]))
            if a["x"] == b["x"]:
                if lo1 < hi2 and lo2 < hi1:
                    bad.append((i, j, "共线重叠"))
            elif abs(a["x"] - b["x"]) < 8:
                if lo1 < hi2 and lo2 < hi1:
                    bad.append((i, j, "近距平行粘连"))
    chk("1. 逐边 0 相交（含共线重叠/近距粘连）", not bad,
        f"{len(edges)} 条边两两求交，冲突 {len(bad)}" + (str(bad[:5]) if bad else ""))

    # 2. 线端点接驳 + 无关线只允许遮挡式穿卡
    bad2 = []
    for e in edges:
        x = e["x"]
        for endv in (e["a"], e["b"]):
            cx = nodes[endv]["x"]
            in_card = abs(x - cx) <= CW[endv] / 2
            in_bar = endv in bars and bars[endv][0] - 1 <= x <= bars[endv][1] + 1
            if not (in_card or in_bar):
                bad2.append((e["a"] + "->" + e["b"], endv))
    chk("2. 线端点接驳端点节点（卡片或引线内）", not bad2, str(bad2[:5]))

    # 3. 引线不被外来线触碰
    bad3 = []
    for v, (b0, b1) in bars.items():
        cy = nodes[v]["y"]
        for e in edges:
            if v in (e["a"], e["b"]):
                continue
            if b0 - 1 <= e["x"] <= b1 + 1:
                lo, hi = sorted((e["y1"], e["y2"]))
                if lo - 1 <= cy <= hi + 1:
                    bad3.append((v, e["a"] + "->" + e["b"]))
    chk("3. 引线(bar)无外来线搭接/穿越", not bad3, str(bad3[:5]))

    # 4. 卡片两两不重叠
    bad4 = []
    items = list(nodes.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (v1, p1), (v2, p2) = items[i], items[j]
            if abs(p1["x"] - p2["x"]) < (CW[v1] + CW[v2]) / 2 + 2 and \
               abs(p1["y"] - p2["y"]) < CARD_H + 2:
                bad4.append((v1, v2))
    chk("4. 卡片两两不重叠（逐节点宽）", not bad4, str(bad4[:5]))

    # 5. 网格对齐
    deg0 = set(meta.get("deg0", []))
    rowy = {}
    for v, p in nodes.items():
        if v in deg0:
            continue
        rowy.setdefault(p["y"], []).append(v)
    pitch_ok = all((b - a) == meta["pitch"] for a, b in zip(sorted(rowy), sorted(rowy)[1:]))
    rowdesc = "; ".join(f"y={y}:{len(vs)}" for y, vs in sorted(rowy.items()))
    chk("5a. 同行节点 y 完全一致（按 y 分组）", len(rowy) == meta["rows"],
        f"{len(rowy)} 个 y 值 = meta.rows={meta['rows']}；{rowdesc}")
    chk("5b. 行距恒等 pitch", pitch_ok, f"pitch={meta['pitch']}")
    odd = [v for v, p in nodes.items() if p["x"] % 2 or p["y"] % 2]
    chk("5c. 全部坐标 2px 网格（偶数）", not odd, str(odd))
    chk("5d. 线全部严格垂直（0 拐弯 0 斜线）",
        all(e["y1"] != e["y2"] for e in edges),
        f"{len(edges)} 条边全部 x1==x2；拐点数 0")

    # 6. 箭头位置合法
    bad6 = []
    for e in edges:
        ax, ay = e["arrow"][0], e["arrow"][1]
        b, yb = nodes[e["b"]], e["y2"]
        in_card = abs(ax - b["x"]) <= CW[e["b"]] / 2 + 4
        in_bar = e["b"] in bars and bars[e["b"]][0] - 6 <= ax <= bars[e["b"]][1] + 6
        if not (in_card or in_bar):
            bad6.append((e["a"] + "->" + e["b"], "箭头超出目标卡/引线横向范围"))
        if abs(ay - yb) > CARD_H / 2 + 12:
            bad6.append((e["a"] + "->" + e["b"], "箭头距目标行中心过远"))
    chk("6. 箭头指向目标端卡片边缘/引线", not bad6, str(bad6[:5]))

    # 7. viewBox 完整包含
    out = []
    for v, p in nodes.items():
        if not (0 < p["x"] - CW[v] / 2 and p["x"] + CW[v] / 2 < W and
                0 < p["y"] - CARD_H / 2 and p["y"] + CARD_H / 2 < H):
            out.append(v)
    for e in edges:
        if not (0 < e["x"] < W):
            out.append(e["a"] + "->" + e["b"])
    chk("7. 全部内容在 viewBox 内", not out, str(out))

    # 8. 渲染比例（1280×800 档）
    s = min(1280 / W, 680 / H) if W and H else 0
    fs_title, fs_value = meta.get("fs", [12.5, 14.0])
    chk("8. 1280×800 渲染比例 ≥ 0.85", s >= 0.85,
        f"viewBox {W}×{H} → s={s:.3f}；标题 {fs_title}×{s:.2f}≈{fs_title * s:.1f}px")

    report["summary"] = {
        "viewBox": [W, H], "aspect": round(W / H, 3) if H else 0,
        "nodes": len(nodes), "edges": len(edges),
        "bars": len(bars), "rows": meta["rows"], "pitch": meta["pitch"],
        "scale_1280x800": round(s, 3),
        "fail": report["fail"]}
    report["rows"] = rowdesc
    return report


def geometry_report_to_file(layout: dict, path: str) -> int:
    rep = geometry_report(layout)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(f"\n{len(rep['checks'])} checks, fail={rep['fail']} -> {path}")
    return 1 if rep["fail"] else 0


def run_check_file(layout_path: str, report_path: str) -> int:
    with open(layout_path, encoding="utf-8") as f:
        layout = json.load(f)
    rc = geometry_report_to_file(layout, report_path)
    sys.exit(rc)


# ═══ auto-v2 几何自检（2026-11-05 六点返修新硬门）═══
def auto_geometry_report(layout: dict) -> dict:
    from .routing import (sample_polyline, dist_point_rect, seg_cross,
                          PRESS_MARGIN, ANCHOR_MIN_DEG, CLEARANCE)
    nodes, edges = layout["nodes"], layout["edges"]
    meta = layout["meta"]
    # --from-layout 手动布局：卡距恒等/简单图规律性是「自动管线结构检查」，
    # 对手动坐标不适用（证书的 regularity 门仍如实评分，不因此放水）。
    manual_mode = bool(meta.get("from_layout"))
    # ref-scrubbed 环形排布：行距恒等/列吸附同属行结构检查，对环排布不适用
    # （证书改用环上等间距 CV + 正多边形模板拟合误差，见 metrics）。
    ring_mode = meta.get("placement") == "ring-cycle"

    # ref-scrubbed 纵列/对称排布：行口径按模式切换（纵列=主链行距恒等+列轴
    # 对齐；对称=镜像轴误差）；24px 列吸附对两模式不适用。
    column_mode = meta.get("placement") == "column-chain"
    sym_mode = meta.get("placement") == "symmetric"
    # ref-scrubbed（美学 v3）领结共点：镜像轴 = 竖直轴 x + 水平轴 y（上下环镜像）
    bowtie_mode = meta.get("placement") == "bowtie-vertex"
    W, H = layout["viewBox"][2], layout["viewBox"][3]
    CARD_H = meta.get("cardH", 44)
    CW = {v: p.get("w", 140) for v, p in nodes.items()}
    report = {"checks": [], "fail": 0}

    def chk(name, ok, detail=""):
        report["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            report["fail"] += 1
        print(("PASS " if ok else "FAIL ") + name + ("  " + detail if detail else ""))

    def polys():
        return [([tuple(p) for p in e["route"]["points"]], e)
                for e in edges]

    # 1. 交叉（折线两两求交，共享端点的边除外）
    bad = []
    P = polys()
    for i in range(len(P)):
        for j in range(i + 1, len(P)):
            pi, ei = P[i]
            pj, ej = P[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            hit = False
            for s1 in zip(pi[:-1], pi[1:]):
                for s2 in zip(pj[:-1], pj[1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                bad.append((f"{ei['a']}->{ei['b']}", f"{ej['a']}->{ej['b']}"))
    chk("1. 交叉 ≤ 2（折线/弧线采样求交；硬门互斥时保硬门放交叉）", len(bad) <= 2,
        f"{len(edges)} 条边，冲突 {len(bad)}" + (str(bad[:5]) if bad else ""))

    # 2. 框压线 = 0（1px 余量；端点只贴自家框边，自家框内不得有正长度穿越）
    bad2 = []
    for pts, e in P:
        dense = sample_polyline(pts)
        for v, p in nodes.items():
            hw, hh = CW[v] / 2, CARD_H / 2
            if v in (e["a"], e["b"]):
                continue
            if any(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN,
                                   hh + PRESS_MARGIN) <= 0 for (px, py) in dense):
                bad2.append((f"{e['a']}->{e['b']}", v))
        for v in (e["a"], e["b"]):
            p = nodes[v]
            hw, hh = CW[v] / 2, CARD_H / 2
            if any(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN,
                                   hh + PRESS_MARGIN) <= 0 for (px, py) in dense[1:-1]):
                bad2.append((f"{e['a']}->{e['b']}", v, "own"))
    chk("2. 框压线 = 0（任何角度，含 1px 余量）", not bad2, str(bad2[:5]))

    # 3. 边-框净距 ≥ 16px（非端点框）
    worst = None
    for pts, e in P:
        dense = sample_polyline(pts)
        for v, p in nodes.items():
            if v in (e["a"], e["b"]):
                continue
            hw, hh = CW[v] / 2, CARD_H / 2
            d = min(dist_point_rect(px, py, p["x"], p["y"], hw, hh) for (px, py) in dense)
            if worst is None or d < worst[0]:
                worst = (d, e["a"], e["b"], v)
    chk("3. 边-框净距 ≥ 16px", worst is None or worst[0] >= CLEARANCE - 1e-6,
        f"最小 {worst[0]:.1f}px（{worst[1]}->{worst[2]} vs {worst[3]}）" if worst else "")

    # 4. 锚点平滑：锚在框边 + 出发方向与框边切线夹角 ≥ 20°
    bad4 = []
    for pts, e in P:
        for v, idx, nidx in ((e["a"], 0, 1), (e["b"], len(pts) - 1, len(pts) - 2)):
            p = nodes[v]
            hw, hh = CW[v] / 2, CARD_H / 2
            a0 = pts[idx]
            off_border = dist_point_rect(a0[0], a0[1], p["x"], p["y"], hw, hh) > 0.75
            dx, dy = pts[nidx][0] - a0[0], pts[nidx][1] - a0[1]
            n = (dx * dx + dy * dy) ** 0.5
            on_x = abs(abs(a0[0] - p["x"]) - hw) <= abs(abs(a0[1] - p["y"]) - hh)
            tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
            c = abs(dx * tx + dy * ty) / n if n > 1e-9 else 1.0
            import math as _m
            ang = _m.degrees(_m.acos(max(0.0, min(1.0, c))))
            if off_border or ang < ANCHOR_MIN_DEG:
                bad4.append((f"{e['a']}->{e['b']}", v, round(ang, 1),
                             "off-border" if off_border else "tangential"))
    chk("4. 锚点平滑（框边锚点，切线夹角 ≥ 20°）", not bad4, str(bad4[:5]))

    # 5. 卡片两两不重叠
    bad5 = []
    items = list(nodes.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (v1, p1), (v2, p2) = items[i], items[j]
            if abs(p1["x"] - p2["x"]) < (CW[v1] + CW[v2]) / 2 + 2 and \
               abs(p1["y"] - p2["y"]) < CARD_H + 2:
                bad5.append((v1, v2))
    chk("5. 卡片两两不重叠（逐节点宽）", not bad5, str(bad5[:5]))

    # 6. 网格/行距
    deg0 = set(meta.get("deg0", []))
    rowy = {}
    for v, p in nodes.items():
        if v in deg0:
            continue
        rowy.setdefault(p["y"], []).append(v)
    pitch_ok = len({b - a for a, b in zip(sorted(rowy), sorted(rowy)[1:])}) <= 1
    odd = [v for v, p in nodes.items() if p["x"] % 2 or p["y"] % 2]
    _6a_na = ("（manual: N/A）" if manual_mode else
              "（ring: N/A）" if ring_mode else
              "（column: 主链行判）" if column_mode else
              "（sym: 全行判）" if sym_mode else "")
    if column_mode:
        spine = (meta.get("column") or {}).get("spine") or []
        sys_ = [nodes[v]["y"] for v in spine if v in nodes]
        pitch_ok = len({b - a for a, b in zip(sys_, sys_[1:])}) <= 1 if len(sys_) > 1 else True
    chk("6a. 行距恒等 pitch（停车带除外）" + _6a_na,
        True if (manual_mode or ring_mode) else pitch_ok, f"pitch={meta['pitch']}")
    chk("6b. 全部坐标 2px 网格（偶数）", not odd, str(odd))

    # 7. viewBox 完整包含
    out = []
    for v, p in nodes.items():
        if not (0 < p["x"] - CW[v] / 2 and p["x"] + CW[v] / 2 < W and
                0 < p["y"] - CARD_H / 2 and p["y"] + CARD_H / 2 < H):
            out.append(v)
    for pts, e in P:
        if any(not (0 < px < W and 0 < py < H) for (px, py) in pts):
            out.append(e["a"] + "->" + e["b"])
    chk("7. 全部内容在 viewBox 内", not out, str(out))

    # 8. 渲染比例（1280×800 档）
    s = min(1280 / W, 680 / H) if W and H else 0
    fs_title, fs_value = meta.get("fs", [12.5, 14.0])
    chk("8. 1280×800 渲染比例 ≥ 0.85", s >= 0.85,
        f"viewBox {W}×{H} → s={s:.3f}；标题 {fs_title}×{s:.2f}≈{fs_title * s:.1f}px")

    # 9. 简单图规律性（≤10 节点：行距恒等 + 24px 列吸附 ≥ 60%）
    # manual 布局：规律性属自动管线结构检查 → N/A（证书 regularity 门仍评分）
    # ring 排布：行口径不适用 → 环上等间距 CV + 正多边形模板拟合误差（与证书同口径）
    snap = sum(1 for p in nodes.values() if p["x"] % 24 == 0) / len(nodes)
    simple = len(nodes) <= 10
    if ring_mode:
        import math as _rm
        rnodes = (meta.get("ring") or {}).get("nodes") or []
        rpts = [(nodes[v]["x"], nodes[v]["y"]) for v in rnodes if v in nodes]
        if len(rpts) >= 3:
            ds = [_rm.dist(rpts[i], rpts[(i + 1) % len(rpts)]) for i in range(len(rpts))]
            md = sum(ds) / len(ds)
            rsv = (sum((d - md) ** 2 for d in ds) / len(ds)) ** 0.5 / md if md else 0.0
            from . import regularity as _reg
            rdev = _reg.cycle_polygon_deviation(
                {v: (nodes[v]["x"], nodes[v]["y"]) for v in rnodes}, rnodes)
            ring_ok = rsv <= 0.05 and rdev <= 0.05
            ring_detail = f"环上等间距 CV={rsv:.4f}，正多边形偏差 D={rdev:.4f}（门 ≤0.05）"
        else:
            ring_ok, ring_detail = False, "meta.ring.nodes 缺失/不足 3 节点"
        chk("9. 环形排布规律性（环上等间距 CV + 模板拟合）", ring_ok, ring_detail)
    elif column_mode:
        import math as _cm
        spine = (meta.get("column") or {}).get("spine") or []
        spts = [(nodes[v]["x"], nodes[v]["y"]) for v in spine if v in nodes]
        if len(spts) >= 2:
            axis = sum(p[0] for p in spts) / len(spts)
            dev = max(abs(p[0] - axis) for p in spts)
            col_ok = dev <= 2.0 and pitch_ok
            col_detail = f"主链列轴偏差 {dev:.2f}px（门 ≤2px），主链行距恒等 {pitch_ok}"
        else:
            col_ok, col_detail = False, "meta.column.spine 缺失/不足 2 节点"
        chk("9. 纵列排布规律性（主链列轴对齐 + 行距恒等）", col_ok, col_detail)
    elif sym_mode:
        sym = meta.get("symmetry") or {}
        axis_x = sym.get("axis_x") or 0.0
        pairs = sym.get("mirror_pairs") or []
        errs = []
        for l, r in pairs:
            if l in nodes and r in nodes:
                errs.append(abs((nodes[l]["x"] + nodes[r]["x"]) / 2 - axis_x))
                errs.append(abs(nodes[l]["y"] - nodes[r]["y"]))
        sym_ok = bool(errs) and max(errs) <= 2.0
        chk("9. 对称排布规律性（镜像轴误差 ≤2px）", sym_ok,
            f"镜像轴误差 {max(errs):.2f}px" if errs else "meta.symmetry.mirror_pairs 缺失")
    elif bowtie_mode:
        sym = meta.get("symmetry") or {}
        axis_x = sym.get("axis_x") or 0.0
        axis_y = sym.get("axis_y") or 0.0
        errs = []
        for l, r in sym.get("mirror_pairs") or []:
            if l in nodes and r in nodes:
                errs.append(abs(nodes[l]["x"] - nodes[r]["x"]))
                errs.append(abs((nodes[l]["y"] + nodes[r]["y"]) / 2 - axis_y))
        sh = sym.get("shared_node")
        if sh in nodes:
            errs.append(abs(nodes[sh]["x"] - axis_x))
            errs.append(abs(nodes[sh]["y"] - axis_y))
        bowtie_ok = bool(errs) and max(errs) <= 2.0
        chk("9. 领结共点排布规律性（镜像轴误差 ≤2px）", bowtie_ok,
            f"镜像轴误差 {max(errs):.2f}px" if errs else "meta.symmetry 缺失")
    else:
        chk("9. 简单图排布规律性" + ("（manual: N/A）" if manual_mode else ""),
            True if manual_mode else ((not simple) or (pitch_ok and snap >= 0.6)),
            f"n={len(nodes)}，24px 列吸附 {snap:.2f}，行距恒等 {pitch_ok}"
            + ("；manual 布局不适用" if manual_mode else ""))

    # 10. 元数据完备（recipe / line_style / engine）
    ok10 = (meta.get("recipe") == "auto-v2" and
            meta.get("line_style") in ("straight", "arc") and
            (meta.get("position_engine") in ("cp-sat", "construct", "manual",
                                             "ring-construct",
                                             "column-construct", "sym-construct",
                                             "bowtie-construct")))
    chk("10. auto-v2 元数据完备", ok10,
        f"recipe={meta.get('recipe')} line_style={meta.get('line_style')} "
        f"engine={meta.get('position_engine')}")

    # 11. WS3 交叉双口径一致性：路由理论（最终路线交叉对数）vs 交付坐标几何复检
    router_pairs = meta.get("router_cross_pairs")
    if router_pairs is not None:
        geom_pairs = len(bad)      # 第 1 项的几何复检结果（边对数）
        chk("11. 交叉双口径一致（路由理论 vs 交付坐标几何复检）",
            abs(router_pairs - geom_pairs) < 0.5,
            f"router={router_pairs} geometric={geom_pairs}")

    # 12. F1：互环对（双向边对）两线最小间距 ≥ 4px（透镜双弧；禁止重合成双箭头线）
    from .routing import min_pair_dist
    pair_bad = []
    pair_note = []
    for i in range(len(P)):
        for j in range(i + 1, len(P)):
            (pi, ei), (pj, ej) = P[i], P[j]
            if (ei["a"], ei["b"]) != (ej["b"], ej["a"]):
                continue
            md = min_pair_dist(sample_polyline(pi), sample_polyline(pj))
            pair_note.append(f"{ei['a']}<->{ei['b']}:{md if md is None else round(md, 1)}px")
            if md is None or md < 4.0:
                pair_bad.append((f"{ei['a']}<->{ei['b']}",
                                 md if md is None else round(md, 1)))
    chk("12. 互环对两线最小间距 ≥ 4px（透镜双弧，禁止重合）",
        not pair_bad, (str(pair_bad[:5]) if pair_bad else "; ".join(pair_note[:6])))

    # 13. ref-scrubbed #15：path_d 渲染几何 = 核验几何（dense points）+ 弧线 G1 切线连续。
    # 历史 bug：route_svg_d 曾在 fillet 弧后无条件补画角点本体，渲染层出现
    # tb→q→ta_next 折返毛刺，而证书只核对 dense 采样点（平滑）——交付与
    # 核验脱节。本检查直接解析渲染用的 path_d（M/L/A），双向核对两套几何
    # 偏差 ≤1.5px，且每个 A 段与相邻 L 段切向夹角 ≤4°（取整容差）。
    pathd_bad = []
    pathd_n = 0
    for pts, e in P:
        d = e.get("route", {}).get("path_d")
        if not d:
            continue
        pathd_n += 1
        elems = _parse_path_d(d)
        if elems is None:
            pathd_bad.append((f"{e['a']}->{e['b']}", "path_d 解析失败"))
            continue
        dp = _path_d_all_points(elems)
        dense = [tuple(p) for p in pts]
        dev = _max_poly_dev(dp, dense)
        if dev > 1.5:
            pathd_bad.append((f"{e['a']}->{e['b']}", f"渲染/核验几何偏差 {dev:.1f}px"))
            continue
        g1 = _path_d_g1_max_deg(elems)
        if g1 > 4.0:
            pathd_bad.append((f"{e['a']}->{e['b']}", f"弧线切线不连续 {g1:.1f}°"))
    chk("13. path_d 渲染几何与核验几何一致 + 弧线 G1 切线连续",
        not pathd_bad,
        (str(pathd_bad[:5]) if pathd_bad
         else f"{pathd_n} 条 vg 路径渲染/核验一致（G1 ≤4°，几何偏差 ≤1.5px）"
         if pathd_n else "本图无 vg path_d 路径（平凡通过）"))

    report["summary"] = {
        "viewBox": [W, H], "aspect": round(W / H, 3) if H else 0,
        "nodes": len(nodes), "edges": len(edges),
        "rows": meta["rows"], "pitch": meta["pitch"],
        "scale_1280x800": round(s, 3),
        "recipe": meta.get("recipe"), "line_style": meta.get("line_style"),
        "position_engine": meta.get("position_engine"),
        "fail": report["fail"]}
    return report
