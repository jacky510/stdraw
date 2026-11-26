# -*- coding: utf-8 -*-
"""Recipe registry — the versioned interface to the engine's outward behavior.

Callers **must specify the recipe explicitly** (the stdraw CLI defaults to auto-v2):
  - auto-v2: layered + crossing count in the objective + straight/arc
    first-class routing + new hard gates
    (box press=0, edge-box clearance>=16px, anchor smoothing, simple-graph
    regularity). Default recipe.
  - candidate-v1: candidate-pool pipeline (opt-in, auto-v2 untouched).

(The retired ortho-v1 recipe — vertical-orthogonal constructive layout —
had its external entry removed (owner ruling, 2026-11-24): the CLI
`--recipe ortho` option, `recipes.ortho_v1()` and the `run("ortho-v1")`
branch are gone. The underlying planar module survives as an INTERNAL
implementation detail (candidate_planar.py still calls it); it carries no
freeze or pin promise anymore.)

Usage (import form):
    import stdraw
    v4 = stdraw.recipes.run("auto-v2", graph, linestyle="arc")

Delivery contract (stdraw/delivery.py): coordinate dicts returned by
recipes carry "delivery": "coordinates-only", "interactive":
false, "engine_version" and a one-line "delivery_warning" (coordinates
are not the stdraw deliverable; the deliverable is demo-2d.html). Pass
suppress_delivery_warning=True only when you truly consume raw
coordinates. The CLI re-stamps interactive=true (no warning) when the
full deliverable was produced.
"""
from . import __version__

RECIPE_VERSIONS = {
    "auto-v2": "2 (2026-11-05: hard gates + straight/arc routing; "
               "2026-11-05 WS3: visibility-graph Dijkstra detour + arc fillet "
               "smoothing + crossing dual-caliber + R/B markers)",
    "candidate-v1": "1 (M1 candidate pool: structure analyzer + template "
                    "sources + orchestrator + three-tier selection + "
                    "routing-in-the-loop, not-worse-than-v0.8.2 guard; "
                    "opt-in, auto-v2 untouched)",
}


def auto_v2(graph, config=None, linestyle: str = "straight",
            suppress_delivery_warning: bool = False) -> dict:
    from .layout_auto import layout as _layout, AutoConfig
    cfg = config or AutoConfig()
    v4 = _layout(graph, cfg, linestyle)
    if suppress_delivery_warning:
        v4.pop("delivery_warning", None)
    return v4


def candidate_v1(graph, config=None, linestyle: str = "straight",
                 suppress_delivery_warning: bool = False) -> dict:
    """Candidate-pool pipeline (M1 minimal loop, plan section 7 M1-A/B):
    graph structure analyzer + template candidate sources + Optimization
    Orchestrator + three-tier selection + routing-in-the-loop, delivered
    through the incumbent pipeline with a not-worse-than-v0.8.2 guard.
    Opt-in recipe; the default auto-v2 path is untouched (negative
    protection)."""
    from .candidate_pipeline import layout as _candidate_layout
    from .layout_auto import AutoConfig
    cfg = config or AutoConfig()
    v4 = _candidate_layout(graph, cfg, linestyle)
    if suppress_delivery_warning:
        v4.pop("delivery_warning", None)
    return v4


def run(recipe: str, graph, config=None, linestyle: str = "straight",
        suppress_delivery_warning: bool = False) -> dict:
    if recipe == "auto-v2":
        return auto_v2(graph, config, linestyle, suppress_delivery_warning)
    if recipe == "candidate-v1":
        return candidate_v1(graph, config, linestyle, suppress_delivery_warning)
    raise ValueError(f"unknown recipe {recipe!r}; available {sorted(RECIPE_VERSIONS)}")
