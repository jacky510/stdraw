# aesthetic_score v1 calibration report (shape-conditional)

Position: three-tier-funnel placeholder heuristic + measurement instrument only.
Final adjudication = Pareto + preference ranker (Phase 3). Certificate grading
(best/uncertified) never reads this score.

## Data

- anchors (positive): 10 — benchmarks/manual/* (11-06~11-20) incl. user-2026-11-20 + tests/data
- negatives: 40 — benchmarks/raw/aesthetic-v1-negatives (current engine auto recipe, re-run)
- **workbuddy workspace: zero reads (red line)**; the three 2026-11-20 anchors
  consumed in-repo after default@main a5a18fc
- edge-set caliber (review MAJOR-1 fix): manual 'Export layout' JSONs carry only
  the edges the user touched; every anchor edge set is completed from the graph
  source BEFORE any feature is measured (per-anchor log: edge_supplement_log in
  calibration-report.json)
- measurement-validity note (review MINOR-4): 9/10 anchors are 'Export layout'
  products (appended edges are straight centre-to-centre lines, no fold points)
  and 1 is a --from-layout CLI product (full edges + engine routing) — bend-
  curvature features are structurally 0 for the export-format anchors, so part
  of their discriminative power comes from the format split, not hand skill
- WS4 archaeology (demos HTML 11-05~11-07): SKIPPED — at 6d689a2 demos/ contained
  only the classic-cld figure (4 files), so the ~20 unmodified-delivery samples
  were never in demos/; their coordinates are retrievable from benchmarks/raw/
  (751 method-tagged JSONs at that commit, measured on this tree) but those are
  not human artifacts — 'unmodified by jacky = endorsement' cannot be derived
  from git history.  Recoverable as data; untrustworthy as human positives;
  excluded from the anchor library.

## Shape-conditional routing (2026-11-20 directive)

- ① 族标签：单环→ring，多环耦合/链/星→hub；② 嵌套环与无标签图：先 hub 强度（hub_degree/n ≥ 0.75 → hub；推导式=阈值适用人群中实测空档 [0.70, 0.80] 的中点；实测强度 induced-demand 0.80 / classic-cld 0.875 落在空档上沿，另一空档 [0.80, 0.875] 中点 0.8375 经对照实测（AUC/LOSO 全维劣于 0.75）弃选），再 degree_canvas_spearman（canvas 中心口径，≤0→ring，>0→hub）；③ ρ 退化→全局公式回退。锚点边集在测特征前已按图源补全；jacky 参考值测自仓外副本，仓内数据不可复现（270 组合搜索 0 命中）——路由只依仓内实测值，逐样本记录在 routing_log 待复核
- hub-intensity threshold derivation: DERIVED = midpoint of the measured empty
  gap [0.70, 0.80] over the threshold-eligible (unlabeled/nested) population
  (measured intensities: induced-demand 0.80, classic-cld 0.875 sit right above
  the gap; the other gap [0.80, 0.875] midpoint 0.8375 was measured worse on
  AUC/LOSO in the counterfactual refit and rejected); re-derived whenever the
  corpus grows (review MINOR-3, re-measured on a real run after review MAJOR-3)
- ring model excludes: ['alignment_max_coverage'] — operator 令：行/列对齐在环族天然低（brand-flywheel 33%），权重必须为 0
- global formula = fallback only (rho undefined / shape subset not fittable)

## Reference-vs-measured rho (NOT a sign check — see note)

The operator's hand-measured reference values were taken on an out-of-repo copy
and are NOT reproducible from in-repo data (independent review: 270-combination
search, 0 hits).  The table documents the discrepancy; routing uses the in-repo
supplemented-edge measurement only.

| graph | expected | reference ρ | measured ρ (in-repo) | sign match | routed |
|---|---|---|---|---|---|
| random-n10-i05 | ring | -0.26 | 0.190128171 | False | hub |
| brand-flywheel | ring | -0.14 | 0.15430335 | False | hub |
| epidemic-feedback | ring | -0.24 | -0.107700688 | True | ring |
| classic-cld-growth-and-burden | hub | 0.4 | -0.536349916 | False | hub |
| random-n10-i00 | hub | 0.59 | -0.56445967 | False | ring |

## Headline (winning caliber: normalized — cross-canvas / cross-graph (normalized by canvas diagonal, RFC §15.2))

- ring: AUC=0.976471, separation=-6.9 (pos min 49.9 / neg max 56.8), n=5/17, excluded=['alignment_max_coverage']
  - HONESTY NOTE: ring positives do NOT fully separate from negatives under the supplemented-edge caliber (separation <= 0) — this is the honest state of the model, no threshold was tuned to mask it
- hub: AUC=0.973913, separation=-9.2 (pos min 67.8 / neg max 77.0), n=5/23, excluded=none
  - HONESTY NOTE: hub positives do NOT fully separate from negatives under the supplemented-edge caliber (separation <= 0) — this is the honest state of the model, no threshold was tuned to mask it
- global: AUC=0.955, separation=-47.1 (pos min 36.1 / neg max 83.2), n=10/40, excluded=none
  - HONESTY NOTE: global positives do NOT fully separate from negatives under the supplemented-edge caliber (separation <= 0) — this is the honest state of the model, no threshold was tuned to mask it
- LOSO (shape-conditional): ring min 17.3 / hub min 57.9
- human lower bound (recomputed per shape): {'ring': 49.9, 'hub': 67.8, 'global': 36.1}
- fit sample counts recorded per shape in the model; weights/bounds MUST be re-derived
  whenever the anchor library grows — nothing here is a hardcoded constant.

## Caliber comparison (③)

| metric | absolute px | normalized |
|---|---|---|
| worst-shape AUC | 0.964706 | 0.973913 |
| worst-shape LOSO min | 1.3 | 17.3 |

- Spearman across calibers: negatives 0.9957, positives 0.9878
- cross-class ordering disagreements: 2 / 400 pairs; ranking-reversal observed: True
- domain declarations: absolute = same-canvas-family (~960px viewBox) only;
  normalized = cross-canvas (§15.2). Every score output carries its domain.

## Family separation (②, normalized caliber — cross-canvas domain, post-routing)

Computed under the normalized caliber (px / canvas diagonal): the table crosses
4 canvas families, which is outside the absolute caliber's declared domain
(review MINOR-2).

| family | n_neg | neg max | pos shape | n_pos | pos min | separated |
|---|---|---|---|---|---|---|
| classic/单环 | 1 | 23.1 | 0 | None | False |
| classic/多环耦合 | 11 | 46.4 | 0 | None | False |
| classic/嵌套环 | 8 | 77.0 | 0 | None | False |
| hub | 0 | None | 5 | 67.8 | False |
| random-n10 | 20 | 68.7 | 0 | None | False |
| ring | 0 | None | 5 | 49.9 | False |

## LOSO per anchor (normalized)

| held-out | shape | score |
|---|---|---|
| brand-flywheel | hub | 57.9 |
| classic-cld-growth-and-burden | hub | 81.5 |
| fan-d12 | hub | 62.4 |
| fan-d17 | hub | 79.8 |
| random-n10-i00 | ring | 63.4 |
| random-n10-i05 | hub | 58.0 |
| random-n10-i05 | ring | 87.2 |
| random-n10-i11 | ring | 84.7 |
| random-n10-i11 | ring | 86.3 |
| epidemic-feedback | ring | 17.3 |

## i05 retest pair stability (11-16 fixture vs 11-20 redrag)

- absolute: 11-16=79.2 (hub) vs 11-20=94.0 (ring), |Δ|=14.8
- normalized: 11-16=79.2 (hub) vs 11-20=94.0 (ring), |Δ|=14.8
