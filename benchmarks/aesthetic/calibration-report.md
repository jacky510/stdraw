# aesthetic_score v1 calibration report (shape-conditional)

Position: three-tier-funnel placeholder heuristic + measurement instrument only.
Final adjudication = Pareto + preference ranker (Phase 3). Certificate grading
(best/uncertified) never reads this score.

## Data

- anchors (positive): 10 — benchmarks/manual/* (11-06~11-20) incl. user-2026-11-20 + tests/data
- negatives: 40 — benchmarks/raw/aesthetic-v1-negatives (current engine auto recipe, re-run)
- **workbuddy workspace: zero reads (red line)**; the three 2026-11-20 anchors
  consumed in-repo after default@main a5a18fc
- WS4 archaeology (demos HTML 11-05~11-07): SKIPPED — demos at those commits contain
  rendered HTML only, no embedded layout-coordinate JSON (`git show 6d689a2:demos/`,
  grep '"x"' = 0); "unmodified by jacky" attribution not derivable from history alone.

## Shape-conditional routing (2026-11-20 directive)

- ① 族标签：单环→ring，多环耦合/链/星→hub；② 嵌套环与无标签图：先 hub 强度（hub_degree/n ≥ 0.75 → hub），再 degree_centroid_spearman（canvas 中心口径，≤0→ring，>0→hub）；③ ρ 退化→全局公式回退。已知局限：i00 仓内 fixture 实测 ρ=-0.53、hub 强度 0.5，按本路由入 ring，与 jacky 参考值（+0.59，测自本卡禁读的 WorkBuddy 侧副本）冲突——逐样本记录在 routing_log 待复核
- ring model excludes: ['alignment_max_coverage'] — operator 令：行/列对齐在环族天然低（brand-flywheel 33%），权重必须为 0
- global formula = fallback only (rho undefined / shape subset not fittable)

## New-feature sign verification vs jacky's hand measurements

| graph | expected | reference ρ | measured ρ | sign match | routed |
|---|---|---|---|---|---|
| random-n10-i05 | ring | -0.26 | -0.671545463 | True | ring |
| brand-flywheel | ring | -0.14 | -0.097590007 | True | ring |
| epidemic-feedback | ring | -0.24 | -0.107700688 | True | ring |
| classic-cld-growth-and-burden | hub | 0.4 | -0.536349916 | False | hub |
| random-n10-i00 | hub | 0.59 | -0.532632835 | False | ring |

## Headline (winning caliber: normalized — cross-canvas / cross-graph (normalized by canvas diagonal, RFC §15.2))

- ring: AUC=0.97479, separation=-15.5 (pos min 56.5 / neg max 72.0), n=7/17, excluded=['alignment_max_coverage']
- hub: AUC=1.0, separation=7.8 (pos min 68.8 / neg max 61.0), n=3/23, excluded=none
- global: AUC=0.9625, separation=-35.7 (pos min 34.5 / neg max 70.2), n=10/40, excluded=none
- LOSO (shape-conditional): ring min 50.8 / hub min None
- human lower bound (recomputed per shape): {'ring': 56.5, 'hub': 68.8, 'global': 34.5}
- fit sample counts recorded per shape in the model; weights/bounds MUST be re-derived
  whenever the anchor library grows — nothing here is a hardcoded constant.

## Caliber comparison (③)

| metric | absolute px | normalized |
|---|---|---|
| worst-shape AUC | 0.97479 | 0.97479 |
| worst-shape LOSO min | 12.6 | 50.8 |

- Spearman across calibers: negatives 0.8164, positives 0.9387
- cross-class ordering disagreements: 1 / 400 pairs; ranking-reversal observed: True
- domain declarations: absolute = same-canvas-family (~960px viewBox) only;
  normalized = cross-canvas (§15.2). Every score output carries its domain.

## Family separation (②, absolute caliber, post-routing)

| family | n_neg | neg max | pos shape | n_pos | pos min | separated |
|---|---|---|---|---|---|---|
| classic/单环 | 1 | 10.5 | 0 | None | False |
| classic/多环耦合 | 11 | 47.2 | 0 | None | False |
| classic/嵌套环 | 8 | 67.8 | 0 | None | False |
| hub | 0 | None | 3 | 72.3 | False |
| random-n10 | 20 | 70.9 | 0 | None | False |
| ring | 0 | None | 7 | 54.0 | False |

## LOSO per anchor (normalized)

| held-out | shape | score |
|---|---|---|
| brand-flywheel | ring | 82.7 |
| classic-cld-growth-and-burden | hub | None |
| fan-d12 | hub | None |
| fan-d17 | hub | None |
| random-n10-i00 | ring | 87.9 |
| random-n10-i05 | ring | 89.2 |
| random-n10-i05 | ring | 87.4 |
| random-n10-i11 | ring | 84.7 |
| random-n10-i11 | ring | 86.4 |
| epidemic-feedback | ring | 50.8 |

## i05 retest pair stability (11-16 fixture vs 11-20 redrag)

- absolute: 11-16=88.2 (ring) vs 11-20=88.2 (ring), |Δ|=0.0
- normalized: 11-16=89.3 (ring) vs 11-20=87.5 (ring), |Δ|=1.8
