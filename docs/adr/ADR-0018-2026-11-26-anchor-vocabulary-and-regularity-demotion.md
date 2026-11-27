# ADR-0018: 2026-11-26 batch — multi-slot anchor vocabulary, on-border+angle anchors_standard, fan slot swap, and the n>10 regularity demotion

- **Status**: Accepted 2026-11-26 (two rulings: the multi-slot anchor vocabulary card, and the n>10 regularity demotion)

## Context

Two owner rulings landed on 2026-11-26, after the first code-hygiene pass had
already migrated the earlier annotations. Both were grounded in the same
evidence base: the `stdraw20` manual-calibration lessons (the hand-drawn
figures and their exported layouts).

1. **Multi-slot anchor vocabulary.** The hand-drawn vocabulary is
   multi-slot (`s-g1 / s-g2 / ...`); one side may carry many lines, so the
   fixed 16-point set cannot express it. The `anchors_standard` hard gate
   therefore changed criterion: the legacy 16-set membership test is retired
   (it blocked ~80% of manually calibrated figures) and replaced by
   "endpoint ON its box border + departure/arrival angle >= floor". Fan
   slot competition is settled by SWAP keyed on the departure azimuth phi,
   not on the far-end coordinate.
2. **n>10 regularity demotion.** The mechanical-grid regularity gates
   (`cv_le_035` / `pitch_uniform` family / `column_snap24_ge_060`) reward
   mechanical grids and penalize human arrangements. On the automatic
   pipeline they gate only n <= 10 figures; for n > 10 they demote to
   certificate report items. The manual (`--from-layout`) caliber is NOT
   touched.

## Decision (rule in force)

- **Anchor vocabulary (ADR-0018-a)**: each box side carries a numbered slot
  ladder `g1..g7` at fixed, context-free fractions measured clockwise from
  the side's first endpoint (`g1 = 0.382`, `g2 = 0.618` = the legacy golden
  pair, byte-stable with the 16-point set; `g3 = 0.500`; `g4 = 0.250`,
  `g5 = 0.750`; `g6 = 0.125`, `g7 = 0.875`). The `anchors_standard` gate
  reads "endpoint ON the box border (<= 0.75px) AND departure/arrival angle
  >= the anchor-angle floor" — it is not a membership table against the
  legacy 16-set.
- **Fan slot swap (ADR-0018-b)**: competing fan endpoints exchange slots by
  the departure-azimuth phi key; a far-end-monotone slot order still
  crosses when the routes approach the shared node from opposite sides
  (detour vs direct). The swap is the last endpoint-moving repair, so the
  dual crossing accounting below it includes its effect; groups without
  near-segment crossings are skipped byte-for-byte.
- **n>10 regularity demotion (ADR-0018-c)**: the three mechanical-grid
  regularity gates are hard gates only for n <= 10 on the automatic
  pipeline. For n > 10 their measured boolean travels in the certificate
  `reports` block (same key names) plus a `regularity_demoted_note`; they
  are excluded from `gates_passed` / `blocking_gates` and never press the
  grade. All other gates and the grade semantics are unchanged.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/anchors.py:147`

```
# ── Multi-slot side vocabulary (jacky 2026-11-26 approval; grounded in the
#    stdraw20 manual-calibration lessons §4: the manual vocabulary is
#    multi-slot -- s-g1 / s-g2 / ... -- and a single side may carry many
```

Source: `stdraw/cert_gates.py:123`

```
    """anchors_standard criterion (jacky 2026-11-26, multi-slot vocabulary
    card): every delivered endpoint sits ON its box border and meets the
    anchor-angle floor -- the legacy 16-set membership requirement is
```

Source: `stdraw/cert_gates.py:561`

```
    # ``when`` policy (jacky ruling 2026-11-26, stdraw20 manual-calibration
    # lessons doc section 5.1): the mechanical-grid regularity gates
    # (``cv_le_035`` / ``pitch_uniform`` family / ``column_snap24_ge_060``)
```

Source: `stdraw/layout_auto.py:2975`

```
    # fan slot competition by SWAP (departure-azimuth φ key; jacky 2026-11-26
    # approval, stdraw20 lesson §4): last endpoint-moving repair, so the
    # dual crossing accounting below includes its effect.  Groups without
```

Source: `stdraw/metrics.py:568`

```
        # anchors_standard criterion (jacky 2026-11-26 approval, grounded in
        # the stdraw20 manual-calibration lessons §4 / W9 evaluation: the
        # legacy 16-set membership blocked ~80% of manually calibrated
```

Source: `stdraw/metrics.py:1160`

```
        # anchors_standard criterion (jacky 2026-11-26): endpoint ON the box
        # border + departure/arrival angle >= floor -- the vocabulary is the
        # multi-slot anchors.py set, not a membership table
```

Source: `stdraw/metrics.py:1233`

```
        # n>10 regularity demotion transport (jacky ruling 2026-11-26,
        # stdraw20 manual calibration): the demoted mechanical-grid gates
        # report their measured boolean here instead of gating; metrics
```

Source: `stdraw/metrics.py:1239`

```
        reports["regularity_demoted_note"] = (
            "report items (n>10, jacky 2026-11-26 ruling): the "
            "mechanical-grid regularity gates cv_le_035 / pitch_uniform / "
            "column_snap24_ge_060 are demoted from hard gates per the "
            "stdraw20 manual-calibration evidence (they reward mechanical "
            "grids and penalize human arrangements); measured values above, "
            "all other gates and grade semantics unchanged")
```

Source: `stdraw/metrics.py:1246`

```
        notes.append("n>10 caliber: mechanical-grid regularity gates "
                     "(cv_le_035 / pitch_uniform / column_snap24_ge_060) "
                     "demoted to report items per jacky 2026-11-26 ruling")
```

Source: `stdraw/metrics.py:1324`

```
    # n>10 (jacky ruling 2026-11-26) -- a demoted gate no longer blocks the
    # grade; its measured value travels in reports (block below).  For
    # n<=10 / manual figures the keys are present and the reads are
```

Source: `stdraw/routing.py:2476`

```
        jacky 2026-11-26 approval (multi-slot anchor vocabulary card),
        grounded in the stdraw20 manual-calibration lessons §4: the fan X
        5→3 fix came from SWAPPING the two competing anchors at the shared
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and
replaced in code by the rule text plus a `docs/adr/ADR-0018` pointer, per
the code-hygiene card. Two of them were **certificate output strings**
(the `regularity_demoted_note` report item and the matching `notes` entry),
so their de-attribution changes the emitted certificate bytes for n > 10
figures — see `docs/a-tier-drift-registry.md` for the registered drift.
