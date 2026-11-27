# ADR-0017: UI-A theme baseline: design tokens single source

- **Status**: Accepted 2026-11-11

## Context

The spec document is frozen as the v0.8.0 snapshot; its 3D token
sections are historical since the 3D layer removal (v0.9.0) and are NOT
re-edited by this migration.

## Decision (rule in force)

The UI-A "drafting room" spec is the declared major-version visual
baseline; design tokens live in stdraw/themes.py as the single source
(light "tracing paper" + dark "midnight ink" tiers). Spec original
preserved in-repo at docs/ui-theme-spec-a.md.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/themes.py:5`

```
Caliber (UI-A "drafting room" spec, jacky 2026-11-11 ruling; spec original
preserved in-repo at docs/ui-theme-spec-a.md):
  - `light` was a frozen-literal static-export baseline through v0.7.x. The
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0017` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
