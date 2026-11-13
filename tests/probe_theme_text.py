#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Theme text-color regression probe (dark-theme black-on-dark fix).

Renders the corpus graph success-to-the-successful twice (dark + light)
via the CLI, loads each demo-2d.html in a headless browser, and walks every
text-bearing element (h1..h4, p, li, td, th, span, button) measuring:

  1. computed color -- dark theme must have ZERO element left on the UA
     default black (the bug this probe pins: body had no color, so the
     certificate panel / h1 / paragraphs fell back to black on deep blue);
  2. WCAG contrast of computed color vs the effective panel background
     (nearest non-transparent ancestor backgroundColor), floor 4.5:1.

Light face is frozen: UA-default black is correct there, so light only
checks the contrast floor, with DECLARED pre-existing sub-floor families
exempted (frozen tokens #6e6a5e muted/note and #dc2626 .bad, measured
below 4.5:1 on their effective backgrounds; the probe asserts nothing
below the floor falls outside that set and that the set still matches at
least once, so the exemption cannot rot into a blanket pass).

SKIP (exit 2, same caliber as probe_interactive) when playwright is
unavailable; otherwise exit 0 (pass) / 1 (fail).
Usage: python tests/probe_theme_text.py [corpus .cld path]
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

COLLECT_JS = r"""
() => {
  const out = [];
  const els = document.querySelectorAll(
    'h1,h2,h3,h4,p,li,td,th,span,button,label,b,strong');
  for (const el of els) {
    const own = Array.from(el.childNodes).some(
      n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const cs = getComputedStyle(el);
    let bg = null, node = el;
    while (node && node.nodeType === 1) {
      const c = getComputedStyle(node).backgroundColor;
      if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') { bg = c; break; }
      node = node.parentElement;
    }
    let cls = '';
    if (el.className && typeof el.className === 'string') cls = el.className;
    out.push({tag: el.tagName, cls: cls,
              inCert: !!(el.closest && el.closest('.cert')),
              text: (el.textContent || '').trim().slice(0, 40),
              color: cs.color, bg: bg});
  }
  return out;
}
"""


def _parse_rgb(s):
    m = re.findall(r"[\d.]+", s or "")
    if len(m) < 3:
        raise ValueError("unparsable color %r" % s)
    return tuple(float(x) for x in m[:3])


def _lum_rgb(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(fg, bg):
    l1, l2 = sorted((_lum_rgb(fg), _lum_rgb(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def render_fixture(theme, outdir, cld):
    r = subprocess.run(
        [sys.executable, "-m", "stdraw", "layout", cld, "--recipe", "auto",
         "--skip-3d", "--theme", theme, "--outdir", outdir, "--name", "sts"],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAIL  render %s exited %s: %s" % (theme, r.returncode, r.stderr[-400:]))
        sys.exit(1)
    demo = os.path.join(outdir, "demo-2d.html")
    if not os.path.isfile(demo):
        print("FAIL  demo-2d.html missing for %s" % theme)
        sys.exit(1)
    return demo


def measure(page, demo):
    page.goto("file:///" + demo.replace("\\", "/"))
    page.wait_for_load_state("load")
    # navigation race guard: an evaluate fired on the OLD document (being
    # torn down by the goto) returns detached-element measurements
    # (observed: cert-area collapsed 78 -> 2). Wait until the new document
    # has taken over AND its cert structure is fully present.
    expect_tail = demo.replace("\\", "/").split("/")[-2] + "/" + \
        demo.replace("\\", "/").split("/")[-1]
    page.wait_for_function(
        "() => document.readyState === 'complete' && "
        "location.href.endsWith(%r) && "
        "document.querySelectorAll('.cert').length === 2" % expect_tail)
    return page.evaluate(COLLECT_JS)


def audit(theme, rows):
    """Returns (failures, exception_rows, n).

    Light face is frozen, so its DECLARED pre-existing sub-floor families
    are exempted (measured on this fixture):
      - rgb(110, 106, 94)  #6e6a5e muted/note  (4.26:1 on the page surround,
        4.88:1 on the panel -- the footer .note sits on page_bg)
      - rgb(220, 38, 38)   #dc2626 .bad marks  (4.36:1 on the panel; present
        only when a gate fails, so the family may legitimately be empty)
    Anything below the floor OUTSIDE this set is a failure; the set must
    match at least once per run (the footer note always exists) so the
    exemption cannot silently rot into a blanket pass.
    """
    exempt_light = {"rgb(110, 106, 94)", "rgb(220, 38, 38)"}
    fails, exc = [], []
    for row in rows:
        fg = _parse_rgb(row["color"])
        if row["bg"] is None:
            fails.append("no effective background: %s %s %r"
                         % (row["tag"], row["cls"], row["text"]))
            continue
        bg = _parse_rgb(row["bg"])
        r = _ratio(fg, bg)
        if theme == "dark" and row["color"] == "rgb(0, 0, 0)":
            fails.append("UA-default black residue: %s.%s %r on %s"
                         % (row["tag"], row["cls"], row["text"], row["bg"]))
            continue
        if theme == "light" and r < 4.5 and row["color"] in exempt_light:
            exc.append(row)
            continue
        if r < 4.5:
            fails.append("contrast %.2f:1 < 4.5  %s.%s %r color=%s bg=%s"
                         % (r, row["tag"], row["cls"], row["text"],
                            row["color"], row["bg"]))
    return fails, exc, len(rows)


def main():
    cld = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "benchmarks", "corpus", "classic", "success-to-the-successful.cld")
    if not os.path.isfile(cld):
        print("FAIL  corpus fixture missing: %s" % cld)
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("SKIP  probe_theme_text: playwright unavailable (optional layer)")
        return 2

    all_ok = True
    with tempfile.TemporaryDirectory(prefix="stdraw_theme_text_") as tmp:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="msedge", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                for theme in ("dark", "light"):
                    demo = render_fixture(
                        theme, os.path.join(tmp, theme), cld)
                    rows = measure(page, demo)
                    fails, exc, n = audit(theme, rows)
                    cert_n = sum(1 for r in rows if r.get("inCert"))
                    black_n = sum(1 for r in rows if r["color"] == "rgb(0, 0, 0)")
                    print("[%s] measured=%d cert-area=%d ua-black=%d "
                          "exception-family=%d failures=%d"
                          % (theme, n, cert_n, black_n, len(exc), len(fails)))
                    # empty-set guard: an empty measurement must not be green
                    if n < 20 or cert_n < 5:
                        fails.append("fixture degenerate: measured=%d cert=%d"
                                     % (n, cert_n))
                    if theme == "light" and len(exc) == 0:
                        fails.append("light exception family empty -- the "
                                     "declared .bad exemption matched nothing")
                    for f in fails:
                        print("  FAIL  " + f)
                    all_ok = all_ok and not fails
            finally:
                browser.close()
    print("RESULT: %s" % ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
