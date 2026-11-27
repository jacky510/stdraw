# ADR-0010: Manual ground-truth recalibration: hand-drawn fixtures override uncalibrated thresholds

- **Status**: Ring battery v0.8.2; radial recalibrated 2026-11-15; anchor data packaged with the candidate-generation card

## Context

Principle: manual ground truth is the calibration authority for
regularity thresholds; uncalibrated engine-derived floors that reject good
hand layouts are wrong, not the layouts.

## Decision (rule in force)

(a) Card-gap breathing target 36px = the average over 14 hand-drawn
samples (+35.8px). (b) Ring regularity: the former 0.05 calibers were
uncalibrated and REJECTED the hand-drawn good ring itself (brand-flywheel
CV 0.0802 / deviation 0.1197); thresholds re-derived from the manual band
(CV <= 0.50, template fit <= 0.70, single source stdraw/ringlayout.py).
(c) Radial: recalibrated against hand-dragged fan-d12/fan-d17 exports -
minimum card pair rect-gap 6px (tight manual packing), azimuth CV up to
0.486 - the band reads the fixtures, not the old engine's quantization
floor; box-aware packing reproduces the manual packing almost exactly
(fan-d17 ~283px vs manual 282px). (d) Anchor-prior data: the hand-drawn
layouts and their precomputed feature rows are DATA
(stdraw/data/anchor-features.json, packaged with the wheel, only-add); the
code never embeds anchor coordinates or thresholds.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/radellayout.py:49`

```
manual ground truth -- jacky hand-dragged fan-d12/fan-d17, exported via
"Export layout", stored under benchmarks/manual/):
  - HUB center deviation <= 2px (engine invariant: the hub sits on the
```

Source: `stdraw/radellayout.py:60`

```
  - min card pair rect-gap >= 6px (manual minimum: 6px fan-d17 -- jacky
    packs tightly to keep total spoke length minimal; the chord-based
    ring radius is retired for the single-ring path);
```

Source: `stdraw/radellayout.py:71`

```
reproduces jacky's manual packing almost exactly (fan-d17: closed-form
minimum ~283px vs manual mean spoke 282px; the old conservative caliber
sat at 414px, +46% total edge length).  A double ring now only appears
```

Source: `stdraw/radellayout.py:154`

```
    full chord width), which is exactly the slack jacky's manual layouts
    use to keep total spoke length minimal.
    """
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0010` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
