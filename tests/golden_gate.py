#!/usr/bin/env python
"""Golden archetype gate: the small, hard acceptance baseline for engine changes.

Scope (docs/validation-tiers.md section 10): tests/golden/*.cld holds the
first batch of classic system archetypes (3-8 nodes each).  Every graph must
come out of the full CLI pipeline as::

    grade == "best", geometry fail == 0, loops_audit problems == 0,
    every certificate hard gate true, 0 crossings, 0 visual crossings

and must stay byte-identical to tests/golden/baseline.json:

- ``certificate.json`` / ``loops_audit.json``: sha256 of the raw bytes with
  CRLF folded to LF (the CLI writes text-mode files, so Windows and Linux
  check-outs differ only by EOL);
- ``layout.json``: sha256 of the canonical JSON dump with ``engine_version``
  removed (that one field moves at every version closure; everything else in
  the layout is content);
- ``<name>.cld``: the input fixture itself, so an edit to a golden graph is
  also a drift that needs a conscious re-bless.

Any mismatch is a DRIFT failure naming the field.  Re-blessing is an explicit
action (``--update-baseline``) that belongs to an approved card and prints
what changed; the gate never rewrites the baseline on its own.

Timing: per-graph wall seconds are recorded into the baseline as a reference
(``timing_ref``) and printed against it on every run (avg + max, the T12
speed-up ledger).  Timing never fails the gate -- runner speed is not a repo
property -- but a run slower than 2x the reference is reported loudly.

Engine caliber: the baseline is only meaningful under the cp-sat layered
engine.  Without ortools the gate refuses to run (exit 1) instead of
comparing a fallback-construct render against a cp-sat baseline.

Usage::

    python tests/golden_gate.py                     # gate (CI + local)
    python tests/golden_gate.py --update-baseline   # re-bless (approved card only)
    python tests/golden_gate.py --only escalation   # single graph, quick probe
    python tests/golden_gate.py --json out.json     # also dump the measured records
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GOLDEN_DIR = os.path.join(HERE, "golden")
BASELINE_PATH = os.path.join(GOLDEN_DIR, "baseline.json")
SCHEMA = "stdraw-golden-baseline/1"
ENGINE_CALIBER = "cp-sat-layered"
RAW_PINNED = ("certificate.json", "loops_audit.json")
TIMING_WARN_FACTOR = 2.0

# Option 1 (row pitch 96) of the GaU layout plan, approved 2026-11-26:
# the one archetype whose ring column reads too narrow is re-tuned at
# the render call site; the engine itself stays untouched.  The baseline
# entry for this graph is the fingerprint of the --pitch 96 render
# (re-blessed under that approval; see docs/a-tier-drift-registry.md).
# Transitional: --pitch is deprecated (T14); migration to a recipe-level
# parameter is a separate card, due before the P3 physical removal.
PER_GRAPH_CLI_ARGS = {
    "growth-and-underinvestment": ["--pitch", "96"],
}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fold_lf(data):
    return data.replace(b"\r\n", b"\n")


def sha256_file_lf(path):
    with open(path, "rb") as f:
        return sha256_bytes(fold_lf(f.read()))


def sha256_file_cld(path):
    # same EOL folding for the fixture: autocrlf check-outs differ by EOL only
    return sha256_file_lf(path)


def layout_fingerprint(layout_obj):
    obj = dict(layout_obj)
    obj.pop("engine_version", None)
    canon = json.dumps(obj, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
    return sha256_bytes(canon)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def golden_clds(only=None):
    paths = sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.cld")))
    if only:
        paths = [p for p in paths
                 if os.path.splitext(os.path.basename(p))[0] == only]
    return paths


def engine_version():
    sys.path.insert(0, ROOT)
    try:
        import stdraw  # noqa: WPS433
        return stdraw.__version__
    finally:
        sys.path.pop(0)


def ortools_version():
    try:
        import ortools  # noqa: WPS433
    except Exception:  # pragma: no cover - environment dependent
        return None
    return getattr(ortools, "__version__", "unknown")


def run_graph(cld, outdir):
    """Run the full CLI pipeline (same entry as docs quickstart) on one graph."""
    os.makedirs(outdir, exist_ok=True)
    name = os.path.splitext(os.path.basename(cld))[0]
    cmd = [sys.executable, "-m", "stdraw", "layout", cld, "--outdir", outdir]
    cmd += PER_GRAPH_CLI_ARGS.get(name, [])
    t0 = time.time()
    r = subprocess.run(
        cmd,
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    return r, time.time() - t0


def evaluate(name, cld, outdir, rc, seconds):
    """Hard assertions for one golden graph -> (record, problems)."""
    problems = []
    rec = {"cld": os.path.basename(cld), "seconds": round(seconds, 2),
           "sha256": {"cld": sha256_file_cld(cld)}}
    if rc != 0:
        problems.append(f"golden {name}: CLI exit {rc}")
        return rec, problems
    for fn in RAW_PINNED + ("layout.json", "geometry_report.json"):
        if not os.path.exists(os.path.join(outdir, fn)):
            problems.append(f"golden {name}: missing output {fn}")
    if problems:
        return rec, problems
    cert = load_json(os.path.join(outdir, "certificate.json"))
    geo = load_json(os.path.join(outdir, "geometry_report.json"))
    audit = load_json(os.path.join(outdir, "loops_audit.json"))
    layout = load_json(os.path.join(outdir, "layout.json"))
    metrics = cert.get("metrics", {})
    gates = cert.get("gates", {})
    false_gates = sorted(k for k, v in gates.items() if v is False)
    rec.update({
        "caliber": cert.get("caliber"),
        "grade": cert.get("grade"),
        "placement": cert.get("placement"),
        "gates_passed": cert.get("gates_passed"),
        "crossings": metrics.get("crossings"),
        "visual_crossings": metrics.get("visual_crossings"),
        "box_press_1px": metrics.get("box_press_1px"),
        "edge_box_min_clear": metrics.get("edge_box_min_clear"),
        "min_card_gap": metrics.get("min_card_gap"),
        "geometry_fail": (geo.get("summary") or {}).get("fail"),
        "loops_problems": (audit.get("summary") or {}).get("problems"),
        "loops_declared": len(audit.get("loops") or []),
        "nodes": len(layout.get("nodes") or {}),
        "edges": len(layout.get("edges") or []),
        "sha256": {
            "cld": rec["sha256"]["cld"],
            "certificate": sha256_file_lf(os.path.join(outdir, "certificate.json")),
            "loops_audit": sha256_file_lf(os.path.join(outdir, "loops_audit.json")),
            "layout": layout_fingerprint(layout),
        },
    })
    if cert.get("caliber") != "v2-hardgates" or cert.get("recipe") != "auto-v2":
        problems.append(f"golden {name}: caliber/recipe {cert.get('caliber')}/"
                        f"{cert.get('recipe')} (expected v2-hardgates/auto-v2)")
    if cert.get("grade") != "best":
        problems.append(f"golden {name}: grade {cert.get('grade')} (expected best); "
                        f"blocking={cert.get('blocking_gates')}")
    if false_gates:
        problems.append(f"golden {name}: hard gate(s) false: {false_gates}")
    if rec["geometry_fail"] != 0:
        problems.append(f"golden {name}: geometry fail {rec['geometry_fail']} (expected 0)")
    if rec["loops_problems"] != 0:
        problems.append(f"golden {name}: loops_audit problems {rec['loops_problems']} "
                        f"(expected 0): {audit.get('problems')}")
    if rec["crossings"] != 0 or rec["visual_crossings"] != 0:
        problems.append(f"golden {name}: crossings {rec['crossings']} / visual "
                        f"{rec['visual_crossings']} (expected 0/0)")
    if cert.get("deliverable") is not True:
        problems.append(f"golden {name}: certificate deliverable={cert.get('deliverable')}")
    return rec, problems


def compare(name, rec, entry):
    """Baseline comparison -> list of drift strings (empty = identical)."""
    drift = []
    if not entry:
        return [f"golden {name}: no baseline entry (run --update-baseline under an approved card)"]
    for key in ("grade", "placement", "gates_passed", "crossings", "visual_crossings",
                "nodes", "edges", "loops_declared"):
        if rec.get(key) != entry.get(key):
            drift.append(f"golden {name}: {key} drift {entry.get(key)!r} -> {rec.get(key)!r}")
    for key, want in (entry.get("sha256") or {}).items():
        got = (rec.get("sha256") or {}).get(key)
        if got != want:
            drift.append(f"golden {name}: sha256.{key} drift {str(want)[:12]} -> {str(got)[:12]}")
    return drift


def timing_summary(records):
    secs = [r["seconds"] for r in records]
    if not secs:
        return {"avg": 0.0, "max": 0.0}
    return {"avg": round(sum(secs) / len(secs), 2), "max": round(max(secs), 2)}


def timing_report(records, ref):
    """Print the timing table vs the recorded reference; return warn lines."""
    cur = timing_summary(records)
    lines = []
    ref_avg = float((ref or {}).get("avg") or 0.0)
    ref_max = float((ref or {}).get("max") or 0.0)
    print(f"     golden timing: avg {cur['avg']}s / max {cur['max']}s "
          f"(reference avg {ref_avg}s / max {ref_max}s"
          + (f", {ref.get('platform')}" if ref else "") + ")")
    if ref_avg and cur["avg"] > TIMING_WARN_FACTOR * ref_avg:
        lines.append(f"WARN golden timing: avg {cur['avg']}s is "
                     f"{cur['avg'] / ref_avg:.1f}x the reference {ref_avg}s "
                     f"(speed-up ledger: compare runner speed first)")
    if ref_max and cur["max"] > TIMING_WARN_FACTOR * ref_max:
        lines.append(f"WARN golden timing: max {cur['max']}s is "
                     f"{cur['max'] / ref_max:.1f}x the reference {ref_max}s")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--update-baseline", action="store_true",
                    help="re-bless tests/golden/baseline.json from this run "
                         "(approved card only; prints what changed)")
    ap.add_argument("--only", default=None,
                    help="restrict to one golden graph name (quick probe)")
    ap.add_argument("--json", default=None,
                    help="also dump the measured records to this JSON path")
    args = ap.parse_args(argv)

    ortools_ver = ortools_version()
    if ortools_ver is None:
        print(f"FAIL golden gate: ortools absent -- the baseline is recorded under the "
              f"{ENGINE_CALIBER} engine and a fallback-construct render cannot be compared "
              f"against it. Rerun under an ortools interpreter.", file=sys.stderr)
        return 1
    clds = golden_clds(args.only)
    if not clds:
        print("FAIL golden gate: no tests/golden/*.cld found", file=sys.stderr)
        return 1
    baseline = load_json(BASELINE_PATH) if os.path.exists(BASELINE_PATH) else {}
    graphs_base = baseline.get("graphs") or {}
    failures = []
    records = {}
    tmp = tempfile.mkdtemp(prefix="stdraw-golden-")
    try:
        print(f"golden gate: {len(clds)} graph(s), engine {ENGINE_CALIBER} "
              f"(ortools {ortools_ver}), stdraw {engine_version()}")
        for cld in clds:
            name = os.path.splitext(os.path.basename(cld))[0]
            outdir = os.path.join(tmp, name)
            r, seconds = run_graph(cld, outdir)
            rec, problems = evaluate(name, cld, outdir, r.returncode, seconds)
            if problems and r.stderr:
                problems.append(f"golden {name}: stderr tail: "
                                + r.stderr.strip().splitlines()[-1][:300])
            records[name] = rec
            if problems:
                failures.extend(problems)
                for p in problems:
                    print("FAIL " + p)
                continue
            if args.update_baseline:
                print(f"OK   golden {name}: {rec['grade']} / {rec['placement']} / "
                      f"gates {rec['gates_passed']} / crossings {rec['crossings']} / "
                      f"loops {rec['loops_problems']} / geo fail {rec['geometry_fail']} / "
                      f"{rec['seconds']}s (baseline will be rewritten)")
                continue
            drift = compare(name, rec, graphs_base.get(name))
            if drift:
                failures.extend(drift)
                for d in drift:
                    print("DRIFT " + d)
            else:
                print(f"OK   golden {name}: {rec['grade']} / {rec['placement']} / "
                      f"gates {rec['gates_passed']} / crossings {rec['crossings']} / "
                      f"loops {rec['loops_problems']} / geo fail {rec['geometry_fail']} / "
                      f"{rec['seconds']}s / baseline identical")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    warns = []
    if not args.only and not args.update_baseline:
        warns = timing_report(list(records.values()), baseline.get("timing_ref"))
    for w in warns:
        print(w)

    if args.update_baseline:
        if failures:
            print("\nREFUSED --update-baseline: hard-gate failures above; a non-best "
                  "render is never blessed.", file=sys.stderr)
            return 1
        old = graphs_base
        changed = []
        for name, rec in records.items():
            prev = old.get(name) or {}
            for key in ("grade", "placement", "gates_passed"):
                if prev.get(key) != rec.get(key):
                    changed.append(f"{name}: {key} {prev.get(key)!r} -> {rec.get(key)!r}")
            for key in (rec.get("sha256") or {}):
                if (prev.get("sha256") or {}).get(key) != rec["sha256"][key]:
                    changed.append(f"{name}: sha256.{key} "
                                   f"{str((prev.get('sha256') or {}).get(key))[:12]} -> "
                                   f"{rec['sha256'][key][:12]}")
        full_records = dict(records)
        # --only re-bless: keep the untouched graphs from the previous baseline
        for name, prev in old.items():
            full_records.setdefault(name, prev)
        ordered = {k: full_records[k] for k in sorted(full_records)}
        new_baseline = {
            "_schema": SCHEMA,
            "_meta": {
                "engine_caliber": ENGINE_CALIBER,
                "ortools": ortools_ver,
                "engine_version": engine_version(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "recorded": datetime.date.today().isoformat(),
                "hash_caliber": {
                    "cld": "sha256 of the fixture bytes, CRLF folded to LF",
                    "certificate": "sha256 of certificate.json bytes, CRLF folded to LF",
                    "loops_audit": "sha256 of loops_audit.json bytes, CRLF folded to LF",
                    "layout": "sha256 of layout.json as canonical JSON (sort_keys, "
                              "compact separators, ensure_ascii=False) minus engine_version",
                },
                "timing_caliber": "per-graph wall seconds of `python -m stdraw layout` "
                                  "on the recording machine; reference only, never a gate",
                "rebless": "only under an approved card: python tests/golden_gate.py --update-baseline",
            },
            "timing_ref": dict(timing_summary(list(ordered.values())),
                               platform=platform.platform(),
                               per_graph={k: v["seconds"] for k, v in ordered.items()}),
            "graphs": ordered,
        }
        dump_json(BASELINE_PATH, new_baseline)
        print(f"\nbaseline rewritten: {BASELINE_PATH}")
        if changed:
            print("changed vs previous baseline:")
            for c in changed:
                print(" -", c)
        else:
            print("changed vs previous baseline: nothing (byte/metric identical)")
        return 0

    if args.json:
        dump_json(args.json, {"records": records, "failures": failures,
                              "timing": timing_summary(list(records.values()))})
    failed_names = {f.split(":", 1)[0].replace("golden ", "", 1) for f in failures}
    n_ok = sum(1 for n in records if n not in failed_names)
    print(f"\ngolden gate: {n_ok}/{len(clds)} graphs pass"
          + (" -- ALL GREEN" if not failures else f" -- {len(failed_names)} graph(s) red, "
                                                  f"{len(failures)} failure line(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
