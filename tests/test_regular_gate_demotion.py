#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regular-gate demotion (jacky ruling 2026-11-26, stdraw20 calibration).

The mechanical-grid regularity gates -- ``cv_le_035`` / ``pitch_uniform``
family / ``column_snap24_ge_060`` -- apply as hard gates ONLY on n<=10
figures of the automatic pipeline; for n>10 the registry ``when``
policies (stdraw/cert_gates.py ``_regularity_applies``) demote them to
certificate report items (measured boolean kept, excluded from
gates_passed / hard_ok).  n<=10 bytes and the manual (--from-layout)
caliber are untouched: n<=10 keeps all three keys, manual keeps today's
slots (P1-2 N/A + cv_le_035 still gating).
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.cert_gates import GateContext, build_gates, MODE_GATE_SETS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LENS_4N = os.path.join(ROOT, "tests", "data", "limits-to-growth-4n.cld")
N20 = os.path.join(ROOT, "benchmarks", "corpus", "random", "random-n20-i00.cld")

REG_KEYS = ("cv_le_035", "pitch_uniform", "column_snap24_ge_060")

ALL_TRUE = {
    "box_press_1px": 0, "edge_box_min_clear": 40, "anchor_violations": 0,
    "anchor_standard_violations": 0, "min_card_gap": 30, "spacing_cv": 0.2,
    "line_line_coincident_pairs": 0, "visual_crossings": 0,
}


def _ctx(n, manual=False):
    scene = {"nodes": {}, "edges": [], "polylines": {}}
    return GateContext(
        scene=scene, metrics=dict(ALL_TRUE), nodes={}, edges=[],
        ids=list(range(n)), crossings=[], plz={}, exactness=None,
        gates_param=None, routing_consistent=None, annotation_layer=True,
        notes=[], ring_mode=False, radial_mode=False, column_mode=False,
        sym_mode=False, bowtie_mode=False, spine_mode=False, comb_mode=False,
        lens_mode=False, layered_mode=True, manual_mode=manual, plz_l1=False,
        ring_nodes=None, radial=None, comb={}, lens={}, spine_wing=None,
        symmetry=None, pitch_uniform=False, snap_rate=0.0, mutual_min_sep=None,
        mutual_pairs_closed=True, pair_infos=[])


# ── registry wiring guard: every demotable slot carries the when policy ──

def test_registry_attaches_when_policies_to_all_demotable_slots():
    expected = {
        "column-chain": {"spine_pitch_uniform", "cv_le_035"},
        "comb-bilateral": {"column_pitch_uniform"},
        "symmetric|bowtie-vertex": {"cv_le_035"},
        "spine-wing": {"cv_le_035"},
        "lens-chain": {"cv_le_035", "pitch_uniform", "column_snap24_ge_060"},
        "layered": {"cv_le_035", "pitch_uniform", "column_snap24_ge_060"},
    }
    got = {}
    for mode_set in MODE_GATE_SETS:
        for entry in mode_set["entries"]:
            if entry["when"] is not None:
                got.setdefault(mode_set["mode"], set()).add(entry["key"])
    assert got == expected, got


# ── build_gates-level semantics ──────────────────────────────────────────

def test_small_n_keeps_all_three_gates():
    g = build_gates(_ctx(10))
    for k in REG_KEYS:
        assert isinstance(g[k], bool), (k, g[k])
    n_gates = sum(1 for v in g.values() if isinstance(v, bool))
    assert n_gates == 12  # layered set, all slots present


def test_large_n_demotes_to_report_items():
    ctx = _ctx(12)
    g = build_gates(ctx)
    for k in REG_KEYS:
        assert k not in g, k
        assert isinstance(ctx.demoted_gates[k], bool), k
    n_gates = sum(1 for v in g.values() if isinstance(v, bool))
    assert n_gates == 9  # 12 - 3 demoted


def test_manual_large_n_caliber_untouched():
    ctx = _ctx(12, manual=True)
    g = build_gates(ctx)
    assert ctx.demoted_gates == {}
    assert g["pitch_uniform"] == "N/A"          # P1-2 slots unchanged
    assert g["column_snap24_ge_060"] == "N/A"
    assert isinstance(g["cv_le_035"], bool)     # cv still gates on manual


# ── CLI-level: real pipeline, cheap small fixture first ──────────────────

def _cli(args):
    return subprocess.run(
        [sys.executable, "-m", "stdraw"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT)


def _cert(outdir):
    with open(os.path.join(outdir, "certificate.json"), encoding="utf-8") as f:
        return json.load(f)


def test_small_n_cli_keeps_boolean_gates(tmp_path):
    out = str(tmp_path / "small")
    r = _cli(["layout", LENS_4N, "--outdir", out])
    assert r.returncode == 0, r.stderr[-400:]
    g = _cert(out)["gates"]
    for k in REG_KEYS:
        assert isinstance(g[k], bool), (k, g[k])


@pytest.mark.slow
def test_large_n_cli_reports_demotion(tmp_path):
    out = str(tmp_path / "large")
    r = _cli(["layout", N20, "--outdir", out, "--allow-oversize"])
    # rc 1 = honest geometry hard-gate failure (the CLI still writes the
    # certificate); rc 0 = certified figure.  A traceback is never accepted.
    assert r.returncode in (0, 1), (r.returncode, r.stderr[-400:])
    assert "Traceback" not in r.stderr, r.stderr[-400:]
    cert = _cert(out)
    g, rep, m = cert["gates"], cert["reports"], cert["metrics"]
    assert cert["n"] > 10
    for k in REG_KEYS:
        assert k not in g, k
        assert isinstance(rep[k], bool), (k, rep[k])
        assert m.get("spacing_cv") is not None or k == "pitch_uniform"
    assert "regularity_demoted_note" in rep
    assert any("demoted to report items" in n for n in cert["honest_notes"])
    # gates_passed denominator excludes the demoted slots (13 -> 10 for the
    # layered set); the numerator stays the honest pass count
    n_bool = sum(1 for v in g.values() if isinstance(v, bool))
    assert cert["gates_passed"].split("/")[1] == str(n_bool), cert["gates_passed"]
    assert int(cert["gates_passed"].split("/")[1]) < 13
