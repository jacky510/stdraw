#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Complexity budget hard gate (2026-11-18 closure batch, DeepSeek external
review follow-up: "size x time budget into a hard gate so breadth expansion
cannot re-inflate complexity").

Assertions (honest SKIP without ortools, same caliber as test_scalability):
  1. random-n10-i00 auto-v2 wall clock <= 350s   (REPORT S3 budget protocol:
     "random n<=10 = 350s"; quiet dev box measured ~45-60s/graph post-WS5);
  2. random-n20-i00 auto-v2 wall clock <= 900s   (the test_scalability cap,
     jacky scope ruling 2026-11-14: n<=20, honest per-run downgrade cap);
  3. scaling class: t(n20) <= 4 * t(n10) + 60s   (a quadratic envelope with
     headroom). Grounding: quiet-box measurements give t20/t10 ~= 2.0-2.6
     (n10 45-60s, n20 97-144s, REPORT.md section 222 note + S5 records), so
     the gate carries >50% headroom while still catching the historical
     regression class: the dense-snap first cut inflated n20 ~7.6x (126s ->
     956.2s) while barely touching n10 -- that run scores ~19:1 and goes red
     here.

The gate measures wall clock, which varies with machine load; both budgets
above already encode that slack (350s vs 60s measured, 900s vs 144s worst
measured). The scaling-class gate is load-robust because contention inflates
both sides of the ratio.
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
RATIO_CAP = 4.0
RATIO_SLACK_S = 60.0


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
    # scaling-class gate: t20 <= 4 * t10 + 60s (see docstring grounding)
    ratio = times[20] / max(times[10], 1e-9)
    limit = RATIO_CAP * times[10] + RATIO_SLACK_S
    print(f"  scaling: t20/t10 = {ratio:.2f} "
          f"(cap {RATIO_CAP}x + {RATIO_SLACK_S:.0f}s -> {limit:.1f}s)")
    assert times[20] <= limit, (
        f"complexity budget: scaling class blown -- t20 {times[20]:.1f}s "
        f"exceeds {RATIO_CAP}x * t10 + {RATIO_SLACK_S:.0f}s "
        f"(ratio {ratio:.2f}); breadth expansion likely re-inflated complexity")
    assert meta_seen["position_engine"] == "cp-sat", meta_seen
    print("OK  test_complexity_budget: absolute budgets + quadratic "
          "scaling envelope hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# pytest entry (CI full-suite collection; script behavior unchanged).
def test_complexity_budget():
    assert main() == 0
