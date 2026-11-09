# -*- coding: utf-8 -*-
"""Viewer theme-switch probe (ref-scrubbed acceptance #2).

Real-browser (playwright chromium, file:// open of viewer/index.html):
  A. default theme is dark (no stored preference) — shipped look unchanged;
  B. clicking the topbar "Theme" button switches instantly: html dataset,
     computed body background, and the topbar button label all flip;
  C. the preference persists across reload (localStorage stdraw-theme);
  D. switching back to dark restores the dark look;
  E. zero uncaught page errors across the whole run.
Screenshots for both themes are written next to this probe
(docs/gallery/theme-viewer-<name>.png) when OUT_DIR is provided as argv[1].

Run: python tests/probe_viewer_theme.py [out_dir]   (exit 0 = all gates green)
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(ROOT, "viewer", "index.html")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else None


def main():
    if sync_playwright is None:
        print("SKIP playwright unavailable (honest skip, not a pass)")
        return 3
    url = "file:///" + VIEWER.replace("\\", "/")
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(url)
        page.wait_for_function("window.__ready === true", timeout=30000)

        def ds():
            return page.evaluate("document.documentElement.dataset.theme")

        def body_bg():
            return page.evaluate("getComputedStyle(document.body).backgroundColor")

        def btn():
            return page.text_content("#btnTheme").strip()

        # A. default dark
        assert ds() == "dark", "default theme should be dark, got %r" % ds()
        assert btn() == "Theme: Dark", "default button label wrong: %r" % btn()
        dark_bg = body_bg()
        assert dark_bg == "rgb(11, 14, 20)", "dark body bg wrong: %r" % dark_bg
        print("OK  A default=dark  body_bg=%s" % dark_bg)

        if OUT_DIR:
            os.makedirs(OUT_DIR, exist_ok=True)
            page.screenshot(path=os.path.join(OUT_DIR, "theme-viewer-dark.png"))

        # B. instant switch to light
        page.click("#btnTheme")
        assert ds() == "light", "dataset did not flip to light: %r" % ds()
        light_bg = body_bg()
        assert light_bg == "rgb(248, 250, 252)", "light body bg wrong: %r" % light_bg
        assert btn() == "Theme: Light", "button label after switch: %r" % btn()
        stored = page.evaluate("localStorage.getItem('stdraw-theme')")
        assert stored == "light", "localStorage not persisted: %r" % stored
        print("OK  B switch->light  body_bg=%s stored=%s" % (light_bg, stored))

        if OUT_DIR:
            page.screenshot(path=os.path.join(OUT_DIR, "theme-viewer-light.png"))

        # C. persistence across reload
        page.reload()
        page.wait_for_function("window.__ready === true", timeout=30000)
        assert ds() == "light", "preference lost on reload: %r" % ds()
        assert body_bg() == light_bg, "light bg lost on reload: %r" % body_bg()
        print("OK  C reload keeps light")

        # D. switch back to dark
        page.click("#btnTheme")
        assert ds() == "dark" and body_bg() == dark_bg and btn() == "Theme: Dark"
        print("OK  D switch back->dark")

        # E. zero uncaught errors
        errs = page.evaluate("window.__errors")
        assert not errs, "uncaught page errors: %r" % errs
        print("OK  E zero page errors")
        browser.close()
    print("ALL VIEWER THEME GATES GREEN" if ok else "FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
