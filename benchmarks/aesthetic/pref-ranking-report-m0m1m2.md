# Preference-ranking comparison: M0 / M1 / M2 (+ M1s / M2s)

First Learning-to-Rank round on the 2026-11-21 blind-choice session (24 first-round pairs, 13 decided / 7 both-good / 4 both-bad first-round; 6 retest repeats, consistency 5/6 = individual noise baseline).

## Conclusion (first round)

- No arm clears the coin-flip line convincingly, and no arm reaches jacky's retest noise baseline (5/6 = 83.3%): the first-round reading is **no signal** at n=13 decided pairs.
- M1 (v2 features) reads 85.5% mean in-fold train but 38.5% held-out (gap +47.0pp) and M2 reads 7.7% held-out (gap +92.3pp): both trip the 15pp overfitting review trigger.  After the solver-convergence fix every BT arm sits inside the noise band - no signal; the first delivery's "M1s/M2s diverge from M1/M2 in opposite directions" reading was an unconverged-solver artifact and is withdrawn: at the converged optimum M2 and M2s anti-generalize in the SAME direction (the synthetic-pair dose caliber remains a diagnosis family, reported side by side, never merged).
- M2's first-delivery 0/13 held-out ("every topology fold 0/N, systematic anti-generalization, not a protocol artifact") was an optimizer artifact: the diagonal-Hessian IRLS with a duplicated feature column (mirror_axis_err == symmetry_axis_err_px on every candidate) never converged.  At the converged optimum M2 reads 1/13 held-out and M2s reads 0/13 - all BT arms inside the noise band, no signal.  The anti-generalization DIRECTION survives for M2 (12/13 held-out margins keep the delivered sign; only the classic tie pair q19 flips), but the exact 0/13 and per-fold 0/N readings do not; the label-flip sanity leg still reads non-degenerately (see JSON sanity_flip_leg).
- Practical read: the 24-pair first-round budget does not support per-topology preference training yet; the pointwise M0 baseline (61.5%) and its 3/3 Top-1 rate on the three aggregable graphs remain the strongest round-one observation.

## Headline (read with the CI width - n=13 decided pairs)

| arm | pairwise acc | 95% CI (Wilson) | above noise 5/6 | Top-1 rate |
|---|---|---|---|---|
| M0 | 8/13 = 61.5% | [35.5%, 82.3%] | no | 3/3 (100%) |
| M1 | 5/13 = 38.5% | [17.7%, 64.5%] | no | 2/3 (67%) |
| M2 | 1/13 = 7.7% | [1.4%, 33.3%] | no | 0/3 (0%) |
| M1s | 3/13 = 23.1% | [8.2%, 50.3%] | no | 1/3 (33%) |
| M2s | 0/13 = 0.0% | [0.0%, 22.8%] | no | 0/3 (0%) |

Honesty notes:

- n=13 decided pairs: every CI is wide; conclusions are "signal / no signal" only, never "model A beats model B".
- Top-1 aggregation covers only graphs where jacky's plurality winner is unique (see per-graph table below).
- Synthetic pairs are user-confirmed, but they come from the diagnosis card's dose caliber (node-centre movement + edge damage), NOT the route-preserving dose family; s-arms and plain arms are reported side by side and never merged.
- The route-preserving dose gate remains unmeasurable; the v3-beta report statement carries over verbatim.

## Per-fold detail (leave-one-topology-out)

| arm | held-out topology | graphs | n train (human/syn) | train acc | test acc |
|---|---|---|---|---|---|
| M0 | 多环耦合 | coupled-underinvestment | 10/0 | 50.0% | 100.0% (3/3) |
| M0 | 嵌套环 | brand-flywheel, classic-cld-growth-and-burden | 8/0 | 100.0% | 0.0% (0/5) |
| M0 | 梳状 | comb-supply-demand | 11/0 | 54.5% | 100.0% (2/2) |
| M0 | 非平面族 | nonplanar-credit | 10/0 | 50.0% | 100.0% (3/3) |
| M1 | 多环耦合 | coupled-underinvestment | 10/0 | 80.0% | 100.0% (3/3) |
| M1 | 嵌套环 | brand-flywheel, classic-cld-growth-and-burden | 8/0 | 100.0% | 0.0% (0/5) |
| M1 | 梳状 | comb-supply-demand | 11/0 | 81.8% | 100.0% (2/2) |
| M1 | 非平面族 | nonplanar-credit | 10/0 | 80.0% | 0.0% (0/3) |
| M2 | 多环耦合 | coupled-underinvestment | 10/0 | 100.0% | 0.0% (0/3) |
| M2 | 嵌套环 | brand-flywheel, classic-cld-growth-and-burden | 8/0 | 100.0% | 20.0% (1/5) |
| M2 | 梳状 | comb-supply-demand | 11/0 | 100.0% | 0.0% (0/2) |
| M2 | 非平面族 | nonplanar-credit | 10/0 | 100.0% | 0.0% (0/3) |
| M1s | 多环耦合 | coupled-underinvestment | 10/30 | 80.0% | 100.0% (3/3) |
| M1s | 嵌套环 | brand-flywheel, classic-cld-growth-and-burden | 8/30 | 100.0% | 0.0% (0/5) |
| M1s | 梳状 | comb-supply-demand | 11/30 | 63.6% | 0.0% (0/2) |
| M1s | 非平面族 | nonplanar-credit | 10/30 | 90.0% | 0.0% (0/3) |
| M2s | 多环耦合 | coupled-underinvestment | 10/30 | 80.0% | 0.0% (0/3) |
| M2s | 嵌套环 | brand-flywheel, classic-cld-growth-and-burden | 8/30 | 100.0% | 0.0% (0/5) |
| M2s | 梳状 | comb-supply-demand | 11/30 | 90.9% | 0.0% (0/2) |
| M2s | 非平面族 | nonplanar-credit | 10/30 | 90.0% | 0.0% (0/3) |

## Train-holdout gap (review trigger at 15pp)

| arm | mean train acc | pooled test acc | gap (pp) | flagged |
|---|---|---|---|---|
| M1 | 0.8546 | 0.3846 | 47.0 | YES |
| M2 | 1.0 | 0.0769 | 92.3 | YES |
| M1s | 0.8341 | 0.2308 | 60.3 | YES |
| M2s | 0.9023 | 0.0 | 90.2 | YES |

## Top-1 selection vs jacky (per graph)

| graph | jacky top (win counts) | M0 | M1 | M2 | M1s | M2s |
|---|---|---|---|---|---|
| brand-flywheel | tie (g4c1:1, g4c2:1, g4c3:1) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) |
| classic-cld-growth-and-burden | tie (g5c1:1, g5c4:1) | g5c0 (tie-note) | g5c0 (tie-note) | g5c1 (tie-note) | g5c0 (tie-note) | g5c0 (tie-note) |
| comb-supply-demand | g3c0 (g3c0:2) | **g3c0** | **g3c0** | g3c1 | g3c1 | g3c1 |
| coupled-underinvestment | g1c0 (g1c0:3) | **g1c0** | **g1c0** | g1c1 | **g1c0** | g1c1 |
| nonplanar-credit | g2c0 (g2c0:3) | **g2c0** | g2c1 | g2c1 | g2c1 | g2c1 |

## Full-data BT weights (calibration model, disclosure)

- M1 (bias 0.0): avg_edge_length=0.64565, bend_total_curvature=-0.603799, crossing_count=-0.64565, alignment_max_coverage=0.619097
  - converged: 6 Newton iters, final gradient norm 7.23777e-16, objective 5.86225
- M2 (bias 0.0): anchor_orient_dev_mean=-0.27857, avg_edge_length=0.745198, bend_total_curvature=0.098117, hub_degree=0.0, mirror_axis_err=-0.088587, nonloop_straight_rate=-0.062602, alignment_max_coverage=0.535428, alignment_max_coverage_tight=0.47416
  - merged duplicate column: symmetry_axis_err_px dropped (bitwise identical to mirror_axis_err)
  - converged: 50 Newton iters, final gradient norm 8.33295e-10, objective 7.21515
- M1s (bias 0.0): avg_edge_length=0.18013, bend_total_curvature=-0.353697, crossing_count=-1.606185, alignment_max_coverage=0.274135
  - converged: 7 Newton iters, final gradient norm 4.54469e-14, objective 23.7496
- M2s (bias 0.0): anchor_orient_dev_mean=-0.23991, avg_edge_length=-1.271645, bend_total_curvature=-0.618282, hub_degree=0.0, mirror_axis_err=0.031291, nonloop_straight_rate=0.140156, alignment_max_coverage=0.241772, alignment_max_coverage_tight=0.156698
  - merged duplicate column: symmetry_axis_err_px dropped (bitwise identical to mirror_axis_err)
  - converged: 6 Newton iters, final gradient norm 2.47703e-13, objective 24.0275
- convergence gate: every BT fit (LOSO folds, full-data calibration, sanity leg) ends with final gradient norm < 1e-6, asserted at fit time; duplicate feature columns are merged before fitting (JSON bt_weights_full_data.*.merged_duplicate_columns)

## Epsilon calibration initial values (7 both-good pairs)

epsilon0 = max |margin| over tie pairs (below epsilon0 -> declare tie); contrast = min |margin| over decided training pairs.

| arm | epsilon0 | decided-pair min abs margin |
|---|---|---|
| M0 | 58.6 | 0.0 |
| M1 | 1.203222 | 0.0 |
| M2 | 1.087513 | 0.054949 |
| M1s | 0.991306 | 0.0 |
| M2s | 1.398247 | 0.0923 |

Solver caliber note: the review's converged epsilon reference (M2 1.066145 / M2s 1.399488) was computed on the UNMERGED feature space, where the ridge acts on BOTH duplicate columns; with mirror_axis_err / symmetry_axis_err_px merged the merged-column readings shift in the last decimals (M2 1.087513 / M2s 1.398247) while every headline reading matches.  Convergence acceptance uses the gradient gate (< 1e-6 asserted on every fit), not the unmerged-space objective value.

## Both-bad pairs (pool-quality warning, 6)

| pair | graph | a | b |
|---|---|---|---|
| nonplanar-credit|g2c1|g2c3 | nonplanar-credit | g2c1/draft/uncertified | g2c3/auto-arc/uncertified |
| coupled-underinvestment|g1c1|g1c3 | coupled-underinvestment | g1c1/draft/best | g1c3/auto-arc/best |
| brand-flywheel|g4c2|g4c3 | brand-flywheel | g4c2/auto/best | g4c3/auto-arc/best |
| nonplanar-credit|g2c2|g2c3 | nonplanar-credit | g2c2/auto/uncertified | g2c3/auto-arc/uncertified |
| nonplanar-credit|g2c1|g2c3 | nonplanar-credit | g2c1/draft/uncertified | g2c3/auto-arc/uncertified |
| brand-flywheel|g4c2|g4c3 | brand-flywheel | g4c2/auto/best | g4c3/auto-arc/best |

## Discriminator non-regression (quality gate)

All four committed v3-beta AUC-table rows reproduced exactly after preference training (deterministic refits; the pointwise judge is untouched, sha-pinned before/after):

| reading | ring | hub | global |
|---|---|---|---|
| legacy_kept_set_reproduction | 1.0 | 1.0 | 0.995833 |
| committed_kept_set_backfilled | 1.0 | 1.0 | 0.997222 |
| backfilled_drop_nonloop_straight_rate | 0.986928 | 1.0 | 0.981944 |
| backfilled_drop_both_format_artifacts | 0.947712 | 1.0 | 0.886111 |

- caliber note: the operating instruction's 'ring 0.987' corresponds to the drop-nonloop_straight_rate ABLATION row (0.986928); the committed kept set on the backfilled path reads ring 1.0 / hub 1.0. All four committed rows reproduced exactly after preference training; preference training touches no pointwise artifact (sha256 pinned before/after)
- sha256 pins on the pointwise scorer artifacts unchanged (7 files)

## Red lines honoured

- zero certificate-grade reads by the ranker (grades appear only in the pool-quality warning composition)
- candidate pool reproduced with the viewer's gate-viability filter, zero score weight; pool validated field-by-field against the committed session metadata
- deterministic output (double-run byte-identical); negatives library read-only; committed scorer artifacts sha-pinned

