# ADR-0007: Dense-mode branch authorization (shared anchors, relaxed angle limits)

- **Status**: Accepted 2026-11-14

## Context

Owner authorization recorded on the dense card; the proposal
(stdraw-dense) was approved by default final review. G-FAN-DENSE mirrors
G-FAN with the relaxed floor.

## Decision (rule in force)

Dense graphs (hub-degree threshold exceeded) may run a dense-only branch:
"1 anchor may be shared by multiple lines; angle limits may be relaxed
appropriately." The mutual-pair separation floor relaxes 4.0 -> 3.0 in dense
slots. Every dense constant is read ONLY when the router's dense hub is
set.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/routing.py:382`

```
# Dense mode (jacky 2026-11-14 authorization: "1 anchor may be shared by
# multiple lines; angle limits may be relaxed appropriately" — dense-only
# branch, proposal stdraw-dense approved by default final review).  Every
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0007` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
