# Final preference comparison v2: three merged rounds

36 strict decided pairs (13 + 12 + 11), 18 both-good, 29 both-bad; converged BT solver; strata S_all / S_r12 (mixed picture caliber) / S_r3 (byte-faithful) reported as-is.

## Conclusion

- **S_r3 M0 reads 8/11 = 72.7%, numerically above the 66.7% gate** - but the Wilson CI [43.4%, 90.2%] is wide at this n; read as *directional, not conclusive*.
- M2 vs M1 edge-dimension increment: **still not demonstrated** (CIs overlap in every stratum; n=36 remains insufficient).
- New-topology generalization (nested-ring-shared-node / chain-ring-hybrid / dual-hub-asymmetric): **not measurable** - zero decided pairs; all 14 newtopo pairs answered both-bad (pool-quality warning, {"nested-ring-shared-node": 5, "chain-ring-hybrid": 5, "dual-hub-asymmetric": 4, "classic-cld-growth-and-burden": 1, "brand-flywheel": 1, "comb-supply-demand": 1, "nonplanar-credit": 2}).
- Anchor vs engine (the round's most direct new signal): jacky prefers his own hand-made anchor in 6 of 7 decided anchor pairs (86%), but the preference-trained arms rank the human anchor FIRST in only {"M0": 4, "M1": 0, "M2": 1, "M1s": 0, "M2s": 1} of the 9 asked pairs (out-of-fold, S_all) - the BT arms do not recognize the human quality jacky sees; the untrained pointwise M0 does noticeably better ({"M0": 0.5714, "M1": 0.0, "M2": 0.1429, "M1s": 0.0, "M2s": 0.1429}).
- Noise floor: round-3 retests were 3 tie-reproductions (tie-level 3/3); the winner-level gate stays 2/3 = 66.7% (pooled cross-session 5/6).  Epsilon initial value (P75 over 18 both-good pairs): {"M0": 58.6, "M1": 0.241496, "M2": 0.001107, "M1s": 0.176325, "M2s": 0.204446}.

Backward compatibility: S_r12 (rounds 1-2 merged) reproduces the committed two-round artifact's S_all readings exactly (M0 0.4, M1 0.12, M2 0.28, M1s 0.12, M2s 0.36) - the round-3 feature-space extension is provably neutral on the rounds-1-2 reading.

## Headline (read with the CI widths)

| stratum | arm | pairwise acc | 95% CI (Wilson) | verdict |
|---|---|---|---|---|
| S_all | M0 | 18/36 = 50.0% | [34.5%, 65.5%] | no signal |
| S_all | M1 | 6/36 = 16.7% | [7.9%, 31.9%] | no signal |
| S_all | M2 | 8/36 = 22.2% | [11.7%, 38.1%] | no signal |
| S_all | M1s | 6/36 = 16.7% | [7.9%, 31.9%] | no signal |
| S_all | M2s | 11/36 = 30.6% | [18.0%, 46.9%] | no signal |
| S_r12 | M0 | 10/25 = 40.0% | [23.4%, 59.3%] | no signal |
| S_r12 | M1 | 3/25 = 12.0% | [4.2%, 30.0%] | no signal |
| S_r12 | M2 | 7/25 = 28.0% | [14.3%, 47.6%] | no signal |
| S_r12 | M1s | 3/25 = 12.0% | [4.2%, 30.0%] | no signal |
| S_r12 | M2s | 9/25 = 36.0% | [20.2%, 55.5%] | no signal |
| S_r3 | M0 | 8/11 = 72.7% | [43.4%, 90.2%] | signal |
| S_r3 | M1 | 5/11 = 45.5% | [21.3%, 72.0%] | no signal |
| S_r3 | M2 | 3/11 = 27.3% | [9.8%, 56.6%] | no signal |
| S_r3 | M1s | 5/11 = 45.5% | [21.3%, 72.0%] | no signal |
| S_r3 | M2s | 3/11 = 27.3% | [9.8%, 56.6%] | no signal |

## Per-graph leave-one-graph-out accuracy (question 2)

| graph | M0 | M1 | M2 |
|---|---|---|---|
| brand-flywheel | 0.3333 (3/9) | 0.3333 (3/9) | 0.0 (0/9) |
| classic-cld-growth-and-burden | 0.0 (0/7) | 0.0 (0/7) | 0.2857 (2/7) |
| comb-supply-demand | 0.7778 (7/9) | 0.1111 (1/9) | 0.3333 (3/9) |
| coupled-underinvestment | 0.5 (3/6) | 0.1667 (1/6) | 0.0 (0/6) |
| nonplanar-credit | 1.0 (5/5) | 0.2 (1/5) | 0.0 (0/5) |

New-topology verdict: ZERO decided pairs on the three training-unseen graphs: all 14 newtopo pairs were answered both-bad, so per-graph leave-one-graph-out pairwise accuracy on them is NOT MEASURABLE (n=0).  The both-bad composition is the actual generalization signal and is reported in the warning list.

## Anchor vs engine (question 3, out-of-fold margins)

| qid | graph | human | engine | jacky | S_all/M0 | S_all/M1 | S_all/M2 |
|---|---|---|---|---|---|---|---|
| q04 | classic-cld-growth-and-burden | g5c0 | r3e5g0c1 | engine | -60.900 | -1.571 | -3.075 |
| q11 | coupled-underinvestment | g1c0 | r3e1g0c0 | human | +0.000 | +0.000 | -0.505 |
| q18 | comb-supply-demand | g3c0 | r3e3g0c0 | human | +10.600 H | -0.328 | -2.707 |
| q20 | nonplanar-credit | g2c0 | r3e2g0c0 | human | +74.900 H | -9.717 | -11.355 |
| q21 | comb-supply-demand | g3c0 | r3e3g0c2 | human | +52.400 H | -1.310 | -3.669 |
| q22 | classic-cld-growth-and-burden | g5c0 | r3e5g0c0 | both_bad | - | - | - |
| q25 | classic-cld-growth-and-burden | g5c1 | r3e5g0c0 | human | +0.000 | +0.000 | +0.009 H |
| q29 | comb-supply-demand | g3c0 | r3e3g0c1 | human | +35.100 H | -1.960 | -1.131 |
| q30 | brand-flywheel | g4c0 | r3e4g0c0 | both_bad | - | - | - |

Human-first ratios - primary = OUT-OF-FOLD margins on the 7 jacky-decided anchor pairs; secondary = full-data calibration model over all 9 asked pairs (in-sample for the 7, disclosed caveat):

- S_all M0: out-of-fold 4/7 = 57.1% | all-9 calib-model 6/9 = 66.7%
- S_all M1: out-of-fold 0/7 = 0.0% | all-9 calib-model 5/9 = 55.6%
- S_all M2: out-of-fold 1/7 = 14.3% | all-9 calib-model 9/9 = 100.0%
- S_all M1s: out-of-fold 0/7 = 0.0% | all-9 calib-model 5/9 = 55.6%
- S_all M2s: out-of-fold 1/7 = 14.3% | all-9 calib-model 8/9 = 88.9%
- S_r3 M0: out-of-fold 4/7 = 57.1% | all-9 calib-model 6/9 = 66.7%
- S_r3 M1: out-of-fold 1/7 = 14.3% | all-9 calib-model 5/9 = 55.6%
- S_r3 M2: out-of-fold 3/7 = 42.9% | all-9 calib-model 9/9 = 100.0%
- S_r3 M1s: out-of-fold 1/7 = 14.3% | all-9 calib-model 5/9 = 55.6%
- S_r3 M2s: out-of-fold 2/7 = 28.6% | all-9 calib-model 8/9 = 88.9%

## Epsilon calibration (P75 over 18 both-good pairs)

| arm | P75 initial | P50 | max (legacy epsilon0) | P75 r12 | P75 r3 | exact-zero margins |
|---|---|---|---|---|---|---|
| M0 | 58.6 | 2.3 | 58.6 | 58.6 | 30.45 | 8 |
| M1 | 0.241496 | 0.163738 | 0.241496 | 0.241496 | 0.224826 | 8 |
| M2 | 0.001107 | 0.001107 | 0.430781 | 0.001107 | 0.430781 | 8 |
| M1s | 0.176325 | 0.114149 | 0.225956 | 0.176325 | 0.225956 | 8 |
| M2s | 0.204446 | 0.202875 | 0.828577 | 0.204446 | 0.828577 | 8 |

## Both-bad pool-quality warning (round 3, 19 pairs)

By graph: {"nested-ring-shared-node": 5, "chain-ring-hybrid": 5, "dual-hub-asymmetric": 4, "classic-cld-growth-and-burden": 1, "brand-flywheel": 1, "comb-supply-demand": 1, "nonplanar-credit": 2}

New-topology engine recipe counts: {"auto": 14, "ortho": 14}

| pair_key | kind | a | b |
|---|---|---|---|
| nested-ring-shared-node|r3n1g0c0|r3n1g0c2 | newtopo | r3n1g0c0/auto+A@68 | r3n1g0c2/auto+B@68 |
| chain-ring-hybrid|r3n2g0c2|r3n2g0c3 | newtopo | r3n2g0c2/auto+B@68 | r3n2g0c3/ortho+B@80 |
| chain-ring-hybrid|r3n2g0c0|r3n2g0c2 | newtopo | r3n2g0c0/auto+A@68 | r3n2g0c2/auto+B@68 |
| dual-hub-asymmetric|r3n3g0c0|r3n3g0c1 | newtopo | r3n3g0c0/auto+A@68 | r3n3g0c1/ortho+A@80 |
| chain-ring-hybrid|r3n2g0c1|r3n2g0c3 | newtopo | r3n2g0c1/ortho+A@80 | r3n2g0c3/ortho+B@80 |
| dual-hub-asymmetric|r3n3g0c1|r3n3g0c3 | newtopo | r3n3g0c1/ortho+A@80 | r3n3g0c3/ortho+B@80 |
| dual-hub-asymmetric|r3n3g0c0|r3n3g0c2 | newtopo | r3n3g0c0/auto+A@68 | r3n3g0c2/auto+B@68 |
| chain-ring-hybrid|r3n2g0c0|r3n2g0c3 | newtopo | r3n2g0c0/auto+A@68 | r3n2g0c3/ortho+B@80 |
| dual-hub-asymmetric|r3n3g0c2|r3n3g0c3 | newtopo | r3n3g0c2/auto+B@68 | r3n3g0c3/ortho+B@80 |
| classic-cld-growth-and-burden|g5c0|r3e5g0c0 | anchor | g5c0/manual | r3e5g0c0/ortho+A@80 |
| nested-ring-shared-node|r3n1g0c1|r3n1g0c3 | newtopo | r3n1g0c1/ortho+A@80 | r3n1g0c3/ortho+B@80 |
| chain-ring-hybrid|r3n2g0c0|r3n2g0c1 | newtopo | r3n2g0c0/auto+A@68 | r3n2g0c1/ortho+A@80 |
| brand-flywheel|g4c0|r3e4g0c0 | anchor | g4c0/manual | r3e4g0c0/ortho+A@80 |
| nested-ring-shared-node|r3n1g0c0|r3n1g0c3 | newtopo | r3n1g0c0/auto+A@68 | r3n1g0c3/ortho+B@80 |
| comb-supply-demand|g3c1|g3c2 | disagree | g3c1/draft | g3c2/auto |
| nonplanar-credit|g2c1|r3e2g0c2 | disagree | g2c1/draft | r3e2g0c2/auto+A@72 |
| nonplanar-credit|g2c1|r3e2g0c0 | disagree | g2c1/draft | r3e2g0c0/auto+A@68 |
| nested-ring-shared-node|r3n1g0c2|r3n1g0c3 | newtopo | r3n1g0c2/auto+B@68 | r3n1g0c3/ortho+B@80 |
| nested-ring-shared-node|r3n1g0c0|r3n1g0c1 | newtopo | r3n1g0c0/auto+A@68 | r3n1g0c1/ortho+A@80 |

## Noise floor

- in-session (round 1): 5/6 = 83.3%
- cross-session winner-level (round 2): 2/3 = 66.7% - the SIGNAL GATE stays at 66.7%
- cross-session tie-level (round 3): 3/3 tie reproductions
- pooled cross-session: 5/6 = 83.3%

## Edge-dimension increment (M2 vs M1, question 5)

- S_all: M1 16.7% vs M2 22.2% (delta 5.6pp), CIs overlap -> no increment demonstrated (CIs overlap, n insufficient)
- S_r12: M1 12.0% vs M2 28.0% (delta 16.0pp), CIs overlap -> no increment demonstrated (CIs overlap, n insufficient)
- S_r3: M1 45.5% vs M2 27.3% (delta -18.2pp), CIs overlap -> no increment demonstrated (CIs overlap, n insufficient)

## Train-holdout gap (review trigger at 15pp)

- S_all M1: gap 50.7pp (flag YES)
- S_all M2: gap 70.1pp (flag YES)
- S_all M1s: gap 50.7pp (flag YES)
- S_all M2s: gap 62.7pp (flag YES)
- S_r12 M1: gap 58.7pp (flag YES)
- S_r12 M2: gap 60.8pp (flag YES)
- S_r12 M1s: gap 58.7pp (flag YES)
- S_r12 M2s: gap 52.8pp (flag YES)
- S_r3 M1: gap 33.2pp (flag YES)
- S_r3 M2: gap 72.7pp (flag YES)
- S_r3 M1s: gap 33.2pp (flag YES)
- S_r3 M2s: gap 70.2pp (flag YES)

## Sanity flip leg

- M1: {'correct': 15, 'n': 36, 'acc': 0.4167, 'ci95': (0.4167, 0.2714, 0.578)}, M2: {'correct': 21, 'n': 36, 'acc': 0.5833, 'ci95': (0.5833, 0.422, 0.7286)} (a healthy evaluator reads neither 0% nor 100% here)

## Discriminator non-regression

All four committed v3-beta AUC-table rows reproduced exactly after preference training; scorer artifacts sha256-pinned before/after (7 files).

## Red lines honoured

- zero certificate-grade reads by the ranker (grades appear only in the pool-quality warning composition)
- candidate pool reproduced with the viewer's gate-viability filter; round-3 fresh docs gate-viability validated field-by-field against the session registry
- deterministic output (double-run byte-identical); negatives library read-only; committed scorer artifacts sha-pinned; thresholds are named constants

