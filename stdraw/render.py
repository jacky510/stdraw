# -*- coding: utf-8 -*-
"""2D 渲染层：planar 布局 JSON → 独立 HTML（内联 SVG，零依赖零联网）。"""
import html
import json


def render_html(v4: dict, graph_name: str = "", cert: dict = None,
                loops_report: dict = None, labels: dict = None,
                values: dict = None) -> str:
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
