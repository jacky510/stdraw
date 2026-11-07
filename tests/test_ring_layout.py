#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop-dominant ring placement (ref-scrubbed) unit tests.

Coverage:
  1. trigger detection: cover (debt-spiral, declared loop order + polarity) /
     ratio (growth-and-burden) / pure ring (4-node ring);
  2. negatives not misfired: chain / tree / two triangles + bridge
     (cover 3 < n-2 and loop-edge ratio < 0.9) / 13-node ring;
  3. place_ring determinism (two calls equal item by item) and the 2px grid;
  4. layout() integration: debt-spiral goes through ring-construct, meta
     caliber complete, on-ring equidistant CV / template fit error <= 0.05;
  5. radius over the upper bound -> InfeasibleRing -> fallback to layered
     (engine is not ring-construct).
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


# -- 1. trigger detection --
ds = g(os.path.join(CORPUS, "debt-spiral.cld"))
p = ringlayout.detect_ring(ds)
check("debt-spiral triggers (cover)", p is not None and p["trigger"] == "cover")
check("debt-spiral main loop covers all 5 nodes",
      p is not None and sorted(p["ring"]) == sorted(ds.node_ids()))
check("debt-spiral main loop = declared loop R2 (polarity readable along the loop)",
      p is not None and p["declared_loop"] == "R2" and p["polarity"] == "R")
check("debt-spiral chord crossings 0", p is not None and p["chord_crossings"] == 0)

gb = g(os.path.join(CORPUS, "classic-cld-growth-and-burden.cld"))
p2 = ringlayout.detect_ring(gb)
check("growth-and-burden triggers (ratio branch)",
      p2 is not None and p2["trigger"] == "ratio")

pure = parse('graph "纯环"\nvar a "甲"\nvar b "乙"\nvar c "丙"\nvar d "丁"\n'
             'a -> + b\nb -> + c\nc -> + d\nd -> + a\n')
p3 = ringlayout.detect_ring(pure)
check("pure ring triggers (pure-cycle, reusing the existing cycle-slot construction)",
      p3 is not None and p3["trigger"] == "pure-cycle"
      and sorted(p3["ring"]) == ["a", "b", "c", "d"])

# -- 2. negatives not misfired --
check("chain does not trigger", ringlayout.detect_ring(parse(
    'graph "链"\nvar a "A"\nvar b "B"\nvar c "C"\nvar d "D"\n'
    'a -> + b\nb -> + c\nc -> + d\n')) is None)
check("tree does not trigger", ringlayout.detect_ring(parse(
    'graph "树"\nvar r "根"\nvar x "子"\nvar y "孙"\n'
    'r -> + x\nx -> + y\n')) is None)
check("two triangles + bridge do not trigger (cover 3 < 6-2 and loop-edge ratio 0.86 < 0.9)",
      ringlayout.detect_ring(parse(
          'graph "双三角"\nvar a1 "一"\nvar a2 "二"\nvar a3 "三"\n'
          'var b1 "四"\nvar b2 "五"\nvar b3 "六"\n'
          'a1 -> + a2\na2 -> + a3\na3 -> + a1\n'
          'b1 -> + b2\nb2 -> + b3\nb3 -> + b1\na1 -> + b1\n')) is None)
big = parse("graph \"大环\"\n" + "".join(f'var v{i} "节点{i}"\n' for i in range(13))
            + "".join(f'v{i} -> + v{(i + 1) % 13}\n' for i in range(13)))
check("13-node ring does not trigger (n > 12 small-graph limit)",
      ringlayout.detect_ring(big) is None)

# -- 3. place_ring determinism + 2px grid --
cfg = AutoConfig()
edges = [(e.a, e.b) for e in ds.edges]
adj, _ = ringlayout._adjacency(edges)
r1 = ringlayout.place_ring(p, {v: 96 for v in ds.node_ids()}, 44, cfg, adj, edges)
r2 = ringlayout.place_ring(p, {v: 96 for v in ds.node_ids()}, 44, cfg, adj, edges)
check("place_ring determinism (two calls equal item by item)", r1 == r2)
check("place_ring all coordinates on the 2px grid",
      all(x % 2 == 0 for x in r1[0].values()) and
      all(y % 2 == 0 for y in r1[1].values()))

# -- 4. layout() integration --
v4 = layout(ds, cfg)
m = v4["meta"]
check("layout() goes through ring-construct", m["position_engine"] == "ring-construct")
check("layout() meta.placement=ring-cycle", m.get("placement") == "ring-cycle")
rn = m["ring"]["nodes"]
pts = [(v4["nodes"][v]["x"], v4["nodes"][v]["y"]) for v in rn]
dists = [math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
md = sum(dists) / len(dists)
cv = (sum((d - md) ** 2 for d in dists) / len(dists)) ** 0.5 / md
check("on-ring equidistant CV <= 0.05", cv <= 0.05, f"cv={cv:.4f}")
from stdraw.regularity import cycle_polygon_deviation
dev = cycle_polygon_deviation({v: (v4["nodes"][v]["x"], v4["nodes"][v]["y"])
                               for v in rn}, rn)
check("regular polygon template fit error <= 0.05", dev <= 0.05, f"D={dev:.4f}")

# -- 5. radius over upper bound -> fallback to layered --
wide = parse('graph "宽环"\n' + "".join(
    f'var v{i} "超长标签节点编号{i}号占位"\n' for i in range(11)) + "".join(
    f'v{i} -> + v{(i + 1) % 11}\n' for i in range(11)))
try:
    ringlayout._ring_radius(11, {i: 600 for i in range(11)})
    check("wide-label ring should raise InfeasibleRing", False)
except ringlayout.InfeasibleRing:
    check("wide-label ring raises InfeasibleRing (radius over the upper bound)", True)

print()
if failures:
    print(f"{len(failures)} FAILURES:", *failures, sep="\n - ")
    sys.exit(1)
print("All ring layout tests passed.")
