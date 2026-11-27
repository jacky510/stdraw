# ADR index - owner rulings migrated from code annotations

One file per ruling; the original in-code annotations (with attribution) are preserved verbatim inside each file. Code sites carry the rule and a `docs/adr/ADR-XXXX` pointer.

- [ADR-0001-standard-anchors](ADR-0001-standard-anchors.md) - 16 standard anchors are the default endpoint attachment caliber (Accepted 2026-11-08 (verbal spec) / 2026-11-09 (default-caliber ruling))
- [ADR-0002-layout-aesthetics-v2](ADR-0002-layout-aesthetics-v2.md) - Layout aesthetics directive v2: explicit symmetry, patterned placement, spine-wing, whole-graph mode chain (Accepted 2026-11-05 / 2026-11-06)
- [ADR-0003-aesthetics-v3-bowtie-vertex](ADR-0003-aesthetics-v3-bowtie-vertex.md) - Layout aesthetics v3: bowtie-vertex symmetric placement (wage-price-spiral) (Accepted 2026-11-06)
- [ADR-0004-comb-bilateral-hdd-ground-truth](ADR-0004-comb-bilateral-hdd-ground-truth.md) - Comb-bilateral placement ground truth: hand-pulled HDD supply-chain layout (Accepted 2026-11-07)
- [ADR-0005-two-color-polarity-rendering](ADR-0005-two-color-polarity-rendering.md) - Edge coloring: two-color polarity rework (Accepted 2026-11-09)
- [ADR-0006-connection-point-accounting](ADR-0006-connection-point-accounting.md) - Connection-point accounting: fan spread, azimuth-monotone slot order, midband preference (Accepted 2026-11-06 (rule 3) / 2026-11-09 (slot-order rework); midband directive; second-review rejection)
- [ADR-0007-dense-mode-authorization](ADR-0007-dense-mode-authorization.md) - Dense-mode branch authorization (shared anchors, relaxed angle limits) (Accepted 2026-11-14)
- [ADR-0008-manual-certificate-caliber](ADR-0008-manual-certificate-caliber.md) - Manual-layout certificate caliber: structural gates N/A + waypoint endpoint rule (Accepted 2026-11-13 (P1-2); T2 plan A approved with the manual loop-closure card)
- [ADR-0009-reverse-form-gate](ADR-0009-reverse-form-gate.md) - Reverse-form gate: a detected-but-abandoned form degrades the certificate (Accepted 2026-11-15; widened 2026-11-16)
- [ADR-0010-manual-ground-truth-recalibration](ADR-0010-manual-ground-truth-recalibration.md) - Manual ground-truth recalibration: hand-drawn fixtures override uncalibrated thresholds (Ring battery v0.8.2; radial recalibrated 2026-11-15; anchor data packaged with the candidate-generation card)
- [ADR-0011-interactive-resilience-ux](ADR-0011-interactive-resilience-ux.md) - Interactive layer: fail-visible isolation, decluttered dots, endpoint hit-test and arc-freeze root fixes (Outage fixes v0.7.9 / v0.7.11; endpoint UX root fix 2026-11-12)
- [ADR-0012-planarization-degrade-contract](ADR-0012-planarization-degrade-contract.md) - Planarized 2D degrade ladder: D1 budgets, L1 exact default, honest fallbacks (Accepted 2026-11-14 (D1-D4))
- [ADR-0013-engine-scope-n20](ADR-0013-engine-scope-n20.md) - Engine capability scope: n <= 20 (Accepted 2026-11-14)
- [ADR-0014-gate-changes-owner-gated](ADR-0014-gate-changes-owner-gated.md) - Hard-gate thresholds and grade semantics change only with explicit owner authorization (Standing governance; restated with the gate-registry refactor)
- [ADR-0015-edge-placement-rules-v1](ADR-0015-edge-placement-rules-v1.md) - Edge placement rules v1: the pre-routing decision layer (Spec engineered from the owner's verbal spec (docs/edge-placement-rules-v1.md))
- [ADR-0016-ring-selection-key-frozen](ADR-0016-ring-selection-key-frozen.md) - Ring main-selection key frozen; reordering pending (S2-3) (Frozen since the WorkBuddy observability task 2026-11-11 (S2-1); S2-3 PENDING owner ruling)
- [ADR-0017-ui-theme-spec-a](ADR-0017-ui-theme-spec-a.md) - UI-A theme baseline: design tokens single source (Accepted 2026-11-11)
- [ADR-0018-2026-11-26-anchor-vocabulary-and-regularity-demotion](ADR-0018-2026-11-26-anchor-vocabulary-and-regularity-demotion.md) - 2026-11-26 batch: multi-slot anchor vocabulary + on-border/angle `anchors_standard` + fan slot swap (phi key) + n>10 regularity demotion to report items (Accepted 2026-11-26)
