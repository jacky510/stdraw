#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual-coordinate certificate gate caliber (P1-2, WorkBuddy ticket R5).

jacky's 2026-11-13 ruling: under ``--from-layout`` (manual coordinates) the
two automatic-pipeline structural checks -- ``pitch_uniform`` and
``column_snap24_ge_060`` -- read "N/A" in ``certificate.gates`` (same caliber
as the geometry self-check in check.py 6a/9, "manual: N/A"), instead of a
measured ``false`` that no manual layout can ever satisfy.  This is a
caliber alignment, NOT a threshold change: the measured values stay in
``metrics`` (honest accounting), no other gate is touched, and the AUTO
path keeps boolean gate values (a 0-crossing hand-drawn layout can now
reach grade=best, 10/10 applicable gates).

Fixture: tests/data/epidemic-feedback-manual-layout.json (a hand-drawn
0-crossing layout of the tests/data/epidemic-feedback.cld graph; under the
pre-P1-2 caliber it graded uncertified 10/12 with both structural gates
false).

Stdlib only (subprocess CLI, same invocation shape as the other test files).
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLD = os.path.join(ROOT, "tests", "data", "epidemic-feedback.cld")
MANUAL = os.path.join(ROOT, "tests", "data",
                      "epidemic-feedback-manual-layout.json")
AUTO_LAYERED = os.path.join(ROOT, "benchmarks", "corpus", "random",
                            "random-n10-i00.cld")


def run_cli(args):
    return subprocess.run(
        [sys.executable, "-m", "stdraw"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT)


def _render(outdir, cld, extra):
    r = run_cli(["layout", cld, "--outdir", outdir, "--skip-3d"] + extra)
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
    return outdir


def _cert(outdir):
    with open(os.path.join(outdir, "certificate.json"),
              encoding="utf-8") as f:
        return json.load(f)


def test_manual_structural_gates_na(tmp_path):
    out = _render(str(tmp_path / "m"), CLD, ["--from-layout", MANUAL])
    cert = _cert(out)
    g = cert["gates"]
    assert g["pitch_uniform"] == "N/A", g["pitch_uniform"]
    assert g["column_snap24_ge_060"] == "N/A", g["column_snap24_ge_060"]
    # a 0-crossing hand-drawn layout now reaches best on the applicable gates
    assert cert["grade"] == "best", cert["grade"]
    assert cert["gates_passed"] == "10/10", cert["gates_passed"]
    assert cert["blocking_gates"] == [], cert["blocking_gates"]
    assert cert["metrics"]["crossings"] == 0
    assert cert["metrics"]["visual_crossings"] == 0
    # honest accounting: the measured structural values stay in metrics
    assert cert["metrics"]["column_snap24_rate"] == 0.0
    assert any("Manual coordinates" in n for n in cert["honest_notes"])
    assert cert.get("from_layout"), "manual provenance field missing"


def test_auto_path_keeps_boolean_gates(tmp_path):
    # caliber leakage guard: the auto certificate must keep measured
    # booleans (and its full gate count), never "N/A".
    out = _render(str(tmp_path / "a"), AUTO_LAYERED, [])
    cert = _cert(out)
    g = cert["gates"]
    assert isinstance(g["pitch_uniform"], bool), g["pitch_uniform"]
    assert isinstance(g["column_snap24_ge_060"], bool), g["column_snap24_ge_060"]
    assert "N/A" not in (str(v) for v in g.values())
    # honest grading on this random fixture: rc/grade not asserted here (a
    # random dense graph may legitimately grade uncertified); the guard is
    # about the gate VALUE caliber, not the grade.


def test_manual_deterministic(tmp_path):
    a = _render(str(tmp_path / "d1"), CLD, ["--from-layout", MANUAL])
    b = _render(str(tmp_path / "d2"), CLD, ["--from-layout", MANUAL])
    for name in ("layout.json", "certificate.json", "demo-2d.html"):
        with open(os.path.join(a, name), "rb") as f:
            ba = f.read()
        with open(os.path.join(b, name), "rb") as f:
            bb = f.read()
        assert ba == bb, name


if __name__ == "__main__":
    sys.exit(0)
