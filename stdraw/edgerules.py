# -*- coding: utf-8 -*-
"""Edge placement rules v1 — the pre-routing decision layer
(docs/edge-placement-rules-v1.md, jacky's verbal spec engineered).

For every graph edge this module fixes, per end, the box side + the
standard anchor (edge midpoint / golden-section points only — never
corners), plus the line type (straight / arc / lens arc) and the arc
bulge side.  Routing afterwards only connects the pre-assigned anchors;
the repair passes that used to redistribute endpoints post-hoc
(``fan_spread`` / ``midband_reanchor`` / ``anchor_snap`` /
``lens_joint_reassign`` / ``mutual_straight_reroute``) are retired on
this path (spec §8).

Caliber summary (spec §3):
  rule 1  side choice per end from the center offset (|dy| >= |dx| ->
          vertical sides; 10% tie -> the side group with more usable
          slots, still tied -> vertical);
  rule 2  slot pattern per side by line count/type mix (non-B first:
          first R/N at the midpoint, goldens next; B always on a golden);
  rule 3  line type: R/N straight, B arc (adaptive_arc_k); arc bulges
          AWAY from the midpoint line;
  rule 4  a B with a free golden-pair choice picks the pair whose arc
          vertex (t=0.5) has the LARGER perpendicular distance to the
          midpoint line (far side; near side only via an audited
          violation);
  rule 5  on-side order matches the target-direction order (order wins
          over the type pattern, violation recorded);
  rule 6  overflow spills to ADJACENT sides only (near-side golden
          first, then the adjacent midpoint) — never to the opposite
          side;
  rule 7  remote boxes: unchanged routing between the assigned anchors;
  rule 8  mutual pairs: mixed non-B + B -> straight midpoint + arc
          golden; same-type pairs keep the lens double-arc (D2-A) on
          midpoint + golden chords, each bulging away from the other's
          chord;
  rule 9  both ends of one line are assigned together (the golden-pair
          mirror mapping keeps the chord parallel to the midpoint line);
  rule 10 determinism: every tie falls back to ANCHOR_IDS index order /
          fixed iteration orders; same input -> same assignment.

Pure functions only; nothing here mutates the graph or the router.
"""
import math
from collections import defaultdict

from .anchors import ANCHOR_IDS, standard_anchors
from .routing import (adaptive_arc_k, loop_arc_sides,
                      ARC_NEAR_PENALTY,
                      STRAIGHT_ON_B_PENALTY, DENSE_GRID_STEP,
                      DENSE_SLOT_SEP_MIN)

SLOT_SEP_MIN = 10.0        # spec §1.3 (same caliber as routing.PAIR_SEP_MIN)
TIE_FRAC = 0.10            # rule 1: |dx| vs |dy| within 10% = tie
FAR_TIE_EPS = 0.5          # rule 4: distance tie threshold (px)
REPORT_VERSION = "v1"

SIDES = ("n", "e", "s", "w")
ADJACENT = {"n": ("e", "w"), "e": ("n", "s"),
            "s": ("e", "w"), "w": ("n", "s")}
# rule 6: the golden point of the adjacent side that sits on the SAME
# global side as the original (crowded) side — e.g. spilling east from
# side e: n-g2 (upper right) / s-g1 (lower right).
NEAR_GOLDEN = {("e", "n"): "n-g2", ("e", "s"): "s-g1",
               ("w", "n"): "n-g1", ("w", "s"): "s-g2",
               ("n", "e"): "e-g1", ("n", "w"): "w-g2",
               ("s", "e"): "e-g2", ("s", "w"): "w-g1"}
# rule 9: mirror golden ids on facing sides (both sit on the same global
# side, e.g. s-g1 (right part of the bottom edge) <-> n-g2 (right part
# of the top edge)).
GOLD_MIRROR = {("s", "n"): {"s-g1": "n-g2", "s-g2": "n-g1"},
               ("n", "s"): {"n-g1": "s-g2", "n-g2": "s-g1"},
               ("e", "w"): {"e-g1": "w-g2", "e-g2": "w-g1"},
               ("w", "e"): {"w-g1": "e-g2", "w-g2": "e-g1"}}
_KIND_ORDER = {"R": 0, "N": 1, "B": 2}   # rule 2 placement order: R, N, B
SYM_G = "G?"             # symbolic golden: exact id resolved by rules 4 + 9


# ------------------------------------------------------------------
# geometry helpers
# ------------------------------------------------------------------

def _anchor_table(cx, cy, hw, hh):
    """{anchor id: (x, y)} for one box (standard 16-point set)."""
    return {p[0]: (p[1], p[2]) for p in standard_anchors(cx, cy, hw, hh)}


def _usable(table, side, sep_min=None):
    """Usable anchor ids on one side (spec §1.3): the midpoint plus the
    golden points that clear SLOT_SEP_MIN from it, in ANCHOR_IDS order.

    sep_min overrides the separation floor for one call (dense branch:
    the dense hub box reads DENSE_SLOT_SEP_MIN = 6px, gate table #0;
    every other box keeps the default None -> SLOT_SEP_MIN caliber)."""
    out = []
    mx, my = table[side]
    floor = SLOT_SEP_MIN if sep_min is None else sep_min
    grid = sorted((aid for aid in table if aid.startswith(side + "@")),
                  key=lambda aid: int(aid.split("@")[1]))
    for aid in (side, side + "-g1", side + "-g2") + tuple(grid):
        if aid not in table:
            continue          # dense hub: the golden points are popped
        x, y = table[aid]
        if aid != side and math.hypot(x - mx, y - my) < floor:
            continue
        out.append(aid)
    return out


def _extend_dense_grid(t):
    """Dense hub-box slot grid (dense card, gate table #0): replace the
    side golden points with deterministic grid slots at multiples of
    DENSE_GRID_STEP inside the inset rectangle (half-3 clamp, same inset
    caliber as the 16-point set).  The midpoint stays.  Pure mutation of
    the caller's private table; only the dense hub box gets it, so every
    non-dense path is byte-for-byte unchanged.  Grid slots carry synthetic
    ids ``<side>@+<k>`` / ``<side>@-<k>`` (k = grid steps from the
    midpoint); with the 6px floor they are all usable, which lifts the
    per-side capacity above the >16-edge single-box scenario."""
    for side in SIDES:
        for g in (side + "-g1", side + "-g2"):
            t.pop(g, None)
        mx, my = t[side]
        on_x = side in ("n", "s")     # n/s sides order (and run) along x
        half = _half_len_of(t, side)
        k = 1
        while k * DENSE_GRID_STEP <= half:
            off = k * DENSE_GRID_STEP
            for sgn in (1, -1):
                aid = "%s@%s%d" % (side, "+" if sgn > 0 else "-", k)
                t[aid] = ((mx + sgn * off, my) if on_x else (mx, my + sgn * off))
            k += 1


def _half_len_of(t, side):
    """Inset half length of one side from the anchor table (midpoint vs
    corner coordinate on the side's axis; the corners sit on the inset
    rectangle, so |corner - midpoint| = half - inset)."""
    ax = _side_axis(side)
    corner = ("ne", "se") if side == "e" else ("se", "sw") if side == "s" \
        else ("sw", "nw") if side == "w" else ("nw", "ne")
    return abs(t[corner[0]][ax] - t[side][ax])


def _side_axis(side):
    """Ordering axis along a side: n/s sides order by x, e/w sides by y."""
    return 0 if side in ("n", "s") else 1


def _slots_by_coord(table, side, sep_min=None):
    """Usable anchor ids of one side sorted by coordinate along the side
    (ascending, ties by ANCHOR_IDS index) — the rule-5 slot order.

    Dense grid slots (synthetic ``@`` ids) order after the standard ids
    at equal coordinate (deterministic; they never tie in practice — the
    grid is offset from the golden fractions)."""
    ax = _side_axis(side)
    return sorted(_usable(table, side, sep_min=sep_min),
                  key=lambda aid: (table[aid][ax],) + _aid_ord(aid))


def _center_coord(t, side):
    """Target-box center coordinate along the side's ordering axis."""
    return t["cx"] if side in ("n", "s") else t["cy"]


def _geom_tables(nodes_px):
    """Anchor tables (+ centers) per box from Router-convention nodes_px
    {id: (x, y, w, h)} (center + FULL size)."""
    ntab = {}
    for v, p in nodes_px.items():
        t = _anchor_table(p[0], p[1], p[2] / 2.0, p[3] / 2.0)
        t["cx"], t["cy"] = p[0], p[1]
        ntab[v] = t
    return ntab


def _facing_side(ntab, a, b, sep_min=None):
    """Rule 1: the side of box `a` facing box `b` (sep_min: dense-branch
    slot floor override for box a's usable counts, dense branch only)."""
    ta = ntab[a]
    dx, dy = ntab[b]["cx"] - ta["cx"], ntab[b]["cy"] - ta["cy"]
    adx, ady = abs(dx), abs(dy)
    if adx and ady and abs(adx - ady) <= TIE_FRAC * max(adx, ady):
        vert = (len(_usable(ta, "n", sep_min=sep_min))
                + len(_usable(ta, "s", sep_min=sep_min))) >= \
               (len(_usable(ta, "e", sep_min=sep_min))
                + len(_usable(ta, "w", sep_min=sep_min)))
    else:
        vert = ady >= adx
    if vert:
        return "n" if dy < 0 else "s"
    return "e" if dx > 0 else "w"


def _ctrl_sign_of(pa, pb, ctrl):
    """+1/-1: which side of the pa->pb chord the ctrl point sits on
    (router's quad parameterization sign)."""
    vx, vy = pb[0] - pa[0], pb[1] - pa[1]
    dist = math.hypot(vx, vy) or 1.0
    ux, uy = -vy / dist, vx / dist
    mx, my = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0
    return 1 if ((ctrl[0] - mx) * ux + (ctrl[1] - my) * uy) >= 0 else -1


def _ctrl_for_side(pa, pb, side_sign):
    """Quad ctrl point bulging to side_sign of the pa->pb chord."""
    vx, vy = pb[0] - pa[0], pb[1] - pa[1]
    dist = math.hypot(vx, vy) or 1.0
    k = adaptive_arc_k(dist)
    ux, uy = -vy / dist, vx / dist
    return [(pa[0] + pb[0]) / 2.0 + ux * k * dist * side_sign,
            (pa[1] + pb[1]) / 2.0 + uy * k * dist * side_sign]


def _arc_vertex(pa, pb, sign):
    """Quad arc vertex (t=0.5) for the given bulge sign."""
    ctrl = _ctrl_for_side(pa, pb, sign)
    return (0.25 * pa[0] + 0.5 * ctrl[0] + 0.25 * pb[0],
            0.25 * pa[1] + 0.5 * ctrl[1] + 0.25 * pb[1])


def _line_dist(pt, la, lb):
    """Perpendicular distance from pt to the infinite line through la-lb."""
    (x1, y1), (x2, y2) = la, lb
    vx, vy = x2 - x1, y2 - y1
    ln = math.hypot(vx, vy) or 1.0
    return abs((pt[0] - x1) * vy / ln - (pt[1] - y1) * vx / ln)


# ------------------------------------------------------------------
# loop-kind classification (spec §1.1 — same caliber as layout_auto's
# post-route loop coloring, computed here BEFORE routing)
# ------------------------------------------------------------------

def loop_edge_kinds(loops, edges):
    """Per-edge kind 'R'/'B'/'N': an edge belongs to the set of declared
    loop kinds covering it; a single kind wins, a mix (or no loop) -> N."""
    eset = set(edges)
    cov = defaultdict(set)
    for lp in loops or []:
        kind = getattr(lp, "kind", None)
        if not kind:
            continue
        seq = list(lp.nodes)
        for i in range(len(seq)):
            x, y = seq[i], seq[(i + 1) % len(seq)]
            if (x, y) in eset:
                cov[(x, y)].add(kind)
            elif (y, x) in eset:
                cov[(y, x)].add(kind)
    out = []
    for e in edges:
        ks = cov.get(e) or cov.get((e[1], e[0])) or set()
        out.append(sorted(ks)[0] if len(ks) == 1 else "N")
    return out


# ------------------------------------------------------------------
# assignment
# ------------------------------------------------------------------

class _Entry(object):
    """One line-end occupying a (box, side).  After a rule-6 spill the
    entry carries its concrete target anchor (spilled=True) so the slot
    pattern pass claims it as-is instead of re-assigning it."""
    __slots__ = ("edge", "end", "kind", "box", "other", "rank",
                 "spilled", "anchor_override")

    def __init__(self, edge, end, kind, box, other, rank):
        self.edge = edge
        self.end = end
        self.kind = kind
        self.box = box
        self.other = other
        self.rank = rank
        self.spilled = False
        self.anchor_override = None


def _ename(edges, i):
    return "%s->%s" % (edges[i][0], edges[i][1])


def assign(nodes_px, edges, kinds, skip=(), dense_hub=None, loop_arcs=None):
    """Edge placement rules v1 decision layer (spec §3/§5).

    dense_hub: dense-mode node id or None (default — legacy caliber).
    When set, this box's sides run on the deterministic slot grid (gate
    table #0: goldens replaced by DENSE_GRID_STEP slots, 6px usable
    floor); the grid capacity alone hosts >16-edge single boxes, so the
    dense branch does not need slot sharing here (a residual collision
    still records its honest rule-2 violation).
    loop_arcs: declared loops (loop-direction arc default, rule 3 as
    amended for loop-member lines): an R line that belongs to a declared
    loop and is not part of a mutual pair is preset as an arc bulging away
    from its loop centroid; None = original rule 3 (R straight).

    Returns ``(presets, report)``.
      presets: {edge idx: preset dict} — pa/pb endpoint xy, a_anchor /
        b_anchor standard anchor ids, a_side / b_side, style ("line" |
        "arc" | "lens_a" | "lens_b"), arc_side (+1/-1 bulge sign).
      report: certificate block per spec §6.
    """
    skip = set(skip)
    ntab = _geom_tables(nodes_px)
    if dense_hub is not None and dense_hub in ntab:
        _extend_dense_grid(ntab[dense_hub])
    hub_sep = DENSE_SLOT_SEP_MIN if dense_hub is not None else None

    def _sep_of(v):
        return hub_sep if v == dense_hub else None

    violations = []
    overflow = 0

    # ---- rule 1: initial side per end -------------------------------
    side_of = {}
    for i, (a, b) in enumerate(edges):
        if i in skip:
            continue
        side_of[(i, "a")] = _facing_side(ntab, a, b, sep_min=_sep_of(a))
        side_of[(i, "b")] = _facing_side(ntab, b, a, sep_min=_sep_of(b))

    # occupancy per (box, side); rank = target center coordinate along
    # the side's ordering axis (rule 5 order)
    occ = defaultdict(list)
    for i, (a, b) in enumerate(edges):
        if i in skip:
            continue
        for end, v, w in (("a", a, b), ("b", b, a)):
            side = side_of[(i, end)]
            rank = _center_coord(ntab[w], side)
            occ[(v, side)].append(_Entry(i, end, kinds[i], v, w, rank))

    claimed = {}   # (box, anchor id) -> edge idx

    def claim(v, aid, i):
        claimed[(v, aid)] = i

    # ---- rule 6: spill overflow to adjacent sides -------------------
    # triggers when entries exceed usable slots OR the side cannot host
    # every B line on a golden point (B leaves first — rule 2 order
    # R, N, B means B is placed last / moved first).  Bounded passes:
    # each spill re-queues on the target side, revisited next pass.
    work = sorted(occ, key=lambda k: (SIDES.index(k[1]), k[0]))
    for _pass in range(4):
        moved = 0
        for (v, side) in work:
            while True:
                entries = occ.get((v, side)) or []
                usable = _usable(ntab[v], side, sep_min=_sep_of(v))
                golds = [s for s in usable if "-g" in s]
                nb = sum(1 for e in entries if e.kind == "B")
                if len(entries) <= len(usable) and nb <= len(golds):
                    break
                victim = None
                for kind in ("B", "N", "R"):
                    c = [e for e in entries if e.kind == kind]
                    if c:
                        victim = sorted(c, key=lambda e: (-e.rank, e.edge))[0]
                        break
                if victim is None:
                    break
                target = _spill_target(v, side, victim, ntab, claimed,
                                       sep_min=_sep_of(v))
                if target is None:
                    violations.append({"edge": _ename(edges, victim.edge),
                                       "rule": 6,
                                       "detail": "no adjacent-side anchor free; stays on %s" % side})
                    break
                entries.remove(victim)
                victim.spilled = True
                victim.anchor_override = target[1]
                occ[(v, target[0])].append(victim)
                overflow += 1
                moved += 1
        if not moved:
            break
        work = sorted(occ, key=lambda k: (SIDES.index(k[1]), k[0]))

    # ---- rule 2 + rule 5: slot pattern per (box, side) --------------
    end_anchor = {}   # (edge idx, end) -> anchor id or SYM_G
    end_side = {}
    for (v, side) in sorted(occ, key=lambda k: (SIDES.index(k[1]), k[0])):
        entries = occ.get((v, side)) or []
        for ent in entries:
            if ent.spilled:
                # rule 6 spill: concrete anchor already chosen — claim it
                claim(v, ent.anchor_override, ent.edge)
                end_anchor[(ent.edge, ent.end)] = ent.anchor_override
                end_side[(ent.edge, ent.end)] = side
        entries = sorted((e for e in entries if not e.spilled),
                         key=lambda e: (e.rank, e.edge))          # rule 5 order
        if not entries:
            continue
        usable = _slots_by_coord(ntab[v], side, sep_min=_sep_of(v))
        mids = [s for s in usable if s in SIDES]
        golds = [s for s in usable if "-g" in s]
        n_b = sum(1 for e in entries if e.kind == "B")
        want = []
        nonb_seen = 0
        b_seen = 0
        for e in entries:
            if e.kind == "B":
                if golds:
                    want.append(SYM_G if n_b == 1 else
                                golds[min(b_seen, len(golds) - 1)])
                else:
                    want.append(mids[0] if mids else usable[0])
                b_seen += 1
            else:
                if nonb_seen == 0 and mids:
                    want.append(mids[0])
                elif golds:
                    want.append(golds[min(nonb_seen - (1 if mids else 0),
                                          len(golds) - 1)])
                else:
                    want.append(usable[min(nonb_seen, len(usable) - 1)])
                nonb_seen += 1
        # rule 5 remap: slot coordinate order follows entry rank order
        # (symbolic markers stay attached to their entry)
        fixed = [(j, w) for j, w in enumerate(want) if w != SYM_G]
        fixed_sorted = sorted(fixed, key=lambda jw: usable.index(jw[1])
                              if jw[1] in usable else 99)
        for (j, _), (_, aid) in zip(fixed, fixed_sorted):
            want[j] = aid
        for e, aid in zip(entries, want):
            if aid == SYM_G:
                end_anchor[(e.edge, e.end)] = SYM_G
            else:
                if (v, aid) in claimed:
                    # collision (should not happen after spill): fall back
                    # to any free usable slot, rule 10 order
                    alt = next((s for s in usable if (v, s) not in claimed), None)
                    if alt is None:
                        violations.append({"edge": _ename(edges, e.edge),
                                           "rule": 2,
                                           "detail": "side %s fully occupied" % side})
                        continue
                    aid = alt
                claim(v, aid, e.edge)
                end_anchor[(e.edge, e.end)] = aid
            end_side[(e.edge, e.end)] = side

    # ---- rule 8: lens pairs (same-type mutual, both non-B) ---------
    eset = set(edges)
    mutual = defaultdict(list)
    for i, (a, b) in enumerate(edges):
        if i in skip:
            continue
        if a < b and (b, a) in eset:
            mutual[(a, b)].append(i)
    lens = {}
    for key in sorted(mutual):
        idxs = sorted(mutual[key])
        if len(idxs) != 2:
            continue
        i1, i2 = idxs
        if kinds[i1] == kinds[i2] and kinds[i1] in ("R", "N"):
            lens[i1], lens[i2] = "lens_a", "lens_b"
        # mixed pairs (one B) already fall out of the pattern:
        # non-B takes the midpoint, B takes a golden (rule 8 row 1)

    # ---- resolve symbolic goldens (rules 4 + 9, per edge) ----------
    arc_sides = (loop_arc_sides({v: (p[0], p[1]) for v, p in nodes_px.items()},
                                edges, loop_arcs) if loop_arcs else {})
    presets = {}
    for i, (a, b) in enumerate(edges):
        if i in skip:
            continue
        style = lens.get(i, "arc" if (kinds[i] == "B" or i in arc_sides)
                         else "line")
        aid_a, aid_b = end_anchor.get((i, "a")), end_anchor.get((i, "b"))
        sd_a, sd_b = end_side.get((i, "a")), end_side.get((i, "b"))
        if aid_a is None or aid_b is None or sd_a is None or sd_b is None:
            continue
        if aid_a == SYM_G or aid_b == SYM_G:
            ga, gb, v4 = _resolve_symbolic_golden(
                a, b, sd_a, sd_b, aid_a, aid_b, ntab, claimed)
            violations.extend(v4)
            claim(a, ga, i)
            claim(b, gb, i)
            end_anchor[(i, "a")], end_anchor[(i, "b")] = ga, gb
            aid_a, aid_b = ga, gb
        presets[i] = _finalize(i, a, b, style, aid_a, aid_b, sd_a, sd_b,
                               ntab, arc_sides.get(i))

    # rule 8 (D2-A): lens pair bulge directions are mutually exclusive —
    # the midpoint-chord arc bends away from the golden chord's side.
    for key in sorted(mutual):
        idxs = sorted(mutual[key])
        if len(idxs) != 2 or idxs[0] not in presets or idxs[1] not in presets:
            continue
        p1, p2 = presets[idxs[0]], presets[idxs[1]]
        m_idx = None
        g_idx = None
        for j, p in ((idxs[0], p1), (idxs[1], p2)):
            if p["a_anchor"] in SIDES and p["b_anchor"] in SIDES:
                m_idx = j
                m_p = p
            else:
                g_idx = j
                g_p = p
        if m_idx is None or g_idx is None:
            continue
        ta, tb = ntab[edges[m_idx][0]], ntab[edges[m_idx][1]]
        m1, m2 = ta[m_p["a_side"]], tb[m_p["b_side"]]
        # signed side of the golden chord midpoint relative to the M chord line
        gm = ((g_p["pa"][0] + g_p["pb"][0]) / 2.0,
              (g_p["pa"][1] + g_p["pb"][1]) / 2.0)
        (x1, y1), (x2, y2) = m1, m2
        vx, vy = x2 - x1, y2 - y1
        ln = math.hypot(vx, vy) or 1.0
        signed = ((gm[0] - x1) * vy / ln - (gm[1] - y1) * vx / ln)
        m_p["arc_side"] = -1 if signed > 0 else 1

    report = {"version": REPORT_VERSION, "edges_total": len(edges),
              "violations": violations,
              "overflow_to_adjacent_side": overflow,
              "lens_pairs": sum(1 for s in lens.values() if s == "lens_a")}
    return presets, report


def _aid_ord(aid):
    """Deterministic order key for an anchor id: ANCHOR_IDS index for the
    standard set; dense grid slots (synthetic ``@`` ids) sort after all
    standard ids by (side-local) grid step."""
    if aid in ANCHOR_IDS:
        return (0, ANCHOR_IDS.index(aid), 0)
    return (1, int(aid.split("@")[1]), 0 if "+" in aid else 1)


def _resolve_symbolic_golden(a, b, sd_a, sd_b, aid_a, aid_b, ntab, claimed):
    """Rules 4 + 9 for an edge holding a symbolic golden end.

    Candidate golden pairs = free golden points at the symbolic end(s),
    matched by the rule-9 mirror (same global side).  Picks the pair
    whose arc vertex (t=0.5, best bulge sign) has the largest
    perpendicular distance to the midpoint line (rule 4 far side); ties
    fall back to rule 10 (lower ANCHOR_IDS index at the a end)."""
    ta, tb = ntab[a], ntab[b]
    concrete_a = None if aid_a == SYM_G else aid_a
    concrete_b = None if aid_b == SYM_G else aid_b
    golds_a = [g for g in _usable(ta, sd_a) if "-g" in g]
    golds_b = [g for g in _usable(tb, sd_b) if "-g" in g]
    free_a = [g for g in golds_a if (a, g) not in claimed] or golds_a
    free_b = [g for g in golds_b if (b, g) not in claimed] or golds_b
    pairs = []
    if concrete_a is None and concrete_b is None:
        mirror = GOLD_MIRROR.get((sd_a, sd_b), {})
        for ga in free_a:
            gb = mirror.get(ga)
            if gb is None:
                pairs.extend((ga, gb2) for gb2 in free_b)
            elif gb in free_b:
                pairs.append((ga, gb))
        if not pairs:
            pairs = [(ga, gb) for ga in free_a for gb in free_b]
    elif concrete_a is None:
        pairs = [(ga, concrete_b) for ga in free_a]
    else:
        pairs = [(concrete_a, gb) for gb in free_b]
    if not pairs:
        return sd_a, sd_b, [{"edge": "%s->%s" % (a, b), "rule": 4,
                             "detail": "no free golden pair; midpoints used"}]
    m1, m2 = ta[sd_a], tb[sd_b]     # midpoint line (rule 4 reference)
    scored = []
    for ga, gb in pairs:
        pa, pb = ta[ga], tb[gb]
        far = max(_line_dist(_arc_vertex(pa, pb, 1), m1, m2),
                  _line_dist(_arc_vertex(pa, pb, -1), m1, m2))
        scored.append((far, ga, gb))
    best_far = max(s[0] for s in scored)
    # rule 10 tie-break: within FAR_TIE_EPS of the best -> lowest anchor ids
    tied = [s for s in scored if s[0] >= best_far - FAR_TIE_EPS]
    tied.sort(key=lambda s: (_aid_ord(s[1]), _aid_ord(s[2])))
    return tied[0][1], tied[0][2], []


def _spill_target(v, side, ent, ntab, claimed, sep_min=None):
    """Rule 6: adjacent side + anchor for a spilled entry.  Prefers the
    near-side golden of the adjacent side chosen by target direction,
    then the adjacent midpoint.  Returns (side, anchor id) or None."""
    tgt = _center_coord(ntab[ent.other], side)
    ax = _side_axis(side)
    cands = []
    for adj in ADJACENT[side]:
        g = NEAR_GOLDEN.get((side, adj))
        if g is not None and g in ntab[v]:
            # golden points rank BEFORE the adjacent midpoint at equal
            # distance (spec rule 6: prefer the golden point on the side
            # closer to the original edge, then the midpoint)
            cands.append((abs(ntab[v][g][ax] - tgt), 0, ANCHOR_IDS.index(g),
                          adj, g))
        if adj in _usable(ntab[v], adj, sep_min=sep_min):
            cands.append((abs(ntab[v][adj][ax] - tgt), 1, ANCHOR_IDS.index(adj),
                          adj, adj))
    cands.sort()
    for _, _, _, adj, aid in cands:
        if (v, aid) not in claimed:
            return (adj, aid)
    return None


def _finalize(i, a, b, style, aid_a, aid_b, sd_a, sd_b, ntab, arc_pref=None):
    """Build one preset; pick the rule-3 bulge sign.

    arc_pref (loop-direction arc default): +1/-1 takes the bulge away from
    the loop centroid; 0 / None falls back to the original rule 3 sign
    (away from the midpoint line)."""
    ta, tb = ntab[a], ntab[b]
    pa, pb = list(ta[aid_a]), list(tb[aid_b])
    arc_side = 1
    if style in ("arc", "lens_a", "lens_b"):
        if arc_pref in (1, -1):
            arc_side = arc_pref
        else:
            m1, m2 = ta[sd_a], tb[sd_b]
            d1 = _line_dist(_arc_vertex(pa, pb, 1), m1, m2)
            d2 = _line_dist(_arc_vertex(pa, pb, -1), m1, m2)
            arc_side = 1 if d1 >= d2 else -1
    return {"pa": pa, "pb": pb, "a_anchor": aid_a, "b_anchor": aid_b,
            "a_side": sd_a, "b_side": sd_b, "style": style,
            "arc_side": arc_side}


# ------------------------------------------------------------------
# post-routing audit (spec §6: violations recorded, not graded)
# ------------------------------------------------------------------

def audit_delivery(presets, routes, edges):
    """Compare delivered routes with the presets and record violations:
      rule 2 — the delivered route presses another box or arrives/
               departs at a tangential (< ANCHOR_MIN_DEG) angle (the
               candidate pool could not avoid it between the fixed
               endpoints; recorded honestly, hard gates still grade it);
      rule 3 — a B line's arc fell back to a polyline/vg route;
      rule 4 — the delivered arc bulges to the near side (the far side
               candidate lost to press/crossings in scoring).
    Returns the violation list."""
    from .routing import ANCHOR_MIN_DEG
    out = []
    for i, p in sorted(presets.items()):
        info = routes.get(i)
        if not info:
            continue
        kind = info.get("kind")
        if kind not in ("line", "arc"):
            if p["style"] in ("arc", "lens_a", "lens_b"):
                out.append({"edge": _ename(edges, i), "rule": 3,
                            "detail": "arc fell back to %s route" % kind})
            continue
        if kind == "arc" and p["style"] in ("arc", "lens_a", "lens_b"):
            ctrl = info.get("ctrl") or info["points"][len(info["points"]) // 2]
            pts = info["points"]
            if _ctrl_sign_of(pts[0], pts[-1], ctrl) != p["arc_side"]:
                out.append({"edge": _ename(edges, i), "rule": 4,
                            "detail": "near-side bulge used (far side crossed/pressed)"})
        press = info.get("press") or 0
        if press:
            out.append({"edge": _ename(edges, i), "rule": 2,
                        "detail": "delivered route presses %d box(es)" % press})
        ang_a, ang_b = info.get("ang_a"), info.get("ang_b")
        for end, ang in (("a", ang_a), ("b", ang_b)):
            if ang is not None and ang < ANCHOR_MIN_DEG:
                out.append({"edge": _ename(edges, i), "rule": 2,
                            "detail": "delivered %s-end arrival angle %.1f deg < %d (tangential)"
                                      % (end, ang, ANCHOR_MIN_DEG)})
    return out


# ------------------------------------------------------------------
# §4 hard-gate precedence: preset eligibility validation
# ------------------------------------------------------------------

def validate_presets(nodes_px, edges, presets, clearance, dense_hub=None):
    """Spec §4: hard gates rank above the rules.  A preset is dropped
    (edge falls back to the legacy candidate pool, honest violation
    recorded by the caller) when its fixed chord geometry would make a
    hard gate unachievable:
      - departure/arrival angle vs the border tangent < ANCHOR_MIN_DEG
        (tangential exit — the fixed anchor cannot be fixed by any
        candidate geometry);  dense-mode hub ends read the relaxed
        DENSE_ANCHOR_MIN_DEG floor (dense card, Q2);
      - the straight chord pierces another box AND no visibility-graph
        detour exists between the fixed endpoints (press unavoidable).
    Returns the set of edge indices to exempt."""
    import math as _m
    from .routing import ANCHOR_MIN_DEG, PRESS_MARGIN, DENSE_ANCHOR_MIN_DEG
    from . import visibility as _vis
    rects = []
    ntab = _geom_tables(nodes_px)
    boxes = {}
    for v, p in nodes_px.items():
        boxes[v] = (p[0], p[1], p[2] / 2.0, p[3] / 2.0)
    drop = set()
    for i, p in sorted(presets.items()):
        a, b = edges[i]
        pa, pb = p["pa"], p["pb"]
        vx, vy = pb[0] - pa[0], pb[1] - pa[1]
        ln = _m.hypot(vx, vy)
        if ln < 1e-9:
            drop.add(i)
            continue
        bad_angle = False
        # The tangent side is taken from the preset's assigned side (the
        # decision layer knows it exactly).  Guessing it from coordinates
        # against the RAW half extents is wrong: the standard 16-anchor set
        # lives on the rectangle inset by ANCHOR_INSET (3px), so an e/w
        # anchor never satisfies |ax-cx|==hw and was mis-judged with a
        # horizontal tangent -- shallow grazing chords (7-16 deg vs the TRUE
        # vertical border) passed as "smooth" (measured: random-n20-i00
        # 4 grazing arrivals delivered).  e/w border -> vertical tangent;
        # n/s border -> horizontal tangent (metrics caliber).
        for v, side, anchor, other in ((a, p["a_side"], pa, pb),
                                       (b, p["b_side"], pb, pa)):
            ax, ay = anchor
            tx, ty = (0.0, 1.0) if side in ("e", "w") else (1.0, 0.0)
            dvx, dvy = other[0] - ax, other[1] - ay
            dl = _m.hypot(dvx, dvy) or 1.0
            ang = _m.degrees(_m.acos(max(0.0, min(1.0,
                abs((dvx / dl) * tx + (dvy / dl) * ty)))))
            _floor = (DENSE_ANCHOR_MIN_DEG
                      if dense_hub is not None and v == dense_hub
                      else ANCHOR_MIN_DEG)
            if ang < _floor:
                bad_angle = True
                break
        if bad_angle:
            drop.add(i)
            continue
        # press feasibility: chord pierces a FOREIGN box (endpoint boxes
        # excluded — their distance is 0 by construction) -> require a vg
        # detour between the fixed endpoints, else drop the preset
        rects = [r for v, r in boxes.items() if v not in (a, b)]
        pierce = any(_vis.seg_rect_distance(pa, pb, r) <= PRESS_MARGIN
                     for r in rects)
        if pierce:
            route = _vis.plan_route(pa, pb, rects, clearance + 2.0)
            if not route:
                drop.add(i)
    return drop


# ------------------------------------------------------------------
# §5 step 7: bounded local re-enumeration when crossings survive
# ------------------------------------------------------------------

def alternate_presets(nodes_px, edges, kinds, presets, involved, round_no,
                      dense_hub=None, loop_arcs=None):
    """Deterministic local re-enumeration for edges still involved in
    crossings (spec §5 step 7).  round_no 1/2/3 tries, per involved edge:
      1. mirror the golden pair (other global side, bulge sign flipped);
         a loop-direction arc on midpoint anchors has no golden mirror, so
         round 1 flips its bulge side alone (the "near side" of rule 3);
      2. move both ends to a near-side golden of an adjacent side
         (rule 6 spill geometry);
      3. straight between the facing side midpoints (last resort).
    dense_hub: dense-mode node id or None — the dense hub table carries
    the slot grid (same caliber as assign).
    Returns the updated preset dict, or None when no variant applies."""
    ntab = _geom_tables(nodes_px)
    if dense_hub is not None and dense_hub in ntab:
        _extend_dense_grid(ntab[dense_hub])
    hub_sep = DENSE_SLOT_SEP_MIN if dense_hub is not None else None
    arc_sides = (loop_arc_sides({v: (p[0], p[1]) for v, p in nodes_px.items()},
                                edges, loop_arcs) if loop_arcs else {})

    def _sep_of(v):
        return hub_sep if v == dense_hub else None
    out = dict(presets)
    changed = False
    for i in sorted(involved):
        p = presets.get(i)
        if not p:
            continue
        a, b = edges[i]
        ta, tb = ntab[a], ntab[b]
        cand = None
        if round_no == 1 and p["style"] in ("arc", "lens_a", "lens_b"):
            ma = GOLD_MIRROR.get((p["a_side"], p["b_side"]), {})
            mb = GOLD_MIRROR.get((p["b_side"], p["a_side"]), {})
            ga2, gb2 = ma.get(p["a_anchor"]), mb.get(p["b_anchor"])
            if ga2 and gb2 and ga2 in _usable(ta, p["a_side"],
                                              sep_min=_sep_of(a)) \
                    and gb2 in _usable(tb, p["b_side"], sep_min=_sep_of(b)):
                cand = dict(p, a_anchor=ga2, b_anchor=gb2,
                            pa=list(ta[ga2]), pb=list(tb[gb2]),
                            arc_side=-p["arc_side"])
            elif p["style"] == "arc" and arc_sides.get(i) in (1, -1) \
                    and p["a_anchor"] in SIDES and p["b_anchor"] in SIDES:
                cand = dict(p, arc_side=-p["arc_side"])
        elif round_no == 2:
            ea = _spill_target(a, p["a_side"],
                               _Entry(i, "a", kinds[i], a, b,
                                      _center_coord(ntab[b], p["a_side"])),
                               ntab, {}, sep_min=_sep_of(a))
            eb = _spill_target(b, p["b_side"],
                               _Entry(i, "b", kinds[i], b, a,
                                      _center_coord(ntab[a], p["b_side"])),
                               ntab, {}, sep_min=_sep_of(b))
            if ea and eb:
                cand = dict(p, a_side=ea[0], b_side=eb[0],
                            a_anchor=ea[1], b_anchor=eb[1],
                            pa=list(ta[ea[1]]), pb=list(tb[eb[1]]))
        elif round_no == 3:
            if p["a_side"] in _usable(ta, p["a_side"], sep_min=_sep_of(a)) \
                    and p["b_side"] in _usable(tb, p["b_side"],
                                               sep_min=_sep_of(b)):
                cand = dict(p, style="line", a_anchor=p["a_side"],
                            b_anchor=p["b_side"], pa=list(ta[p["a_side"]]),
                            pb=list(tb[p["b_side"]]))
        if cand is not None:
            out[i] = cand
            changed = True
    return out if changed else None
