# -*- coding: utf-8 -*-
"""Delivery-contract metadata for stdraw coordinate outputs.

stdraw's deliverable is the interactive demo page (demo-2d.html: drag
touch-up layer + embedded quality certificate), not bare coordinates.
Every coordinate dict produced by the layout pipelines (ortho-v1 /
auto-v2) therefore carries an explicit delivery contract:

    "delivery"         "coordinates-only" | "stdraw-cli"
    "interactive"      false | true
    "engine_version"   stdraw.__version__ of the producing engine
    "delivery_warning" one-line warning (coordinates-only mode only)

The contract is additive metadata: hosts that only read known keys
(nodes/edges/viewBox/meta) keep working unchanged. Hosts that build
their own static renderer from the coordinates lose live drag
re-routing, waypoint handles, the export->recompute loop and the honest
quality certificate -- the warning says so at the point of consumption.

Layering:
  - pipeline cores (planar.PlanarLayout.run / layout_auto.layout) stamp
    coordinates-only metadata;
  - the CLI re-stamps to "stdraw-cli" / interactive=true when the full
    deliverable set (demo-2d.html + certificate.json) was produced, and
    omits the warning;
  - the ortho CLI strips the metadata before writing layout.json: the
    ortho-v1 layout.json artifact is a byte-frozen production pin
    (tests/baselines/, ci_checks gate A) and must stay byte-stable; its
    delivery contract travels on certificate.json instead (the
    "interactive" / "drag_layer" fields).

Consumers who truly need raw coordinates can silence the warning via
stdraw.recipes.run(..., suppress_delivery_warning=True) -- an explicit,
transparent opt-out.
"""
from . import __version__

DELIVERY_KEYS = ("delivery", "interactive", "engine_version",
                 "delivery_warning")

DELIVERY_WARNING = (
    "coordinates-only output: this file is layout coordinates, not the "
    "stdraw deliverable. The stdraw deliverable is demo-2d.html (drag "
    "touch-up layer + embedded quality certificate); produce it with "
    "`stdraw layout <input.cld>` and embed that page (see README, "
    "Agent Integration). Building a static renderer from these "
    "coordinates loses live drag re-routing, waypoint handles, the "
    "export->recompute loop and the quality certificate.")


def stamp_coordinates_only(v4: dict, warning: bool = True) -> dict:
    """Stamp the coordinates-only delivery contract onto a layout dict.

    Additive: delivery keys are appended after the existing keys; existing
    keys and their order are untouched (backward compatible, deterministic).
    """
    v4["delivery"] = "coordinates-only"
    v4["interactive"] = False
    v4["engine_version"] = __version__
    if warning:
        v4["delivery_warning"] = DELIVERY_WARNING
    else:
        v4.pop("delivery_warning", None)
    return v4


def stamp_cli_deliverable(v4: dict) -> dict:
    """Re-stamp a layout dict produced alongside the full CLI deliverable
    (demo-2d.html + certificate.json): interactive, no warning."""
    v4["delivery"] = "stdraw-cli"
    v4["interactive"] = True
    v4["engine_version"] = __version__
    v4.pop("delivery_warning", None)
    return v4


def strip_delivery_metadata(v4: dict) -> dict:
    """Remove delivery-contract keys (ortho CLI freeze-compat path)."""
    for k in DELIVERY_KEYS:
        v4.pop(k, None)
    return v4
