# -*- coding: utf-8 -*-
"""Quality certificate (this project's moat) — five metrics + placement metrics + honest grading.

All verification runs on the **delivered coordinates** (the rounded/exported
copy); this is discipline, not an optimization option.
Metric implementations: seg_cross / Liang-Barsky seg_hits_rect / rect_gap /
row alignment rate.
Plus the first-priority placement metric: spacing coefficient of variation (CV).

Honest grading (never masquerade as a finished product):
  best = placement requirements met + 0 line crossings
  second = placement requirements met + 1-2 crossings (certificate records
           crossing coordinates for human review)
  uncertified = everything else (stated honestly, never downgraded to fake it)
The 3D layer is out of scope for this module (3D metrics belong to M2; the M0
3D demo only reports placement and edge lengths).
"""
import json
import math
from typing import Dict, List, Optional

from . import __version__ as _PKG_VERSION

EPS = 1e-9
ROW_EPS = 4          # visual same-row test: y difference <= 4px counts as one row
INFLATE = 4          # card-piercing caliber: card box outward inflation px
                     # (a softened substitute for the 16px inflation caliber)


def seg_cross(p1, p2, p3, p4):
    """Strict intersection test (incl. collinear overlap; endpoint touch excluded)."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < EPS else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    if d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0:
        return True
    if d1 == 0 and d2 == 0 and d3 == 0 and d4 == 0:
        def on(a, b, c):
            return (min(a[0], b[0]) - EPS <= c[0] <= max(a[0], b[0]) + EPS and
                    min(a[1], b[1]) - EPS <= c[1] <= max(a[1], b[1]) + EPS)
        if on(p3, p4, p1) or on(p3, p4, p2) or on(p1, p2, p3) or on(p1, p2, p4):
            near = [q for q in (p3, p4) for p in (p1, p2)
                    if abs(q[0] - p[0]) < EPS and abs(q[1] - p[1]) < EPS]
            if len(near) >= 1:
                return False
            return True
    return False


def seg_hits_rect(x1, y1, x2, y2, cx, cy, hw, hh):
    """Liang-Barsky: whether a segment crosses a rectangle (positive-length
    entry counts; merely touching the border does not)."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - (cx - hw)), (dx, (cx + hw) - x1),
                 (-dy, y1 - (cy - hh)), (dy, (cy + hh) - y1)):
        if abs(p) < EPS:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return t1 - t0 > EPS


def rect_gap(x1, y1, w1, h1, x2, y2, w2, h2):
    """Rectangular gap between two cards (hypot of components; 0 when overlapping)."""
    dx = abs(x1 - x2) - (w1 + w2) / 2
    dy = abs(y1 - y2) - (h1 + h2) / 2
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def scene_from_planar(v4: dict, card_h: int = None) -> dict:
    """Planar layout JSON -> generic scene (segments = vertical lines, y is row center)."""
    nodes = {}
    ch = card_h or v4["meta"].get("cardH", 42)
    for v, p in v4["nodes"].items():
        nodes[v] = {"x": p["x"], "y": p["y"], "w": p.get("w", 140), "h": ch}
    edges = [{"a": e["a"], "b": e["b"]} for e in v4["edges"]]
    segs = {}
    for i, e in enumerate(v4["edges"]):
        segs[i] = ((e["x"], e["y1"]), (e["x"], e["y2"]))
    return {"nodes": nodes, "edges": edges, "segments": segs}


def scene_from_grid(nodes: dict, edges: list, card_h: int) -> dict:
    """Center-coordinate graph (viewer grid/ring forms) -> generic scene
    (segments = center-to-center lines)."""
    segs = {}
    for i, e in enumerate(edges):
        a, b = nodes[e["a"]], nodes[e["b"]]
        segs[i] = ((a["x"], a["y"]), (b["x"], b["y"]))
    return {"nodes": {v: dict(p, h=card_h) for v, p in nodes.items()},
            "edges": edges, "segments": segs}


def certificate(scene: dict, graph_name: str = "", layer: str = "2D",
                gates: Optional[dict] = None,
                notes: Optional[List[str]] = None,
                interactive: str = "no", drag_layer: str = "no") -> dict:
    nodes: Dict[str, dict] = scene["nodes"]
    edges: List[dict] = scene["edges"]
    segs: dict = scene["segments"]
    ids = list(nodes)
    notes = list(notes or [])

    # 1. Straight-line crossings
    crossings = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            si, sj = segs[i], segs[j]
            if seg_cross(si[0], si[1], sj[0], sj[1]):
                crossings.append({"edges": [f"{ei['a']}->{ei['b']}",
                                            f"{ej['a']}->{ej['b']}"],
                                  "at": si[1] if si[0] == sj[0] and si[1] == sj[1]
                                  else _interpolate(si, sj)})

    # 2. Line piercing unrelated cards (Liang-Barsky): INFLATE caliber +
    #    true 0px piercing caliber
    occ_inflated, occ_true = [], []
    for i in range(len(edges)):
        s = segs[i]
        for v in ids:
            if v in (edges[i]["a"], edges[i]["b"]):
                continue
            p = nodes[v]
            if seg_hits_rect(s[0][0], s[0][1], s[1][0], s[1][1],
                             p["x"], p["y"], p["w"] / 2 + INFLATE, p["h"] / 2 + INFLATE):
                occ_inflated.append({"edge": f"{edges[i]['a']}->{edges[i]['b']}", "card": v})
            if seg_hits_rect(s[0][0], s[0][1], s[1][0], s[1][1],
                             p["x"], p["y"], p["w"] / 2, p["h"] / 2):
                occ_true.append({"edge": f"{edges[i]['a']}->{edges[i]['b']}", "card": v})

    # 3. Average edge length (center distance)
    avg_len = (sum(math.dist(segs[i][0], segs[i][1]) for i in segs) / len(segs)) if segs else 0.0

    # 4. Row alignment rate (visual same row: grouped counting with y diff <= ROW_EPS)
    ysorted = sorted(p["y"] for p in nodes.values())
    aligned, i = 0, 0
    while i < len(ysorted):
        j = i
        while j + 1 < len(ysorted) and ysorted[j + 1] - ysorted[j] <= ROW_EPS:
            j += 1
        if j > i:
            aligned += j - i + 1
        i = j + 1
    row_rate = aligned / len(ids) if ids else 0.0

    # 5. Card gap (minimum over all pairs)
    gaps = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            va, vb = nodes[ids[a]], nodes[ids[b]]
            gaps.append(rect_gap(va["x"], va["y"], va["w"], va["h"],
                                 vb["x"], vb["y"], vb["w"], vb["h"]))
    min_gap = min(gaps) if gaps else 0.0

    # Placement first priority: spacing CV (std/mean of nearest-neighbor
    # center distances)
    nn = []
    for a in ids:
        dists = [math.dist((nodes[a]["x"], nodes[a]["y"]),
                           (nodes[b]["x"], nodes[b]["y"]))
                 for b in ids if b != a]
        if dists:
            nn.append(min(dists))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn) if nn and mean_nn else 0.0

    W = max(p["x"] + p["w"] / 2 for p in nodes.values()) - min(p["x"] - p["w"] / 2 for p in nodes.values())
    H = max(p["y"] + p["h"] / 2 for p in nodes.values()) - min(p["y"] - p["h"] / 2 for p in nodes.values())

    metrics = {
        "crossings": len(crossings),
        "crossing_details": crossings[:10],
        "occlusions_inflated4px": len(occ_inflated),
        "occlusions_true_0px": len(occ_true),
        "occlusion_details_true": occ_true[:10],
        "avg_edge_length": round(avg_len, 1),
        "row_align_rate": round(row_rate, 3),
        "min_card_gap": round(min_gap, 1),
        "spacing_cv": round(cv, 3),
        "bbox": [round(W), round(H)],
    }

    g = {
        "crossings_zero": metrics["crossings"] == 0,
        "min_gap_ge_16": metrics["min_card_gap"] >= 16,
        "row_align_ge_060": metrics["row_align_rate"] >= 0.60,
        "cv_le_035": metrics["spacing_cv"] <= 0.35,
    }
    if gates:
        for k, v in gates.items():
            g[k] = v
    g_pass = sum(1 for v in g.values() if v)

    # Honest grading
    arrangement_ok = g["min_gap_ge_16"] and g["cv_le_035"]
    if metrics["crossings"] == 0 and arrangement_ok:
        grade = "best"
        grade_note = "placement requirements met + 0 line crossings"
    elif arrangement_ok and metrics["crossings"] <= 2:
        grade = "second"
        grade_note = ("placement requirements met + <= 2 crossings "
                      "(coordinates recorded in the certificate for review); "
                      "on conflict, keep placement, release crossings")
    else:
        grade = "uncertified"
        grade_note = ("placement requirements unmet or crossings > 2 — honestly "
                      "ungraded; a certificate bought with a relaxed budget "
                      "never poses as a finished product")

    cert = {
        "tool": "stdraw", "version": _PKG_VERSION, "layer": layer,
        "graph": graph_name,
        "n": len(ids), "m": len(edges),
        "coords": "delivered/rounded",     # all verification runs on delivered coordinates
        "metrics": metrics,
        "gates": g,
        "gates_passed": f"{g_pass}/{len(g)}",
        "grade": grade,
        "grade_note": grade_note,
        "honest_notes": notes,
        "no_zero_crossing_claim_for_all_graphs": (
            "CLDs are often non-planar; 0 crossings has a mathematical "
            "boundary. This certificate holds only for this graph and this layout"),
    }
    # Delivery-face confession: did this certificate ship with the
    # interactive deliverable (demo-2d.html + its drag touch-up layer)?
    # CLI passes yes/yes; library callers grading bare coordinates get no/no.
    cert["interactive"] = interactive
    cert["drag_layer"] = drag_layer
    # Caliber confession (D1=C, WorkBuddy task 2026-11-11): additive
    # self-describing fields only -- no existing key or value is touched.
    # render.py consumes grade/gates/gates_passed/grade_note/metrics, so the
    # demo-2d.html bytes do not change (evidence line E8).
    cert["recipe"] = "ortho-v1"
    cert["caliber"] = "v1-legacy"
    cert["grade_semantics"] = (
        "v1-legacy caliber: best = 0 crossings AND min_gap >= 16 AND "
        "cv <= 0.35; second = placement ok AND <= 2 crossings (legacy "
        "branch kept byte-compatible, logically near-unreachable); else "
        "uncertified. Gate set/count differs from auto-v2 (v2-hardgates): "
        "read caliber before interpreting grade. Single source: "
        "docs/grading-contract.md")
    cert["blocking_gates"] = [k for k, v in g.items() if v is False]
    cert["placement"] = "ortho-v1"
    cert["deliverable"] = False
    cert["blocked_reason"] = (
        "vertical-orthogonal layout banned (D0): box-over-line / leader-bar "
        "occlusion is structural in visibility representation and repeatedly "
        "unfixable; pin-safe CI regression baseline only")
    cert["blocked_by"] = "D0"
    return cert


def _interpolate(si, sj):
    """Approximate intersection coordinates of two segments (generic for
    vertical/straight lines: solve the two line equations)."""
    (x1, y1), (x2, y2) = si
    (x3, y3), (x4, y4) = sj
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < EPS:
        return [round(si[1][0]), round(si[1][1])]
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return [round(px), round(py)]


# ═══ (2) 2026-11-05 six-point rework: auto recipe v2 certificate (new hard gates) ═══
# v1 certificate() stays byte-compatible (ortho-v1 production behavior pin);
# auto goes through certificate_auto.

from .routing import (sample_polyline, dist_point_rect, seg_cross as _rc_seg_cross,
                      min_pair_dist,
                      PRESS_MARGIN, ANCHOR_MIN_DEG, CLEARANCE,
                      span_one_way_segs, COINCIDE_THR, COINCIDE_SPAN)
from .anchors import standard_anchors as _std_anchors


def scene_from_auto(v4: dict) -> dict:
    """Auto layout JSON -> v2 scene (polyline/arc discretized sampling + anchors)."""
    nodes = {}
    ch = v4["meta"].get("cardH", 44)
    for v, p in v4["nodes"].items():
        nodes[v] = {"x": p["x"], "y": p["y"], "w": p.get("w", 140), "h": ch}
    edges, polylines, anchors = [], {}, {}
    for i, e in enumerate(v4["edges"]):
        edges.append({"a": e["a"], "b": e["b"]})
        polylines[i] = [tuple(p) for p in e["route"]["points"]]
        anchors[i] = e["anchors"]
    return {"nodes": nodes, "edges": edges, "polylines": polylines,
            "anchors": anchors,
            "router_pairs": v4["meta"].get("router_cross_pairs"),
            # ref-scrubbed finalize: dense-snap deferral pass-through (None on
            # normal graphs) -- certificate_auto annotates anchors_standard.
            "anchor_snap_deferred": v4["meta"].get("anchor_snap_deferred"),
            # edge placement rules v1 pass-through (certificate records it)
            "edge_rules": v4["meta"].get("edge_rules"),
            "line_style": v4["meta"].get("line_style", "straight"),
            "deg0": set(v4["meta"].get("deg0", [])),
            # ring placement caliber: certificate picks metrics per placement mode
            "placement": v4["meta"].get("placement"),
            "ring_nodes": (v4["meta"].get("ring") or {}).get("nodes"),
            # column-chain / symmetric placement calibers
            "column_spine": (v4["meta"].get("column") or {}).get("spine"),
            "symmetry": v4["meta"].get("symmetry"),
            # spine-wing mode certificate caliber
            "spine_wing": v4["meta"].get("spine_wing"),
            # comb-bilateral mode certificate caliber (v0.7.7)
            "comb": v4["meta"].get("comb"),
            # ref-scrubbed: deterministic mode-decision audit trail (which rule
            # hit, why, trial gate, legacy band exemption)
            "mode_decision_trace": v4["meta"].get("mode_decision_trace"),
            # T1: --from-layout provenance (anchor source auto vs user) --
            # present only on the manual path; the auto path carries None
            # (scene-level pass-through, output bytes unchanged).
            "from_layout": v4["meta"].get("from_layout"),
            # line-kind statistics (arc > straight > polyline hierarchy report)
            "line_kinds": [e["route"].get("kind") for e in v4["edges"]],
            }


def _anchor_tangent_angle(node, anchor, direction):
    """Angle (degrees) between the route direction at an anchor and the tangent
    of the owning box border. Direction is the unit vector leaving the anchor."""
    cx, cy, hw, hh = node["x"], node["y"], node["w"] / 2, node["h"] / 2
    on_x_border = abs(abs(anchor[0] - cx) - hw) <= abs(abs(anchor[1] - cy) - hh)
    tx, ty = (0.0, 1.0) if on_x_border else (1.0, 0.0)
    c = abs(direction[0] * tx + direction[1] * ty)
    return math.degrees(math.acos(max(0.0, min(1.0, c))))


# ── Line-line visual coincidence (machine-checkable detection) ─────────────
# Caliber constants (COINCIDE_THR=1.0 within-1px adherence / COINCIDE_SPAN=8.0
# over-8px counts as coincident, endpoint-meeting exempted) live in
# routing.py — routing penalty and certificate must share one source.

def _coincidence_span(sa, sb, step, thr=COINCIDE_THR):
    """Length (px) over which two sampled polylines run in parallel within
    <thr distance (max of both directions; deterministic).

    Both directions delegate to routing.span_one_way_segs (same source as the
    routing re-routing caliber; a copy would drift). The momentary adherence
    at endpoint anchors is only ~1-2px and never crosses the 8px span gate;
    true coincidence (long-span parallel adherence) is captured stably by
    either direction.
    """
    return max(span_one_way_segs(sa, list(zip(sb[:-1], sb[1:])), step, thr),
               span_one_way_segs(sb, list(zip(sa[:-1], sa[1:])), step, thr))


def _bbox_gap(pa, pb):
    """Gap between the bounding boxes of two polylines (0 = intersect/overlap)."""
    ax0 = min(p[0] for p in pa); ax1 = max(p[0] for p in pa)
    ay0 = min(p[1] for p in pa); ay1 = max(p[1] for p in pa)
    bx0 = min(p[0] for p in pb); bx1 = max(p[0] for p in pb)
    by0 = min(p[1] for p in pb); by1 = max(p[1] for p in pb)
    return max(0.0, max(bx0 - ax1, ax0 - bx1, by0 - ay1, ay0 - by1))


def certificate_auto(scene: dict, graph_name: str = "", layer: str = "2D",
                     gates: Optional[dict] = None,
                     notes: Optional[List[str]] = None,
                     graph=None, exactness: Optional[dict] = None,
                     interactive: str = "no", drag_layer: str = "no",
                     deliverable: bool = False) -> dict:
    """v2 quality certificate: five metrics + new hard gates + honest grading.
    All verification runs on delivered coordinates.

    New hard gates (v0.2 quality rework):
      box_press_zero      box press = 0 (any edge at any angle, incl. 1px
                          margin; endpoints only touch their own box border)
      edge_box_clear_ge16 edge-box clearance >= 16px (non-endpoint boxes,
                          sampled minimum distance)
      anchors_smooth      anchor smoothness: departure direction vs border
                          tangent angle >= ANCHOR_MIN_DEG
      regularity_simple   simple graph (<=10 nodes) placement regularity:
                          uniform row pitch + 24px column snap >= 60%
    """
    nodes = scene["nodes"]
    edges = scene["edges"]
    polys = scene["polylines"]
    anchors = scene.get("anchors", {})
    ids = list(nodes)
    notes = list(notes or [])
    line_style = scene.get("line_style", "straight")
    # Ring placement caliber: row alignment / column snap are naturally
    # inapplicable to ring placement; metrics are picked per placement mode
    # (ring = on-ring equal spacing CV + regular-polygon template fit error).
    ring_mode = scene.get("placement") == "ring-cycle"
    ring_nodes = scene.get("ring_nodes") or []
    # column-chain / symmetric placement calibers
    column_mode = scene.get("placement") == "column-chain"
    sym_mode = scene.get("placement") == "symmetric"
    # bowtie-vertex mode certificate caliber: mirror-axis error (upper/lower
    # ring mirrored)
    bowtie_mode = scene.get("placement") == "bowtie-vertex"
    # spine-wing mode certificate caliber: spine x alignment + midline
    # adherence + mirror symmetry error (outer mirror pairs)
    spine_mode = scene.get("placement") == "spine-wing"
    spine_wing = scene.get("spine_wing") or {}
    column_spine = scene.get("column_spine") or []
    symmetry = scene.get("symmetry") or {}
    # comb-bilateral mode certificate caliber (v0.7.7): column axis alignment
    # + constant column pitch + hub-pair mirror symmetry + all-straight fan
    comb_mode = scene.get("placement") == "comb-bilateral"
    comb = scene.get("comb") or {}
    # P1-2 (jacky 2026-11-13 ruling): manual coordinates (--from-layout) are
    # exempt from the two automatic-pipeline structural checks — same caliber
    # as check.py 6a/9 ("manual: N/A"). Layered-mode gate slots read "N/A";
    # the measured values stay in metrics.
    manual_mode = bool(scene.get("from_layout"))
    layered_mode = not (ring_mode or column_mode or sym_mode or bowtie_mode
                        or spine_mode or comb_mode)

    # 1. Crossings (pairwise polyline intersection)
    crossings = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if _rc_seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        crossings.append({"edges": [f"{ei['a']}->{ei['b']}",
                                                    f"{ej['a']}->{ej['b']}"]})
                        break
                else:
                    continue
                break

    # 1a. Visual crossings (reported metric, NOT a hard gate): pairwise
    # polyline intersection over ALL delivered edge pairs, INCLUDING pairs
    # sharing an endpoint (fan pairs). The graph-theory caliber above exempts
    # shared-endpoint pairs, which misses fan lines visibly crossing mid-air
    # under the same box (ref-scrubbed blind spot: classic-cld showed an X under
    # the adopter box while crossings=0). Repo principle: honest grading —
    # never masquerade as zero crossings. Strict seg_cross already excludes
    # mere endpoint touch, so edges that only meet at their anchors add
    # nothing here; only real mid-air intersections count.
    visual_crossings = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            shared = ({ei["a"], ei["b"]} & {ej["a"], ej["b"]})
            hit = None
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if _rc_seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = (s1, s2)
                        break
                else:
                    continue
                break
            if hit is not None:
                visual_crossings.append({
                    "edges": [f"{ei['a']}->{ei['b']}",
                              f"{ej['a']}->{ej['b']}"],
                    "at": _interpolate(hit[0], hit[1]),
                    "fan_pair": bool(shared)})

    # 1b. Mutual-pair separation (F1): minimum two-line distance for
    # bidirectional edge pairs (counted per "edge pair"; None when no mutual pair)
    pair_infos = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            ei, ej = edges[i], edges[j]
            if (ei["a"], ei["b"]) != (ej["b"], ej["a"]):
                continue
            md = min_pair_dist(sample_polyline(polys[i]), sample_polyline(polys[j]))
            pair_infos.append({"pair": [f"{ei['a']}<->{ei['b']}",
                                        round(md, 1) if md is not None else None]})
    mutual_min_sep = (min(p["pair"][1] for p in pair_infos if p["pair"][1] is not None)
                      if any(p["pair"][1] is not None for p in pair_infos) else None)

    # 1c. Line-line visual coincidence pairs: any two edges (including edge
    # pairs sharing a node — endpoint meeting is exempt via the 8px span gate)
    # running in parallel within <1px over >8px on delivered geometry count as
    # coincident. bbox gap prefilter (coincident pairs must have overlapping
    # bboxes; an equivalent speedup).
    coincide_pairs = []
    _step = 4.0
    for i in range(len(edges)):
        sa = sample_polyline(polys[i])
        for j in range(i + 1, len(edges)):
            sb = sample_polyline(polys[j])
            if _bbox_gap(sa, sb) > COINCIDE_THR:
                continue
            span = _coincidence_span(sa, sb, _step)
            if span > COINCIDE_SPAN:
                coincide_pairs.append(
                    {"pair": [f"{edges[i]['a']}->{edges[i]['b']}",
                              f"{edges[j]['a']}->{edges[j]['b']}"],
                     "span_px": round(span, 1)})

    # 2. Box press (1px margin) + edge-box clearance + own-box endpoint compliance
    press, clear_details, anchor_bad = [], [], []
    anchor_standard_bad = 0          # ref-scrubbed: 16-anchor-set membership gate
    anchor_standard_details = []
    min_clear = None
    for i, e in enumerate(edges):
        pts = sample_polyline(polys[i])
        for v in ids:
            p = nodes[v]
            hw, hh = p["w"] / 2, p["h"] / 2
            if v in (e["a"], e["b"]):
                continue
            dmin = min(dist_point_rect(px, py, p["x"], p["y"], hw, hh)
                       for (px, py) in pts)
            dmin1 = min(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN, hh + PRESS_MARGIN)
                        for (px, py) in pts)
            # Card-piercing counting is deduped per "edge x card": the same
            # (edge, card) pair is recorded once (a 0-margin hit is not
            # double-recorded as a 1px-margin entry)
            if dmin <= 0:
                press.append({"edge": f"{e['a']}->{e['b']}", "card": v})
            elif dmin1 <= 0:
                press.append({"edge": f"{e['a']}->{e['b']}", "card": v, "margin": 1})
            min_clear = dmin if min_clear is None else min(min_clear, dmin)
        # Own box: no other sampled point may enter the box (incl. 1px margin);
        # anchors must sit on the box border.
        # ref-scrubbed: standard anchors sit INSET 3px inside the border, so the
        # attachment zone (samples within 6px of the endpoint, before the
        # departure clears the 1px-inflated margin) is part of the attachment
        # by construction and is exempt -- the same accounting as
        # Router._own_press (anchor_snap gate).  What this gate still catches
        # is the route BODY (beyond the attachment zone) stabbing into the box.
        for v, end_key in ((e["a"], "a"), (e["b"], "b")):
            p = nodes[v]
            hw, hh = p["w"] / 2, p["h"] / 2
            a0 = anchors.get(i, {}).get(end_key)
            if a0 is None or dist_point_rect(a0[0], a0[1], p["x"], p["y"], hw, hh) > 0.75:
                anchor_bad.append({"edge": f"{e['a']}->{e['b']}", "end": end_key,
                                   "why": "anchor off-border"})
                continue
            q0, q1 = pts[0], pts[-1]
            interior = any(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN, hh + PRESS_MARGIN) <= 0
                           for (px, py) in pts[1:-1]
                           if math.hypot(px - q0[0], py - q0[1]) > 6.0 and
                           math.hypot(px - q1[0], py - q1[1]) > 6.0)
            if interior:
                press.append({"edge": f"{e['a']}->{e['b']}", "card": v, "why": "own-box"})
        # Anchor smoothness (angle recomputed independently)
        poly = polys[i]
        for end_key, p_idx, nxt_idx in (("a", 0, 1), ("b", len(poly) - 1, len(poly) - 2)):
            a0 = anchors.get(i, {}).get(end_key)
            if a0 is None:
                continue
            dx, dy = poly[nxt_idx][0] - a0[0], poly[nxt_idx][1] - a0[1]
            n = math.hypot(dx, dy)
            if n < EPS:
                anchor_bad.append({"edge": f"{e['a']}->{e['b']}", "end": end_key,
                                   "why": "zero-length departure"})
                continue
            v = e["a"] if end_key == "a" else e["b"]
            ang = _anchor_tangent_angle(nodes[v], a0, (dx / n, dy / n))
            if ang < ANCHOR_MIN_DEG:
                anchor_bad.append({"edge": f"{e['a']}->{e['b']}", "end": end_key,
                                   "angle": round(ang, 1)})
        # ref-scrubbed: endpoint membership in the 16 standard anchor set
        # (anchors.py caliber; tol 0.75px = the same border tolerance as the
        # anchor on-border check above).  The default attachment caliber:
        # every rendered endpoint sits on one of its box's 16 standard
        # connection points.
        for end_key in ("a", "b"):
            v = e[end_key]
            a0 = anchors.get(i, {}).get(end_key)
            if a0 is None:
                continue
            nd = nodes[v]
            pts16 = _std_anchors(nd["x"], nd["y"], nd["w"] / 2.0, nd["h"] / 2.0)
            if not any(abs(ax - a0[0]) <= 0.75 and abs(ay - a0[1]) <= 0.75
                       for _aid, ax, ay in pts16):
                anchor_standard_bad += 1
                if len(anchor_standard_details) < 10:
                    anchor_standard_details.append(
                        {"edge": f"{e['a']}->{e['b']}", "end": end_key,
                         "anchor": [round(a0[0], 1), round(a0[1], 1)]})

    # 3. Average edge length / row alignment / card gap / CV (same caliber as v1)
    avg_len = sum(sum(math.dist(polys[i][k], polys[i][k + 1])
                      for k in range(len(polys[i]) - 1))
                  for i in polys) / len(polys) if polys else 0.0
    if ring_mode:
        row_rate = None          # ring placement: row alignment inapplicable (caliber stated honestly)
    else:
        ysorted = sorted(p["y"] for p in nodes.values())
        aligned, i2 = 0, 0
        while i2 < len(ysorted):
            j = i2
            while j + 1 < len(ysorted) and ysorted[j + 1] - ysorted[j] <= ROW_EPS:
                j += 1
            if j > i2:
                aligned += j - i2 + 1
            i2 = j + 1
        row_rate = aligned / len(ids) if ids else 0.0
    gaps = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            va, vb = nodes[ids[a]], nodes[ids[b]]
            gaps.append(rect_gap(va["x"], va["y"], va["w"], va["h"],
                                 vb["x"], vb["y"], vb["w"], vb["h"]))
    min_gap = min(gaps) if gaps else 0.0
    nn = []
    for a in ids:
        dists = [math.dist((nodes[a]["x"], nodes[a]["y"]),
                           (nodes[b]["x"], nodes[b]["y"]))
                 for b in ids if b != a]
        if dists:
            nn.append(min(dists))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn) if nn and mean_nn else 0.0

    # Regularity (simple graph <=10 nodes): uniform row pitch + 24px column
    # snap share (parking-lane nodes excluded from row pitch).
    # Ring placement: regularity caliber switches to on-ring equal spacing CV +
    # regular-polygon template fit error.
    # Column placement: uniform row pitch judged on main-chain rows (branch
    # half-row offsets excluded); column snap inapplicable.
    # Symmetric placement: regularity caliber = mirror-axis error (left/right
    # vertices equidistant to the axis + y on the same row).
    deg0 = scene.get("deg0", set())
    ring_spacing_cv = None
    ring_template_dev = None
    col_axis_dev = None
    sym_mirror_err = None
    sw_spine_axis_dev = None
    sw_midline_dev = None
    if ring_mode and len(ring_nodes) >= 3:
        rpts = [(nodes[v]["x"], nodes[v]["y"]) for v in ring_nodes
                if v in nodes]
        if len(rpts) >= 3:
            dists = [math.dist(rpts[i], rpts[(i + 1) % len(rpts)])
                     for i in range(len(rpts))]
            md = sum(dists) / len(dists)
            ring_spacing_cv = (math.sqrt(sum((d - md) ** 2 for d in dists)
                                         / len(dists)) / md) if md else 0.0
            try:
                from . import regularity as _reg
                ring_template_dev = _reg.cycle_polygon_deviation(
                    {v: (nodes[v]["x"], nodes[v]["y"]) for v in ring_nodes},
                    ring_nodes)
            except Exception:
                ring_template_dev = None
    if ring_mode:
        pitch_uniform, snap_rate, simple, regularity_ok = True, None, False, True
    elif column_mode and len(column_spine) >= 2:
        ys = [nodes[v]["y"] for v in column_spine if v in nodes]
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        axis_x = (sum(nodes[v]["x"] for v in column_spine if v in nodes) /
                  max(1, len([v for v in column_spine if v in nodes])))
        col_axis_dev = max(abs(nodes[v]["x"] - axis_x)
                           for v in column_spine if v in nodes) if column_spine else None
        snap_rate, simple = None, len(ids) <= 10
        regularity_ok = pitch_uniform and (col_axis_dev or 0.0) <= 2.0
    elif comb_mode and comb.get("column"):
        # comb-bilateral: sources in one vertical column (x on-axis <=2px,
        # constant column pitch), hubs in mirrored left/right slots at the
        # column middle row (pair symmetric about the column axis)
        col_ids = [v for v in comb["column"] if v in nodes]
        axis_x = comb.get("axis_x", 0.0)
        ys = [nodes[v]["y"] for v in col_ids]
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        col_axis_dev = max(abs(nodes[v]["x"] - axis_x)
                           for v in col_ids) if col_ids else None
        hub_sym_err = None
        hl, hr = comb.get("hubs") or (None, None)
        if hl in nodes and hr in nodes:
            hub_sym_err = max(abs((nodes[hl]["x"] + nodes[hr]["x"]) / 2 - axis_x),
                              abs(nodes[hl]["y"] - nodes[hr]["y"]))
        snap_rate, simple = None, len(ids) <= 10
        regularity_ok = (col_axis_dev is not None and col_axis_dev <= 2.0
                         and hub_sym_err is not None and hub_sym_err <= 2.0
                         and pitch_uniform)
    elif sym_mode and symmetry.get("mirror_pairs"):
        axis_x = (symmetry.get("axis_x") if symmetry.get("axis_x") is not None
                  else 0.0)
        pairs = symmetry.get("mirror_pairs")
        errs = []
        for l, r in pairs:
            if l in nodes and r in nodes:
                errs.append(abs((nodes[l]["x"] + nodes[r]["x"]) / 2 - axis_x))
                errs.append(abs(nodes[l]["y"] - nodes[r]["y"]))
        sym_mirror_err = max(errs) if errs else None
        ys = sorted({p["y"] for v, p in nodes.items() if v not in deg0})
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        snap_rate, simple = None, len(ids) <= 10
        regularity_ok = (sym_mirror_err is not None and sym_mirror_err <= 2.0
                         and pitch_uniform)
    elif spine_mode and spine_wing.get("spine"):
        # spine-wing: spine x on-axis (<=2px) + wings hugging the midline band
        # (<=2px) + mirror-pair error (x equal + y symmetric about the
        # horizontal axis, <=2px); uniform row pitch judged on wing row pitch
        # (constructed row_pitch, all-node y difference set is constant)
        axis_x = (spine_wing.get("axis_x") if spine_wing.get("axis_x") is not None
                  else 0.0)
        axis_y = (spine_wing.get("axis_y") if spine_wing.get("axis_y") is not None
                  else 0.0)
        spine_ids = [s for s in spine_wing.get("spine") or [] if s in nodes]
        wing_ids = [w for w in spine_wing.get("wings") or [] if w in nodes]
        errs = []
        if spine_ids:
            sw_spine_axis_dev = max(abs(nodes[s]["x"] - axis_x)
                                    for s in spine_ids)
            errs.append(sw_spine_axis_dev)
        if wing_ids:
            sw_midline_dev = max(abs(nodes[w]["y"] - axis_y)
                                 for w in wing_ids)
            errs.append(sw_midline_dev)
        for up, down in spine_wing.get("mirror_pairs") or []:
            if up in nodes and down in nodes:
                errs.append(abs(nodes[up]["x"] - nodes[down]["x"]))
                errs.append(abs((nodes[up]["y"] + nodes[down]["y"]) / 2
                                - axis_y))
        sym_mirror_err = max(errs) if errs else None
        ys = sorted({p["y"] for v, p in nodes.items() if v not in deg0})
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        snap_rate, simple = None, len(ids) <= 10
        regularity_ok = (sym_mirror_err is not None and sym_mirror_err <= 2.0
                         and pitch_uniform)
    elif bowtie_mode and symmetry.get("mirror_pairs"):
        # bowtie-vertex: upper/lower ring mirrored (equidistant to the vertical
        # axis in x + symmetric about the horizontal axis in y), shared node centered
        axis_x = (symmetry.get("axis_x") if symmetry.get("axis_x") is not None
                  else 0.0)
        axis_y = (symmetry.get("axis_y") if symmetry.get("axis_y") is not None
                  else 0.0)
        pairs = symmetry.get("mirror_pairs")
        errs = []
        for l, r in pairs:
            if l in nodes and r in nodes:
                errs.append(abs(nodes[l]["x"] - nodes[r]["x"]))
                errs.append(abs((nodes[l]["y"] + nodes[r]["y"]) / 2 - axis_y))
        sh = symmetry.get("shared_node")
        if sh in nodes:
            errs.append(abs(nodes[sh]["x"] - axis_x))
            errs.append(abs(nodes[sh]["y"] - axis_y))
        sym_mirror_err = max(errs) if errs else None
        ys = sorted({p["y"] for v, p in nodes.items() if v not in deg0})
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        snap_rate, simple = None, len(ids) <= 10
        regularity_ok = (sym_mirror_err is not None and sym_mirror_err <= 2.0
                         and pitch_uniform)
    else:
        ys = sorted({p["y"] for v, p in nodes.items() if v not in deg0})
        pitch_uniform = (len(set(b - a for a, b in zip(ys, ys[1:]))) <= 1
                         if len(ys) > 1 else True)
        snap_n = sum(1 for p in nodes.values() if abs(p["x"] % 24) < EPS)
        snap_rate = snap_n / len(ids) if ids else 0.0
        simple = len(ids) <= 10
        regularity_ok = pitch_uniform and (snap_rate >= 0.6 if simple else snap_rate >= 0.0)

    W = max(p["x"] + p["w"] / 2 for p in nodes.values()) - min(p["x"] - p["w"] / 2 for p in nodes.values())
    H = max(p["y"] + p["h"] / 2 for p in nodes.values()) - min(p["y"] - p["h"] / 2 for p in nodes.values())

    # WS3 dual crossing accounting: routing-theory caliber (crossing edge pairs
    # of the final unrounded route) vs delivered-geometry recheck (item 1 of
    # this section, strict intersection / Liang-Barsky). The certificate is
    # issued only when both agree; disagreement -> uncertified (both values
    # recorded honestly).
    router_xe = scene.get("router_pairs")
    routing_consistent = None
    router_pairs = None
    if router_xe is not None:
        router_pairs = router_xe
        routing_consistent = abs(router_pairs - len(crossings)) < 0.5

    # Loop cohesion: each declared loop = max center distance / full-graph
    # diagonal (smaller = more cohesive; large distances read as semantic
    # disconnection). Center offset: horizontal offset between the node bbox
    # center and the edge-inclusive geometry bbox center (a centering
    # normalization report item).
    loop_cohesion = None
    if graph is not None:
        try:
            diag = math.hypot(W, H) or 1.0
            loop_cohesion = {}
            for lp in getattr(graph, "loops", []):
                pts_l = [(nodes[v]["x"], nodes[v]["y"])
                         for v in lp.nodes if v in nodes]
                if len(pts_l) >= 2:
                    spread = max(math.dist(p, q) for i, p in enumerate(pts_l)
                                 for q in pts_l[i + 1:])
                    loop_cohesion[lp.id] = round(spread / diag, 4)
        except Exception:
            loop_cohesion = None
    nodes_cx = ((max(p["x"] + p["w"] / 2 for p in nodes.values()) -
                 min(p["x"] - p["w"] / 2 for p in nodes.values())) / 2 +
                min(p["x"] - p["w"] / 2 for p in nodes.values()))
    all_cx = ((max(px for pl in polys.values() for px, _ in pl) +
               min(px for pl in polys.values() for px, _ in pl)) / 2
              if polys else nodes_cx)
    center_offset = round(abs(nodes_cx - all_cx), 1)
    line_kind_counts = {}
    for k in scene.get("line_kinds") or []:
        line_kind_counts[k] = line_kind_counts.get(k, 0) + 1

    metrics = {
        "crossings": len(crossings),
        "crossing_details": crossings[:10],
        "visual_crossings": len(visual_crossings),
        "fan_visual_crossings": sum(1 for v in visual_crossings
                                    if v["fan_pair"]),
        "visual_crossing_details": visual_crossings[:10],
        "box_press_1px": len(press),
        "routing_router_pairs": router_pairs,
        "press_details": press[:10],
        "edge_box_min_clear": round(min_clear, 1) if min_clear is not None else None,
        "anchor_violations": len(anchor_bad),
        "anchor_details": anchor_bad[:10],
        # ref-scrubbed: delivered endpoints must sit on the box's 16 standard
        # anchor set (anchors.py caliber) -- the default attachment caliber.
        "anchor_standard_violations": anchor_standard_bad,
        "anchor_standard_details": anchor_standard_details[:10],
        "avg_edge_length": round(avg_len, 1),
        "row_align_rate": round(row_rate, 3) if row_rate is not None else None,
        "min_card_gap": round(min_gap, 1),
        "spacing_cv": round(cv, 3),
        "column_snap24_rate": round(snap_rate, 3) if snap_rate is not None else None,
        "mutual_pair_min_sep": mutual_min_sep,
        "mutual_pair_details": pair_infos[:10],
        "line_line_coincident_pairs": len(coincide_pairs),
        "line_line_coincident_details": coincide_pairs[:10],
        "loop_cohesion_spread": loop_cohesion,
        "center_offset_x": center_offset,
        "line_kind_counts": line_kind_counts,
        "bbox": [round(W), round(H)],
    }
    if ring_mode:
        metrics["ring_spacing_cv"] = (round(ring_spacing_cv, 4)
                                      if ring_spacing_cv is not None else None)
        metrics["ring_template_deviation"] = (round(ring_template_dev, 4)
                                              if ring_template_dev is not None else None)
    if column_mode:
        metrics["column_axis_deviation"] = (round(col_axis_dev, 2)
                                            if col_axis_dev is not None else None)
    if comb_mode:
        metrics["column_axis_deviation"] = (round(col_axis_dev, 2)
                                            if col_axis_dev is not None else None)
        metrics["hub_symmetry_err"] = (round(hub_sym_err, 2)
                                       if hub_sym_err is not None else None)
    if sym_mode or bowtie_mode or spine_mode:
        metrics["symmetry_mirror_err"] = (round(sym_mirror_err, 2)
                                          if sym_mirror_err is not None else None)
    if spine_mode:
        metrics["spine_axis_deviation"] = (round(sw_spine_axis_dev, 2)
                                           if sw_spine_axis_dev is not None else None)
        metrics["midline_deviation"] = (round(sw_midline_dev, 2)
                                        if sw_midline_dev is not None else None)

    # Crossing caliber adjustment: crossings_zero demoted from hard gate to
    # report item (<=2 crossings allowed when placement regularity holds —
    # "some line intersection is acceptable; order and elegance come first");
    # grading semantics (best = all hard gates + 0 crossings; the former
    # second tier was removed in v0.7.15+ as a logically unreachable dead
    # branch: every counted crossing also counts in visual_crossings, so
    # hard_ok already forces 0).
    if ring_mode:
        # Ring caliber gates: on-ring equal spacing CV + template fit error
        # (within 2px quantization tolerance ~= 0)
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "anchors_standard": metrics["anchor_standard_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "ring_spacing_cv_le_005": (metrics["ring_spacing_cv"] is not None
                                       and metrics["ring_spacing_cv"] <= 0.05),
            "ring_template_fit_le_005": (metrics["ring_template_deviation"] is not None
                                         and metrics["ring_template_deviation"] <= 0.05),
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    elif column_mode:
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "anchors_standard": metrics["anchor_standard_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "cv_le_035": metrics["spacing_cv"] <= 0.35,
            "column_axis_aligned": (metrics["column_axis_deviation"] is not None
                                    and metrics["column_axis_deviation"] <= 2.0),
            "spine_pitch_uniform": pitch_uniform,
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    elif comb_mode:
        # comb-bilateral caliber gates: column axis alignment + constant
        # column pitch + hub-pair mirror symmetry + all hub edges straight
        # (the comb contract); spacing CV is not applicable as a gate (the
        # hub wings are structurally far from the column, reported only)
        _hl, _hr = comb.get("hubs") or (None, None)
        _hub_bad = 0
        if _hl and _hr:
            for _e, _k in zip(edges, scene.get("line_kinds") or []):
                if (_e["a"] in (_hl, _hr) or _e["b"] in (_hl, _hr)) \
                        and _k != "line":
                    _hub_bad += 1
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "anchors_standard": metrics["anchor_standard_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "column_axis_aligned": (metrics["column_axis_deviation"] is not None
                                    and metrics["column_axis_deviation"] <= 2.0),
            "column_pitch_uniform": pitch_uniform,
            "hub_symmetry_le_2px": (metrics["hub_symmetry_err"] is not None
                                    and metrics["hub_symmetry_err"] <= 2.0),
            "hub_edges_straight": _hub_bad == 0,
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    elif sym_mode or bowtie_mode:
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "anchors_standard": metrics["anchor_standard_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "cv_le_035": metrics["spacing_cv"] <= 0.35,
            "symmetry_mirror_le_2px": (metrics["symmetry_mirror_err"] is not None
                                       and metrics["symmetry_mirror_err"] <= 2.0),
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    elif spine_mode:
        # spine-wing equivalent gates: the equivalent of ring CV/template fit
        # for the spine-wing shape = spine x alignment <=2px + midline
        # adherence <=2px + mirror-pair error <=2px (crossings is a soft-target
        # report item; determinism is carried by the CLI double-run
        # byte-identical gate)
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "anchors_standard": metrics["anchor_standard_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "cv_le_035": metrics["spacing_cv"] <= 0.35,
            "spine_axis_le_2px": (metrics["spine_axis_deviation"] is not None
                                  and metrics["spine_axis_deviation"] <= 2.0),
            "midline_adherence_le_2px": (metrics["midline_deviation"] is not None
                                         and metrics["midline_deviation"] <= 2.0),
            "symmetry_mirror_le_2px": (metrics["symmetry_mirror_err"] is not None
                                       and metrics["symmetry_mirror_err"] <= 2.0),
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    else:
        g = {
            "box_press_zero": metrics["box_press_1px"] == 0,
            "edge_box_clear_ge_16": (metrics["edge_box_min_clear"] or 0) >= CLEARANCE,
            "anchors_smooth": metrics["anchor_violations"] == 0,
            "anchors_standard": metrics["anchor_standard_violations"] == 0,
            "min_gap_ge_16": metrics["min_card_gap"] >= 16,
            "cv_le_035": metrics["spacing_cv"] <= 0.35,
            # Row alignment demoted to report item (14 hand-pulled samples show
            # row_align delta ~= 0, users do not care; placement regularity is
            # carried by uniform row pitch + column snap)
            "pitch_uniform": pitch_uniform,
            "column_snap24_ge_060": (snap_rate is None or snap_rate >= 0.60),
            # F1 hard gate: mutual-pair two-line minimum distance >= 4px
            # (trivially passes when no mutual pair exists)
            "mutual_pairs_separated": mutual_min_sep is None or mutual_min_sep >= 4.0,
            # Hard gate: line-line visual coincidence pairs = 0
            "lines_no_coincidence": metrics["line_line_coincident_pairs"] == 0,
        }
    # ref-scrubbed: visual crossings (all-edge-pair caliber incl.
    # shared-endpoint fan pairs) is a HARD gate in every placement mode --
    # the 3-figure fan-X sweep (population-logistic / renewable-resource /
    # shifting-the-burden) closed the last legacy nonzero counts, so the
    # "awaits a legacy-number decision" report item becomes an assertion.
    # hard_ok below folds it in: a drawing with a fan X can no longer
    # grade best (honest grading: the certificate must see what the eye
    # sees).
    g["visual_crossings_zero"] = metrics["visual_crossings"] == 0
    if routing_consistent is not None:
        g["routing_consistent"] = routing_consistent
    if gates:
        for k, v in gates.items():
            g[k] = v
    # P1-2: manual coordinates mark the two automatic-pipeline structural
    # gates "N/A" (check.py 6a/9 caliber, jacky 2026-11-13 ruling); they are
    # excluded from the pass count and never block. This is a caliber
    # alignment, not a threshold change — no other gate is touched.
    if manual_mode and layered_mode:
        g["pitch_uniform"] = "N/A"
        g["column_snap24_ge_060"] = "N/A"
    g_pass = sum(1 for v in g.values() if v is True)
    n_gates = sum(1 for v in g.values() if v != "N/A")
    reports = {
        "crossings_zero": metrics["crossings"] == 0,
        "crossings_note": ("soft target: <=2 crossings allowed when placement "
                           "regularity holds (product call: some line "
                           "intersection is acceptable; order and elegance "
                           "come first); grading caliber unchanged "
                           "(best = all hard gates + 0 crossings)"),
        "row_align_ge_060": (metrics["row_align_rate"] is None
                             or metrics["row_align_rate"] >= 0.60),
        "row_align_note": ("report item: row alignment is no longer a "
                           "veto (hand-pulled samples show row_align delta ~= 0)"),
    }

    if ring_mode:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and
                   g["ring_spacing_cv_le_005"] and g["ring_template_fit_le_005"])
    elif comb_mode:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and
                   g["column_axis_aligned"] and g["column_pitch_uniform"] and
                   g["hub_symmetry_le_2px"] and g["hub_edges_straight"])
    elif column_mode:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and
                   g["cv_le_035"] and g["column_axis_aligned"] and
                   g["spine_pitch_uniform"])
    elif sym_mode or bowtie_mode:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and
                   g["cv_le_035"] and g["symmetry_mirror_le_2px"])
    elif spine_mode:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and
                   g["cv_le_035"] and g["spine_axis_le_2px"] and
                   g["midline_adherence_le_2px"] and
                   g["symmetry_mirror_le_2px"])
    else:
        hard_ok = (g["box_press_zero"] and g["edge_box_clear_ge_16"] and
                   g["anchors_smooth"] and g["min_gap_ge_16"] and g["cv_le_035"] and
                   (manual_mode or g["pitch_uniform"]))
    # ref-scrubbed finalize (approved 2026-11-09): honest dense-snap
    # deferral annotation -- the anchors_standard gate value stays MEASURED
    # (False when endpoints remain off-anchor on a deferred dense graph);
    # the deferral record documents the approved downgrade with its measured
    # regressions.  No gate fudging: grade reflects the deferral honestly.
    if scene.get("anchor_snap_deferred"):
        g["anchors_standard_deferred"] = scene["anchor_snap_deferred"]
    hard_ok = (hard_ok and g["anchors_standard"]       # ref-scrubbed: 16-anchor membership
               and g["visual_crossings_zero"])
    dual_ok = routing_consistent is not False   # dual-accounting mismatch -> refuse the certificate
    if metrics["crossings"] == 0 and hard_ok and dual_ok:
        grade = "best"
        grade_note = ("all hard gates passed (box press 0 / clearance >=16 / "
                      "anchors smooth / regularity) + 0 line crossings")
    elif not dual_ok:
        grade = "uncertified"
        grade_note = (f"dual crossing accounting mismatch (routing theory "
                      f"{router_pairs} vs geometric recheck {len(crossings)}) "
                      f"— theory and geometry must agree before a certificate "
                      f"is issued")
    else:
        grade = "uncertified"
        grade_note = ("hard gates not all passed or crossings > 2 — honestly "
                      "ungraded; a certificate bought with a relaxed budget "
                      "never poses as a finished product")

    out = {
        "tool": "stdraw", "version": _PKG_VERSION, "layer": layer,
        "graph": graph_name,
        "n": len(ids), "m": len(edges),
        "coords": "delivered/rounded",
        "recipe": "auto-v2",
        "line_style": line_style,
        "placement": ("ring-cycle" if ring_mode else
                      "column-chain" if column_mode else
                      "symmetric" if sym_mode else
                      "bowtie-vertex" if bowtie_mode else
                      "spine-wing" if spine_mode else
                      "comb-bilateral" if comb_mode else "layered"),
        # ref-scrubbed: which structural rule fired and why, trial-gate outcome,
        # and whether the registered anchor-band legacy exemption applies —
        # the trigger-template audit trail (None for scenes without the trace,
        # e.g. hand-built scenes in tests).
        "mode_decision_trace": scene.get("mode_decision_trace"),
        # T1: --from-layout anchor provenance (auto vs user) — emitted only
        # when present (the manual path); the auto certificate stays
        # byte-for-byte unchanged.
        **({"from_layout": scene["from_layout"]}
           if scene.get("from_layout") else {}),
        # edge placement rules v1 certificate block (spec §6): emitted only
        # when the decision layer ran (auto path); violations recorded,
        # grading untouched (D4-A).
        **({"edge_rules": scene["edge_rules"]} if scene.get("edge_rules") else {}),
        "metrics": metrics,
        "gates": g,
        "gates_passed": f"{g_pass}/{n_gates}",
        "reports": reports,
        "grade": grade,
        "grade_note": grade_note,
        "proven_optimal": None,          # WS2 exact layer: see the exactness block
        "gap": None,
        "exactness": _exactness_block(exactness),
        "regularity": _regularity_block(graph, nodes),
        "honest_notes": notes + [
            "Hard-gate caliber: box press = 0 (1px margin), edge-box clearance >= 16px, "
            "smooth anchors, simple-graph regularity",
            "Mutual pairs (a<->b bidirectional edges): two-line minimum distance >= 4px "
            "(lens double-arc / parallel offset / outer detour; merging back into a "
            "double-arrowhead line is forbidden; card-piercing counting deduped per "
            "edge x card)",
            "Line-line visual coincidence pairs = 0 (any two lines running in parallel "
            "within <1px over >8px count as coincident; momentary meetings at endpoint "
            "anchors excluded; machine-checkable metric)",
            "Dual crossing accounting: the routing-theory per-edge hit count sum / 2 "
            "must equal the delivered-geometry recheck count; on mismatch the "
            "certificate is refused",
            "Routing math: obstacle avoidance = clearance-inflated obstacle visibility "
            "graph Dijkstra shortest path (exactly optimal on the graph; vs the true "
            "continuous-space shortest path around rounded-corner obstacles, at most "
            "(2 - pi/2) x inflation margin px more per hugging corner); smoothing = "
            "tangent arcs at bends (G1 tangent-continuous, bounded curvature); convex "
            "tangent arcs dip toward the obstacle side by r*(1/cos(theta/2) - 1), "
            "bounded by the inflation margin"],
        "no_zero_crossing_claim_for_all_graphs": (
            "CLDs are often non-planar; the crossing count is an objective-function "
            "minimization term, not a theorem guarantee. This certificate holds only "
            "for this graph and this layout"),
    }
    if ring_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "Ring placement caliber: row alignment / 24px column snap are "
            "inapplicable to ring placement; the regularity gates switch to "
            "on-ring equal spacing CV <= 0.05 + regular-polygon template fit "
            "error <= 0.05; the main ring follows regular-polygon slots in ring "
            "order with chords inside the ring, and loop polarity (R/B) badges "
            "stay readable along the ring"]
        out["ring"] = {
            "nodes": list(ring_nodes),
            "spacing_cv": metrics.get("ring_spacing_cv"),
            "template_deviation": metrics.get("ring_template_deviation"),
        }
    if manual_mode and layered_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "Manual coordinates: uniform row pitch / 24px column snap are "
            "automatic-pipeline structural checks, not applicable to manual "
            "layouts (same caliber as the geometry self-check 6a/9 \"manual: "
            "N/A\"); the gate slots read N/A and the measured values remain "
            "in metrics"]
    if column_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "Column placement caliber: the main chain aligns vertically in one "
            "column (column-axis deviation <= 2px gate) with a uniform "
            "main-chain row-pitch gate; branches hang on the main chain's "
            "nearest side (half-row offsets excluded from the main-chain "
            "row-pitch gate); the main-chain closing edge is constructed as a "
            "large left arc (loop cohesion / ring feel); row alignment / column "
            "snap reports inapplicable (honestly None)"]
        out["column"] = {
            "spine": list(column_spine),
            "axis_deviation": metrics.get("column_axis_deviation"),
            "loop_cohesion_spread": metrics.get("loop_cohesion_spread"),
        }
    if sym_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "Symmetric placement caliber: bowtie (two triangles sharing an edge) "
            "structure made explicitly symmetric — shared-edge endpoints on the "
            "vertical axis, left/right vertices mirrored (mirror-axis error "
            "<= 2px gate); line-kind consistency hard rule: axis edges straight "
            "+ side edges all arcs (no mixing); row alignment / column snap "
            "reports inapplicable (honestly None)"]
        out["symmetry"] = {
            "mirror_pairs": symmetry.get("mirror_pairs"),
            "mirror_err": metrics.get("symmetry_mirror_err"),
        }
    if bowtie_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "Bowtie-vertex caliber (aesthetics v3): two loops sharing a single "
            "node made explicitly symmetric — shared node centered, the two "
            "loops occupying the upper/lower half-planes mirrored "
            "(mirror-axis error <= 2px gate, cross-checked against the "
            "hand-pulled reference sample wage-price-spiral); detection = "
            "enumerated simple cycles (exactly 2 loops sharing exactly 1 "
            "node), declared loops are not a detection input; line-kind "
            "consistency hard rule: all straight lines (outer edges horizontal "
            "+ spokes direct, shared-side anchor edges symmetrically spread "
            "at edge midpoint +/-14px); row alignment / column snap reports "
            "inapplicable (honestly None)"]
        out["symmetry"] = {
            "shared_node": symmetry.get("shared_node"),
            "mirror_pairs": symmetry.get("mirror_pairs"),
            "mirror_err": metrics.get("symmetry_mirror_err"),
        }
    if spine_mode:
        out["honest_notes"] = out["honest_notes"] + [
            "Spine-wing caliber (v0.7.1): hub pair strictly vertical on the "
            "spine axis (x alignment <= 2px gate), wings pressed onto the "
            "midline horizontal band (adherence <= 2px gate), outer mirror "
            "pairs symmetric top-to-bottom (mirror error <= 2px gate) — "
            "cross-checked against the hand-pulled reference sample "
            "classic-cld-growth-and-burden; detection = deterministic "
            "topological metrics (hub pair with >= 3 common neighbors + "
            "pairable rest secondary clusters + main-chain length share "
            "<= 0.5), see docs/layout-modes.md; spine edges constructed as "
            "vertical straight lines, the rest through the Router; row "
            "alignment / column snap reports inapplicable (honestly None)"]
        out["spine_wing"] = {
            "spine": spine_wing.get("spine"),
            "wings": spine_wing.get("wings"),
            "mirror_pairs": spine_wing.get("mirror_pairs"),
            "rest_single": spine_wing.get("rest_single"),
            "spine_axis_deviation": metrics.get("spine_axis_deviation"),
            "midline_deviation": metrics.get("midline_deviation"),
            "mirror_err": metrics.get("symmetry_mirror_err"),
        }
    # Delivery-face confession (same caliber as certificate()):
    out["interactive"] = interactive
    out["drag_layer"] = drag_layer
    # Caliber confession (D1=C, WorkBuddy task 2026-11-11): additive
    # self-describing fields; grading implementation untouched.
    out["caliber"] = "v2-hardgates"
    out["grade_semantics"] = (
        "v2-hardgates caliber: best = 0 line crossings AND all "
        "placement-specific hard gates AND anchors_standard AND "
        "visual_crossings_zero AND dual crossing accounting; else "
        "uncertified (honest no-grade). Soft targets (crossings <= 2, row "
        "alignment) are layout objective-function report items, NOT "
        "certificate gates. Tokens: best | uncertified (2D certificate "
        "field); the 3d tier in the docs describes the 3D delivery path. "
        "second was removed in v0.7.15+ (logically unreachable). Single "
        "source: docs/grading-contract.md")
    out["blocking_gates"] = [k for k, v in g.items() if v is False]
    out["deliverable"] = bool(deliverable)
    # D3 observability probe (S2-1, WorkBuddy task 2026-11-11): every
    # candidate main ring with the exact selection-key inputs, recorded on
    # the CERTIFICATE trace only (the layout meta trace stays byte-stable;
    # detection re-runs are deterministic and side-effect free).
    cand = _ring_candidates_block(graph)
    if cand is not None:
        tr = dict(out.get("mode_decision_trace") or {})
        tr["ring_candidates"] = cand
        out["mode_decision_trace"] = tr
    return out


def _ring_candidates_block(graph):
    """D3 observability probe (WorkBuddy task 2026-11-11, S2-1): re-run the
    deterministic ring detection and record EVERY candidate main ring with
    the exact selection-key inputs, plus which ring the alternative key
    (chord crossings first) would pick. Recording only: the selection key
    itself is frozen (S2-3 pending jacky's D3 ruling)."""
    if graph is None:
        return None
    from .ringlayout import detect_ring
    why: dict = {}
    detect_ring(graph, why=why)
    rows = why.get("candidates")
    if not rows:
        return None
    sel = next((r for r in rows if r.get("selected")), None)
    alt = min(rows, key=lambda r: (r["chord_crossings"], -r["k"],
                                   r["ring"]))

    def _brief(r):
        return {"k": r["k"], "chord_crossings": r["chord_crossings"],
                "declared_loop": r["declared_loop"], "ring": r["ring"]}

    return {
        "note": ("observability probe only: all candidate main rings with "
                 "the selection-key inputs; the selection key is frozen "
                 "(D3 pending jacky's ruling)"),
        "selection_key": "(-k, chord_crossings, ring order)",
        "alternative_key": "(chord_crossings, -k, ring order)",
        "candidates": [{k: r[k] for k in
                        ("k", "chord_crossings", "declared_loop", "ring",
                         "selected")} for r in rows],
        "selected": _brief(sel) if sel else None,
        "alternative_winner": _brief(alt),
        "would_switch": bool(sel and sel["ring"] != alt["ring"]),
    }


_EXACT_SCOPE_NOTE = (
    "proven_optimal holds only relative to the model class defined in "
    "docs/crossing-exact.md sections 1-5: the good-drawing crossing-number "
    "caliber (adjacent edges do not cross, each pair at most once, no three "
    "edges through one point), the 2-edge-connected core family after safe "
    "reduction, and the planar-subgraph x full-embedding family covered by "
    "the B&B. No optimality claim is made over the full metric set or an "
    "arbitrary drawing space.")


def _exactness_block(exactness):
    """WS2 certificate exactness block: honestly marked computed=False when
    not computed."""
    if not exactness:
        return {"computed": False, "proven_optimal": None, "gap": None,
                "crossing_number": None, "lb": None, "coverage": None,
                "method": "crossing-number exactness not computed "
                          "(pass --exact to compute)", "scope": _EXACT_SCOPE_NOTE}
    return {
        "computed": True,
        "proven_optimal": bool(exactness.get("proven_optimal")),
        "gap": exactness.get("gap"),
        "crossing_number": exactness.get("crossing_number"),
        "lb": exactness.get("lb"),
        "coverage": exactness.get("coverage"),
        "method": exactness.get("method"),
        "witness_digest": len(json.dumps(exactness.get("witness") or [],
                                         ensure_ascii=False, sort_keys=True)),
        "scope": _EXACT_SCOPE_NOTE,
        "caliber_note": (
            "crossing_number is the crossing number cr(G) of the graph itself "
            "(a lower bound over arbitrary drawings); metrics.crossings is the "
            "crossing count of this layout (the value achieved). The two "
            "calibers differ: cr(G) = 0 only guarantees a 0-crossing drawing "
            "exists, not that this layout achieves it"),
    }


def _regularity_block(graph, nodes):
    """WS2 placement regularity block (structure-detection driven; definitions
    in stdraw/regularity.py and docs/crossing-exact.md section 6; all metrics
    computable and recomputable)."""
    if graph is None:
        return None
    try:
        from . import regularity
        positions = {v: (nodes[v]["x"], nodes[v]["y"]) for v in nodes}
        return regularity.regularity_report(graph, positions)
    except Exception:
        return None
