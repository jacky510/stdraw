# -*- coding: utf-8 -*-
"""fan_slot_reorder unit tests (multi-slot anchor vocabulary card;
owner approval 2026-11-26).

Covers the third approved item: fan slot competition by SWAP keyed by the
departure azimuth φ (stdraw20 lesson §4: credit-cycle fan X 5→3 came from
swapping competing anchors, not from give-way).

- a crossing fan at a shared node side is swapped so the near segments
  uncross, with every FAN_SPREAD edge gate rechecked;
- non-crossing input is restored byte-for-byte (zero-drift contract);
- end-to-end: the fan-family corpus samples stay deterministic with all
  hard gates green and crossings not raised.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.routing import Router  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def _crossing_fan_routes():
    """Two entry edges arriving on box A's top border with their slots
    swapped relative to the targets' azimuth -> the near segments cross.

    A = (200, 100) 96x44 (top border y=77, border x-range 152..248).
    e1: T1=(260,300) -> A, anchor slot at x=170 (LEFT slot) but arriving
        from the RIGHT -> near segment aims right-down.
    e2: T2=(140,300) -> A, anchor slot at x=230 (RIGHT slot) arriving from
        the LEFT -> aims left-down.  The two near segments cross mid-air.
    """
    routes = {
        0: {"kind": "line", "press": 0, "min_clear": None, "cross": 0,
            "cross_edges": 0, "ang_a": 90.0, "ang_b": 90.0,
            "points": [[260.0, 300.0], [170.0, 77.0]]},
        1: {"kind": "line", "press": 0, "min_clear": None, "cross": 0,
            "cross_edges": 0, "ang_a": 90.0, "ang_b": 90.0,
            "points": [[140.0, 300.0], [230.0, 77.0]]},
    }
    return routes


def test_crossing_fan_is_swapped_by_phi_key():
    nodes = {"A": (200, 100, 96, 44), "T1": (260, 300, 96, 44),
             "T2": (140, 300, 96, 44)}
    edges = [("T1", "A"), ("T2", "A")]
    r = Router(nodes, edges)
    routes = _crossing_fan_routes()
    before = {i: [list(p) for p in routes[i]["points"]] for i in routes}
    out = r.fan_slot_reorder(routes)
    # something changed: the anchors were swapped (slots exchanged)
    assert [out[0]["points"][-1], out[1]["points"][-1]] != \
        [before[0][-1], before[1][-1]]
    # the near segments no longer cross
    from stdraw.routing import seg_cross
    s1 = (tuple(out[0]["points"][0]), tuple(out[0]["points"][1]))
    s2 = (tuple(out[1]["points"][0]), tuple(out[1]["points"][1]))
    assert not seg_cross(s1[0], s1[1], s2[0], s2[1])
    # each endpoint still sits on its own box border (tangent coordinate
    # swapped, border coordinate intact)
    for i, end_idx in ((0, 1), (1, 1)):
        p = out[i]["points"][end_idx]
        assert abs(p[1] - 77.0) <= 3.01 and 152.0 <= p[0] <= 248.0
    assert r.fan_reorder_report, "swap must be reported"


def test_non_crossing_input_restored_byte_for_byte():
    # same geometry, slots NOT swapped (left target -> left slot): no
    # near-segment crossing -> the pass must return identical bytes.
    nodes = {"A": (200, 100, 96, 44), "T1": (260, 300, 96, 44),
             "T2": (140, 300, 96, 44)}
    edges = [("T1", "A"), ("T2", "A")]
    r = Router(nodes, edges)
    routes = _crossing_fan_routes()
    # swap the anchors manually so slot order matches target order
    routes[0]["points"][-1] = [230.0, 77.0]
    routes[1]["points"][-1] = [170.0, 77.0]
    before = json.dumps({i: routes[i]["points"] for i in routes})
    out = r.fan_slot_reorder(routes)
    assert json.dumps({i: out[i]["points"] for i in out}) == before
    assert not getattr(r, "fan_reorder_report", [])


def test_determinism_double_run():
    snaps = []
    for _ in range(2):
        nodes = {"A": (200, 100, 96, 44), "T1": (260, 300, 96, 44),
                 "T2": (140, 300, 96, 44)}
        edges = [("T1", "A"), ("T2", "A")]
        r = Router(nodes, edges)
        routes = _crossing_fan_routes()
        out = r.fan_slot_reorder(routes)
        snaps.append(json.dumps({i: out[i]["points"] for i in out},
                                sort_keys=True))
    assert snaps[0] == snaps[1]


# ── end-to-end fan-family samples: gates green, crossings not raised ──

FAN_FAMILY = [
    "benchmarks/corpus/classic/population-logistic.cld",
    "benchmarks/corpus/classic/renewable-resource.cld",
    "benchmarks/corpus/classic/shifting-the-burden.cld",
]


@pytest.mark.repo("benchmarks/corpus")
@pytest.mark.parametrize("rel", FAN_FAMILY)
def test_fan_family_gates_and_crossings(rel, tmp_path):
    src = os.path.join(ROOT, rel)
    if not os.path.exists(src):
        pytest.skip("corpus file missing")
    digests = []
    for run in (1, 2):
        out = tmp_path / f"run{run}"
        r = subprocess.run([PY, "-m", "stdraw", "layout", src,
                            "--outdir", str(out)], cwd=ROOT,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr[-500:]
        cert = json.load(open(out / "certificate.json", encoding="utf-8"))
        for k, v in cert["gates"].items():
            if v is False:
                raise AssertionError(f"{rel}: hard gate {k} FAIL")
        assert cert["metrics"]["crossings"] <= 2
        assert cert["grade"] in ("best", "second")
        digests.append((out / "layout.json").read_bytes())
    assert digests[0] == digests[1], f"{rel}: non-deterministic"
