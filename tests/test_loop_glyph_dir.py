#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loop label glyph + pill text (annotation layer, P1 acceptance rework A1 / A2).

A1  The direction glyph follows the loop's circulation AS DRAWN, never the
    R/B kind.  The expected direction is re-derived here with the acceptance
    reviewer's independent reading (never ``annotations.loop_circulation``):
      * >= 3 members: shoelace area of the member-centre polygon walked in
        member order; > 0 = clockwise on screen.  Collinear centres (zero
        area) are read from the delivered ring (the member routes
        concatenated in loop order).
      * 2 members: side = cross(d_centres, apex(a->b) - apex(b->a)), the
        Q-arc apex = 0.25*p0 + 0.5*ctrl + 0.25*p1 (a polyline: its
        midpoint); side < 0 = clockwise.
    The glyph is read back from the shipped SVG (arc sweep flag, 1 =
    clockwise).  Covers the 8 golden figures and the lens-chain target
    figure with its delay variant.
A2  The pill's content (icon + text) is centred as ONE block: three equal
    gaps -- pill left edge -> head tip, arc outer stroke -> text ink, text
    ink -> pill right edge.  The text is placed by a frozen calibration table
    of the rendering font (never a font read) with a start anchor, so the
    block's left and right gaps differ by the calibration error only.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw import annotations as ann
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw.render import DEFAULT_STATIC_THEME, _get_theme

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden")
TARGET = os.path.join(ROOT, "tests", "data", "limits-to-growth-4n.cld")
TARGET_DELAY = os.path.join(ROOT, "tests", "data", "limits-to-growth-4n-delay.cld")
FIGURES = sorted(
    os.path.join(GOLDEN, f) for f in os.listdir(GOLDEN) if f.endswith(".cld")
) + [TARGET, TARGET_DELAY]

_T = _get_theme(DEFAULT_STATIC_THEME)
_SWEEP = re.compile(r'<g transform="translate\([^"]*\)"><path d="M [^"]*? '
                    r'A [\d.]+ [\d.]+ \d+ [01] ([01]) ')
_TEXT_X = re.compile(r'<text x="(-?[\d.]+)" y="0" text-anchor="start"')
_GLYPH_GX = re.compile(r'<g transform="translate\((-?[\d.]+) 0\)"><path d="M [^"]*? A ')
_PILL_RECT = re.compile(r'<rect x="(-?[\d.]+)" y="-?\d+" width="(\d+)"')


def _shoelace(pts):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _apex(route):
    pts = route["points"]
    p0, p1 = pts[0], pts[-1]
    if route.get("arc") and route.get("ctrl") is not None:
        c = route["ctrl"]
        return (0.25 * p0[0] + 0.5 * c[0] + 0.25 * p1[0],
                0.25 * p0[1] + 0.5 * c[1] + 0.25 * p1[1])
    return ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)


def _reviewer_dir(members, nodes, routes):
    """('cw' | 'ccw' | None): the reviewer's reading of the drawn loop."""
    pts = [(nodes[v]["x"], nodes[v]["y"]) for v in members]
    if len(pts) >= 3:
        area = _shoelace(pts)
        if abs(area) > 1e-9:
            return "cw" if area > 0 else "ccw"
        ring = []
        for u, v in zip(members, members[1:] + members[:1]):
            seg = None
            r = routes.get((u, v))
            if r is not None:
                seg = [tuple(p) for p in r["points"]]
            else:
                r = routes.get((v, u))
                if r is not None:
                    seg = [tuple(p) for p in reversed(r["points"])]
            if seg is None:
                return None
            ring.extend(seg[:-1])
        area = _shoelace(ring)
        return None if abs(area) < 1.0 else ("cw" if area > 0 else "ccw")
    if len(pts) == 2:
        a, b = members
        rab, rba = routes.get((a, b)), routes.get((b, a))
        if rab is None or rba is None:
            return None
        dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        aa, ab = _apex(rab), _apex(rba)
        side = dx * (aa[1] - ab[1]) - dy * (aa[0] - ab[0])
        return None if abs(side) < 1e-9 else ("cw" if side < 0 else "ccw")
    return None


def _glyph_dir(rec):
    svg = ann.label_svg(rec, _T)
    m = _SWEEP.search(svg)
    assert m, svg
    return "cw" if m.group(1) == "1" else "ccw"


# -- A1: the golden figures + the lens-chain target ---------------------------
def test_glyph_follows_the_drawn_circulation():
    """Every loop of every golden figure and of the target figure (with its
    delay variant): the shipped glyph = the reviewer's reading of the drawn
    circulation.  The former caliber (glyph = kind: R clockwise / B
    counter-clockwise) disagreed with the drawing on 10 of these loops."""
    read = flipped = 0
    for path in FIGURES:
        with open(path, encoding="utf-8") as fh:
            g = parse(fh.read())
        v4 = layout(g)
        labels = {lb["id"]: lb for lb in v4["annotations"]["loop_labels"]}
        assert labels and all(lb["placed"] for lb in labels.values()), path
        routes = {(e["a"], e["b"]): e["route"] for e in v4["edges"]}
        for lp in g.loops:
            expected = _reviewer_dir(lp.nodes, v4["nodes"], routes)
            assert expected is not None, (path, lp.id)
            rec = labels[lp.id]
            assert rec["dir"] == expected, (path, lp.id, expected, rec["dir"])
            assert _glyph_dir(rec) == expected, (path, lp.id, expected)
            read += 1
            if path != TARGET_DELAY and rec["dir"] != (
                    "cw" if rec["kind"] == "R" else "ccw"):
                flipped += 1
    assert read == 22 and flipped >= 10, (read, flipped)


def test_target_figure_glyphs_are_clockwise():
    """The lens-chain target: the reinforcing lens flows clockwise along its
    top arc (efforts -> performance) and the balancing lens down its right
    arc -- both glyphs clockwise, as a reader of the arrows sees it."""
    with open(TARGET_DELAY, encoding="utf-8") as fh:
        v4 = layout(parse(fh.read()))
    labels = {lb["id"]: lb for lb in v4["annotations"]["loop_labels"]}
    assert {k: labels[k]["dir"] for k in labels} == {"R1": "cw", "B1": "cw"}
    assert {k: _glyph_dir(labels[k]) for k in labels} == {"R1": "cw", "B1": "cw"}


# -- A1: the reader itself ----------------------------------------------------
def _nodes(*xy):
    return {chr(97 + i): {"x": x, "y": y, "w": 60} for i, (x, y) in enumerate(xy)}


def test_circulation_member_polygon_three_or_more_nodes():
    nodes = _nodes((0, 0), (100, 0), (100, 100))
    assert ann.loop_circulation(["a", "b", "c"], nodes) == ("cw", "polygon")
    assert ann.loop_circulation(["b", "c", "a"], nodes) == ("cw", "polygon")
    assert ann.loop_circulation(["a", "c", "b"], nodes) == ("ccw", "polygon")
    assert ann.loop_circulation(["c", "b", "a"], nodes) == ("ccw", "polygon")


def test_circulation_two_node_ring_by_the_two_member_arcs():
    nodes = _nodes((0, 0), (100, 0))
    over = [(0, 0), (50, -40), (100, 0)]
    under = [(100, 0), (50, 40), (0, 0)]
    polys = {("a", "b"): over, ("b", "a"): under}
    assert ann.loop_circulation(["a", "b"], nodes, polys) == ("cw", "ring")
    # a member route stored against the loop's travel direction is read
    # reversed (the loop closes c -> a through the route stored a -> c)
    nodes3 = _nodes((0, 0), (100, 0), (200, 0))
    stored = {("a", "b"): [(0, 0), (100, 0)], ("b", "c"): [(100, 0), (200, 0)],
              ("a", "c"): [(0, 0), (0, 40), (200, 40), (200, 0)]}
    assert ann.loop_circulation(["a", "b", "c"], nodes3, stored) == ("cw", "ring")


def test_circulation_falls_back_when_the_drawing_does_not_decide():
    nodes = _nodes((0, 0), (100, 0), (200, 0))
    # two members, no delivered routes: nothing to read
    assert ann.loop_circulation(["a", "b"], nodes) == (None, "kind:no-ring")
    # both member routes on the same line: no closed ring
    flat = {("a", "b"): [(0, 0), (100, 0)], ("b", "a"): [(100, 0), (0, 0)]}
    assert ann.loop_circulation(["a", "b"], nodes, flat) == (None, "kind:no-ring")
    # a member route is missing
    half = {("a", "b"): [(0, 0), (100, -30), (200, 0)]}
    assert ann.loop_circulation(["a", "b"], nodes, half) == (None, "kind:no-ring")
    # collinear centres: the member polygon has no area, the ring decides
    ring = {("a", "b"): [(0, 0), (100, -30), (200, 0)],
            ("b", "a"): [(200, 0), (100, 30), (0, 0)]}
    assert ann.loop_circulation(["a", "b"], nodes, ring) == ("cw", "ring")
    three = dict(ring)
    three[("b", "c")] = [(200, 0), (200, 100)]
    three[("c", "a")] = [(200, 100), (0, 100), (0, 0)]
    assert ann.loop_circulation(["a", "b", "c"], nodes, three) == ("cw", "ring")
    # no ring at all for a collinear three-node loop
    assert ann.loop_circulation(["a", "b", "c"], nodes) == (None, "kind:collinear")


def test_circulation_two_member_loop_of_straight_lines_keeps_both_end_points():
    # quota loop of the fishing-collapse corpus graph: a mutual pair
    # delivered as two parallel straight lines 9 px apart.  Each route has
    # only its two end points; dropping the last one collapsed the ring and
    # the glyph fell back to the kind default, which pointed the wrong way.
    nodes = _nodes((106, 202), (224, 210))
    fwd = [(151.0, 197.5), (179.0, 205.5)]
    back = [(179.0, 214.5), (151.0, 206.5)]
    polys = {("a", "b"): fwd, ("b", "a"): back}
    assert ann.loop_circulation(["a", "b"], nodes, polys) == ("cw", "ring")
    # the arrows fix the circulation: listing the two members the other way
    # round reads the same ring (right along the upper line, back left)
    assert ann.loop_circulation(["b", "a"], nodes, polys) == ("cw", "ring")
    # the same two lines with no offset enclose nothing: no reading
    flat = {("a", "b"): [(151.0, 205.5), (179.0, 205.5)],
            ("b", "a"): [(179.0, 205.5), (151.0, 205.5)]}
    assert ann.loop_circulation(["a", "b"], nodes, flat) == (None, "kind:no-ring")


def test_kind_default_only_when_undetermined():
    nodes = _nodes((0, 0), (100, 0))

    def _loop(lid, kind):
        return type("L", (), {"id": lid, "label": "x", "kind": kind,
                              "nodes": ["a", "b"]})()

    recs = ann.place_loop_labels(nodes, [], [_loop("B1", "B"), _loop("R1", "R")],
                                 42, 400, 300)
    assert [(r["dir"], r["dir_source"]) for r in recs] == [
        ("ccw", "kind:no-ring"), ("cw", "kind:no-ring")]
    assert [_glyph_dir(r) for r in recs] == ["ccw", "cw"]
    # a record without the direction (older layout) keeps the same default
    assert _glyph_dir({"id": "R1", "name": "x", "kind": "B", "w": 60, "h": 18,
                       "placed": False}) == "ccw"


# -- A2: the pill's content (icon + text) is centred as one block --------------
def _pill_gaps(svg):
    """(left gap, icon-text gap, right gap) of one label's content block, from the
    delivered SVG coordinates and the calibrated text ink."""
    from stdraw.textmetrics import rendered_ink_extent
    m = _PILL_RECT.search(svg)
    px0, w = float(m.group(1)), float(m.group(2))
    gx = float(_GLYPH_GX.search(svg).group(1))
    tx = float(_TEXT_X.search(svg).group(1))
    # the shipped markup: <tspan font-weight="700">id</tspan> <tspan>name</tspan>
    # (a literal space text node between the two spans)
    runs = [(t, True) for t in re.findall(r'<tspan font-weight="700"[^>]*>([^<]*)</tspan>', svg)]
    runs += [(" " + t, False) for t in re.findall(r' <tspan>([^<]*)</tspan>', svg)]
    tl, tr = rendered_ink_extent(runs, ann.LABEL_FS)
    return ((gx + ann.GLYPH_INK_LEFT) - px0,
            (tx + tl) - (gx + ann.GLYPH_INK_RIGHT),
            (px0 + w) - (tx + tr))


def test_glyph_ink_constants_match_the_shipped_paths():
    for cw in (True, False):
        arc, head = ann.dir_glyph_paths(ann.GLYPH_R, cw)
        toks = head.replace("M", "").replace("L", "").replace("Z", "").split()
        xs = [float(toks[i]) for i in range(0, len(toks), 2)]
        assert abs(min(xs) - ann.GLYPH_INK_LEFT) < 1e-9          # the head tip
        radius = float(arc.split("A ")[1].split()[0])
        assert abs(radius + 0.65 - ann.GLYPH_INK_RIGHT) < 1e-9    # arc + half stroke


@pytest.mark.parametrize("lid,name", [("R1", "Growth"), ("B1", "Limit"),
                                      ("R12", ""), ("B2", "Balancing loop"),
                                      ("R1", "\u519b\u5907\u5347\u7ea7")])
def test_pill_content_block_is_centred(lid, name):
    w, h = ann.label_size(lid, name)
    rec = {"id": lid, "name": name, "kind": lid[0], "w": w, "h": h,
           "placed": True, "x": 100, "y": 100, "dir": "cw"}
    svg = ann.label_svg(rec, _T)
    assert 'text-anchor="start"' in svg
    left, mid, right = _pill_gaps(svg)
    # three equal gaps (two decimals in the delivered coordinates)
    assert abs(left - right) <= 0.02 and abs(mid - left) <= 0.02, (left, mid, right)
    # every gap keeps at least the design padding: label_size's analytic width
    # is an upper bound of the calibrated rendered width for these labels
    assert min(left, mid, right) >= ann.LABEL_PAD_X, (left, mid, right)


def test_pill_content_block_is_centred_in_the_delivered_html():
    """The same three gaps on every label of a rendered figure: the static export
    and the interactive layer share label_svg, so one reading covers both."""
    from stdraw.render import render_auto_html
    g = parse(open(TARGET, encoding="utf-8").read())
    html = render_auto_html(layout(g), "target")
    blocks = html.split('<g class="stdraw-looplabel"')[1:]
    assert len(blocks) == 2
    for b in blocks:
        left, mid, right = _pill_gaps(b.split("</text></g>")[0])
        assert abs(left - right) <= 0.02 and abs(mid - left) <= 0.02, (left, mid, right)


def test_label_svg_never_reads_a_measuring_font(monkeypatch):
    """The pill geometry must not depend on the fonts of the generating machine."""
    from stdraw import textmetrics

    def _boom(px):
        raise AssertionError("label_svg must not read a measuring font")
    monkeypatch.setattr(textmetrics, "_load_font", _boom)
    w, h = ann.label_size("R1", "\u519b\u5907\u5347\u7ea7")
    rec = {"id": "R1", "name": "\u519b\u5907\u5347\u7ea7", "kind": "R", "w": w, "h": h,
           "placed": True, "x": 100, "y": 100, "dir": "ccw"}
    left, mid, right = _pill_gaps(ann.label_svg(rec, _T))
    assert abs(left - right) <= 0.02 and abs(mid - left) <= 0.02


def test_calibration_table_matches_browser_measurements():
    from stdraw import textmetrics as tm
    assert len(tm._CAL["regular"]) == 95 and len(tm._CAL["bold"]) == 95
    # tabular digits: one advance per weight
    assert len({tm._CAL["regular"][d][0] for d in "0123456789"}) == 1
    assert len({tm._CAL["bold"][d][0] for d in "0123456789"}) == 1
    # text ink widths of delivered golden labels as measured in Edge headless
    # (device scale 2, canvas ink bounds + tspan boxes) by the acceptance
    # review: within the half-pixel CJK edge rule plus rounding
    for lid, name, measured in (("R1", "\u519b\u5907\u5347\u7ea7", 62.724),
                                ("B1", "Limit", 44.368),
                                ("R1", "Growth", 56.725)):
        l, r = tm.rendered_ink_extent([(lid, True), (" " + name, False)], 11.0)
        assert abs((r - l) - measured) <= 0.6, (lid, name, r - l, measured)
