# -*- coding: utf-8 -*-
"""几何自检（11 项）—— 只吃布局 JSON，通用。

检查跑在**交付坐标**上（取整/导出后的那份 JSON），这是纪律不是优化项。
输出 report JSON（可当 CI 门禁），fail>0 时 exit 1。
"""
import json
import sys
from typing import List


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
    chk("6a. 行距恒等 pitch（停车带除外）" + ("（manual: N/A）" if manual_mode else ""),
        True if manual_mode else pitch_ok, f"pitch={meta['pitch']}")
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
    snap = sum(1 for p in nodes.values() if p["x"] % 24 == 0) / len(nodes)
    simple = len(nodes) <= 10
    chk("9. 简单图排布规律性" + ("（manual: N/A）" if manual_mode else ""),
        True if manual_mode else ((not simple) or (pitch_ok and snap >= 0.6)),
        f"n={len(nodes)}，24px 列吸附 {snap:.2f}，行距恒等 {pitch_ok}"
        + ("；manual 布局不适用" if manual_mode else ""))

    # 10. 元数据完备（recipe / line_style / engine）
    ok10 = (meta.get("recipe") == "auto-v2" and
            meta.get("line_style") in ("straight", "arc") and
            (meta.get("position_engine") in ("cp-sat", "construct", "manual")))
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

    report["summary"] = {
        "viewBox": [W, H], "aspect": round(W / H, 3) if H else 0,
        "nodes": len(nodes), "edges": len(edges),
        "rows": meta["rows"], "pitch": meta["pitch"],
        "scale_1280x800": round(s, 3),
        "recipe": meta.get("recipe"), "line_style": meta.get("line_style"),
        "position_engine": meta.get("position_engine"),
        "fail": report["fail"]}
    return report
