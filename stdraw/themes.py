# -*- coding: utf-8 -*-
"""Design tokens: the single source of truth for every color in stdraw's two
themes (`light` and `dark`).

Caliber (jacky 2026-11-08 ruling, task ref-scrubbed):
  - `light` is the static-export baseline: its values are frozen literals —
    byte-identity of the default (light) static pipeline depends on them, so
    NEVER touch a light token without re-running the default-path sweep.
  - `dark` follows the interactive viewer's measured slate look (do not
    redesign the dark look; the values mirror viewer/index.html as shipped).
  - R/B semantic pairs, one per theme: dark R=#fbbf24 (amber-400) /
    B=#7dd3fc (sky-400); light R=#d97706 (amber-600) / B=#0284c7 (sky-600)
    — deep shades on the white canvas for contrast.

Consumers:
  - Python static export: stdraw/render.py reads THEMES[...] via get().
  - Interactive viewer: viewer/themes.js is GENERATED from this module by
    viewer_js(); tests/test_theme_tokens.py pins the generated file byte-exact
    (drift gate: edit tokens here, regenerate, never hand-edit the .js).
"""

LIGHT = {
    # ── static export (render.py) ────────────────────────────────────────
    "page_bg": "#f8fafc",          # body background
    "canvas_bg": "#fff",           # svg canvas background
    "canvas_border": "#e2e8f0",    # svg canvas border
    "panel_bg": "#fff",            # certificate / toolbar panels
    "panel_border": "#e2e8f0",
    "leader_line": "#94a3b8",      # leader bars (ortho representation)
    "line": "#64748b",             # vertical lines + arrowheads (ortho)
    "card_fill": "#fffbeb",        # node cards
    "card_stroke": "#f59e0b",
    "card_label": "#78350f",
    "card_value": "#1f2937",
    "ok": "#16a34a",
    "bad": "#dc2626",
    "note": "#64748b",
    "grade": "#1d4ed8",
    "toolbar_bg": "#fff",
    "toolbar_border": "#e2e8f0",
    "btn_bg": "#f8fafc",
    "btn_border": "#cbd5e1",
    "btn_hover_bg": "#e2e8f0",
    "hint_text": "#64748b",
    "metrics_text": "#1f2937",
    "edge_pos": "#d97706",         # '+' amber (two-color polarity rework)
    "edge_neg": "#0284c7",         # '−' sky blue
    "neutral": "#64748b",          # defensive fallback only
    "loop_r": "#d97706",           # R semantic, light tier (deep amber)
    "loop_b": "#0284c7",           # B semantic, light tier (deep sky)
    # ── interactive viewer (viewer/index.html) ──────────────────────────
    "scene_bg": "#f8fafc",
    "bar_bg": "rgba(248,250,252,.92)",
    "bar_border": "#e2e8f0",
    "bar_text": "#1f2937",
    "seg_bg": "#fff",
    "seg_border": "#cbd5e1",
    "seg_text": "#334155",
    "seg_on_bg": "#0e7490",
    "seg_on_text": "#e0f2fe",
    "btn_text": "#334155",
    "leg_text": "#64748b",
    "hint_bg": "rgba(255,255,255,.82)",
    "loops_bg": "rgba(255,255,255,.95)",
    "panel_text": "#334155",
    "loop_hover_bg": "#f1f5f9",
    "loop_on_bg": "#e0f2fe",
    "loop_on_border": "#0e7490",
    "tag_r_bg": "#fffbeb",
    "tag_r_text": "#d97706",
    "tag_b_bg": "#e0f2fe",
    "tag_b_text": "#0369a1",
    "fallback_bg": "#f8fafc",
    "fallback_card_bg": "#fff",
    "fallback_card_border": "#e2e8f0",
    "fallback_title": "#d97706",
    "fallback_code_bg": "#f1f5f9",
    "fallback_code_text": "#0369a1",
    "label_bg": "rgba(255,255,255,.97)",   # canvas label sprites
    "label_border": "#94a3b8",
    "label_text": "#1f2937",
    "grid_major": "#cbd5e1",
    "grid_minor": "#e2e8f0",
    "faint_line": "#94a3b8",
    "edge_p": "#0891b2",           # viewer '+' (cyan-600, deep tier)
    "edge_m": "#ea580c",           # viewer '−' (orange-600, deep tier)
}

DARK = {
    # ── static export (render.py) — slate, mirrors the viewer look ──────
    "page_bg": "#0b1220",
    "canvas_bg": "#0f172a",
    "canvas_border": "#334155",
    "panel_bg": "#0f172a",
    "panel_border": "#334155",
    "leader_line": "#475569",
    "line": "#475569",
    "card_fill": "#78350f",        # dark amber card (viewer tag.R family)
    "card_stroke": "#f59e0b",
    "card_label": "#fbbf24",
    "card_value": "#f1f5f9",
    "ok": "#4ade80",
    "bad": "#f87171",
    "note": "#64748b",
    "grade": "#60a5fa",
    "toolbar_bg": "#0f172a",
    "toolbar_border": "#334155",
    "btn_bg": "#1e293b",
    "btn_border": "#334155",
    "btn_hover_bg": "#334155",
    "hint_text": "#64748b",
    "metrics_text": "#f1f5f9",
    "edge_pos": "#fbbf24",         # '+' amber-400 (dark tier)
    "edge_neg": "#7dd3fc",         # '−' sky-400 (dark tier)
    "neutral": "#475569",
    "loop_r": "#fbbf24",           # R semantic, dark tier
    "loop_b": "#7dd3fc",           # B semantic, dark tier
    # ── interactive viewer — current shipped slate look, values frozen ──
    "scene_bg": "#0b0e14",
    "bar_bg": "rgba(11,14,20,.85)",
    "bar_border": "#263041",
    "bar_text": "#e2e8f0",
    "seg_bg": "#1e293b",
    "seg_border": "#334155",
    "seg_text": "#e2e8f0",
    "seg_on_bg": "#0e7490",
    "seg_on_text": "#e0f2fe",
    "btn_text": "#e2e8f0",
    "leg_text": "#94a3b8",
    "hint_bg": "rgba(11,14,20,.7)",
    "loops_bg": "rgba(11,14,20,.92)",
    "panel_text": "#cbd5e1",
    "loop_hover_bg": "#1e293b",
    "loop_on_bg": "#0f2a33",
    "loop_on_border": "#0e7490",
    "tag_r_bg": "#78350f",
    "tag_r_text": "#fbbf24",
    "tag_b_bg": "#0c3a55",
    "tag_b_text": "#7dd3fc",
    "fallback_bg": "#0b0e14",
    "fallback_card_bg": "#111827",
    "fallback_card_border": "#334155",
    "fallback_title": "#fbbf24",
    "fallback_code_bg": "#1e293b",
    "fallback_code_text": "#7dd3fc",
    "label_bg": "rgba(17,24,39,.97)",
    "label_border": "#526175",
    "label_text": "#f1f5f9",
    "grid_major": "#24304a",
    "grid_minor": "#161d2e",
    "faint_line": "#64748b",
    "edge_p": "#22d3ee",           # viewer '+' (current shipped cyan)
    "edge_m": "#fb923c",           # viewer '−' (current shipped orange)
}

THEMES = {"light": LIGHT, "dark": DARK}
DEFAULT_STATIC_THEME = "light"    # static pipeline default (current production face)
DEFAULT_VIEWER_THEME = "dark"     # viewer default (current shipped look)


def get(name):
    """Theme accessor with a hard failure on unknown names (no silent light)."""
    try:
        return THEMES[name]
    except KeyError:
        raise ValueError("unknown theme %r; expected one of %s"
                         % (name, sorted(THEMES))) from None


def viewer_js():
    """Render viewer/themes.js content (generated artifact, byte-pinned)."""
    import json
    header = (
        "/* GENERATED by stdraw/themes.py — do not edit by hand.\n"
        " * Regenerate: python -c \"from stdraw.themes import write_viewer_js; "
        "write_viewer_js('viewer/themes.js')\"\n"
        " * Byte-pinned by tests/test_theme_tokens.py (drift gate).\n"
        " */\n")
    return header + "window.STDRAW_THEMES = " + \
        json.dumps(THEMES, ensure_ascii=False, separators=(",", ":")) + ";\n"


def write_viewer_js(path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(viewer_js())
