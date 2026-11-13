# -*- coding: utf-8 -*-
"""Two-stage candidate search (admissible-bound prune) regression tests.

The prune's contract: run() must select exactly the candidate full
enumeration selects, on every input -- proven here by brute-force
enumeration over the same stage-1 survivors (try_candidate == the old
full pipeline) and byte-comparison of the delivered layouts.
"""
import os
import sys

import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import stdraw  # noqa: E402

assert os.path.realpath(stdraw.__file__).startswith(os.path.realpath(ROOT)), stdraw.__file__

from stdraw.planar import PlanarLayout, LayoutConfig  # noqa: E402
from stdraw.dsl import parse  # noqa: E402


def _cld(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return parse(f.read())


def _full_enumeration_layout(g):
    """The pre-two-stage run(): finalize every viable candidate, stable-sort
    by score, take the first (discovery-order tie-break)."""
    eng = PlanarLayout(g, LayoutConfig())
    rot, dummy = eng.augment(eng.build_rotation())
    cands = []
    seen_st = set()
    for a, b in eng.edges:
        for s, t in ((a, b), (b, a)):
            try:
                r = eng.try_candidate(rot, dummy, s, t)
            except AssertionError:
                continue
            if not r:
                continue
            key = tuple(sorted(r[4].items()))
            if key in seen_st:
                continue
            seen_st.add(key)
            cands.append(r)
    assert cands
    cands.sort(key=lambda x: x[0])
    sc, s, t, rot, g_, Y_aug, Xe, RXe, dummy, Y, data = cands[0]
    v4 = eng.stage3(g_, Y, RXe)
    v4["meta"]["st"] = [s, t]
    v4["meta"]["down"] = data["down"]
    v4["meta"]["n"] = len(eng.nodes)
    v4["meta"]["m"] = len(eng.edges)
    v4["meta"]["method"] = ("visibility-representation (Rosenstiehl-Tarjan) "
                            "0-crossing guaranteed; wires strictly vertical; "
                            "compact packing (occlusion allowed under cards)")
    from stdraw.delivery import stamp_coordinates_only
    return stamp_coordinates_only(v4)


def _run_with_count(g):
    """run() plus the number of stage-2 (expensive) finalizations."""
    eng = PlanarLayout(g, LayoutConfig())
    calls = {"n": 0}
    orig = PlanarLayout._stage2_candidate

    def counted(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    PlanarLayout._stage2_candidate = counted
    try:
        v4 = eng.run()
    finally:
        PlanarLayout._stage2_candidate = orig
    return v4, calls["n"]


class TestTwoStagePrune(unittest.TestCase):
    def test_output_identical_to_full_enumeration(self):
        for rel in ("examples/limits-to-growth.cld",
                    "benchmarks/corpus/classic/wage-price-spiral.cld",
                    "benchmarks/corpus/classic/arms-race.cld"):
            g = _cld(rel)
            v4_prune, _ = _run_with_count(g)
            v4_full = _full_enumeration_layout(g)
            self.assertEqual(
                v4_prune, v4_full,
                f"pruned selection differs from full enumeration: {rel}")

    def test_prune_actually_skips_candidates(self):
        # On a grid graph most candidates are provably worse than the
        # incumbent long before their turn; the prune must skip them while
        # keeping the output identical (discriminative power, not a no-op).
        n = 6
        nodes = [stdraw.model.Node(f"N{r}_{c}", f"N{r}_{c}")
                 for r in range(n) for c in range(n)]
        edges = []
        for r in range(n):
            for c in range(n):
                if c + 1 < n:
                    edges.append(stdraw.model.Edge(f"N{r}_{c}", f"N{r}_{c+1}", "+"))
                if r + 1 < n:
                    edges.append(stdraw.model.Edge(f"N{r}_{c}", f"N{r+1}_{c}", "+"))
        g = stdraw.model.Graph(nodes=nodes, edges=edges, name="grid6")
        v4, calls = _run_with_count(g)
        eng = PlanarLayout(g, LayoutConfig())
        rot, dummy = eng.augment(eng.build_rotation())
        survivors = 0
        seen = set()
        for a, b in eng.edges:
            for s, t in ((a, b), (b, a)):
                st1 = eng._stage1_candidate(rot, s, t)
                if not st1:
                    continue
                key = tuple(sorted(st1[0].items()))
                if key in seen:
                    continue
                seen.add(key)
                survivors += 1
        self.assertLess(calls, survivors,
                        "prune finalized every candidate -- no discriminative power")
        v4_full = _full_enumeration_layout(g)
        self.assertEqual(v4, v4_full, "pruned grid layout differs from full enumeration")

    def test_deterministic_two_runs(self):
        g = _cld("examples/limits-to-growth.cld")
        a, _ = _run_with_count(g)
        b, _ = _run_with_count(g)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
