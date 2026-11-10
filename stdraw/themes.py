# -*- coding: utf-8 -*-
"""Design tokens: the single source of truth for every color in stdraw's two
themes (`light` and `dark`), plus the per-theme 3D parameter groups.

Caliber (UI-A "drafting room" spec, jacky 2026-11-11 ruling; spec original
preserved in-repo at docs/ui-theme-spec-a.md):
  - `light` was a frozen-literal static-export baseline through v0.7.x. The
    UI-A spec replaces it as a DECLARED major-version baseline update (the
    v0.8.0 face, spec section 5): landing it requires the default-path full
    sweep and a version-closure card before any release claims it. It is a
    declared re-baselining channel, not a silent-drift channel — the pins in
    tests/test_theme_tokens.py and tests/test_render_bugs.py track the new
    baseline.
  - `dark` 2D (static export) follows the UI-A dark tier ("micro-blue ink"):
    darker blue-leaning ground, NEUTRAL steel-gray container stroke and grid
    (no more cyan collusion with the B ink), amber/sky kept as the only two
    polar colors on the canvas.
  - The interactive-viewer token block and the 3D DARK group are the shipped
    look, FROZEN REGRESSION PINS (spec D5 / section 3.2: zero changes;
    render3d.py's dark constants mirror DARK_3D verbatim).
  - R/B semantic pairs, one per theme (UI-A): light R=#c2410c (vermilion) /
    B=#1e6fae (drafting blue); dark R=#ffb454 / B=#6ec6ff. The polar inks are
    the ONLY two colors in a delivered figure; everything else stays
    neutral/ink. No token may introduce a third chromatic hue.

Consumers:
  - Python static export: stdraw/render.py reads THEMES[...] via get().
  - Interactive viewer: viewer/themes.js is GENERATED from this module by
    viewer_js(); tests/test_theme_tokens.py pins the generated file byte-exact
    (drift gate: edit tokens here, regenerate, never hand-edit the .js).
  - 3D layer: LIGHT_3D / DARK_3D are token definitions only in this landing
    step; render3d.py consumption (light stage / dark freeze wiring) is a
    follow-up card.
"""

LIGHT = {
    # ── static export (render.py) — UI-A light tier ("tracing paper") ────
    "page_bg": "#e9e4d8",          # page background (paper surround)
    "canvas_bg": "#f7f3ea",        # svg canvas background (tracing paper)
    "canvas_border": "#e2e8f0",    # unspecified by the UI-A table; kept
    "panel_bg": "#f7f3ea",         # certificate panel (ink-sign base)
    "panel_border": "#2a3644",     # certificate panel border (ink line)
    "leader_line": "#94a3b8",      # leader bars (ortho representation)
    "line": "#64748b",             # vertical lines + arrowheads (ortho)
    "card_fill": "#fffdf6",        # node cards (paper white)
    "card_stroke": "#2a3644",      # ink-line stroke (1.3px at render)
    "card_label": "#22303f",       # label ink
    "card_value": "#6e6a5e",       # muted secondary text (mono)
    "ok": "#2f7d4f",               # pass / ink-seal green
    "bad": "#dc2626",              # unspecified by the UI-A table; kept
    "note": "#6e6a5e",             # muted notes
    "grade": "#2f7d4f",            # grade seal (stamp color per spec)
    "toolbar_bg": "#fff",          # unspecified by the UI-A table; kept
    "toolbar_border": "#e2e8f0",
    "btn_bg": "#f8fafc",
    "btn_border": "#cbd5e1",
    "btn_hover_bg": "#e2e8f0",
    "hint_text": "#64748b",
    "metrics_text": "#1f2937",
    "edge_pos": "#c2410c",         # '+' vermilion (UI-A light polar ink)
    "edge_neg": "#1e6fae",         # '−' drafting blue (UI-A light polar ink)
    "neutral": "#64748b",          # defensive fallback only
    "loop_r": "#c2410c",           # R semantic, light tier
    "loop_b": "#1e6fae",           # B semantic, light tier
    # UI-A new tokens ─────────────────────────────────────────────────────
    "card_radius": 14,             # rounded card corners (three-tier large)
    "canvas_grid": {               # canvas grid layer (new render feature)
        "style": "dots",           # tracing-paper dot grid
        "color": "#cfc7b4",
        "spacing": 22,             # px between dots
        "dot_radius": 1.1,
    },
    # ── interactive viewer (viewer/index.html) — unspecified by the UI-A ──
    #    2D table; values kept from the shipped look.
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
    # ── static export (render.py) — UI-A dark tier ("micro-blue ink") ────
    "page_bg": "#090d14",          # page background
    "canvas_bg": "#0d131e",        # canvas (micro-blue ink, pressed deep)
    "canvas_border": "#334155",    # unspecified by the UI-A table; kept
    "panel_bg": "#0d131e",         # certificate panel base
    "panel_border": "rgba(147,167,196,.45)",   # certificate border (steel)
    "leader_line": "#475569",
    "line": "#475569",
    "card_fill": "rgba(16,22,34,.92)",
    "card_stroke": "#93a7c4",      # NEUTRAL steel gray (UI-A key fix: the
                                   # old cyan stroke collided with the B ink)
    "card_label": "#dfe7f2",       # ink
    "card_value": "#8b98ab",       # muted
    "ok": "#4ade80",
    "bad": "#f87171",              # unspecified by the UI-A table; kept
    "note": "#8b98ab",
    "grade": "#4ade80",            # grade seal (stamp color per spec)
    "toolbar_bg": "#0f172a",       # unspecified by the UI-A table; kept
    "toolbar_border": "#334155",
    "btn_bg": "#1e293b",
    "btn_border": "#334155",
    "btn_hover_bg": "#334155",
    "hint_text": "#64748b",
    "metrics_text": "#f1f5f9",
    "edge_pos": "#ffb454",         # '+' amber (UI-A dark polar ink)
    "edge_neg": "#6ec6ff",         # '−' sky (UI-A dark polar ink)
    "neutral": "#475569",
    "loop_r": "#ffb454",           # R semantic, dark tier
    "loop_b": "#6ec6ff",           # B semantic, dark tier
    # UI-A new tokens (mirror the light-tier keyset) ──────────────────────
    "card_radius": 14,
    "canvas_grid": {
        "style": "lines",          # neutral steel line grid (no more cyan)
        "color": "rgba(147,167,196,.10)",
        "spacing": 24,             # px between lines
    },
    # ── interactive viewer — shipped slate look, FROZEN regression pins ──
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
DEFAULT_STATIC_THEME = "light"    # static pipeline default (production face)
DEFAULT_VIEWER_THEME = "dark"     # viewer default (shipped look, frozen)

# ── 3D parameter groups (token definitions only in this landing step; the
#    render3d.py consumption is a follow-up card) ───────────────────────────
# LIGHT (UI-A spec section 3.1; structure unchanged, parameters only).
LIGHT_3D = {
    "scene_bg": "#f0ece1",         # stage / scene.background
    "fog_color": "#ded8c9",        # fog target
    "grid_major": "#d3ccbb",       # GridHelper major line
    "grid_minor": "#c6bfad",       # GridHelper minor line
    "card_fill": "#fffdf6",        # card texture fill
    "card_stroke": "#2a3644",      # card texture stroke
    "card_text": "#22303f",        # card label ink
    "card_muted": "#6e6a5e",       # card secondary text
    "tube_r": "#c2410c",           # '+' polarity tube/cone material
    "tube_b": "#1e6fae",           # '−' polarity tube/cone material
}

# DARK — FROZEN REGRESSION PIN (UI-A spec D5 / section 3.2: zero changes).
# Values mirror render3d.py's shipped constants verbatim (full mirror,
# including tokens the spec table does not restate). Any byte change in the
# dark 3D output is a pin break, not a restyle.
DARK_3D = {
    "scene_bg": "#0b1220",         # scene.background AND fog color (0x0b1220)
    "fog_color": "#0b1220",
    "grid_major": "#1e293b",       # GridHelper(1600, 32, 0x1e293b, ...)
    "grid_minor": "#16233b",
    "card_fill": "#1e293b",        # card family fill (0x1e293b)
    "card_stroke": "#334155",      # card border line (0x334155)
    "card_text": "#f1f5f9",        # label sprite text
    "node_sprite": "#f59e0b",      # node sphere sprite (0xf59e0b)
    "tube_r": "#fbbf24",           # '+' amber-400
    "tube_b": "#7dd3fc",           # '−' sky-400
}

THEMES_3D = {"light": LIGHT_3D, "dark": DARK_3D}


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
