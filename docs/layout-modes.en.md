# Layout Modes & Aesthetics Caliber

> English edition of [docs/layout-modes.md](layout-modes.md) (the Chinese
> original). Both editions describe the same engine; this document is
> self-contained. Engineering doc — maintained alongside `stdraw/layout_auto.py`
> and the per-mode modules it dispatches to.

> jacky's 2026-11-05 whole-corpus review set the top-priority design principles:
> "If box placement can be regular, make it regular — a vertical column, a
> circular loop. Lines should follow the boxes. Regularity makes diagrams
> prettier and easier to read." / "Loops should pull their boxes close to the
> loop's start, so the loop reads as a ring." / "Some line crossings are
> acceptable — order and beauty matter more."

## Mode selection (deterministic graph-theoretic metrics, highest priority first)

| Priority | Mode | Trigger | meta.placement |
|---|---|---|---|
| 1 | Bowtie symmetry (shared edge) | The core graph is exactly two triangles sharing one edge (4 nodes / 5 edges, degree sequence {3,3,2,2}, the degree-3 nodes adjacent) | `symmetric` |
| 1 | Bowtie-vertex symmetry (aesthetics v3) | Exactly 2 simple loops (length >= 3, canonical-form dedup), the two loops share exactly 1 node, and the loop union covers all non-isolated nodes (topologically mutually exclusive with the shared-edge bowtie: 5 nodes / 6 edges) | `bowtie-vertex` |
| 2 | Spine + wings (v0.7.1) | Hub pair (a directed edge whose endpoints share 3 <= W <= 4 common neighbors; ties: more declared-loop co-occurrence, then smaller canonical form) + a non-empty pairable rest cluster + spine length ratio <= 0.5 (see below) | `spine-wing` |
| 2 | Bilateral comb (v0.7.7, wide-card fan v0.7.8) | Exactly two non-adjacent hubs with identical neighborhoods equal to the shared source set S (\|S\| = m >= 3); remaining core nodes form pendant forests on S (one source per tree); the comb source column must be strictly longer than the best column spine to preempt column; the ring ratio branch refuses to enter when best k <= 4 and detect_comb hits (see below) | `comb-bilateral` |
| 3 | Column (long chain / few loops) | 3 <= n <= 12 ∧ longest simple loop 3 <= k <= 4 ∧ k < n (small main ring -> strong chain reading; k = n macro-loops go to ring; pure-cycle/ratio ring triggers do not enter column) | `column-chain` |
| 4 | Ring | Pure cycle / main-ring coverage >= n-2 / cycle-edge ratio >= 0.9 ∧ k >= 5 or full coverage | `ring-cycle` |
| 5 | Layered (existing path) | Everything else (chains / trees / large graphs) | `layered` |

Every new mode carries a **trial gate**: after constructing the placement, the
same router re-runs a hard-gate proxy (crossings <= 2, press = 0, clearance
>= 16, smooth anchors, mutual-pair separation, card gap >= 16). Any failure
**silently falls back** to the next priority — the fallback output is
byte-for-byte identical to the non-triggering path (negative examples are
byte-stable).

### Mode decision trace (ref-scrubbed)

The deterministic priority chain above is auditable: every auto layout records
a `mode_decision_trace` in `meta` (`layout.json`) and in the certificate
(`certificate.json`, same field name):

```json
"mode_decision_trace": {
  "engine": "spine-construct", "placement": "spine-wing", "manual": false,
  "rules": [
    {"tier": 1, "rule": "symmetric (shared-edge bowtie)", "triggered": false,
     "reason": "core n=8, edges m=13 (need exactly 4 core nodes / 5 edges)",
     "trial_gate": null},
    {"tier": 2, "rule": "spine-wing", "triggered": true,
     "reason": "hub pair rate->adopters with W=3 common neighbors, rest n=3 ...",
     "trial_gate": "pass"}],
  "fallback": {"used": false, "reason": null},
  "legacy_band_exemption": {"triggered": false, "detail": "spine-wing: 100% in-band enforced ..."}
}
```

- `rules` — one entry per priority-chain rule, in evaluation order, each with
  the measured structural facts that decided it (triggered / not evaluated /
  detected-but-preempted) and the trial-gate outcome (`pass` / `fail` / null).
- `fallback` — whether the layered path took over, and why.
- `legacy_band_exemption` — the registered v0.7.2 anchor-band baselines: the
  enhanced mid-band re-anchor + mutual-straight reroute channels are
  spine-wing only; every other engine keeps its registered baseline in-band
  ratio (CI `BASELINE_BAND` lock). The exemption is disclosed per figure
  instead of being silently applied.
- Manual layouts (`--from-layout`) bypass the chain: `manual: true`,
  `rules: []` — routing hard gates still apply, graded honestly.

### Column mode (column-chain)

- **Spine selection**: candidates = declared loops ∪ graph-enumerated cycles,
  chosen deterministically by "longest loop -> fewest negative edges
  (all-positive growth loops preferred as the spine) -> WL structural-color
  signature -> declared first -> canonical form"; start = the most
  structurally salient node (WL color -> degree), direction = the side with
  more directed-edge follows.
- **Placement**: spine nodes aligned in one central column (x = column axis,
  y = top + i·pitch); branches (residual nodes) hang on the spine's nearest
  side (right column preferred, groups placed whole); isolated nodes park in
  the top parking strip.
- **Spine closing edge** (last -> first): constructed as a **large left arc**
  (quadratic Bezier; ctrl solved so the t=0.5 bulge clears the leftmost
  obstacle by clear+4px; per-box verification uses check3's step=4 dense
  sampling — sparse sampling misses the high-curvature chord-tangent effect
  at arc ends).
- **Cross-row chord edges** (|row delta| >= 2): constructed as a **large right
  arc** (opposite the closing arc); if infeasible (chord collisions), fall
  back to the Router candidate pool.
- Certificate regularity gates: spine column-axis deviation <= 2px + uniform
  spine row pitch (branch half-row/whole-row offsets excluded); row alignment
  rate / column snap are inapplicable to column (honestly null).

### Spine + wings (spine-wing, v0.7.1)

> Ground truth: jacky hand-laid classic-cld-growth-and-burden (limits-to-growth
> x shifting-the-burden): the central spine adopters (top) / rate (bottom)
> strictly vertical on the canvas centerline (dx 1px); the left wings
> word/potential and the right cluster crowding hug the same horizontal
> midline (y exactly equal); quickfix upper-right / sideeffect lower-right
> near-mirrored (dx 6px); fundamental lower-right inside on rate's row. This
> mode hard-codes that "spine + midline wings" aesthetic as deterministic
> rules (`stdraw/spinewinglayout.py`).

- **Trigger** (deterministic topological metrics, all required):
  1. **Hub pair (spine)**: a directed edge whose endpoints share W common
     neighbors, 3 <= W <= 4 (ties: more declared-loop co-occurrence -> smaller
     canonical (u,v)). Classic CLD "rate -> adopters" diffusion hub pairs win
     naturally (classic-cld W=3; corpus max otherwise 2);
  2. **Wings** = the hub pair's common neighbors (each completing a 3-loop
     with the pair); the **rest cluster** (core nodes outside spine ∪ wings)
     is non-empty, <= 6, and all its adjacency stays within
     spine ∪ wings ∪ rest (no outsiders — double-axis constructibility;
     limits-to-growth shares the spine skeleton but rest = 0: a pure growth
     core, no trigger);
  3. **Spine length ratio** = |spine nodes| / |core nodes| <= 0.5 (compact hub
     pair; long-chain shapes go to column-chain);
  4. **Rest pairability** (mirror constructibility): pairs sharing a declared
     loop first (sample: quickfix/sideeffect both in R2), then restricted
     neighborhood keys; at most 1 leftover.
  - Priority-chain slot: bowtie-vertex -> **spine-wing** -> column ->
    ring-cycle; **pure simple rings still go to ring-cycle with zero drift**
    (pure-ring families have W <= 1 and never hit).
  - 19-figure corpus sweep (v0.7.1): only classic-cld-growth-and-burden hits;
    the three bowtie graphs have W=1, shared-edge bowties and the column
    family W <= 2, pure-ring family W <= 1 — all miss; the other 18
    layout.json files stay byte-identical to base 7378016.
- **Placement** (constructed constraints — calibrated against the hand-laid
  sample, not a global objective term):
  - Spine: the hub pair strictly vertical on the layout axis x=0, head at
    y=−Hs, tail at y=+Hs, Hs = 2·(card_h+GAP) = 160 (sample half-distance 160;
    head/target on top follows the sample's "causes grow upward" direction);
  - Midline wings: all wings on the y=0 horizontal band. The **anchor wing**
    (most adjacency to rest, sample: crowding) sits nearest on the right;
    remaining wings sorted (loop kind R<B<other -> canonical form) go left,
    inside-out (sample: word inside / potential outside);
  - Rest mirror pairs: shared-declared-loop pairs stack in one column at
    ±(card_h+GAP) = ±80 (sample ±82 idealized to 0px error); leftovers sit
    lower-right inside at y=+160 (rate's band, sample fundamental y=532 vs
    rate 534); all coordinates even (2px grid).
- **Routing**: spine edges are constructed vertical straight lines (top card's
  bottom-border midpoint -> bottom card's top-border midpoint, injected
  without the candidate pool); everything else goes through the same Router
  candidate pool (straight/arc first-class; mutual pairs crowding<->quickfix /
  crowding<->fundamental ride the Router mutual corridors >= 4px apart).
- **Trial gate**: reuses `_constructed_gates` (press / clearance / anchors /
  card gap / mutual separation / crossings <= 2); on failure, silent fallback,
  negatives byte-stable.
- **Certificate regularity gates (equivalent caliber)**: for the spine+wing
  shape, ring's "CV <= 0.05 / template fit <= 0.05" caliber becomes — **spine
  x alignment <= 2px + wing midline hug <= 2px + mirror-pair error <= 2px**
  (classic-cld measured 0px on all three; crossings are a reported soft
  target; determinism carried by byte-identical CLI double runs). The caliber
  switch applies only to classic-cld; the other ring figures remain
  zero-drift and regression-checked.
- Isomorphism: limits-to-growth shares the {rate, adopters, word, potential,
  crowding} sub-skeleton but rest = 0 — "growth core vs growth+burden whole
  graph" is separated naturally by the rest criterion.

### Bilateral comb (comb-bilateral, v0.7.7; wide-card fan v0.7.8)

> Ground truth = jacky's hand-drawn HDD supply chain (K_{5,2} + pendant):
> sources in one strictly coaxial column, dual hubs in mirrored slots at the
> column's middle row, all hub edges straight fan lines, in-column edges
> vertical.

- **Geometry**: sources + pendant in one column (x on-axis deviation 0),
  hub_y at the column's middle row, hubs mirrored about the column axis
  (center mirror error 0); hub_dx floor = max(200, (widest in-column card +
  hub card)/2 + 16 + 110).
- **Two fan tiers (v0.7.8)**:
  - **Tier-0 (narrow cards, v0.7.7 semantics unchanged)**: hub edges ride the
    router candidate pool's border_point anchors; the hub half-span widens in
    24px bracket steps (<= 16 steps) hunting a feasible window.
  - **Tier-1 (wide cards, 8777 dual-ticker class)**: for wide cards
    (hw >> hh) the center ray almost always anchors on the top/bottom border,
    and near-horizontal fan lines launched from a horizontal border always
    exit below 20° — wider brackets only flatten further. The clearance
    requirement and the anchor-angle requirement become mutually exclusive and
    the tier-0 window is always empty. Hub edges then switch to **constructed
    straight lines between facing vertical borders**: the center line's
    intersections with the two cards' facing vertical edges (band-clamped
    ±(hh−3), 2px grid), hub-side anchors in a fixed slot order spread by
    source row (>= FAN_SEP_MIN=8px — non-stacking plus order-preserving is
    the necessary-and-sufficient condition for pairwise non-crossing fan
    lines); the lines live in the empty corridors beside the column band
    (clearance holds structurally; near-horizontal lines exit a vertical
    border at ≈90°). Delivered via the constructed injection channel
    (kind=line, frozen out of coincide/midband/fan_spread); the trial gate
    re-runs the unified hard gates over the full edge set; meta.comb.fan
    = "facing-border". Only when both tiers exhaust does InfeasibleComb throw
    and the silent layered fallback take over.
- **Gate set (metrics/check/ci_checks share one caliber)**: column_axis <= 2px
  + constant column_pitch + hub center mirror <= 2px + hub_edges_straight +
  the generic hard gates; CV is a structural report item, not a gate.

### Bowtie-vertex symmetry (aesthetics v3)

> Ground truth: jacky hand-laid wage-price-spiral: shared node dead-center,
> the two rings' remaining nodes on four symmetric positions, the whole figure
> mirror-symmetric up/down/left/right — the v0.6.0 engine had misread it as
> column-chain; "topology should decide the layout". This mode hard-codes that
> aesthetic as deterministic rules.

- **Trigger**: enumerate undirected simple loops (length >= 3, canonical-form
  dedup) — **not declared loops** (the declared table mixes 2-node
  pseudo-loops and misses derived loops: #11 declares 2 / actual 3, #18
  declares 3 / actual 6); exactly 2 loops ∧ the node sets share exactly 1
  node ∧ the union = all non-isolated nodes (dangling nodes outside the rings
  -> conservatively no trigger). Corpus hits: {eroding-goals,
  shifting-the-burden, wage-price-spiral}. **No misfires**: figures 08/10/17
  also have exactly 2 simple loops but share 2 nodes (the shared-edge type) —
  the criterion excludes them naturally.
- **Placement**: the shared node at canvas center (layout axis x=y=0); each
  ring occupies one half-plane (first ring top / second ring bottom, order by
  kind R<B<other -> canonical); remaining ring nodes sit in the same
  half-plane's horizontal row at left/right mirror positions (same D, same H
  -> strict whole-figure mirroring, mirror-axis error gate <= 2px, measured
  0px). Left/right assignment = walk the ring from the shared node along
  directed-edge follows: successor left, next right (sample: wages left /
  cost right, real_income left / demand right).
- **Routing**: constructed all-straight injection (line-type consistency:
  outer edges horizontal straights + direct spokes). The corpus's 4 spokes are
  all mutual pairs (bidirectional) — a single constructed line would overlap
  point-for-point in both directions, so mutual corridors use ±12px parallel
  double lines (shared-side midpoint ± t spread, card-end anchors tangent
  along the owning border, horizontal borders paired "swap if crossing" to
  prevent flip-overs); the shared node's same-side double spokes spread
  symmetrically around the edge midpoint (never stacked on one point).
- **Certificate regularity gate**: mirror-axis error <= 2px (shared node on
  the axis + mirror pairs x-equal + y symmetric about the horizontal axis).
- Isomorphism: {eroding-goals, shifting-the-burden, wage-price-spiral} are
  digraph-isomorphic -> one layout template.

### Bowtie symmetry (symmetric)

- Shared-edge endpoints A (upper row) / B (lower row) on the vertical axis;
  the two vertices mirrored at left (−D) / right (+D) on the middle row —
  explicit geometric symmetry (the fix for #11 learning-flywheel "could be
  symmetric but sat off-axis").
- **Line-type consistency hard rule**: axis edge straight + all 4 side edges
  constructed as mirror arcs (no straight/arc/polyline mixing inside one
  symmetric structure); the trial gate additionally rejects any vg/poly
  polyline.
- Certificate regularity gate: mirror-axis error <= 2px (vertices equidistant
  from the axis + same row).
- Isomorphism: {learning-flywheel, fixes-that-fail} digraph-isomorphic -> one
  template.

### Isomorphic skeleton -> same layout template

Structurally identical graphs must produce structurally identical layouts
(readers recognize isomorphic textbook models as "the same figure").
Mechanism: spine selection and slot assignment are driven by **WL structural
color signatures** (2 refine rounds, independent of declared-loop id order);
isomorphic graphs' corresponding nodes share colors -> corresponding slots.
Verified corpus isomorphism groups:
- {eroding-goals, shifting-the-burden, wage-price-spiral} (digraph-isomorphic,
  all in bowtie-vertex since aesthetics v3);
- {fixes-that-fail, learning-flywheel} (digraph-isomorphic, all in
  shared-edge bowtie symmetry);
- {bullwhip, tragedy-of-the-commons} (undirected-isomorphic, all in the
  column isomorphic template).
Ties at automorphic (self-symmetric) positions break by id order —
geometrically equivalent (mirror images).

## R/B loop coloring (replaces letter badges)

- **Data**: every edge in `layout.json` carries `loop_kinds` (the kinds of
  declared loops it belongs to) and `loop_color`; the polarity data in
  `certificate.json` / `loops_audit.json` is unchanged.
- **Coloring (deterministic rules)**:
  - Edge in exactly one declared loop -> that loop kind's color: **R = amber
    `#d97706`, B = sky `#0284c7`** (hues aligned with the online convention
    `--am:#ffc94d / --bl:#7cc7ff`, darkened for white-background readability;
    black-and-white printing may ignore per jacky);
  - Edge in multiple loops of the same kind -> that color;
  - Edge in loops of different kinds (e.g. brand-flywheel's
    ad_effect->awareness in both R1+B1) -> **neutral gray `#64748b`** (siding
    with no loop);
  - Edge in no declared loop -> neutral gray.
- **Letter badges removed**: edges no longer render R/B letter badges (text
  clutter on complex graphs); negative-polarity edges are **dashed**
  (`stroke-dasharray="6 4"`), positive polarity solid.
- The interactive (drag) layer follows the same caliber: coloring/dashing are
  static stroke attributes preserved through drag re-routing.

## Line-kind hierarchy: arc > straight > polyline

- Candidate evaluation adds fixed type costs: `vg` (detour corners) +120,
  `poly` (lane polylines) +40, `wrap` (outer wrap-around) +200 — when a
  straight line or arc is feasible, a polyline no longer steals the score;
  **polylines are the last resort**.
- Line-kind consistency inside a symmetric structure (constructed guarantee:
  axis edge straight + side edges all arcs).
- Column spine closing edges / cross-row chords are constructed as large arcs
  (never in the polyline candidate pool).

## Line-to-box connection-point caliber (tightened 2026-11-06)

> "Overall it should look coordinated; the point where a line meets a box
> should prefer each edge's midpoint, never the corners."

- **Anchor caliber (`routing.border_point`, same source on the Python and JS
  sides)**: the ray picks the border (same edge as the old caliber) -> the
  anchor is clamped **along that edge's tangent into the midpoint ± 1/4
  edge-length band** — orthogonal exits hit the midpoint exactly, oblique
  exits get pulled back into the band; **corners are excluded entirely**
  (never a candidate, never a fallback; the hit count is always 0). The
  interactive (drag live-follow) layer uses the same caliber.
- **Constructed arc mapping**: symmetric arcs are first shaped at their
  natural anchors, then ctrl maps through the chord-coordinate transform
  (α chord ratio + β vertical offset) onto the clamped anchors — the arc's
  relative shape and exit tangent are preserved.
- **Non-stacking hard rule**: with >= 2 anchors on the same side of one node,
  `Router.fan_spread` sorts by incidence angle and spreads them symmetrically
  around the midpoint along the border tangent (18px steps, clamped inside
  the edge); after spreading, every edge is re-checked against the hard gates
  (press / clearance / anchor angle / crossing count non-increasing / mutual
  separation); a violating node rolls back wholesale. Mutual corridors (bowtie
  spokes) anchor as ±12px parallel double lines; same-side double spokes
  narrow to ±7px.
- **Acceptance caliber**: corpus-wide in-band anchor ratio (± 1/4 edge length),
  corner hits (= 0), exact-midpoint ratio — before/after statistics reported
  into the certificate.
- **CI anchor hard gate (v0.7.3 second-verification rework)**: corner hits = 0
  (all engines); per-figure in-band ratio >= its v0.7.2 baseline
  (tests/ci_checks.py `BASELINE_BAND` lock table), where spine-wing (this
  caliber's home domain) requires **100% in-band**. Registered baseline
  out-of-band leftovers: ring-cycle mutual pairs (brand-flywheel 87.5% /
  fishing-collapse 83.3%), bowtie-vertex ±12px spoke corridors
  (62.5%–66.7%) — fixing them moves the delivered dx shift and the 18-figure
  zero-drift hard gate, deferred to a later card. (Disclosed per figure in the
  certificate's `mode_decision_trace.legacy_band_exemption`.)
- **Delivery-layer three-stage clamping (`Router.midband_reanchor(enhanced=)`)**:
  stage 0 baseline caliber (v0.7.2 original semantics: clamp endpoints, ctrl
  untouched, deliver on success — the guarantee that the other 18 figures stay
  byte-identical) -> stage 1 enhanced stair (spine-wing only): ① arc ctrl
  translates with the anchor + Bezier re-parameterization (exit tangent
  preserved); ② stair stepping along the border toward the edge midpoint
  (4px/stage, capped at half-band); ③ the gate set adds an **own-box interior
  check** (`_edge_stats` counts only other boxes' press; after ctrl follows
  the anchor the tangent can dip into the own box — a measured classic-cld
  pit) -> backstop "in-band local re-route for mutual pairs"
  (`_reroute_pair_band`): in-band anchor candidates (`_band_candidates`:
  variant clamps recomputing line/arc on the new chord + both-side nested-arc
  escape gates + natural in-band corridor families) greedily picked over two
  passes, hard gates re-checked on the delivered caliber.
  **Constructed-arc mapping erratum**: v0.7.2's "ctrl chord-coordinate
  mapping" covered only constructed arcs; routed arcs' exit anchors were not
  clamped (root cause jacky flagged on second verification: classic-cld's
  symptoms-solution dashed line exited 3px from the corner while the in-band
  interval [635.5,708.5] measured out-of-band) — from this version the
  delivery-layer three-stage clamp covers all routed arcs.

## Arc curvature parameterization (aesthetics v3)

- **Adaptive bend coefficient `routing.adaptive_arc_k(chord)`**: bulge =
  min(6 + 0.06·chord, 40) px, k = 2·bulge/chord ∈ [0.12, 0.50] — short edges
  bend less, long edges cap (typical 130px chord -> k ≈ 0.21, matching the
  v0.6.0 look).
- The candidate arc's first tier IS the adaptive tier (the ARC_KS ladder is
  kept as a feasibility backstop, order-preserving dedupe).
- **Equal curvature within a loop**: constructed arcs of one symmetric
  structure (symmetric side arcs) all take the median-chord tier of the 4
  side chords — uniform curvature inside one structure; column closing arcs /
  chord arcs still solve for the clearance target (geometric necessity
  first).
- The JS drag layer's arc-follow delivers ctrl (arcFollow), same caliber as
  Python.

## Crossing caliber: soft target + honest reporting (since v0.6.0)

- `crossings_zero` is demoted from a hard gate to a **report item**
  (`certificate.reports.crossings_zero`): <= 2 crossings are allowed when
  placement regularity holds (order and beauty first).
- `row_align_ge_060` is likewise a report item (the 14 hand-laid samples
  measured row_align delta ≈ 0; users do not care; placement regularity is
  carried by "uniform row pitch + column snap / mode calibers").
- **Grade semantics unchanged**: best = all hard gates + 0 crossings; second =
  all hard gates + <= 2 crossings (details recorded in the certificate for
  review); uncertified = everything else. Placement-regularity classes
  (press / clearance / anchors / mode regularity gates) remain hard gates.

## Breathing room (spacing targets)

- Measured on the 14 hand-laid samples: min_card_gap averaged +35.8px (max
  +73) -> **card gap target 36px** (`layout_auto.GAP_TARGET`): column/symmetric
  placements lay out at 36px (SIDE_GAP/SYM_GAP); the layered path's polish
  objective adds a `8×max(0, 36−min card gap)` soft penalty (no hard gate; the
  existing >= 16 gate is the floor).
- Certificate report metrics added: `loop_cohesion_spread` (per declared loop,
  node spread / figure diagonal — smaller is tighter), `center_offset_x`
  (centering offset), `line_kind_counts` (line-kind distribution).

## Certificate mode calibers (metrics/check share one caliber)

| Mode | Regularity gates |
|---|---|
| ring-cycle | on-ring equal-spacing CV <= 0.05 + regular-polygon template fit <= 0.05 |
| spine-wing | spine x alignment <= 2px + wing midline hug <= 2px + mirror-pair error <= 2px |
| column-chain | spine column-axis deviation <= 2px + uniform spine row pitch |
| symmetric | mirror-axis error <= 2px |
| bowtie-vertex | mirror-axis error <= 2px (shared node on the axis + rings mirrored up/down) |
| layered | uniform row pitch + 24px column snap >= 60% (simple graphs) |

## Standard box anchor set (16 points, ref-scrubbed, interactive layer only)

- **Caliber**: each box gets 16 discrete standard connection points = 4 edge
  midpoints + 4 corners + 2 golden-ratio points (0.382/0.618) per edge = a
  16-point symmetric caliber (jacky's 2026-11-08 dictation "4 edge midpoints +
  4 corners + golden points", symmetrized per card; a single golden point per
  edge breaks symmetry — rejected). All 16 points sit on a rectangle **inset
  3px** from the border (reusing the fan slot's `half − 3` inset,
  `stdraw/anchors.py:ANCHOR_INSET`); corners never sit on the geometric corner
  tip (outside the rx=7 rounded corners); golden-point directions are fixed
  clockwise (g1 = 0.382, g2 = 0.618; top edge left->right, right edge
  top->bottom, bottom edge right->left, left edge bottom->top).
- **Source of truth**: `stdraw/anchors.py` (pure functions; the static
  layout/routing pipeline does NOT import it — the automatic anchor planning
  caliber is unchanged -> 21-input sweep byte-identical); the interactive
  layer's `_interactive_js.stdAnchors` mirrors the same formulas (live card
  geometry), probe-verified point-by-point JS vs Python (<= 0.02px).
- **Interactive semantics**: hovering a box shows the 16 anchors (toolbar
  toggle); edge endpoints (start + arrow end) drag individually and snap on
  release to the **owning box's** nearest standard anchor (ties take the
  earlier ANCHOR_IDS entry); clicking a visible anchor = explicit assignment
  (nearest-drop endpoint wins).
- **user-anchored reprojection**: after explicit assignment (drag snap / click
  / `__stdrawApplyLayout` `edge_anchors`), node drags only **reproject the
  endpoint onto the same anchor slot** (recomputed on live geometry) — no
  drift; exported layout's `edges[].anchors {src,dst}` follows the Export
  layout semantics (viewer replay; CLI `--from-layout` does not consume that
  key yet).

## Delivery-layer default snapping to the 16 standard anchors (ref-scrubbed, `Router.anchor_snap`)

jacky 2026-11-09: "the connection points are still not the 16 standard ones I
defined" — the 16-anchor caliber is upgraded from interactive-only to the
**default attachment caliber**: on the auto recipe every engine (constructed /
waypoint frozen edges included) must deliver every edge endpoint (start +
arrow end) on one of the owning box's 16 standard anchors; the certificate
gains the `anchors_standard` hard gate (membership tol 0.75px, in the grade
conjunction).

- **Algorithm path (gate-checked nearest-anchor assignment, not blind
  post-hoc snapping)**: (1) occupancy — endpoints already exactly on an
  anchor claim it per (box, anchor) (two endpoints never share one anchor
  point, so no V co-points); (2) per edge (deterministic order) each endpoint
  enumerates the 16 candidates **nearest first** (ties take the ANCHOR_IDS
  order) and a candidate is applied only if the full delivery hard-gate set
  holds: press no-worse / zero new crossings vs any other edge / clearance
  (CI-raw >= 16, i.e. router inflated >= 15) / departure angle >= 20 deg
  (router AND certificate-side classification must both pass — corner anchors
  can classify differently per side; population-logistic nw measured router
  50.2 deg vs certificate 0.0 deg) / mutual separation >= 4px / own-box arc
  intrusion no worse (6px attachment-zone sampling exemption, same source as
  metrics/check). (3) fixpoint sweeps (<= 4): earlier snaps update the shared
  geometry, later edges re-check against the **already-snapped state** —
  sequential-joint solving; the mover's own gates already counted its
  crossings.
- **Router-shape coupling**: straight endpoints move directly; arc endpoints
  snap + ctrl translates in lockstep then rescales around the new chord
  midpoint via `ARC_CTRL_SCALE_LADDER` (1.0 -> 0.45/1.6, detour side kept,
  gates re-checked — long tangent detour arcs such as bullwhip's east arc
  meet the departure-angle gate via this ladder); vg polyline endpoints +
  adjacent via translate together (first segment stays collinear, departure
  direction kept) + rigid fillet move + re-densification from corners +
  fillets; poly/wrap translate their vias the same way; waypoints move
  endpoints only (user vias untouched).
- **Relation to existing calibers**: the ±1/4 in-band ratio (ref-scrubbed /
  ref-scrubbed midpoint-preference proxy gate) is **superseded with cause** —
  ci_checks `BASELINE_BAND` lock table and the test_layout_modes band-ratio
  lock are re-baselined to the 16-anchor membership hard gate (in-band ratio
  stays as a report item; measured after snapping: classic-cld 18/26,
  brand-flywheel 8/16, urban-migration 8/16, limits-to-growth 9/14; classic
  corpus corner-anchor hits are constantly 0); fan_spread / midband_reanchor
  / mutual channels unchanged (they run first, anchor_snap finishes).
- **Validation (21-input sweep, per-graph before/after byte diff on the
  card)**: 21/21 crossings 0, grade best, visual_crossings_zero True,
  anchors_standard True, 0 off-anchor endpoints; deterministic (two runs
  byte-identical, ci_checks layer B).

### Density-threshold probe mode (ref-scrubbed closure, approved 2026-11-09)

Random dense sampling measured: n10-i05 (E/N = 1.60) fails three gates after
snapping — visual_crossings 2 -> 4 (2 fan pairs + 2 normal pairs), 1 endpoint
with no feasible anchor (N03->N08 poly), line-line coincidence. Meanwhile the
classic flagship classic-cld (E/N = 13/8 = 1.62) snaps clean across the
21-graph sweep, and the failing case's max degree (4) is LOWER than
classic-cld's (7) — **no static scalar density threshold can both pass
classic-cld and block random n10**. The landed caliber:

- **Threshold**: `ANCHOR_SNAP_DENSE_E_OVER_N = 1.6` (E/N >= 1.6, i.e. average
  degree >= 3.2) switches snap into **probe mode**; below the threshold the
  snap stays unconditional.
- **Probe**: run the full snap on a working copy, then re-evaluate three hard
  gates (plain crossing pairs via `final_crossing_pairs` / line-line
  coincidence pairs / endpoint anchor membership — any unanchored endpoint
  fails); **keep the snapped routes only at zero regressions, otherwise
  revert to the pre-snap routes as a whole** (invariant: a dense graph is
  either fully anchored or fully reverted — no half-snapped state).
- **Honest downgrade**: on revert the certificate records
  `gates.anchors_standard_deferred = {density_en, reason[],
  moved_before_revert}` and the `anchors_standard` gate **stays measured
  False** (no gate fudging, grade semantics untouched — deferred dense graphs
  honestly grade uncertified/second; this is exactly the downgrade path
  jacky approved); the layout meta always carries `anchor_snap_deferred`
  (null = snapped). Reverted routes skip the post-snap
  `mutual_arrival_flip(enhanced_gates=True)` (the pre-snap flip already ran;
  re-flipping unsnapped routes would perturb the honest pre-snap state).
- **ci_checks assertion (B2 random layer)**: a dense graph (E/N >= 1.6) must
  either pass the membership gate (probe kept) or carry a deferred record
  with a non-empty measured reason; a below-threshold graph may never carry
  a deferral (no downgrade excuse for sparse graphs).
- **Known limitation (follow-up card)**: fan-pair visual-crossing deltas are
  not yet part of the probe's regression set (measured n10-i05 reverts via
  the unanchored-endpoint trigger; a fan-only regression has not been
  observed) — the dense-snap specialization card (coincidence gate + chained
  crossing tracing) owns this.
### Joint lens anchor re-assignment (ref-scrubbed, restoring the <=10 deg arrival target)

The snap's MIRRORED golden-pair quantization gives some lens pairs a hard
chord-tilt floor: classic-cld crowding<->fundamental has a 24px box-center
offset, and the quantized anchor offsets (crowding +-10.6px / fundamental
+-16.5px) leave the mirror chords only dx = 24 +- 5.9px — the worst chord
tilt is atan(29.9/122) ~= 13.8 deg.  Arriving within 10 deg of the border
normal on BOTH ends requires the anchor horizontal offset
|dx| <= tan(10 deg) * H (H = the chord's vertical span ~= 122px here ->
21.4px); the 29.9px mirror chord exceeds that cone bound, the ctrl-only
re-fit bottoms out at ~11.5 deg per arc (14.4 deg delivered), and the
target is mathematically unreachable under that anchor assignment (the
basis of ref-scrubbed's honest 15 deg downgrade).

**Fix = widen the anchor-assignment space, not the ctrl search**: each arc
may take a NON-mirrored pair of facing-border anchors (ordered anchor pairs
per box, anchors claimed by other edges excluded); every candidate is
re-fit (lockstep ctrl translate + ARC_CTRL_SCALE_LADDER rescale), passes
the full delivery gate set (press / crossings / clearance / anchor angles /
own-box / sibling fan crossings / mid-band / mutual separation >= 12px),
then the post-snap `mutual_arrival_flip(enhanced_gates=True)` is simulated
to measure all four end deviations.  `Router.lens_joint_reassign` triggers
only for pairs the joint snap mirror-assigned AND whose simulated post-flip
state still exceeds `ARRIVAL_TARGET_DEG`; **the winning assignment is
applied only when ALL FOUR ends meet <= 10 deg** (marginal improvements
that still miss the target are rejected — measured on soil-erosion
crop_yield<->farming: enumeration best 21.69 deg vs delivered 21.82 deg,
bytes correctly untouched).  After application the caller's flip reproduces
the simulated final state exactly (this pass writes only the PRE-flip
ladder geometry).

- **classic-cld measured**: winning assignment = arc1
  (crowding->fundamental) takes (s-g2 +10.6px -> n 0px), arc2
  (fundamental->crowding) takes (n-g1 -16.5px -> s-g1 -10.6px); chord
  tilts 6.27 / 8.44 deg, four end deviations 2.8 / 6.8 / 0.9 / 8.9 deg
  (max 8.93 deg), mutual separation 16.5px, 14 checks fail=0, grade best,
  all hard gates green — the <= 10 deg target is RESTORED
  (test_mutual_lens_arrow_normal pins ARRIVAL_TARGET_DEG again; the
  15 deg anchor-caliber ceiling of ref-scrubbed is retired).
- **Byte impact**: the 21-figure classic sweep drifts on classic-cld ONLY
  (layout/certificate/demo-2d re-rendered with the engine, demos/
  freshness gate updated in the same batch); the other 20 figures are
  byte-identical (constructively excluded: pairs the flip already fixes
  are skipped at the simulation stage).
