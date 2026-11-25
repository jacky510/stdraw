#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fact-based line-kind caliber + the CLI --no-loop-labels flag.

Coverage:
  1. demo-2d.html H1 and the CLI summary print the DELIVERED line-kind
     counts (certificate metrics.line_kind_counts), never the --linestyle
     request echo (the loop-side arc default can deliver all-arc drawings
     while the request reads straight);
  2. --no-loop-labels suppresses the annotation layer in the demo only
     (loop-label group, delay tick marks, Loops toolbar toggle, the
     embedded loops/delay payload keys); the line and arrow geometry is
     untouched and layout.json keeps its annotation records;
  3. with the flag, the certificate records loop_labels_clear /
     delay_marks_clear as "N/A" (excluded from gates_passed, never
     blocking), the grade stays identical to the default leg, and an
     honest note documents the suppression;
  4. default runs keep today's bytes for every non-demo product.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.render import line_kind_summary

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLASSIC = os.path.join("examples", "classic-cld-growth-and-burden.cld")
DELAYED = os.path.join(HERE, "data", "limits-to-growth-4n-delay.cld")


def _run_cli(cld, outdir, *extra):
    return subprocess.run(
        [sys.executable, "-m", "stdraw", "layout", cld,
         "--outdir", outdir, *extra],
        capture_output=True, text=True, cwd=ROOT,
        encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def legs(tmp_path_factory):
    """Two CLI legs on the loop+delay fixture: default and --no-loop-labels."""
    tmp = tmp_path_factory.mktemp("line-style-facts")
    out = {}
    for key, extra in (("default", ()), ("nolabels", ("--no-loop-labels",))):
        d = os.path.join(str(tmp), key)
        r = _run_cli(DELAYED, d, *extra)
        assert r.returncode == 0, r.stderr[-2000:]
        out[key] = d
    return out


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _cert(d):
    return json.loads(_read(os.path.join(d, "certificate.json")))


def test_h1_prints_delivered_line_kinds(tmp_path):
    """H1 states the delivered line-kind counts, matching the certificate."""
    d = os.path.join(str(tmp_path), "out")
    r = _run_cli(CLASSIC, d, "--name", "classic-cld")
    assert r.returncode == 0, r.stderr[-2000:]
    html = _read(os.path.join(d, "demo-2d.html"))
    counts = _cert(d)["metrics"]["line_kind_counts"]
    expected = " / ".join(f"{k} {n}" for k, n in
                          sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    assert f"line kinds {expected}" in html
    # the request echo must not pose as a delivered fact anywhere in the face
    assert "line style straight" not in html
    assert "line kinds arc" in html  # loop arcs are the delivered default


def test_cli_summary_prints_line_kinds(tmp_path):
    """The [3/5] CLI summary line prints delivered counts, not the request."""
    d = os.path.join(str(tmp_path), "out")
    r = _run_cli(CLASSIC, d, "--name", "classic-cld")
    assert r.returncode == 0, r.stderr[-2000:]
    assert "line kinds arc" in r.stdout
    assert "line style=" not in r.stdout


def test_no_loop_labels_suppresses_annotation_layer_in_demo(legs):
    """The flag removes the identity marks from the demo face, nothing else."""
    html = _read(os.path.join(legs["nolabels"], "demo-2d.html"))
    assert 'id="stdraw-looplabels"' not in html
    assert 'class="stdraw-delay"' not in html
    assert "Loops: on" not in html
    assert '"loops":[' not in html
    assert '"delay":true' not in html
    # the default leg still carries every annotation-layer element
    dhtml = _read(os.path.join(legs["default"], "demo-2d.html"))
    assert 'id="stdraw-looplabels"' in dhtml
    assert 'class="stdraw-delay"' in dhtml
    # geometry delivery is untouched: the edge groups are identical once the
    # (suppressed) delay tick path is discounted
    def groups(text):
        return [g.split("</g>")[0].replace("\n", "")
                for g in text.split("<g data-edge=")
                if g[:1].isdigit()]
    assert [x for x in groups(html)] == \
        [y for y in groups(dhtml)
         if 'class="stdraw-delay"' not in y]


def test_no_loop_labels_certificate_na_and_grade_unchanged(legs):
    """Suppressed layer -> gates honestly N/A; grade semantics unchanged."""
    cert_off = _cert(legs["nolabels"])
    cert_on = _cert(legs["default"])
    assert cert_off["gates"]["loop_labels_clear"] == "N/A"
    assert cert_off["gates"]["delay_marks_clear"] == "N/A"
    assert cert_on["gates"]["loop_labels_clear"] is True
    assert cert_on["gates"]["delay_marks_clear"] is True
    assert cert_off["grade"] == cert_on["grade"]
    n_off = int(cert_off["gates_passed"].split("/")[0])
    n_on = int(cert_on["gates_passed"].split("/")[0])
    assert n_off == n_on - 2
    notes = " ".join(cert_off["honest_notes"])
    assert "annotation layer suppressed by request" in notes
    # metrics rows stay measured (they describe layout.json, which still
    # carries the placed annotations)
    assert cert_off["metrics"]["delay_mark_count"] == \
        cert_on["metrics"]["delay_mark_count"]


def test_no_loop_labels_layout_json_byte_identical(legs):
    """Only the demo face and the certificate change; layout.json does not."""
    assert _read(os.path.join(legs["nolabels"], "layout.json")) == \
        _read(os.path.join(legs["default"], "layout.json"))


def test_line_kind_summary_fallback_counts_routes():
    """Without a certificate the helper counts the delivered edge routes."""
    v4 = {"edges": [
        {"route": {"kind": "arc"}},
        {"route": {"kind": "line"}},
        {"route": {"kind": "arc"}},
        {"route": {}},
    ]}
    assert line_kind_summary(v4) == "arc 2 / line 2"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
