# -*- coding: utf-8 -*-
"""几何自检（11 项）—— 只吃布局 JSON，通用。

检查跑在**交付坐标**上（取整/导出后的那份 JSON），这是纪律不是优化项。
输出 report JSON（可当 CI 门禁），fail>0 时 exit 1。
"""
import json
import sys
from typing import List


def geometry_report(layout: dict) -> dict:
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
