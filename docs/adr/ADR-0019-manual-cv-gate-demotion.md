# ADR-0019: Manual (`--from-layout`) caliber — `cv_le_035` demotes to a report item

- **Status**: Accepted 2026-11-27

## Context

The 2026-11-26 ruling (ADR-0018-c) demoted the three mechanical-grid
regularity gates to report items on the **automatic** pipeline for n > 10
figures, on the evidence of the `stdraw20` manual-calibration lessons
(`stdraw20/docs/.../stdraw20-manual-calibration-lessons-for-stdraw.md`
section 5.1): the gates reward mechanical grids and penalize human
arrangements.

That ruling deliberately left the **manual** (`--from-layout`) caliber
alone — a hand-drawn replay kept `cv_le_035` as a hard gate. The manual
side is precisely the caliber the evidence is about, so the same
contradiction surfaced there: on six hand-drawn samples with 0 crossings
and 0 box press (row pitch / column snap not applicable by construction),
the spacing-CV gate alone rejected the certificates. Calibrating a
hand-drawn layout against a mechanical-grid regularity measure measures
nothing about the drawing.

The two calibers also shared one expression —
`_regularity_applies(c) = c.n_nodes <= 10 or c.manual_mode` — so a ruling
on either side could silently move the other. Separating them was a
precondition for changing one of them safely.

## Decision (rule in force)

- **Manual caliber (ADR-0019-a)**: on a `--from-layout` replay the
  spacing-CV gate `cv_le_035` never gates. It leaves `gates`, its measured
  boolean travels in the certificate `reports` block under the same key
  name, an additive `regularity_demoted_note` names the manual caliber and
  the 2026-11-27 ruling, and the gate is excluded from `gates_passed`,
  `blocking_gates` and the grading `hard_ok`. The underlying metrics rows
  (`spacing_cv`, `column_snap24_rate`) stay measured.
- **The pitch/snap family is NOT part of this ruling**: `pitch_uniform`
  (with its `spine_pitch_uniform` / `column_pitch_uniform` mode aliases)
  and `column_snap24_ge_060` keep the P1-2 `"N/A"` applicability slot they
  have carried since 2026-11-13 (ADR-0008). Those are applicability facts
  written into `gates` by the manual N/A overlay, not measured report
  items; demoting them would move the key into `reports` while the overlay
  writes it back as `"N/A"` — one key in two places, contradicting itself.
- **The automatic pipeline is untouched**: n <= 10 keeps all three
  regularity gates as hard gates; n > 10 keeps the ADR-0018-c demotion of
  all three. Certificate bytes for automatic figures are unchanged.
- **Caliber separation (ADR-0019-b)**: the registry `when` slots read one
  criterion per caliber and the two are composed, never merged —
  `_auto_regularity_applies` (n <= 10) for the automatic side,
  `_manual_cv_never_gates` (constant false) and
  `_manual_pitch_family_keeps_slot` (constant true) for the manual side,
  combined by `_caliber_policy(auto, manual)` keyed on `c.manual_mode`.
  A ruling on one caliber therefore cannot move the other by construction,
  which is what the 720-cell domain exhaustion in
  `tests/test_regular_gate_demotion.py` pins.

## Consequences

- A manual certificate carries one fewer applicable gate than the n <= 10
  automatic caliber: the measured gate count drops by exactly the demoted
  slot (e.g. 12/12 -> 11/11 on the classic-cld hand draft), and
  `reports["cv_le_035"]` carries the measured boolean.
- Manual figures whose only blocker was this gate now certify; figures
  blocked by crossings / box press / clearance / gap are unaffected and
  stay honestly ungraded.
- Nothing is relaxed for the automatic pipeline, and no gate threshold or
  grade semantics change (ADR-0014 remains in force).
- Evidence base and the full acceptance record live in the card that
  landed this: manual-leg byte regression over every active hand draft,
  registry-level domain exhaustion, the golden set and the full test
  suite.

## Original annotation (verbatim, as it stood in the code before migration)

> ``when`` policy (owner ruling 2026-11-26, stdraw20 manual-calibration
> lessons doc section 5.1; docs/adr/ADR-0018): ... The manual
> (--from-layout) caliber is NOT touched: manual figures keep today's
> slots (pitch_uniform / column_snap24_ge_060 = N/A per the P1-2 ruling,
> cv_le_035 still gating).

and, from the card that extended the ruling to the manual caliber:

> manual caliber: mechanical-grid spacing-CV gate cv_le_035 demoted to a
> report item per owner ruling 2026-11-27 (pitch_uniform /
> column_snap24_ge_060 keep their N/A slots)
