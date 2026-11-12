#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual-layout hard-gate fallback regression (layout_auto manual injection).

Covers the classic CLD "success-to-the-successful" fixture with a hand-dragged
node placement plus three user-styled/anchored edges, two of which breach hard
gates when replayed verbatim:

  - a_alloc->a_perf (arc + exported ctrl): quad dips into its OWN target box
    (own-box press) -- gate 2;
  - a_perf->a_alloc: both directions share the same designated anchor pair, so
    the mutual pair reads as one merged line (separation 0px) -- gate 12.

Expected engine behavior (manual-mode hard-gate fallback):
  1. the breaching pair falls back to the engine's own routing (mutual-pair
     lens offset / press avoidance / clearance machinery) and the delivered
     geometry passes ALL geometry checks (fail=0, crossings 0);
  2. the gate-clean user edge (a_perf->b_alloc straight, anchors w/s) is
     honored untouched -- no fallback recorded for it;
  3. a manual layout WITHOUT the breaching styles never records a fallback
     (benign layouts stay byte-for-byte identical);
  4. determinism: two runs of the breaching layout are byte-identical.

Stdlib only.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLD = os.path.join(ROOT, "benchmarks", "corpus", "classic",
                   "success-to-the-successful.cld")

failures = []


def ok(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          ("  " + str(detail)[:180] if detail else ""))
    if not cond:
        failures.append(name)


def run(args):
    return subprocess.run([sys.executable, "-m", "stdraw"] + args,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ROOT)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def manual_layout(edges):
    """Hand-dragged node placement (the sole authority) + user edge styles."""
    return {
        "tool": "stdraw", "kind": "manual-layout",
        "graph": "富者愈富 · 赢家通吃",
        "viewBox": [0, 0, 512, 480],
        "nodes": {
            "pool": {"x": 253, "y": 48},
            "a_alloc": {"x": 426, "y": 174},
            "a_perf": {"x": 262, "y": 360},
            "b_alloc": {"x": 99, "y": 174},
            "b_perf": {"x": 264, "y": 173},
            "gap": {"x": 263, "y": 268},
        },
        "edges": edges,
    }


EDGE_PAIR = [
    {"a": "a_alloc", "b": "a_perf", "style": "arc",
     "ctrl": [240.4, 335.9], "anchors": {"src": "s", "dst": "e-g2"}},
    {"a": "a_perf", "b": "a_alloc", "style": "arc",
     "ctrl": [488.6, 221.4], "anchors": {"src": "e-g2", "dst": "s"}},
]
EDGE_CLEAN = {"a": "a_perf", "b": "b_alloc", "style": "straight",
              "anchors": {"src": "w", "dst": "s"}}


def main():
    tmp = tempfile.mkdtemp(prefix="stdraw-manual-fallback-")
    try:
        # -- 1. breaching user styles: fallback -> all geometry checks pass --
        src = os.path.join(tmp, "breach.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump(manual_layout(EDGE_PAIR + [EDGE_CLEAN]), f,
                      ensure_ascii=False)
        out = os.path.join(tmp, "breach")
        r = run(["layout", CLD, "--recipe", "auto", "--from-layout", src,
                 "--outdir", out, "--skip-3d"])
        ok("breaching layout: pipeline ran", r.returncode in (0, 1),
           r.stderr[-120:] if r.returncode not in (0, 1) else "")
        rep = load(os.path.join(out, "geometry_report.json"))
        ok("breaching layout: all geometry checks pass (fail=0)",
           rep["fail"] == 0, str(rep["fail"]))
        lay = load(os.path.join(out, "layout.json"))
        fm = lay["meta"].get("from_layout", {})
        fb = {e["edge"]: e["reason"] for e in fm.get("manual_fallback", [])}
        ok("fallback recorded exactly for the breaching pair",
           set(fb) == {"a_alloc->a_perf", "a_perf->a_alloc"}, str(fb))
        ok("forward arc reason = own-box press",
           "own" in fb.get("a_alloc->a_perf", ""), fb.get("a_alloc->a_perf"))
        ok("reverse arc reason = mutual-pair separation",
           "mutual-pair" in fb.get("a_perf->a_alloc", ""),
           fb.get("a_perf->a_alloc"))
        ok("gate-clean user edge kept (no fallback entry)",
           "a_perf->b_alloc" not in fb, str(sorted(fb)))
        ok("user anchors kept for the clean edge",
           fm.get("user_anchors", {}).get("a_perf->b_alloc") ==
           {"src": "w", "dst": "s"},
           str(fm.get("user_anchors")))
        cert = load(os.path.join(out, "certificate.json"))
        m = cert["metrics"]
        ok("delivered crossings 0", m["crossings"] == 0, str(m["crossings"]))
        ok("delivered box press 0", m["box_press_1px"] == 0,
           str(m["box_press_1px"]))
        ok("delivered edge-box clearance >= 16px",
           (m["edge_box_min_clear"] or 0) >= 16.0, str(m["edge_box_min_clear"]))
        ok("mutual pairs separated >= 4px",
           m["mutual_pair_min_sep"] is not None
           and m["mutual_pair_min_sep"] >= 4.0,
           str(m["mutual_pair_min_sep"]))
        clean = [e for e in lay["edges"]
                 if (e["a"], e["b"]) == ("a_perf", "b_alloc")]
        ok("clean edge delivered as user-styled straight line",
           len(clean) == 1 and clean[0]["route"]["kind"] == "line",
           str(clean[0]["route"]["kind"]) if clean else "missing")
        ok("clean edge endpoints on designated w/s anchors",
           len(clean) == 1 and clean[0]["anchors"]["a"] == [241.0, 384.0]
           and clean[0]["anchors"]["b"] == [122.0, 217.0],
           str(clean[0]["anchors"]) if clean else "missing")

        # -- 2. benign manual layout: no fallback, byte-stable honors --
        src2 = os.path.join(tmp, "benign.json")
        with open(src2, "w", encoding="utf-8") as f:
            json.dump(manual_layout([EDGE_CLEAN]), f, ensure_ascii=False)
        out2 = os.path.join(tmp, "benign")
        r2 = run(["layout", CLD, "--recipe", "auto", "--from-layout", src2,
                  "--outdir", out2, "--skip-3d"])
        ok("benign layout: pipeline ran", r2.returncode in (0, 1), "")
        lay2 = load(os.path.join(out2, "layout.json"))
        fm2 = lay2["meta"].get("from_layout", {})
        ok("benign layout: no fallback recorded",
           "manual_fallback" not in fm2, str(fm2.get("manual_fallback")))
        rep2 = load(os.path.join(out2, "geometry_report.json"))
        ok("benign layout: all geometry checks pass (fail=0)",
           rep2["fail"] == 0, str(rep2["fail"]))
        # benign delivery must equal the breaching delivery's key geometry
        # (the engine routing that the fallback lands on is the same path)
        ka = {k: lay[k] for k in ("viewBox", "nodes", "edges")}
        kb = {k: lay2[k] for k in ("viewBox", "nodes", "edges")}
        ok("fallback delivery == benign delivery (same engine path)",
           ka == kb, "key geometry differs")

        # -- 3. determinism: two runs byte-identical --
        out3 = os.path.join(tmp, "breach2")
        run(["layout", CLD, "--recipe", "auto", "--from-layout", src,
             "--outdir", out3, "--skip-3d"])
        same = all(
            open(os.path.join(out, fn), "rb").read() ==
            open(os.path.join(out3, fn), "rb").read()
            for fn in ("layout.json", "geometry_report.json",
                       "certificate.json"))
        ok("determinism: two runs byte-identical", same, "")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"FAIL ({len(failures)}): " + "; ".join(failures))
        return 1
    print("PASS: manual hard-gate fallback regression")
    return 0


if __name__ == "__main__":
    sys.exit(main())
