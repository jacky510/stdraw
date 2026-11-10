# -*- coding: utf-8 -*-
"""2D rendering layer: planar layout JSON -> standalone HTML (inline SVG, zero
dependencies, zero network)."""
import html
import json

from ._interactive_js import _INTERACTIVE_JS
from .themes import (DEFAULT_STATIC_THEME, LIGHT, THEMES, get as _get_theme)

# Two-color polarity constants kept for backward compatibility: they are the
# LIGHT-tier values; themed rendering reads the tokens via _edge_svg(T=...).
EDGE_COLOR_POS = LIGHT["edge_pos"]
EDGE_COLOR_NEG = LIGHT["edge_neg"]
NEUTRAL_COLOR = LIGHT["neutral"]  # defensive fallback only (DSL edges always carry a sign)


def _grid_layer(W, H, T):
    """Canvas grid layer (UI-A spec section 4.2): an SVG `<defs><pattern>` +
    a full-canvas backdrop rect emitted FIRST (beneath every other element).
    Parameters come from the theme's `canvas_grid` token — light = tracing-
    paper dot grid, dark = neutral steel line grid. No token -> no layer."""
    g = T.get("canvas_grid") or {}
    style = g.get("style")
    spacing = g.get("spacing", 22)
    color = g.get("color")
    if not style or not color:
        return ""
    if style == "dots":
        r = g.get("dot_radius", 1.1)
        tile = (f'<circle cx="{spacing / 2:g}" cy="{spacing / 2:g}" '
                f'r="{r:g}" fill="{color}"/>')
    elif style == "lines":
        tile = (f'<path d="M {spacing} 0 L 0 0 0 {spacing}" fill="none" '
                f'stroke="{color}" stroke-width="1"/>')
    else:
        return ""
    return (f'<defs><pattern id="stdraw-grid" width="{spacing:g}" '
            f'height="{spacing:g}" patternUnits="userSpaceOnUse">{tile}</pattern></defs>'
            # pointer-events:none — the grid is paint-only. As an SVG child it
            # would otherwise sit above the interactive hit layer (#stdraw-hits,
            # inserted at svg.firstChild by the drag script) and swallow every
            # edge hit-test (hover / segment drag / double-click style cycle
            # all dead). Regression-probed by tests/probe_interactive.py's
            # elementFromPoint hit gate.
            f'<rect x="0" y="0" width="{W:g}" height="{H:g}" '
            f'fill="url(#stdraw-grid)" pointer-events="none"/>')


def _cert_css(T):
    """Certificate panel skin, UI-A ink-sign form (spec D3): SQUARE corners
    (the panel must NOT follow the rounded cards), label rows system-ui
    12.5px/600, value rows ui-monospace 10.5px (same both tiers)."""
    mono = ("ui-monospace,SFMono-Regular,Menlo,Consolas,monospace")
    return (
        f'.cert{{margin-top:12px;padding:10px 14px;background:{T["panel_bg"]};'
        f'border:1.4px solid {T["panel_border"]};border-radius:0;font-size:13px;'
        f'max-width:1280px}}'
        f'.cert-head{{display:flex;align-items:baseline;justify-content:space-between;'
        f'gap:12px;border-bottom:1.4px solid {T["panel_border"]};'
        f'padding-bottom:6px;margin-bottom:8px}}'
        f'.cert-title{{font-family:system-ui,sans-serif;font-size:12.5px;'
        f'font-weight:600;letter-spacing:3px}}'
        f'.cert-sub{{font-family:{mono};font-size:10.5px;color:{T["note"]}}}'
        f'.cert-sign{{border-collapse:collapse;margin:0 0 8px}}'
        f'.cert-sign td{{border:1px solid {T["panel_border"]};padding:3px 12px}}'
        f'.cert-sign td.lbl{{font-family:system-ui,sans-serif;font-size:12.5px;'
        f'font-weight:600}}'
        f'.cert-sign td.val{{font-family:{mono};font-size:10.5px}}'
        f'.stamp{{display:inline-block;border:2px solid {T["ok"]};color:{T["ok"]};'
        f'padding:1px 12px;font-family:system-ui,sans-serif;font-size:14px;'
        f'font-weight:700;letter-spacing:2px;text-transform:uppercase;'
        f'transform:rotate(-2deg)}}'
        f'.stamp-mut{{border-color:{T["note"]};color:{T["note"]}}}'
        f'.cert-detail table{{border-collapse:collapse;margin:4px 0}}'
        f'.cert-detail td{{border:1px solid {T["panel_border"]};padding:2px 10px}}'
        f'.cert-detail td:first-child{{font-family:system-ui,sans-serif;'
        f'font-size:12.5px;font-weight:600}}'
        f'.cert-detail td:not(:first-child){{font-family:{mono};font-size:10.5px}}'
        f'.cert-detail h4{{font-family:system-ui,sans-serif;font-size:12.5px;'
        f'font-weight:600;margin:8px 0 2px}}'
    )


def _cert_head(grade, sub):
    """Ink-sign head: title + stamp-style grade (best = seal green, anything
    else = muted — the honest grade is never dressed up as a pass)."""
    stamp_cls = "stamp" if grade == "best" else "stamp stamp-mut"
    return (f'<div class="cert-head"><span class="cert-title">'
            f'QUALITY CERTIFICATE</span><span class="cert-sub">{html.escape(sub)}</span>'
            f'<span class="{stamp_cls}">{html.escape(grade)}</span></div>')


def render_html(v4: dict, graph_name: str = "", cert: dict = None,
                loops_report: dict = None, labels: dict = None,
                values: dict = None, theme: str = DEFAULT_STATIC_THEME) -> str:
    T = _get_theme(theme)
    if v4.get("edges") and "route" in v4["edges"][0]:
        return render_auto_html(v4, graph_name, cert, loops_report, labels,
                                values, theme)
    W, H = v4["viewBox"][2], v4["viewBox"][3]
    nodes, edges, bars = v4["nodes"], v4["edges"], v4.get("bars", {})
    meta = v4["meta"]
    card_h = meta.get("cardH", 42)
    labels = labels or {}
    values = values or {}

    parts = []
    parts.append(f'<svg viewBox="0 0 {W} {H}" font-family="Microsoft YaHei,sans-serif">')
    # Canvas grid layer (UI-A): dots (light) / lines (dark), beneath everything
    parts.append(_grid_layer(W, H, T))
    # Leader bars (horizontal lines at card row centers, spanning only their
    # own associated line columns)
    for v, (b0, b1) in bars.items():
        parts.append(f'<line x1="{b0}" y1="{nodes[v]["y"]}" x2="{b1}" y2="{nodes[v]["y"]}" '
                     f'stroke="{T["leader_line"]}" stroke-width="2"/>')
    # Vertical lines + arrows
    for e in edges:
        x, y1, y2 = e["x"], e["y1"], e["y2"]
        parts.append(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" '
                     f'stroke="{T["line"]}" stroke-width="1.3"/>')
        ax, ay, d = e["arrow"]
        parts.append(f'<path d="M {ax - 4} {ay - 6 * d} L {ax} {ay} L {ax + 4} {ay - 6 * d} '
                     f'Z" fill="{T["line"]}"/>')
    # Cards
    for v, p in nodes.items():
        x, y, w = p["x"], p["y"], p["w"]
        label = html.escape(labels.get(v, v))
        value = html.escape(values.get(v, ""))
        parts.append(f'<g><rect x="{x - w / 2:.0f}" y="{y - card_h / 2:.0f}" width="{w}" '
                     f'height="{card_h}" rx="{T["card_radius"]}" fill="{T["card_fill"]}" stroke="{T["card_stroke"]}" '
                     f'stroke-width="1.5"/>'
                     f'<text x="{x:.0f}" y="{y - card_h / 2 + 17:.0f}" text-anchor="middle" '
                     f'font-size="{meta.get("fs", [12.5, 14])[0]}" fill="{T["card_label"]}">{label}</text>')
        if value:
            parts.append(f'<text x="{x:.0f}" y="{y + card_h / 2 - 7:.0f}" text-anchor="middle" '
                         f'font-size="{meta.get("fs", [12.5, 14])[1]}" font-weight="bold" '
                         f'fill="{T["card_value"]}">{value}</text>')
        parts.append('</g>')
    parts.append('</svg>')

    cert_html = ""
    if cert:
        m = cert["metrics"]
        def _cls(v):
            return "ok" if v else "bad"
        def _mark(v):
            return "✓" if v else "✗"
        rows = "".join(
            f'<tr><td>{k}</td><td class="{_cls(v)}">{_mark(v)}</td></tr>'
            for k, v in cert["gates"].items())
        cert_html = f'''<div class="cert">{_cert_head(cert["grade"], "rechecked on delivered coordinates · ortho-v1 theorem guarantee")}
<div class="cert-detail">
<table>
<tr><td>Crossings</td><td>{m["crossings"]}</td></tr>
<tr><td>Line piercing unrelated cards (0px)</td><td>{m["occlusions_true_0px"]}</td></tr>
<tr><td>Line piercing unrelated cards (4px inflated)</td><td>{m["occlusions_inflated4px"]}</td></tr>
<tr><td>Average edge length</td><td>{m["avg_edge_length"]}</td></tr>
<tr><td>Row alignment rate</td><td>{m["row_align_rate"]}</td></tr>
<tr><td>Minimum card gap</td><td>{m["min_card_gap"]}</td></tr>
<tr><td>Spacing coefficient of variation (CV)</td><td>{m["spacing_cv"]}</td></tr>
</table>
<h4>Gates {cert["gates_passed"]}</h4><table>{rows}</table>
<p class="grade">Grade: <b>{cert["grade"]}</b> — {html.escape(cert["grade_note"])}</p>
<p class="note">{html.escape(" / ".join(cert.get("honest_notes", [])))}</p>
</div>
</div>'''
    loops_html = ""
    if loops_report:
        def _status(it):
            st = "closed ✓" if it["closed"] else "not closed ✗"
            par = "balancing B" if it["neg_edges"] % 2 else "reinforcing R"
            bad = "" if it["kind_consistent"] else " (inconsistent with declaration!)"
            return f'{st}, negative edges {it["neg_edges"]} -> {par}{bad}'
        items = "".join(
            '<li>[{} {}] {} — {}</li>'.format(
                it["declared_kind"] or "?", it["id"], html.escape(it["label"]),
                _status(it))
            for it in loops_report["loops"])
        probs = loops_report["problems"]
        prob_text = html.escape("; ".join(probs)) if probs else "no problems"
        loops_html = ('<div class="cert"><h3>Loop semantics audit</h3><ul>' + items +
                      '</ul><p>' + prob_text + '</p></div>')

    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>stdraw 2D · {html.escape(graph_name)}</title>
<style>
body{{margin:16px;background:{T["page_bg"]};font-family:Microsoft YaHei,sans-serif}}
h1{{font-size:18px}} svg{{background:{T["canvas_bg"]};border:1px solid {T["canvas_border"]};border-radius:8px;max-width:1280px}}
{_cert_css(T)}
.ok{{color:{T["ok"]}}} .bad{{color:{T["bad"]}}} .note{{color:{T["note"]};font-size:12px}}
.grade{{color:{T["grade"]}}}
</style>
<h1>stdraw 2D layout · {html.escape(graph_name)} (visibility representation: all-vertical lines, 0 crossings guaranteed by theorem; unrelated lines piercing cards occlusion-style is allowed by design)</h1>
{''.join(parts)}
{cert_html}
{loops_html}
<p class="note">stdraw M0 · honest grading: this certificate holds only for this graph and this layout; no claim of 0 crossings for arbitrary graphs.</p>
'''


# ═══ auto-v2 rendering: straight/arc lines first-class + anchored directional arrows ═══
# Edge coloring caliber (jacky 2026-11-09 ruling, two-color polarity rework):
# lines carry exactly TWO colors keyed to each edge's own sign — '+' = amber,
# '−' = sky blue — and every line is solid. The dashed=negative encoding, the
# gray shared-edge color and the loop-id badges are retired; loop membership is
# no longer a visual encoding (a shared R/B edge takes its own sign color).
# The legend shrinks to two swatches + "+"/"−". Polarity data in layout.json /
# certificate.json unchanged. Token values live in stdraw/themes.py (one
# definition consumed by the static export and the viewer alike).


def _edge_svg(e, labels, values, T):
    """One edge -> SVG (line/poly polyline, arc real Bezier, vg exact L+A
    path); arrow follows the last segment direction."""
    r = e["route"]
    pts = r["points"]
    pol = e.get("polarity", "+")
    color = (T["edge_neg"] if pol == "-" else
             T["edge_pos"] if pol == "+" else T["neutral"])
    if r.get("path_d"):
        d = r["path_d"]
    elif r["kind"] == "arc" and "ctrl" in r:
        c = r["ctrl"]
        d = (f'M {pts[0][0]} {pts[0][1]} Q {c[0]} {c[1]} '
             f'{pts[-1][0]} {pts[-1][1]}')
    else:
        d = 'M ' + ' L '.join(f'{p[0]} {p[1]}' for p in pts)
    out = [f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.3"/>']
    # Arrow: last-segment direction
    import math as _m
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = _m.degrees(_m.atan2(y2 - y1, x2 - x1))
    ax, ay = e["arrow"]
    out.append(f'<path d="M 0 0 L -7 -3 L -7 3 Z" fill="{color}" '
               f'transform="translate({ax} {ay}) rotate({ang:.1f})"/>')
    return ''.join(out)


# R/B text badges were removed together with the coloring rework: edge
# coloring now carries each edge's own sign ('+' amber / '−' sky, all solid);
# polarity data stays in layout.json / certificate.json. The drag layer was
# synced the same way: the badge replay (refreshMarkers/polGroups) in
# _interactive_js was removed too, and drag re-routing keeps the static
# stroke attributes.


def render_auto_html(v4: dict, graph_name: str = "", cert: dict = None,
                     loops_report: dict = None, labels: dict = None,
                     values: dict = None,
                     theme: str = DEFAULT_STATIC_THEME) -> str:
    T = _get_theme(theme)
    W, H = v4["viewBox"][2], v4["viewBox"][3]
    nodes, edges = v4["nodes"], v4["edges"]
    meta = v4["meta"]
    card_h = meta.get("cardH", 44)
    labels = labels or {}
    values = values or {}

    parts = []
    parts.append(f'<svg id="stdraw-svg" viewBox="0 0 {W} {H}" '
                 f'font-family="Microsoft YaHei,sans-serif">')
    # Canvas grid layer (UI-A): dots (light) / lines (dark), beneath every
    # edge/card; static geometry, untouched by the interactive drag layer.
    parts.append(_grid_layer(W, H, T))
    # R/B text badges removed (each edge's sign is now expressed by two-color
    # edge coloring: '+' amber / '−' sky blue, all solid).
    # Polarity data stays in layout.json / certificate.json.
    for i, e in enumerate(edges):
        e["_idx"] = i
        parts.append(f'<g data-edge="{i}">' + _edge_svg(e, labels, values, T) + '</g>')
    for v, p in nodes.items():
        x, y, w = p["x"], p["y"], p["w"]
        label = html.escape(labels.get(v, v))
        value = html.escape(values.get(v, ""))
        parts.append(f'<g data-node="{html.escape(v, quote=True)}">'
                     f'<rect x="{x - w / 2:.0f}" y="{y - card_h / 2:.0f}" width="{w}" '
                     f'height="{card_h}" rx="{T["card_radius"]}" fill="{T["card_fill"]}" stroke="{T["card_stroke"]}" '
                     f'stroke-width="1.5"/>'
                     f'<text x="{x:.0f}" y="{y + 4:.0f}" text-anchor="middle" '
                     f'dominant-baseline="middle" '
                     f'font-size="{meta.get("fs", [12.5, 14])[0]}" fill="{T["card_label"]}">{label}</text>')
        if value:
            parts.append(f'<text x="{x:.0f}" y="{y + card_h / 2 - 7:.0f}" text-anchor="middle" '
                         f'font-size="{meta.get("fs", [12.5, 14])[1]}" font-weight="bold" '
                         f'fill="{T["card_value"]}">{value}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    # ── Interactive layer: toolbar + embedded data + script ──
    # Zero dependencies, zero network; without dragging the initial geometry is
    # byte-identical to the static rendering (the script only attaches
    # listeners; the v0.7.9 font-environment sync is a strict no-op whenever
    # the rendered text fits the planned cards, which the engine's
    # conservative text-metrics padding guarantees in matching environments).
    payload = {
        "name": graph_name,
        "viewBox": [0, 0, W, H],
        "cardH": card_h,
        "nodes": [{"id": v, "x": p["x"], "y": p["y"], "w": p.get("w", 140)}
                  for v, p in nodes.items()],
        "edges": [{"a": e["a"], "b": e["b"], "pol": e.get("polarity", "+"),
                   "arc": bool(e["route"].get("arc")),
                   "ctrl": e["route"].get("ctrl"),
                   # vg polyline corner points (handle positions and the bend
                   # semantics source for drag re-routing)
                   "via": e["route"].get("via"),
                   "pts": e["route"]["points"]}
                  for e in edges],
    }
    parts.append(
        '<div class="stdraw-toolbar">'
        '<span class="stdraw-hint">Drag cards to rearrange (mouse/touch) · double-click a line '
        'to cycle its style (auto/straight/arc/free) · in free style click the line to add fold '
        'points (max 8) · drag a segment of a hand-drawn line to shift it · hover a box to show '
        'its 16 standard anchors (toggle) · drag an edge endpoint to snap it to the nearest '
        'anchor · click an anchor to connect explicitly · metrics are live '
        'recomputed on preview geometry; the certificate is '
        'authoritative via CLI --from-layout</span>'
        '<span id="stdraw-metrics">…</span>'
        '<button id="stdraw-anchors-toggle" type="button">Anchors: off</button>'
        '<button id="stdraw-export" type="button">Export layout</button>'
        '<button id="stdraw-reset" type="button">Reset</button>'
        '</div>')
    parts.append('<script id="stdraw-data" type="application/json">' +
                 json.dumps(payload, ensure_ascii=False,
                            separators=(",", ":")).replace("</", "<\\/") +
                 '</script>')
    parts.append('<scr' + 'ipt>' + _INTERACTIVE_JS + '</scr' + 'ipt>')

    cert_html = ""
    if cert:
        m = cert["metrics"]
        def _cls(v):
            return "ok" if v else "bad"
        def _mark(v):
            return "✓" if v else "✗"
        rows = "".join(
            f'<tr><td>{k}</td><td class="{_cls(v)}">{_mark(v)}</td></tr>'
            for k, v in cert["gates"].items())
        placement = cert.get("placement")
        metric_rows = (
            f'<tr><td>Crossings (soft target · report item)</td><td>{m["crossings"]}</td></tr>'
            f'<tr><td>Visual crossings (hard gate · incl. fan pairs)</td><td>{m.get("visual_crossings")}</td></tr>'
            f'<tr><td>Box press (1px margin)</td><td>{m["box_press_1px"]}</td></tr>'
            f'<tr><td>Min edge-box clearance</td><td>{m["edge_box_min_clear"]}</td></tr>'
            f'<tr><td>Anchor violations</td><td>{m["anchor_violations"]}</td></tr>'
            f'<tr><td>Average edge length</td><td>{m["avg_edge_length"]}</td></tr>'
            f'<tr><td>Minimum card gap</td><td>{m["min_card_gap"]}</td></tr>'
            f'<tr><td>Line-kind distribution</td><td>{m.get("line_kind_counts")}</td></tr>')
        if placement == "ring-cycle":
            metric_rows += (
                f'<tr><td>On-ring equal-spacing CV</td><td>{m.get("ring_spacing_cv")}</td></tr>'
                f'<tr><td>Regular-polygon template deviation</td><td>{m.get("ring_template_deviation")}</td></tr>')
            placement_html = (
                '<h4>Placement mode: ring (main ring in regular-polygon slots + '
                'in-ring chord routing; row alignment / column snap inapplicable)</h4>')
        elif placement == "column-chain":
            metric_rows += (
                f'<tr><td>Main-chain column-axis deviation</td><td>{m.get("column_axis_deviation")}</td></tr>'
                f'<tr><td>Loop cohesion</td><td>{m.get("loop_cohesion_spread")}</td></tr>')
            placement_html = (
                '<h4>Placement mode: column (main chain in one vertical column + '
                'branches on the nearest side + closing edge as a large left arc; '
                'row alignment / column snap inapplicable)</h4>')
        elif placement == "comb-bilateral":
            metric_rows += (
                f'<tr><td>Column-axis deviation</td><td>{m.get("column_axis_deviation")}</td></tr>'
                f'<tr><td>Hub-pair symmetry error</td><td>{m.get("hub_symmetry_err")}</td></tr>')
            placement_html = (
                '<h4>Placement mode: comb-bilateral (sources in one vertical '
                'column + two mirrored hub wings at the column middle row; '
                'all hub edges straight lines)</h4>')
        elif placement == "symmetric":
            metric_rows += (
                f'<tr><td>Mirror-axis error</td><td>{m.get("symmetry_mirror_err")}</td></tr>')
            placement_html = (
                '<h4>Placement mode: symmetric (shared edge on the vertical axis + '
                'left/right vertices mirrored; axis edges straight + side edges all arcs)</h4>')
        else:
            metric_rows += (
                f'<tr><td>Row alignment rate (report item)</td><td>{m["row_align_rate"]}</td></tr>'
                f'<tr><td>Spacing coefficient of variation (CV)</td><td>{m["spacing_cv"]}</td></tr>'
                f'<tr><td>24px column snap rate</td><td>{m["column_snap24_rate"]}</td></tr>')
            placement_html = ""
        rep = cert.get("reports") or {}
        rep_html = ""
        if rep:
            rep_html = (f'<h4>Report items (non-vetoing)</h4><table>'
                        f'<tr><td>0 crossings</td><td class="{_cls(rep.get("crossings_zero"))}">'
                        f'{_mark(rep.get("crossings_zero"))}</td></tr>'
                        f'<tr><td>Row alignment &ge;0.60</td>'
                        f'<td class="{_cls(rep.get("row_align_ge_060"))}">'
                        f'{_mark(rep.get("row_align_ge_060"))}</td></tr></table>')
        legend = ('<p class="note">Edge sign: '
                  '<svg width="28" height="10" style="vertical-align:middle" aria-hidden="true">'
                  f'<line x1="2" y1="5" x2="26" y2="5" stroke="{T["edge_pos"]}" stroke-width="4"/></svg> <b>+</b>'
                  '&nbsp;&nbsp;'
                  '<svg width="28" height="10" style="vertical-align:middle" aria-hidden="true">'
                  f'<line x1="2" y1="5" x2="26" y2="5" stroke="{T["edge_neg"]}" stroke-width="4"/></svg> <b>−</b></p>')
        # Ink-sign summary (UI-A spec D3/§4.3): two-column label/value table,
        # square outer frame (styled in _cert_css), stamp-style grade.
        cv_val = m.get("spacing_cv")
        if cv_val is None:
            cv_val = m.get("ring_spacing_cv")
        cv_text = "—" if cv_val is None else cv_val
        mode_val = placement or "layered"
        sign_rows = (
            f'<tr><td class="lbl">GRADE</td><td class="val">'
            f'<span class="{"stamp" if cert["grade"] == "best" else "stamp stamp-mut"}">'
            f'{html.escape(cert["grade"])}</span></td></tr>'
            f'<tr><td class="lbl">GATES</td><td class="val">{cert["gates_passed"]}</td></tr>'
            f'<tr><td class="lbl">CROSSINGS</td><td class="val">{m["crossings"]}</td></tr>'
            f'<tr><td class="lbl">PRESS</td><td class="val">{m["box_press_1px"]}</td></tr>'
            f'<tr><td class="lbl">CLEAR</td><td class="val">{m["edge_box_min_clear"]}</td></tr>'
            f'<tr><td class="lbl">CV</td><td class="val">{cv_text}</td></tr>'
            f'<tr><td class="lbl">MODE</td><td class="val">{html.escape(mode_val)}</td></tr>')
        cert_html = f'''<div class="cert">{_cert_head(cert["grade"], "rechecked on delivered coordinates · auto-v2 hard gates")}
<table class="cert-sign">
{sign_rows}
</table>
<div class="cert-detail">
<h4>Metrics</h4>
<table>
{metric_rows}
</table>
{placement_html}
<h4>Gates {cert["gates_passed"]}</h4><table>{rows}</table>
{rep_html}
<p class="grade">Grade: <b>{cert["grade"]}</b> — {html.escape(cert["grade_note"])}</p>
{legend}
<p class="note">{html.escape(" / ".join(cert.get("honest_notes", [])))}</p>
</div>
</div>'''
    loops_html = ""
    if loops_report:
        def _status(it):
            st = "closed ✓" if it["closed"] else "not closed ✗"
            par = "balancing B" if it["neg_edges"] % 2 else "reinforcing R"
            bad = "" if it["kind_consistent"] else " (inconsistent with declaration!)"
            return f'{st}, negative edges {it["neg_edges"]} -> {par}{bad}'
        items = "".join(
            '<li>[{} {}] {} — {}</li>'.format(
                it["declared_kind"] or "?", it["id"], html.escape(it["label"]),
                _status(it))
            for it in loops_report["loops"])
        probs = loops_report["problems"]
        prob_text = html.escape("; ".join(probs)) if probs else "no problems"
        loops_html = ('<div class="cert"><h3>Loop semantics audit</h3><ul>' + items +
                      '</ul><p>' + prob_text + '</p></div>')

    engine = meta.get("position_engine", "construct")
    ls = meta.get("line_style", "straight")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>stdraw 2D · {html.escape(graph_name)}</title>
<style>
body{{margin:16px;background:{T["page_bg"]};font-family:Microsoft YaHei,sans-serif}}
h1{{font-size:18px}} svg{{background:{T["canvas_bg"]};border:1px solid {T["canvas_border"]};border-radius:8px;max-width:1280px}}
{_cert_css(T)}
.ok{{color:{T["ok"]}}} .bad{{color:{T["bad"]}}} .note{{color:{T["note"]};font-size:12px}}
.grade{{color:{T["grade"]}}}
.stdraw-toolbar{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:10px;padding:8px 12px;background:{T["toolbar_bg"]};border:1px solid {T["toolbar_border"]};border-radius:8px;font-size:13px;max-width:1280px}}
.stdraw-toolbar button{{padding:4px 14px;border:1px solid {T["btn_border"]};border-radius:6px;background:{T["btn_bg"]};color:{T["btn_text"]};cursor:pointer;font-size:13px}}
.stdraw-toolbar button:hover{{background:{T["btn_hover_bg"]}}}
.stdraw-hint{{color:{T["hint_text"]};font-size:12px}}
#stdraw-metrics{{font-weight:600;color:{T["metrics_text"]}}}
#stdraw-svg{{--stdraw-chrome-b:{T["edge_neg"]};--stdraw-chrome-r:{T["edge_pos"]}}}
#stdraw-svg [data-node]{{cursor:grab}}
#stdraw-svg [data-node] rect{{touch-action:none}}
#stdraw-svg [data-node].dragging{{cursor:grabbing}}
</style>
<h1>stdraw 2D layout · {html.escape(graph_name)} (auto-v2: straight/arc lines first-class, zero box-press hard gate, edge-box clearance &ge;16px; position engine {engine}, line style {ls})</h1>
{''.join(parts)}
{cert_html}
{loops_html}
<p class="note">stdraw auto-v2 · honest grading: the crossing count is an objective-function minimization term, not a theorem guarantee; this certificate holds only for this graph and this layout.</p>
'''
