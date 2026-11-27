# ADR-0003: Layout aesthetics v3: bowtie-vertex symmetric placement (wage-price-spiral)

- **Status**: Accepted 2026-11-06

## Context

Hand-laid ground truth: the owner drew the wage-price-spiral diagram by
hand and the engine's bowtie-vertex mode cross-checks its relative geometry
against that sample.

## Decision (rule in force)

For two simple loops sharing exactly one node (the wage-price-spiral
family), the shared node sits at the exact center of the figure, the
remaining nodes of the two rings occupy four symmetric positions, and the
whole figure is axis-symmetric up/down and left/right - "topology should
decide the layout".

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/bowtielayout.py:2`

```
"""Bowtie-vertex (two rings sharing a single node) symmetric placement
(2026-11-06 jacky aesthetics v3, ref-scrubbed).

> jacky hand-laid the wage-price-spiral diagram: the shared node sits at the
> exact center of the figure, the remaining nodes of the two rings occupy
```

Source: `stdraw/bowtielayout.py:23`

```
Placement (place_bowtie_vertex, cross-checked against the relative geometry
of jacky's hand-laid sample):
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0003` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
