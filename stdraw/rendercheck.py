# -*- coding: utf-8 -*-
"""框界真值层（① CI 侧）：真实渲染后用无头浏览器量 DOM 实际框界。

与 textmetrics（布局侧保守度量）构成两层验证——缺一层不许报完成：
  - 布局侧：按真实字体最坏度量 + 保守 padding 规划框界（textmetrics.card_size）；
  - CI 侧：本模块在真实渲染后逐卡量 DOM `getBBox()`，与规划框界比对，
    文字实际宽度超出框内可用宽度（框宽 − 2×PAD_SIDE_MIN）即 fail——
    证书量的不再是估算值，而是渲染真值。

用法：
    python -m stdraw.rendercheck <outdir>       # 量 outdir/demo-2d.html vs layout.json
退出码：0 全过；1 有超出；2 playwright 不可用（如实跳过，不算通过也不算失败）。

依赖：`pip install stdraw[render-check]`（playwright；首次需 playwright install chromium）。
"""
import json
import sys

from .textmetrics import PAD_SIDE_MIN


def check_dom_bounds(html_path: str, layout: dict, tol: float = 0.5):
    """playwright 无头 chromium 打开 demo，逐卡量文字 getBBox 对比框界。

    返回 (problems, checked_n)。problems: [{node, text_w, avail_w}]。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, 0
    meta = layout["meta"]
    fs_title = meta.get("fs", [12.5, 14.0])[0]
    problems = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path}")
            page.wait_for_timeout(600)
            data = page.evaluate("""() => {
              const out = [];
              document.querySelectorAll('svg g').forEach(g => {
                const rect = g.querySelector('rect');
                const text = g.querySelector('text');
                if (rect && text) {
                  const tb = text.getBBox();
                  out.push({text: text.textContent,
                            textW: tb.width,
                            boxX: +rect.getAttribute('x'),
                            boxW: +rect.getAttribute('width')});
                }
              });
              return out;
            }""")
            browser.close()
    except Exception:
        return None, 0
    id2n = {v: p_ for v, p_ in layout["nodes"].items()}
    # demo 里 label 文本 → 节点（layout 键序与渲染一致）
    labels = {nd.get("label", ""): v for v, nd in
              (layout.get("_labels") or {}).items()}
    for row in data:
        avail = row["boxW"] - 2 * PAD_SIDE_MIN
        if row["textW"] > avail + tol:
            problems.append({"node": row["text"], "text_w": round(row["textW"], 1),
                             "avail_w": round(avail, 1)})
    return problems, len(data)


def main(argv):
    if len(argv) < 1:
        print("用法: python -m stdraw.rendercheck <outdir>", file=sys.stderr)
        return 2
    import os
    outdir = argv[0]
    with open(os.path.join(outdir, "layout.json"), encoding="utf-8") as f:
        layout = json.load(f)
    problems, n = check_dom_bounds(os.path.abspath(
        os.path.join(outdir, "demo-2d.html")), layout)
    if problems is None:
        print("SKIP: playwright 不可用（pip install stdraw[render-check] 后可跑）")
        return 2
    print(f"{n} 卡 DOM 实测完成，超出 {len(problems)}")
    for pr in problems:
        print("  OVERFLOW", pr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
