# -*- coding: utf-8 -*-
"""Drawing annotations that ride on the delivered geometry.

Single source for three consumers: the layout pipeline (positions are
computed once and shipped in layout.json under ``annotations``), the static
export + interactive layer (draw / re-place), and the two verification
channels (check.py geometry report, metrics certificate) which both re-read
the shipped positions and test them against the delivered boxes and lines.

delay marks (@delay links)
    Two short perpendicular ticks at the arc-length midpoint of the route.
    Gated on delivered coordinates: >= 16px from every box (its own
    endpoints included), crossing no other line and no other mark.

loop labels
    ``R1``/``B1`` id + loop name + a direction glyph at the loop's visual
    center (the centroid of its member nodes), nudged onto the first
    collision-free slot around that center.  Polarity keeps its two-color
    encoding: the glyph takes the loop kind's own ink (R = reinforcing,
    vermilion / B = balancing, blue); no ``+``/``-`` sign is ever drawn.
    The glyph's arrow follows the loop's circulation AS DRAWN (loop_circulation:
    the signed area of the member route on screen), never the R/B kind -- a
    reinforcing loop may run either way on the page.  The text is centred
    between the glyph and the pill's right edge.  A loop for which no
    collision-free slot exists inside the viewBox is reported unplaced --
    never drawn on top of a box or a line.
"""
import math

from .metrics import rect_gap, seg_hits_rect

# ── delay marks ──
DELAY_TICK_HALF = 5.0     # each tick spans +/- 5px perpendicular to the line
DELAY_TICK_GAP = 2.0      # the two ticks sit +/- 2px from the arc-length midpoint

# ── loop labels ──
LABEL_FS = 11.0           # label font size (px)
LABEL_H = 18              # label pill height
LABEL_PAD_X = 7           # pill side padding
GLYPH_BOX = 12            # direction glyph box (px square)
GLYPH_R = 4.2             # direction glyph arc radius (= the glyph's ink half-width)
GLYPH_GAP = 5             # slack kept between the glyph and the text slot
LABEL_BOX_GAP = 4.0       # a label keeps >= 4px from every card and every line (gate)
LABEL_TARGET_GAP = 8.0    # ... placement first tries >= 8px, the gate gap is the floor
LABEL_LABEL_GAP = 8.0     # ... and >= 8px from every other label
LABEL_EDGE = 4.0          # ... and stays >= 4px inside the viewBox
# candidate slots: concentric rings around the loop centroid, nearest first
LABEL_RADII = (0, 12, 20, 28, 36, 44, 52, 64, 80, 96, 112, 128, 144, 160)
LABEL_DIRS = 12
LABEL_RADII_FAR = (168, 176, 184, 192, 200, 212, 224, 240, 256)
LABEL_DIRS_FAR = 24


# ═══════════════════════════ delay marks ═══════════════════════════

def midpoint_tangent(pts):
    """Arc-length midpoint of a polyline + the unit tangent there.
    Returns (mx, my, tx, ty), or None for a degenerate polyline."""
    segs = []
    total = 0.0
    for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
        d = math.hypot(x2 - x1, y2 - y1)
        if d > 1e-9:
            segs.append(((x1, y1), (x2, y2), d))
            total += d
    if not segs:
        return None
    half = total / 2.0
    acc = 0.0
    for (x1, y1), (x2, y2), d in segs:
        if acc + d >= half - 1e-12:
            t = (half - acc) / d
            return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t,
                    (x2 - x1) / d, (y2 - y1) / d)
        acc += d
    (x1, y1), (x2, y2), d = segs[-1]
    return (x2, y2, (x2 - x1) / d, (y2 - y1) / d)


def delay_mark(points):
    """The two tick segments of a delay mark on a delivered polyline:
    [(x1, y1, x2, y2), (x1, y1, x2, y2)], or None when the route is degenerate."""
    mt = midpoint_tangent([(float(x), float(y)) for x, y in points])
    if mt is None:
        return None
    mx, my, tx, ty = mt
    nx, ny = -ty, tx
    out = []
    for s in (-DELAY_TICK_GAP, DELAY_TICK_GAP):
        cx, cy = mx + tx * s, my + ty * s
        out.append((cx - nx * DELAY_TICK_HALF, cy - ny * DELAY_TICK_HALF,
                    cx + nx * DELAY_TICK_HALF, cy + ny * DELAY_TICK_HALF))
    return out


def delay_mark_d(points):
    """SVG path data (M/L, 0.1px) of a delay mark -- one caliber shared by the
    static export and the interactive layer's JS port."""
    mk = delay_mark(points)
    if mk is None:
        return ""
    return " ".join("M %.1f %.1f L %.1f %.1f" % seg for seg in mk)


def _dense(seg, step=1.0):
    (x1, y1), (x2, y2) = seg
    d = math.hypot(x2 - x1, y2 - y1)
    n = max(1, int(math.ceil(d / step)))
    return [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n + 1)]


def delays_clear(nodes, polys, delayed, names, card_h):
    """Independent re-verification of delay marks on delivered coordinates:
    every tick is >= CLEARANCE (16px) from every box (its own endpoints
    included), crosses no other line and no other mark.
    ``polys`` = per-edge delivered point lists (index-aligned with
    ``names``); ``delayed`` = the indices that carry a delay; ``names[i]`` =
    the edge's display name.  Returns (ok, problems, min tick->box distance);
    (True, [], None) when no edge carries a delay."""
    from .routing import CLEARANCE, dist_point_rect, seg_cross
    if not delayed:
        return True, [], None
    polys = [[(float(x), float(y)) for x, y in polys[i]] for i in range(len(names))]
    marks = {}
    problems = []
    min_box = None
    for i in delayed:
        mk = delay_mark(polys[i])
        if mk is None:
            problems.append(f"{names[i]}: degenerate route")
            continue
        marks[i] = [[(s[0], s[1]), (s[2], s[3])] for s in mk]
    for i, ticks in marks.items():
        eid = names[i]
        for t in ticks:
            for v, p in nodes.items():
                d = min(dist_point_rect(x, y, p["x"], p["y"], p["w"] / 2, card_h / 2)
                        for x, y in _dense(t))
                min_box = d if min_box is None else min(min_box, d)
                if d < CLEARANCE - 1e-6:
                    problems.append(f"{eid}: tick {d:.1f}px from box {v}")
            for j, poly in enumerate(polys):
                if j == i:
                    continue
                if any(seg_cross(t[0], t[1], q1, q2)
                       for q1, q2 in zip(poly[:-1], poly[1:])):
                    problems.append(f"{eid}: tick crosses {names[j]}")
            for i2, t2 in marks.items():
                if i2 <= i:
                    continue
                for s in t2:
                    if seg_cross(t[0], t[1], s[0], s[1]):
                        problems.append(f"{eid}: tick crosses the mark of {names[i2]}")
    return (not problems), problems, (None if min_box is None else round(min_box, 1))


def mark_svg(mk, color):
    """Static-export SVG for a delay mark (one stroked path, two ticks)."""
    d = " ".join("M %.1f %.1f L %.1f %.1f" % tuple(s) for s in mk)
    return (f'<path class="stdraw-delay" d="{d}" fill="none" stroke="{color}" '
            f'stroke-width="1.3"/>')


# ═══════════════════════════ loop labels ═══════════════════════════

def _loop_fields(lp):
    """(id, name, kind, member node ids) from a Loop object or a dict."""
    if isinstance(lp, dict):
        lid = lp.get("id")
        name = lp.get("label") or lp.get("name") or ""
        kind = (lp.get("kind") or lp.get("declared_kind") or "R").upper()
        members = list(lp.get("nodes") or [])
    else:
        lid = lp.id
        name = lp.label or ""
        kind = (lp.kind or "R").upper()
        members = list(lp.nodes)
    return lid, name, kind, members


def label_size(lid, name):
    """Pill size (w, h) of a loop label: [glyph 12] + gap + bold id + name.

    Font-independent by construction (analytic widths only): a font-measured width
    differs between a machine that has the measuring font and a fontless checkout,
    which made every labelled figure's delivered bytes platform-dependent."""
    from .textmetrics import analytic_width
    text_w = analytic_width(lid, LABEL_FS) + analytic_width(" " + name, LABEL_FS)
    w = LABEL_PAD_X + GLYPH_BOX + GLYPH_GAP + int(math.ceil(text_w)) + LABEL_PAD_X
    return w, LABEL_H


def dir_glyph_paths(r, clockwise):
    """(arc d, head d) of a small circular arrow centered on the origin.
    On screen (SVG y down) increasing angle is clockwise."""
    span = 280.0
    t1 = 140.0 if clockwise else -140.0
    t0 = t1 - span if clockwise else t1 + span
    a0, a1 = math.radians(t0), math.radians(t1)
    x0, y0 = r * math.cos(a0), r * math.sin(a0)
    x1, y1 = r * math.cos(a1), r * math.sin(a1)
    arc = "M %.1f %.1f A %.1f %.1f 0 1 %d %.1f %.1f" % (
        x0, y0, r, r, 1 if clockwise else 0, x1, y1)
    # head along the direction of travel at the arc end
    s = 1.0 if clockwise else -1.0
    tx, ty = -s * math.sin(a1), s * math.cos(a1)
    nx, ny = -ty, tx
    tip = (x1 + 3.6 * tx, y1 + 3.6 * ty)
    b1 = (x1 + 2.2 * nx, y1 + 2.2 * ny)
    b2 = (x1 - 2.2 * nx, y1 - 2.2 * ny)
    head = "M %.1f %.1f L %.1f %.1f L %.1f %.1f Z" % (tip + b1 + b2)
    return arc, head


# ── loop circulation (the glyph's direction) ──
# Screen coordinates (SVG y down): a closed polygon walked in order has a
# positive shoelace area exactly when it turns CLOCKWISE on screen.
_RING_AREA_EPS = 1.0      # px^2 -- a ring enclosing less than this is a coincidence


def _shoelace(pts):
    """Signed area of a closed polygon (shoelace); > 0 = clockwise on screen."""
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _node_xy(nodes, v):
    p = nodes[v]
    if isinstance(p, dict):
        return float(p["x"]), float(p["y"])
    return float(p[0]), float(p[1])


def loop_circulation(members, nodes, edge_polys=None):
    """Direction a traveller follows around the loop AS DRAWN on screen.

    Returns ``('cw' | 'ccw', how)`` or ``(None, why)`` when the drawing does
    not determine one (the caller then falls back to the loop-kind default).

    members: loop node ids in declaration order (node x / y = centres);
    edge_polys: {(a, b): [(x, y), ..]} delivered routes (arcs sampled).
      >= 3 members: signed area of the member-centre polygon walked in member
        order (``how = 'polygon'``) -- the reading a viewer makes from the
        arrows; collinear centres (zero area) fall through to the ring.
      2 members / collinear centres: the delivered RING -- the member routes
        concatenated in loop order (``how = 'ring'``); straight-line members
        keep both end points, so two offset lines read as a thin ring.
    """
    pts = [_node_xy(nodes, v) for v in members if v in nodes]
    if len(pts) >= 3:
        area = _shoelace(pts)
        if abs(area) > 1e-9:
            return ("cw" if area > 0 else "ccw"), "polygon"
        why = "kind:collinear"
    else:
        why = "kind:no-ring"
    if not edge_polys or len(members) < 2:
        return None, why
    ring = []
    for u, v in zip(members, members[1:] + members[:1]):
        poly = edge_polys.get((u, v))
        if poly is None:
            rev = edge_polys.get((v, u))
            poly = None if rev is None else rev[::-1]
        if poly is None or len(poly) < 2:
            return None, why
        # A route's last point is where the loop turns towards the next
        # member; drop it only when the next route starts there.  Arcs
        # end on a card edge and the next member starts on another, so
        # the implicit jump cuts the card; a straight line has just its
        # two end points and must keep both or the ring collapses.
        if ring and abs(ring[-1][0] - poly[0][0]) < 1e-6 and abs(ring[-1][1] - poly[0][1]) < 1e-6:
            ring.extend(poly[1:])
        else:
            ring.extend(poly)
    area = _shoelace(ring)
    if abs(area) < _RING_AREA_EPS:
        return None, why
    return ("cw" if area > 0 else "ccw"), "ring"


def label_rect_clear(cx, cy, w, h, nodes, polys, others, W, H, card_h,
                     box_gap=LABEL_BOX_GAP):
    """True when the label rect (center cx,cy; size w,h) stays
    >= box_gap (default LABEL_BOX_GAP, the gate floor) from every card and
    every line, >= LABEL_LABEL_GAP from every already placed label, and
    >= LABEL_EDGE inside the viewBox.
    ``others`` = [(x, y, w, h)] of placed labels; ``polys`` = per-edge point
    lists (arcs already sampled)."""
    if (cx - w / 2 < LABEL_EDGE or cx + w / 2 > W - LABEL_EDGE or
            cy - h / 2 < LABEL_EDGE or cy + h / 2 > H - LABEL_EDGE):
        return False
    hw, hh = w / 2 + box_gap, h / 2 + box_gap
    for v, p in nodes.items():
        if rect_gap(cx, cy, w, h, p["x"], p["y"], p["w"], card_h) < box_gap - 1e-9:
            return False
    for poly in polys:
        for (x1, y1), (x2, y2) in zip(poly[:-1], poly[1:]):
            if seg_hits_rect(x1, y1, x2, y2, cx, cy, hw, hh):
                return False
    for (ox, oy, ow, oh) in others:
        if rect_gap(cx, cy, w, h, ox, oy, ow, oh) < LABEL_LABEL_GAP - 1e-9:
            return False
    return True


def _rint(v):
    """Round half up (toward +infinity on ties) exactly like JS Math.round,
    so the interactive replay picks the same integer slot as the export."""
    return int(math.floor(v + 0.5))


def _ring(cx0, cy0, radii, ndirs):
    seen = set()
    for r in radii:
        n = 1 if r == 0 else ndirs
        for k in range(n):
            a = 2.0 * math.pi * k / n - math.pi / 2
            cx = _rint(cx0 + r * math.cos(a))
            cy = _rint(cy0 + r * math.sin(a))
            if (cx, cy) not in seen:
                seen.add((cx, cy))
                yield cx, cy


def _candidates(cx0, cy0):
    """Near-to-far candidate centers: the standard ring first, then the far
    ring (more directions) for dense drawings whose near field is full."""
    yield from _ring(cx0, cy0, LABEL_RADII, LABEL_DIRS)
    yield from _ring(cx0, cy0, LABEL_RADII_FAR, LABEL_DIRS_FAR)


def _staged_candidates(cx0, cy0):
    """(cx, cy, gap) in placement order: comfortable slots near the loop
    centroid first, then gate-floor slots near, then the far ring."""
    near = list(_ring(cx0, cy0, LABEL_RADII, LABEL_DIRS))
    far = list(_ring(cx0, cy0, LABEL_RADII_FAR, LABEL_DIRS_FAR))
    for gap in (LABEL_TARGET_GAP, LABEL_BOX_GAP):
        for cx, cy in near:
            yield cx, cy, gap
    for gap in (LABEL_TARGET_GAP, LABEL_BOX_GAP):
        for cx, cy in far:
            yield cx, cy, gap


def place_loop_labels(nodes, polys, loops, card_h, W, H, edges=None):
    """Place every loop label; returns the records in loop declaration order
    (empty when the graph declares no loop).  Record keys: id / name / kind /
    w / h / placed / x / y / offset (distance from the loop centroid),
    ``dir`` = the glyph's direction ('cw' / 'ccw' = the loop's circulation as
    drawn, loop_circulation) with ``dir_source`` = how it was read, and,
    when unplaced, ``reason``.  ``edges`` = [(a, b)] parallel to ``polys``
    (the delivered routes); without it only the member-centre polygon can be
    read and every other loop falls back to the kind default."""
    edge_polys = {}
    for (a, b), poly in zip(edges or [], polys):
        edge_polys.setdefault((a, b), [tuple(p) for p in poly])
    out = []
    placed_rects = []
    for lp in loops:
        lid, name, kind, members = _loop_fields(lp)
        w, h = label_size(lid, name)
        rec = {"id": lid, "name": name, "kind": kind, "w": w, "h": h,
               "placed": False, "x": None, "y": None, "offset": None}
        present = [v for v in members if v in nodes]
        rec["members"] = present
        direction, how = (loop_circulation(present, nodes, edge_polys)
                          if len(present) >= 2 else (None, "kind:members<2"))
        if direction is None:
            direction = "ccw" if kind == "B" else "cw"
        rec["dir"] = direction
        rec["dir_source"] = how
        if len(present) < 2:
            rec["reason"] = "loop has fewer than two placed members"
            out.append(rec)
            continue
        cx0 = sum(nodes[v]["x"] for v in present) / len(present)
        cy0 = sum(nodes[v]["y"] for v in present) / len(present)
        for cx, cy, gap in _staged_candidates(cx0, cy0):
            if label_rect_clear(cx, cy, w, h, nodes, polys, placed_rects, W, H,
                                card_h, box_gap=gap):
                rec.update(placed=True, x=cx, y=cy,
                           offset=round(math.hypot(cx - cx0, cy - cy0), 1))
                placed_rects.append((cx, cy, w, h))
                break
        if not rec["placed"]:
            rec["reason"] = "no collision-free slot inside the viewBox"
        out.append(rec)
    return out


def labels_clear(nodes, polys, labels, card_h, W, H):
    """Independent re-verification of shipped label positions: every placed
    label must keep its clearances.  Returns (ok, problems)."""
    problems = []
    placed = [(l["x"], l["y"], l["w"], l["h"]) for l in labels if l.get("placed")]
    for l in labels:
        if not l.get("placed"):
            continue
        cx, cy, w, h = l["x"], l["y"], l["w"], l["h"]
        others = [r for r in placed if (r[0], r[1]) != (cx, cy)]
        if not label_rect_clear(cx, cy, w, h, nodes, polys, others, W, H, card_h):
            problems.append(l["id"])
    return (not problems), problems


def label_svg(rec, T):
    """Static-export SVG for one loop label (pill + glyph + text)."""
    import html as _html
    lid, name, kind = rec["id"], rec["name"], rec["kind"]
    w, h = rec["w"], rec["h"]
    ink = T["loop_r"] if kind == "R" else T["loop_b"]
    # the arrow follows the loop's circulation as drawn (rec['dir'], read by
    # place_loop_labels); a record without it keeps the kind-based default
    cw = rec["dir"] == "cw" if rec.get("dir") in ("cw", "ccw") else kind != "B"
    arc, head = dir_glyph_paths(GLYPH_R, cw)
    gx = -w / 2 + LABEL_PAD_X + GLYPH_BOX / 2
    # text centred between the glyph's right edge and the pill's right edge:
    # anchor = middle at the interval midpoint, so the rendered text's own
    # width splits the slack evenly on both sides (the analytic pill width is
    # an upper bound of the rendered width, never smaller)
    # the interval starts at the glyph's INK edge (gx + GLYPH_R), not at the
    # glyph box's edge: the ink is narrower than its box
    tx = (LABEL_PAD_X + GLYPH_BOX / 2.0 + GLYPH_R) / 2.0
    disp = "" if rec.get("placed") else ' display="none"'
    # an unplaced label keeps a hidden group at the origin so the
    # interactive layer can still show it once a drag frees a slot
    lx = rec.get("x") if rec.get("placed") else None
    ly = rec.get("y") if rec.get("placed") else None
    lx = 0 if lx is None else lx
    ly = 0 if ly is None else ly
    return (f'<g class="stdraw-looplabel" data-loop="{_html.escape(str(lid), quote=True)}"'
            f' transform="translate({lx:.0f} {ly:.0f})"'
            f' pointer-events="none"{disp}>'
            f'<rect x="{-w / 2:.0f}" y="{-h / 2:.0f}" width="{w}" height="{h}" rx="{h / 2:.0f}"'
            f' fill="{T["card_fill"]}" fill-opacity="0.92"/>'
            f'<g transform="translate({gx:.1f} 0)">'
            f'<path d="{arc}" fill="none" stroke="{ink}" stroke-width="1.3"/>'
            f'<path d="{head}" fill="{ink}"/></g>'
            f'<text x="{tx:.1f}" y="0" text-anchor="middle" dominant-baseline="middle"'
            f' font-size="{LABEL_FS:g}"'
            f' fill="{T["card_label"]}">'
            f'<tspan font-weight="700" fill="{ink}">{_html.escape(str(lid))}</tspan>'
            + (f' <tspan>{_html.escape(name)}</tspan>' if name else "")
            + '</text></g>')
