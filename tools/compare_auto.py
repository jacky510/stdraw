#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare-auto: dual-certificate comparison (manual vs automatic layout).

Development gauge, moved out of the CLI into tools/ (2026-11-26 T16
subtraction card): not shipped in the wheel; the repo keeps it runnable.

    python tools/compare_auto.py <input.cld> --from-layout MANUAL_JSON \
        --outdir OUTDIR [--name NAME]

Runs the layout pipeline twice with `python -m stdraw layout` (manual
coordinates via --from-layout, then the automatic layout of the same
graph into OUTDIR-compare-auto/) and writes compare-auto.json into
OUTDIR: metric table (manual / auto / delta) + dual grades + gates.
The gap is the aesthetic distance between engine and human (the basis
for future objective-function tuning); the hard-gate caliber applies
equally to manual layouts and grades honestly without manual favors;
the comparison automatic layout does not run the --exact layer.

Stdlib only (engine invoked as a subprocess).
"""
import argparse
import json
import os
import subprocess
import sys


def _cert(d):
    with open(os.path.join(d, "certificate.json"), encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="compare-auto",
        description="dual-certificate comparison: manual (--from-layout) vs automatic layout")
    ap.add_argument("input", help="input .cld (DSL) or .json (graph model)")
    ap.add_argument("--from-layout", required=True, metavar="MANUAL_JSON",
                    help="manual layout JSON (demo-2d.html \"Export layout\" product)")
    ap.add_argument("--outdir", default="stdraw-out",
                    help="manual-run output directory (default stdraw-out); the "
                         "automatic comparison run lands in <outdir>-compare-auto")
    ap.add_argument("--name", default=None, help="graph name (default: the DSL graph name)")
    a = ap.parse_args(argv)

    def run(outdir, extra=()):
        cmd = [sys.executable, "-m", "stdraw", "layout", a.input, "--outdir", outdir] \
            + list(extra)
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r

    rm = run(a.outdir, ("--from-layout", a.from_layout)
             + ((("--name", a.name) if a.name else ())))
    if rm.returncode not in (0, 1):
        print(rm.stdout, rm.stderr, file=sys.stderr)
        sys.exit(rm.returncode or 1)

    cmp_dir = a.outdir.rstrip("/\\") + "-compare-auto"
    print("-- compare-auto: automatic layout comparison for the same graph --")
    ra = run(cmp_dir, (("--name", a.name) if a.name else ()))
    rc_cmp = ra.returncode

    cert_m, cert_a = _cert(a.outdir), _cert(cmp_dir)
    keys = ("crossings", "box_press_1px", "edge_box_min_clear",
            "anchor_violations", "avg_edge_length", "row_align_rate",
            "min_card_gap", "spacing_cv", "column_snap24_rate")
    table = {}
    for k in keys:
        mv, av = cert_m["metrics"].get(k), cert_a["metrics"].get(k)
        delta = (mv - av) if isinstance(mv, (int, float)) and \
            isinstance(av, (int, float)) else None
        table[k] = {"manual": mv, "auto": av,
                    "delta_manual_minus_auto": delta}
    name = a.name or cert_m.get("graph") or ""
    cmp_obj = {
        "tool": "tools/compare_auto.py", "graph": name,
        "manual_outdir": a.outdir, "auto_outdir": cmp_dir,
        "auto_cli_exit": rc_cmp,
        "metrics": table,
        "grade": {"manual": cert_m["grade"], "auto": cert_a["grade"]},
        "gates_passed": {"manual": cert_m["gates_passed"],
                         "auto": cert_a["gates_passed"]},
        "note": ("the gap is the aesthetic distance between engine and human "
                 "(the basis for future objective-function tuning); the hard-gate "
                 "caliber applies equally to manual layouts and grades honestly "
                 "without manual favors; the comparison automatic layout did not "
                 "run the --exact layer"),
    }
    p = os.path.join(a.outdir, "compare-auto.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cmp_obj, f, ensure_ascii=False, indent=1)
    print("  metric                      manual       auto")
    for k, v in table.items():
        print(f"  {k:<26} {str(v['manual']):>8} {str(v['auto']):>10}"
              f"  D={v['delta_manual_minus_auto']}")
    print(f"  grade: manual={cert_m['grade']} / auto={cert_a['grade']}; "
          f"gates manual {cert_m['gates_passed']} / auto {cert_a['gates_passed']}"
          f" (auto_cli_exit={rc_cmp})")
    print(f"  -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
