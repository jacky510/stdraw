# -*- coding: utf-8 -*-
"""Theme token layer gates.

Pins:
  1. LIGHT tokens are pinned literals through v0.7.x they froze the
     pre-theme production face; since the UI-A spec (docs/ui-theme-spec-a.md,
     jacky 2026-11-11 ruling) they pin the DECLARED v0.8.0 major-version
     baseline (spec section 5). Any further light change needs the same
     declared re-baselining caliber, never a silent drift.
  2. dark rendering actually consumes dark tokens (no silent light).
  3. R/B semantic pairs meet the >=3.0 WCAG non-text contrast floor against
     their own canvas background (measured here, printed for the record).
  4. body/panel text inks clear 4.5:1 on every surface (dark-theme text fix).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stdraw.themes import DARK, LIGHT
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


# ── 5. body/panel text ink contrast (dark-theme text fix regression) 
# The dark face must emit a body foreground that clears 4.5:1 on every
# surface text can sit on (page, certificate panel, toolbar); the light
# face stays frozen (no body color emitted, UA default black clears the
# floor too). Guards future panel additions against silent black-on-dark.
def test_body_text_contrast():
    assert DARK["body_text"] == "#e2e8f0"
    assert LIGHT["body_text"] is None
    for bg in (DARK["page_bg"], DARK["panel_bg"], DARK["toolbar_bg"]):
        r = _ratio(DARK["body_text"], bg)
        print("contrast dark body_text %s on %s = %.2f:1"
              % (DARK["body_text"], bg, r))
        assert r >= 4.5, "dark body_text on %s only %.2f:1" % (bg, r)
    _hex7 = lambda h: h if len(h) == 7 else "#" + "".join(c * 2 for c in h[1:])
    for bg in (LIGHT["page_bg"], LIGHT["panel_bg"], LIGHT["toolbar_bg"]):
        r = _ratio("#000000", _hex7(bg))
        print("contrast light UA-default black on %s = %.2f:1" % (bg, r))
        assert r >= 4.5, "light UA-default black on %s only %.2f:1" % (bg, r)
    # emission caliber: light byte-identical (no color), dark emits once
    light_html = render_html(V4, "t")
    assert "body{margin:16px;background:" in light_html
    dark_html = render_html(V4, "t", theme="dark")
    assert dark_html.count("body{margin:16px;color:#e2e8f0;background:") >= 1
    assert "color:#e2e8f0" not in render_html(V4, "t")
