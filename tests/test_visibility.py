# -*- coding: utf-8 -*-
"""WS3 布线数学层单元测试：手工障碍场景逐例验证。

覆盖：
  A. 可见性图最短路——最优性 vs 暴力枚举真值（小规模角点全排列）、
     净距保持、确定性、不可达检测、G1 切线连续；
  B. Router 集成——直线被挡自动生成 vg 候选、硬门保持、
     交叉双口径（路由理论 vs 交付坐标几何复检）一致。

运行：python tests/test_visibility.py（stdlib-only，exit 0 = 全过）。
"""
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw import visibility as vis
from stdraw.routing import Router, CLEARANCE, VG_PAD

C = 17.5          # 测试膨胀净距（= CLEARANCE + VG_PAD）
FAILURES = []


def ok(name, cond, detail=""):
    tag = "OK " if cond else "FAIL"
    print(f"{tag} {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


# ── A. 可见性图最短路 ────────────────────────────────────
def brute_optimal(src, dst, rects, c):
    nodes = vis._graph_nodes(src, dst, rects, c)
    best = float("inf")
    for k in range(0, len(nodes[2:]) + 1):
        for perm in itertools.permutations(nodes[2:], k):
            pts = [tuple(src)] + list(perm) + [tuple(dst)]
            if all(vis._visible(pts[i], pts[i + 1], rects, c)
                   for i in range(len(pts) - 1)):
                best = min(best, sum(math.dist(pts[i], pts[i + 1])
                                     for i in range(len(pts) - 1)))
    return best


def case(name, src, dst, rects, reachable=True):
    r = vis.plan_route(src, dst, rects, C)
    if not reachable:
        ok(f"{name}: 不可达如实返回 None", r is None)
        return
    ok(f"{name}: 可达", r is not None)
    if r is None:
        return
    worst = (min(min(vis.pt_rect_distance(px, py, rect) for rect in rects)
                 for (px, py) in r["dense"]) if rects else float("inf"))
    ok(f"{name}: 净距保持 ≥ {C}", worst >= C - 1e-6, f"min={worst:.2f}")
    opt = brute_optimal(src, dst, rects, C)
    L = sum(math.dist(r["corner_pts"][i], r["corner_pts"][i + 1])
            for i in range(len(r["corner_pts"]) - 1))
    ok(f"{name}: 最优性（= 暴力枚举真值）", abs(L - opt) < 1e-6,
       f"L={L:.2f} brute={opt:.2f}")
    r2 = vis.plan_route(src, dst, rects, C)
    ok(f"{name}: 确定性（两次运行逐字节一致）",
       r["dense"] == r2["dense"] and r["path_d"] == r2["path_d"])
    for f in r["fillets"]:
        i = f["i"]
        a, q, b = (r["corner_pts"][i - 1], r["corner_pts"][i],
                   r["corner_pts"][i + 1])
        samples = vis._arc_samples(f["center"], f["r"], f["ta"], f["tb"], 16)
        ux, uy = (q[0] - a[0], q[1] - a[1])
        wx, wy = (b[0] - q[0], b[1] - q[1])
        theta = math.acos(max(-1.0, min(1.0, (ux * wx + uy * wy) /
                        (math.hypot(ux, uy) * math.hypot(wx, wy)))))
        # 弦向 vs 切向的固有偏差 = θ/(2·采样数)，容差再加 0.3°
        tol = max(1.0, math.degrees(theta / (2 * 16)) + 0.3)
        for seg, s0, s1 in ((a, samples[0], samples[1]),
                            (b, samples[-1], samples[-2])):
            ux, uy = seg[0] - q[0], seg[1] - q[1]
            n1 = math.hypot(ux, uy)
            d = (s1[0] - s0[0], s1[1] - s0[1])
            n2 = math.hypot(*d)
            cosang = abs((ux * d[0] + uy * d[1]) / (n1 * n2))
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            ok(f"{name}: 弧 G1 切线连续（r={f['r']}）", ang < tol,
               f"{ang:.2f}deg < tol {tol:.2f}")


case("无障碍直线", (0, 300), (600, 300), [])
case("单障碍居中（对称 tie-break 确定性）", (0, 300), (600, 300),
     [(300, 300, 60, 40)])
case("单障碍偏上（走下方更短）", (0, 320), (600, 320), [(300, 260, 80, 45)])
case("双障碍 Z 字走廊", (50, 300), (600, 300),
     [(250, 270, 70, 60), (420, 330, 70, 60)])
case("密封障碍不可达", (0, 300), (300, 300), [(300, 300, 60, 60)],
     reachable=False)

# ── B. Router 集成 ───────────────────────────────────────
# a 垂直上方 b，中段被 c 挡死 → 直线被挡，须出 vg 候选且硬门保持
nodes_px = {"a": (300, 100, 120, 44), "b": (300, 340, 120, 44),
            "c": (300, 220, 140, 44)}
rt = Router(nodes_px, [("a", "b")], CLEARANCE, 80)
out = rt.route_all()
info = out[0]
kinds = {info["kind"]}
ok("Router: 直线被挡时生成绕障路线", info["kind"] in ("vg", "poly", "arc"),
   f"kind={info['kind']}")
ok("Router: 框压线 = 0", info["press"] == 0)
clr = info.get("min_clear")
ok("Router: 净距 ≥ 16px", clr is None or clr >= CLEARANCE, f"min_clear={clr}")
if info["kind"] == "vg":
    ok("Router: vg 路线带角点与弧参数",
       "vg_corners" in info and "vg_fillets" in info)

# 双口径：final_crossing_pairs == 交付坐标几何复检（同一布局上两算）
edges2 = [("a", "b"), ("b", "c")]
nodes2 = {"a": (200, 100, 120, 44), "b": (300, 220, 120, 44),
          "c": (400, 340, 120, 44)}
rt2 = Router(nodes2, edges2, CLEARANCE, 80)
out2 = rt2.route_all()
router_pairs = rt2.final_crossing_pairs(out2)


def _seg_cross(p1, p2, p3, p4):
    from stdraw.routing import seg_cross
    return seg_cross(p1, p2, p3, p4)


geom_pairs = 0
items = sorted(out2.items())
for x in range(len(items)):
    for y in range(x + 1, len(items)):
        ia, pa = items[x][0], items[x][1]["points"]
        ib, pb = items[y][0], items[y][1]["points"]
        if edges2[ia][0] in edges2[ib] or edges2[ia][1] in edges2[ib]:
            continue
        hit = any(_seg_cross(s1[0], s1[1], s2[0], s2[1])
                  for s1 in zip(pa[:-1], pa[1:])
                  for s2 in zip(pb[:-1], pb[1:]))
        geom_pairs += 1 if hit else 0
ok("Router: 交叉双口径一致（理论 vs 几何）",
   abs(router_pairs - geom_pairs) < 0.5,
   f"router={router_pairs} geometric={geom_pairs}")

print()
if FAILURES:
    print(f"FAILED ({len(FAILURES)}): {FAILURES}")
    sys.exit(1)
print("test_visibility: ALL PASS")
