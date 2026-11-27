# ADR-0005: Edge coloring: two-color polarity rework

- **Status**: Accepted 2026-11-09

## Context

A rendering-caliber ruling replacing the earlier letter-badge/dashed
encodings; CI phase H3 pins the two inks and forbids dashed / gray / badge
regressions.

## Decision (rule in force)

Lines carry exactly TWO colors keyed to each edge's own sign - '+' = amber,
'-' = sky blue - and every line is solid. The dashed=negative encoding, the
gray shared-edge color and the loop-id badges are retired; loop membership
stays in data (loop_kinds / polarity), not in line styling.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/render.py:217`

```
# Edge coloring caliber (jacky 2026-11-09 ruling, two-color polarity rework):
# lines carry exactly TWO colors keyed to each edge's own sign — '+' = amber,
# '−' = sky blue — and every line is solid. The dashed=negative encoding, the
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0005` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
