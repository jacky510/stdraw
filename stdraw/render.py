# -*- coding: utf-8 -*-
"""2D 渲染层：planar 布局 JSON → 独立 HTML（内联 SVG，零依赖零联网）。"""
import html
import json

from ._interactive_js import _INTERACTIVE_JS


def render_html(v4: dict, graph_name: str = "", cert: dict = None,
                loops_report: dict = None, labels: dict = None,
                values: dict = None) -> str:
    if v4.get("edges") and "route" in v4["edges"][0]:
        return render_auto_html(v4, graph_name, cert, loops_report, labels, values)
    W, H = v4["viewBox"][2], v4["viewBox"][3]
    nodes, edges, bars = v4["nodes"], v4["edges"], v4.get("bars", {})
    meta = v4["meta"]
    card_h = meta.get("cardH", 42)
    labels = labels or {}
    values = values or {}

    parts = []
    parts.append(f'<svg viewBox="0 0 {W} {H}" font-family="Microsoft YaHei,sans-serif">')
    # 引线 bar（水平横线，位于卡片行中心，只横贯自身关联线列）
    for v, (b0, b1) in bars.items():
        parts.append(f'<line x1="{b0}" y1="{nodes[v]["y"]}" x2="{b1}" y2="{nodes[v]["y"]}" '
                     f'stroke="#94a3b8" stroke-width="2"/>')
    # 竖线 + 箭头
    for e in edges:
        x, y1, y2 = e["x"], e["y1"], e["y2"]
        parts.append(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" '
                     f'stroke="#64748b" stroke-width="1.3"/>')
        ax, ay, d = e["arrow"]
        parts.append(f'<path d="M {ax - 4} {ay - 6 * d} L {ax} {ay} L {ax + 4} {ay - 6 * d} '
                     f'Z" fill="#64748b"/>')
    # 卡片
    for v, p in nodes.items():
        x, y, w = p["x"], p["y"], p["w"]
        label = html.escape(labels.get(v, v))
        value = html.escape(values.get(v, ""))
        parts.append(f'<g><rect x="{x - w / 2:.0f}" y="{y - card_h / 2:.0f}" width="{w}" '
                     f'height="{card_h}" rx="7" fill="#fffbeb" stroke="#f59e0b" '
                     f'stroke-width="1.5"/>'
                     f'<text x="{x:.0f}" y="{y - card_h / 2 + 17:.0f}" text-anchor="middle" '
                     f'font-size="{meta.get("fs", [12.5, 14])[0]}" fill="#78350f">{label}</text>')
        if value:
            parts.append(f'<text x="{x:.0f}" y="{y + card_h / 2 - 7:.0f}" text-anchor="middle" '
                         f'font-size="{meta.get("fs", [12.5, 14])[1]}" font-weight="bold" '
                         f'fill="#1f2937">{value}</text>')
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
        cert_html = f'''<div class="cert"><h3>质量证书（交付坐标复检）</h3>
<table>
<tr><td>交叉</td><td>{m["crossings"]}</td></tr>
<tr><td>线穿无关卡(0px)</td><td>{m["occlusions_true_0px"]}</td></tr>
<tr><td>线穿无关卡(外扩4px)</td><td>{m["occlusions_inflated4px"]}</td></tr>
<tr><td>平均边长</td><td>{m["avg_edge_length"]}</td></tr>
<tr><td>行对齐率</td><td>{m["row_align_rate"]}</td></tr>
<tr><td>卡间最小净距</td><td>{m["min_card_gap"]}</td></tr>
<tr><td>间距变异系数 CV</td><td>{m["spacing_cv"]}</td></tr>
</table>
<h4>门禁 {cert["gates_passed"]}</h4><table>{rows}</table>
<p class="grade">分级：<b>{cert["grade"]}</b> — {html.escape(cert["grade_note"])}</p>
<p class="note">{html.escape(" / ".join(cert.get("honest_notes", [])))}</p>
</div>'''
    loops_html = ""
    if loops_report:
        def _status(it):
            st = "闭合✓" if it["closed"] else "不闭合✗"
            par = "平衡B" if it["neg_edges"] % 2 else "增强R"
            bad = "" if it["kind_consistent"] else "（与声明不一致！）"
            return f'{st}，负边 {it["neg_edges"]} 条 → {par}{bad}'
        items = "".join(
            '<li>[{} {}] {} — {}</li>'.format(
                it["declared_kind"] or "?", it["id"], html.escape(it["label"]),
                _status(it))
            for it in loops_report["loops"])
        probs = loops_report["problems"]
        prob_text = html.escape("; ".join(probs)) if probs else "无问题"
        loops_html = ('<div class="cert"><h3>环路语义审计</h3><ul>' + items +
                      '</ul><p>' + prob_text + '</p></div>')

    return f'''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>stdraw 2D · {html.escape(graph_name)}</title>
<style>
body{{margin:16px;background:#f8fafc;font-family:Microsoft YaHei,sans-serif}}
h1{{font-size:18px}} svg{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;max-width:1280px}}
.cert{{margin-top:12px;padding:10px 14px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;max-width:1280px}}
.cert table{{border-collapse:collapse}} .cert td{{border:1px solid #e2e8f0;padding:2px 10px}}
.ok{{color:#16a34a}} .bad{{color:#dc2626}} .note{{color:#64748b;font-size:12px}}
.grade{{color:#1d4ed8}}
</style>
<h1>stdraw 2D 布局 · {html.escape(graph_name)}（可见性表示：线全竖直、0 交叉有定理保证；无关线遮挡式穿卡为设计允许）</h1>
{''.join(parts)}
{cert_html}
{loops_html}
<p class="note">stdraw M0 · 诚实分级：本证书只对本图本布局成立，绝不宣称任意图 0 交叉。</p>
'''


# ═══ auto-v2 渲染（2026-11-05 六点返修）：直线/弧线一等 + 锚点方向箭头 ═══
def _edge_svg(e, labels, values):
    """单条边 → SVG（line/poly 折线，arc 真贝塞尔，vg 精确 L+A 路径），箭头按末段方向。"""
    r = e["route"]
    pts = r["points"]
    color = "#64748b"
    if r.get("path_d"):
        d = r["path_d"]
    elif r["kind"] == "arc" and "ctrl" in r:
        c = r["ctrl"]
        d = (f'M {pts[0][0]} {pts[0][1]} Q {c[0]} {c[1]} '
             f'{pts[-1][0]} {pts[-1][1]}')
    else:
        d = 'M ' + ' L '.join(f'{p[0]} {p[1]}' for p in pts)
    out = [f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.3"/>']
    # 箭头：末段方向
    import math as _m
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = _m.degrees(_m.atan2(y2 - y1, x2 - x1))
    ax, ay = e["arrow"]
    out.append(f'<path d="M 0 0 L -7 -3 L -7 3 Z" fill="{color}" '
               f'transform="translate({ax} {ay}) rotate({ang:.1f})"/>')
    return ''.join(out)


# ═══ WS3：R/B 极性标记（随切线方向确定性放置，不遮字不压线）═══
def _poly_point_at(pts, t):
    """折线按弧长比例取点与局部切向。"""
    import math as _m
    segs = [(_m.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
            for i in range(len(pts) - 1)]
    total = sum(segs)
    target = total * max(0.0, min(1.0, t))
    acc = 0.0
    for i, L in enumerate(segs):
        if acc + L >= target and L > 0:
            f = (target - acc) / L
            p = (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
                 pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f)
            d = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            n = _m.hypot(*d) or 1.0
            return p, (d[0] / n, d[1] / n)
        acc += L
    return pts[-1], (0.0, 1.0)


def _pt_poly_dist(px, py, pts):
    """点到折线的最小距离。"""
    best = float("inf")
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
        d = ((px - ax - t * vx) ** 2 + (py - ay - t * vy) ** 2) ** 0.5
        best = min(best, d)
    return best


def _polarity_marker(e, polys, boxes, W, H, placed=()):
    """R/B 标记位置：确定性候选序（t × 法向偏移），首个不遮字不压线的位置。

    boxes: [(cx, cy, hw, hh)] 全部框；不遮字 = 与框外缘保持 ≥8px；
    不压线 = 与其他边折线保持 ≥11px；
    不互撞（ref-scrubbed #10②）= 与已放置徽标圆心保持 ≥17px
    （徽标圆 r=7.5，两圆不相交需 >15px，留 2px 视觉余量）。
    """
    pol = e.get("polarity", "+")
    if pol not in ("+", "-"):
        return None
    letter = "R" if pol == "+" else "B"
    color = "#dc2626" if pol == "+" else "#2563eb"
    own = e["route"]["points"]
    other_polys = [p for j, p in polys.items() if j != e.get("_idx")]
    for t in (0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74):
        p, tan = _poly_point_at(own, t)
        nx, ny = -tan[1], tan[0]
        for off in (10, -10, 14, -14, 18, -18, 22, -22):
            cand = (p[0] + nx * off, p[1] + ny * off)
            if not (8 <= cand[0] <= W - 8 and 8 <= cand[1] <= H - 8):
                continue
            # 不互撞：与已放置徽标 ≥17px
            if any((cand[0] - bx) ** 2 + (cand[1] - by) ** 2 < 17.0 ** 2
                   for (bx, by) in placed):
                continue
            # 不遮字：与任何框（含端点框）外缘保持 ≥8px
            near_box = False
            for (cx, cy, hw, hh) in boxes:
                dx = max(abs(cand[0] - cx) - hw, 0.0)
                dy = max(abs(cand[1] - cy) - hh, 0.0)
                if (dx * dx + dy * dy) ** 0.5 < 8:
                    near_box = True
                    break
            if near_box:
                continue
            # 不压线：与其他边折线保持 ≥11px
            if any(_pt_poly_dist(cand[0], cand[1], p2) < 11 for p2 in other_polys):
                continue
            return cand, letter, color
    return None


def render_auto_html(v4: dict, graph_name: str = "", cert: dict = None,
                     loops_report: dict = None, labels: dict = None,
                     values: dict = None) -> str:
    W, H = v4["viewBox"][2], v4["viewBox"][3]
    nodes, edges = v4["nodes"], v4["edges"]
    meta = v4["meta"]
    card_h = meta.get("cardH", 44)
    labels = labels or {}
    values = values or {}

    parts = []
    parts.append(f'<svg id="stdraw-svg" viewBox="0 0 {W} {H}" '
                 f'font-family="Microsoft YaHei,sans-serif">')
    polys = {i: e["route"]["points"] for i, e in enumerate(edges)}
    boxes = [(p["x"], p["y"], p.get("w", 140) / 2, card_h / 2) for p in nodes.values()]
    for i, e in enumerate(edges):
        e["_idx"] = i
        parts.append(f'<g data-edge="{i}">' + _edge_svg(e, labels, values) + '</g>')
    # WS3：R/B 极性标记（确定性放置，白底盘 + 字母）；
    # ref-scrubbed #10②：逐个放置时与已放徽标保持 ≥17px（互撞避让）。
    placed_pol = []
    for i, e in enumerate(edges):
        mk = _polarity_marker(e, polys, boxes, W, H, placed_pol)
        if mk:
            (mx, my), letter, mcolor = mk
            placed_pol.append((mx, my))
            parts.append(f'<g data-pol="{i}" transform="translate({mx:.1f} {my:.1f})">'
                         f'<circle r="7.5" fill="#ffffff" stroke="{mcolor}" '
                         f'stroke-width="1.2"/>'
                         f'<text y="3.2" text-anchor="middle" font-size="9.5" '
                         f'font-weight="bold" fill="{mcolor}">{letter}</text></g>')
    for v, p in nodes.items():
        x, y, w = p["x"], p["y"], p["w"]
        label = html.escape(labels.get(v, v))
        value = html.escape(values.get(v, ""))
        parts.append(f'<g data-node="{html.escape(v, quote=True)}">'
                     f'<rect x="{x - w / 2:.0f}" y="{y - card_h / 2:.0f}" width="{w}" '
                     f'height="{card_h}" rx="7" fill="#fffbeb" stroke="#f59e0b" '
                     f'stroke-width="1.5"/>'
                     f'<text x="{x:.0f}" y="{y + 4:.0f}" text-anchor="middle" '
                     f'dominant-baseline="middle" '
                     f'font-size="{meta.get("fs", [12.5, 14])[0]}" fill="#78350f">{label}</text>')
        if value:
            parts.append(f'<text x="{x:.0f}" y="{y + card_h / 2 - 7:.0f}" text-anchor="middle" '
                         f'font-size="{meta.get("fs", [12.5, 14])[1]}" font-weight="bold" '
                         f'fill="#1f2937">{value}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    # ── 交互层（ref-scrubbed 拖拽重排）：工具栏 + 内嵌数据 + 脚本 ──
    # 零依赖零联网；不拖时初始几何与静态渲染完全一致（脚本只挂监听）。
    payload = {
        "name": graph_name,
        "viewBox": [0, 0, W, H],
        "cardH": card_h,
        "nodes": [{"id": v, "x": p["x"], "y": p["y"], "w": p.get("w", 140)}
                  for v, p in nodes.items()],
        "edges": [{"a": e["a"], "b": e["b"], "pol": e.get("polarity", "+"),
                   "arc": bool(e["route"].get("arc")),
                   "ctrl": e["route"].get("ctrl"),
                   "pts": e["route"]["points"]}
                  for e in edges],
    }
    parts.append(
        '<div class="stdraw-toolbar">'
        '<span class="stdraw-hint">拖动卡片重排（鼠标/触摸）· 指标为预览几何实时复算，'
        '证书以 CLI --from-layout 复算为准</span>'
        '<span id="stdraw-metrics">…</span>'
        '<button id="stdraw-export" type="button">导出布局</button>'
        '<button id="stdraw-reset" type="button">重置</button>'
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
        if cert.get("placement") == "ring-cycle":
            metric_rows = (
                f'<tr><td>交叉</td><td>{m["crossings"]}</td></tr>'
                f'<tr><td>框压线(1px余量)</td><td>{m["box_press_1px"]}</td></tr>'
                f'<tr><td>边-框最小净距</td><td>{m["edge_box_min_clear"]}</td></tr>'
                f'<tr><td>锚点违例</td><td>{m["anchor_violations"]}</td></tr>'
                f'<tr><td>平均边长</td><td>{m["avg_edge_length"]}</td></tr>'
                f'<tr><td>环上等间距 CV</td><td>{m.get("ring_spacing_cv")}</td></tr>'
                f'<tr><td>正多边形模板偏差</td><td>{m.get("ring_template_deviation")}</td></tr>'
                f'<tr><td>卡间最小净距</td><td>{m["min_card_gap"]}</td></tr>')
            placement_html = (
                '<h4>排布模式：环形（主环正多边形槽位 + 弦内布线；'
                '行对齐率/列吸附口径不适用）</h4>')
        else:
            metric_rows = (
                f'<tr><td>交叉</td><td>{m["crossings"]}</td></tr>'
                f'<tr><td>框压线(1px余量)</td><td>{m["box_press_1px"]}</td></tr>'
                f'<tr><td>边-框最小净距</td><td>{m["edge_box_min_clear"]}</td></tr>'
                f'<tr><td>锚点违例</td><td>{m["anchor_violations"]}</td></tr>'
                f'<tr><td>平均边长</td><td>{m["avg_edge_length"]}</td></tr>'
                f'<tr><td>行对齐率</td><td>{m["row_align_rate"]}</td></tr>'
                f'<tr><td>卡间最小净距</td><td>{m["min_card_gap"]}</td></tr>'
                f'<tr><td>间距变异系数 CV</td><td>{m["spacing_cv"]}</td></tr>'
                f'<tr><td>24px 列吸附率</td><td>{m["column_snap24_rate"]}</td></tr>')
            placement_html = ""
        cert_html = f'''<div class="cert"><h3>质量证书（交付坐标复检 · auto-v2 硬门）</h3>
<table>
{metric_rows}
</table>
{placement_html}
<h4>门禁 {cert["gates_passed"]}</h4><table>{rows}</table>
<p class="grade">分级：<b>{cert["grade"]}</b> — {html.escape(cert["grade_note"])}</p>
<p class="note">{html.escape(" / ".join(cert.get("honest_notes", [])))}</p>
</div>'''
    loops_html = ""
    if loops_report:
        def _status(it):
            st = "闭合✓" if it["closed"] else "不闭合✗"
            par = "平衡B" if it["neg_edges"] % 2 else "增强R"
            bad = "" if it["kind_consistent"] else "（与声明不一致！）"
            return f'{st}，负边 {it["neg_edges"]} 条 → {par}{bad}'
        items = "".join(
            '<li>[{} {}] {} — {}</li>'.format(
                it["declared_kind"] or "?", it["id"], html.escape(it["label"]),
                _status(it))
            for it in loops_report["loops"])
        probs = loops_report["problems"]
        prob_text = html.escape("; ".join(probs)) if probs else "无问题"
        loops_html = ('<div class="cert"><h3>环路语义审计</h3><ul>' + items +
                      '</ul><p>' + prob_text + '</p></div>')

    engine = meta.get("position_engine", "construct")
    ls = meta.get("line_style", "straight")
    return f'''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>stdraw 2D · {html.escape(graph_name)}</title>
<style>
body{{margin:16px;background:#f8fafc;font-family:Microsoft YaHei,sans-serif}}
h1{{font-size:18px}} svg{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;max-width:1280px}}
.cert{{margin-top:12px;padding:10px 14px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;max-width:1280px}}
.cert table{{border-collapse:collapse}} .cert td{{border:1px solid #e2e8f0;padding:2px 10px}}
.ok{{color:#16a34a}} .bad{{color:#dc2626}} .note{{color:#64748b;font-size:12px}}
.grade{{color:#1d4ed8}}
.stdraw-toolbar{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:10px;padding:8px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;max-width:1280px}}
.stdraw-toolbar button{{padding:4px 14px;border:1px solid #cbd5e1;border-radius:6px;background:#f8fafc;cursor:pointer;font-size:13px}}
.stdraw-toolbar button:hover{{background:#e2e8f0}}
.stdraw-hint{{color:#64748b;font-size:12px}}
#stdraw-metrics{{font-weight:600;color:#1f2937}}
#stdraw-svg [data-node]{{cursor:grab}}
#stdraw-svg [data-node] rect{{touch-action:none}}
#stdraw-svg [data-node].dragging{{cursor:grabbing}}
</style>
<h1>stdraw 2D 布局 · {html.escape(graph_name)}（auto-v2：直线/弧线一等、框不压线硬门、边-框净距≥16px；定位引擎 {engine}，线型 {ls}）</h1>
{''.join(parts)}
{cert_html}
{loops_html}
<p class="note">stdraw auto-v2 · 诚实分级：交叉数是目标函数最小化项而非定理保证，本证书只对本图本布局成立。</p>
'''
