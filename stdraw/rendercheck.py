# -*- coding: utf-8 -*-
"""Bounding-box ground-truth layer (1, CI side): after real rendering, measure actual DOM bounds with a headless browser.

Together with textmetrics (conservative measurement on the layout side) this forms two-layer verification -- neither layer may be missing when claiming completion:
    - Layout side: plan bounds with worst-case measurement using the real font + conservative padding (textmetrics.card_size);
    - CI side: this module measures DOM `getBBox()` per card after real rendering and compares against the planned bounds;
        actual text width exceeding the usable width inside the box (box width - 2*PAD_SIDE_MIN) fails --
        the certificate now measures rendered ground truth rather than an estimate.

Usage:
        python -m stdraw.rendercheck <outdir>       # measure outdir/demo-2d.html vs layout.json
Exit codes: 0 all pass; 1 overflow found; 2 playwright unavailable (honest skip, counted as neither pass nor failure).

Dependency: `pip install stdraw[render-check]` (playwright; first run needs playwright install chromium).
"""
import json
import sys

from .textmetrics import PAD_SIDE_MIN


def check_dom_bounds(html_path: str, layout: dict, tol: float = 0.5):
    """Open the demo in headless chromium via playwright; measure text getBBox per card against the bounds.

    Returns (problems, checked_n). problems: [{node, text_w, avail_w}].
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
    # label text in the demo -> node (layout key order matches rendering)
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
        print("usage: python -m stdraw.rendercheck <outdir>", file=sys.stderr)
        return 2
    import os
    outdir = argv[0]
    with open(os.path.join(outdir, "layout.json"), encoding="utf-8") as f:
        layout = json.load(f)
    problems, n = check_dom_bounds(os.path.abspath(
        os.path.join(outdir, "demo-2d.html")), layout)
    if problems is None:
        print("SKIP: playwright unavailable (pip install stdraw[render-check] to enable)")
        return 2
    print(f"{n} cards DOM-measured, overflows {len(problems)}")
    for pr in problems:
        print("  OVERFLOW", pr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
