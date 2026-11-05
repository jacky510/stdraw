#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回路主导环形排布（ref-scrubbed）单元测试。

覆盖：
  1. 触发判定：cover（debt-spiral，声明环序+极性）/ ratio（growth-and-burden）
     / 纯环（4 节点环）；
  2. 负例不误伤：链 / 树 / 双三角+桥（覆盖 3 < n-2 且环边比 < 0.9）/ 13 节点环；
  3. place_ring 确定性（两次调用逐项相等）与 2px 网格；
  4. layout() 集成：debt-spiral 走 ring-construct、meta 口径齐备、
     环上等间距 CV / 模板拟合误差 ≤ 0.05；
  5. 半径超上界 → InfeasibleRing → 回退分层（engine 非 ring-construct）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import ringlayout
from stdraw.dsl import parse
from stdraw.layout_auto import layout, AutoConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic")
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def g(path):
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


# ── 1. 触发判定 ──
ds = g(os.path.join(CORPUS, "debt-spiral.cld"))
p = ringlayout.detect_ring(ds)
check("debt-spiral 触发（cover）", p is not None and p["trigger"] == "cover")
check("debt-spiral 主环覆盖全部 5 节点",
      p is not None and sorted(p["ring"]) == sorted(ds.node_ids()))
check("debt-spiral 主环=声明环 R2（极性沿环可读）",
      p is not None and p["declared_loop"] == "R2" and p["polarity"] == "R")
check("debt-spiral 弦交叉 0", p is not None and p["chord_crossings"] == 0)

gb = g(os.path.join(CORPUS, "classic-cld-growth-and-burden.cld"))
p2 = ringlayout.detect_ring(gb)
check("growth-and-burden 触发（ratio 分支）",
      p2 is not None and p2["trigger"] == "ratio")

pure = parse('graph "纯环"\nvar a "甲"\nvar b "乙"\nvar c "丙"\nvar d "丁"\n'
             'a -> + b\nb -> + c\nc -> + d\nd -> + a\n')
p3 = ringlayout.detect_ring(pure)
check("纯环触发（pure-cycle，复用既有 cycle 槽位构造）",
      p3 is not None and p3["trigger"] == "pure-cycle"
      and sorted(p3["ring"]) == ["a", "b", "c", "d"])

# ── 2. 负例不误伤 ──
check("链不触发", ringlayout.detect_ring(parse(
    'graph "链"\nvar a "A"\nvar b "B"\nvar c "C"\nvar d "D"\n'
    'a -> + b\nb -> + c\nc -> + d\n')) is None)
check("树不触发", ringlayout.detect_ring(parse(
    'graph "树"\nvar r "根"\nvar x "子"\nvar y "孙"\n'
    'r -> + x\nx -> + y\n')) is None)
check("双三角+桥不触发（覆盖 3 < 6-2 且环边比 0.86 < 0.9）",
      ringlayout.detect_ring(parse(
          'graph "双三角"\nvar a1 "一"\nvar a2 "二"\nvar a3 "三"\n'
          'var b1 "四"\nvar b2 "五"\nvar b3 "六"\n'
          'a1 -> + a2\na2 -> + a3\na3 -> + a1\n'
          'b1 -> + b2\nb2 -> + b3\nb3 -> + b1\na1 -> + b1\n')) is None)
big = parse("graph \"大环\"\n" + "".join(f'var v{i} "节点{i}"\n' for i in range(13))
            + "".join(f'v{i} -> + v{(i + 1) % 13}\n' for i in range(13)))
check("13 节点环不触发（n > 12 小图上限）",
      ringlayout.detect_ring(big) is None)

# ── 3. place_ring 确定性 + 2px 网格 ──
cfg = AutoConfig()
edges = [(e.a, e.b) for e in ds.edges]
adj, _ = ringlayout._adjacency(edges)
r1 = ringlayout.place_ring(p, {v: 96 for v in ds.node_ids()}, 44, cfg, adj, edges)
r2 = ringlayout.place_ring(p, {v: 96 for v in ds.node_ids()}, 44, cfg, adj, edges)
check("place_ring 确定性（两次调用逐项相等）", r1 == r2)
check("place_ring 全坐标 2px 网格",
      all(x % 2 == 0 for x in r1[0].values()) and
      all(y % 2 == 0 for y in r1[1].values()))

# ── 4. layout() 集成 ──
v4 = layout(ds, cfg)
m = v4["meta"]
check("layout() 走 ring-construct", m["position_engine"] == "ring-construct")
check("layout() meta.placement=ring-cycle", m.get("placement") == "ring-cycle")
rn = m["ring"]["nodes"]
pts = [(v4["nodes"][v]["x"], v4["nodes"][v]["y"]) for v in rn]
dists = [math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
md = sum(dists) / len(dists)
cv = (sum((d - md) ** 2 for d in dists) / len(dists)) ** 0.5 / md
check("环上等间距 CV ≤ 0.05", cv <= 0.05, f"cv={cv:.4f}")
from stdraw.regularity import cycle_polygon_deviation
dev = cycle_polygon_deviation({v: (v4["nodes"][v]["x"], v4["nodes"][v]["y"])
                               for v in rn}, rn)
check("正多边形模板拟合误差 ≤ 0.05", dev <= 0.05, f"D={dev:.4f}")

# ── 5. 半径超上界 → 回退分层 ──
wide = parse('graph "宽环"\n' + "".join(
    f'var v{i} "超长标签节点编号{i}号占位"\n' for i in range(11)) + "".join(
    f'v{i} -> + v{(i + 1) % 11}\n' for i in range(11)))
try:
    ringlayout._ring_radius(11, {i: 600 for i in range(11)})
    check("宽标签环应抛 InfeasibleRing", False)
except ringlayout.InfeasibleRing:
    check("宽标签环抛 InfeasibleRing（半径超上界）", True)

print()
if failures:
    print(f"{len(failures)} FAILURES:", *failures, sep="\n - ")
    sys.exit(1)
print("All ring layout tests passed.")
