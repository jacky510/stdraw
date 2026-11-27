# ADR-0001: 16 standard anchors are the default endpoint attachment caliber

- **Status**: Accepted 2026-11-08 (verbal spec) / 2026-11-09 (default-caliber ruling)

## Context

The 16-point set was specified verbally (symmetric formulation) and then
extended by a follow-up ruling: the standard connection points are the
DEFAULT attachment caliber of every rendered endpoint - a rendering-pipeline
concern, not an interactive-layer nicety.

## Decision (rule in force)

Every rendered edge endpoint attaches to the 16-point standard anchor set
(4 edge midpoints + 4 corners + 2 golden-section points per edge = 16 points,
per-box), not only in the interactive layer. Assignment is gate-checked
nearest-anchor with per-(node, anchor) occupancy, fixpoint sweeps and a
yield-and-retry conflict channel; the certificate carries an
`anchors_standard` hard gate.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/routing.py:4142`

```
        jacky 2026-11-09: the 16 standard connection points (ref-scrubbed) must
        be the DEFAULT attachment caliber of every rendered edge endpoint --
        not only the interactive layer.  Algorithm path (joint selection, not
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0001` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
