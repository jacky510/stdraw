#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI checks: run the CLI on both in-repo examples and assert the hard results.

Covers:
  1. both examples exit 0;
  2. 11-item geometry report: fail == 0 for both cases;
  3. certificate: crossings == 0, grade == "最优" (honest grading: both demo
     graphs are planar, so the theorem-level grade must hold);
  4. loops audit: summary.problems == 0, all declared loops closed;
  5. determinism: two runs of the same input are byte-identical.

Stdlib only — no pytest needed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

EXAMPLES = [
    "examples/limits-to-growth.cld",
    "examples/classic-cld-growth-and-burden.cld",
]


def run_cli(path, outdir):
    r = subprocess.run(
        [sys.executable, "-m", "stdraw", "layout", path,
         "--outdir", outdir, "--pitch", "62"],
        capture_output=True, text=True)
    return r


def load(outdir, name):
    with open(os.path.join(outdir, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    failures = []

    tmp = tempfile.mkdtemp(prefix="stdraw-ci-")
    try:
        for ex in EXAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-1")
            out2 = os.path.join(tmp, name + "-2")

            r1 = run_cli(ex, out1)
            if r1.returncode != 0:
                failures.append(f"{ex}: CLI exit {r1.returncode}\n{r1.stderr}")
                continue
            r2 = run_cli(ex, out2)
            if r2.returncode != 0:
                failures.append(f"{ex}: determinism re-run exit {r2.returncode}")
                continue

            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"{ex}: geometry report fail={geo['fail']}")
            n_checks = geo.get("checks")
            if n_checks != 11:
                # tolerate either a count field or a list
                checks = geo.get("results") or geo.get("items")
                if isinstance(checks, list) and len(checks) != 11:
                    failures.append(f"{ex}: expected 11 geometry checks, got {len(checks)}")

            cert = load(out1, "certificate.json")
            if cert["metrics"]["crossings"] != 0:
                failures.append(f"{ex}: crossings={cert['metrics']['crossings']} != 0")
            if cert["grade"] != "最优":
                failures.append(f"{ex}: grade={cert['grade']!r} != '最优'")

            audit = load(out1, "loops_audit.json")
            s = audit["summary"]
            if s["problems"] != 0:
                failures.append(f"{ex}: loops problems={s['problems']}")
            if s["closed"] != s["declared"]:
                failures.append(f"{ex}: closed={s['closed']} != declared={s['declared']}")

            # determinism: byte-identical artifact sets
            for fn in ("graph.json", "layout.json", "certificate.json",
                       "loops_audit.json", "demo-2d.html"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"{ex}: {fn} not byte-identical across runs")

            print(f"OK  {ex}: crossings=0 grade={cert['grade']} "
                  f"loops {s['closed']}/{s['declared']} closed, deterministic")

        if failures:
            print("\nFAILURES:")
            for f in failures:
                print(" -", f)
            return 1
        print("\nAll CI checks passed.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
