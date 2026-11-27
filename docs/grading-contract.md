# Grading Contract — single source of truth

This document is the **single source of truth** for stdraw's quality-grade
semantics. Hosts (CI pipelines, agent integrators) should link here instead
of copying grade tables into their own docs. The docs-consistency gate
(`scripts/check_docs_consistency.py`) verifies that the user-facing surfaces
(README.md / README_zh-CN.md / AGENTS.md / skills/stdraw/SKILL.md) stay in
sync with this contract.

Canonical facts are the CODE, never the prose:
- v2 grading: `certificate_auto()` in `stdraw/metrics.py` (caliber
  `v2-hardgates`, recipe `auto-v2`);
- v1 grading: **retired** — the `certificate()` function (caliber
  `v1-legacy`, recipe `ortho-v1`) was removed by owner ruling, 2026-11-24,
  together with the ortho recipe's external entry (CLI `--recipe ortho`,
  `recipes.ortho_v1()`). Historical v1-legacy certificates (archived
  benchmark evidence, prior deliverables) keep their fields and are read
  back under the rules in this document.

## 1. Grade tokens (what `certificate.json.grade` can contain)

| caliber | recipe | tokens emitted by the 2D pipeline |
|---|---|---|
| `v2-hardgates` | `auto-v2` | `best`, `crossed-certified` (planarized L1 only), `uncertified` |
| `v1-legacy` (**retired**, historical read-back only) | `ortho-v1` (**entry removed** 2026-11-24) | historically `best`, `uncertified`, `second` — no new v1 certificates can be produced |

`3d` is a **retired documentation-level tier**: it described the 3D delivery
path (a separate layout3d / render3d module pair and its CLI flags), removed
from the engine after v0.9.0. It never appeared as a value of the 2D
`certificate.json.grade` field; the token is kept in the read-back set only so
historical certificates still validate.

`second` is **v1-legacy only**: it was removed from the v2 implementation in
v0.7.15+ (logically unreachable), and the v1 grading code that still carried
it was deleted on 2026-11-24 with the ortho entry removal. No document may
present `second` as a current tier; existing certificates bearing it are
historical artifacts.

## 2. The calibers are different rulers (v1 kept for historical read-back)

Historical v1-legacy certificates could also emit `grade: "best"`, but the
token meant something different there. Current certificates self-describe
(fields are additive; consumers read `caliber` **before** interpreting
`grade`):

| field | v2-hardgates (auto-v2, current) | v1-legacy (historical artifacts only) |
|---|---|---|
| `recipe` | `auto-v2` | `ortho-v1` |
| `caliber` | `v2-hardgates` | `v1-legacy` |
| `placement` | placement mode (ring-cycle / spine-wing / ...) | `ortho-v1` |
| `grade_semantics` | grading formula, in the certificate | grading formula, in the certificate |
| `blocking_gates` | list of `false` gate keys | list of `false` gate keys |
| `deliverable` | reflects the delivery contract (CLI full deliverable: `true`) | always `false` (see §4) |
| `blocked_reason` / `blocked_by` | absent | set (`D0`) |
| gate count at `best` | 11+ hard gates (placement-specific; n ≤ 10) — n > 10 figures carry fewer: the §3.3 demotion removes the three mechanical-grid regularity slots; manual (`--from-layout`) figures carry one fewer than n ≤ 10: the §3.4 demotion removes `cv_le_035` | 4 legacy gates |

Grading formulas:

- **v2-hardgates**: `best` = 0 line crossings AND all placement-specific
  hard gates AND `anchors_standard` AND `visual_crossings_zero` AND dual
  crossing accounting; everything else is `uncertified` (honest no-grade).
  `anchors_standard` criterion (jacky 2026-11-26, multi-slot anchor
  vocabulary change): every delivered endpoint sits ON its box border
  (<= 0.75px) AND its departure/arrival angle meets the anchor-angle
  floor -- the legacy "endpoint ∈ its box's 16-anchor set" membership
  requirement was retired (W9 evaluation: it blocked ~80% of manually
  calibrated figures whose human g-slot endpoints sit off the 16-point
  set).  No threshold was loosened: both legs reuse the pre-existing
  on-border and anchors_smooth accounting.
- **v1-legacy (historical)**: `best` = 0 crossings AND min card gap >= 16
  AND spacing CV <= 0.35; `second` (legacy) = placement ok AND <= 2
  crossings; else `uncertified`. The code behind this formula is gone;
  this row exists so archived certificates still read back correctly.

Host rule: **read `caliber` first, then `grade`.** A historical v1 `best`
and a v2 `best` are not interchangeable claims; and a v1 output is never a
deliverable at all (§4).

## 3. Soft targets vs certificate gates (the caliber split)

"Crossings <= 2 acceptable" and "row alignment" describe the **layout
objective function** (report items / soft targets: when placement
regularity holds, <= 2 crossings may be tolerated — order and elegance
first). They are **not** certificate gates: the certificate-level `best`
requires 0 crossings (and, in v2, `visual_crossings_zero` as a hard gate).
A figure laid out under the soft
target regime with 1-2 crossings is correctly `uncertified` — that is an
honest result, not a bug, and thresholds must never be tuned to change it.

### 3.1 Manual coordinates — automatic-pipeline structural checks are N/A

Under `--from-layout` (manual coordinates), two layered-mode certificate
gates — `pitch_uniform` and `column_snap24_ge_060` — read the string
`"N/A"` instead of a measured boolean (jacky's ruling of 2026-11-13;
same caliber as the geometry self-check in `check.py` items 6a/9,
"manual: N/A"). Uniform card pitch and 24px column snapping are
properties of the automatic pipeline's placement, not of a human-drawn
arrangement; grading a hand layout `false` on them measured nothing.

Consequently:

- the `N/A` slots are excluded from `gates_passed` (a clean manual layout
  reads e.g. `10/10`) and can never appear in `blocking_gates`;
- this is a **caliber alignment, not a threshold change**: the measured
  values stay in `metrics` (`column_snap24_rate`, …), every other gate is
  untouched, and the AUTO path keeps boolean gate values;
- a manual layout still earns `best` only through the full remaining hard
  gates + 0 crossings under both crossing calibers.

### 3.2 Planarized non-planar graphs — the L1/L2 degrade ladder

Non-planar cores (after degree 0/1 safe reduction) follow the degrade
ladder of `docs/planarization-degrade-contract.md` (@ 4e0cdec):

- **L1** (planarization + witness drawing within CAP=min(3n,80) /
  deterministic operation budgets): the drawing is a straight-line planar
  drawing of the planarized graph H; every crossing sits on a
  planarization witness and is rendered as a small marker. New hard
  gates: `crossings_witnessed` (every geometric crossing maps to a
  witness, counts equal) replaces `visual_crossings_zero`, and
  `three_account_consistent` (geometric recount == witness count ==
  oracle cr UB) is required. Anchor/row-column regularity gates read
  `"N/A"` (inapplicable to the straight-line planarized drawing, same
  N/A pattern as §3.1). When all L1 hard gates plus dual crossing
  accounting pass, the grade is **`crossed-certified`**: the certified
  crossings equal cr(G) and each one is proven necessary by the
  planarization witness. 0-crossing graphs keep `best`; `crossed-certified`
  never applies to a planar-core (L0) drawing.
- **L2** (L1 admission failure: over CAP / over budget / no realizable
  witness drawing): the generic auto-v2 path runs unchanged with an
  additive honest record `gates.planarization_deferred = {reason: [...],
  measured: ...}` (same transport pattern as `anchors_standard_deferred`).
  Grade follows today's gates unchanged (normally `uncertified`); gate
  values stay measured, never fudged.

For L1 the oracle cr UB participates by default (the `--exact` layer,
D4 of the contract); without it `three_account_consistent` cannot pass
and the certificate stays honestly `uncertified`.  The D4 fallback is
wired as the `--no-exact` CLI flag (jacky 2026-11-14 scope ruling,
stdraw range n<=20): default stays ON for certificate integrity;
opting out keeps the witness-marked L1 drawing but the grade honestly
drops to `uncertified`.

### 3.3 n > 10 figures — the mechanical-grid regularity gates demote to report items

jacky's ruling of 2026-11-26 (stdraw20 manual-calibration lessons §5.1): the
three mechanical-grid regularity gates — `cv_le_035`, `pitch_uniform` (with its
`spine_pitch_uniform` / `column_pitch_uniform` mode aliases) and
`column_snap24_ge_060` — reward mechanical grids and penalize human
arrangements; on figures they cannot certify they measure nothing. They are
implemented as registry `when` policies (stdraw/cert_gates.py): on the
**automatic pipeline they apply only to n ≤ 10 figures** — for n > 10 the
measured boolean leaves `gates`, lands in `reports` (same key name) with an
additive `regularity_demoted_note`, is excluded from `gates_passed` and
`blocking_gates`, and can no longer block the grade. All other gates and the
grade semantics are unchanged; the underlying metrics rows (`spacing_cv`,
`column_snap24_rate`, …) stay measured. n ≤ 10 certificates are byte-for-byte
unchanged (the human-parity tier keeps all three as hard gates).

The two calibers are stated **separately** in the registry, so a ruling on
one cannot silently move the other: `_auto_regularity_applies` (n ≤ 10) is
the automatic side; `_manual_cv_never_gates` / `_manual_pitch_family_keeps_slot`
are the manual side (§3.4).

### 3.4 Manual (`--from-layout`) figures — `cv_le_035` demotes to a report item

Ruling record: [ADR-0019](adr/ADR-0019-manual-cv-gate-demotion.md) (accepted
2026-11-27); the automatic-tier counterpart is
[ADR-0018](adr/ADR-0018-2026-11-26-anchor-vocabulary-and-regularity-demotion.md).

jacky's ruling of 2026-11-27 extends the same evidence to the **manual
caliber**: a hand-drawn layout is not a mechanical grid, so the spacing-CV
gate never gates a `--from-layout` replay. `cv_le_035` leaves `gates`, its
measured boolean lands in `reports` (same key name) with an additive
`regularity_demoted_note` whose wording names the **manual caliber and the
2026-11-27 ruling** (never the n > 10 automatic one), is excluded from
`gates_passed` / `blocking_gates`, and cannot block the grade.

Scope is exactly one gate and one caliber:

- **only `cv_le_035`** is demoted on the manual side;
- `pitch_uniform` / `column_snap24_ge_060` keep their **P1-2 `N/A`
  applicability slot** (§3.1, jacky 2026-11-13) — they are applicability
  facts, not measured report items, and are untouched;
- the **automatic pipeline is untouched**, including n ≤ 10 (all three stay
  hard gates) and n > 10 (the 2026-11-26 demotion of all three, §3.3).

Rationale (stdraw20 manual-calibration lessons §5.1): on six hand-drawn
samples with 0 crossings and 0 box press, the CV gate alone rejected the
certificates; with it demoted those human layouts certify, which is the
caliber this engine exists to serve. Nothing is relaxed for the automatic
pipeline.

## 4. D0 — vertical-orthogonal diagrams are banned as deliverables

Ruling D0 (jacky, 2026-11-11): **vertical-orthogonal (ortho-v1) output is
banned as a deliverable / publication / iframe embed / gallery screenshot.**
"Box-over-line everywhere, repeatedly unfixable."

Engineering basis (isolation, not repair):

- the visibility-representation layout declares `wires strictly vertical`
  and `occlusion allowed under cards` by design — unrelated wires passing
  underneath opaque cards are structural, not incidental;
- leader bars span nearly the full canvas width while edges degenerate to
  single-column `{a, b, x, y1, y2}` segments, so cause-and-effect tracing
  through the drawing is broken;
- the layout was byte-frozen for CI regression (production behavior pin),
  so any layout-level fix collided with the freeze — the defect was
  unfixable in place, hence the delivery-exit ban.

Consequently (updated 2026-11-24, owner ruling A-item: the ortho entry
removal):

- the recipe's external entry (CLI `--recipe ortho`, `recipes.ortho_v1()`,
  the v1-legacy certificate caliber, `tests/baselines/`) is **removed** —
  new vertical-orthogonal output can no longer be produced through
  supported surfaces;
- historical v1-legacy artifacts carry `deliverable: false`,
  `blocked_reason`, `blocked_by: "D0"` in their certificates (read-back
  only; the `[BANNED / D0]` CLI notice is gone with the entry);
- enforcement stays in place: `scripts/check_no_ortho_delivery.py` (wired
  into `tests/ci_checks.py`) rejects any output directory that ships an
  `.html` page with vertical-orthogonal signals — certificate confessions
  (`caliber` / `recipe` / `deliverable`, kept for historical artifacts)
  plus geometry fallbacks (`meta.method`, leader bars + single-x edges,
  "all lines strictly vertical") so stripped or hand-made products cannot
  bypass it.

## 5. Change rules

- Grading implementation, gate thresholds, and the token set change only
  via an explicitly authorized card (never to let a specific figure pass).
- This document is updated in the same change set as any doc that presents
  grading tiers; the docs-consistency gate fails on drift.

## Appendix B. Annotation gates and the lens-chain tier (auto-v2)

- `loop_labels_clear` -- every certificate of a figure with declared loops
  carries the loop labels (loop id + name + direction glyph; polarity is
  carried by colour only, no `+`/`-` glyphs) in `layout.json`
  `annotations.loop_labels`. The glyph follows the loop's circulation as
  drawn: >= 3-node loops by the signed area of the member centers in
  member order, 2-node loops by the relative position of the two member
  arcs; the verdict is recorded per label (`dir` = `cw` / `ccw`,
  `dir_source` = `polygon` / `ring`) and echoed in the certificate
  metrics (`loop_labels[].dir`). An undecidable circulation is recorded
  honestly (`dir` = null, `dir_source` = `kind:collinear` /
  `kind:no-ring`) and only then does the glyph fall back to the kind
  default (B = `ccw`, otherwise `cw`). The shipped positions are
  re-verified on the delivered coordinates: >= 4px from every card and
  every line, >= 8px from every other label, >= 4px inside the viewBox. A
  label that cannot be placed is reported `placed: false`
  (`metrics.loop_labels_unplaced`), is hidden in the export, and never
  counts as a violation by itself.
- Label placement order (raises quality, never lowers the floor): the
  candidate centers are concentric rings around the loop centroid (near
  ring up to 160px, then a far ring 168-256px in 24 directions). Slots are
  tried in four passes -- near ring with the comfort clearance (>= 8px
  from cards and lines), near ring at the gate floor (4px), far ring with
  the comfort clearance, far ring at the floor. Slot coordinates round
  half up exactly like the interactive layer's JS `Math.round`, so the
  drag replay reproduces the exported positions.
- `delay_marks_clear` -- present when an edge carries `@delay`: every tick
  >= 16px from every card, no tick crosses another line or another mark.
- Both gates are listed in the certificate gate table (counted in
  `gates_passed`) and as geometry-report checks (a violation makes
  `geometry_report.json` `fail > 0`).
- `--no-loop-labels` (render-time annotation-layer suppression): the CLI
  flag removes the whole identity layer from `demo-2d.html` — loop-center
  labels AND `@delay` tick marks, one switch (the API equivalent is
  `render_html(..., loop_labels=False)`). The certificate then records
  `loop_labels_clear` / `delay_marks_clear` as `"N/A"` (same caliber as
  §3.1: the slots are excluded from `gates_passed`, never appear in
  `blocking_gates`, and never block), with an honest note in
  `honest_notes`. The `metrics` rows (`loop_labels`, `delay_mark_count`,
  …) stay measured — they describe `layout.json`, which still carries the
  placed annotations. Grade semantics are unchanged: an `N/A` slot is
  truthy-neutral in the hard-gate fold, so the grade is decided by the
  remaining gates exactly as before. A drawing without declared loops or
  `@delay` edges is unaffected (the keys only exist when the drawing
  carries the annotation — byte-neutrality holds).
- `line_style` field semantics (request vs delivery): the certificate
  field `line_style` (and the CLI `--linestyle` argument, echoed into
  `layout.json` `meta.line_style`) is the **request**, not a claim about
  the delivered drawing. With the loop-side arc default and the placement
  modes' constructed template geometry, the delivered line-kind
  distribution can differ from the request (e.g. every edge delivered as
  an arc while the request reads `straight`). The **delivered facts** are
  `metrics.line_kind_counts` (per-edge `route.kind` in `layout.json`) and
  the `loop_arcs` block. The human-facing summaries (the `demo-2d.html`
  headline and the CLI `[3/5]` line) therefore print the delivered counts
  ("line kinds arc 9 / line 1" form), never the request value.
- `lens-chain` tier (pure 2-loop figures, placement mode `lens-chain`):
  gate set = the layered regularity gates + `lens_pairs_closed` +
  `lens_pair_min_sep_ge_12` (14 gates). A figure without a mutual pair
  keeps its pre-lens mode trace byte-for-byte.
- Mutual pairs on every non-lens placement mode (2026-11-26): the delivery
  pass `Router.mutual_lens_construct` rebuilds each a<->b pair as the
  lens-chain double arc (gate-checked per edge; a rejected rebuild restores
  the original lines byte-for-byte and is reported as `status: blocked`).
  The hard gate `mutual_pairs_closed` re-reads the delivered geometry (both
  lines Q arcs, bulge >= 0.15, opposite sides, >= 12px apart); a chord tilt
  beyond `lens_tilt_max_deg()` (~37.4 deg) is an accounted exemption
`LENS_TILT_MAX_DEG` (a routing module constant; default `None` = the derived ceiling above) narrows the rebuild scope when set to a number: a pair tilted more than that stays the delivered parallel lines and is recorded `tilt`; the certificate re-measures with the same function.
  (`status: tilt`, re-measured from the node centres by the certificate). The
  lens-chain mode answers `N/A` (its lenses are constructed before routing;
  `lens_pairs_closed` carries the contract). The non-lens gate sets grow by
  this one gate (only added, nothing relaxed); grade semantics are unchanged.
  A figure without a mutual pair keeps the gate true and carries no
  `meta.mutual_lens` key in `layout.json`.
- Byte-neutrality: a figure without declared loops and without `@delay`
  carries no `annotations` key and no `delay` edge key.
- `loop_arcs` (a report item, not a gate): loop-member lines (both ends
  adjacent nodes of a declared loop of >= 3 nodes; mutual pairs excepted)
  default to an arc bulging away from the loop centroid. The record counts
  `preferred` / `arced` / `opposite_side_arcs` / `templated` and lists every
  fallback in `fallbacks[]` with a measured reason re-evaluated on the
  delivered coordinates. Mutual-pair members that are not arcs (a
  straight or polyline member of an a<->b pair) are listed in
  `fallbacks[]` too, under the separate `mutual_pair_non_arc` count --
  bookkeeping only: they are not scored against `preferred` (the pair's
  geometry belongs to the lens / rule-8 contract) and never touch
  `reports.loop_edges_arced` or `grade`. `reports.loop_edges_arced` is
  true only when every member line is a loop-side arc; a placement mode's
  constructed template geometry never counts as an arc, so `false` is not
  a quality failure and never touches `grade`. Caliber original:
  `docs/edge-placement-rules-v1.md` section 20.
- Byte-neutrality (loop arcs): a figure without declared loops, a figure
  whose loops are all mutual pairs, and the `--from-layout` manual path
  carry no `loop_arcs` key and no `loop_edges_arced` report.
