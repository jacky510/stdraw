# Edge-aggregate feature candidates (post-external-review merge)

Status: candidate list only — nothing here is wired into the scorer.
Origin: operator-merged list (2026-11-21) from the external review's eight
edge-aggregate feature proposals, deduplicated against this research line's
mirror-consistency definition, plus the adopted design principles and the
literature anchor.

Literature anchor (verified real): Klammler, Mchedlidze & Pak, "Aesthetic
Discrimination of Graph Layouts", GD 2018, arXiv:1809.01017, JGAA 2019
extension (97.58% pairwise discrimination). Framework adopted: no absolute
aesthetic thresholds; pairwise discrimination of layouts of the SAME graph
(manual vs engine outputs of one corpus graph), which is exactly the
caliber used in the mirror measurement
(`docs/edge-mirror-measurement.md`).

## Non-negotiable design rules for every candidate

1. **Topology-conditioned comparison.** Every consistency-style feature
   compares edges only within a conditioning class: mirror pairs (verified
   automorphism), similar-direction classes, edges of one loop, spokes of
   one hub. Structurally NECESSARY differences (a hub connecting to nodes
   in different directions must use different anchors) are never
   inconsistencies. Penalty targets unnecessary visual inconsistency under
   similar structural conditions.
2. **Normalized units only.** Distances relative to node size or canvas
   diagonal; angles as-is; never absolute screen pixels as a feature.
3. **Multi-quantile output per feature**: mean, sigma, worst, P75, P90 —
   one bad edge must be exposed by the worst value, not averaged away.
4. **Pairwise-discrimination validation** (same-graph manual vs engine)
   before any key enters the scorer; single-key AUC and worst-shape
   separation reported honestly (see the mirror precedent: presence-only
   2x, conditional consistency AUC 0.431 — rejected).

## Deduplicated candidate list

| # | candidate | conditioning class | measures | relation to mirror work |
|---|---|---|---|---|
| 1 | Mirror Consistency | verified mirror pairs (automorphism) | anchor/style/path agreement of mirror edge pairs | DEFINED + MEASURED this research line — weak standalone (do not gate); machinery (mirror search, anchor normalization tables, direction-aligned comparison, path mirror distance) is reusable by #2/#3/#8 |
| 2 | Anchor Consistency | edges with similar relative direction (per endpoint: out-direction class x in-direction class) | whether edges in the same structural situation choose the same anchor sector | generalizes the mirror anchor comparison; sector vocabulary reusable; must exclude structurally necessary differences via the direction class |
| 3 | Routing Regularity | edge class (straight/arc/poly, loop vs chain) | polyline regularity: angle uniformity, bend count, symmetry of bends | path-mirror distance machinery reusable for bend comparison |
| 4 | Edge Direction Harmony | whole graph or per region | dominance of orientation classes (H/V/diagonal), deviation histogram | new measurement; trivially normalized (angles) |
| 5 | Loop Closure Quality | edges of one feedback loop (loop tags exist in DSL) | closure shape: does the loop close without bows; bend budget per loop | new measurement; loop membership is a natural conditioning class |
| 6 | Edge Visual Clutter | whole graph | crossings, box-over-line, edge-edge min distance, length distribution — all normalized | overlaps with existing certificate metrics (crossings, clearance already tracked); feature = normalized aggregation, not a new geometry engine |
| 7 | Port Distribution | per node side, conditioned on node degree | anchor slot occupancy balance around each card (no pile-up on one side when alternatives exist) | anchor table + nearest-anchor machinery reusable |
| 8 | Style Consistency | graph-level and per edge class | style-class uniformity (auto/straight/arc/free vs engine route kinds) | style comparison code reusable; already logged as DATA in scorer v2 (coverage 8/18 < MIN_COVERAGE then — re-check coverage before any key) |

## Sequencing recommendation

1. Measure cheap, high-signal candidates first on the existing 18+40
   corpus with the same pairwise-discrimination caliber: #4 (direction
   harmony) and #8 (style consistency, coverage permitting), then #2
   (anchor consistency — highest engineering reuse from this card).
2. Only candidates clearing an honest AUC/worst-shape bar become v3 key
   proposals; everything else is reported as data, not keys (the v2
   precedent: style/anchors logged as data because coverage gated them out).
3. Mirror Consistency stays: presence as at most a low-weight supporting
   term; the definition doc remains the reference for mirror-pair
   machinery.
