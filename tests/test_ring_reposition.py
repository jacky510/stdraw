#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single-node zero-crossing neighborhood reposition (ring-cycle) regression.

Covers the ring-cycle reposition post-processing (layout_auto._ring_reposition):

  1. epidemic-feedback fixture (10 nodes / 14 edges / 5 loops, SIR +
     capacity-constraint structure): the selected 9-node main ring carries
     chord crossings under the frozen selection key and the delivery used to
     grade uncertified with crossings=1 / visual=1. The post-processing must
     rescue it to grade=best with BOTH crossing calibers at 0, every hard
     gate passing, and record its decision on the certificate-facing
     mode_decision_trace (post_layout_reposition).
  2. success-to-the-successful (the classic corpus fixture): same rescue.
  3. A healthy ring figure (debt-spiral, delivered at 0 crossings with a
     chord-crossing-free main ring) must stay untouched: no
     post_layout_reposition key at all (a no-op never writes).
  4. Determinism: two renders of the same fixture are byte-identical.

Stdlib only (subprocess CLI, same invocation shape as the other test files).
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPIDEMIC = os.path.join(ROOT, "tests", "data", "epidemic-feedback.cld")
SUCCESS = os.path.join(ROOT, "benchmarks", "corpus", "classic",
                       "success-to-the-successful.cld")
DEBT = os.path.join(ROOT, "benchmarks", "corpus", "classic",
                    "debt-spiral.cld")


def run_layout(cld_path, outdir):
    """CLI render at the CI caliber (auto recipe self-tunes its pitch)."""
    return subprocess.run(
        [sys.executable, "-m", "stdraw", "layout", cld_path,
         "--outdir", outdir, "--skip-3d"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT)


def load(outdir, name):
    with open(os.path.join(outdir, name), encoding="utf-8") as f:
        return json.load(f)


def _render(tmpdir, tag, cld_path):
    out = os.path.join(str(tmpdir), tag)
    r = run_layout(cld_path, out)
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]
    return out


def _cert(out):
    return load(out, "certificate.json")


def _trace(out):
    return (load(out, "layout.json")["meta"].get("mode_decision_trace") or {})


def test_epidemic_rescued_to_best(tmp_path):
    out = _render(tmp_path, "epidemic", EPIDEMIC)
    cert = _cert(out)
    assert cert["grade"] == "best", cert["grade"]
    assert cert["gates_passed"] == "11/11", cert["gates_passed"]
    assert cert["blocking_gates"] == [], cert["blocking_gates"]
    m = cert["metrics"]
    assert m["crossings"] == 0 and m["visual_crossings"] == 0
    rec = _trace(out).get("post_layout_reposition")
    assert rec, "reposition decision trace missing"
    assert rec["crossings_after"] == 0 and rec["visual_crossings_after"] == 0
    assert rec["node"] in rec["moved_nodes"]
    # the demotion kept the ring gates green on the re-fit polygon
    assert cert["gates"].get("ring_spacing_cv_le_005") is True
    assert cert["gates"].get("ring_template_fit_le_005") is True


def test_success_rescued_to_best(tmp_path):
    out = _render(tmp_path, "success", SUCCESS)
    cert = _cert(out)
    assert cert["grade"] == "best", cert["grade"]
    m = cert["metrics"]
    assert m["crossings"] == 0 and m["visual_crossings"] == 0
    assert _trace(out).get("post_layout_reposition")


def test_healthy_ring_untouched(tmp_path):
    out = _render(tmp_path, "debt", DEBT)
    cert = _cert(out)
    assert cert["grade"] == "best", cert["grade"]
    assert cert["placement"] == "ring-cycle", cert["placement"]
    assert "post_layout_reposition" not in _trace(out)


def test_reposition_deterministic(tmp_path):
    a = _render(tmp_path, "d1", EPIDEMIC)
    b = _render(tmp_path, "d2", EPIDEMIC)
    for name in ("layout.json", "certificate.json", "demo-2d.html"):
        with open(os.path.join(a, name), "rb") as f:
            ba = f.read()
        with open(os.path.join(b, name), "rb") as f:
            bb = f.read()
        assert ba == bb, name
