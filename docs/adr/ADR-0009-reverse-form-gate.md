# ADR-0009: Reverse-form gate: a detected-but-abandoned form degrades the certificate

- **Status**: Accepted 2026-11-15; widened 2026-11-16

## Context

The gate precedes every hygiene metric in grading; silent fallback is
not acceptable for the form families where a reverse form is visually
wrong.

## Decision (rule in force)

A structural form that was detected but abandoned (trial gate fail ->
layered fallback) disqualifies the certificate regardless of geometric
hygiene - "form misplacement is failing before any hygiene metric." The
certificate records `topology_form_fallback` with an honest grade
downgrade. Widened to spine-wing / ring-cycle once manual ground truth
landed in benchmarks/manual.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/metrics.py:1385`

```
                      "never poses as a finished product")
    # reverse-form gate (jacky ruling 2026-11-15): a structural form that
    # was detected but abandoned (trial gate fail -> layered fallback)
    # disqualifies the certificate regardless of geometric hygiene --
```

Source: `stdraw/layout_auto.py:47`

```

# Reverse-form gate scope (jacky ruling 2026-11-15; widened 2026-11-16 to
# spine-wing/ring-cycle once manual ground truth landed in
# benchmarks/manual): a structural form that was detected but abandoned
```

Source: `stdraw/layout_auto.py:3384`

```
              if _dense_hub is not None else {}),
            # reverse-form gate (jacky ruling 2026-11-15): a detected-
            # but-abandoned structural reading degrades the certificate
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0009` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
