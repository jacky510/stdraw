#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Complexity budget hard gate (2026-11-18 closure batch, DeepSeek external
review follow-up: "size x time budget into a hard gate so breadth expansion
cannot re-inflate complexity").

Assertions (honest SKIP without ortools, same caliber as test_scalability):
  1. random-n10-i00 auto-v2 wall clock <= 350s   (REPORT S3 budget protocol:
     "random n<=10 = 350s");
  2. random-n20-i00 auto-v2 wall clock <= 900s   (the test_scalability cap,
     jacky scope ruling 2026-11-14: n<=20, honest per-run downgrade cap).

Absolute budgets only. A quadratic scaling envelope (t20 <= 4*t10 + 60s)
shipped in this batch was removed the same day (jacky 2026-11-18, option A):
it was grounded on pre-planarization timings (n20 97-144s, ratio 2.0-2.6),
but planarization adds a ~700s structural L2-fallback floor to n20 runs that
n10 does not pay (quiet-box calibration 2026-11-18: n10 19.5-36.4s, n20
545-838s, family ratio 20-40x), so the ratio measures graph-difficulty
difference, not complexity scaling, and cannot pass on any quiet machine.
The absolute n20 cap remains the regression-class guard: the historical
dense-snap first cut ran 956.2s and would trip it. Re-introduce an envelope
gate only after the planarization performance work (DeepSeek review deep
closure item) lands.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.dsl import parse                       # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASES = {
    10: os.path.join(REPO, "benchmarks", "corpus", "random", "random-n10-i00.cld"),
    20: os.path.join(REPO, "benchmarks", "corpus", "random", "random-n20-i00.cld"),
}
ABS_BUDGET_S = {10: 350.0, 20: 900.0}


def _run_auto(path):
    from stdraw.recipes import run as recipes_run
    from stdraw.layout_auto import AutoConfig

    g = parse(open(path, encoding="utf-8").read())
    t0 = time.perf_counter()
    v4 = recipes_run("auto-v2", g, AutoConfig(), "straight")
    dt = time.perf_counter() - t0
    return v4, dt


def main():
    try:
        import ortools  # noqa: F401
    except Exception:
        print("SKIP  test_complexity_budget: ortools unavailable "
              "(budget path needs CP-SAT)")
        return 0
    times = {}
    meta_seen = None
    for n, path in CASES.items():
        v4, dt = _run_auto(path)
        times[n] = dt
        meta = v4["meta"]
        meta_seen = meta
        status = meta.get("solver_status")
        budget = ABS_BUDGET_S[n]
        print(f"  n={n}: {dt:.1f}s (budget {budget:.0f}s) "
              f"engine={meta['position_engine']} status={status}")
        assert dt <= budget, (
            f"complexity budget: n={n} wall clock {dt:.1f}s > {budget:.0f}s cap")
    assert meta_seen["position_engine"] == "cp-sat", meta_seen
    print(f"  scaling: t20/t10 = {times[20] / max(times[10], 1e-9):.2f} "
          "(recorded, no envelope gate; absolute budgets are the gate)")
    print("OK  test_complexity_budget: absolute budgets hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# pytest entry (CI full-suite collection; script behavior unchanged).
def test_complexity_budget():
    assert main() == 0
