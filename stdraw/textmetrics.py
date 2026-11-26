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


def analytic_width(s: str, fs: float) -> float:
    """Font-independent width bound: the analytic estimate (CJK 1.10x fs / others 0.62x fs)
    times the safety factor. Use it for drawn containers whose bytes must not depend on the
    measuring font: with a font file the measurement can exceed the analytic estimate for
    Latin text, which makes the output differ between a machine that has the font and a
    fontless checkout."""
    return _analytic(s, fs) * SAFETY


# -- calibrated advances of the rendering font (a frozen table, never a live font read) --
# The loop-label pill (annotations.label_svg) centres its content on the width the
# text will really occupy, so it needs the rendered width -- but reading a font file
# at generation time makes the delivered bytes depend on which fonts the generating
# machine has (the platform-dependence analytic_width exists to avoid).  So the width
# comes from this table: Microsoft YaHei regular and bold, the font render.py draws
# with, measured once with canvas measureText in Edge headless (device scale 2).
# One 7-digit field per ASCII character 32..126: advance in 1/1000 em (4 digits) +
# ink right edge of the single glyph in whole pixels at 11 px (2 digits) + ink left
# code (1 digit = actualBoundingBoxLeft + 1).  Advances are linear in the font size
# (22 px / 11 px = 2.0000 on every glyph); CJK ideographs (U+2E80 and up) all advance
# exactly 1 em in this font.
_CAL_REGULAR = (
    "029600103120310436041063808205860710890101087010102560310334041033404204"
    "550510742080024103204330510241031042706205860710586051058607105860610586"
    "072058606105860710586071058607105860710241031024103207420700742080074207"
    "004830611031111070408206270710669081076209105500610531061074408107730810"
    "294031039604206350810513061097710108130910815091061207108151010653081057"
    "707105730720747081067608210181220645082060407206200720334041041606203340"
    "310742080044806202950410553061063907105010610640071056707103470510640071"
    "061607102660310267033054407102660310937101061607106360710639071064007103"
    "820510463051037305206160710525072079009205070620529072049206203340410269"
    "03103340410742081"
)
_CAL_BOLD = (
    "029800103490410521051064008206170710931111091110103080310390061039004204"
    "870620761080028603204370510286031047306206170710617051061707106170710617"
    "082061707106170710617071061707106170710286031028603207610800761080076108"
    "004740611030111075209206840810673081079209105720710558061076509108210910"
    "335031047005206930910547071102811108480910818091065708108181010698091060"
    "207106250720776081071509210761320700082064808206500820390051046407203900"
    "410761081044806203330410578061066608105170610665071058207104050520665071"
    "064607102960310302033059607102960310982111064807106570810666081066507104"
    "240510494061041405206480710577072085210205850720574072051406203900510341"
    "03103900510761081"
)
_CAL_CJK_FIRST = 0x2E80
_CAL_CJK_INK_MID = 0.5    # px at 11 px: midpoint of the two central whole-pixel ink edges
_CAL_LATIN_FALLBACK_EM = 0.62


def _cal_table(s):
    return {chr(32 + i): (int(s[7 * i:7 * i + 4]) / 1000.0, int(s[7 * i + 4:7 * i + 6]),
                          int(s[7 * i + 6]) - 1)
            for i in range(len(s) // 7)}


_CAL = {"regular": _cal_table(_CAL_REGULAR), "bold": _cal_table(_CAL_BOLD)}


def rendered_ink_extent(runs, fs):
    """Calibrated ink extent of consecutive text runs sharing a start anchor.

    runs = [(text, bold), ...]: what one <text text-anchor="start"> renders.
    Returns (left, right) of the ink in px at font size fs, relative to the run
    origin: left <= 0 (the ink starts at or left of the origin), right = the
    ink's right edge.  Static table look-up only, so the result is the same on
    every machine.  A character outside the table takes the analytic advance
    (CJK 1 em, others 0.62 em); a CJK glyph's ink edge is then the midpoint of
    its two central whole-pixel edges (accurate to half a pixel), any other
    unknown glyph is assumed to end its ink at the advance.
    """
    n = len(runs)
    adv = []
    for i, (text, bold) in enumerate(runs):
        if i == 0:
            text = text.lstrip()        # SVG collapses leading whitespace
        if i == n - 1:
            text = text.rstrip()        # ... and trailing whitespace
        tab = _CAL["bold" if bold else "regular"]
        for ch in text:
            if ch in tab:
                adv.append(tab[ch][0] * fs)
            else:
                adv.append(fs if ord(ch) >= _CAL_CJK_FIRST else _CAL_LATIN_FALLBACK_EM * fs)
    if not adv:
        return 0.0, 0.0
    k = fs / 11.0
    first = runs[0][0].lstrip()[0]
    first_bold = runs[0][1]
    tab_first = _CAL["bold" if first_bold else "regular"]
    left = -tab_first[first][2] * k if first in tab_first else (
        -_CAL_CJK_INK_MID * k if ord(first) >= _CAL_CJK_FIRST else 0.0)
    last = runs[-1][0].rstrip()[-1]
    tab_last = _CAL["bold" if runs[-1][1] else "regular"]
    right = sum(adv[:-1])
    if last in tab_last:
        right += tab_last[last][1] * k
    else:
        # a CJK ideograph's outline bounds round to whole pixels around its em
        # box (measured 10/11/12 px for an 11 px em, 141 of 194 at 12): the
        # midpoint of the two central values is accurate to half a pixel
        right += adv[-1] + (_CAL_CJK_INK_MID * k if ord(last) >= _CAL_CJK_FIRST else 0.0)
    return left, right


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
              pad: float = None, min_w: int = 96, min_h: int = 44,
              value_pad: float = None):
    """Planned card bounds: worst-case width of the two text lines + conservative padding, on a 2px grid.

    Returns (w, h). Height is generous per line count (title line + value line); a single line still keeps the visual height.

    value_pad: extra per-side padding px reserved for the second (value) text
    line, on top of the historical pad-4 baseline. Default None keeps the
    historical behavior byte-for-byte (zero drift); callers that render long
    ticker/price strings (e.g. "7741.T 22,395.00 JPY" measured ~120px vs a
    108px card) opt in via AutoConfig.value_pad_extra / CLI --value-pad.
    """
    pad_side = pad if pad is not None else PAD_SIDE_MIN + 6
    value_pad_side = (pad_side - 4) if value_pad is None else value_pad
    w = max(text_width(label, fs_title, bold=True) + 2 * pad_side,
            text_width(value, fs_value, bold=True) + 2 * value_pad_side,
            min_w)
    two_line = bool(value)
    h = max(min_h, 46 if two_line else 44)
    return int((w + 1) // 2 * 2), h
