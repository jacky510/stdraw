# Offline A/B: M0-gate + anchor-similarity ranking (anchors-as-prior S3)

Evaluation set only (three merged rounds, zero new annotation, zero API cost). n=9 anchor subset is DIRECTIONAL ONLY; new topologies (0 decided pairs) carry no ordering claim; both-bad pairs are pool quality.

## Metric 1 - anchor recognition subset (9 asked pairs)

- committed M0 readings: OUT-OF-FOLD 4/7 tested (of the 9 asked; the primary committed caliber), full-calibration model 6/9 (in-sample for the 7 decided pairs, disclosed)
- NEW order ranks the human candidate first in 6/6 evaluable pairs
- NOT EVALUABLE (three-state, never 0): 3 pairs where the M0 gate ELIMINATED the engine candidate -- classic-cld-growth-and-burden|g5c0|r3e5g0c1 (engine r3e5g0c1 eliminated); nonplanar-credit|g2c0|r3e2g0c0 (engine r3e2g0c0 eliminated); brand-flywheel|g4c0|r3e4g0c0 (engine r3e4g0c0 eliminated). The gate itself is the stronger signal there (the engine counterpart fell below the committed epsilon), but the pairwise subset shrinks accordingly.

| pair_key | graph | human | engine | human_pos | engine_pos | human_first |
|---|---|---|---|---|---|---|
| classic-cld-growth-and-burden|g5c0|r3e5g0c1 | classic-cld-growth-and-burden | g5c0 | r3e5g0c1 | 4 | None | None |
| coupled-underinvestment|g1c0|r3e1g0c0 | coupled-underinvestment | g1c0 | r3e1g0c0 | 3 | 4 | True |
| comb-supply-demand|g3c0|r3e3g0c0 | comb-supply-demand | g3c0 | r3e3g0c0 | 0 | 6 | True |
| nonplanar-credit|g2c0|r3e2g0c0 | nonplanar-credit | g2c0 | r3e2g0c0 | 0 | None | None |
| comb-supply-demand|g3c0|r3e3g0c2 | comb-supply-demand | g3c0 | r3e3g0c2 | 0 | 4 | True |
| classic-cld-growth-and-burden|g5c0|r3e5g0c0 | classic-cld-growth-and-burden | g5c0 | r3e5g0c0 | 4 | 5 | True |
| classic-cld-growth-and-burden|g5c1|r3e5g0c0 | classic-cld-growth-and-burden | g5c1 | r3e5g0c0 | 0 | 5 | True |
| comb-supply-demand|g3c0|r3e3g0c1 | comb-supply-demand | g3c0 | r3e3g0c1 | 0 | 5 | True |
| brand-flywheel|g4c0|r3e4g0c0 | brand-flywheel | g4c0 | r3e4g0c0 | 0 | None | None |

## Metric 2 - pool-top anchor similarity (hit-family subset)

- hit graphs: 5; new top closer: 3; new top farther: 0; delta median: -0.265794

| graph | anchor | old top dist | new top dist |
|---|---|---|---|
| brand-flywheel | brand-flywheel | 0.34027 | 0.0 |
| classic-cld-growth-and-burden | retest-classic-cld | 0.265794 | 0.0 |
| comb-supply-demand | comb-supply-demand | 0.0 | 0.0 |
| coupled-underinvestment | nested-capacity | 0.435853 | 0.435853 |
| nonplanar-credit | nonplanar-credit | 0.520765 | 0.0 |

## Metric 3 - pool diversity (gate must not collapse the pool)

- min distinct-recipe coverage after the gate: 1
- COLLAPSE WATCH: nonplanar-credit keeps only 1 distinct recipe(s) after the gate -- flagged honestly, not hidden.
- pool sizes: {"brand-flywheel": 5, "chain-ring-hybrid": 4, "classic-cld-growth-and-burden": 7, "comb-supply-demand": 7, "coupled-underinvestment": 5, "dual-hub-asymmetric": 4, "nested-ring-shared-node": 4, "nonplanar-credit": 6}

## Metric 4 - gating cost

- eliminated by the M0 gate: 9 candidates total ({"brand-flywheel": 1, "chain-ring-hybrid": 0, "classic-cld-growth-and-burden": 1, "comb-supply-demand": 0, "coupled-underinvestment": 0, "dual-hub-asymmetric": 2, "nested-ring-shared-node": 0, "nonplanar-credit": 5})
- family-unmatched: 3 graphs (["chain-ring-hybrid", "dual-hub-asymmetric", "nested-ring-shared-node"])
- top-1 changed on 6 graphs

## Reading discipline

- n=9 DIRECTIONAL ONLY (CI discipline); no improvement claim
- zero decided pairs on the three round-3 topologies -> any ordering improvement there is NOT measurable and NOT claimed
- 29 both-bad pairs are pool quality; ranking cannot fix them; not claimed
- Scorer parity vs the committed FeatureBank caliber: True

