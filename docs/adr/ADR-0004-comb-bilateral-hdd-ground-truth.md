# ADR-0004: Comb-bilateral placement ground truth: hand-pulled HDD supply-chain layout

- **Status**: Accepted 2026-11-07

## Context

Ground truth is the owner's hand-pulled HDD supply-chain layout; the
comb mode outranks column only when the source column is longer than the
best spine.

## Decision (rule in force)

K_{m,2}-family graphs (two non-adjacent hubs, shared source set,
pendant trees) are placed as a bilateral comb: all source nodes in one
vertical column, the two hubs in symmetric left/right slots at the column
middle row, every hub edge a straight fan.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/comblayout.py:3`

```

Ground truth = jacky's hand-pulled HDD supply-chain layout (2026-11-07):
6 source nodes in one vertical column (column x spread <= 10px in the hand
```

Source: `stdraw/layout_auto.py:1660`

```
    every source connected to both, pendant trees on the source side.
    Geometric ground truth = jacky's hand-pulled HDD supply-chain layout.
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0004` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
