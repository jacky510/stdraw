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
- v1 grading: `certificate()` in `stdraw/metrics.py` (caliber `v1-legacy`,
  recipe `ortho-v1`).

## 1. Grade tokens (what `certificate.json.grade` can contain)

| caliber | recipe | tokens emitted by the 2D pipeline |
|---|---|---|
| `v2-hardgates` | `auto-v2` | `best`, `crossed-certified` (planarized L1 only), `uncertified` |
| `v1-legacy` | `ortho-v1` | `best`, `uncertified` (plus a retained legacy `second` branch, logically near-unreachable) |

`3d` is a **retired documentation-level tier**: it described the 3D delivery
path (a separate layout3d / render3d module pair and its CLI flags), removed
from the engine after v0.9.0. It never appeared as a value of the 2D
`certificate.json.grade` field; the token is kept in the read-back set only so
historical certificates still validate.

`second` is **v1-legacy only**: the branch still exists in the v1 grading
code for byte-compatible regression, but it was removed from the v2
implementation in v0.7.15+ (logically unreachable). No document may present
`second` as a current tier of the auto-v2 recipe.

## 2. The two calibers are different rulers

Both calibers can emit `grade: "best"`, but the token means different
things under each. The certificate therefore self-describes (fields are
additive; consumers read `caliber` **before** interpreting `grade`):

| field | v1-legacy (ortho-v1) | v2-hardgates (auto-v2) |
|---|---|---|
| `recipe` | `ortho-v1` | `auto-v2` |
| `caliber` | `v1-legacy` | `v2-hardgates` |
| `placement` | `ortho-v1` | placement mode (ring-cycle / spine-wing / ...) |
| `grade_semantics` | grading formula, in the certificate | grading formula, in the certificate |
| `blocking_gates` | list of `false` gate keys | list of `false` gate keys |
| `deliverable` | always `false` (see §4) | reflects the delivery contract (CLI full deliverable: `true`) |
| `blocked_reason` / `blocked_by` | set (`D0`) | absent |
| gate count at `best` | 4 legacy gates | 11+ hard gates (placement-specific) |

Grading formulas:

- **v2-hardgates**: `best` = 0 line crossings AND all placement-specific
  hard gates AND `anchors_standard` AND `visual_crossings_zero` AND dual
  crossing accounting; everything else is `uncertified` (honest no-grade).
- **v1-legacy**: `best` = 0 crossings AND min card gap >= 16 AND spacing
  CV <= 0.35; `second` (legacy) = placement ok AND <= 2 crossings; else
  `uncertified`.

Host rule: **read `caliber` first, then `grade`.** A v1 `best` and a v2
`best` are not interchangeable claims; and a v1 output is never a
deliverable at all (§4).

## 3. Soft targets vs certificate gates (the caliber split)

"Crossings <= 2 acceptable" and "row alignment" describe the **layout
objective function** (report items / soft targets: when placement
regularity holds, <= 2 crossings may be tolerated — order and elegance
first). They are **not** certificate gates: the certificate-level `best`
requires 0 crossings under both calibers, and in v2
`visual_crossings_zero` is a hard gate. A figure laid out under the soft
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
- the layout is byte-frozen for CI regression (production behavior pin),
  so any layout-level fix collides with the freeze — the defect is
  unfixable in place, hence the delivery-exit ban.

Consequently:

- `recipe=ortho-v1` / `caliber=v1-legacy` outputs carry
  `deliverable: false`, `blocked_reason`, `blocked_by: "D0"`, and the CLI
  prints a `[BANNED / D0]` notice;
- the frozen baseline itself stays in place for CI byte-regression
  (`tests/baselines/*.layout.json`, gate A) — the ban is on the **exit**,
  not on the recipe code or its regression data;
- enforcement: `scripts/check_no_ortho_delivery.py` (wired into
  `tests/ci_checks.py`) rejects any output directory that ships an `.html`
  page with vertical-orthogonal signals, using both certificate
  confessions (`caliber` / `recipe` / `deliverable`) and geometry
  fallbacks (`meta.method`, leader bars + single-x edges, "all lines
  strictly vertical") so stripped or hand-made products cannot bypass it.

## 5. Change rules

- Grading implementation, gate thresholds, and the token set change only
  via an explicitly authorized card (never to let a specific figure pass).
- This document is updated in the same change set as any doc that presents
  grading tiers; the docs-consistency gate fails on drift.

## Appendix B. Annotation gates and the lens-chain tier (auto-v2)

- `loop_labels_clear` -- every certificate of a figure with declared loops
  carries the loop labels (loop id + name + direction glyph; polarity is
  carried by colour only, no `+`/`-` glyphs) in `layout.json`
  `annotations.loop_labels`. The shipped positions are re-verified on the
  delivered coordinates: >= 4px from every card and every line, >= 8px from
  every other label, >= 4px inside the viewBox. A label that cannot be
  placed is reported `placed: false` (`metrics.loop_labels_unplaced`), is
  hidden in the export, and never counts as a violation by itself.
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
- Byte-neutrality: a figure without declared loops and without `@delay`
  carries no `annotations` key and no `delay` edge key.
- `loop_arcs` (a report item, not a gate): loop-member lines (both ends
  adjacent nodes of a declared loop of >= 3 nodes; mutual pairs excepted)
  default to an arc bulging away from the loop centroid. The record counts
  `preferred` / `arced` / `opposite_side_arcs` / `templated` and lists every
  fallback in `fallbacks[]` with a measured reason re-evaluated on the
  delivered coordinates. `reports.loop_edges_arced` is true only when every
  member line is a loop-side arc; a placement mode's constructed template
  geometry never counts as an arc, so `false` is not a quality failure and
  never touches `grade`. Caliber original: `docs/edge-placement-rules-v1.md`
  section 20.
- Byte-neutrality (loop arcs): a figure without declared loops, a figure
  whose loops are all mutual pairs, and the `--from-layout` manual path
  carry no `loop_arcs` key and no `loop_edges_arced` report.
