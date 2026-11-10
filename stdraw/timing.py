# -*- coding: utf-8 -*-
"""Observational stage timing for the auto layout pipeline (stage-timing layer).

Enable with STDRAW_TIMING=1 (checked per layout() call at start()); anything
else is a hard no-op: no bookkeeping, no output, and layout.json bytes are
untouched. Marks are sequential, ci_checks.mark() style — each mark records
the seconds elapsed since the previous mark, so an interval is attributed to
the stage that follows its preceding boundary. The report goes to stderr
only; the timing layer never participates in any layout decision
(determinism preserved, see the zero-drift sweep in benchmarks/REPORT.md §9).
"""
import sys
import time

_active = None


class _Run:
    def __init__(self):
        self.t0 = time.perf_counter()
        self._last = self.t0
        self.stages = []

    def mark(self, label):
        now = time.perf_counter()
        self.stages.append((label, now - self._last))
        self._last = now

    def report(self, stream=None):
        stream = stream if stream is not None else sys.stderr
        total = self._last - self.t0
        width = max((len(s) for s, _ in self.stages), default=10)
        print(f"[stdraw] stage timing (STDRAW_TIMING=1), "
              f"total {total * 1000:.0f} ms:", file=stream)
        for label, dt in self.stages:
            pct = (dt / total * 100.0) if total > 0 else 0.0
            print(f"  {label:<{width}}  {dt * 1000:9.1f} ms  {pct:5.1f}%",
                  file=stream)


def start():
    """Open a timing run for the current layout() call (no-op unless enabled)."""
    global _active
    import os
    if os.environ.get("STDRAW_TIMING", "") == "1":
        _active = _Run()


def mark(label):
    if _active is not None:
        _active.mark(label)


def finish():
    """Print the stage table to stderr and close the run."""
    global _active
    if _active is not None:
        _active.report()
        _active = None
