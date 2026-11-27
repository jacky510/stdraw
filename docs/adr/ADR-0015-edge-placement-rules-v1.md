# ADR-0015: Edge placement rules v1: the pre-routing decision layer

- **Status**: Spec engineered from the owner's verbal spec, handed over 2026-11-11 (docs/edge-placement-rules-v1.md §"2026-11-11 转交本文档即视同认可建议项"); codified in code 2026-11-11

## Context

The spec document is the original; code comments carry the pointer only.

## Decision (rule in force)

For every graph edge the pre-routing decision layer fixes, per end, the
box side + the standard anchor, per the written spec
docs/edge-placement-rules-v1.md - engineered from the owner's verbal
spec.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/edgerules.py:2`

```
"""Edge placement rules v1 — the pre-routing decision layer
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0015` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
