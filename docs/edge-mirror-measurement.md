# Edge-mirror feature: measurement report (18 manual anchors vs 40 engine negatives)

Research card deliverable (measurement only — no scorer/engine code changed).
Definition: `docs/edge-mirror-feature.md`. Raw data:
`kanban/evidence/<research-card>/edge-mirror-measurement.json` (untracked).

## Data and calibers

- Positives: the 18 manual anchors (v1 10 + batch-2 8), edge sets completed
  from graph sources / engine layouts BEFORE measurement (review MAJOR-1
  caliber), plus the user-modified edge subset measured separately (the
  edges the human actually touched in the export).
- Negatives: 40 engine auto-recipe outputs (`benchmarks/raw/aesthetic-v1-negatives`),
  full edge sets with routes and coordinate anchors.
- Anchor sub-calibers: golden (geometric slot mirror) and slot (ordinal
  attachment slot); see the definition doc.

## Headline numbers

Mirror presence (a geometry-valid mirror with >= 1 edge pair exists):

| population | presence |
|---|---|
| manual anchors | 8/18 = 44.4% |
| engine negatives | 9/40 = 22.5% |

Consistency among mirror pairs (golden caliber):

| population | mean | min | max | n |
|---|---|---|---|---|
| manual (primary mirror) | 0.769 | 0.50 | 1.00 | 8 |
| engine (primary mirror) | 0.778 | 0.00 | 1.00 | 9 |
| manual (best over candidates) | 0.769 | 0.50 | 1.00 | 8 |
| engine (best over candidates) | 0.778 | 0.00 | 1.00 | 9 |

Slot caliber: manual mean 0.738 (min 0.25), engine mean 0.778 — same shape.

Composite (no mirror counts as 0):

| population | mean | AUC (manual vs engine) |
|---|---|---|
| composite, golden | 0.342 | 0.610 |
| composite, slot | 0.328 | 0.608 |
| conditional consistency | — | 0.431 (worse than chance) |

Multi-quantile output (operator directive 2026-11-21: mean / sigma / worst /
P75 / P90 — a single bad edge must be exposed by the worst value; all
quantiles over the primary-mirror pair verdicts, golden caliber):

| level | population | n | mean | sigma | worst | P75 | P90 |
|---|---|---|---|---|---|---|---|
| pair-level (pooled) | manual | 36 | 0.750 | 0.433 | 0 | 1.00 | 1.00 |
| pair-level (pooled) | engine | 22 | 0.727 | 0.445 | 0 | 1.00 | 1.00 |
| graph-level | manual | 8 | 0.769 | 0.205 | 0.50 | 1.00 | 1.00 |
| graph-level | engine | 9 | 0.778 | 0.343 | 0.00 | 1.00 | 1.00 |

The pooled pair-level distributions are nearly identical (0.750 vs 0.727) —
the multi-quantile view strengthens, not weakens, the weak-verdict below.

Literature anchor (verified real): Klammler, Mchedlidze & Pak, "Aesthetic
Discrimination of Graph Layouts" (GD 2018; arXiv:1809.01017; JGAA 2019
extension, 97.58% discrimination). Its framework — abandon absolute
aesthetic metrics, perform pairwise discrimination of layouts of the SAME
graph — is the same-family measurement caliber as this card (same-graph
manual-vs-engine paired comparison). Its feature selection is the reference
point for the follow-up candidate list in
`docs/edge-feature-candidates.md`.

Design principle adopted with it (operator directive): edge-consistency
features must be TOPOLOGY-CONDITIONED — compare like with like (similar
direction classes, mirror structures, edges within one loop, spokes of one
hub); structurally necessary anchor differences (a hub connecting to nodes
in different directions necessarily uses different anchors) are NOT
inconsistencies; what should be penalized is unnecessary visual
inconsistency under similar structural conditions. The mirror-consistency
feature above is already conditioned on the strictest possible class
(mirror pairs under a verified automorphism) — and still does not
separate; that is evidence the conditioning principle alone will not rescue
consistency-style features, and future candidates need the weaker
conditioning classes (direction/loop/hub) measured before any are added to
the scorer. All future edge features must output normalized quantities
(relative to node size / canvas diagonal), never absolute screen pixels.

Tolerance sensitivity (mirror presence at SCALE_FRAC 0.35 / 0.50 / 0.75):
manual 8 / 8 / 8; engine 8 / 9 / 11 — the verdicts below do not hinge on the
tolerance choice.

## Per-anchor detail (positives, golden caliber)

| anchor | mirror | candidates | pairs | consistency | user-modified subset |
|---|---|---|---|---|---|
| fan-d12 | yes | 1 | 5 | 0.80 | 0.80 (5 pairs) |
| fan-d17 | yes | 1 | 8 | 0.75 | 0.75 (8) |
| bowtie-wage-price | yes | 1 | 4 | 1.00 | 1.00 (4) |
| comb-supply-demand | yes | 1 | 3 | 1.00 | 1.00 (2) |
| coupled-underinvestment | yes | 1 | 5 | 0.60 | 0.00 (2) |
| nested-capacity | yes | 1 | 3 | 1.00 | (no within-set pairs) |
| nested-learning | yes | 1 | 4 | 0.50 | 0.00 (2) |
| nonplanar-inventory | yes | 1 | 4 | 0.50 (slot: 0.25) | 0.50 (4) |
| 10 others (brand-flywheel, classic-cld, nonplanar-credit, retest-classic, random-n10-i00/i05 x2/i11 x2, epidemic-feedback) | no | 0 | — | — | — |

Engine negatives with mirrors (9): arms-race 1.0, burnout-attrition 0.0,
eroding-goals 1.0, fixes-that-fail 1.0, learning-flywheel 1.0,
shifting-the-burden 0.5, soil-erosion 0.5, urban-migration 1.0,
wage-price-spiral 1.0 — six of nine at 1.00, most with only 2 pairs.

## Verdict: weak discriminative power as a standalone feature

1. Presence is the only positive signal: 44.4% vs 22.5% (2x), but with
   n=18/40 it is far from separating (10/18 manual anchors have no mirror
   at all).
2. Conditional consistency does NOT separate: manual 0.769 vs engine 0.778;
   AUC 0.431 (worse than chance). Six of nine mirror-bearing engine
   negatives score a perfect 1.00.
3. Composite AUC 0.61 — below any usable single-key gate (the existing
   scorer's worst-shape AUCs are well above this).
4. Recommendation: do NOT add an edge-mirror key to the scorer (v3
   candidate rejected on measurement). If the aesthetic dimension is
   wanted in scoring at all, only `edge_mirror_presence` is defensible, as
   a low-weight supporting term — not as a gate.

### Why it fails (cause analysis)

- The engine's deterministic grid/row layout produces mirror-consistent
  anchors and routes as a BYPRODUCT on its few structural mirror pairs:
  when two nodes are placed symmetrically, the per-edge deterministic
  routing solves both sides identically, so anchor sectors, route kinds and
  mirrored paths agree (6/9 negatives at 1.00, mostly 2-pair graphs).
  Mirror consistency therefore measures "did a symmetric placement happen",
  not "did a human impose order" — the engine gets it for free exactly
  where it has a mirror at all.
- Manual anchors ARE highly consistent where a mirror exists (min 0.50):
  the human signal shows up as mirror PRESENCE (arranging the main shape
  symmetrically at all), not as extra pair consistency.
- Negatives' perfect scores ride on 2-pair graphs (small-n noise); a
  consistency mean over 2 pairs is 0/0.5/1 with no granularity.
- Export-format anchors carry no path data (supplemented edges are straight
  centre-to-centre), so the path dimension is effectively engine-only —
  the same format split already disclosed in the calibration report for
  bend-curvature features.

### User-modified edge subset (the "human intent" signal)

7 anchors have within-set pairs. Two readings:

- comb, bowtie, fan-d12/d17, nonplanar-inventory: 0.50–1.00 — where jacky
  arranges a symmetric shape, the touched edges carry mirrored anchors.
- coupled-underinvestment and nested-learning: 0.00 on the touched pairs
  (vs 0.60/0.50 on the full set) — the specific edges jacky re-anchored are
  exactly the ones breaking the mirror, i.e. hand overrides are local
  adjustments, not global symmetry enforcement. The subset confirms the
  full-set picture (weak, mixed signal) and adds no discriminative power.

## Threats to validity

- 18/40 samples; 8/9 mirror-bearing subsets. All differences except
  presence are within noise.
- Engine negatives are one recipe (auto-v2, current); a symmetric-placement
  recipe would change presence, not consistency.
- Path-mirror dimension is evaluable almost exclusively on negatives
  (format split) — it cannot be credited for any positive-sample separation.
- The golden/slot anchor sub-calibers disagree only on nonplanar-inventory
  (0.50 vs 0.25); jacky's actual group-anchor usage matches the golden
  reading on one pair and the slot reading on another, i.e. his own usage
  is not fully consistent under either reading. No separation consequence
  (engine negatives have no group anchors).
