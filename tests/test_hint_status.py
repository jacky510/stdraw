# -*- coding: utf-8 -*-
"""T14 hint delivered-status (0.10.1): the certificate ``hints.status`` block.

The record used to list the DECLARED hints only — a hint the engine read but
that never moved the delivered drawing (``@pair rate,adopters`` on
limits-to-growth, ``@main R1`` on a template placement) read exactly like one
that did. This module pins the fix:

  * every declaration carries ``status`` = applied | unapplied and, when
    unapplied, a reason code (cross-row / mode-not-eligible /
    no-effect-measured);
  * the status is MEASURED by ablation on the delivered artifacts — re-run
    the same delivery with exactly one declaration removed and diff node
    centers + route points (@main / @pair) or the delivered loop-label
    sequence (@order, whose effect IS the reading order). It is never
    asserted from "the engine reads this field";
  * a hints-free graph keeps its certificate bytes byte-for-byte (the block
    only exists when hints are declared);
  * a certificate built outside the delivery path honestly reports
    ``unmeasured`` / ``measurement-not-run`` instead of a fabricated status.
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.dsl import parse                        # noqa: E402
from stdraw.hints import (APPLIED, UNAPPLIED, UNMEASURED,  # noqa: E402
                          REASON_CROSS_ROW, REASON_MODE_NOT_ELIGIBLE,
                          REASON_NO_EFFECT, REASON_NOT_MEASURED, hint_entries,
                          measure_status, status_block, without_entry)
from stdraw.layout_auto import AutoConfig, layout   # noqa: E402
from stdraw.metrics import certificate_auto, scene_from_auto  # noqa: E402

PY = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── fixtures ──

# Column-chain template placement (no hint consumer): a declared hint here
# must measure unapplied, NOT "applied because cfg got the field".
COLUMN_TXT = """\
graph "hint-status-column"
var rate "Rate"
var adopters "Adopters"
var word "Word"
var potential "Potential"
var crowding "Crowding"
adopters -> + word @loops R1
word -> + rate @loops R1
rate -> + adopters @loops R1,B1
potential -> + rate @loops B1
adopters -> - potential @loops B1
crowding -> - rate @loops B2
adopters -> + crowding @loops B2
loop R1 "adoption" "R" [rate, adopters, word]
loop B1 "saturation" "B" [rate, adopters, potential]
loop B2 "crowding" "B" [rate, adopters, crowding]
"""

# Ring template placement: @pair rotates the ring into consecutive slots
# (ringlayout T14 branch) — a real delivered-geometry effect.
RING_TXT = """graph "hint-status-ring"
var gain "Gain"
var usage "Usage"
var total "Total"
var resource "Resource"
gain -> + usage @loops R1,B2,B3
usage -> + gain @loops R1
usage -> + total @loops B2,B3
total -> - gain @loops B2
total -> - resource @loops B3
resource -> + gain @loops B3
loop R1 "worse over time" "R" [usage, gain]
loop B2 "gain dilution" "B" [usage, total, gain]
loop B3 "resource depletion" "B" [usage, total, resource, gain]
"""

# Layered (cp-sat placement objective) graph: @main adds the centering term
# and moves the delivered nodes; @pair e,f is cross-row there.
LAYERED_TXT = """\
graph "hint-status-layered"
var a "A"
var b "B"
var c "C"
var d "D"
var e "E"
var f "F"
var g "G"
var h "H"
a -> + b @loops R1
b -> + c @loops R1
c -> + d @loops R1
d -> + a @loops R1
c -> + e
e -> + f
f -> + g
g -> + h
h -> - e
loop R1 "cycle" "R" [a, b, c, d]
"""


def _deliver(txt, hints=None):
    g = parse(txt)
    if hints is not None:
        g.hints = hints
    return g, layout(g, AutoConfig())


def _measured(txt, hints):
    """Deliver once, then measure every declared hint by ablation."""
    from stdraw.model import Hints  # noqa: F401  (documents the intent)
    pristine = parse(txt)
    pristine.hints = hints
    g, v4 = _deliver(txt, hints)
    status = measure_status(pristine, v4,
                            lambda alt: layout(alt, AutoConfig()))
    return g, v4, status


# ── per-hint status: the three acceptance cases ──

def test_cross_row_pair_unapplied_with_reason():
    """@pair rate,adopters on the column template: the two variables are
    delivered on different rows, so the pair cannot be adjacent."""
    from stdraw.model import Hints
    _, v4, status = _measured(COLUMN_TXT, Hints(pairs=[("rate", "adopters")]))
    rec = status["pairs"][0]
    assert rec["pair"] == ["rate", "adopters"]
    assert rec["status"] == UNAPPLIED
    assert rec["reason"] == REASON_CROSS_ROW
    assert v4["nodes"]["rate"]["y"] != v4["nodes"]["adopters"]["y"]


def test_pair_applied_when_the_ring_rotates():
    """@pair on a ring placement rotates the delivered ring — the ablation
    sees different node centers, so the status is applied."""
    from stdraw.model import Hints
    _, _, status = _measured(RING_TXT, Hints(pairs=[("gain", "total")]))
    rec = status["pairs"][0]
    assert rec["status"] == APPLIED
    assert "reason" not in rec


def test_main_applied_on_layered_placement():
    """@main on the cp-sat layered path adds the centering term and moves the
    delivered nodes — applied, measured on the delivered coordinates."""
    from stdraw.model import Hints
    _, v4, status = _measured(LAYERED_TXT, Hints(main=["R1"]))
    assert v4["meta"]["position_engine"] == "cp-sat"
    rec = status["main"][0]
    assert rec["loop"] == "R1"
    assert rec["status"] == APPLIED


def test_main_unapplied_and_mode_not_eligible_on_template_placement():
    """@main on a template placement (no hint consumer) is unapplied with
    mode-not-eligible — never 'applied' just because the field was read."""
    from stdraw.model import Hints
    _, v4, status = _measured(COLUMN_TXT, Hints(main=["R1"]))
    assert v4["meta"]["position_engine"] not in ("cp-sat", "construct",
                                                 "ring-construct")
    rec = status["main"][0]
    assert rec["status"] == UNAPPLIED
    assert rec["reason"] == REASON_MODE_NOT_ELIGIBLE


def test_order_status_measured_on_the_delivered_loop_sequence():
    """@order declares a reading order, not a geometry: its delivered
    observable is the loop-label sequence in layout.json. Reordering the
    sequence measures applied even though node coordinates do not move."""
    from stdraw.model import Hints
    pristine = parse(COLUMN_TXT)
    pristine.hints = Hints(order=["B1", "R1", "B2"])
    g, v4 = _deliver(COLUMN_TXT, pristine.hints)
    ablated = layout(without_entry(pristine, "order", None), AutoConfig())
    # geometry (node centers + routes) is IDENTICAL -- the honest diff line
    assert [v4["nodes"][k] for k in sorted(v4["nodes"])] == \
        [ablated["nodes"][k] for k in sorted(ablated["nodes"])]
    assert [e["route"] for e in v4["edges"]] == [e["route"] for e in ablated["edges"]]
    status = measure_status(pristine, v4,
                            lambda alt: layout(alt, AutoConfig()))
    rec = status["order"]
    assert rec["ids"] == ["B1", "R1", "B2"]
    assert rec["status"] == APPLIED


def test_status_is_not_self_certified_by_the_declaration():
    """The status must come from the delivery, not from the hint object: an
    empty declaration set yields no status block at all."""
    from stdraw.model import Hints
    g = parse(COLUMN_TXT)
    v4 = layout(g, AutoConfig())
    assert hint_entries(g) == []
    assert measure_status(g, v4, lambda alt: layout(alt, AutoConfig())) == {}
    cert = certificate_auto(scene_from_auto(v4), graph_name="x", graph=g,
                            deliverable=True)
    assert "hints" not in cert


# ── certificate wiring ──

def test_certificate_carries_the_measured_status_block():
    from stdraw.model import Hints
    g, v4, status = _measured(COLUMN_TXT, Hints(main=["R1"],
                                                order=["B1", "R1", "B2"],
                                                pairs=[("rate", "adopters")]))
    cert = certificate_auto(scene_from_auto(v4), graph_name="x", graph=g,
                            deliverable=True, hint_status=status)
    blk = cert["hints"]["status"]
    assert blk["main"][0]["status"] == UNAPPLIED
    assert blk["main"][0]["reason"] == REASON_MODE_NOT_ELIGIBLE
    assert blk["order"]["status"] == APPLIED
    assert blk["pairs"][0]["status"] == UNAPPLIED
    assert blk["pairs"][0]["reason"] == REASON_CROSS_ROW
    assert blk["measurement"]["method"] == "delivery-ablation"
    assert blk["measurement"]["ablation_runs"] == 3
    assert blk["measurement"]["applied"] == 1
    assert blk["measurement"]["unapplied"] == 2


def test_certificate_without_measurement_is_honestly_unmeasured():
    from stdraw.model import Hints
    g = parse(COLUMN_TXT)
    g.hints = Hints(main=["R1"], pairs=[("rate", "adopters")])
    v4 = layout(g, AutoConfig())
    cert = certificate_auto(scene_from_auto(v4), graph_name="x", graph=g,
                            deliverable=True)
    blk = cert["hints"]["status"]
    assert blk["main"][0]["status"] == UNMEASURED
    assert blk["main"][0]["reason"] == REASON_NOT_MEASURED
    assert blk["pairs"][0]["status"] == UNMEASURED
    assert blk["measurement"]["method"] == "none"


def test_status_block_flattens_every_declaration():
    from stdraw.model import Hints
    g = parse(COLUMN_TXT)
    g.hints = Hints(main=["R1", "B1"], order=["B1", "R1", "B2"],
                    pairs=[("rate", "adopters"), ("word", "potential")])
    blk = status_block(g)
    assert [r["loop"] for r in blk["main"]] == ["R1", "B1"]
    assert [r["pair"] for r in blk["pairs"]] == [["rate", "adopters"],
                                                 ["word", "potential"]]
    assert blk["order"]["ids"] == ["B1", "R1", "B2"]


# ── CLI: bytes + determinism ──

def _run_cli(path, outdir, extra=()):
    return subprocess.run(
        [PY, "-m", "stdraw", "layout", path, "--outdir", outdir, *extra],
        capture_output=True, text=True, cwd=ROOT)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_cli_hinted_delivery_is_deterministic_and_reports_status(tmp_path):
    src = tmp_path / "hinted.cld"
    src.write_text(LAYERED_TXT + "\n@main R1\n@pair e,f\n", encoding="utf-8")
    a, b = tmp_path / "a", tmp_path / "b"
    ra = _run_cli(str(src), str(a))
    rb = _run_cli(str(src), str(b))
    assert ra.returncode == 0 and rb.returncode == 0, (ra.stderr, rb.stderr)
    # double run: same input -> byte-identical delivered artifacts
    assert _sha(str(a / "layout.json")) == _sha(str(b / "layout.json"))
    assert _sha(str(a / "certificate.json")) == _sha(str(b / "certificate.json"))
    cert = json.loads((a / "certificate.json").read_text(encoding="utf-8"))
    blk = cert["hints"]["status"]
    assert blk["main"][0]["status"] == APPLIED
    assert blk["pairs"][0]["status"] == UNAPPLIED
    # the CLI transcript names the measured statuses
    assert "[hints]" in ra.stdout and "applied" in ra.stdout


def test_cli_hints_free_certificate_has_no_status_block(tmp_path):
    """The hints block only exists when hints are declared: a hints-free graph
    keeps its certificate bytes (the golden gate pins the same fact)."""
    src = tmp_path / "plain.cld"
    src.write_text(LAYERED_TXT, encoding="utf-8")
    r = _run_cli(str(src), str(tmp_path / "out"))
    assert r.returncode == 0, r.stderr
    cert = json.loads((tmp_path / "out" / "certificate.json")
                      .read_text(encoding="utf-8"))
    assert "hints" not in cert
    assert "[hints]" not in r.stdout


def test_without_entry_removes_exactly_one_declaration():
    from stdraw.model import Hints
    g = parse(COLUMN_TXT)
    g.hints = Hints(main=["R1"], order=["B1", "R1", "B2"],
                    pairs=[("rate", "adopters")])
    only = without_entry(g, "pairs", ("rate", "adopters"))
    assert only.hints.pairs == []
    assert only.hints.main == ["R1"] and len(only.hints.order) == 3
    assert g.hints.pairs == [("rate", "adopters")]   # input not mutated
    no_main = without_entry(g, "main", "R1")
    assert no_main.hints.main == [] and len(no_main.hints.pairs) == 1
