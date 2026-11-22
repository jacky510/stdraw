# -*- coding: utf-8 -*-
"""Deterministic mirror-symmetry post-pass (anchors-as-prior S2, Option A).

docs/proposals/anchor-prior-candidate-generation.zh.md section 2 +
docs/proposals/edge-mirror-symmetry-routing.md Option A: AFTER stage-2
routing settles, detect the drawing's left-right mirror (a y-preserving
involution automorphism + fitted axis), then rewrite every mirror edge
pair so the slave side is the EXACT geometric mirror (``x' = 2c - x``) of
the master side.  No search, no solver, byte-deterministic.

Machinery reuse (never re-implemented here): the involution enumeration is
``features._automorphisms`` (the same automorphism search the symmetry
features use), the axis fit is ``features._fit_reflection``, the tolerance
is ``0.5 x median nearest-neighbour node distance`` (the adaptive caliber
of docs/edge-mirror-feature.md, NOT canvas-relative), and the gate
accounting is the Router's own hard-gate summary.

Validity gate re-run (fail-loud): after each pair rewrite the SAME hard
gates are recounted on the whole route set (box press, edge-box clearance,
mutual-pair separation, graph-theory crossings, visual crossings, line
coincidence).  A violating pair keeps its ORIGINAL routes and the exception
is recorded -- this pass must never turn a gate-clean layout into a
gate-breaking one.  Exceptions travel in the returned report and land in
the delivered meta.

DEFAULT OFF: the pass runs only under ``--mirror-symmetry`` (cfg flag).
With the flag off, ``layout_auto.layout`` never enters this module, so
every byte-pinned consumer (gate A, frozen baselines, STDRAW_PIN) is
constructively unaffected.  The anchor mirror tables (golden / slot dual
caliber) for the anchor id system live in stdraw.features
(``_ANCHOR_MIRROR_GOLDEN`` / ``_ANCHOR_MIRROR_SLOT``) and are consumed via
the edge-mirror feature; the route-level mirror here is the geometric
sibling for delivered polylines.
"""
import math

from . import features
from .routing import seg_cross

# Preregistered constants (proposal section 2.2 calibers).
AXIS_VERTICAL_TOL_DEG = 3.0     # fitted mirror line must be near-vertical
MIRROR_PAIR_SEPARATOR_MIN = 4.0  # mutual-pair hard gate (F1 caliber)

_SEG_CACHE_LIMIT = 4096


def _layout_doc(cand, edges, routes):
    """Route-set snapshot as a features.Layout doc (single-source parse)."""
    pos, y, widths = cand["pos"], cand["y"], cand["widths"]
    nodes_doc = {}
    for v in cand["nodes"]:
        nodes_doc[v] = {"x": pos[v], "y": y[v], "w": widths[v]}
    xs0 = min(pos[v] - widths[v] / 2 for v in cand["nodes"])
    xs1 = max(pos[v] + widths[v] / 2 for v in cand["nodes"])
    ys0 = min(y[v] - cand["card_h"] / 2 for v in cand["nodes"])
    ys1 = max(y[v] + cand["card_h"] / 2 for v in cand["nodes"])
    edges_doc = [{"a": a, "b": b,
                  "route": {"points": [list(p) for p in routes[i]["points"]]}}
                 for i, (a, b) in enumerate(edges)]
    return {"nodes": nodes_doc, "edges": edges_doc,
            "viewBox": [0, 0, int(math.ceil(xs1 - xs0)) + 1,
                        int(math.ceil(ys1 - ys0)) + 1],
            "meta": {"cardH": cand["card_h"],
                     "clearance": cand.get("clearance", 16)}}


def _select_sigma(layout, pos, y):
    """y-preserving involutive automorphism with a near-vertical fitted
    axis; main mirror = axis closest to the canvas mid-x (tie-breaks:
    tighter axis scatter -> more mirror pairs -> enumeration order)."""
    adj = features._adjacency(layout)
    autos = features._automorphisms(layout, adj, features.AUTO_MAP_CAP)
    tol = 0.5 * (features._median_nn_scale(layout) or 0.0)
    canvas_mid_x = layout.vx + layout.vw / 2.0
    cands = []
    for mapping in autos:
        if any(mapping[mapping[v]] != v for v in layout.ids):
            continue                      # involution only
        if any(abs(y[v] - y[mapping[v]]) > tol for v in layout.ids):
            continue                      # y-preserving only
        src = [layout.pos[v] for v in layout.ids]
        dst = [layout.pos[mapping[v]] for v in layout.ids]
        resid, axis_deg, pivot = features._fit_reflection(src, dst)
        if abs(axis_deg - 90.0) > AXIS_VERTICAL_TOL_DEG:
            continue                      # left-right mirror only
        pairs = sum(1 for v in layout.ids if mapping[v] != v) // 2
        cands.append({"sigma": dict(mapping), "axis_c": pivot[0],
                      "axis_deg": axis_deg, "residual": resid,
                      "node_pairs": pairs})
    if not cands:
        return None, {"reason": "no y-preserving involution with a "
                                "near-vertical fitted axis"}
    cands.sort(key=lambda c: (abs(c["axis_c"] - canvas_mid_x),
                              c["residual"], -c["node_pairs"]))
    return cands[0], {"candidates": len(cands)}


def _edge_pairs(edges, sigma):
    """Mirror edge pairs under sigma: {slave_index: (master_index, reversed)}.
    Self-mirror edges (fixed by sigma) and unpaired edges stay untouched."""
    eidx = {}
    for i, (a, b) in enumerate(edges):
        eidx.setdefault((a, b), i)
    pairs = {}
    for i, (a, b) in enumerate(edges):
        sa, sb = sigma.get(a, a), sigma.get(b, b)
        if (sa, sb) == (a, b):
            continue                      # self-mirror (fixed edge)
        j = eidx.get((sa, sb))
        reversed_ = False
        if j is None:
            j = eidx.get((sb, sa))
            reversed_ = True
        if j is None or j == i:
            continue
        if j < i:                         # count each pair once
            continue
        ka = tuple(sorted(edges[i]))
        kb = tuple(sorted(edges[j]))
        # canonical smaller endpoint id side is the master
        master, slave, rev = i, j, reversed_
        if kb < ka:
            master, slave, rev = j, i, not reversed_
        pairs[slave] = (master, rev)
    return pairs


def _mirror_points(pts, axis_c):
    return [[2.0 * axis_c - float(p[0]), float(p[1])] for p in pts]


def _visual_crossings(routes, edges):
    """metrics visual-crossing caliber on the route set (strict seg_cross,
    endpoint touch excluded; shared-endpoint pairs included)."""
    items = sorted(routes.items())
    count = 0
    for a in range(len(items)):
        pa = items[a][1]["points"]
        for b in range(a + 1, len(items)):
            pb = items[b][1]["points"]
            for s1 in zip(pa[:-1], pa[1:]):
                hit = False
                for s2 in zip(pb[:-1], pb[1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    count += 1
                    break
    return count


def _edge_gate_ok(router, i, routes):
    """Router's own hard-gate summary for edge i on the current route set:
    box press (others + own), edge-box clearance, mutual-pair separation,
    anchor smoothness."""
    from .routing import ANCHOR_MIN_DEG
    press, min_clr, _ang, _cross, msep = router._edge_stats(i, routes)
    if press != 0:
        return False, "box press %d" % press
    if router._own_press(i, routes) != 0:
        return False, "own-box press"
    if min_clr is not None and min_clr < router.cl - 1e-6:
        return False, "clearance %.1f < %.1f" % (min_clr, router.cl)
    if msep is not None and msep < MIRROR_PAIR_SEPARATOR_MIN:
        return False, "mutual separation %.1f < %.1f" % (
            msep, MIRROR_PAIR_SEPARATOR_MIN)
    ang_a = routes[i].get("ang_a", ANCHOR_MIN_DEG)
    ang_b = routes[i].get("ang_b", ANCHOR_MIN_DEG)
    if min(ang_a, ang_b) < ANCHOR_MIN_DEG - 1e-9:
        return False, "anchor smoothing %.1f/%.1f < %.1f deg" % (
            ang_a, ang_b, ANCHOR_MIN_DEG)
    if not router._cert_angle_ok(i, routes):
        return False, "certificate-caliber anchor smoothing"
    # mirrored endpoints must land ON the sigma-image boxes' borders (the
    # certificate's off-border caliber: dist_point_rect <= 0.75 px)
    from .routing import dist_point_rect
    a, b = router.edges[i]
    pts = routes[i]["points"]
    for v, p in ((a, pts[0]), (b, pts[-1])):
        cx, cy, hw, hh = router.N[v]
        if dist_point_rect(p[0], p[1], cx, cy, hw, hh) > 0.75:
            return False, "mirrored endpoint off-border of %s" % v
    return True, ""


def apply_mirror_symmetry(cfg, cand, routes, router, edges):
    """Stage-2 post-pass. Returns (routes, report_dict_or_None)."""
    if not routes:
        return routes, None
    doc = _layout_doc(cand, edges, routes)
    try:
        layout = features.Layout(doc)
    except features.FeatureError as exc:
        return routes, {"reason": "layout-unreadable",
                        "detail": "%s: %s" % (type(exc).__name__, exc)}
    sigma, why = _select_sigma(layout, cand["pos"], cand["y"])
    if sigma is None:
        return routes, {"reason": why.get("reason"),
                        "candidates": why.get("candidates", 0)}
    axis_c = sigma["axis_c"]
    pairs = _edge_pairs(edges, sigma["sigma"])
    if not pairs:
        return routes, {"sigma_nodes": len(sigma["sigma"]),
                        "axis_c": axis_c, "axis_deg": sigma["axis_deg"],
                        "residual": sigma["residual"],
                        "mirror_pairs": 0,
                        "reason": "no mirror edge pairs"}

    pre_cross = router.final_crossing_pairs(routes)
    pre_coincide = len(router._route_coincide_pairs(routes))
    pre_visual = _visual_crossings(routes, edges)
    out = dict(routes)
    mirrored, exceptions = [], []
    for slave in sorted(pairs):
        master, rev = pairs[slave]
        if out[master].get("kind") == "vg" or out[slave].get("kind") == "vg":
            # v1 defers visibility-detour pairs: their fillet bookkeeping
            # (corner indices under reversal) is not worth guessing -- the
            # exception is recorded fail-loud instead.
            exceptions.append({"slave": slave, "master": master,
                               "reason": "vg-kind pair not mirrored in v1"})
            continue
        mpts = out[master]["points"]
        mpts = _mirror_points(mpts, axis_c)
        if rev:
            mpts = mpts[::-1]
        saved = dict(out[slave])
        new = dict(saved)
        new["points"] = mpts
        # recompute anchor smoothness honestly on the mirrored endpoints
        a, b = edges[slave]
        new["ang_a"] = router._anchor_angle(a, mpts[0], mpts[0], mpts[1])
        new["ang_b"] = router._anchor_angle(b, mpts[-1], mpts[-1], mpts[-2])
        if saved.get("ctrl") is not None:
            new["ctrl"] = [2.0 * axis_c - float(saved["ctrl"][0]),
                           float(saved["ctrl"][1])]
        if saved.get("vg_corners"):
            new["vg_corners"] = [[2.0 * axis_c - float(p[0]), float(p[1])]
                                 for p in saved["vg_corners"]]
        out[slave] = new
        # ---- validity gate re-run on the WHOLE route set (fail-loud) ----
        ok_pair, why_pair = _edge_gate_ok(router, slave, out)
        ok_master, _ = _edge_gate_ok(router, master, out)
        post_cross = router.final_crossing_pairs(out)
        post_coincide = len(router._route_coincide_pairs(out))
        post_visual = _visual_crossings(out, edges)
        if (ok_pair and ok_master and post_cross <= pre_cross
                and post_coincide <= pre_coincide
                and post_visual <= pre_visual):
            mirrored.append({"slave": slave, "master": master})
        else:
            out[slave] = saved          # keep the original routes verbatim
            exceptions.append({
                "slave": slave, "master": master,
                "reason": why_pair or (
                    "crossings %d->%d, coincide %d->%d, visual %d->%d"
                    % (pre_cross, post_cross, pre_coincide, post_coincide,
                       pre_visual, post_visual)),
            })
    report = {
        "sigma_nodes": len(sigma["sigma"]),
        "axis_c": axis_c,
        "axis_deg": sigma["axis_deg"],
        "residual": sigma["residual"],
        "mirror_pairs": len(pairs),
        "mirrored": len(mirrored),
        "mirrored_pairs": [dict(p) for p in sorted(
            mirrored, key=lambda p: (p["slave"], p["master"]))],
        "exceptions": exceptions,
    }
    return out, report
