# Scorer v3-alpha: feature-system rebuild (calibration report)

Branch-only preview. Committed v1/v2 models and reports untouched;
positives zero-touch; negatives bytes sha256-verified unchanged;
certificate grading never reads the scorer; deterministic output.

## 1. Prescreen: before/after

- **before** (v2 single-variable AUC prescreen on the v3 pool): would keep **6 / 60** scalars — the blindness the hub-collapse diagnosis measured (23/32 signals thrown away; kept only align/bend).
- **after** (LASSO logistic lambda path, 5-fold CV selection, nnz <= n_pos guard): kept **9 / 60** scalars at lambda 2.942 (CV AUC 0.963).

| kept by LASSO | single-var AUC | v2 prescreen verdict |
|---|---|---|
| alignment_max_coverage | 0.850694 | keep |
| alignment_max_coverage_tight | 0.913194 | keep |
| anchor_orient_dev_mean | 0.89375 | keep |
| avg_edge_length | 0.277083 | DROP (signal recovered by v3) |
| bend_total_curvature | 0.088194 | keep |
| hub_degree | 0.511806 | DROP (signal recovered by v3) |
| mirror_axis_err | 0.660714 | DROP (signal recovered by v3) |
| nonloop_straight_rate | 0.861111 | keep |
| symmetry_axis_err_px | 0.660714 | DROP (signal recovered by v3) |

Dropped by LASSO (regularization decided, honest list): anchor_orient_dev_p75, anchor_orient_dev_sigma, anchor_orient_dev_worst, angular_resolution_min, aspect_deviation, automorphism_residual, bend_soft_margin, canvas_fill_rate, crossing_count, degree_canvas_spearman, edge_bend_mean, edge_bend_p75, edge_bend_sigma, edge_bend_worst, edge_detour_mean, edge_detour_p75, edge_detour_sigma, edge_detour_worst, edge_length_cv, edge_mirror_best_golden, edge_mirror_best_slot, edge_mirror_consistency_golden, edge_mirror_consistency_slot, edge_mirror_pair_coverage, edge_mirror_presence, hub_centroid_px, hub_centroid_ratio, hub_neighbor_centrality_ratio, loop_arc_rate, loop_arc_share_mean, loop_arc_share_p75, loop_arc_share_sigma, loop_arc_share_worst, loop_bow_agree_mean, loop_bow_agree_worst, loop_bow_outward_mean, loop_bow_outward_worst, loop_compactness_mean, loop_edge_crossings, loop_edge_length_cv, loop_foreign_nodes, loop_overlap_area, loop_self_intersections, max_min_edge_ratio, min_crossing_angle, min_spacing_px, min_spacing_ratio, node_spacing_cv, visual_centroid_px, visual_centroid_ratio, voronoi_area_cv

Coefficient path: lasso-path-v3-alpha.svg (data: lasso-path-v3-alpha.json).

## 2. AUC vs committed v2 (non-regression gate) + LOSO

| shape | v2 committed | v3-alpha | floor | floor met | non-reg | LOSO min (v3) |
|---|---|---|---|---|---|---|
| ring | 0.993464 | 1.0 | 0.993 | True | True | 41.6 |
| hub | 0.985507 | 1.0 | 0.986 | True | True | 64.9 |
| global | 0.975 | 0.995833 | None | None | True | 16.5 |

Held-out caveat: the LASSO kept set is selected on the full corpus
(mild selection leakage, disclosed); per-shape weights are re-fit
without the held-out anchor in the LOSO column.

## 3. Tier readings (negatives split by negatives-tiers.json)

- standard_only (n=25):
  - global: fitted=True AUC=0.995556 sep=-15.7
  - hub: fitted=True AUC=1.0 sep=49.0
  - ring: fitted=True AUC=1.0 sep=14.5
- engine_high_quality_only (n=15):
  - global: fitted=True AUC=0.992593 sep=-11.1
  - hub: fitted=True AUC=1.0 sep=14.5
  - ring: fitted=True AUC=0.444444 sep=-97.5

  Tier readings are EXPLORATORY subset refits (same convention as
  the tier-card preview), not committed models.  The
  engine_high_quality ring bucket (n=15 negatives, AUC 0.444 below
  chance) is reported as-is: the near-human engine tier genuinely
  overlaps the human ring anchors in the current feature space —
  consistent with the tier card's near_human findings.

## 4. Dose-response (perturbation pairs = diagnosis card D6)

- monotone-decreasing: **4 / 15 scored** (target >= 12/15) — **NOT met** (honest disclosure; per-anchor breakdown in the JSON); committed v2 model on the SAME pairs: 11 monotone-decreasing
- resolution classes: {"gate-blocked": 3, "mixed": 11, "monotone-decreasing": 4, "no-resolution": 0}
- gate-blocked anchors are excluded from the denominator (same rule
  as the committed diagnosis card).

### 4b. Why the target was NOT met (honest root causes)

- DOMINANT — stale-geometry recompute under relocation: the D6 doses move NODE CENTRES but the manual docs' stored route polylines / coordinate anchors do not move (byte-faithful ③A caliber).  The new per-edge features (anchor orientation, straight-rate, detour) recompute against that stale geometry and inject directionless noise: v2 (centre-based features) degrades coherently (11/15 monotone) while v3-alpha does not (4/15).
- score saturation: 11/15 anchors already score >= 90 at L0 (in-sample AUC 1.0 -> logistic overconfidence), so small feature changes near the cluster produce outsized swings.
- L1 jitter (+-3 px id-hash) sits below the 0.1 score resolution: 8/15 L1 steps score 0.0 delta, so the measured dose is effectively L2+ only.
- L2 swap2 RELOCATES two cards wholesale; for centre-based features (hub_degree / alignment / centroid) a relocation is not a degradation — 10/14 increase steps happen at L2.
- shape routing flips mid-dose (3 anchors): the score switches weight sets across the routing threshold, a discontinuity the monotonicity read penalizes but the certificate does not.

Bottom line (honest): v3-alpha REGRESSES on dose-response vs
committed v2 on identical pairs (4 vs 11 monotone-decreasing).
The dominant cause is measurable, not mysterious: the D6 doses
move node centres while the stored route polylines/coordinate
anchors stay put (byte-faithful ③A caliber), so the new
per-edge features recompute against stale geometry and inject
directionless noise; v2's centre-based features degrade
coherently. AUC/separation and hub-distinctness gates above
still show the feature system separates better; the
dose-response gate must be re-run AFTER perturbed docs get
re-routed/regenerated edge geometry (engine-side follow-up)
and after score calibration (top-of-scale saturation).

## 5. Hub-bucket collapse retest

- hub positives: 9; distinct kept-space vectors: **v2 = 2 (committed; re-measured 2) -> v3 = 9** — **improved**
- v3 hub features: alignment_max_coverage, alignment_max_coverage_tight, anchor_orient_dev_mean, avg_edge_length, bend_total_curvature, hub_degree, mirror_axis_err, nonloop_straight_rate, symmetry_axis_err_px

## 6. Calibers carried into the pool

- alignment tightened to a separate ±1 px key (alignment_max_coverage_tight); the v1 normalized key is unchanged;
- mirror consistency at the strict research caliber (slot = g<->g primary, golden as data) — regularizer decides its weight;
- edge aggregates are unitless (ratios / [0,1] angles), multi-quantile (mean/sigma/worst/P75); no absolute-pixel features.

## Red lines verified this run

- positives zero-touch; committed models/reports read-only;
- negatives bytes unchanged (sha256 before/after, 40 files);
- certificate grading never reads the scorer;
- deterministic output (no RNG; double-run byte-identical — evidence
  in the card evidence tree).
