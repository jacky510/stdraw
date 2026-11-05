# -*- coding: utf-8 -*-
"""配方（recipe）注册表 —— 引擎对外行为的版本化接口。

调用方**必须显式指定配方**（stdraw CLI 默认 auto-v2）：
  - ortho-v1：可见性表示构造法（planar.py，正交竖线）。**行为冻结**，
    生产调用方显式 pin 此配方——stdraw CI 以 tests/baselines/ 逐字节回归
    保护（改 planar.py 必先过这条门）。
    已知边界（legacy，如实声明）：允许无关线遮挡式穿卡；净距门禁 16px 靠调用方
    --pitch 调参。后续质量修复只在 auto-v2 演进，不回写冻结层。
  - auto-v2：分层 + 交叉数进目标 + 直线/弧线一等布线 + 新硬门
    （框压线=0、边-框净距≥16px、锚点平滑、简单图规律性）。默认配方。

用法（import 形态）：
    import stdraw
    v4 = stdraw.recipes.run("ortho-v1", graph, config)      # 生产行为 pin
    v4 = stdraw.recipes.run("auto-v2", graph, linestyle="arc")
"""
from . import __version__

RECIPE_VERSIONS = {
    "ortho-v1": "1 (frozen 2026-11-05, byte-stable, pin-safe)",
    "auto-v2": "2 (2026-11-05: hard gates + straight/arc routing; "
               "2026-11-05 WS3: visibility-graph Dijkstra detour + arc fillet "
               "smoothing + crossing dual-caliber + R/B markers)",
}


def ortho_v1(graph, config=None) -> dict:
    from .planar import PlanarLayout
    return PlanarLayout(graph, config).run()


def auto_v2(graph, config=None, linestyle: str = "straight") -> dict:
    from .layout_auto import layout as _layout, AutoConfig
    cfg = config or AutoConfig()
    return _layout(graph, cfg, linestyle)


def run(recipe: str, graph, config=None, linestyle: str = "straight") -> dict:
    if recipe == "ortho-v1":
        return ortho_v1(graph, config)
    if recipe == "auto-v2":
        return auto_v2(graph, config, linestyle)
    raise ValueError(f"未知配方 {recipe!r}；可选 {sorted(RECIPE_VERSIONS)}")
