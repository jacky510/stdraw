# Scorer v3-beta: independent-review rework (calibration report)

Branch-only preview. Committed v3-alpha model / report / lasso
path and the committed v2 model are read-only (sha256-pinned);
positives zero-touch; negatives bytes sha256-verified unchanged;
certificate grading never reads the scorer; deterministic output.

## 1. MAJOR-1 — dose comparison put on one criterion

- Same criterion (monotone AND at least one strictly decreasing step) on the committed D6 pairs, legacy caliber, per-anchor scores reproducing calibration-report-v3-alpha 18/18: **v3 4 vs v2 6** of 15 scored (the earlier "4 vs 11" counted v2 non-increasing, all-flat anchors included).
- v2 monotone non-increasing on the same pairs: 11; the 5 all-flat anchors (brand-flywheel-manual-layout, classic-cld-manual-layout, comb-supply-demand-manual-layout, coupled-underinvestment-manual-layout, retest-classic-cld-manual-layout) are listed separately — half of the v2 column was "perturbation cannot move the score at all", not "degrades coherently".
- Naming fixed: monotone_nondecreasing -> **monotone_nonincreasing**
  (never rises; flat allowed). Dose gate stays UNMET (4/15, target >= 12/15).

## 2. MAJOR-2 — dose attribution rewritten + route-preserving dose

- Stored-geometry audit: stale geometry (polylines/coordinate
  anchors left behind by centre doses) applies to **1/18 anchors**
  (only epidemic-feedback stores route polylines). For the other
  anchors the noise source is the slot-anchor + centre-line
  semantics, not stale geometry; "engine-side reroute then
  re-measure" had no positive pilot support and is withdrawn as
  an acceptance route.
- New route-preserving dose arm (edge attributes only; node
  centres / card dims / viewBox byte-frozen — asserted per level):
  v3 **0 vs v2 15** strict monotone-decreasing of 15 scored;
  route-preserved violations: 0.
- MEASURABLE: every anchor exposes edge attributes (slot anchors / declared style / waypoints), so the RP dose perturbs the features the committed model actually reads without a caliber change confound beyond the disclosed backfill. GATE STATUS: no RP target value is committed here; the committed D6 centre-moving gate remains UNMET (4/15) and any RP gate value must be decided AFTER a model refit on the fixed data path (follow-up card, not this one). The committed model was fit on the legacy caliber, so RP readings are exploratory.
- WITHDRAWN as an acceptance route: the review's reroute pilot produced no positive example (verifybot reroute.json — epidemic-feedback re-routed stays 56.9/56.5/0.5 and was monotone anyway; brand-flywheel re-routed changes caliber, L0 98.9->30.8, and still rises +1.2 at L1), and only 1/18 anchors carries stored polylines (>= 3 would be needed). Re-testing rerouting requires first collecting >= 3 anchors with stored polylines (follow-up corpus work, not this card).

## 3. MAJOR-3 — loop data path fixed, honest re-measurement

- merge_layout_edges now backfills loop_kinds / loop_color (and
  maps engine arc/line route kinds to style) onto manual anchors,
  multiplicity-aware, never overriding human values; committed
  v1/v2 calibers pinned legacy for byte-reproducibility.
- Evaluability after the fix: loop_arc_rate evaluability after the backfill: 4/18 positives (below floor) — the loop-closure family still cannot enter the LASSO (coverage floor 0.7 NOT met). Loop metadata reaches the positives from exactly two sources: manual exports that natively carry loop_kinds (epidemic-feedback, the only one) and negatives-library engine layouts backfilled by merge_layout_edges (brand-flywheel, classic-cld, retest-classic-cld — 3 anchors); graph-source (.cld) merges have no loop metadata to backfill, and random-graph engines declare no loops. Root cause is fixed in the data path; the corpus needs engine-delivered layouts for the remaining anchors before the family can be scored (follow-up).
- ring AUC below the 0.993 floor with the committed kept set on the fixed path when drop nonloop_straight_rate (0.986928) — reported as-is; the ring bucket stays DOWNGRADED and hub (AUC 1.0, robust in every ablation) + independent LOSO carry the non-regression evidence.
- ring AUC below the 0.993 floor with the committed kept set on the fixed path when drop both format artifacts (0.947712) — reported as-is; the ring bucket stays DOWNGRADED and hub (AUC 1.0, robust in every ablation) + independent LOSO carry the non-regression evidence.
- hub distinct kept-space vectors: 9 (committed 9) — unchanged.

AUC readings (committed kept set; refits are disclosed exploratory
readings, the committed model is unchanged):

| reading | ring | hub | global |
|---|---|---|---|
| legacy caliber (reproduction) | 1.0 | 1.0 | 0.995833 |
| backfilled path | 1.0 | 1.0 | 0.997222 |
| backfilled, drop nonloop_straight_rate | 0.986928 | 1.0 | 0.981944 |
| backfilled, drop both format artifacts | 0.947712 | 1.0 | 0.886111 |

## 4. ring AUC 1.0 — downgraded; evidence restated

- DOWNGRADED: the ring bucket AUC 1.0 is NOT claimed as 'the feature system separates human quality better'. Part of it is explained by the manual-export format (pixel-aligned slot anchors, no stored polylines): with the format-artifact features removed the reading falls below the 0.993 floor (see Arm C ablations). Non-regression evidence is restated on the hub bucket (AUC 1.0, robust in every ablation) plus the committed independent LOSO.
- Committed LOSO minima: ring 41.6 / hub 64.9 (independent held-out support); hub AUC 1.0 with hub-distinct vectors 9 (committed 9).

## 5. MINOR dispositions

- MINOR-1 (mirror duplicate): mirror_axis_err and symmetry_axis_err_px are one duplicated column (identical value on all 58/58 docs — 22 non-null equal + 36 both-null; identical weights in all three shape models). Narrative fixed: the LASSO rescue is 3 INDEPENDENT signals, not 4. Pool names kept byte-stable; merging the column is a schema change deferred to the next pool revision.
- MINOR-2 (lambda path): the fixed-sweep warm-start path is NOT strictly nested (nnz [0, 1, 2, 4, 4, 5, 6, 7, 7, 7, 9, 11, 12, 13, 12, 13, 13, 13, 12, 13, 13, 15, 15, 15], 2 decrease step(s)); the selection rule and the selected lambda are unaffected; disclosure added here and to the path-plot note.
- MINOR-3 (saturation): z/derivative table added to the JSON
  (ring z 0.278..5.9897, hub z 1.6929..5.3024, global z -0.8979..6.3416; no positive in
  the floating saturation region).
- MINOR-4 (EHQ ring bucket): corrected wording: the EHQ ring bucket holds 2 NEGATIVES (the 15 is the whole EHQ tier); the AUC 0.444 reading is a 2-negative reading and is labelled as such.

## Red lines verified this run

- committed v3-alpha model/report/lasso path + v2 model sha256
  unchanged; positives zero-touch; negatives bytes unchanged;
- certificate grading never reads the scorer;
- legacy-caliber D6 arm reproduces the committed per-anchor
  scores 18/18; deterministic output (double-run byte-identical,
  evidence in the card evidence tree).
