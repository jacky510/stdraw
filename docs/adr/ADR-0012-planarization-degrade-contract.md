# ADR-0012: Planarized 2D degrade ladder: D1 budgets, L1 exact default, honest fallbacks

- **Status**: Accepted 2026-11-14 (D1-D4)

## Context

The contract document is the single authority; code comments now point
here and to the ADR instead of restating the attribution.

## Decision (rule in force)

Implementation basis (sole authority): docs/planarization-degrade-contract.md
@ 4e0cdec, D1-D4 approved. D1 locked budgets: 2000 insertion steps, 600
planarized-graph vertices. L1 planarized drawings default to --exact (the
oracle cr UB participates in the three-account check). D4 fallback: --no-exact
opts out; the certificate then stays honestly 'uncertified'
(three_account_consistent cannot pass without the oracle cr UB). Solve time
over budget is REPORTED, never silently downgraded. Planarized L1 rendering
scale: the witness-marked drawing carries a product-call canvas tier
PENDING (UIDesignerBot marker spec) - reported, not vetoed (honest N/A).

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/planarized_layout.py:81`

```
# ── D1 locked numbers (jacky 2026-11-14) ──────────────────────────────
BUDGET_INSERT_STEPS = 2000  # insertion steps (one per witness crossing)
BUDGET_H_VERTICES = 600     # planarized-graph vertex cap
```

Source: `stdraw/planarized_layout.py:500`

```
    # D4 cost call (jacky's contract clause: solve-time over budget is
    # reported, never silently downgraded) -- see the implementation
    # card's measured numbers.
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0012` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
