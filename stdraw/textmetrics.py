# -*- coding: utf-8 -*-
"""Bounding-box ground-truth layer (1, layout side): measure card text width with the real font; conservative padding.

Background (root cause of the v0.2 quality rework): the old text_px estimated width as character count x font size,
which inevitably deviates from actual browser rendering -- bounds measured too small -> wires hug/press the box while the certificate still passes (same-source distortion).

Principles of this layer:
    - Measuring font = rendering font (render.py font-family prefers Microsoft YaHei);
    - Worst case: titles measured at the bold upper bound; take the larger of "measured" vs "analytic";
    - Conservative padding: >= 12px on each side, plus a 6% stretch margin;
    - When PIL is unavailable, fall back to a conservative analytic formula (CJK 1.10x fs / others 0.62x fs, times a 1.08 safety factor).

The CI side (the second layer) is rendercheck.py comparing actual DOM bounds after real rendering -- both layers are indispensable.
"""
import os

# same rendering font as render.py (worst case measured with bold)
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",   # Microsoft YaHei Bold (widest)
    "C:/Windows/Fonts/msyh.ttc",     # Microsoft YaHei
    "C:/Windows/Fonts/simhei.ttf",   # SimHei fallback
]
_FALLBACK_PATHS = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Linux CI fallback
]

PAD_SIDE_MIN = 12      # minimum per-side padding px
SAFETY = 1.06          # measurement stretch safety factor

_cache = {}


def _load_font(px: int):
    """Load a font by pixel size (cached); returns None on failure."""
    key = px
    if key in _cache:
        return _cache[key]
    font = None
    try:
        from PIL import ImageFont
        for path in _FONT_CANDIDATES + _FALLBACK_PATHS:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, px)
                    break
                except Exception:
                    continue
    except Exception:
        font = None
    _cache[key] = font
    return font


def _analytic(s: str, fs: float) -> float:
    """Conservative analytic formula when no font file is available (safety factor tightened vs the old text_px)."""
    w = 0.0
    for ch in s:
        w += fs * 1.10 if ord(ch) > 0x2E7F else fs * 0.62
    return w


def text_width(s: str, fs: float, bold: bool = False) -> float:
    """Rendered width of a single line of text (px, conservative upper bound). Empty string returns 0."""
    if not s:
        return 0.0
    est = _analytic(s, fs)
    font = _load_font(max(8, int(round(fs))))
    if font is not None:
        try:
            m = font.getlength(s) * (1.06 if bold else 1.0)
            return max(m, est) * SAFETY
        except Exception:
            pass
    return est * SAFETY


def card_size(label: str, value: str, fs_title: float, fs_value: float,
              pad: float = None, min_w: int = 96, min_h: int = 44):
    """Planned card bounds: worst-case width of the two text lines + conservative padding, on a 2px grid.

    Returns (w, h). Height is generous per line count (title line + value line); a single line still keeps the visual height.
    """
    pad_side = pad if pad is not None else PAD_SIDE_MIN + 6
    w = max(text_width(label, fs_title, bold=True) + 2 * pad_side,
            text_width(value, fs_value, bold=True) + 2 * (pad_side - 4),
            min_w)
    two_line = bool(value)
    h = max(min_h, 46 if two_line else 44)
    return int((w + 1) // 2 * 2), h
