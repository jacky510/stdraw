# ADR-0002: Layout aesthetics directive v2: explicit symmetry, patterned placement, spine-wing, whole-graph mode chain

- **Status**: Accepted 2026-11-05 / 2026-11-06

## Context

One aesthetics session produced several mode directives plus the
whole-graph direction; the engine implements each as a placement mode with
mirror/axis regularity gates, benchmarked against the hand-laid samples.

## Decision (rule in force)

Symmetric structures must be explicitly symmetric (learning-flywheel
"could be symmetric yet leans left"). Long-chain / few-ring graphs follow a
column pattern. The classic-cld-growth-and-burden family follows the
hand-laid spine-wing template (owner final call, B-limited edition): central
spine strictly vertical on the canvas centerline, wings and clusters on the
same horizontal midline. The whole-graph placement engine consumes a mode
priority chain built on these directives.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/spinewinglayout.py:2`

```
"""Spine-wing (central spine + midline wings) placement (2026-11-06 jacky's
final call, B-limited edition, ref-scrubbed).
```

Source: `stdraw/spinewinglayout.py:5`

```
> jacky hand-laid the classic-cld-growth-and-burden diagram: the central
> spine adopters (top) / rate (bottom) sits strictly vertical on the canvas
> centerline; left wings word/potential and the right cluster crowding sit
```

Source: `stdraw/spinewinglayout.py:250`

```
    Constructed constraints (relative geometry cross-checked against jacky's
    hand-laid classic-cld sample; see the module docstring).
    """
```

Source: `stdraw/symlayout.py:3`

```
(2026-11-06 jacky layout aesthetics v2, ref-scrubbed).

> #11 learning-flywheel "could be symmetric yet leans left" — symmetric
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0002` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
