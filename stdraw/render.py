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
# ref-scrubbed R/B 颜色化：回路边按所属声明回路极性着色（R=琥珀 #d97706 /
# B=天蓝 #0284c7——线上惯例色相的白底可读加深档），去掉 R/B 文字
# 徽标（复杂图文字干扰）；负极性边虚线（+/- 语义保留）；极性数据在
# layout.json / certificate.json 不变。
LOOP_COLOR_R = "#d97706"
LOOP_COLOR_B = "#0284c7"
NEUTRAL_COLOR = "#64748b"


def _edge_svg(e, labels, values):
    """单条边 → SVG（line/poly 折线，arc 真贝塞尔，vg 精确 L+A 路径），箭头按末段方向。"""
    r = e["route"]
    pts = r["points"]
    color = e.get("loop_color") or NEUTRAL_COLOR
    dash = ' stroke-dasharray="6 4"' if e.get("polarity") == "-" else ""
    if r.get("path_d"):
        d = r["path_d"]
    elif r["kind"] == "arc" and "ctrl" in r:
        c = r["ctrl"]
        d = (f'M {pts[0][0]} {pts[0][1]} Q {c[0]} {c[1]} '
             f'{pts[-1][0]} {pts[-1][1]}')
    else:
        d = 'M ' + ' L '.join(f'{p[0]} {p[1]}' for p in pts)
    out = [f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.3"{dash}/>']
    # 箭头：末段方向
    import math as _m
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = _m.degrees(_m.atan2(y2 - y1, x2 - x1))
    ax, ay = e["arrow"]
    out.append(f'<path d="M 0 0 L -7 -3 L -7 3 Z" fill="{color}" '
               f'transform="translate({ax} {ay}) rotate({ang:.1f})"/>')
    return ''.join(out)


# ref-scrubbed：R/B 文字徽标（_polarity_marker/_poly_point_at/_pt_poly_dist）
# 已随「回路极性颜色化」移除——徽标语义由边着色（R=琥珀/B=天蓝）+ 负边
# 虚线承载；极性数据保留在 layout.json / certificate.json。
# 拖拽层同步：_interactive_js 的徽标重放（refreshMarkers/polGroups）一并移除。


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
    # ref-scrubbed：R/B 文字徽标已去除（回路极性改由边着色表达：R=琥珀/B=天蓝；
    # 负极性边虚线）。极性数据保留在 layout.json / certificate.json。
    for i, e in enumerate(edges):
        e["_idx"] = i
        parts.append(f'<g data-edge="{i}">' + _edge_svg(e, labels, values) + '</g>')
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
                   # ref-scrubbed：vg 折线角点（把手位置与拖拽重布线的折点语义源）
                   "via": e["route"].get("via"),
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
        placement = cert.get("placement")
        metric_rows = (
            f'<tr><td>交叉（软目标·报告项）</td><td>{m["crossings"]}</td></tr>'
            f'<tr><td>框压线(1px余量)</td><td>{m["box_press_1px"]}</td></tr>'
            f'<tr><td>边-框最小净距</td><td>{m["edge_box_min_clear"]}</td></tr>'
            f'<tr><td>锚点违例</td><td>{m["anchor_violations"]}</td></tr>'
            f'<tr><td>平均边长</td><td>{m["avg_edge_length"]}</td></tr>'
            f'<tr><td>卡间最小净距</td><td>{m["min_card_gap"]}</td></tr>'
            f'<tr><td>线型分布</td><td>{m.get("line_kind_counts")}</td></tr>')
        if placement == "ring-cycle":
            metric_rows += (
                f'<tr><td>环上等间距 CV</td><td>{m.get("ring_spacing_cv")}</td></tr>'
                f'<tr><td>正多边形模板偏差</td><td>{m.get("ring_template_deviation")}</td></tr>')
            placement_html = (
                '<h4>排布模式：环形（主环正多边形槽位 + 弦内布线；'
                '行对齐率/列吸附口径不适用）</h4>')
        elif placement == "column-chain":
            metric_rows += (
                f'<tr><td>主链列轴偏差</td><td>{m.get("column_axis_deviation")}</td></tr>'
                f'<tr><td>回路聚拢度</td><td>{m.get("loop_cohesion_spread")}</td></tr>')
            placement_html = (
                '<h4>排布模式：纵列（主链纵向对齐一列 + 支路挂近邻侧 + '
                '闭合边左侧大弧；行对齐率/列吸附口径不适用）</h4>')
        elif placement == "symmetric":
            metric_rows += (
                f'<tr><td>镜像轴误差</td><td>{m.get("symmetry_mirror_err")}</td></tr>')
            placement_html = (
                '<h4>排布模式：对称（共享边居纵轴 + 左右顶点镜像；'
                '轴边直线 + 侧边全弧）</h4>')
        else:
            metric_rows += (
                f'<tr><td>行对齐率（报告项）</td><td>{m["row_align_rate"]}</td></tr>'
                f'<tr><td>间距变异系数 CV</td><td>{m["spacing_cv"]}</td></tr>'
                f'<tr><td>24px 列吸附率</td><td>{m["column_snap24_rate"]}</td></tr>')
            placement_html = ""
        rep = cert.get("reports") or {}
        rep_html = ""
        if rep:
            rep_html = (f'<h4>报告项（不一票否决）</h4><table>'
                        f'<tr><td>0 交叉</td><td class="{_cls(rep.get("crossings_zero"))}">'
                        f'{_mark(rep.get("crossings_zero"))}</td></tr>'
                        f'<tr><td>行对齐 ≥0.60</td>'
                        f'<td class="{_cls(rep.get("row_align_ge_060"))}">'
                        f'{_mark(rep.get("row_align_ge_060"))}</td></tr></table>')
        legend = ('<p class="note">边着色：琥珀=增强回路(R) · 天蓝=平衡回路(B) · '
                  '灰=非回路边/多环异色；虚线=负极性（−）</p>')
        cert_html = f'''<div class="cert"><h3>质量证书（交付坐标复检 · auto-v2 硬门）</h3>
<table>
{metric_rows}
</table>
{placement_html}
<h4>门禁 {cert["gates_passed"]}</h4><table>{rows}</table>
{rep_html}
<p class="grade">分级：<b>{cert["grade"]}</b> — {html.escape(cert["grade_note"])}</p>
{legend}
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
