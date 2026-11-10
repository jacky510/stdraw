# -*- coding: utf-8 -*-
"""Theme token layer gates (ref-scrubbed).

Pins:
  1. viewer/themes.js is byte-identical to the generated artifact of
     stdraw/themes.py (drift gate: tokens have ONE definition).
  2. LIGHT tokens are pinned literals — through v0.7.x they froze the
     pre-theme production face; since the UI-A spec (docs/ui-theme-spec-a.md,
     jacky 2026-11-11 ruling) they pin the DECLARED v0.8.0 major-version
     baseline (spec section 5). Any further light change needs the same
     declared re-baselining caliber, never a silent drift.
  3. dark rendering actually consumes dark tokens (no silent light).
  4. R/B semantic pairs meet the >=3.0 WCAG non-text contrast floor against
     their own canvas background (measured here, printed for the record).
  5. viewer/index.html pre-paint CSS fallbacks equal the DARK tokens (the
     shipped look stays dark even before themes.js runs).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.themes import DARK, LIGHT, THEMES, viewer_js
from stdraw.render import render_html

V4 = {
    "viewBox": [0, 0, 400, 200],
    "meta": {"cardH": 44, "fs": [12.5, 14]},
    "nodes": {"a": {"x": 100, "y": 100, "w": 120},
              "b": {"x": 300, "y": 100, "w": 120}},
    "edges": [{"a": "a", "b": "b", "polarity": "+",
               "route": {"kind": "straight", "points": [[160, 100], [240, 100]]},
               "arrow": [240, 100]},
              {"a": "b", "b": "a", "polarity": "-",
               "route": {"kind": "straight", "points": [[240, 110], [160, 110]]},
               "arrow": [160, 110]}],
}


def _rel(path):
    return os.path.join(ROOT, path)


# ── 1. generated artifact drift gate ────────────────────────────────────────
def test_themes_js_matches_generator():
    with open(_rel("viewer/themes.js"), "rb") as f:
        on_disk = f.read()
    assert on_disk.decode("utf-8") == viewer_js()


def test_token_keysets_identical():
    assert set(LIGHT) == set(DARK), "light/dark must define the same token names"


# ── 2. light tier pinned to the UI-A declared v0.8.0 baseline ──────────────
FROZEN_LIGHT = {
    "page_bg": "#e9e4d8", "canvas_bg": "#f7f3ea", "canvas_border": "#e2e8f0",
    "panel_bg": "#f7f3ea", "panel_border": "#2a3644",
    "leader_line": "#94a3b8", "line": "#64748b",
    "card_fill": "#fffdf6", "card_stroke": "#2a3644",
    "card_label": "#22303f", "card_value": "#6e6a5e",
    "ok": "#2f7d4f", "bad": "#dc2626", "note": "#6e6a5e", "grade": "#2f7d4f",
    "toolbar_bg": "#fff", "toolbar_border": "#e2e8f0",
    "btn_bg": "#f8fafc", "btn_border": "#cbd5e1", "btn_hover_bg": "#e2e8f0",
    "hint_text": "#64748b", "metrics_text": "#1f2937",
    "edge_pos": "#c2410c", "edge_neg": "#1e6fae", "neutral": "#64748b",
    "loop_r": "#c2410c", "loop_b": "#1e6fae",
}


def test_light_tokens_frozen():
    for k, v in FROZEN_LIGHT.items():
        assert LIGHT[k] == v, "light token %s drifted from the pinned UI-A " \
            "(v0.8.0 declared baseline) value %r" % (k, v)


def test_ui_a_new_tokens():
    # UI-A new tokens (spec section 2): rounded cards + canvas grid layer.
    for theme in (LIGHT, DARK):
        assert theme["card_radius"] == 14
    assert LIGHT["canvas_grid"] == {"style": "dots", "color": "#cfc7b4",
                                    "spacing": 22, "dot_radius": 1.1}
    assert DARK["canvas_grid"] == {"style": "lines",
                                   "color": "rgba(147,167,196,.10)",
                                   "spacing": 24}


def test_3d_token_groups():
    from stdraw.themes import DARK_3D, LIGHT_3D, THEMES_3D
    assert THEMES_3D == {"light": LIGHT_3D, "dark": DARK_3D}
    # UI-A light 3D group (spec section 3.1) — token definitions only.
    assert LIGHT_3D == {
        "scene_bg": "#f0ece1", "fog_color": "#ded8c9",
        "grid_major": "#d3ccbb", "grid_minor": "#c6bfad",
        "card_fill": "#fffdf6", "card_stroke": "#2a3644",
        "card_text": "#22303f", "card_muted": "#6e6a5e",
        "tube_r": "#c2410c", "tube_b": "#1e6fae",
    }
    # DARK 3D group = frozen regression pin (spec D5 / section 3.2): mirrors
    # render3d.py's shipped constants; zero changes allowed.
    assert DARK_3D == {
        "scene_bg": "#0b1220", "fog_color": "#0b1220",
        "grid_major": "#1e293b", "grid_minor": "#16233b",
        "card_fill": "#1e293b", "card_stroke": "#334155",
        "card_text": "#f1f5f9", "node_sprite": "#f59e0b",
        "tube_r": "#fbbf24", "tube_b": "#7dd3fc",
    }


# ── 3. dark rendering consumes dark tokens ─────────────────────────────────
def test_default_is_light_and_dark_actually_dark():
    default_html = render_html(V4, "t")
    assert default_html == render_html(V4, "t", theme="light")
    dark_html = render_html(V4, "t", theme="dark")
    assert DARK["page_bg"] in dark_html
    assert DARK["canvas_bg"] in dark_html
    assert DARK["edge_pos"] in dark_html
    assert DARK["edge_neg"] in dark_html
    # negative assertions scoped to the static markup: the embedded interactive
    # drag layer legitimately keeps its own (light-tier) interaction colors
    # (handles/anchors/tips) — out of this card's scope.
    static_part = dark_html.split("<script")[0]
    assert LIGHT["page_bg"] not in static_part
    assert LIGHT["edge_pos"] not in static_part
    assert LIGHT["edge_neg"] not in static_part


# ── 4. R/B contrast (WCAG relative luminance ratio vs canvas background) ───
def _lum(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _ratio(fg, bg):
    l1, l2 = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def test_rb_contrast_pairs():
    cases = [
        ("dark", DARK["loop_r"], DARK["canvas_bg"]),
        ("dark", DARK["loop_b"], DARK["canvas_bg"]),
        ("light", LIGHT["loop_r"], LIGHT["canvas_bg"]),
        ("light", LIGHT["loop_b"], LIGHT["canvas_bg"]),
    ]
    for theme, fg, bg in cases:
        r = _ratio(fg, bg)
        print("contrast %-5s %s on %s = %.2f:1" % (theme, fg, bg, r))
        assert r >= 3.0, "%s %s on %s only %.2f:1 (< 3.0 non-text floor)" % (theme, fg, bg, r)


# ── 5. viewer pre-paint fallbacks equal the dark tokens ────────────────────
ROOT_FALLBACKS = {
    "--st-scene-bg": DARK["scene_bg"],
    "--st-bar-bg": DARK["bar_bg"],
    "--st-bar-border": DARK["bar_border"],
    "--st-bar-text": DARK["bar_text"],
    "--st-seg-bg": DARK["seg_bg"],
    "--st-seg-border": DARK["seg_border"],
    "--st-seg-text": DARK["seg_text"],
    "--st-seg-on-bg": DARK["seg_on_bg"],
    "--st-seg-on-text": DARK["seg_on_text"],
    "--st-leg-text": DARK["leg_text"],
    "--st-hint-text": DARK["hint_text"],
    "--st-hint-bg": DARK["hint_bg"],
    "--st-loops-bg": DARK["loops_bg"],
    "--st-panel-text": DARK["panel_text"],
    "--st-loop-hover-bg": DARK["loop_hover_bg"],
    "--st-loop-on-bg": DARK["loop_on_bg"],
    "--st-loop-on-border": DARK["loop_on_border"],
    "--st-tag-r-bg": DARK["tag_r_bg"],
    "--st-tag-r-text": DARK["tag_r_text"],
    "--st-tag-b-bg": DARK["tag_b_bg"],
    "--st-tag-b-text": DARK["tag_b_text"],
    "--st-fallback-card-bg": DARK["fallback_card_bg"],
    "--st-fallback-card-border": DARK["fallback_card_border"],
    "--st-fallback-title": DARK["fallback_title"],
    "--st-fallback-code-bg": DARK["fallback_code_bg"],
    "--st-fallback-code-text": DARK["fallback_code_text"],
    "--st-edge-p": DARK["edge_p"],
    "--st-edge-m": DARK["edge_m"],
}


def test_viewer_css_fallbacks_are_dark_tokens():
    with open(_rel("viewer/index.html"), "r", encoding="utf-8") as f:
        html = f.read()
    block = re.search(r":root\{(.*?)\}", html, re.S).group(1)
    declared = dict(re.findall(r"(--st-[a-z-]+):([^;]+)", block))
    for var, expect in ROOT_FALLBACKS.items():
        got = declared.get(var)
        assert got is not None, "viewer :root lost %s" % var
        assert got == expect, "viewer fallback %s=%r != dark token %r" % (var, got, expect)
    # every CSS var consumed by the stylesheet must be declared as a fallback
    consumed = set(re.findall(r"var\((--st-[a-z-]+)", html))
    missing = consumed - set(declared)
    assert not missing, "vars consumed without a :root fallback: %s" % sorted(missing)
