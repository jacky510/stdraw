#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""@delay DSL + annotation layer (loop labels, delay marks).

Coverage:
  1. DSL: @delay parses on an edge line in either order with @loops, the
     canonical dump order, parse(dumps(g)) == g, malformed tokens rejected;
  2. graph JSON: the delay key is written only when set and round-trips;
  3. layout(): layout.json carries annotations.loop_labels (placed, clear
     of cards and lines) and per-edge delay; a figure without declared
     loops carries no annotation key at all (byte-neutral);
  4. gates: loop_labels_clear / delay_marks_clear on delivered
     coordinates, the mark is two perpendicular ticks at the arc-length
     midpoint, a mark touching a card fails the gate;
  5. CLI end-to-end on the delayed fixture: grade best, geometry fail=0,
     the demo carries the label pills, the delay ticks and the toggle.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import annotations as ann
from stdraw.check import geometry_report
from stdraw.dsl import dumps, parse
from stdraw.layout_auto import layout
from stdraw.model import Graph

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LTG4D = os.path.join(HERE, "data", "limits-to-growth-4n-delay.cld")
NO_LOOP = 'graph "p"\nvar a "A"\nvar b "B"\na -> + b\n'

DSL = ('graph "d"\nvar a "A"\nvar b "B"\nvar c "C"\nvar x "X"\n'
       'a -> + b @loops R1 @delay\nb -> + c @delay\nc -> - a @loops R1\n'
       'x -> + a @delay @loops R1\nloop R1 "g" "R" [a, b, c]\n')


def test_delay_dsl_roundtrip():
    g = parse(DSL)
    assert [e.delay for e in g.edges] == [True, True, False, True]
    text = dumps(g)
    assert "@loops R1 @delay" in text and "@delay @loops" not in text
    assert parse(text) == g
    assert "@delay" not in dumps(parse(NO_LOOP))


def test_delay_dsl_rejects_malformed():
    head = 'graph "d"\nvar a "A"\nvar b "B"\n'
    for tail in ("a -> + b @delayy\n", "a -> + b @delay @delay\n",
                 "a -> + b @delay extra\n"):
        with pytest.raises(Exception) as ei:
            parse(head + tail)
        assert "DSL" in str(ei.value), tail


def test_graph_json_delay_key_only_when_set():
    g = parse(DSL)
    d = g.to_dict()
    assert [e.get("delay") for e in d["edges"]] == [True, True, None, True]
    assert Graph.from_dict(json.loads(json.dumps(d))) == g
    d0 = parse(NO_LOOP).to_dict()
    assert all("delay" not in e for e in d0["edges"])


def test_layout_annotations_and_delay_keys():
    with open(LTG4D, encoding="utf-8") as fh:
        g = parse(fh.read())
    v4 = layout(g)
    labels = v4["annotations"]["loop_labels"]
    assert [lb["id"] for lb in labels] == ["R1", "B1"]
    assert all(lb["placed"] for lb in labels)
    assert [e.get("delay", False) for e in v4["edges"]] == [False, True, False, True, False]
    v0 = layout(parse(NO_LOOP))
    assert "annotations" not in v0
    assert all("delay" not in e for e in v0["edges"])


def test_delay_mark_is_two_perpendicular_ticks_at_the_midpoint():
    marks = ann.delay_mark([(0.0, 0.0), (10.0, 0.0)])
    assert len(marks) == 2
    xs = sorted({round(m[0], 3) for m in marks})
    assert xs == [3.0, 7.0]                      # midpoint 5, +/- DELAY_TICK_GAP
    for x1, y1, x2, y2 in marks:
        assert x1 == x2 and round(abs(y2 - y1), 3) == 2 * ann.DELAY_TICK_HALF
    assert ann.delay_mark([(5.0, 5.0), (5.0, 5.0)]) is None   # degenerate route
    assert ann.delay_mark_d([(0.0, 0.0), (10.0, 0.0)]) == (
        "M 3.0 -5.0 L 3.0 5.0 M 7.0 -5.0 L 7.0 5.0")


def test_delay_gate_clearance_from_every_box():
    card_h = 44
    nodes = {"a": {"x": 30, "y": 22, "w": 60}, "b": {"x": 330, "y": 22, "w": 60}}
    poly = [(60.0, 22.0), (300.0, 22.0)]
    ok, problems, dist = ann.delays_clear(nodes, [poly], [0], ["a->b"], card_h)
    assert ok and problems == [] and dist is not None and dist >= 16
    blocked = dict(nodes, c={"x": 180, "y": 22, "w": 24})   # a box sitting on the line
    ok2, problems2, dist2 = ann.delays_clear(blocked, [poly], [0], ["a->b"], card_h)
    assert not ok2 and dist2 < 16 and any("box c" in p for p in problems2)
    assert ann.delays_clear(nodes, [poly], [], ["a->b"], card_h) == (True, [], None)


def test_label_size_is_font_independent(monkeypatch):
    # the pill width must not depend on the measuring font: a fontless checkout
    # (Linux CI) and a machine with the font (Windows) must deliver identical bytes
    import stdraw.textmetrics as tm
    monkeypatch.setattr(tm, "_load_font", lambda px: None)
    tm._cache.clear()
    want = ann.label_size("R1", "Growth loop")
    monkeypatch.undo()
    tm._cache.clear()
    assert ann.label_size("R1", "Growth loop") == want
    # and it equals the documented analytic rule (CJK 1.10 fs / others 0.62 fs, x1.06)
    fs = ann.LABEL_FS
    exp = (ann.LABEL_PAD_X + ann.GLYPH_BOX + ann.GLYPH_GAP
           + math.ceil((2 * 0.62 * fs + 12 * 0.62 * fs) * 1.06) + ann.LABEL_PAD_X, ann.LABEL_H)
    assert want == exp


def test_label_gate_clearance():
    card_h, W, H = 44, 720, 424
    nodes = {"a": {"x": 60, "y": 22, "w": 80}, "b": {"x": 660, "y": 22, "w": 80}}
    polys = [[(100.0, 22.0), (620.0, 22.0)]]
    free = {"id": "R1", "name": "g", "kind": "R", "w": 80, "h": 18, "placed": True,
            "x": 360, "y": 200}
    ok, problems = ann.labels_clear(nodes, polys, [free], card_h, W, H)
    assert ok and problems == []
    on_line = dict(free, y=22)                       # pill on top of the line
    ok2, problems2 = ann.labels_clear(nodes, polys, [on_line], card_h, W, H)
    assert not ok2 and problems2 == ["R1"]
    on_card = dict(free, x=60, y=22)                 # pill on top of a card
    ok3, problems3 = ann.labels_clear(nodes, polys, [on_card], card_h, W, H)
    assert not ok3 and problems3 == ["R1"]
    unplaced = dict(free, placed=False)
    assert ann.labels_clear(nodes, polys, [unplaced], card_h, W, H) == (True, [])


def test_unplaced_label_is_hidden_in_the_static_export():
    from stdraw import themes
    T = themes.LIGHT
    # the pipeline's real record for a label without a slot: x / y are None
    rec = {"id": "R1", "name": "g", "kind": "R", "w": 80, "h": 18,
           "placed": False, "x": None, "y": None, "offset": None}
    svg = ann.label_svg(rec, T)
    assert 'display="none"' in svg and 'transform="translate(0 0)"' in svg
    assert 'data-loop="R1"' in svg
    assert 'display="none"' not in ann.label_svg(dict(rec, placed=True, x=200, y=120), T)


def test_label_placement_prefers_a_comfortable_slot():
    # centroid slot keeps 7px from the line (gate floor 4 < 7 < target 8):
    # the label must move out to the nearest slot with >= 8px clearance
    card_h, W, H = 44, 600, 400
    nodes = {"a": {"x": 200, "y": 100, "w": 80}, "b": {"x": 200, "y": 300, "w": 80}}
    polys = [[(0.0, 216.0), (600.0, 216.0)]]
    loops = [{"id": "R1", "label": "g", "nodes": ["a", "b"], "kind": "R"}]
    [lb] = ann.place_loop_labels(nodes, polys, loops, card_h, W, H)
    assert lb["placed"] and (lb["x"], lb["y"]) == (200, 188) and lb["offset"] == 12.0
    assert ann.labels_clear(nodes, polys, [lb], card_h, W, H) == (True, [])
    assert ann.label_rect_clear(200, 200, lb["w"], lb["h"], nodes, polys, [], W, H,
                                card_h, box_gap=ann.LABEL_BOX_GAP)
    assert not ann.label_rect_clear(200, 200, lb["w"], lb["h"], nodes, polys, [], W, H,
                                    card_h, box_gap=ann.LABEL_TARGET_GAP)
    # when nothing near reaches the target the gate floor still places it
    polys_floor = [[(0.0, 209.0), (600.0, 209.0)], [(0.0, 191.0), (600.0, 191.0)]]
    [lb2] = ann.place_loop_labels(nodes, polys_floor, loops, card_h, W, H)
    assert lb2["placed"] and lb2["offset"] > 0
    assert ann.labels_clear(nodes, polys_floor, [lb2], card_h, W, H) == (True, [])


def test_label_candidate_stages_and_far_ring():
    # JS Math.round caliber: ties go up, so the replay picks the same slot
    assert (ann._rint(210.5), ann._rint(-2.5), ann._rint(0.4999), ann._rint(2.5)) == (211, -2, 0, 3)
    stages = list(ann._staged_candidates(300.0, 200.0))
    near_n = len(list(ann._ring(300.0, 200.0, ann.LABEL_RADII, ann.LABEL_DIRS)))
    far_n = len(list(ann._ring(300.0, 200.0, ann.LABEL_RADII_FAR, ann.LABEL_DIRS_FAR)))
    assert near_n == 1 + (len(ann.LABEL_RADII) - 1) * ann.LABEL_DIRS
    assert far_n == len(ann.LABEL_RADII_FAR) * ann.LABEL_DIRS_FAR
    assert [s[2] for s in stages] == ([ann.LABEL_TARGET_GAP] * near_n +
                                      [ann.LABEL_BOX_GAP] * near_n +
                                      [ann.LABEL_TARGET_GAP] * far_n +
                                      [ann.LABEL_BOX_GAP] * far_n)
    assert stages[0][:2] == (300, 200)
    near_pos = set((s[0], s[1]) for s in stages[:near_n])
    far_pos = set((s[0], s[1]) for s in stages[2 * near_n:2 * near_n + far_n])
    assert len(near_pos) == near_n and len(far_pos) == far_n and not (near_pos & far_pos)
    # a drawing whose near field is full falls through to the far ring
    card_h, W, H = 44, 600, 400
    nodes = {"a": {"x": 300, "y": 60, "w": 80}, "b": {"x": 300, "y": 340, "w": 80}}
    polys = [[(0.0, 200.0), (600.0, 200.0)]]
    loops = [{"id": "R1", "label": "g", "nodes": ["a", "b"], "kind": "R"}]
    [lb] = ann.place_loop_labels(nodes, polys, loops, card_h, W, H)
    assert lb["placed"] and lb["offset"] < ann.LABEL_RADII_FAR[0]
    saved = ann.LABEL_RADII
    try:
        ann.LABEL_RADII = (0, 12)
        [lb2] = ann.place_loop_labels(nodes, polys, loops, card_h, W, H)
    finally:
        ann.LABEL_RADII = saved
    assert lb2["placed"] and lb2["offset"] >= ann.LABEL_RADII_FAR[0] - 2
    assert ann.labels_clear(nodes, polys, [lb2], card_h, W, H) == (True, [])


def test_induced_demand_four_labels_all_placed():
    # regression: a classic whose two labels had no near slot used to crash
    # the static export (None coordinates formatted into the transform)
    src = os.path.join(ROOT, "benchmarks", "corpus", "classic", "induced-demand.cld")
    with open(src, encoding="utf-8") as fh:
        g = parse(fh.read())
    L = layout(g)
    labels = L["annotations"]["loop_labels"]
    assert [lb["id"] for lb in labels] == ["B1", "R1", "B2", "R3"]
    assert all(lb["placed"] for lb in labels)
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run([sys.executable, "-m", "stdraw", "layout", src,
                               "--outdir", tmp], cwd=ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-800:]
        with open(os.path.join(tmp, "demo-2d.html"), encoding="utf-8") as fh:
            html = fh.read()
        assert html.count('class="stdraw-looplabel"') == 4
        assert 'display="none"' not in "".join(
            m for m in html.split("<g class=\"stdraw-looplabel\"")[1:])
        with open(os.path.join(tmp, "certificate.json"), encoding="utf-8") as fh:
            cert = json.load(fh)
    assert cert["grade"] == "best" and cert["gates"]["loop_labels_clear"] is True
    assert cert["metrics"]["loop_labels_unplaced"] == 0


def test_cli_delayed_fixture_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run([sys.executable, "-m", "stdraw", "layout", LTG4D,
                               "--outdir", tmp], cwd=ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-800:]
        with open(os.path.join(tmp, "certificate.json"), encoding="utf-8") as fh:
            cert = json.load(fh)
        with open(os.path.join(tmp, "geometry_report.json"), encoding="utf-8") as fh:
            geo = json.load(fh)
        with open(os.path.join(tmp, "layout.json"), encoding="utf-8") as fh:
            lay = json.load(fh)
        assert cert["grade"] == "best", cert["gates"]
        assert cert["gates"]["loop_labels_clear"] is True
        assert cert["gates"]["delay_marks_clear"] is True
        assert cert["metrics"]["loop_labels_unplaced"] == 0
        assert cert["metrics"]["delay_mark_count"] == 2
        assert geo["summary"]["fail"] == 0
        texts = " | ".join(c.get("check", "") for c in geo["checks"])
        assert "label" in texts and "delay" in texts
        assert [lb["id"] for lb in lay["annotations"]["loop_labels"]] == ["R1", "B1"]
        with open(os.path.join(tmp, "demo-2d.html"), encoding="utf-8") as fh:
            html = fh.read()
        assert html.count('class="stdraw-delay"') == 2
        assert html.count('class="stdraw-looplabel"') == 2
        # Default CLI page is static (no toolbar): the annotation elements
        # themselves are static SVG and must still be present; the toolbar
        # Loops toggle ships with the --interactive opt-in only.
        assert "stdraw-toolbar" not in html
        proc2 = subprocess.run([sys.executable, "-m", "stdraw", "layout", LTG4D,
                                "--outdir", os.path.join(tmp, "interactive"),
                                "--interactive"], cwd=ROOT,
                               capture_output=True, text=True)
        assert proc2.returncode == 0, proc2.stderr[-800:]
        with open(os.path.join(tmp, "interactive", "demo-2d.html"),
                  encoding="utf-8") as fh:
            html2 = fh.read()
        assert "stdraw-loops-toggle" in html2
