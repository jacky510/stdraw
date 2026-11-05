# -*- coding: utf-8 -*-
"""框界真值层（① 布局侧）：按真实字体度量卡片文字宽度，保守 padding。

背景（v0.2 质量返修根因）：旧 text_px 用字符数 × 字号估算，
与浏览器实际渲染必有偏差——框界量小 → 线贴框/压线，证书却达标（同源失真）。

本层原则：
  - 度量字体 = 渲染字体（render.py 的 font-family 首选 Microsoft YaHei）；
  - 最坏情况：标题按 bold 度量上限、取「实测与解析式」的较大者；
  - 保守 padding：左右各 ≥ 12px，外加 6% 伸缩余量；
  - PIL 不可用时退到保守解析式（CJK 1.10×fs / 其他 0.62×fs，再乘 1.08 安全系数）。

CI 侧（第二层）由 rendercheck.py 在真实渲染后量 DOM 实际框界比对——两层缺一不可。
"""
import os

# 与 render.py 渲染字体一致（最坏情况用 bold 度量）
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",   # Microsoft YaHei Bold（最宽）
    "C:/Windows/Fonts/msyh.ttc",     # Microsoft YaHei
    "C:/Windows/Fonts/simhei.ttf",   # SimHei 备选
]
_FALLBACK_PATHS = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Linux CI 兜底
]

PAD_SIDE_MIN = 12      # 单侧最小留白 px
SAFETY = 1.06          # 度量伸缩安全系数

_cache = {}


def _load_font(px: int):
    """按像素字号加载字体（带缓存）；失败返回 None。"""
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
    """无字体文件时的保守解析式（较旧 text_px 已收紧安全系数）。"""
    w = 0.0
    for ch in s:
        w += fs * 1.10 if ord(ch) > 0x2E7F else fs * 0.62
    return w


def text_width(s: str, fs: float, bold: bool = False) -> float:
    """单行文字渲染宽度（px，保守上界）。空串返回 0。"""
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
    """卡片规划框界：按两行文字最坏宽度 + 保守 padding，2px 网格。

    返回 (w, h)。高度按行数给足（标题行 + 数值行），单行也保持视觉高度。
    """
    pad_side = pad if pad is not None else PAD_SIDE_MIN + 6
    w = max(text_width(label, fs_title, bold=True) + 2 * pad_side,
            text_width(value, fs_value, bold=True) + 2 * (pad_side - 4),
            min_w)
    two_line = bool(value)
    h = max(min_h, 46 if two_line else 44)
    return int((w + 1) // 2 * 2), h
