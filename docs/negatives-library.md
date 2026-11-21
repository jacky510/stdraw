# Negatives library — aesthetic calibration (aesthetic-v1-negatives)

Single reference for the engine negative corpus used by the aesthetic-score
calibration set: what it is, its byte-protection status, and the TIER
dimension added by the negative-sample tier re-label card (v3 prerequisite 1,
approved caliber 2026-11-21).

## Corpus

- Location: `benchmarks/raw/aesthetic-v1-negatives/` — 40 engine auto-recipe
  layout JSONs (34 classic-graph engine outputs + 20 random-n10 samples
  i00–i19). **BYTE-PROTECTED, READ-ONLY**: every calibration driver
  (calibrate_v1, calibrate_v2, diagnose_collapse, calibrate_v3_preview)
  re-verifies sha256 stability and aborts on any change.
- Role in the calibration set: negatives for the human-vs-engine
  discriminator. Source labels (human/engine) are a FIXED dimension — the
  discriminator's job is untouched by any tiering.

## Tier dimension (approved caliber, 2026-11-21)

Negatives are additionally partitioned into tiers (source labels unchanged):

| tier | definition | n |
|---|---|---|
| `standard` | engine certificate grade != best | 25 |
| `engine_high_quality` | engine certificate grade == best (proxy caliber) | 15 |

- **Grade caliber**: proxy certificate — straight centre-to-centre segments,
  card dims from the doc (96×44 default), same caliber as
  `docs/diagnosis-hub-collapse.md` §5. `certificate_auto` (engine v2-hardgates
  ruler) is NOT re-run here.
- **near_human marker**: inside `engine_high_quality` only, a sample whose
  kept-feature-space L2 distance to the nearest human anchor is < 0.3 gets
  `near_human: true`. Measured members: soil-erosion (0.0856 →
  brand-flywheel), random-n10-i03 (0.2006 → epidemic-feedback).
- **Boundary disclosures (honest, no threshold tuning)**:
  fishing-collapse L2 = 0.3023 ≥ 0.3 → NOT near_human (card caliber listed
  it as a known candidate; the strict threshold wins); random-n10-i02
  L2 = 0.2995 < 0.3 but is standard-tier (grade second), and near_human
  applies only inside engine_high_quality.

## random-n10-i03 crossing suspect (dual reading)

Under the proxy caliber i03 grades best (0 straight-segment crossings), but
under the ENGINE DELIVERED POLYLINE geometry it has 3 endpoint-shared
crossings (N05→N06 arc × N00→N06 / N06→N07 lines) — see
`docs/diagnosis-hub-collapse.md` §5 (certificate-caliber caveat). Under
engine visual-crossing semantics (`certificate_auto`), i03 would NOT grade
best and the high-quality tier is **14**, not 15.

Caliber decision (approved): tier membership follows the proxy caliber;
the doubt is annotated in the manifest (`crossing_suspect`), never silently
dropped. Both counts travel together in every reading: 15 (proxy) / 14
(engine polyline semantics).

## Manifest + readings (authoritative files)

- `benchmarks/aesthetic/negatives-tiers.json` — per-sample manifest
  (graph / file / family / source_label / engine_grade_proxy /
  grade_caliber / proxy_crossings / tier / near_human /
  kept_feature_l2_distance / nearest_anchor / v2_score / routed_shape /
  i03 suspect annotation) + both calibration readings:
  - `default_all_negatives`: all 40, asserted equal to the committed
    `calibration-report-v2` shape stats (committed model space);
  - `tiered_standard_only` / `tiered_engine_high_quality_only`: per-tier
    negatives vs the full positive set, per-shape models RE-FIT on the
    subset — exploratory preview for the v3 decision, not a released model.
- `benchmarks/aesthetic/negatives-tiers-report.md` — human-readable summary.
- Driver: `benchmarks/aesthetic/calibrate_v3_preview.py` (deterministic,
  double-run byte-identical; recompute:
  `python benchmarks/aesthetic/calibrate_v3_preview.py`).

## Red lines

- Positives: zero-touch. v1/v2 models and committed calibration reports:
  read-only, never rewritten by the tiering.
- Discriminator (human vs engine): function unchanged — tiering is a
  reporting/decision dimension over engine negatives only.
- Any change to the 40 negative files' bytes is a violation and will be
  caught by the drivers' hash gates.
