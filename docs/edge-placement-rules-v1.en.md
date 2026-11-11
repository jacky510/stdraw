# stdraw Edge Placement Rules v1 (English edition)

> Canonical edition: [edge-placement-rules-v1.md](edge-placement-rules-v1.md)
> (Chinese, jacky's verbal spec engineered). This is the English companion
> per the repo's bilingual publishing-face convention; on any divergence the
> Chinese edition wins.

## 0. Purpose and principles

Move "which side + which anchor a line leaves a box from, and whether it is
drawn straight or as an arc" out of the post-routing repair passes into **one
rule table decided BEFORE routing**.

Principles: (1) anchors first, then lines; (2) replace, don't stack — the
repair passes this ruleset takes over are retired (§15); (3) hard gates are
not relaxed (zero crossings, no box press, clearance ≥ 16px); (4)
determinism — same input, byte-identical output; (5) unmet rules are
recorded honestly in the certificate, never silently dropped.

## 1. Terms

**Line kinds** (existing loop-coloring caliber): **R** reinforcing (edge only
in R loops), **B** balancing (only in B loops), **N** neutral (mixed / no
loop). Edge polarity (+/−) is NOT used for classification.

**Box sides & anchors**: 4 sides (n/e/s/w) × standard 16-anchor set
(`anchors.py`): edge midpoints, two golden-section points per edge (0.382 /
0.618), corners. All anchors sit 3px inside the border. **v1 uses midpoints
and golden points only** — corners stay reserved for manual designation.

**Usable anchors** (§1.3): on one side, two used anchors must be ≥
`SLOT_SEP_MIN` (10px) apart. With the real card size this gives the n/s sides
3 usable anchors (midpoint + two goldens) and the e/w sides only the
midpoint — computed per actual box size, never hard-coded.

**Adjacent vs remote**: adjacent = a straight line between the facing
midpoints touches no other box (after 16px clearance inflation); otherwise
remote. **Mutual pair** = A→B and B→A both exist.

## 2. Position in the pipeline

```text
node placement (existing, unchanged)
      ↓
【new】edge rules: per edge end -> side + anchor + line kind
      ↓
routing: adjacent boxes connect directly; remote boxes use the existing
visibility-graph routing, endpoints fixed at the assigned anchors
      ↓
retained checks and fallbacks (§15)
      ↓
certificate
```

## 3. Rules

1. **Side choice** (per end): |dy| ≥ |dx| → vertical sides (facing one);
   otherwise horizontal. Within 10% tie → the side group with more usable
   slots; still tied → vertical.
2. **Slot pattern** (per side, by line count/type mix): placement order
   R, N, B. Single non-B → midpoint, straight. Single B → a golden point,
   arc. 1 non-B + B(s) → non-B midpoint, B on goldens. 2/3 R → midpoint +
   golden points (all straight — golden points ARE the "secondary slots",
   decision D1-A). Capacity overflow spills (rule 6).
3. **Line kind**: R/N straight, B arc (`adaptive_arc_k` curvature). The arc
   bulges AWAY from the midpoint line (or, when no midpoint line exists,
   away from the center-to-center line).
4. **B golden-pair choice**: pick the pair whose arc vertex (t = 0.5) has
   the LARGER perpendicular distance to the midpoint line (far side, rule 9
   mirror pairing keeps both ends on the same global side). Near side only
   as an audited rule-4 violation. Ties (< 0.5px) → rule 10.
5. **On-side order matches target-direction order** (left-to-right along
   the edge = left-to-right of the targets). Order wins over the type
   pattern; a yielding R records a rule-5 violation.
6. **Spill**: overflow moves to ADJACENT sides only, never the opposite
   side. B leaves first, then N, then R; the adjacent side's NEAR-side
   golden point first, then the adjacent midpoint, chosen by target
   direction.
7. **Remote boxes**: endpoints still follow rules 1–6; the middle path is
   the existing visibility-graph router, unchanged.
8. **Mutual pairs**: mixed non-B + B → straight midpoint + arc golden
   (rule 4 side). Same-type pairs keep the lens double-arc (D2-A): midpoint
   chord + golden chord, each bulging away from the other's chord.
9. **Both ends together**: the two ends of one line are assigned jointly;
   the golden-pair mirror mapping keeps B chords parallel to the midpoint
   line.
10. **Determinism**: every tie falls back to `ANCHOR_IDS` index order, then
   the (source, target) id lexicographic order.

## 4. Priority order (lexicographic)

1. zero crossings (hard gate) · 2. no box press, clearance ≥ 16px · 3.
on-side anchor spacing ≥ 10px · 4. correct line kinds · 5. on-side order ·
6. B far side · 7. midpoint priority (R/N) · 8. load balance · 9. rule-10
tie-breaks.

## 5. Algorithm (deterministic)

Classify kinds → compute usable slots → choose sides (rule 1) → spill
overflow (rule 6) → per-side slot pattern (rules 2/5) → resolve symbolic
goldens (rules 4/9) → line kinds and bulge sides (rules 3/8) → route →
audit delivery (§6) → bounded local re-enumeration (≤ 3 rounds) for edges
still involved in crossings (spec §5 step 7). Per-side enumeration is ≤ 6
arrangements; total cost is negligible.

## 6. Certificate

`certificate.json` / `layout.json meta` gain an `edge_rules` block:
`{version: "v1", edges_total, violations[], overflow_to_adjacent_side,
lens_pairs}`. **Rule violations are recorded, not graded** (D4-A): grade
logic is unchanged, so re-bless grade changes come purely from geometry.

## 7–12. Anchors, taken-over passes, examples, engineering, decisions

- Endpoints land only on standard anchors → the `anchors_standard` gate
  passes by construction (still measured honestly on delivered bytes).
- Taken-over repair passes on the auto path (see the Chinese edition §15
  for the full table): `fan_spread`, `anchor_snap`, `midband_reanchor`,
  `lens_joint_reassign`, `mutual_straight_reroute` and the post-snap
  enhanced arrival flip are retired; `coincide_reroute` and the legacy
  `mutual_arrival_flip` stay as fallbacks; `joint_reroute` lives inside the
  bounded re-enumeration channel. Repair passes on the auto path: 3 ≤ 4 ✓.
  The manual path keeps the full legacy pipeline (user authority over
  endpoints).
- **Scope (measured ruling)**: v1 governs the LAYERED engine path only
  (placement engines `cp-sat` / `construct`).  The constructed placement
  engines (ring / column / comb / spine-wing / symmetric / bowtie-vertex)
  deliver their own disciplined geometry with registered anchor calibers
  locked by CI — measured: generic presets there dropped 18/19 classic
  images to uncertified.  They are exempt in v1, byte-identical behavior;
  extending rules 1–6 to them is a v2 question.
- §9 paper-walk examples (vertical/horizontal mutual R+B, 3×R fan, 2R+2B
  spill, neutral lines) are all pinned in `tests/test_edge_rules_v1.py`.
- Decisions D1–D4 all resolved **A** (see the Chinese edition §13).

## Implementation mapping

`stdraw/edgerules.py` (pure-function decision layer) + `Router(presets=…)`
candidate channel (rule geometry first, honest fixed penalties 25/60 for
bending off the rule, vg/lane fallbacks from the fixed endpoints) +
`layout_auto` wiring (auto path only). See the Chinese edition §14 for the
line-by-line mapping from jacky's verbal rules to code.
