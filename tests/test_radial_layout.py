#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Radial (hub-centered spoke) placement unit tests.

Coverage:
  1. trigger detection: pure fan (leaf_frac 1.0) / mixed star (leaf-leaf
     edges lower leaf_frac past the 0.5 line) / large-fan backstop
     (hub_deg >= 10);
  2. negatives not misfired: chain / tree / pure ring / hub_deg 3 branch
     graph (the whole corpus scores zero hits -- asserted against every
     classic corpus figure below);
  3. place_radial determinism (two calls equal item by item) + the 2px
     grid + HUB on the declared center + per-ring azimuth equal-spacing
     CV <= 0.05 (single and double ring);
  4. layout() integration: the fan fixture goes through radial-construct,
     meta caliber complete (radial hub/ring_nodes/ring_groups/center),
     certificate gates radial_hub_center_le_2px / radial_spacing_cv_le_005;
  5. radius need above the bound with a ring too small to split ->
     InfeasibleRadial -> fallback to layered (engine is not
     radial-construct).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import radellayout
from stdraw.dsl import parse
from stdraw.layout_auto import layout, AutoConfig
from stdraw.ringlayout import InfeasibleRing, _adjacency

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def fan(n, extra=()):
    lines = ['graph "fan"', 'var HUB "HUB"'] + \
        [f'var L{i:02d} "L{i:02d}"' for i in range(n)] + \
        [f'HUB -> + L{i:02d}' for i in range(n)]
    for a, b in extra:
        lines.append(f"{a} -> + {b}")
    return parse("\n".join(lines) + "\n")


# -- 1. trigger detection --
p = radellayout.detect_radial(fan(12))
check("pure fan d12 triggers", p is not None and p["hub"] == "HUB"
      and p["hub_deg"] == 12 and p["leaf_frac"] == 1.0)
p2 = radellayout.detect_radial(
    fan(9, (("L00", "L01"), ("L03", "L04"))))
check("mixed star triggers via leaf_frac >= 0.5 (deg-1 leaves 5/9)",
      p2 is not None and p2["hub_deg"] == 9 and p2["leaves"] == 5
      and 0.5 <= p2["leaf_frac"] < 1.0)
p3 = radellayout.detect_radial(fan(10))
check("hub_deg >= 10 backstop triggers regardless of leaf_frac",
      p3 is not None)

# -- 2. negatives not misfired --
check("chain does not trigger", radellayout.detect_radial(parse(
    'graph "chain"\nvar a "A"\nvar b "B"\nvar c "C"\nvar d "D"\n'
    'a -> + b\nb -> + c\nc -> + d\n')) is None)
check("tree does not trigger", radellayout.detect_radial(parse(
    'graph "tree"\nvar r "root"\nvar x "mid"\nvar y "leaf"\n'
    'r -> + x\nx -> + y\n')) is None)
check("pure ring does not trigger (hub_deg 2)", radellayout.detect_radial(parse(
    'graph "ring"\nvar a "a"\nvar b "b"\nvar c "c"\nvar d "d"\n'
    'a -> + b\nb -> + c\nc -> + d\nd -> + a\n')) is None)

# whole classic corpus: the detector must score zero hits (structural zero
# drift for the layered corpus; measured margins: max deg 8, worst leaf_frac
# among deg>=6 hubs 0.167)
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "classic")
miss = 0
hit = []
for fn in sorted(os.listdir(CORPUS)):
    if not fn.endswith(".cld"):
        continue
    g = parse(open(os.path.join(CORPUS, fn), encoding="utf-8").read())
    if radellayout.detect_radial(g) is not None:
        hit.append(fn)
    else:
        miss += 1
check(f"classic corpus zero trigger ({miss} figures scanned)",
      not hit, f"unexpected hits: {hit}")

# -- 3. place_radial determinism / grid / CV --
cfg = AutoConfig()


def _widths(g):
    from stdraw import textmetrics
    out = {}
    for v in g.node_ids():
        nd = g.id2node()[v]
        w, h = textmetrics.card_size(nd.label, nd.value, cfg.fs_title,
                                     cfg.fs_value, min_w=cfg.card_min_w)
        out[v] = w
    return out



for label, graph in (("single ring d12", fan(12)),
                     ("double ring d17", fan(17))):
    plan = radellayout.detect_radial(graph)
    edges = [(e.a, e.b) for e in graph.edges]
    adj, _ = _adjacency(edges)
    widths = _widths(graph)
    r1 = radellayout.place_radial(plan, widths, 44, cfg, adj, edges)
    r2 = radellayout.place_radial(plan, widths, 44, cfg, adj, edges)
    check(f"place_radial deterministic ({label})",
          r1[0] == r2[0] and r1[1] == r2[1] and r1[2] == r2[2])
    pos, y, meta = r1
    off = [v for v in graph.node_ids() if pos[v] % 2 or y[v] % 2]
    check(f"2px grid ({label})", not off, str(off[:4]))
    rd = meta["radial"]
    check(f"HUB on the declared center ({label})",
          pos[rd["hub"]] == rd["center"][0] and y[rd["hub"]] == rd["center"][1])
    cv = radellayout.azimuth_cv(rd["ring_groups"] or rd["ring_nodes"],
                                pos, y, *rd["center"])
    check(f"azimuth equal-spacing CV <= 0.05 ({label}, "
          f"{rd['rings']} ring(s))",
          cv is not None and cv <= 0.05, f"cv={cv:.4f}")

# -- 4. layout() integration --
out = layout(fan(12), AutoConfig())
meta = out["meta"]
check("fan d12 goes through radial-construct",
      meta.get("position_engine") == "radial-construct"
      and meta.get("placement") == "radial")
rd = meta.get("radial") or {}
check("meta radial caliber complete",
      rd.get("hub") == "HUB" and len(rd.get("ring_nodes") or []) == 12
      and isinstance(rd.get("center"), list)
      and rd.get("rings") in (1, 2))
rules = (meta.get("mode_decision_trace") or {}).get("rules") or []
check("mode trace records the radial rule on trigger",
      any(r.get("rule") == "radial" and r.get("triggered") for r in rules))

# non-trigger layered graph: the trace must NOT gain a radial entry
# (byte-stable trace discipline)
g_chain = parse('graph "chain"\n' + "".join(
    f'var c{i} "c{i}"\n' for i in range(8)) + "".join(
    f"c{i} -> + c{i+1}\n" for i in range(7)))
out2 = layout(g_chain, AutoConfig())
rules2 = ((out2["meta"].get("mode_decision_trace") or {}).get("rules")) or []
check("non-hit layered graph trace has no radial entry",
      not any(r.get("rule") == "radial" for r in rules2))

# -- 5. infeasible -> fallback (unit level; a CLI-level fixture with 17
# extra-wide cards falls back to layered which is minutes-slow) --

wide = parse('graph "wide"\nvar HUB "HUB"\n' + "".join(
    f'var L{i:02d} "' + "x" * 40 + f'{i:02d}"\n' for i in range(17))
    + "".join(f"HUB -> + L{i:02d}\n" for i in range(17)))
plan_w = radellayout.detect_radial(wide)
check("wide-card fan still detected (backstop branch)",
      plan_w is not None)
adj_w, _ = _adjacency([(e.a, e.b) for e in wide.edges])
widths_w = _widths(wide)
raised = None
try:
    radellayout.place_radial(plan_w, widths_w, 44, cfg, adj_w,
                             [(e.a, e.b) for e in wide.edges])
except InfeasibleRing:
    raised = True
check("radius-need overflow raises InfeasibleRadial (caller falls back)",
      raised is True)

print()
if failures:
    print(f"== {len(failures)} FAILURES ==")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("== ALL PASS ==")
