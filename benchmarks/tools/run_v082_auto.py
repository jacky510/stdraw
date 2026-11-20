# -*- coding: utf-8 -*-
"""Phase 0 re-measure driver (v0.8.2 current engine): full corpus auto re-run
with STDRAW_TIMING=1, fresh outputs under benchmarks/raw/v082/.

Scope (hard-limits compliant: n<=20 tier only, n30/n50 excluded entirely):
  classic/*.cld (20 files)      budget 300s/graph
  random n10 x20                budget 350s/graph
  random n20 x20                budget 100s/graph

Re-enterable: existing outputs are skipped. On timeout a DNF record is
written. Stage-timing stderr goes to benchmarks/raw/v082/timing/<base>.txt.
Layout bytes are unaffected by the timing layer (REPORT §9 zero-drift sweep).

Usage: python benchmarks/tools/run_v082_auto.py [family]
  family in {classic, random10, random20} (default: all three, in that order)
"""
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.abspath(os.path.join(HERE, "..", "raw", "v082"))
TIMING = os.path.join(RAW, "timing")
PY = sys.executable


def budget_for(family):
    return {"classic": 300, "random10": 350, "random20": 100}[family]


def files_for(family):
    if family == "classic":
        pats = [os.path.join(REPO, "benchmarks", "corpus", "classic", "*.cld")]
    elif family == "random10":
        pats = [os.path.join(REPO, "benchmarks", "corpus", "random", "random-n10-*.cld")]
    else:
        pats = [os.path.join(REPO, "benchmarks", "corpus", "random", "random-n20-*.cld")]
    out = []
    for p in pats:
        out.extend(sorted(glob.glob(p)))
    return out


def main():
    os.makedirs(TIMING, exist_ok=True)
    families = sys.argv[1:] or ["classic", "random10", "random20"]
    for fam in families:
        b = budget_for(fam)
        for cld in files_for(fam):
            base = os.path.splitext(os.path.basename(cld))[0]
            out = os.path.join(RAW, f"{base}.auto.json")
            if os.path.exists(out):
                print(f"skip {base} (exists)", flush=True)
                continue
            env = dict(os.environ)
            env["STDRAW_TIMING"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            t0 = time.time()
            try:
                p = subprocess.run(
                    [PY, os.path.join(HERE, "run_stdraw.py"), cld, RAW, "auto"],
                    capture_output=True, timeout=b, cwd=REPO, env=env)
                rc, so, se = p.returncode, p.stdout, p.stderr
            except subprocess.TimeoutExpired as e:
                rc, so, se = "TIMEOUT", (e.stdout or b""), (e.stderr or b"")
            dt = time.time() - t0
            ttxt = (se or b"").decode("utf-8", "replace")
            if ttxt.strip():
                with open(os.path.join(TIMING, f"{base}.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(ttxt)
            if rc == "TIMEOUT":
                with open(out, "w", encoding="utf-8") as f:
                    json.dump({"tool": "stdraw-auto", "graph": base,
                               "status": "dnf", "why": f"timeout at budget {b}s",
                               "budget_s": b}, f, ensure_ascii=False)
            print(f"{fam}/{base} rc={rc} {dt:.1f}s", flush=True)


if __name__ == "__main__":
    main()
