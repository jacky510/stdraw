# -*- coding: utf-8 -*-
"""Recipe registry — the versioned interface to the engine's outward behavior.

Callers **must specify the recipe explicitly** (the stdraw CLI defaults to auto-v2):
  - ortho-v1: visibility-representation construction (planar.py, orthogonal
    vertical lines). **Behavior frozen**;
    production callers explicitly pin this recipe — stdraw CI protects it with
    byte-for-byte regression against tests/baselines/
    (any change to planar.py must pass this gate first).
    Known limitations (legacy, declared honestly): unrelated lines may pass
    through cards and occlude them; the 16px clearance gate is left for
    callers to tune via --pitch. Future quality fixes evolve only in auto-v2,
    never backported to the frozen layer.
  - auto-v2: layered + crossing count in the objective + straight/arc
    first-class routing + new hard gates
    (box press=0, edge-box clearance>=16px, anchor smoothing, simple-graph
    regularity). Default recipe.

Usage (import form):
    import stdraw
    v4 = stdraw.recipes.run("ortho-v1", graph, config)      # production behavior pin
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
    raise ValueError(f"unknown recipe {recipe!r}; available {sorted(RECIPE_VERSIONS)}")
