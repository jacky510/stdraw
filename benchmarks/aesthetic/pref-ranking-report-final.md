# Final preference comparison: two merged rounds, stratified

Merged data: 25 strict decided pairs (round-1 13 + round-2 12), 11 both-good (epsilon calibration), 10 both-bad (pool-quality warning); noise baselines: in-session 5/6 = 83.3%, cross-session 2/3 = 66.7% (the signal gate).  All BT arms run on the converged solver (gradient gate < 1e-6 asserted on every fit); synthetic arms listed side by side, never merged.

## Stratified headline (read with the CI width)

| stratum | arm | pairwise acc | 95% CI (Wilson) | signal? | Top-1 | gap (pp) |
|---|---|---|---|---|---|---|
| S_all | M0 | 10/25 = 40.0% | [23.4%, 59.3%] | no signal | 3/3 | - |
| S_all | M1 | 3/25 = 12.0% | [4.2%, 30.0%] | no signal | 0/3 | 58.7 |
| S_all | M2 | 7/25 = 28.0% | [14.3%, 47.6%] | no signal | 0/3 | 60.8 |
| S_all | M1s | 3/25 = 12.0% | [4.2%, 30.0%] | no signal | 0/3 | 58.7 |
| S_all | M2s | 9/25 = 36.0% | [20.2%, 55.5%] | no signal | 0/3 | 52.8 |
| S_r2 | M0 | 2/12 = 16.7% | [4.7%, 44.8%] | no signal | 2/2 | - |
| S_r2 | M1 | 5/12 = 41.7% | [19.3%, 68.0%] | no signal | 0/2 | 23.7 |
| S_r2 | M2 | 8/12 = 66.7% | [39.1%, 86.2%] | at the gate (equal to 2/3, not above) | 0/2 | 25.8 |
| S_r2 | M1s | 5/12 = 41.7% | [19.3%, 68.0%] | no signal | 0/2 | 23.7 |
| S_r2 | M2s | 9/12 = 75.0% | [46.8%, 91.1%] | signal | 0/2 | 25.0 |
| S_r1 | M0 | 8/13 = 61.5% | [35.5%, 82.3%] | no signal | 3/3 | - |
| S_r1 | M1 | 5/13 = 38.5% | [17.7%, 64.5%] | no signal | 2/3 | 47.0 |
| S_r1 | M2 | 1/13 = 7.7% | [1.4%, 33.3%] | no signal | 0/3 | 92.3 |
| S_r1 | M1s | 3/13 = 23.1% | [8.2%, 50.3%] | no signal | 1/3 | 60.3 |
| S_r1 | M2s | 0/13 = 0.0% | [0.0%, 22.8%] | no signal | 0/3 | 85.2 |

Signal gate = cross-session noise baseline 2/3 = 66.7% (stricter than in-session 5/6 = 83.3%).  n=25/12/13: CIs are wide by construction; the only allowed conclusions are "signal / no signal" and "did the edge dimensions add increment".

## Edge dimensions (M2 vs M1) - increment judgment

| stratum | M1 acc | M2 acc | delta | CI overlap | verdict |
|---|---|---|---|---|---|
| S_all | 12.0% | 28.0% | 16.0pp | yes | no increment demonstrated (CIs overlap, n insufficient - one more round needed) |
| S_r2 | 41.7% | 66.7% | 25.0pp | yes | no increment demonstrated (CIs overlap, n insufficient - one more round needed) |
| S_r1 | 38.5% | 7.7% | -30.8pp | yes | no increment demonstrated (CIs overlap, n insufficient - one more round needed) |

## Round divergence check (S_r1 old picture caliber vs S_r2 byte-faithful)

| arm | S_r1 acc | S_r2 acc | delta | same side of coin flip? |
|---|---|---|---|---|
| M0 | 61.5% | 16.7% | -44.9pp | NO - divergence |
| M1 | 38.5% | 41.7% | 3.2pp | yes |
| M2 | 7.7% | 66.7% | 59.0pp | NO - divergence |
| M1s | 23.1% | 41.7% | 18.6pp | yes |
| M2s | 0.0% | 75.0% | 75.0pp | NO - divergence |

## Per-fold detail (LOSO by topology)

### S_all

| arm | held-out topology | n train (human/syn) | train acc | test acc |
|---|---|---|---|---|
| M0 | 多环耦合 | 20/0 | 35.0% | 60.0% (3/5) |
| M0 | 嵌套环 | 14/0 | 71.4% | 0.0% (0/11) |
| M0 | 梳状 | 20/0 | 35.0% | 60.0% (3/5) |
| M0 | 非平面族 | 21/0 | 28.6% | 100.0% (4/4) |
| M1 | 多环耦合 | 20/0 | 70.0% | 20.0% (1/5) |
| M1 | 嵌套环 | 14/0 | 71.4% | 0.0% (0/11) |
| M1 | 梳状 | 20/0 | 70.0% | 20.0% (1/5) |
| M1 | 非平面族 | 21/0 | 71.4% | 25.0% (1/4) |
| M2 | 多环耦合 | 20/0 | 65.0% | 20.0% (1/5) |
| M2 | 嵌套环 | 14/0 | 100.0% | 36.4% (4/11) |
| M2 | 梳状 | 20/0 | 95.0% | 40.0% (2/5) |
| M2 | 非平面族 | 21/0 | 95.2% | 0.0% (0/4) |
| M1s | 多环耦合 | 20/30 | 70.0% | 20.0% (1/5) |
| M1s | 嵌套环 | 14/30 | 71.4% | 0.0% (0/11) |
| M1s | 梳状 | 20/30 | 70.0% | 20.0% (1/5) |
| M1s | 非平面族 | 21/30 | 71.4% | 25.0% (1/4) |
| M2s | 多环耦合 | 20/30 | 65.0% | 40.0% (2/5) |
| M2s | 嵌套环 | 14/30 | 100.0% | 36.4% (4/11) |
| M2s | 梳状 | 20/30 | 95.0% | 40.0% (2/5) |
| M2s | 非平面族 | 21/30 | 95.2% | 25.0% (1/4) |

### S_r2

| arm | held-out topology | n train (human/syn) | train acc | test acc |
|---|---|---|---|---|
| M0 | 多环耦合 | 10/0 | 20.0% | 0.0% (0/2) |
| M0 | 嵌套环 | 6/0 | 33.3% | 0.0% (0/6) |
| M0 | 梳状 | 9/0 | 11.1% | 33.3% (1/3) |
| M0 | 非平面族 | 11/0 | 9.1% | 100.0% (1/1) |
| M1 | 多环耦合 | 10/0 | 70.0% | 50.0% (1/2) |
| M1 | 嵌套环 | 6/0 | 50.0% | 33.3% (2/6) |
| M1 | 梳状 | 9/0 | 77.8% | 33.3% (1/3) |
| M1 | 非平面族 | 11/0 | 63.6% | 100.0% (1/1) |
| M2 | 多环耦合 | 10/0 | 90.0% | 100.0% (2/2) |
| M2 | 嵌套环 | 6/0 | 100.0% | 66.7% (4/6) |
| M2 | 梳状 | 9/0 | 88.9% | 66.7% (2/3) |
| M2 | 非平面族 | 11/0 | 90.9% | 0.0% (0/1) |
| M1s | 多环耦合 | 10/30 | 70.0% | 50.0% (1/2) |
| M1s | 嵌套环 | 6/30 | 50.0% | 33.3% (2/6) |
| M1s | 梳状 | 9/30 | 77.8% | 33.3% (1/3) |
| M1s | 非平面族 | 11/30 | 63.6% | 100.0% (1/1) |
| M2s | 多环耦合 | 10/30 | 100.0% | 100.0% (2/2) |
| M2s | 嵌套环 | 6/30 | 100.0% | 66.7% (4/6) |
| M2s | 梳状 | 9/30 | 100.0% | 66.7% (2/3) |
| M2s | 非平面族 | 11/30 | 100.0% | 100.0% (1/1) |

### S_r1

| arm | held-out topology | n train (human/syn) | train acc | test acc |
|---|---|---|---|---|
| M0 | 多环耦合 | 10/0 | 50.0% | 100.0% (3/3) |
| M0 | 嵌套环 | 8/0 | 100.0% | 0.0% (0/5) |
| M0 | 梳状 | 11/0 | 54.5% | 100.0% (2/2) |
| M0 | 非平面族 | 10/0 | 50.0% | 100.0% (3/3) |
| M1 | 多环耦合 | 10/0 | 80.0% | 100.0% (3/3) |
| M1 | 嵌套环 | 8/0 | 100.0% | 0.0% (0/5) |
| M1 | 梳状 | 11/0 | 81.8% | 100.0% (2/2) |
| M1 | 非平面族 | 10/0 | 80.0% | 0.0% (0/3) |
| M2 | 多环耦合 | 10/0 | 100.0% | 0.0% (0/3) |
| M2 | 嵌套环 | 8/0 | 100.0% | 20.0% (1/5) |
| M2 | 梳状 | 11/0 | 100.0% | 0.0% (0/2) |
| M2 | 非平面族 | 10/0 | 100.0% | 0.0% (0/3) |
| M1s | 多环耦合 | 10/30 | 80.0% | 100.0% (3/3) |
| M1s | 嵌套环 | 8/30 | 100.0% | 0.0% (0/5) |
| M1s | 梳状 | 11/30 | 63.6% | 0.0% (0/2) |
| M1s | 非平面族 | 10/30 | 90.0% | 0.0% (0/3) |
| M2s | 多环耦合 | 10/30 | 60.0% | 0.0% (0/3) |
| M2s | 嵌套环 | 8/30 | 100.0% | 0.0% (0/5) |
| M2s | 梳状 | 11/30 | 90.9% | 0.0% (0/2) |
| M2s | 非平面族 | 10/30 | 90.0% | 0.0% (0/3) |

## Top-1 vs jacky (per stratum)

### S_all

| graph | jacky top (win counts) | M0 | M1 | M2 | M1s | M2s |
|---|---|---|---|---|---|---|
| brand-flywheel | tie (g4c1:2, g4c2:2, g4c3:2) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) |
| classic-cld-growth-and-burden | tie (g5c0:1, g5c1:1, g5c2:1, g5c3:1, g5c4:1) | g5c0 (tie-note) | g5c0 (tie-note) | g5c0 (tie-note) | g5c0 (tie-note) | g5c0 (tie-note) |
| comb-supply-demand | g3c0 (g3c0:4, g3c1:1) | **g3c0** | g3c1 | g3c1 | g3c1 | g3c1 |
| coupled-underinvestment | g1c0 (g1c0:4, g1c1:1) | **g1c0** | g1c1 | g1c1 | g1c1 | g1c1 |
| nonplanar-credit | g2c0 (g2c0:4) | **g2c0** | g2c1 | g2c1 | g2c1 | g2c1 |

### S_r2

| graph | jacky top (win counts) | M0 | M1 | M2 | M1s | M2s |
|---|---|---|---|---|---|---|
| brand-flywheel | tie (g4c1:1, g4c2:1, g4c3:1) | g4c0 (tie-note) | g4c0 (tie-note) | g4c1 (tie-note) | g4c0 (tie-note) | g4c1 (tie-note) |
| classic-cld-growth-and-burden | tie (g5c0:1, g5c2:1, g5c3:1) | g5c0 (tie-note) | g5c2 (tie-note) | g5c0 (tie-note) | g5c2 (tie-note) | g5c0 (tie-note) |
| comb-supply-demand | g3c0 (g3c0:2, g3c1:1) | **g3c0** | g3c1 | g3c1 | g3c1 | g3c1 |
| coupled-underinvestment | tie (g1c0:1, g1c1:1) | g1c0 (tie-note) | g1c1 (tie-note) | g1c1 (tie-note) | g1c1 (tie-note) | g1c1 (tie-note) |
| nonplanar-credit | g2c0 (g2c0:1) | **g2c0** | g2c1 | g2c1 | g2c1 | g2c1 |

### S_r1

| graph | jacky top (win counts) | M0 | M1 | M2 | M1s | M2s |
|---|---|---|---|---|---|---|
| brand-flywheel | tie (g4c1:1, g4c2:1, g4c3:1) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) | g4c0 (tie-note) |
| classic-cld-growth-and-burden | tie (g5c1:1, g5c4:1) | g5c0 (tie-note) | g5c0 (tie-note) | g5c1 (tie-note) | g5c0 (tie-note) | g5c0 (tie-note) |
| comb-supply-demand | g3c0 (g3c0:2) | **g3c0** | **g3c0** | g3c1 | g3c1 | g3c1 |
| coupled-underinvestment | g1c0 (g1c0:3) | **g1c0** | **g1c0** | g1c1 | **g1c0** | g1c1 |
| nonplanar-credit | g2c0 (g2c0:3) | **g2c0** | g2c1 | g2c1 | g2c1 | g2c1 |

## Train-holdout gap (review trigger at 15pp)

| stratum | arm | mean train acc | pooled test acc | gap (pp) | flagged |
|---|---|---|---|---|---|
| S_all | M1 | - | 0.12 | 58.7 | YES |
| S_all | M2 | - | 0.28 | 60.8 | YES |
| S_all | M1s | - | 0.12 | 58.7 | YES |
| S_all | M2s | - | 0.36 | 52.8 | YES |
| S_r2 | M1 | - | 0.4167 | 23.7 | YES |
| S_r2 | M2 | - | 0.6667 | 25.8 | YES |
| S_r2 | M1s | - | 0.4167 | 23.7 | YES |
| S_r2 | M2s | - | 0.75 | 25.0 | YES |
| S_r1 | M1 | - | 0.3846 | 47.0 | YES |
| S_r1 | M2 | - | 0.0769 | 92.3 | YES |
| S_r1 | M1s | - | 0.2308 | 60.3 | YES |
| S_r1 | M2s | - | 0.0 | 85.2 | YES |

## Epsilon calibration initial values (11 both-good pairs, P75 caliber)

full-data calibration model per arm (trained on all 25 decided pairs; synthetic added only for the s-arms); tie margin = |model score difference (M0) or BT logit (BT arms)| over the 11 both-good pairs; epsilon initial value = P75 of that distribution (P75 caliber).  The earlier epsilon0 caliber = max over tie pairs (conservative); both are reported.  Relation to the v1.3.1 review draft section 14: the feature caliber descends from its Appendix A 21-feature union, and its small-graph degeneracy risk list (gate-pinned / collapsed features) bounds what a tie margin can express - the P75 value is an INITIAL calibration constant, not a validated threshold.

| arm | P25 | P50 | P75 (initial) | max (legacy epsilon0) | decided min abs margin |
|---|---|---|---|---|---|
| M0 | 0.0 | 0.0 | **58.6** | 58.6 | - |
| M1 | 0.0 | 0.0 | **0.137687** | 0.137687 | 0.0 |
| M2 | 0.0 | 0.0 | **0.295067** | 0.305921 | 0.097671 |
| M1s | 0.0 | 0.0 | **0.002984** | 0.178572 | 0.0 |
| M2s | 0.0 | 0.0 | **0.164992** | 0.342505 | 0.216555 |

Solver convergence (full-data calibration fits; M0 is the pointwise baseline, no fit):

- M1: 50 Newton iters, final gradient norm 1.92208e-08, final objective 13.4677
- M2: 6 Newton iters, final gradient norm 2.19287e-15, final objective 14.4635
- M1s: 7 Newton iters, final gradient norm 1.04075e-12, final objective 30.9674
- M2s: 7 Newton iters, final gradient norm 2.23598e-15, final objective 28.0099
- gate: every BT fit in this experiment (all LOSO folds, all full-data fits, sanity leg) asserts final gradient norm < 1e-6 at fit time; the objective is convex in w (logistic loss + L2 ridge), so the first-order gate is the global-optimum reference.  The pre-convergence artifact readings are not reproducible by design

## Both-bad pairs (pool-quality warning, 10)

| session | pair | graph | a | b |
|---|---|---|---|---|
| r1 | nonplanar-credit|g2c1|g2c3 | nonplanar-credit | g2c1/draft/uncertified | g2c3/auto-arc/uncertified |
| r1 | coupled-underinvestment|g1c1|g1c3 | coupled-underinvestment | g1c1/draft/best | g1c3/auto-arc/best |
| r1 | brand-flywheel|g4c2|g4c3 | brand-flywheel | g4c2/auto/best | g4c3/auto-arc/best |
| r1 | nonplanar-credit|g2c2|g2c3 | nonplanar-credit | g2c2/auto/uncertified | g2c3/auto-arc/uncertified |
| r1 (retest) | nonplanar-credit|g2c1|g2c3 | nonplanar-credit | g2c1/draft/uncertified | g2c3/auto-arc/uncertified |
| r1 (retest) | brand-flywheel|g4c2|g4c3 | brand-flywheel | g4c2/auto/best | g4c3/auto-arc/best |
| r2 | brand-flywheel|brand-flywheel-manual-layout-L4|g4c0 | brand-flywheel | g4c0/manual/best | brand-flywheel-manual-layout-L4/deep-L4/- |
| r2 | nonplanar-credit|g2c3|nonplanar-credit-manual-layout-L4 | nonplanar-credit | g2c3/auto-arc/uncertified | nonplanar-credit-manual-layout-L4/deep-L4/- |
| r2 | nonplanar-credit|g2c1|nonplanar-credit-manual-layout-L4 | nonplanar-credit | g2c1/draft/uncertified | nonplanar-credit-manual-layout-L4/deep-L4/- |
| r2 | nonplanar-credit|g2c2|nonplanar-credit-manual-layout-L4 | nonplanar-credit | g2c2/auto/uncertified | nonplanar-credit-manual-layout-L4/deep-L4/- |

## Round-3 recommendation (measured-yield derived)

Observed strict-decision yield: round 1 0.542, round 2 0.706 (pooled 0.61 of new questions).

ChatGPT 150~250-pair budget, both readings:

| reading | budget | have | still needed | ~sessions of 20q |
|---|---|---|---|---|
| answered questions | 150 | 50 | 100 | 5 |
| answered questions | 250 | 50 | 200 | 10 |
| strict decided pairs | 150 | 25 | 125 | 10 |
| strict decided pairs | 250 | 25 | 225 | 18 |

Wilson half-width at p=0.7: n=50 -> 12.3pp, n=80 -> 9.9pp, n=100 -> 8.8pp.  An incremental verdict (M2 vs M1) needs roughly n=80~100 decided pairs in the SAME picture caliber before its CI can separate; at the pooled 61% decision yield that is about 130~165 new questions = 7~8 sessions of 20 questions.

Round 3 = 20~24 adaptive questions with the round-2 tool, ALL rendered byte-faithful (this experiment shows the old re-routed caliber REVERSES the M2 direction, so mixing calibers again would poison the increment verdict).  Composition: M2-vs-M1 uncertain pairs first (edge-dimension increment is the open question), both-good pairs kept mixed in (epsilon calibration has only 11 samples), 3~4 cross-session retests to grow the stricter noise baseline.  jacky time per session: recorded click time was 1.5~2.5 min (median 2.7~4.0 s/question); budget 5 min with overhead.  Milestone: after ~4 sessions (~80 new answered, ~50 new decided in byte-faithful caliber) re-run this experiment; escalate to the full 150~250-pair budget only if the byte-faithful stratum keeps its direction.

## Sanity flip leg (S_all, M1/M2)

- M1: 19/25 = 76.0% (non-degenerate = evaluator has discriminative power)
- M2: 19/25 = 76.0% (non-degenerate = evaluator has discriminative power)

## Noise-baseline rows (caliber of the 2/3)

| kind | pair | first | retest | agree |
|---|---|---|---|---|
| in-session | coupled-underinvestment|g1c0|g1c1 | g1c0 | g1c0 | yes |
| in-session | coupled-underinvestment|g1c0|g1c3 | g1c0 | g1c0 | yes |
| in-session | nonplanar-credit|g2c1|g2c3 | both_bad | both_bad | yes |
| in-session | comb-supply-demand|g3c0|g3c2 | both | g3c0 | NO |
| in-session | brand-flywheel|g4c2|g4c3 | both_bad | both_bad | yes |
| in-session | classic-cld-growth-and-burden|g5c0|g5c1 | g5c1 | g5c1 | yes |
| in-session | comb-supply-demand|g3c0|g3c2 | both | g3c0 | NO |
| cross-session | classic-cld-growth-and-burden|g5c1|g5c2 | both | both | yes |
| cross-session | brand-flywheel|g4c1|g4c3 | both | both | yes |

(cross-session caliber compares round-2 retest answers with round-1 FIRST-round answers; the comb pair drifted from "both" to a lean - counted as disagree, noise feature)

## Discriminator non-regression (quality gate)

All four committed v3-beta AUC-table rows reproduced exactly after preference training (deterministic refits; the pointwise judge is untouched, sha256-pinned before/after):

| reading | ring | hub | global |
|---|---|---|---|
| backfilled_drop_both_format_artifacts | 0.947712 | 1.0 | 0.886111 |
| backfilled_drop_nonloop_straight_rate | 0.986928 | 1.0 | 0.981944 |
| committed_kept_set_backfilled | 1.0 | 1.0 | 0.997222 |
| legacy_kept_set_reproduction | 1.0 | 1.0 | 0.995833 |

## Red lines honoured

- zero certificate-grade reads by the ranker (grades appear only in the pool-quality warning composition)
- candidate pool reproduced with the viewer's gate-viability filter, zero score weight; pool validated against both sessions' committed metadata
- deterministic output (double-run byte-identical); negatives library read-only; committed scorer artifacts sha-pinned

