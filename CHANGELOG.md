# Changelog

Notable user-visible changes to **stdraw**. Entries before 0.8.0 are not
reproduced here; the engineering version history lives in
[AGENTS.md](AGENTS.md) ("Version" section) — pointer, not a copy.

## 0.10.0 (2026-11-28)

- **closed-ring lenses for mutual pairs, rounded-corner arrow tips**
  (commit `3b8e21d`): a delivery repair pass (`Router.mutual_lens_construct`,
  runs last on every non-lens engine) rebuilds each `a<->b` pair as the
  lens-chain double arc, trying anchor variants in order and gate-checking each
  edge against `LENS_CONSTRUCT` and the >=12px pair separation; a pair the
  arrow-normal channel already closed as a slim lens is left untouched, and a
  refused pair keeps its lines byte-for-byte with per-variant reasons. A new
  hard gate **`mutual_pairs_closed`** re-reads the delivered geometry (fat or
  slim lens closed; tilt exemption reproducible from the node centres and every
  anchor variant's chord; blocked / claimed / frozen / designated accounted as
  exemptions) and joins only the non-lens gate sets (lens-chain keeps
  `lens_pairs_closed`); grade semantics unchanged. Arrow tips on corner anchors
  are projected onto the r=14 rounded outline (the `arrow` field only -- anchors
  and path points untouched; the interactive JS mirrors it with `cardRadius` in
  the payload). `column-chain` members with a spine neighbour take the anchor
  row first. Docs: `docs/layout-modes.md` (zh/en) closed-ring contract,
  `docs/routing-gates.md` section 9, `tests/test_mutual_lens_rebuild.py`.
  **This is the one 0.10.0 change that moves 2D bytes beyond the deliberate
  items listed in the consumer note below** -- gate counts shift (e.g. 11/12 ->
  12/13) and certificates of figures that now fail a gate gain `repair_hints`.

- **Consumer note: 0.10.0 is not a byte-identical drop-in for 0.9.0.** The 3D
  removal itself changes no 2D artifact, but four other changes in this range
  do: `edges[].arrow` (rounded-corner projection), `interactive` / `drag_layer`
  (opt-in drag layer, so the default delivery face declares `false` / `"no"`),
  the new `mutual_pairs_closed` gate (gate counts move), and the resulting
  `metrics` / `mode_decision_trace` / `gates_passed` shift. Measured on
  `examples/limits-to-growth.cld` at both tags: `layout.json` differs in 280
  leaves and `certificate.json` in 48, while `loops_audit.json` and
  `graph.json` are unchanged. Re-generate pinned artifacts before pinning
  again.

- **manual (`--from-layout`) caliber: `cv_le_035` demotes to a report item**
  (jacky's ruling of 2026-11-27, extending the 2026-11-26 automatic-tier
  ruling): a hand-drawn layout is not a mechanical grid, so the spacing-CV
  gate never gates a manual replay. `cv_le_035` leaves `gates`, its measured
  boolean lands in `reports` (same key name) with a `regularity_demoted_note`
  that names the manual caliber and the 2026-11-27 ruling, is excluded from
  `gates_passed` / `blocking_gates`, and cannot block the grade. Implemented
  as registry `when` policies with the two calibers stated **separately**
  (`stdraw/cert_gates.py`: `_auto_regularity_applies` / `_manual_cv_never_gates`
  / `_manual_pitch_family_keeps_slot`), so neither caliber can silently move
  the other. Scope is one gate and one caliber: `pitch_uniform` /
  `column_snap24_ge_060` keep their P1-2 `N/A` slot, and the whole automatic
  pipeline (n ≤ 10 three hard gates; n > 10 the 2026-11-26 demotion) is
  byte-for-byte unchanged. Raw metrics stay measured; grade semantics and every
  gate threshold untouched. Docs: `docs/grading-contract.md` §3.4 and
  `docs/adr/ADR-0019-manual-cv-gate-demotion.md`.

- **metrics.py: the spliced duplicate copy of the module is gone (code
  hygiene, no behavior change)**: the T17 split left `stdraw/metrics.py`
  carrying the module twice — the refactored body (metrics helpers plus the
  nine per-concern `_cert_*` helpers that `certificate_auto` calls) followed by
  the full text of the same module. Python's last-definition-wins made the live
  namespace a mix of both copies (the nine helpers from the first, 13
  redefinitions plus `certificate_auto` from the second), so the file stated one
  definition twice and deleting the wrong run of lines would have removed the
  only definitions of the helpers. The file now carries exactly one definition
  per top-level name, spliced by AST node ranges (no source text retyped): 259
  duplicate lines removed, module namespace, every function's compiled code and
  the module docstring unchanged, and certificates/layouts byte-identical on
  the A-tier dual-leg sweep.


- **refactor: the last two giant functions are split into stage helpers
  (T17 continuation), outputs byte-identical**:
  `layout_auto._layout_optimize_routes` (639 lines on the merge base;
  619 before the anchor-vocabulary card grew it) becomes a 45-line
  orchestrator over six stage helpers (edgerules presets / primary
  routing / manual injection / repair chain / anchor snap / post-snap
  lens channel) with `router`/`routes` threaded in call order;
  `planarized_layout._planarized_l1` (538 lines) becomes a 16-line
  orchestrator over five stage helpers (exactness aggregation / core
  bands / attachment trees / normalization / output assembly), with the
  former nested `_defer` and `_build_polys` lifted to module functions.
  A test-first commit pins the L1 output surface (four corpus L1
  fixtures: witness-on-both-routes, attachment escapes, parking lane,
  viewBox and meta-block invariants -- structural, platform
  independent), then one `refactor(split):` commit per function. No
  public API, CLI flag, output schema or delivered byte changed (golden
  8/8 identical; dual-tree compare identical on 41 inputs including two
  manual `--from-layout` legs; full A-tier and ci_checks green).
  Old-name -> new-location table:
  [docs/refactor-move-map.md](docs/refactor-move-map.md).
- **anchors: multi-slot anchor vocabulary + anchors_standard criterion change
  (owner approval 2026-11-26; grounded in the stdraw20 manual-calibration
  lessons §4)**: (1) the anchor vocabulary opens from the fixed 16-point set
  to numbered side slots `n/s/e/w-g1..g7` (+ corners / midpoints; g1/g2 keep
  the legacy golden coordinates, slot usage is adaptive, the id -> coordinate
  mapping is context-free) synced end-to-end — DSL `@anchors src=..,dst=..`
  (`parse(dumps(g)) == g` preserved, canonical order `@loops -> @anchors ->
  @delay`), `layout.json` `edges[].anchor_ids` (present only on edges
  actually delivered on their designation), interactive manual-layout export,
  `--from-layout` replay (old formats replay unchanged, no warnings); designations
  travel the `--from-layout` user channel including the hard-gate fallback.
  (2) `anchors_standard` = endpoint ON the box border + angle >= floor — the
  16-set membership requirement and the dense slot-grid exemption are retired
  (W9: membership blocked ~80% of manually calibrated figures); no threshold
  loosened. (3) fan slot competition settled by swap with the departure-
  azimuth φ key (`Router.fan_slot_reorder`, repair-chain tail; near-segment
  crossing detected pairwise, candidates = φ order + per-pair swaps,
  acceptance = strictly fewer near crossings + route crossings not increased
  + FAN_SPREAD gates vs baseline; crossing-free groups byte-identical).
  CI J-phase criterion re-anchored to on-border + angle.  Baseline drift
  (golden / demos) is the change's declared effect; re-blessing awaits
  separate approval.

- **certificate caliber: the mechanical-grid regularity gates demote to
  report items on n > 10 figures (owner ruling 2026-11-26, from the
  stdraw20 manual-calibration evidence)**: `cv_le_035` /
  `pitch_uniform` (+ the `spine_pitch_uniform` / `column_pitch_uniform`
  mode aliases) / `column_snap24_ge_060` now apply as hard gates only on
  n ≤ 10 figures — the recommended, human-parity domain; on n > 10 their
  measured booleans move to `reports` (with an additive
  `regularity_demoted_note`) and no longer count in `gates_passed` or
  block the grade. Implemented as registry `when` policies
  (`stdraw/cert_gates.py`), not new branches. n ≤ 10 certificates and the
  manual (`--from-layout`) caliber are unchanged byte-for-byte; layout
  bytes never change (placement does not consume certificate gates).
  Caliber: [docs/grading-contract.md](docs/grading-contract.md) §3.3.

- **code hygiene: personal-ruling annotations migrated to `docs/adr/`
  (T18)**: the 68 "owner + date" ruling annotations across `stdraw/*.py`
  are replaced by the rule text plus a `docs/adr/ADR-XXXX` pointer; each
  ruling's original annotation (with attribution, verbatim) is preserved in
  a dedicated ADR under [docs/adr/](docs/adr/README.md) (18 rulings +
  index, each with the ruling date, the decision in force and the affected
  source sites). Three certificate output strings changed accordingly — the
  ring-observability note (`ring_candidates.note`) and the two n>10
  regularity-demotion strings (`reports.regularity_demoted_note` and the
  matching `notes` entry) now cite the ADR / the owning role instead of a
  personal name; every other delivered byte is identical. New reference doc
  [docs/env-vars.md](docs/env-vars.md): all five `STDRAW_*` engine
  variables (`STDRAW_TIMING` / `STDRAW_SNAP_DEBUG` / `STDRAW_L1_PINNED` /
  `STDRAW_PKG_PARENT` / `STDRAW_PIN`) plus the harness-only variables,
  each with read sites and effect scope, verified against the source.

- **refactor: the giant functions are split behind registries (T17), outputs
  byte-identical**: the certificate gate assembly becomes a data registry
  (`stdraw/cert_gates.py`: `MODE_GATE_SETS` in the historical elif order,
  one check function per gate, ordered overlays, a per-entry `when=` effect
  slot — first version replicates every historical branch, so a future
  applicability change such as "regularity gates become report items for
  n>10" is a one-line data change); the layout mode priority chain becomes a
  registry too (`stdraw/mode_registry.py`: `MODE_CHAIN` detect/trial/guard +
  `PLACE_CHAIN` placement dispatch, the coupled column/comb/ring tier kept
  verbatim); `__main__.main`, `check.auto_geometry_report` (per-check
  helpers), `metrics.certificate_auto` (per-concern scan helpers) and
  `_layout_candidates` (chain + placement moved out) are split with pure
  moves. Every move/split is an independent `refactor(move|split):` commit;
  old-fully-qualified-name -> new-location table in
  [docs/refactor-move-map.md](docs/refactor-move-map.md). No public API,
  CLI flag, output schema or delivered byte changed (golden 8-figure set +
  A-tier frozen baselines + targeted suites green).

- **perf: exact-equivalence hot-path acceleration in the routing engine**
  (auto layout wall clock; outputs byte-identical, 40/40 random-corpus
  graphs cross-checked against the pre-change tree): the coincidence span
  now runs over a content-keyed sampled-geometry cache with seg-grid spans
  and a bbox prefilter; `final_crossing_pairs` walks the cached seg grid;
  the box-press loops (`_edge_stats`, `_own_press`, the cached evaluate
  path, the reposition gate's clearance accounting) use a bbox-vs-box gap
  lower bound with the distance math inlined; the reposition gate skips
  bbox-disjoint pairs for visual crossings; the snap gate reuses the
  already-computed edge stats; the vg candidate blocked test gets a bbox
  prefilter. Random-corpus A-tier legs (n10 x20 + n20 x20, cp-sat-layered):
  n10 median 23.7s -> 21.4s, n10 total wall clock 2.40x, the six slowest
  ring-construct graphs 2.5-3.0x, n20 total 1.22x.
- **BREAKING: the interactive drag layer is now an opt-in (`--interactive`)**:
  the default CLI deliverable page (`demo-2d.html`) is the STATIC diagram +
  certificate (no toolbar / payload / drag script); pass `--interactive` to
  ship the touch-up layer (drag re-routing, waypoint handles, style cycling,
  Export layout). `layout.json` / `certificate.json` honestly declare the
  delivery face either way (`interactive` true/false, `drag_layer` yes/no);
  the layout geometry itself is byte-identical in both modes, and a
  `--interactive` run reproduces the previous default output byte-for-byte
  (golden 8-figure set + a manual-layout replay cross-checked).
  The library API (`render_html`) keeps its previous behavior by default;
  only the CLI default changed.
- **BREAKING: `layout-diff` / `--compare-auto` moved out of the CLI into
  repo tools** (development gauges, not shipped in the wheel or the sdist):
  `stdraw layout-diff a.json b.json --cld x.cld --diff-out d.json` becomes
  `python tools/layoutdiff.py a.json b.json --cld x.cld --out d.json`, and
  the `--compare-auto` flag becomes
  `python tools/compare_auto.py input.cld --from-layout manual.json
  --outdir out` (same dual-certificate comparison JSON). `--from-layout`
  stays a core CLI flag (the manual-calibration loop is a first-class
  feature). Both tools keep in-repo regression tests.

- **BREAKING: ortho-v1 external entry removed** (owner ruling 2026-11-24, A-item:
  the freeze is lifted): the CLI `--recipe ortho` option, `recipes.ortho_v1()`
  and the `run("ortho-v1")` branch, the CLI freeze-compat code (the
  delivery-contract strip and the `[BANNED / D0]` notice), the ortho
  byte-level CI baselines (`tests/baselines/`) and the v1-legacy
  certificate caliber (`metrics.certificate()` / `scene_from_planar`,
  `stdraw.certificate` / `stdraw.PlanarLayout` package exports) are gone;
  `--recipe ortho` now fails as an unknown recipe. The underlying planar
  module survives as an INTERNAL implementation detail (candidate-v1
  still calls it) with no freeze/pin promise. The auto-v2 default path is
  byte-identical. Ruling D0 (vertical-orthogonal pages banned as
  deliverables) remains in force — `scripts/check_no_ortho_delivery.py`
  stays wired into CI with a synthetic-fixture flag test.
- **3D layer removed** (owner ruling 2026-11-24: the 3D deliverable was
  judged low-value and dropped): `layout3d` / `render3d`, the `--solids`,
  `--theme-3d` and `--skip-3d` flags, `positions3d.json`, `demo-3d.html`,
  the bundled three.js assets and the standalone 3D viewer are gone.
  The CLI is 2D-only; every 2D artifact is byte-identical to 0.9.0
  (26-figure three-way hash sweep: pre-removal `--skip-3d`,
  pre-removal default, post-removal default).
- **Loop-reading layer (default on)**: every declared loop carries a
  loop-center label (id + name + direction glyph; polarity stays
  color-only), loop-member edges of loops with >= 3 nodes default to an
  arc bending along their loop — straight / detour fallbacks are recorded
  with measured reasons in `certificate.json` (`loop_arcs.fallbacks`) —
  and the new `@delay` edge marker draws a double tick at the edge
  midpoint (the DSL round-trips through `graph.cld`). New hard gates:
  `loop_labels_clear`, `delay_marks_clear`. The demo page gains a
  `Loops: on/off` toggle.
- **lens-chain placement mode**: pure two-loop figures (two mutual pairs
  sharing a node) place as a lens chain — the 4-node Limits to Growth
  archetype moved from `uncertified` to `best` (15/15 gates) with both
  loops closing as lens-shaped double arcs; hard gates `lens_pairs_closed`
  and `lens_pair_min_sep_ge_12`.
- **Speed**: routing candidate pruning (exact lower bounds, memoized
  mutual-pair spacing, bbox gap pre-checks) with byte-identical output —
  golden archetype set wall time mean 1.63 s -> 0.99 s and max 4.79 s ->
  2.11 s measured on one Windows machine.
- **Fact-based line-kind summaries**: the `demo-2d.html` headline and the
  CLI `[3/5]` summary now print the **delivered** line-kind counts
  (`metrics.line_kind_counts`, e.g. "line kinds arc 9 / line 1") instead
  of the `--linestyle` request echo — with the loop-side arc default the
  request value could contradict the delivered drawing. The certificate
  `line_style` field keeps its meaning (request); the request-vs-delivery
  semantics are documented in `docs/grading-contract.md` Appendix B.
- **`--no-loop-labels` CLI flag**: suppresses the whole annotation layer
  in the demo page (loop-center labels AND `@delay` marks, one switch —
  previously only the API parameter `render_html(loop_labels=False)` and
  the demo toolbar toggle could). The certificate then records
  `loop_labels_clear` / `delay_marks_clear` as `N/A` (excluded from the
  pass count, never blocking; grade semantics unchanged). Non-demo
  products (layout / certificate / audit) of default runs are
  byte-identical.
- Consumer note: render output bytes change (label layer, loop-side arcs,
  the new certificate gate rows). Byte-pinned consumers (STDRAW_PIN) must
  regenerate their artifacts and advance the pin per their own release
  discipline; the live pin is not moved here.

## 0.9.0 — 2026-11-23

- **anchors-as-prior candidate generation (opt-in)**: hand-drawn anchor
  layouts can seed candidate generation — family-gated anchor
  retrieval with feature-distance ranking, a deterministic
  mirror-symmetry post-pass (`--mirror-symmetry`, default OFF), and
  M0-gate ordering — delivered through the existing `--from-layout`
  replay channel. The default auto-v2 path is byte-unchanged (flag off
  = the post-pass branch never runs).
- **candidate-v1 recipe (opt-in)**: structure analyzer + template
  candidate sources + orchestrator + three-tier selection +
  routing-in-the-loop, delivered through the incumbent pipeline with a
  not-worse-than-v0.8.2 guard (`stdraw.recipes.run("candidate-v1",
  ...)`); auto-v2 untouched.
- **Preference research line (research toolchain + experiment
  report)**: pairwise annotation toolchain (adaptive question
  selection across three rounds, byte-faithful rendering), final
  preference comparisons on 25 pairs and a three-round merge of 62
  pairs, with the Bradley-Terry fit converged (diagonal-Hessian Newton
  + duplicate-column merge; earlier M2/M2s readings corrected as
  unconverged-solver artifacts), out-of-fold anchor-preference control
  and a both-bad warning list.
- **Performance**: `layout()` split into verbatim-equivalent stages
  and polish incremental scoring (the top hotspot, ~97% of stage time;
  n=10 median first cut ≤ 30 s).
- **Fixes & hygiene**: `dc.load_corpus` manual-layout filter
  (kind/filename) — pairwise annotation session JSONs no longer break
  corpus loading; CI render-baseline sha re-anchor (CRLF-safe
  .gitattributes byte-pinning); demos freshness repair.
- No visual-face change: the UI-A theme baseline is untouched and the
  default render path is byte-identical to 0.8.2 (frozen-baseline byte
  gate + demo freshness gate re-verified at this closure). Consumer
  note: byte-pinned consumers (STDRAW_PIN) re-verify their artifacts
  against this release per their own release discipline.

## 0.8.2 — 2026-11-17

- **Ring form battery manual-calibrated + reverse-form gate widened to
  spine-wing / ring-cycle**: ring regularity gate thresholds re-derived
  from hand-pulled ring truth fixtures (a certified good ring measured
  chord spacing CV 0.0802 / template fit 0.1197 — the old 0.05 gate
  rejected it; the free-hand upper bound measured CV 0.4626 / fit 0.6922),
  landing at RING_SPACING_CV_MAX = 0.50 / RING_TEMPLATE_FIT_MAX = 0.70
  with a single source in `stdraw/ringlayout.py` (metrics / check /
  ci_checks / tests all consume it). Certificate gate rows renamed
  le_005 -> le_050 / le_070.
- **Trial-gate fallback is no longer silent for radial / spine-wing /
  ring-cycle**: layout meta records `form_fallback` (mode + reason) and
  the certificate gains a `topology_form_fallback` gate row with an
  honest grade downgrade — form misfit precedes every hygiene metric.
  The 42-graph A-tier stock certificate records were regenerated at this
  closure: 23 graphs byte-drifted (11 ring gate-row renames with grades
  unchanged; 11 `form_fallback` meta faces with grades unchanged), with
  exactly one grade flip — random-n10-i11 ring-cycle best -> uncertified
  (spine-wing detected but its trial discarded; approved 2026-11-17).
- Also since 0.8.1: exact content-keyed memoization across polish
  candidate worlds (byte-identical outputs, faster sweeps), and the
  interactive L1 tooltip overlay now emits after the `</svg>` element so
  cross markers keep their node cards inside the svg.
- Consumer note: `certificate.json` `version` and `layout.json`
  `engine_version` advance to 0.8.2 on every render — byte-pinned
  consumers (STDRAW_PIN) must regenerate their artifacts and advance the
  pin per their own release discipline.

## 0.8.1 — 2026-11-13

- **Interactive toolbar hint condensed and overridable**: the English
  chrome hint (340+ chars) is condensed and exposed as a new keyword
  parameter `hint` on `render_html` / `render_auto_html` (default `None`
  = built-in English chrome, per the repo language policy: the engine
  EN face stays CJK-free). Byte-pinned consumers pass their own face
  copy (the Chinese-domain consumer passes Chinese). No geometry or
  interaction-contract change; default output changes only in the hint
  string itself.
- **Dark-tier hint contrast fix (ui-design D1)**: `hint_text` #64748b →
  #94a3b8 on the #0f172a toolbar (WCAG 3.75:1 → 6.96:1, AA-passing).
  viewer/themes.js regenerated from themes.py via write_viewer_js
  (generated-artifact channel, byte-pinned by tests).
- Consumer note: render output bytes change → the byte-pinned consumer
  (investment-advisor HDD chain, STDRAW_PIN 0.8.0/d04a872) must
  regenerate its three artifacts from this release and advance the pin
  (deterministic double-run + CDP regression before the lock moves).
  Note: hash repointed for chain consistency only — the live 8777 STDRAW_PIN
  migration is aligned by advisorbot's next release, not moved here.

## 0.8.0 — 2026-11-11

UI-A theme baseline (drawing-office style, spec:
[docs/ui-theme-spec-a.md](docs/ui-theme-spec-a.md)) — a declared
major-version visual baseline. Engine behavior (parsing, placement,
routing, certificates, gates) is unchanged by this release; what changes
is the delivered look, in both tiers:

### 2D

- **Light tier redefined — "tracing paper"**: parchment page ground with a
  dotted canvas grid and ink-line cards, replacing the amber-carded look;
  the amber / sky-blue polarity inks remain the only two chromatic accents
  on the canvas.
- **Dark tier redefined — "midnight ink"**: faint blue-black ground with
  neutral steel-gray containers and grid, replacing the slate look; the
  polarity inks stay the sole color carriers.
- **Card corner radius 14** (large step of the three-step corner scale).
- **Canvas grid backdrop**: dotted grid rendered under the diagram
  (render-layer only; the edge hit layer remains un-occluded).
- **Certificate as engineering title block**: the quality-certificate
  panel is styled as a drawing title block and deliberately keeps square
  corners (it does not follow the card radius).

### 3D

- **Light stage added**: first light theme for the 3D layer — structure
  and placement unchanged, colors derived from the A light tokens.
- **Dark tier frozen**: the existing dark 3D values are frozen
  byte-for-byte — zero changes.

No routing, placement, certificate-gate or API changes are included in
this entry.
