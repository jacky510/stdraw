# -*- coding: utf-8 -*-
"""Geometry self-report (11 checks) — takes only a layout JSON, generic.

Checks run on the **delivered coordinates** (the rounded/exported JSON); this
is discipline, not an optimization option.
Writes a report JSON (usable as a CI gate); exit 1 when fail > 0.
"""
import json
import math
import sys
from typing import List


# ── SVG path d (M/L/A) parsing and geometry verification helpers ──
def _arc_points(x0, y0, rx, sweep, x1, y1, n=48):
    """SVG arc (rot=0, circle, rx=ry; this engine always uses laf=0=minor arc)
    -> sampled point list."""
    rx = abs(rx)
    if rx < 1e-9 or (abs(x1 - x0) < 1e-12 and abs(y1 - y0) < 1e-12):
        return [(x0, y0), (x1, y1)]
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = x1 - x0, y1 - y0
    chord = math.hypot(dx, dy)
    if chord < 1e-12:
        return [(x0, y0), (x1, y1)]
    if chord / 2.0 > rx:
        rx = chord / 2.0        # degenerate guard: radius clamped to semicircle
    h = math.sqrt(max(0.0, rx * rx - (chord / 2.0) ** 2))
    # Two candidate centers on either side of the chord; for the minor arc the
    # sweep angle is in (-pi, pi), take the one whose direction matches sweep
    for sgn in (1.0, -1.0):
        cx = mx - dy / chord * h * sgn
        cy = my + dx / chord * h * sgn
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        da = a1 - a0
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        if abs(da) > 1e-9 and (da > 0) == (sweep == 1):
            return [(cx + rx * math.cos(a0 + da * k / n),
                     cy + rx * math.sin(a0 + da * k / n)) for k in range(n + 1)]
    return [(x0, y0), (x1, y1)]


def _parse_path_d(d):
    """path d (M/L/A only, this engine's output shape) -> element list.

    ('L', (x0,y0), (x1,y1)) or ('A', [(sampled points)...]). Returns None for
    unrecognized commands.
    """
    toks = d.replace(",", " ").split()
    elems, cur, i = [], None, 0
    try:
        while i < len(toks):
            t = toks[i]
            if t == "M":
                cur = (float(toks[i + 1]), float(toks[i + 2]))
                i += 3
            elif t == "L":
                p = (float(toks[i + 1]), float(toks[i + 2]))
                elems.append(("L", cur, p))
                cur = p
                i += 3
            elif t == "A":
                rx = float(toks[i + 1])
                sweep = int(float(toks[i + 5]))
                p = (float(toks[i + 6]), float(toks[i + 7]))
                elems.append(("A", _arc_points(cur[0], cur[1], rx, sweep,
                                               p[0], p[1])))
                cur = p
                i += 8
            else:
                return None
    except (ValueError, IndexError, TypeError):
        return None
    return elems


def _path_d_all_points(elems):
    out = []
    for el in elems:
        if el[0] == "L":
            out.append(el[1])
            out.append(el[2])
        else:
            out.extend(el[1])
    return out


def _max_poly_dev(pa, pb):
    """Two-directional maximum minimum distance between two polylines
    (sampled Hausdorff caliber)."""
    from .routing import _pt_seg_dist
    def one_way(src, other):
        worst = 0.0
        for p in src:
            dmin = min(_pt_seg_dist(p, other[k], other[k + 1])
                       for k in range(len(other) - 1))
            worst = max(worst, dmin)
        return worst
    return max(one_way(pa, pb), one_way(pb, pa))


def _path_d_g1_max_deg(elems):
    """Maximum tangent-discontinuity angle (degrees) of a path_d element
    sequence. Analytic tangents at L<->A joins."""
    def line_dir(a, b):
        n = math.hypot(b[0] - a[0], b[1] - a[1])
        return ((b[0] - a[0]) / n, (b[1] - a[1]) / n) if n > 1e-12 else None

    def elem_dirs(el):
        if el[0] == "L":
            d = line_dir(el[1], el[2])
            return (d, d)
        pts = el[1]
        # Arc end tangent = end chord direction (n=48 sampling; chord vs true
        # tangent differs by <0.1 deg)
        return (line_dir(pts[0], pts[1]), line_dir(pts[-2], pts[-1]))

    worst = 0.0
    for k in range(len(elems) - 1):
        d_out = elem_dirs(elems[k])[1]
        d_in = elem_dirs(elems[k + 1])[0]
        if d_out is None or d_in is None:
            continue
        ang = math.degrees(math.acos(max(-1.0, min(1.0,
                       d_out[0] * d_in[0] + d_out[1] * d_in[1]))))
        worst = max(worst, ang)
    return worst


def geometry_report(layout: dict) -> dict:
    meta = layout.get("meta", {})
    if meta.get("recipe") == "auto-v2":
        return auto_geometry_report(layout)
    nodes, edges, bars = layout["nodes"], layout["edges"], layout.get("bars", {})
    meta = layout["meta"]
    W, H = layout["viewBox"][2], layout["viewBox"][3]
    CARD_H = meta.get("cardH", 42)
    CW = {v: p.get("w", 140) for v, p in nodes.items()}
    report = {"checks": [], "fail": 0}

    def chk(name, ok, detail=""):
        report["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            report["fail"] += 1
        print(("PASS " if ok else "FAIL ") + name + ("  " + detail if detail else ""))

    # 1. Pairwise zero intersection (incl. collinear overlap / near parallel adhesion)
    bad = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a, b = edges[i], edges[j]
            lo1, hi1 = sorted((a["y1"], a["y2"]))
            lo2, hi2 = sorted((b["y1"], b["y2"]))
            if a["x"] == b["x"]:
                if lo1 < hi2 and lo2 < hi1:
                    bad.append((i, j, "collinear overlap"))
            elif abs(a["x"] - b["x"]) < 8:
                if lo1 < hi2 and lo2 < hi1:
                    bad.append((i, j, "near-parallel adhesion"))
    chk("1. pairwise zero intersection (incl. collinear overlap / near-parallel adhesion)", not bad,
        f"{len(edges)} edges pairwise intersected, conflicts {len(bad)}" + (str(bad[:5]) if bad else ""))

    # 2. Line endpoints docked + unrelated lines may only pierce cards occlusion-style
    bad2 = []
    for e in edges:
        x = e["x"]
        for endv in (e["a"], e["b"]):
            cx = nodes[endv]["x"]
            in_card = abs(x - cx) <= CW[endv] / 2
            in_bar = endv in bars and bars[endv][0] - 1 <= x <= bars[endv][1] + 1
            if not (in_card or in_bar):
                bad2.append((e["a"] + "->" + e["b"], endv))
    chk("2. line endpoints docked at endpoint nodes (card or leader bar)", not bad2, str(bad2[:5]))

    # 3. Leader bars untouched by foreign lines
    bad3 = []
    for v, (b0, b1) in bars.items():
        cy = nodes[v]["y"]
        for e in edges:
            if v in (e["a"], e["b"]):
                continue
            if b0 - 1 <= e["x"] <= b1 + 1:
                lo, hi = sorted((e["y1"], e["y2"]))
                if lo - 1 <= cy <= hi + 1:
                    bad3.append((v, e["a"] + "->" + e["b"]))
    chk("3. leader bars free of foreign line contact/crossing", not bad3, str(bad3[:5]))

    # 4. Cards pairwise non-overlapping
    bad4 = []
    items = list(nodes.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (v1, p1), (v2, p2) = items[i], items[j]
            if abs(p1["x"] - p2["x"]) < (CW[v1] + CW[v2]) / 2 + 2 and \
               abs(p1["y"] - p2["y"]) < CARD_H + 2:
                bad4.append((v1, v2))
    chk("4. cards pairwise non-overlapping (per-node width)", not bad4, str(bad4[:5]))

    # 5. Grid alignment
    deg0 = set(meta.get("deg0", []))
    rowy = {}
    for v, p in nodes.items():
        if v in deg0:
            continue
        rowy.setdefault(p["y"], []).append(v)
    pitch_ok = all((b - a) == meta["pitch"] for a, b in zip(sorted(rowy), sorted(rowy)[1:]))
    rowdesc = "; ".join(f"y={y}:{len(vs)}" for y, vs in sorted(rowy.items()))
    chk("5a. same-row nodes share exactly one y (grouped by y)", len(rowy) == meta["rows"],
        f"{len(rowy)} y values = meta.rows={meta['rows']}; {rowdesc}")
    chk("5b. uniform row pitch", pitch_ok, f"pitch={meta['pitch']}")
    odd = [v for v, p in nodes.items() if p["x"] % 2 or p["y"] % 2]
    chk("5c. all coordinates on the 2px grid (even)", not odd, str(odd))
    chk("5d. all lines strictly vertical (0 bends 0 diagonals)",
        all(e["y1"] != e["y2"] for e in edges),
        f"all {len(edges)} edges have x1==x2; bend count 0")

    # 6. Arrow placement legality
    bad6 = []
    for e in edges:
        ax, ay = e["arrow"][0], e["arrow"][1]
        b, yb = nodes[e["b"]], e["y2"]
        in_card = abs(ax - b["x"]) <= CW[e["b"]] / 2 + 4
        in_bar = e["b"] in bars and bars[e["b"]][0] - 6 <= ax <= bars[e["b"]][1] + 6
        if not (in_card or in_bar):
            bad6.append((e["a"] + "->" + e["b"], "arrow beyond target card/bar horizontal range"))
        if abs(ay - yb) > CARD_H / 2 + 12:
            bad6.append((e["a"] + "->" + e["b"], "arrow too far from target row center"))
    chk("6. arrows point at the target card edge / leader bar", not bad6, str(bad6[:5]))

    # 7. viewBox fully contains everything
    out = []
    for v, p in nodes.items():
        if not (0 < p["x"] - CW[v] / 2 and p["x"] + CW[v] / 2 < W and
                0 < p["y"] - CARD_H / 2 and p["y"] + CARD_H / 2 < H):
            out.append(v)
    for e in edges:
        if not (0 < e["x"] < W):
            out.append(e["a"] + "->" + e["b"])
    chk("7. all content inside the viewBox", not out, str(out))

    # 8. Rendering scale (1280x800 tier)
    s = min(1280 / W, 680 / H) if W and H else 0
    fs_title, fs_value = meta.get("fs", [12.5, 14.0])
    chk("8. 1280x800 rendering scale >= 0.85", s >= 0.85,
        f"viewBox {W}x{H} -> s={s:.3f}; title {fs_title}x{s:.2f}~={fs_title * s:.1f}px")

    report["summary"] = {
        "viewBox": [W, H], "aspect": round(W / H, 3) if H else 0,
        "nodes": len(nodes), "edges": len(edges),
        "bars": len(bars), "rows": meta["rows"], "pitch": meta["pitch"],
        "scale_1280x800": round(s, 3),
        "fail": report["fail"]}
    report["rows"] = rowdesc
    return report


def geometry_report_to_file(layout: dict, path: str) -> int:
    rep = geometry_report(layout)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(f"\n{len(rep['checks'])} checks, fail={rep['fail']} -> {path}")
    return 1 if rep["fail"] else 0


def run_check_file(layout_path: str, report_path: str) -> int:
    with open(layout_path, encoding="utf-8") as f:
        layout = json.load(f)
    rc = geometry_report_to_file(layout, report_path)
    sys.exit(rc)


# ═══ auto-v2 geometry self-report (new hard gates) ═══
def auto_geometry_report(layout: dict) -> dict:
    from .routing import (sample_polyline, dist_point_rect, seg_cross,
                          PRESS_MARGIN, ANCHOR_MIN_DEG, CLEARANCE)
    nodes, edges = layout["nodes"], layout["edges"]
    meta = layout["meta"]
    # --from-layout manual layout: uniform card pitch / simple-graph
    # regularity are "automatic-pipeline structural checks", inapplicable to
    # manual coordinates (the certificate's regularity gate still grades
    # honestly, no leniency because of this).
    manual_mode = bool(meta.get("from_layout"))
    # Ring placement: uniform pitch / column snap are likewise row-structure
    # checks, inapplicable to ring placement (the certificate switches to
    # on-ring equal spacing CV + regular-polygon template fit error; see
    # metrics).
    ring_mode = meta.get("placement") == "ring-cycle"
    # comb-bilateral placement (v0.7.7): row caliber = column pitch + column
    # axis + hub-pair mirror symmetry (same caliber as the certificate)
    comb_mode = meta.get("placement") == "comb-bilateral"
    # column-chain / symmetric placement: row caliber switches per mode
    # (column = uniform main-chain pitch + column-axis alignment;
    # symmetric = mirror-axis error); 24px column snap inapplicable to both.
    column_mode = meta.get("placement") == "column-chain"
    sym_mode = meta.get("placement") == "symmetric"
    # bowtie-vertex: mirror axes = vertical axis x + horizontal axis y
    # (upper/lower rings mirrored)
    bowtie_mode = meta.get("placement") == "bowtie-vertex"
    # spine-wing: spine x on-axis + wings hugging the midline + mirror-pair error
    spine_wing_mode = meta.get("placement") == "spine-wing"
    W, H = layout["viewBox"][2], layout["viewBox"][3]
    CARD_H = meta.get("cardH", 44)
    CW = {v: p.get("w", 140) for v, p in nodes.items()}
    report = {"checks": [], "fail": 0}

    def chk(name, ok, detail=""):
        report["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            report["fail"] += 1
        print(("PASS " if ok else "FAIL ") + name + ("  " + detail if detail else ""))

    def polys():
        return [([tuple(p) for p in e["route"]["points"]], e)
                for e in edges]

    # 1. Crossings (pairwise polyline intersection, edges sharing an endpoint excluded)
    bad = []
    P = polys()
    for i in range(len(P)):
        for j in range(i + 1, len(P)):
            pi, ei = P[i]
            pj, ej = P[j]
            if ei["a"] in (ej["a"], ej["b"]) or ei["b"] in (ej["a"], ej["b"]):
                continue
            hit = False
            for s1 in zip(pi[:-1], pi[1:]):
                for s2 in zip(pj[:-1], pj[1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                bad.append((f"{ei['a']}->{ei['b']}", f"{ej['a']}->{ej['b']}"))
    chk("1. crossings <= 2 (polyline/arc sampled intersection; on hard-gate conflict keep gates, release crossings)", len(bad) <= 2,
        f"{len(edges)} edges, conflicts {len(bad)}" + (str(bad[:5]) if bad else ""))

    # 2. Box press = 0 (1px margin; endpoints only touch their own box
    #    border, no positive-length traversal inside their own box)
    bad2 = []
    for pts, e in P:
        dense = sample_polyline(pts)
        for v, p in nodes.items():
            hw, hh = CW[v] / 2, CARD_H / 2
            if v in (e["a"], e["b"]):
                continue
            if any(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN,
                                   hh + PRESS_MARGIN) <= 0 for (px, py) in dense):
                bad2.append((f"{e['a']}->{e['b']}", v))
        for v in (e["a"], e["b"]):
            p = nodes[v]
            hw, hh = CW[v] / 2, CARD_H / 2
            if any(dist_point_rect(px, py, p["x"], p["y"], hw + PRESS_MARGIN,
                                   hh + PRESS_MARGIN) <= 0 for (px, py) in dense[1:-1]):
                bad2.append((f"{e['a']}->{e['b']}", v, "own"))
    chk("2. box press = 0 (any angle, incl. 1px margin)", not bad2, str(bad2[:5]))

    # 3. Edge-box clearance >= 16px (non-endpoint boxes)
    worst = None
    for pts, e in P:
        dense = sample_polyline(pts)
        for v, p in nodes.items():
            if v in (e["a"], e["b"]):
                continue
            hw, hh = CW[v] / 2, CARD_H / 2
            d = min(dist_point_rect(px, py, p["x"], p["y"], hw, hh) for (px, py) in dense)
            if worst is None or d < worst[0]:
                worst = (d, e["a"], e["b"], v)
    chk("3. edge-box clearance >= 16px", worst is None or worst[0] >= CLEARANCE - 1e-6,
        f"minimum {worst[0]:.1f}px ({worst[1]}->{worst[2]} vs {worst[3]})" if worst else "")

    # 4. Anchor smoothness: anchor on box border + departure direction vs
    #    border tangent angle >= 20 deg
    bad4 = []
    for pts, e in P:
        for v, idx, nidx in ((e["a"], 0, 1), (e["b"], len(pts) - 1, len(pts) - 2)):
            p = nodes[v]
            hw, hh = CW[v] / 2, CARD_H / 2
            a0 = pts[idx]
            off_border = dist_point_rect(a0[0], a0[1], p["x"], p["y"], hw, hh) > 0.75
            dx, dy = pts[nidx][0] - a0[0], pts[nidx][1] - a0[1]
            n = (dx * dx + dy * dy) ** 0.5
            on_x = abs(abs(a0[0] - p["x"]) - hw) <= abs(abs(a0[1] - p["y"]) - hh)
            tx, ty = (0.0, 1.0) if on_x else (1.0, 0.0)
            c = abs(dx * tx + dy * ty) / n if n > 1e-9 else 1.0
            import math as _m
            ang = _m.degrees(_m.acos(max(0.0, min(1.0, c))))
            if off_border or ang < ANCHOR_MIN_DEG:
                bad4.append((f"{e['a']}->{e['b']}", v, round(ang, 1),
                             "off-border" if off_border else "tangential"))
    chk("4. anchor smoothness (border anchors, tangent angle >= 20 deg)", not bad4, str(bad4[:5]))

    # 5. Cards pairwise non-overlapping
    bad5 = []
    items = list(nodes.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (v1, p1), (v2, p2) = items[i], items[j]
            if abs(p1["x"] - p2["x"]) < (CW[v1] + CW[v2]) / 2 + 2 and \
               abs(p1["y"] - p2["y"]) < CARD_H + 2:
                bad5.append((v1, v2))
    chk("5. cards pairwise non-overlapping (per-node width)", not bad5, str(bad5[:5]))

    # 6. Grid / row pitch
    deg0 = set(meta.get("deg0", []))
    rowy = {}
    for v, p in nodes.items():
        if v in deg0:
            continue
        rowy.setdefault(p["y"], []).append(v)
    pitch_ok = len({b - a for a, b in zip(sorted(rowy), sorted(rowy)[1:])}) <= 1
    odd = [v for v, p in nodes.items() if p["x"] % 2 or p["y"] % 2]
    _6a_na = (" (manual: N/A)" if manual_mode else
              " (ring: N/A)" if ring_mode else
              " (comb: column rows)" if comb_mode else
              " (column: main-chain rows)" if column_mode else
              " (sym: all rows)" if sym_mode else "")
    if column_mode:
        spine = (meta.get("column") or {}).get("spine") or []
        sys_ = [nodes[v]["y"] for v in spine if v in nodes]
        pitch_ok = len({b - a for a, b in zip(sys_, sys_[1:])}) <= 1 if len(sys_) > 1 else True
    if comb_mode:
        col = (meta.get("comb") or {}).get("column") or []
        cys = [nodes[v]["y"] for v in col if v in nodes]
        pitch_ok = len({b - a for a, b in zip(cys, cys[1:])}) <= 1 if len(cys) > 1 else True
    chk("6a. uniform row pitch (parking-lane nodes excluded)" + _6a_na,
        True if (manual_mode or ring_mode) else pitch_ok, f"pitch={meta['pitch']}")
    chk("6b. all coordinates on the 2px grid (even)", not odd, str(odd))

    # 7. viewBox fully contains everything
    out = []
    for v, p in nodes.items():
        if not (0 < p["x"] - CW[v] / 2 and p["x"] + CW[v] / 2 < W and
                0 < p["y"] - CARD_H / 2 and p["y"] + CARD_H / 2 < H):
            out.append(v)
    for pts, e in P:
        if any(not (0 < px < W and 0 < py < H) for (px, py) in pts):
            out.append(e["a"] + "->" + e["b"])
    chk("7. all content inside the viewBox", not out, str(out))

    # 8. Rendering scale (1280x800 tier)
    s = min(1280 / W, 680 / H) if W and H else 0
    fs_title, fs_value = meta.get("fs", [12.5, 14.0])
    chk("8. 1280x800 rendering scale >= 0.85", s >= 0.85,
        f"viewBox {W}x{H} -> s={s:.3f}; title {fs_title}x{s:.2f}~={fs_title * s:.1f}px")

    # 9. Simple-graph regularity (<=10 nodes: uniform pitch + 24px column snap >= 60%)
    # manual layout: regularity is an automatic-pipeline structural check -> N/A
    # (the certificate regularity gate still grades)
    # ring placement: row caliber inapplicable -> on-ring equal spacing CV +
    # regular-polygon template fit error (same caliber as the certificate)
    snap = sum(1 for p in nodes.values() if p["x"] % 24 == 0) / len(nodes)
    simple = len(nodes) <= 10
    if ring_mode:
        import math as _rm
        rnodes = (meta.get("ring") or {}).get("nodes") or []
        rpts = [(nodes[v]["x"], nodes[v]["y"]) for v in rnodes if v in nodes]
        if len(rpts) >= 3:
            ds = [_rm.dist(rpts[i], rpts[(i + 1) % len(rpts)]) for i in range(len(rpts))]
            md = sum(ds) / len(ds)
            rsv = (sum((d - md) ** 2 for d in ds) / len(ds)) ** 0.5 / md if md else 0.0
            from . import regularity as _reg
            rdev = _reg.cycle_polygon_deviation(
                {v: (nodes[v]["x"], nodes[v]["y"]) for v in rnodes}, rnodes)
            ring_ok = rsv <= 0.05 and rdev <= 0.05
            ring_detail = f"on-ring equal spacing CV={rsv:.4f}, regular-polygon deviation D={rdev:.4f} (gate <=0.05)"
        else:
            ring_ok, ring_detail = False, "meta.ring.nodes missing / fewer than 3 nodes"
        chk("9. ring placement regularity (on-ring equal spacing CV + template fit)", ring_ok, ring_detail)
    elif column_mode:
        import math as _cm
        spine = (meta.get("column") or {}).get("spine") or []
        spts = [(nodes[v]["x"], nodes[v]["y"]) for v in spine if v in nodes]
        if len(spts) >= 2:
            axis = sum(p[0] for p in spts) / len(spts)
            dev = max(abs(p[0] - axis) for p in spts)
            col_ok = dev <= 2.0 and pitch_ok
            col_detail = f"main-chain column-axis deviation {dev:.2f}px (gate <=2px), main-chain pitch uniform {pitch_ok}"
        else:
            col_ok, col_detail = False, "meta.column.spine missing / fewer than 2 nodes"
        chk("9. column placement regularity (main-chain axis alignment + uniform pitch)", col_ok, col_detail)
    elif comb_mode:
        # comb-bilateral: column x on-axis <=2px + constant column pitch +
        # hub-pair mirror symmetry about the column axis (<=2px)
        comb = meta.get("comb") or {}
        axis_x = comb.get("axis_x") or 0.0
        errs = []
        for cv in comb.get("column") or []:
            if cv in nodes:
                errs.append(abs(nodes[cv]["x"] - axis_x))
        hl, hr = comb.get("hubs") or (None, None)
        if hl in nodes and hr in nodes:
            errs.append(abs((nodes[hl]["x"] + nodes[hr]["x"]) / 2 - axis_x))
            errs.append(abs(nodes[hl]["y"] - nodes[hr]["y"]))
        comb_ok = bool(errs) and max(errs) <= 2.0 and pitch_ok
        chk("9. comb-bilateral placement regularity (column axis + pitch + hub mirror <=2px)",
            comb_ok,
            f"maximum deviation {max(errs):.2f}px, column pitch uniform {pitch_ok}"
            if errs else "meta.comb missing")
    elif sym_mode:
        sym = meta.get("symmetry") or {}
        axis_x = sym.get("axis_x") or 0.0
        pairs = sym.get("mirror_pairs") or []
        errs = []
        for l, r in pairs:
            if l in nodes and r in nodes:
                errs.append(abs((nodes[l]["x"] + nodes[r]["x"]) / 2 - axis_x))
                errs.append(abs(nodes[l]["y"] - nodes[r]["y"]))
        sym_ok = bool(errs) and max(errs) <= 2.0
        chk("9. symmetric placement regularity (mirror-axis error <=2px)", sym_ok,
            f"mirror-axis error {max(errs):.2f}px" if errs else "meta.symmetry.mirror_pairs missing")
    elif bowtie_mode:
        sym = meta.get("symmetry") or {}
        axis_x = sym.get("axis_x") or 0.0
        axis_y = sym.get("axis_y") or 0.0
        errs = []
        for l, r in sym.get("mirror_pairs") or []:
            if l in nodes and r in nodes:
                errs.append(abs(nodes[l]["x"] - nodes[r]["x"]))
                errs.append(abs((nodes[l]["y"] + nodes[r]["y"]) / 2 - axis_y))
        sh = sym.get("shared_node")
        if sh in nodes:
            errs.append(abs(nodes[sh]["x"] - axis_x))
            errs.append(abs(nodes[sh]["y"] - axis_y))
        bowtie_ok = bool(errs) and max(errs) <= 2.0
        chk("9. bowtie-vertex placement regularity (mirror-axis error <=2px)", bowtie_ok,
            f"mirror-axis error {max(errs):.2f}px" if errs else "meta.symmetry missing")
    elif spine_wing_mode:
        # spine-wing: spine x on-axis <=2px + wings hugging the midline <=2px
        # + mirror-pair error <=2px (consistent with certificate metrics in
        # all three places)
        sw = meta.get("spine_wing") or {}
        axis_x = sw.get("axis_x") if sw.get("axis_x") is not None else 0.0
        axis_y = sw.get("axis_y") if sw.get("axis_y") is not None else 0.0
        errs = []
        for sv in sw.get("spine") or []:
            if sv in nodes:
                errs.append(abs(nodes[sv]["x"] - axis_x))
        for w in sw.get("wings") or []:
            if w in nodes:
                errs.append(abs(nodes[w]["y"] - axis_y))
        for up, down in sw.get("mirror_pairs") or []:
            if up in nodes and down in nodes:
                errs.append(abs(nodes[up]["x"] - nodes[down]["x"]))
                errs.append(abs((nodes[up]["y"] + nodes[down]["y"]) / 2 - axis_y))
        sw_ok = bool(errs) and max(errs) <= 2.0
        chk("9. spine-wing placement regularity (spine on-axis + midline adherence + mirror <=2px)",
            sw_ok,
            f"maximum deviation {max(errs):.2f}px" if errs else "meta.spine_wing missing")
    else:
        chk("9. simple-graph placement regularity" + (" (manual: N/A)" if manual_mode else ""),
            True if manual_mode else ((not simple) or (pitch_ok and snap >= 0.6)),
            f"n={len(nodes)}, 24px column snap {snap:.2f}, pitch uniform {pitch_ok}"
            + ("; inapplicable to manual layouts" if manual_mode else ""))

    # 10. Metadata completeness (recipe / line_style / engine)
    ok10 = (meta.get("recipe") == "auto-v2" and
            meta.get("line_style") in ("straight", "arc") and
            (meta.get("position_engine") in ("cp-sat", "construct", "manual",
                                             "ring-construct",
                                             "column-construct", "sym-construct",
                                             "bowtie-construct",
                                             "comb-construct",
                                             "spine-construct")))
    chk("10. auto-v2 metadata complete", ok10,
        f"recipe={meta.get('recipe')} line_style={meta.get('line_style')} "
        f"engine={meta.get('position_engine')}")

    # 11. WS3 dual crossing accounting consistency: routing theory (crossing
    # pairs of the final route) vs delivered-geometry recheck
    router_pairs = meta.get("router_cross_pairs")
    if router_pairs is not None:
        geom_pairs = len(bad)      # geometric recheck result of item 1 (edge pairs)
        chk("11. dual crossing accounting consistent (routing theory vs delivered-geometry recheck)",
            abs(router_pairs - geom_pairs) < 0.5,
            f"router={router_pairs} geometric={geom_pairs}")

    # 12. F1: mutual pairs (bidirectional edge pairs) two-line minimum distance >= 4px
    # (lens double arcs; merging into a double-arrowhead line is forbidden)
    from .routing import min_pair_dist
    pair_bad = []
    pair_note = []
    for i in range(len(P)):
        for j in range(i + 1, len(P)):
            (pi, ei), (pj, ej) = P[i], P[j]
            if (ei["a"], ei["b"]) != (ej["b"], ej["a"]):
                continue
            md = min_pair_dist(sample_polyline(pi), sample_polyline(pj))
            pair_note.append(f"{ei['a']}<->{ei['b']}:{md if md is None else round(md, 1)}px")
            if md is None or md < 4.0:
                pair_bad.append((f"{ei['a']}<->{ei['b']}",
                                 md if md is None else round(md, 1)))
    chk("12. mutual-pair two-line minimum distance >= 4px (lens double arcs, merging forbidden)",
        not pair_bad, (str(pair_bad[:5]) if pair_bad else "; ".join(pair_note[:6])))

    # 13. path_d rendering geometry = verification geometry (dense points) +
    # arc G1 tangent continuity.
    # Historical bug: route_svg_d unconditionally re-drew the corner point
    # itself after the fillet arc, producing a tb->q->ta_next zigzag artifact
    # in the rendering layer while the certificate only checked the dense
    # sampled points (smooth) — delivery and verification were out of sync.
    # This check parses the rendered path_d (M/L/A) directly, verifies both
    # geometries bidirectionally within <=1.5px, and requires each A segment's
    # tangent angle to adjacent L segments <=4 deg (rounding tolerance).
    pathd_bad = []
    pathd_n = 0
    for pts, e in P:
        d = e.get("route", {}).get("path_d")
        if not d:
            continue
        pathd_n += 1
        elems = _parse_path_d(d)
        if elems is None:
            pathd_bad.append((f"{e['a']}->{e['b']}", "path_d parse failed"))
            continue
        dp = _path_d_all_points(elems)
        dense = [tuple(p) for p in pts]
        dev = _max_poly_dev(dp, dense)
        if dev > 1.5:
            pathd_bad.append((f"{e['a']}->{e['b']}", f"render/verify geometry deviation {dev:.1f}px"))
            continue
        g1 = _path_d_g1_max_deg(elems)
        if g1 > 4.0:
            pathd_bad.append((f"{e['a']}->{e['b']}", f"arc tangent discontinuity {g1:.1f} deg"))
    chk("13. path_d rendering geometry consistent with verification geometry + arc G1 tangent continuity",
        not pathd_bad,
        (str(pathd_bad[:5]) if pathd_bad
         else f"{pathd_n} vg paths render/verify consistent (G1 <=4 deg, geometry deviation <=1.5px)"
         if pathd_n else "no vg path_d routes in this graph (trivially passes)"))

    report["summary"] = {
        "viewBox": [W, H], "aspect": round(W / H, 3) if H else 0,
        "nodes": len(nodes), "edges": len(edges),
        "rows": meta["rows"], "pitch": meta["pitch"],
        "scale_1280x800": round(s, 3),
        "recipe": meta.get("recipe"), "line_style": meta.get("line_style"),
        "position_engine": meta.get("position_engine"),
        "fail": report["fail"]}
    return report
