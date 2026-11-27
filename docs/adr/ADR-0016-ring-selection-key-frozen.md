# ADR-0016: Ring main-selection key frozen; reordering pending (S2-3)

- **Status**: Frozen since the WorkBuddy observability task 2026-11-11 (S2-1); S2-3 PENDING owner ruling

## Context

Status: PENDING (not yet decided). The code annotation and the emitted
certificate note both mark the freeze as awaiting the owner decision; this
ADR is the traceable anchor for that pending state.

## Decision (rule in force)

The ring main-selection key `(-k, chord_crossings, ring order)` is
FROZEN. The certificate's observability probe records EVERY candidate main
ring with the exact selection-key inputs plus which ring the alternative
key (chord crossings first) would pick - recording only. Whether to adjust
the ordering (S2-3) is PENDING the owner's D3 ruling; evidence table:
benchmarks/ring-candidate-sweep.md.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/metrics.py:1528`

```
    (chord crossings first) would pick. Recording only: the selection key
    itself is frozen (S2-3 pending jacky's D3 ruling)."""
```

Source: `stdraw/metrics.py:1548`

```
                 "the selection-key inputs; the selection key is frozen "
                 "(D3 pending jacky's ruling)"),
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0016` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
