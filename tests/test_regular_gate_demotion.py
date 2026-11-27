#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regular-gate demotion (jacky rulings 2026-11-26 / 2026-11-27).

Two calibers, two rulings, deliberately stated separately in
``stdraw/cert_gates.py`` (``_auto_regularity_applies`` /
``_manual_cv_never_gates`` / ``_manual_pitch_family_keeps_slot``):

* AUTO (``--recipe auto``, 2026-11-26): the mechanical-grid regularity
  gates -- ``cv_le_035`` / ``pitch_uniform`` family /
  ``column_snap24_ge_060`` -- gate n<=10 figures only; for n>10 the
  registry ``when`` policies demote them to certificate report items
  (measured boolean kept, excluded from gates_passed / hard_ok).
* MANUAL (``--from-layout``, 2026-11-27): ``cv_le_035`` never gates a
  hand-drawn figure -- always demoted to a report item.  The
  ``pitch_uniform`` / ``column_snap24_ge_060`` slots keep their P1-2
  ``"N/A"`` applicability caliber (2026-11-13) and are NOT touched.

n<=10 automatic certificates are byte-for-byte unchanged.
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
CLASSIC = os.path.join(ROOT, "benchmarks", "corpus", "classic",
                       "classic-cld-growth-and-burden.cld")
CLASSIC_MANUAL = os.path.join(ROOT, "benchmarks", "manual",
                              "classic-cld-manual-layout.json")
N10_LAYERED = os.path.join(ROOT, "benchmarks", "corpus", "random",
                           "random-n10-i00.cld")

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


def test_manual_mode_demotes_target_gate_only():
    """MANUAL caliber (jacky 2026-11-27): cv_le_035 never gates a
    --from-layout figure -- it leaves ``gates`` for ``reports`` -- while
    the pitch/snap family keeps its P1-2 N/A slot and stays in ``gates``.
    """
    ctx = _ctx(10, manual=True)
    g = build_gates(ctx)
    assert "cv_le_035" not in g
    assert ctx.demoted_gates == {"cv_le_035": True}
    assert g["pitch_uniform"] == "N/A"          # P1-2 slots unchanged
    assert g["column_snap24_ge_060"] == "N/A"
    assert "pitch_uniform" not in ctx.demoted_gates
    assert "column_snap24_ge_060" not in ctx.demoted_gates
    # the demotion removes exactly one applicable gate from the count
    n_gates = sum(1 for v in g.values() if isinstance(v, bool))
    assert n_gates == 9


def test_manual_large_n_demotes_target_gate_too():
    """The manual criterion is constant (never gates) -- it does not
    depend on n, unlike the automatic n<=10 criterion."""
    ctx = _ctx(12, manual=True)
    g = build_gates(ctx)
    assert "cv_le_035" not in g
    assert ctx.demoted_gates == {"cv_le_035": True}


def test_auto_mode_unaffected_by_manual_ruling():
    """AUTO caliber regression guard: the manual ruling must not leak into
    the automatic pipeline.  n<=10 keeps all three hard gates; n>10
    demotes all three (the pre-existing 2026-11-26 behavior)."""
    g_small = build_gates(_ctx(10))
    for k in REG_KEYS:
        assert isinstance(g_small[k], bool), (k, g_small[k])
    ctx_large = _ctx(12)
    g_large = build_gates(ctx_large)
    assert set(ctx_large.demoted_gates) == set(REG_KEYS)
    for k in REG_KEYS:
        assert k not in g_large, k


def test_manual_demotion_does_not_press_grade_inputs():
    """A demoted gate leaves ``gates`` entirely: it cannot appear in
    ``blocking_gates`` (derived from False gate values) and ``hard_ok``
    reads it with a True default.  Guarded at the value level here; the
    CLI-level test below proves the certificate face."""
    ctx = _ctx(10, manual=True)
    g = build_gates(ctx)
    assert [k for k, v in g.items() if v is False] == []
    assert "cv_le_035" not in g


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


# ── CLI-level: the manual (--from-layout) caliber, real pipeline ─────────

def test_manual_cli_reports_cv_demotion_with_manual_wording(tmp_path):
    """End-to-end on jacky's hand-drawn classic-cld layout: the manual
    certificate drops ``cv_le_035`` from ``gates`` (measured boolean to
    ``reports``), keeps the P1-2 N/A slots, and words the downgrade as
    the MANUAL caliber -- never as the n>10 automatic one."""
    out = str(tmp_path / "manual")
    r = _cli(["layout", CLASSIC, "--from-layout", CLASSIC_MANUAL,
              "--outdir", out])
    assert r.returncode == 0, (r.returncode, r.stderr[-500:])
    cert = _cert(out)
    g, rep = cert["gates"], cert["reports"]
    assert "cv_le_035" not in g
    assert isinstance(rep["cv_le_035"], bool)
    assert g["pitch_uniform"] == "N/A"
    assert g["column_snap24_ge_060"] == "N/A"
    note = rep["regularity_demoted_note"]
    assert "manual caliber" in note and "2026-11-27" in note
    assert "n>10" not in note
    assert any("manual caliber:" in n for n in cert["honest_notes"])
    assert not any("n>10 caliber:" in n for n in cert["honest_notes"])
    # demoted -> not blocking, and gates_passed counts real boolean gates
    assert "cv_le_035" not in cert["blocking_gates"]
    n_bool = sum(1 for v in g.values() if isinstance(v, bool))
    assert cert["gates_passed"].split("/")[1] == str(n_bool)


def test_auto_cli_keeps_bytes_of_n10_caliber(tmp_path):
    """AUTO n<=10 guard: a layered n=10 graph rendered automatically keeps
    all three regularity gates as booleans -- the manual ruling did not
    leak into the automatic pipeline."""
    out = str(tmp_path / "auto")
    r = _cli(["layout", N10_LAYERED, "--outdir", out])
    assert r.returncode == 0, (r.returncode, r.stderr[-400:])
    cert = _cert(out)
    g = cert["gates"]
    assert cert["placement"] == "layered"
    for k in REG_KEYS:
        assert isinstance(g[k], bool), (k, g[k])
    assert "regularity_demoted_note" not in cert["reports"]


# ── domain-exhaustive caliber separation (registry level, no rendering) ──

MODE_FLAG = {
    "ring-cycle": "ring_mode", "radial": "radial_mode",
    "column-chain": "column_mode", "comb-bilateral": "comb_mode",
    "symmetric": "sym_mode", "bowtie-vertex": "bowtie_mode",
    "spine-wing": "spine_mode", "lens-chain": "lens_mode",
    "planarized-L1": "plz_l1",
}


def _flag_ctx(mode_label, n, manual):
    """GateCtx stand-in carrying only what the mode detect lambdas and the
    registry ``when`` policies read.  Used to close the caliber-separation
    claim over the WHOLE input domain instead of sampling graphs."""
    import types as _t
    c = _t.SimpleNamespace()
    c.n_nodes = n
    c.manual_mode = manual
    for f in set(MODE_FLAG.values()) | {"layered_mode"}:
        setattr(c, f, False)
    for m in mode_label.split("|"):
        if m in MODE_FLAG:
            setattr(c, MODE_FLAG[m], True)
    return c


def _kept_keys(mode_set, n, manual):
    c = _flag_ctx(mode_set["mode"], n, manual)
    return [e["key"] for e in mode_set["entries"]
            if e["when"] is None or e["when"](c)]


def test_auto_caliber_is_n_thresholded_and_manual_is_not():
    """The two criteria are structurally different, over n=1..40:

    * AUTO -- the regularity family gates only n<=10 (2026-11-26), so the
      kept-key set must be identical for every n<=10 and identical for
      every n>10, and the two halves must differ where the mode carries
      a regularity entry.
    * MANUAL -- the cv criterion is constant False, so ``cv_le_035`` is
      absent from the kept set at EVERY n and in every mode that carries
      it; the pitch/snap family (constant True) stays present.
    """
    for s in MODE_GATE_SETS:
        has_cv = any(e["key"] == "cv_le_035" for e in s["entries"])
        small = {tuple(_kept_keys(s, n, False)) for n in range(1, 11)}
        large = {tuple(_kept_keys(s, n, False)) for n in range(11, 41)}
        assert len(small) == 1, (s["mode"], small)
        assert len(large) == 1, (s["mode"], large)
        if has_cv:
            assert "cv_le_035" in small.pop()
            assert "cv_le_035" not in large.pop()
        for n in (1, 10, 11, 40):
            kept = _kept_keys(s, n, True)
            if has_cv:
                assert "cv_le_035" not in kept, (s["mode"], n)
            for k in ("pitch_uniform", "spine_pitch_uniform",
                      "column_pitch_uniform", "column_snap24_ge_060"):
                if any(e["key"] == k for e in s["entries"]):
                    assert k in kept, (s["mode"], n, k)


PITCH_FAMILY = frozenset(("pitch_uniform", "spine_pitch_uniform",
                           "column_pitch_uniform", "column_snap24_ge_060"))


def test_manual_delta_is_exactly_the_target_gate_in_every_cell():
    """Cell-by-cell caliber separation over the whole domain.

    For n <= 10 the AUTO caliber keeps all three regularity gates, so
    switching a cell to MANUAL may remove ``cv_le_035`` and nothing else.

    For n > 10 the AUTO caliber already demotes the pitch family
    (2026-11-26) while the MANUAL caliber keeps it (constant True, the
    P1-2 N/A slot) -- so there the delta is: ``cv_le_035`` removed, plus
    the pitch family REAPPEARING.  That reappearance is the pre-existing
    manual caliber showing through, not spill-over from this ruling, and
    it is pinned explicitly here so neither regime can drift silently.
    """
    for s in MODE_GATE_SETS:
        for n in range(1, 41):
            auto = _kept_keys(s, n, False)
            manual = _kept_keys(s, n, True)
            removed = sorted(set(auto) - set(manual))
            added = sorted(set(manual) - set(auto))
            assert removed in ([], ["cv_le_035"]), (s["mode"], n, removed)
            if n <= 10:
                assert added == [], (s["mode"], n, added)
            else:
                # only the pitch family may return; nothing else
                assert set(added) <= PITCH_FAMILY, (s["mode"], n, added)
                assert added == sorted(PITCH_FAMILY & set(added)),                     (s["mode"], n, added)
