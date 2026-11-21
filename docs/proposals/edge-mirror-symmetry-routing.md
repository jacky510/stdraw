# Proposal: mirror-edge-pair path symmetry in the layout engine

PROPOSAL ONLY — not implemented, needs operator sign-off. Scope, stage,
determinism, performance and large-graph degradation analysis per the
research card. Measurement context: `docs/edge-mirror-feature.md` +
`docs/edge-mirror-measurement.md`.

## What is proposed

Add an optional engine objective: **mirror edge pairs route symmetrically**.
Given the feature definition's primary mirror `sigma` (involutive
automorphism, y-preserving, fitted axis) and its edge pairs, routes are made
mirror images: the same anchor ids (mirrored), the same route kind, and a
point-mirrored polyline.

## Recommendation: route symmetrization as a deterministic post-pass, NOT a search objective

The engine does not run per-edge A* over a shared cost field; routing is a
deterministic stage-2 optimization loop (anchor presets + route selection)
after stage-1 placement (layering, rows, crossing-minimizing local search),
with CP-SAT as an optional refinement layer. Two possible integration
points:

### Option A (recommended): deterministic symmetrization post-pass at the END of stage 2 (M2-sized work)

1. After stage-2 routes are fixed, detect mirror candidates + pairs with the
   measured feature code (pure function, stdlib).
2. For each pair, take the LEFT side (smaller canonical endpoint id) as the
   master; recompute the right side as the exact mirror of the left:
   mirrored anchor ids (golden table), same route kind, polyline x-mirrored
   about the fitted axis `c`.
3. Re-run the existing post-route validity gates (box-over-line hard gate,
   clearance checks). If a mirrored route violates a gate, keep the
   original route for that pair and log the exception (never degrade a
   passing layout into a failing one).

- Determinism: pure copy + mirror of already-computed routes; canonical
  master selection; no search, no cost-field coupling. Byte-deterministic.
- Performance: O(pairs x route length) + one automorphism search bounded by
  the feature's state cap. Negligible at the engine's n<=20 scope (the
  measurement runs 58 graphs in ~1 s including 3 tolerance settings).
- Placement unchanged: stage 1 is NOT touched, so crossing/row quality
  metrics are unaffected; only route cosmetics change on mirror pairs.

### Option B (rejected for now): symmetry term inside the stage-2 search (M3-sized)

Adding "mirror agreement" as an objective inside the routing search couples
independent edge optimizations, risks non-deterministic tie spirals, costs
search time, and — per the measurement — buys almost no discriminative
signal (the engine ALREADY scores 1.00 consistency on 6/9 of its
mirror-bearing outputs; the pairs it fails on are exactly the asymmetric
placements that stage 1 produced). Not worth M3 budget.

Placement-side symmetry (making stage 1 produce symmetric layouts at all)
is a different, much larger feature (layout objective + neighborhood
changes = the M3 local-search territory) and is out of scope here.

## Determinism and pin impact (8777 / byte-pinned consumers)

- Default OFF. Ship behind `--mirror-symmetry` (opt-in) so every existing
  byte-pinned consumer (8777 STDRAW_PIN, frozen baselines, gate A
  byte-regression) sees ZERO drift until deliberately upgraded.
- When switching it on for a release: A-tier full 61-graph sweep must be
  re-rendered and any byte drift registered against the pin protocol
  (pin upgrades align with engine releases; the consumer re-pins in the
  same change). Graphs without mirror pairs are bit-identical by
  construction; classic-corpus grid layouts with incidental mirror pairs
  WILL drift and must be listed in the release notes.
- Mirrored-route gate exceptions (step 3) are logged in the certificate /
  routing log (fail-loud, same mechanism as the existing routing log).

## Large-graph degradation (8777 and beyond)

- The automorphism enumeration is the only super-linear step. With degree +
  y-preservation pruning and the state cap it is bounded; at the fleet hard
  scope (n <= 20) no graph truncated in measurement (58/58 under cap).
  Beyond n=20 the cap converts the feature into "best-effort within
  budget" — recommended: keep the hard n<=20 scope for the engine, and let
  any future large-graph line (stdraw20) adopt the post-pass only after its
  own truncation audit.
- Worst case for the post-pass itself is linear in edges; no CP-SAT or
  solver involvement; memory O(E).

## Sizing and sequencing (if approved)

1. Extract the feature code from the evidence script into a pure module
   (`stdraw/edgesymmetry.py`), unit-tested against the measured JSON.
2. Wire the post-pass behind the flag; gate A sweep; register drift.
3. Publishing-face freshness: if demos re-render changes, demos must be
   re-rendered per the freshness gate.
Estimated: small-to-medium M2 item (module + flag + sweep + docs), no
scorer changes.
