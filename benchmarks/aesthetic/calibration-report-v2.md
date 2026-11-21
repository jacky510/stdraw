# aesthetic_score v2 calibration report (18-anchor recalibration)

Position: three-tier-funnel placeholder heuristic + measurement instrument only.
Final adjudication = Pareto + preference ranker (Phase 3). Certificate grading
(best/uncertified) never reads this score.

## Data

- anchors (positive): 18 — benchmarks/manual/* (11-06~11-20) + jacky-batch2/exports (11-21, x8) + tests/data; batch-2 engine drafts excluded
- negatives: 40 — benchmarks/raw/aesthetic-v1-negatives (unchanged bytes)
- edge-set caliber: every anchor edge set completed from its graph source
  (negatives engine layout, else batch-2 sources/*.cld) BEFORE features are
  measured; per-anchor completeness ASSERTED (edge_supplement_log +
  completeness_check in calibration-report-v2.json)
- family labels: topology-families.json extended with the batch-2 families
  (nested-ring x2, nonplanar x2, bowtie, comb, multi-cycle-coupled;
  PROVENANCE.md is the label authority; measured quirks logged in the
  per-graph rationale, e.g. nested shared-edge counts exceed the classic
  nested-cycle <=1 clause — disclosed, not re-judged)

## v1 -> v2 headline (winning caliber: normalized)

| metric | v1 (10 anchors) | v2 (18 anchors) |
|---|---|---|
| ring AUC | 0.976471 | 0.993464 |
| ring separation | -6.9 | -1.6 |
| ring neg max | 56.8 | 58.1 |
| ring pos min | 49.9 | 56.5 |
| ring n_pos/n_neg | 5/17 | 9/17 |
| hub AUC | 0.973913 | 0.985507 |
| hub separation | -9.2 | -13.9 |
| hub neg max | 77.0 | 79.3 |
| hub pos min | 67.8 | 65.4 |
| hub n_pos/n_neg | 5/23 | 9/23 |
| global AUC | 0.955 | 0.975 |
| global separation | -47.1 | -54.1 |
| global neg max | 83.2 | 83.6 |
| global pos min | 36.1 | 29.5 |
| global n_pos/n_neg | 10/40 | 18/40 |
| LOSO ring min | 17.3 | 13.8 |
| LOSO hub min | 57.9 | 63.6 |
| human lower bound | {"global": 36.1, "hub": 67.8, "ring": 49.9} | {"global": 29.5, "hub": 65.4, "ring": 56.5} |

## Shape detail (v2, per shape)

- ring: AUC=0.993464, separation=-1.6 (pos min 56.5 / neg max 58.1), n=9/17, excluded=['alignment_max_coverage']
  - HONESTY NOTE: ring positives do NOT fully separate from negatives under the supplemented-edge caliber (separation <= 0) — this is the honest state of the model, no threshold was tuned to mask it
- hub: AUC=0.985507, separation=-13.9 (pos min 65.4 / neg max 79.3), n=9/23, excluded=none
  - HONESTY NOTE: hub positives do NOT fully separate from negatives under the supplemented-edge caliber (separation <= 0) — this is the honest state of the model, no threshold was tuned to mask it
- global: AUC=0.975, separation=-54.1 (pos min 29.5 / neg max 83.6), n=18/40, excluded=none
  - HONESTY NOTE: global positives do NOT fully separate from negatives under the supplemented-edge caliber (separation <= 0) — this is the honest state of the model, no threshold was tuned to mask it
- LOSO (shape-conditional): ring min 13.8 / hub min 63.6
- human lower bound (recomputed per shape): {'ring': 56.5, 'hub': 65.4, 'global': 29.5}
- fit sample counts recorded per shape in the model; weights/bounds re-derived
  at this run because the anchor library grew (designed flow, first exercise).

## Threshold re-derivation audit (anchor library 10 -> 18)

- verdict: **UNCHANGED** (threshold 0.75)
- measured eligible intensities this run: [0.333333, 0.375, 0.4, 0.444444, 0.5, 0.6, 0.666667, 0.7, 0.8, 0.875, 0.923077, 0.944444, 1.0, 1.2, 1.25]
- gap around threshold still empty: True; threshold is gap midpoint: True
- fail-loud guard (check_hub_intensity_gap) ran on every calibration pass and
  did not raise: no threshold-eligible value landed strictly inside (0.70, 0.80).

## Test-Retest pairs (same graph, repeated drags = individual noise baseline)

| pair | drag 1 | drag 2 |
|---|---|---|
| classic-cld (11-06 vs 11-21 retest) | classic-cld-manual-layout.json | retest-classic-cld-manual-layout.json |
|  |Δ| (abs, norm) | 0.0 | 0.0 |
|  routed shapes (abs) | hub | hub |
| random-n10-i05 (11-16 vs 11-20 double drag) | random-n10-i05-manual-layout.json | i05.json |
|  |Δ| (abs, norm) | 0.4 | 4.5 |
|  routed shapes (abs) | hub | ring |
| random-n10-i11 (11-20 same-day double drag a/b) | i11-a.json | i11-b.json |
|  |Δ| (abs, norm) | 0.0 | 1.1 |
|  routed shapes (abs) | ring | ring |

Per-caliber numbers: test_retest_pairs in calibration-report-v2.json.
Reading: the pair deltas are the individual noise baseline — family/anchor
differences smaller than this baseline are NOT interpretable as signal.
CAVEAT (degeneracy, see shape_bucket_degeneracy): a pair whose two drags both
route into a degenerate bucket has delta 0 BY CONSTRUCTION (e.g. the classic-cld
retest pair, hub bucket) — such a 0 is NOT a stability result.  The interpretable
retest numbers are the ring-bucket ones (i11 a/b, i05).  The i05 pair ALSO
flips routed shape between drags (11-16 hub -> 11-20 ring): same graph,
boundary routing is drag-sensitive — recorded, not tuned away.

## Shape-bucket degeneracy audit (honesty instrument)

- absolute/hub: distinct positive vectors = 2, largest group 8/9  **NEAR-DEGENERATE** — NEAR-degenerate
- absolute/ring: distinct positive vectors = 3, largest group 7/9
- normalized/hub: distinct positive vectors = 2, largest group 8/9  **NEAR-DEGENERATE** — NEAR-degenerate
- normalized/ring: distinct positive vectors = 9, largest group 1/9

## Batch-2 family separation (observation item: did doubling the anchors help?)

Precision on coverage: bowtie / comb / nonplanar had ZERO anchors in v1 —
unmeasurable then, first measured now.  nested-ring and multi-cycle-coupled
HAD classic anchors in v1 (brand-flywheel, classic-cld); this batch adds the
first dedicated nested/coupled hand anchors.  Separation is measured per
anchor family vs the negatives of its routed shape bucket (conservative:
the union over every shape the family routes to).  CAVEAT: hub-bucket anchor
scores sit on the near-degenerate collapsed point (see degeneracy audit),
so a hub-side separation margin of ~2 points is thin and NOT interpretable
as per-family hand-skill signal.

| family | batch-2 anchors (routed, score) | batch2 pos min | shape-bucket neg max | separated |
|---|---|---|---|---|
| 多环耦合 | coupled-underinvestment-manual-layout.json (hub, 81.3) | 81.3 | 79.3 | True |
| 嵌套环 | nested-capacity-manual-layout.json (ring, 84.1); nested-learning-manual-layout.json (ring, 83.3) | 83.3 | 79.3 | True |
| 梳状 | comb-supply-demand-manual-layout.json (hub, 81.3) | 81.3 | 79.3 | True |
| 非平面族 | nonplanar-credit-manual-layout.json (hub, 81.3); nonplanar-inventory-manual-layout.json (ring, 97.8) | 81.3 | 79.3 | True |
| 领结 | bowtie-wage-price-manual-layout.json (ring, 88.6) | 88.6 | 58.1 | True |

Families that do NOT separate: see separated=False rows.  No threshold was
tuned; minimum-anchor estimates for non-separating families are recorded in
the JSON (family_min_anchor_estimate) and restated in the card summary.

## Edge style / anchor position (new data dimensions — NOT features in v2)

- totals over the 8 batch-2 exports: {'manual_edges': 45, 'style': {'auto': 36, 'straight': 5, 'arc': 3, 'free': 1}, 'anchor_positions': {'src:ne': 4, 'src:n': 5, 'dst:e': 4, 'src:w': 4, 'dst:n': 10, 'src:s': 9, 'dst:nw': 4, 'src:se': 2, 'dst:s': 9, 'dst:sw': 3, 'src:e': 4, 'src:s-g1': 2, 'dst:w-g1': 1, 'dst:w': 3, 'src:s-g2': 1, 'src:e-g2': 3, 'dst:e-g1': 1, 'src:w-g1': 1, 'dst:e-g2': 1, 'src:w-g2': 1}, 'edges_with_anchors': 43, 'edges_with_waypoints': 2}
- NOT introduced as model features in v2.  (a) single-source red line: scorer features come from the one measurement source (aesthetic_score extract_scalars); edge style/anchors live only in manual exports.  (b) coverage gate: style data exists for 8/18 anchors (44%) < MIN_COVERAGE 0.70 — the existing feature-keeping gate would drop it, and the 10 v1 anchors have no style field at all (supplemented edges are untouched = straight centre-to-centre, no user style).  Logged as data for a future card that widens the anchor library with style-native exports.

## Caliber comparison

| metric | absolute px | normalized |
|---|---|---|
| worst-shape AUC | 0.944444 | 0.985507 |
| worst-shape LOSO min | 1.0 | 13.8 |

- winning caliber: normalized (cross-canvas / cross-graph (normalized by canvas diagonal, RFC §15.2)); rule: max worst-shape LOSO-min, tie-break worst-shape AUC
- Spearman across calibers: negatives 0.9529, positives 0.5172
- cross-class ordering disagreements: 26 / 720 pairs
- domain declarations: absolute = same-canvas-family only; normalized =
  cross-canvas. Every score output carries its domain.

## Family separation (normalized caliber, post-routing)

| family | n_neg | neg max | n_pos | pos min | separated |
|---|---|---|---|---|---|
| classic/单环 | 1 | 41.7 | 0 | None | False |
| classic/多环耦合 | 11 | 26.6 | 0 | None | False |
| classic/嵌套环 | 8 | 79.3 | 0 | None | False |
| hub | 0 | None | 9 | 65.4 | False |
| random-n10 | 20 | 70.8 | 0 | None | False |
| ring | 0 | None | 9 | 56.5 | False |

## Reference-vs-measured rho (NOT a sign check — see v1 report for the note)

| graph | expected | reference rho | measured rho (in-repo) | sign match | routed |
|---|---|---|---|---|---|
| random-n10-i05 | ring | -0.26 | 0.190128171 | False | hub |
| brand-flywheel | ring | -0.14 | 0.15430335 | False | hub |
| epidemic-feedback | ring | -0.24 | -0.107700688 | True | ring |
| classic-cld-growth-and-burden | hub | 0.4 | -0.536349916 | False | hub |
| random-n10-i00 | hub | 0.59 | -0.56445967 | False | ring |

## LOSO per anchor (normalized)

| held-out | shape | score |
|---|---|---|
| brand-flywheel | hub | 81.2 |
| classic-cld-growth-and-burden | hub | 81.2 |
| fan-d12 | hub | 63.6 |
| fan-d17 | hub | 81.2 |
| bowtie-wage-price | ring | 88.3 |
| comb-supply-demand | hub | 81.2 |
| coupled-underinvestment | hub | 81.2 |
| nested-capacity | ring | 83.6 |
| nested-learning | ring | 82.7 |
| nonplanar-credit | hub | 79.2 |
| nonplanar-inventory | ring | 98.2 |
| classic-cld-growth-and-burden | hub | 81.2 |
| random-n10-i00 | ring | 58.1 |
| random-n10-i05 | hub | 81.2 |
| random-n10-i05 | ring | 13.8 |
| random-n10-i11 | ring | 97.1 |
| random-n10-i11 | ring | 95.9 |
| epidemic-feedback | ring | 52.0 |
