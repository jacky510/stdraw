# -*- coding: utf-8 -*-
"""ref-scrubbed D: offline mutual-lens placement+arrival experiment.

NOT part of the production pipeline.  HISTORICAL ARCHIVE of the pre-ref-scrubbed
exploration (measured on main 5b6721c, before the non-mirrored lens_joint_reassign
channel landed; on newer mains its mini-chain no longer mirrors the production
lens channel -- kept for the record, do not re-run for current numbers).
Reproduces the placement-alignment
exploration that was evaluated for the crowding<->fundamental lens
(classic-cld-growth-and-burden) and archives why NO 24px-grid placement
nudge is adoptable under the delivery gate set.

Measured conclusion (2026-11-09, evidence on card ref-scrubbed):

  1. Baseline placement (24px offset, chord 122px): worst lens arrival
     14.4 deg; the 16-anchor mirrored-pairing tilt floor is 13.8 deg
     (ref-scrubbed derivation, tests/test_mutual_lens_arrow_normal.py).
  2. Placement alignment candidates (x shifts of the pair's boxes on the
     24px grid, +/-24/+/-48/+/-72 on BOTH boxes, full delivery-gate chain
     at the spine-construct calibers) -- EVERY candidate regresses at
     least one hard gate:
       crowding -24 (boxes aligned): arrival ~2-4 deg BUT lens pair
         separation drops to ~4.5px (< 12px SEP_FLOOR, near-merged lens);
       crowding +48: 2 fan visual crossings + 1 off-angle anchor;
       crowding -48/-72: separation 7.2-9.0px (< 12) and/or angle fail;
       fundamental -24/-48: min card gap 11 / 0 px (row overlap);
       quickfix-family shifts: separation 8.9-10.6px or visual crossings.
     => the triangle {arrival <= 10 deg, lens separation >= 12px,
        16-anchor caliber + hard gates} is INFEASIBLE at every tested
        placement; 13.8 deg stands as the hard floor and the delivered
        14.4 deg / 15 deg ceiling caliber stays.
  3. Shared-anchor relaxation (both arcs on ONE anchor): min lens
     separation = 0px (double-arc lens collapses into one stem) --
     violates mutual_pairs_separated (>=4px) and the no-merging rule;
     NOT adoptable.

Run:  python benchmarks/tools/lens_placement_experiment.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from stdraw.routing import ARRIVAL_TARGET_DEG, Router, min_pair_dist, \
    sample_polyline

SEP_FLOOR = 12.0     # tests/test_mutual_lens_arrow_normal.py SEP_FLOOR


def lens_chain(nodes_px, edges, clearance, pitch, enhanced):
    """Full routing channel chain (same sequence as layout_auto 4)."""
    r = Router(nodes_px, edges, clearance, pitch)
    rt = r.route_all()
    rt = r.coincide_reroute(rt)
    rt = r.midband_reanchor(rt, enhanced=enhanced)
    rt = r.fan_spread(rt)
    rt = r.mutual_straight_reroute(rt)
    rt = r.mutual_arrival_flip(rt)
    snap = r.anchor_snap(rt)
    rt = r.mutual_arrival_flip(rt, enhanced_gates=True)
    # ref-scrubbed: production also runs the non-mirrored joint re-assignment
    # after the post-snap flip -- the archive tool mirrors it so its
    # gate/arrival numbers are production-caliber.
    rt = r.lens_joint_reassign(rt, snap.get("lens_pairs", []))
    rt = r.mutual_arrival_flip(rt, enhanced_gates=True)
    return rt, r


def worst_arrival(r, rt):
    worst = 0.0
    for key in sorted(r.mutual):
        for i, v_end in ((r.eidx.get((key[0], key[1])), key[1]),
                         (r.eidx.get((key[1], key[0])), key[0])):
            inf = rt.get(i)
            if not inf or inf.get("kind") != "arc" or inf.get("ctrl") is None:
                return float("inf")
            bx, by, hw, hh = r.N[v_end]
            p, c = inf["points"][-1], inf["ctrl"]
            on_x = abs(abs(p[0] - bx) - hw) <= abs(abs(p[1] - by) - hh)
            nx, ny = ((1.0, 0.0) if p[0] > bx else (-1.0, 0.0)) if on_x \
                else ((0.0, 1.0) if p[1] > by else (0.0, -1.0))
            tx, ty = p[0] - c[0], p[1] - c[1]
            n = math.hypot(tx, ty)
            if n < 1e-9:
                return float("inf")
            worst = max(worst, math.degrees(math.acos(
                max(0.0, min(1.0, abs(tx * nx + ty * ny) / n)))))
    return worst


def lens_sep(r, rt):
    sep = None
    for key in sorted(r.mutual):
        i1 = r.eidx.get((key[0], key[1]))
        i2 = r.eidx.get((key[1], key[0]))
        if i1 in rt and i2 in rt:
            s = min_pair_dist(sample_polyline(rt[i1]["points"], step=2),
                              sample_polyline(rt[i2]["points"], step=2))
            sep = s if sep is None else min(sep, s)
    return sep


def main():
    from stdraw.dsl import parse
    from stdraw.layout_auto import layout
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    ex = os.path.join(root, "examples", "classic-cld-growth-and-burden.cld")
    lay = layout(parse(open(ex, encoding="utf-8").read()))
    nodes = lay["nodes"]
    edges = [(e["a"], e["b"]) for e in lay["edges"]]
    x0 = {v: n["x"] for v, n in nodes.items()}
    y0 = {v: n["y"] for v, n in nodes.items()}
    widths = {v: n["w"] for v, n in nodes.items()}
    card_h = next(iter(nodes.values())).get("h", 44.0)

    def nm(pos):
        return {v: (pos[v], y0[v], widths[v], card_h) for v in pos}

    rt0, r0 = lens_chain(nm(x0), edges, 16.0, 80.0, enhanced=True)
    print(f"baseline: worst arrival {worst_arrival(r0, rt0):.2f} deg "
          f"(target {ARRIVAL_TARGET_DEG:.0f}), lens sep {lens_sep(r0, rt0):.2f}px")
    for key in sorted(r0.mutual):
        for v in key:
            for dx in (24, -24, 48, -48, 72, -72):
                pos = dict(x0)
                pos[v] = x0[v] + dx
                rt, r = lens_chain(nm(pos), edges, 16.0, 80.0, enhanced=True)
                fan = sum(r._sibling_cross(i, rt) for i in rt)
                gx = r.final_crossing_pairs(rt)
                angbad = sum(1 for inf in rt.values()
                             if min(inf.get("ang_a", 20.0),
                                    inf.get("ang_b", 20.0)) < 20.0 - 1e-9)
                sep = lens_sep(r, rt)
                # full delivery placement gates (min card gap >= 16, spacing
                # CV <= 0.35) -- fundamental -24/-48 measured: arrival looks
                # clean but the row overlap ships min_card_gap 11/0px
                ids = sorted(nm(pos))
                gaps = []
                for x1 in range(len(ids)):
                    for x2 in range(x1 + 1, len(ids)):
                        va, vb = nm(pos)[ids[x1]], nm(pos)[ids[x2]]
                        gx = max(vb[0] - vb[2] - (va[0] + va[2]),
                                 va[0] - va[2] - (vb[0] + vb[2]), 0.0)
                        gy = max(vb[1] - vb[3] - (va[1] + va[3]),
                                 va[1] - va[3] - (vb[1] + vb[3]), 0.0)
                        gaps.append(max(gx, gy) if (gx <= 0 or gy <= 0)
                                    else math.hypot(gx, gy))
                min_gap = min(gaps) if gaps else 0.0
                gap_ok = min_gap >= 16.0
                print(f"{v} {dx:+3d}: arrival {worst_arrival(r, rt):6.2f} deg "
                      f"fan_x={fan} graph_x={gx} angbad={angbad} "
                      f"sep={sep if sep is None else round(sep, 2)}px "
                      f"min_gap={round(min_gap, 1)} "
                      f"{'OK' if (fan == 0 and gx == 0 and angbad == 0 and
                                 gap_ok and
                                 sep is not None and sep >= SEP_FLOOR)
                            else 'REJECT'}")


if __name__ == "__main__":
    main()
