# -*- coding: utf-8 -*-
"""F3 rework regression (ref-scrubbed): auto arc bulges must stay inside the viewBox.

Background: since v0.2 the viewBox was computed from node boxes only, and the
bullwhip inventory->forecast arc bulged 7.5px left past the viewBox left edge
-> check7 fail (CLI exit 1). Fix: the delivery layer now folds all edge
geometry (sampled points + arc ctrl) into the translation offset and W/H math.

Coverage:
  A. bullwhip (the original regression case): CLI exit 0, geometry self-check
     fail=0, all route.points/ctrl strictly inside the viewBox open interval;
  B. two CI cases (limits-to-growth / classic-cld-growth-and-burden): same
     assertions (layer-B ci_checks already runs them; here with a finer
     point-by-point containment caliber);
  C. determinism: two layouts of the same input are byte-for-byte identical.

Run: python tests/test_auto_viewbox.py (stdlib-only, exit 0 = all pass).
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAILURES = []


def ok(name, cond, detail=""):
    tag = "OK " if cond else "FAIL"
    print(f"{tag} {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def layout_and_check(root, cld, outdir):
    r = subprocess.run([sys.executable, "-m", "stdraw", "layout", cld,
                        "--recipe", "auto", "--outdir", outdir],
                       capture_output=True, text=True, cwd=root)
    lj = json.load(open(os.path.join(outdir, "layout.json"), encoding="utf-8"))
    geo = json.load(open(os.path.join(outdir, "geometry_report.json"),
                         encoding="utf-8"))
    return r, lj, geo


def contained(lj):
    """All delivered edge geometry (sampled points + arc ctrl) lies strictly inside the viewBox open interval."""
    W, H = lj["viewBox"][2], lj["viewBox"][3]
    bad = []
    for e in lj["edges"]:
        pts = [tuple(p) for p in e["route"]["points"]]
        c = e["route"].get("ctrl")
        if c:
            pts.append(tuple(c))
        for px, py in pts:
            if not (0 < px < W and 0 < py < H):
                bad.append((e["a"], e["b"], px, py))
    return bad


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    cases = [
        "benchmarks/corpus/classic/bullwhip.cld",
        "examples/limits-to-growth.cld",
        "examples/classic-cld-growth-and-burden.cld",
    ]
    tmp = tempfile.mkdtemp(prefix="stdraw-f3-")
    for cld in cases:
        name = os.path.splitext(os.path.basename(cld))[0]
        o1 = os.path.join(tmp, name + "-1")
        o2 = os.path.join(tmp, name + "-2")
        r1, lj, geo = layout_and_check(root, cld, o1)
        ok(f"{name}: CLI exit 0", r1.returncode == 0,
           f"exit={r1.returncode}" + ("" if r1.returncode == 0
                                      else "\n" + r1.stdout[-500:]))
        ok(f"{name}: geometry fail=0", geo.get("fail", -1) == 0,
           f"fail={geo.get('fail')}")
        bad = contained(lj)
        ok(f"{name}: all edge geometry inside the viewBox", not bad,
           f"viewBox={lj['viewBox']} out_of_bounds={bad[:3]}")
        layout_and_check(root, cld, o2)
        a = open(os.path.join(o1, "layout.json"), "rb").read()
        b = open(os.path.join(o2, "layout.json"), "rb").read()
        ok(f"{name}: determinism (two layout.json runs byte-identical)", a == b)
    print()
    if FAILURES:
        print(f"FAILURES ({len(FAILURES)}):", FAILURES)
        return 1
    print("All auto-viewbox regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# pytest entry (CI full-suite collection; script behavior unchanged).
def test_auto_viewbox():
    cwd = os.getcwd()
    try:
        assert main() == 0
    finally:
        os.chdir(cwd)   # main() chdirs to the repo root; keep pytest cwd stable
