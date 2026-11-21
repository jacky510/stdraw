# Negatives tier re-label preview (v3 prerequisite 1)

Approved caliber: engine negatives with proxy certificate grade
= best move to the `engine_high_quality` tier; source labels
(human/engine) unchanged; discriminator models untouched. This
file is a PREVIEW reading for the v3 decision — nothing committed
was rewritten.

## Counts

- negatives total: 40
- standard tier: 25
- engine_high_quality: **15** (proxy caliber) / **14** (engine polyline semantics — random-n10-i03 has 3 endpoint-shared crossings under the delivered polyline geometry; docs/diagnosis-hub-collapse.md §5; annotated in the manifest, NOT silently dropped — approved caliber keeps proxy membership)
- near_human (kept-feature L2 to nearest human anchor < 0.3,
  engine_high_quality members only): **2**

## near_human members

| graph | kept-feature L2 distance | nearest anchor |
|---|---|---|
| random-n10-i03 | 0.2006 | epidemic-feedback:epidemic-feedback-manual-layout.json |
| soil-erosion | 0.0856 | brand-flywheel:brand-flywheel-manual-layout.json |

## Boundary disclosures (honest, no threshold tuning)

- **fishing-collapse** (L2 0.3023): listed as a known near-human candidate in the card caliber, but 0.3023 >= 0.3 — NOT marked near_human under the strict threshold; disclosed as-is
- **random-n10-i02** (L2 0.2995): standard-tier member (grade second); below the 0.3 threshold but near_human applies only inside engine_high_quality by the approved caliber

## Readings (winning caliber: normalized)

default = all 40 negatives (current caliber; asserted equal to the
committed calibration-report-v2 shape stats, committed model space).
tiered = each tier as the negative set vs the FULL positive set,
with per-shape models RE-FIT on that subset (calibrate_shape_
conditional semantics) — an EXPLORATORY preview of what v3
separation would look like if a tier were excluded from the fit
set; per-sample v2_score in the manifest stays in committed-model
space.

| reading | shape | fitted | AUC | separation | n_pos | n_neg | neg max | pos min |
|---|---|---|---|---|---|---|---|---|
| default_all_negatives | global | True | 0.975 | -54.1 | 18 | 40 | 83.6 | 29.5 |
| default_all_negatives | hub | True | 0.985507 | -13.9 | 9 | 23 | 79.3 | 65.4 |
| default_all_negatives | ring | True | 0.993464 | -1.6 | 9 | 17 | 58.1 | 56.5 |
| tiered_standard_only | global | True | 0.991111 | -21.7 | 18 | 25 | 77.7 | 56.0 |
| tiered_standard_only | hub | True | 1.0 | 19.1 | 9 | 10 | 42.8 | 61.9 |
| tiered_standard_only | ring | True | 0.992593 | -10.0 | 9 | 15 | 51.9 | 41.9 |
| tiered_engine_high_quality_only | global | True | 0.97037 | -15.0 | 18 | 15 | 60.7 | 45.7 |
| tiered_engine_high_quality_only | hub | True | 0.991453 | -10.3 | 9 | 13 | 69.2 | 58.9 |
| tiered_engine_high_quality_only | ring | True | 0.055556 | -100.0 | 9 | 2 | 100.0 | 0.0 |

Buckets with fitted=false do not meet the minimum-positive gate
under that negative subset — reported as-is, never padded.

## v3 decision pointers

- human/engine discriminator: UNCHANGED (this card adds a tier
  dimension over engine negatives only).
- if v3 adopts the tiered caliber for separation/AUC, re-derive
  weights via a full calibration run — this preview does not fit
  any released model.
- i03 dual reading must be carried into the v3 card body.

## Red lines verified this run

- positives zero-touch; models / committed reports read-only;
- negatives bytes unchanged (sha256 before/after, 40 files);
- v2 per-sample negative scores reproduced 40/40;
- deterministic output (sorted iteration, no RNG).

Per-sample manifest: negatives-tiers.json (graph / file / family /
grade / tier / near_human / kept_feature_l2_distance /
nearest_anchor / v2_score / routed_shape / i03 suspect annotation).