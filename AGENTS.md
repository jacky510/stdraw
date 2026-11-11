# AGENTS.md — stdraw (in-repo worker caliber + usage manual)

> This file has two parts: **Part One** for AI card workers entering the repo
> (the caliber travels with the repo); **Part Two** for agents using the
> stdraw engine (originally "stdraw usage manual for agents").
> When a card text conflicts with this file: safety / verification / release
> caliber follows this file; requirement content follows the card.
> This file's caliber is maintained by default; workers finding stale caliber
> -> report via a card comment, do not edit this section directly.
>
> Skill pointers (scoped pointers, no copies): the `systems-thinking-diagram`
> skill canonical copy lives on the default side at
> `<user-home>/AppData/Local/hermes/skills/autonomous-ai-agents/systems-thinking-diagram/`;
> this repo's `skills/stdraw/SKILL.md` is the openly published Agent Skill
> (install entry via `npx skills add jacky510/stdraw`) — the two are
> independent: the canonical copy is never copied into the repo, and the
> repo's publishing face never writes back to the canonical copy (a copy
> always drifts).

## Repo structure

| Path | Purpose |
|---|---|
| `stdraw/` | engine package: DSL parsing / placement (auto-v2 mode-based) / mathematical routing (WS3) / exact crossings (WS2) / certificates / CLI (`python -m stdraw` entry) |
| `tests/` | pytest cases + `ci_checks.py` (CI iron-gate script) + `baselines/` (ortho-v1 frozen baselines, byte-pinned) |
| `examples/` | `.cld` samples (limits-to-growth / classic-cld-growth-and-burden) |
| `demos/` | deliverable demo HTML + certificate JSON — **publishing face**, must stay byte-identical to a fresh re-render by the current engine |
| `docs/` | caliber originals: `dsl-spec-v0.1.md` (+ `.zh-CN.md` counterpart) / `layout-modes.md` / `crossing-exact.md` / `gallery/` (screenshots) |
| `benchmarks/` | corpus `corpus/` + raw evidence `raw/` + `REPORT.md` (benchmark summary-table original) + `tools/` |
| `skills/stdraw/` | the openly published Agent Skill (open-source install entry, see the pointer note above) |
| `viewer/` | zero-dependency 3D interactive viewer |
| `assets/` | third-party JS for viewer/3D pages (three.min.js etc.; do not bump versions on your own) |

## Common commands

Local dev interpreter: `<user-home>/AppData/Local/Programs/Python/Python312/python.exe` (repo path `<user-home>/Projects/stdraw`).

| Command | Purpose |
|---|---|
| `python -m pytest tests/ -q` | unit tests |
| `python tests/ci_checks.py` | CI iron gates: ortho frozen regression byte-pinned + auto-v2 hard gates + determinism double-run (+ optional DOM layer) |
| `python -m stdraw layout examples/classic-cld-growth-and-burden.cld --name classic-cld --skip-3d` | run the main sample, producing certificate/demo |
| same command twice + `sha256sum` comparison | determinism verification (outputs are safe to commit, diff must be clean) |
| re-render the demo and compare byte-for-byte against `demos/classic-cld-2d.html` | demo freshness gate (stale-deliverable detection) |

## Allowed (workers may do directly)

- Fix bugs, add tests, change files within the card's stated scope; add docs under `docs/`; add cases under `tests/`
- Append samples to `examples/` / `benchmarks/corpus/` (do not touch existing corpora or REPORT.md's published numbers)
- Re-render `demos/` updates (must pass the freshness gate + publishing-face acceptance, see "Verification & commit")

## Forbidden (must hang a card or kanban_block and wait — never decide on your own)

- Changing the `tests/baselines/` frozen baselines or ortho-v1 frozen behavior — unless the card explicitly requires "re-baselining" and states the basis (only with same-file precedent)
- Touching the publishing face (`README*` / `demos/` / `docs/gallery/` / `skills/stdraw/SKILL.md`) without publishing-face acceptance
- Relaxing certificate hard-gate thresholds or changing the grade semantics (best/3d/uncertified) — never tune gates to let a figure pass
- Copying the default-side `systems-thinking-diagram` skill canonical copy into the repo (pointers only, see the header)
- Bumping the version number (`pyproject.toml` / README badges / the "Version" section of this file) as a side effect — **since ref-scrubbed, version closure is unified through a dedicated "version closure card"**, no scattered bumps
- Shared-main-tree discipline: `<user-home>/Projects/stdraw` main tree often has multiple cards' in-flight changes — **never commit files that are not on your own card's list**; commits always go through a temporary clone (precedent ref-scrubbed)
- Credentials, network configuration, deleting data, force-pushing main / rewriting history

## Verification & commit

- Before committing you must run: `python -m pytest tests/ -q` + `python tests/ci_checks.py`; if you cannot run them, write honestly "unverified + why" — never claim otherwise
- **Determinism snapshot acceptance** (cards changing engine behavior): same input, two runs, byte-identical; multi-graph sweep with byte-zero drift relative to base (precedent ref-scrubbed: 19 graphs, only the target graph switched, the other 18 zero-drift)
- **Sanitization check** (cards touching the publishing face): before committing, verify the publishing face contains no local absolute paths, internal card ids/codenames, credentials, or machine-specific info (open-source facade hygiene)
- **Acceptance tiers**: card-level = this card's acceptance (tests + cross-checks); publishing-face = publishing face + CI certificate gates. Changes touching the publishing face **must pass both tiers**; for publishing-face acceptance, write the cell-by-cell cross-check script before editing docs (certificate gates per key, REPORT.md summary table per cell, CLI parameter table vs `--help` measured)
- Threshold numbers written on a card are snapshots from drafting; the final state follows the measured JSON
- After pushing you must read back: `gh api repos/jacky510/stdraw/commits?per_page=1 --jq '.[0].commit.committer.date'`
- Commit messages describe the change itself; internal card ids are banned from
  public history -- see the internal-leak sanitization gate section below

## Internal-leak sanitization gate

Internal coordination identifiers must never reach the public repository
(history rewrite 2026-11 scrubbed all prior occurrences). Banned in every
tracked file, commit message and branch/tag name:

- Task/card ids matching `t_[0-9a-f]{8}` -- write `ref-scrubbed` instead
- Local machine absolute paths (drive-letter user-profile paths, both slash
  styles) -- write `<user-home>` instead
- Chat-app approval records (the app name followed by `approval`) -- write
  `explicit approval`
- Verdict/approval codes (former `C+B/A+D`-style) -- write `approval`

Enforcement, two independent layers (both must stay green):

1. CI first step: `python scripts/check_internal_leaks.py` scans the tracked tree.
2. Pre-push hook (repo config `core.hooksPath = scripts/hooks`): tree scan plus
   pushed ref-name check plus commit-message range check -- a push carrying any
   banned pattern fails physically.

Adding a new banned pattern = one commit updating all three places together:
`scripts/check_internal_leaks.py`, `scripts/hooks/pre-push`, and this section.

## Branches & release

- Trunk = `main`; after card-level acceptance passes you may push directly (lightweight doc/fix-class); big feature cards complete the sweep zero-drift verification before pushing
- After pushing, watch the remote CI double job until success; if red, fix before closing the card
- Version releases go through a "version closure card": unified bump of version number / badges / the "Version" section of this file + certificate summary cross-check
- Publishing-face changes must attach publishing-face acceptance evidence (cross-check output / screenshots / certificate gates list)

---

The following is the original "stdraw usage manual for agents" (preserved verbatim except the title line):

## stdraw usage manual for agents (detailed)

stdraw is a planarity-aware systems-thinking diagram (CLD / causal loop
diagram) engine: **text DSL in, diagram with a quality certificate out**.
It is designed for agents — zero interaction, deterministic output, and every
deliverable is machine-readable JSON + directly openable HTML.

The shortest path for an agent host: this repo's `skills/stdraw/SKILL.md` is
the standard Agent Skill (`npx skills add jacky510/stdraw` installs it
directly); this document is the detailed manual — the two carry the same
content.

## What it can do (v0.7.1 end state)

1. **auto-v2 default recipe (mode-based placement)**: deterministically picks
   a placement mode by graph structure, priority
   = bowtie-pair symmetric (two triangles sharing an edge, 4 nodes 5 edges)
   -> bowtie-vertex (v0.7.0, exactly 2 enumerated simple cycles sharing
   exactly 1 node) -> spine-wing (v0.7.1, hub pair with >= 3 common neighbors
   + pairable rest secondary clusters + main-chain share <= 0.5)
   -> comb-bilateral
   -> column (3<=n<=12 AND longest simple cycle 3<=k<=4 AND k<n)
   -> ring (pure cycle / main cycle covering >= n-2 or cycle-edge share
   >= 0.9 AND k>=5 or covering the whole graph) -> layered; every mode has a
   **trial gate** (after construction, placement re-runs the same router's
   hard-gate proxies for review), and any failure **silently falls back** to
   the next tier, with negative cases byte-identical. Full rules in
   [docs/layout-modes.md](docs/layout-modes.md) (Chinese; English edition: [docs/layout-modes.en.md](docs/layout-modes.en.md)).
   - **Placement hard gates**: box-over-line = 0 (any angle, 1px margin),
     edge-box clearance >= 16px, smooth anchors, card gap >= 16px (36px
     breathing target), mutual pairs (a<->b bidirectional edges) two-line
     separation >= 4px, line-line visual coincidence = 0; placement
     regularity gates switch per mode — ring: on-ring equal spacing
     CV <= 0.05 + regular-polygon template fit <= 0.05; column: main-chain
     column-axis deviation <= 2px + constant main-chain row pitch;
     symmetric: mirror-axis error <= 2px; bowtie-vertex: mirror-axis error
     <= 2px; spine-wing: spine x alignment <= 2px + midline adherence
     <= 2px + mirror <= 2px; layered: constant row pitch + column snap;
     anchor mid-band (v0.7.3, engine-wide hard gate): corner hits = 0
     + in-band share (+/- 1/4 edge length) >= the v0.7.2 baseline lock table,
     spine-wing requires 100% in-band;
   - **Crossings and row alignment are report items (soft targets)**: when
     placement regularity holds, <= 2 crossings are allowed (order and
     elegance first); grading semantics unchanged — "best" still requires
     0 crossings. Grading single source: `docs/grading-contract.md` —
     auto-v2 (caliber `v2-hardgates`) emits `best` / `uncertified` only
     (`second` removed in v0.7.15+, survives only in the v1-legacy ortho
     caliber, which is banned as a deliverable by ruling D0); read
     `certificate.json.caliber` before interpreting `grade`;
   - **R/B polarity coloring** (replacing letter badges): single-loop edges
     R = amber `#d97706`, B = sky blue `#0284c7`; multi-loop mixed-kind or
     non-loop edges neutral gray `#64748b`; negative-polarity edges dashed
     (`stroke-dasharray="6 4"`).
2. **Mathematical routing layer (WS3)**: obstacle avoidance =
   clearance-inflated obstacle **visibility-graph Dijkstra shortest path**
   (exactly optimal on the graph; at most (2 - pi/2) x inflation margin px
   more per hugging corner than the true continuous-space shortest path
   around rounded-corner obstacles); smoothing = **tangent arcs** at
   polyline bends (G1 tangent-continuous, bounded curvature, per-arc
   clearance recheck); mutual pairs take lens double arcs / parallel offsets
   / outer detours, merging back into a double-arrowhead line is forbidden;
   **dual crossing accounting**: the router's theoretical per-edge hit-count
   sum / 2 must equal the geometric recount on delivered coordinates, and a
   mismatch refuses the certificate; polylines carry fixed type costs
   (vg detour bend +120 / poly lane polyline +40 / wrap outer detour +200)
   — when straight/arc lines are feasible, polylines don't win the score;
   polylines are the last resort.
3. **Exact crossing-number layer (WS2, `--exact`)**: ordering insertion ILP +
   planarization oracle + B&B squeeze computing cr(G), written into the
   certificate `exactness` block (`proven_optimal` / `gap` / `lb` /
   `crossing_number`). Proven reference truths: K5=1, K3,3=1 (Kuratowski),
   K6=3 (Guy 1960 formula), Petersen=2 — methodology and literature caliber
   in [docs/crossing-exact.md](docs/crossing-exact.md) (Chinese). Optimality
   holds only relative to the model class defined in that document's
   sections 1-5 (good-drawing caliber, the 2-edge-connected core family
   after safe reduction, the planar-subgraph x full-embedding family covered
   by the B&B), with no claim over an arbitrary drawing space. Requires the
   optional dependency `pip install "stdraw[solver]"`; when absent,
   `computed:false` is honestly marked.
4. **ortho-v1 frozen recipe (`--recipe ortho`)**: planar embedding +
   st-numbering + visibility representation, all wires strictly vertical,
   **0 crossings on planar graphs with theorem guarantee**; behavior frozen,
   protected by a CI byte-regression iron gate, safe for production callers
   to pin. Non-planar input raises `NotPlanarError` (the CLI prints an
   honest degradation and continues to the 3D layer — not a failure).
5. **Loop semantics audit (lint)**: verifies declared loop closure and R/B
   polarity parity against an independent enumeration of all graph loops;
   `loops_audit.json`'s `summary.problems` must = 0.
6. **Manual touch-up loop (drag -> export -> recompute)**: `demo-2d.html`
   (auto recipe) has a built-in drag layer — while dragging nodes, **all
   line styles re-route live** (a JS port of the visibility-graph shortest
   path, same mathematical caliber as Python; stale detours are invalidated
   the moment their obstacle is dragged away); detour fold points render as
   **draggable handles**, dragging pins the edge as user-anchored, and
   "Export layout" writes `edges[].waypoints` for anchored edges;
   `--from-layout` re-runs the same routing + certificate pipeline on manual
   coordinates (hard-gate caliber unchanged, graded honestly);
   `--compare-auto` additionally runs the automatic layout of the same graph
   and outputs the dual-certificate comparison `compare-auto.json`;
   `layout-diff` produces a three-layer diff (node displacement / structural
   metrics / loop semantics).
7. **3D dimension lift + viewer**: nodes arranged on regular solids
   (sphere/cube/tetrahedron/cone), spatial chords don't intersect, projection
   crossings are solved by the camera; `viewer/index.html` is a
   zero-dependency interactive viewer (four forms + dragging + loop panel).

## Install

```bash
pip install stdraw              # or in-repo pip install -e .; the only hard dependency is networkx; Python >= 3.9
pip install "stdraw[solver]"    # optional: ortools (auto-v2 CP-SAT placement refinement + --exact exact layer)
```

Without the solver, auto-v2 degrades gracefully to the constructive method
(full features, construct-tier quality), honestly marked in the certificate.

## CLI (the `--help` output is authoritative)

```bash
stdraw layout <input.cld|.json> [options]        # full layout pipeline (equivalent to python -m stdraw layout ...)
stdraw layout-diff <layout.json> <layout2.json> [--cld graph-source] [--diff-out diff.json]
```

| Option | Default | Description |
|---|---|---|
| `--outdir` | `stdraw-out` | output directory |
| `--recipe {auto,ortho}` | `auto` | auto = auto-v2 (straight/arc lines + hard gates + mode-based placement); ortho = ortho-v1 (constructive, frozen behavior, pin-safe) |
| `--linestyle {straight,arc}` | `straight` | auto recipe line style (arc = all-arc preference) |
| `--skip-3d` | off | run the 2D layer only |
| `--solids` | `sphere,cube,tetra,cone` | 3D solid list (comma separated) |
| `--pitch` | 56 | row pitch px; raising it for small graphs (e.g. 62) makes the clearance gates easier |
| `--name` | the DSL graph name | graph name in the certificate |
| `--exact` | off | exact crossing-number layer: B&B squeeze computes cr(G) into the certificate exactness block (needs `stdraw[solver]`) |
| `--from-layout` | — | manual layout JSON (a demo-2d.html "Export layout" product or a layout.json subset: node id->x,y + viewBox [+ edges[].waypoints]). Runs the same routing + certificate pipeline on manual coordinates, hard-gate caliber unchanged, graded honestly |
| `--compare-auto` | off | with `--from-layout`: also runs the automatic layout of the same graph into `<outdir>-compare-auto/`, outputting the dual-certificate comparison `compare-auto.json` |
| `--cld` | — | layout-diff: graph source (.cld/.json), enables the semantic layer (loop membership / cohesion) |
| `--diff-out` | — | layout-diff: machine-readable JSON output path |

Examples:

```bash
stdraw layout examples/limits-to-growth.cld --outdir out --pitch 62
python -m stdraw layout examples/limits-to-growth.cld --outdir out --skip-3d
stdraw layout model.cld --outdir out --exact
stdraw layout model.cld --outdir out-manual --skip-3d --from-layout graph-manual-layout.json
stdraw layout-diff out/layout.json out-manual/layout.json --cld model.cld --diff-out diff.json
```

## Input format (.cld DSL)

Line-oriented text, `#` starts a comment. Minimal closed loop = variables /
polarity edges / loop tags (groups optional; the layout layer does not
consume groups — placement is decided by relations alone):

```ld
graph "graph name"
var rate "adoption rate"                  # variable (declare before referencing)
rate -> + adopters @loops R1,B1           # polarity edge (+ same sign / - opposite) + participating loops
loop r1 "adoption diffusion" "R" [rate, adopters, word]   # declared loop: node sequence + expected kind R/B
```

Loop tags are not comments — the lint layer verifies closure and R/B parity
against an independently enumerated set of all graph loops.
Full syntax: [docs/dsl-spec-v0.1.md](docs/dsl-spec-v0.1.md). JSON graph
models are also accepted (`nodes`/`edges`/`loops`, structure identical to the
`graph.json` output).

## Outputs (all under `--outdir`)

| File | Content | How agents use it |
|---|---|---|
| `graph.json` / `graph.cld` | normalized graph model + DSL round-trip text | downstream programmatic consumption |
| `layout.json` | 2D delivered coordinates (all integers, 2px grid); edges carry `loop_kinds`/`loop_color` and route `kind` (line/arc/vg/poly/waypoints) plus `via` fold points; delivery-contract stamped (stdraw/delivery.py): library outputs self-declare `"delivery": "coordinates-only"` + warning, the CLI marks full deliverables `"delivery": "stdraw-cli"` / `"interactive": true`, and the ortho CLI layout.json stays byte-frozen (production pin — its contract travels on certificate.json) | rendering / recomputation |
| `geometry_report.json` | geometry self-checks (CI gate form), CLI exits 1 when `fail>0` | **CI gate** (assert fail==0) |
| `certificate.json` | metrics + gates + report items + honest grade + `placement` mode + delivery-face confession (`"interactive"` / `"drag_layer"`: yes only when the CLI shipped demo-2d.html with its drag layer — usable as a host CI gate) | **quality assertion** (below) |
| `loops_audit.json` | loop audit: declared / closed / enumerated / problems | assert `summary.problems == 0` |
| `demo-2d.html` | 2D deliverable page (embedded certificate + drag touch-up layer) | directly human-viewable / printable |
| `positions3d.json` / `demo-3d.html` | 3D per-solid coordinates + interactive page | demo-3d needs the in-repo `assets/` relative path |
| `compare-auto.json` (with `--compare-auto`) | manual vs automatic dual-certificate comparison | quantifies the aesthetic distance between engine and human |

## How to read the certificate (honest grading semantics)

`certificate.json`:

- **metrics**: crossings / box_press_1px / edge_box_min_clear / min_card_gap /
  spacing_cv / row_align_rate (**honestly null** when inapplicable to the
  mode, e.g. ring/column) + report metrics loop_cohesion_spread (loop
  cohesion), center_offset_x, line_kind_counts, ring_spacing_cv /
  ring_template_deviation (ring calibers);
- **visual_crossings (hard gate since v0.7.12, `visual_crossings_zero`)**:
  pairwise polyline intersection over ALL delivered edge pairs, INCLUDING
  pairs sharing an endpoint (fan pairs) — the blind spot the graph-theory
  `crossings` caliber exempts: fan lines from the same box can visibly cross
  mid-air while `crossings` reports 0 (ref-scrubbed; strict intersection
  excludes mere endpoint touch, so anchor meetings never count).
  Companion fields: `fan_visual_crossings` (the fan-pair subset) and
  `visual_crossing_details` (edge pair + intersection coordinates, capped
  at 10). Introduced as a reported metric in ref-scrubbed ("hard-gating
  awaits a legacy-number decision"); the 3 legacy fan-X figures
  (population-logistic / renewable-resource / shifting-the-burden) were
  fixed in ref-scrubbed (entry-side slot ordering + occupied-slot give-way +
  bowtie shared-side monotone slots) and the report item became a
  mode-independent hard gate folded into the grading `hard_ok` — a drawing
  with a fan X can no longer grade best. v1 ortho certificates stay
  byte-compatible and do not carry it;
- **mutual-pair lens arrows (channel caliber, not a certificate gate)**:
  bidirectional edge pairs are routed as a lens (two Q arcs bowing outward
  from the same anchor pair) and the arrowhead is drawn along the ARRIVAL
  tangent -- so the arrival deviation from the border normal is what carries
  the visible quality (a lens whose arrows stab the border at 20-30 deg reads
  as "twisted", even when every hard gate passes: the anchor-angle gate
  measures the angle to the border TANGENT, not the normal). The engine
  re-derives both arcs' control points to the fullest lens that meets
  `stdraw.routing.ARRIVAL_TARGET_DEG` (10 deg) and falls back to the previous
  geometry when the chord tilt makes the target unreachable (measured:
  soil-erosion 21 deg, induced-demand 20 deg). It is a routing-channel
  target, NOT a certificate gate -- hard-gating awaits an owner decision
  (ref-scrubbed);
- **gates (hard gates, switched by `placement` mode)**: as measured on
  `demos/classic-certificate.json` (spine-wing mode), 12 gates
  **12/12 passed** — box_press_zero / edge_box_clear_ge_16 / anchors_smooth /
  min_gap_ge_16 / cv_le_035 / spine_axis_le_2px / midline_adherence_le_2px /
  symmetry_mirror_le_2px / mutual_pairs_separated / lines_no_coincidence /
  visual_crossings_zero / routing_consistent (the gate key set switches with
  the placement mode; `visual_crossings_zero` is present in every mode since
  v0.7.12; the measured JSON is authoritative);
- **reports (report items, not hard gates)**: `crossings_zero` (soft target:
  <= 2 crossings allowed when placement regularity holds) and
  `row_align_ge_060`; `visual_crossings_zero` moved from reports to the
  hard-gate set in v0.7.12 (grading: a fan-X drawing grades `second` at
  most, not `best`; the `second` tier was removed in v0.7.15+ — logically
  unreachable dead branch);
- **grade**:

| grade | semantics |
|---|---|
| `best` | all placement hard gates pass + 0 line crossings (auto recipe: an optimization result, not a theorem guarantee; ortho recipe: theorem-guaranteed) |
| `3d` | 3D dimension-lift delivery (when the 2D layer is inapplicable or abandoned) |
| `uncertified` | everything else — **honestly ungraded**. This is not an error; it is the honest boundary |

Iron rule: stdraw **never claims 0 crossings for arbitrary graphs**. CLDs
are often non-planar; 0 crossings has a mathematical boundary. When relaying
to users, agents **must convey the grade verbatim** — receiving
"uncertified" must never be reported as "done".

Typical assertions (agent / CI alike):

```python
cert = json.load(open("out/certificate.json", encoding="utf-8"))
assert cert["grade"] == "best"
geo = json.load(open("out/geometry_report.json", encoding="utf-8"))
assert geo["summary"]["fail"] == 0
audit = json.load(open("out/loops_audit.json", encoding="utf-8"))
assert audit["summary"]["problems"] == 0
```

## Determinism

Same input, same output (byte-identical, incl. 3D assignments and HTML).
Layout has no RNG; CP-SAT single worker + fixed seed; CP-SAT placement for
n>10 uses a **deterministic time budget** (`max_deterministic_time=8`, an
operation-count caliber rather than wall clock — the same version on the
same input yields the same incumbent on any machine; `layout.json` meta's
`solver_status`/`solver_det_budget` are honestly marked). Output files can
safely enter the version library with clean diffs.

## Benchmark summary (benchmarks/, protocol in REPORT.md section 2)

Corpus = 19 classic CLDs + 80 fixed-seed random sparse graphs x {stdraw
ortho / stdraw auto / auto+exact layer} x {Graphviz 16.1.0 dot/neato/sfdp,
ELK layered}, six metrics from one same-source implementation, all raw
evaluation JSON archived in `benchmarks/raw/`. **Measurement base point**:
stdraw auto/auto-exact re-measured on the post-WS5-performance-fix engine
(b4ea801+); Graphviz/ELK baselines and stdraw-ortho carried over from WS4
same-machine measurements.

Classic means (REPORT.md section 7):

| Tool | Crossings | Box press | Clearance violations | CV | Row align | Time s | Success |
|---|---|---|---|---|---|---|---|
| stdraw·ortho (constructive) | 0.0 | 1.4 | 1.7 | 0.296 | 0.48 | 0.01 | 19/19 |
| stdraw·auto (WS3 routing) | 0.2 | **0.0** | **0.0** | 0.133 | 0.34 | 10.02 | 19/19 |
| stdraw·auto+WS2 (exact layer) | 0.2 | **0.0** | **0.0** | 0.133 | 0.34 | 10.42 | 19/19 |
| Graphviz dot | 0.2 | 0.1 | 2.6 | 0.139 | 0.34 | 0.03 | 19/19 |
| Graphviz neato | **0.1** | 1.2 | 3.1 | 0.080 | 0.05 | 0.06 | 19/19 |
| Graphviz sfdp | 0.3 | **0.0** | **0.0** | 0.131 | 0.37 | 0.03 | 19/19 |
| ELK layered | **0.1** | **0.0** | 3.0 | 0.208 | 0.41 | 0.07 | 19/19 |

Honest conclusions (wins stated as wins, losses as losses):

- **Where it wins**: on the classic corpus, the only tools achieving the
  double zero of "box press = 0 AND clearance violations = 0" are
  stdraw-auto (-exact) and sfdp, and within that group stdraw has fewer
  crossings (0.16 vs 0.26); CLD card drawing with same-input same-box
  dimensions + hard-gate semantics met simultaneously across all dimensions
  is stdraw's comparative advantage domain;
- **Where it loses**: "lowest crossings overall" **does not hold** (neato/ELK
  average 0.05 lower, at the cost of breaking placement hard gates); runtime
  is **2-3 orders of magnitude** slower than baselines (10.0s vs
  0.03-0.07s);
- **Random sparse family**: n=20/30 produce 20/20 figures, n=50 19/20, but
  box press / clearance are non-zero (routing is penalty minimization, not a
  theorem guarantee); a "best at all scales" claim does not hold;
- **OGDF**: not run on the same problem (no build toolchain, honestly
  assessed), not part of the win/loss verdict.

## Limitations (honest boundaries — do not overstate when relaying to users)

- Crossings are a soft target (since v0.6.0): placement regularity first;
  with all hard gates passed, <= 2 crossings are acceptable (the "best"
  grade still requires 0 crossings); the ortho recipe raises
  `NotPlanarError` on non-planar input; 2D planarization degradation is on
  the roadmap;
- ortho-v1 allows "unrelated wires occluded under cards" (cards opaque, the
  v0.1 design caliber), honestly counted in the certificate; auto-v2's
  box-over-line is a hard gate = 0. **Delivery ban (ruling D0, 2026-11-11):
  vertical-orthogonal (ortho-v1) output is NOT a deliverable** —
  box-over-line / leader-bar occlusion is structural in visibility
  representation and repeatedly unfixable; the frozen baseline stays only
  for CI byte-regression; enforced by `scripts/check_no_ortho_delivery.py`
  (CI gate) plus the certificate's `deliverable: false` / `blocked_by: D0`
  confession; see `docs/grading-contract.md` section 4;
- The 3D layer makes no 2D crossing promise;
- Random sparse graphs n>=20: positioned as the best incumbent within the
  8det budget (not proven optimal); routing box press / clearance follow
  REPORT section 4 measurements (non-zero); `_polish` feedback runs only for
  n<=10;
- The local-search neighborhood is limited to in-row shifts and adjacent
  swaps; the last crossing of some graphs may need a larger neighborhood
  (roadmap M3).

## MCP server (placeholder)

The MCP server form is on the roadmap (planned, not implemented). Current
agent integration goes through CLI + JSON files: any agent that can run
commands and read JSON can use stdraw fully. When implemented, this section
will be updated with the integration method.

## Version

Current **0.8.0** (`stdraw.__version__`, consistent with `pyproject.toml`).
The DSL is a v0.1 draft; backward-compatible upgrades will bump in sync with
the spec documents.

- **v0.8.0 version closure** (UI-A theme baseline; declared major-version
  visual baseline, spec = docs/ui-theme-spec-a.md): 2D light ("tracing
  paper") and dark ("midnight ink") token tables redefined in
  `stdraw/themes.py` (new `card_radius` / `canvas_grid` tokens plus
  `LIGHT_3D` / `DARK_3D` parameter groups); card corner radius 14;
  dotted canvas grid (render-layer only, edge hit layer un-occluded);
  certificate panel restyled as an engineering title block, square
  corners kept; 3D light stage added (structure unchanged), 3D dark
  frozen byte-for-byte; demos + docs/gallery re-rendered on the new
  light tier; CHANGELOG.md introduced with the 0.8.0 entry as the
  first declared changelog record.
- **v0.7.16 version closure** (≤10-node optimization line T1–T6 + validation
  tier re-plan):
  (a) **manual loop closure** (T1/T2): `--from-layout` reads back
  `edges[].anchors` so user-designated endpoints land on the 16-anchor
  standard set (±0.1px, straight/arc/waypoint route classes alike);
  waypoint & free-edge endpoints default to the standard anchor nearest the
  first/last bend direction (JS preview and CLI recompute parity ±0.5px);
  documented boundary: a contested anchor can settle differently in the
  preview vs recompute frames;
  (b) **observational stage timing** (T3): `STDRAW_TIMING=1` emits per-stage
  wall-clock to stderr, zero output drift off/on (classic 21 + random n4
  25/25 sha-identical);
  (c) **gate unification** (T4): repair-pass delivery gates collected into
  `stdraw/gates.py` (pure refactor, 41/41 layouts byte-identical);
  (d) **snap degradation revert at every density** (T5): the dense branch's
  worsening-revert probe now also guards the sub-1.6 threshold — a snap that
  worsens the hard-gate picture is no longer delivered silently;
  (e) **code hygiene** (T6): snap-debug prints folded into env-gated `_dbg()`,
  `EDGES_REF` module global made explicit, route caches cleared at
  `layout()` start (same-process batch order independence), unreachable
  `second` grade branch removed (old certificates with `grade=second` still
  read back as valid);
  (f) **validation tiers re-planned** (`docs/validation-tiers.md`): full
  byte-identical gate scoped to n ≤ 20 (61 figures); n21–30 reserved as the
  ZCODE upgrade tier (acceptance brief `docs/zcode-upgrade-brief.md`);
  n > 30 figures are out of the verification envelope — for larger diagrams
  we recommend driving Graphviz directly (`benchmarks/tools/run_graphviz.py`
  is the same-source evaluation harness);
  full-series verification: 86/101 corpus pairs sha256-identical, 0 drift;
  151 tests green.

- **v0.7.15 version closure** (dense snap gate path; complements the lens
  joint re-assign landed in v0.7.13's window): **routing gate-path
  hardening for anchor snapping on denser graphs** —
  (a) anchor_snap candidates gain the **coincidence gate**
  (`_coincide_no_worse` / `_coincide_max_span`, certificate-same-source
  accounting): a candidate may never CREATE a line-line coincident pair
  (span < COINCIDE_SPAN stays < 8px) and existing violations repair
  monotonically;
  (b) **joint-detour tier** (`_snap_joint_detour`): an endpoint rejected on
  all 16 anchors by tier-1 re-plans the whole edge as a visibility-graph
  route from a standard-anchor PAIR (nearest-first ladders × two inflation
  tiers) — both endpoints land on the 16-anchor set by construction;
  mutual pairs and user waypoint edges are excluded;
  (c) **edge-direction endpoint order law**: re-planned routes emit
  points[0] on box a and points[-1] on box b — a reversed route ships both
  ends off-border (random-n10-i00 measured);
  (d) random-corpus A/B vs the previous main: n10 family 6 improved / 9
  unchanged / 0 regressed / 5 pre-existing crashes (separate card);
  probe-kept snap 2→8 graphs (worst-case visual crossings 4→1,
  anchor/coincidence violations →0); classic 21 graphs byte-identical;
  density threshold 1.6 kept, de-deferral deferred pending more data;
  (e) lens placement exploration archived
  (`benchmarks/tools/lens_placement_experiment.py`): mirrored-pairing
  quantization floor 13.8 deg confirmed, 12 placement nudges all
  gate-rejected, shared anchor = 0 px separation — the data behind the
  non-mirrored lens joint re-assign (already on main: classic-cld four ends
  max 8.93 deg). Demos re-rendered; pytest 119 passed (+1 pre-existing
  theme drift-gate failure reproduced on clean main — theme card's domain);
  ci_checks EXIT=0.
- **v0.7.14 version closure** (theme layer): design tokens in
  `stdraw/themes.py` (single source; light tier frozen to the shipped
  values, dark tier = the viewer slate look); `viewer/themes.js` generated
  artifact byte-pinned by tests; CLI `--theme light|dark` (default light =
  production face unchanged, 21-input sweep byte-identical); viewer topbar
  theme toggle (localStorage `stdraw-theme`, default dark) with
  real-browser probe gates; R/B semantic pairs per tier (dark #fbbf24 /
  #7dd3fc, light #d97706 / #0284c7, WCAG ≥3.0 measured). pytest 120/120 +
  ci_checks EXIT=0.
- **v0.7.13 version closure** (implementation cards ref-scrubbed / ref-scrubbed /
  ref-scrubbed / ref-scrubbed): **16 standard anchors by default + polarity-only
  two-color rendering + certificate schema additions** —
  (a) per-box **16-anchor set** (`stdraw/anchors.py`: 4 edge midpoints + 4
  corners + 8 golden-section points, all on the inset-3px border rect) with
  interactive-layer hover display (toolbar toggle, default off), edge-endpoint
  drag with nearest-anchor snapping, explicit anchor pinning that
  re-projects endpoints on node drag, and export/layout round-trip
  (`edges[].anchors` / `edge_anchors`);
  (b) **anchor snapping in the default pipeline** (`Router.anchor_snap`:
  gated nearest-anchor assignment with per-box-per-anchor occupancy,
  immovable-point scan ≤4 rounds, yield-and-retry conflict channel; mutual
  pairs snap as mirror golden pairs, `mutual_arrival_flip(enhanced_gates)`
  restores vertical entry); certificate adds the **`anchors_standard` hard
  gate**; **density-gated deferral** (E/N ≥ 1.6 → snap deferred with
  `anchors_standard_deferred` recorded — honest downgrade, no gate
  watering);
  (c) render declutter: anchor dots default-off and endpoint handles
  hidden until hover/drag — no decorative circles in delivered
  PNG/HTML/3D;
  (d) loop visualization: **edge colors encode edge polarity only**
  (+ amber #d97706 / − sky #0284c7, all solid; gray shared-edge tint,
  dashed=negative, loop-id pills and multi-row legends removed; 3D
  polarity tubes + ConeGeometry arrowheads readable when scaled); minimal
  two-block legend;
  (e) certificate adds **`mode_decision_trace`** (which structural rule
  fired and why); README EN/zh lead with scale/latency expectations
  (≤10 nodes / classic ~10s vs graphviz 0.03s); `docs/layout-modes.en.md`
  English edition.
  Baselines regenerated with per-figure expected-change lists; classic
  21/21 sweep green (crossings 0 / grade best / anchors_standard true);
  pytest 114/114 + ci_checks EXIT=0; AGENTS version section written by
  default with jacky's explicit approval (protected-file op,
  2026-11-09).
- **v0.7.12 version closure** (implementation card ref-scrubbed): **fan
  crossings eliminated + visual_crossings hard-gated** — entry-side (target
  end) fan slots order by the approach-point projection when the other-box
  azimuths tie (population-logistic births box X), single-slidable fans
  give way to frozen/arc anchors occupying the same border side with
  give-way-only semantics, no-conflict single-entry fans stay byte-untouched
  (renewable-resource harvest T-junction), and bowtie shared-side mutual
  slots are azimuth-monotone across both rings (shifting-the-burden problem
  box X; spread >= PAIR_T sides reproduce the per-ring assignment
  byte-for-byte). `visual_crossings_zero` joined the hard-gate set in every
  placement mode and the grading `hard_ok`; cert panel row + AGENTS schema
  synced; 23-input sweep: exactly the 3 figures changed (grade best->best,
  visual_crossings 1->0), the other 20 byte-identical; pytest 102/102 +
  ci_checks green; certificate digest byte-identical pre/post bump.
- **v0.7.11** (ref-scrubbed / 14bd041; entry backfilled — no version-section
  entry was written at bump time): visible-edge redraw fix, per-edge
  fail-visible isolation, deterministic comb constraints.
- **v0.7.9** (ref-scrubbed / 5a3db81; entry backfilled): font-environment
  robustness — post-render DOM geometry re-anchor.

- **v0.7.10 version closure** (fix landed in ref-scrubbed / 25acc80, closure
  card ref-scrubbed): **interactive-layer edge hit CSS fix** — `.stdraw-hit`
  hit-paths carried `stroke: transparent` under `pointer-events: stroke`,
  which is unhittable on Chromium builds that gate hit-testing on painted
  pixels; the stroke is now painted near-transparent
  (`rgba(255,255,255,0.01)`, the diagram-js approach). `pointer-events: all`
  is deliberately NOT used: with `fill: none` SVG implicitly closes the
  polygon, so the edge would swallow clicks in the empty region between its
  endpoints. The real-hit gate is regression-guarded: `probe_interactive.py`
  gains a hit gate (elementFromPoint sampling at multiple points along each
  edge + CDP real-mouse double-click style cycling / waypoint insertion /
  drag / export replay, 33/33 green) and `tests/test_hit_gate.py` adds 4
  deterministic unit tests. Honest defect-tree note: on current Chromium
  builds (Edge 157 verified) hit testing does NOT follow painted pixels —
  the transparent-stroke failure does not reproduce there; the painted
  stroke is kept as a defense for older builds. Certificate summary
  cross-checked: the version string never enters output bytes
  (demos/classic-certificate.json byte-identical pre/post bump).
- **v0.7.8 version closure** (implementation card ref-scrubbed, closure
  card ref-scrubbed): **comb-bilateral wide-card tier-1 facing-border fan** —
  double-ticker wide cards (the 8777 caliber: xval 330px / wafer 292px) made
  the tier-0 global fan widening angle-infeasible: measured across the
  widening bracket, widening anti-correlates with the horizontal-border
  departure angle (19.9 -> 8.1 deg, every bracket failure angle-bound), so
  the comb honestly fell back to layered/uncertified; tier 1 instead anchors
  hub edges on the facing vertical borders (center-line border crossing
  anchors with in-band clamp), spreads hub-side slots in source-row order at
  >= 8px spacing (a non-crossing condition backed by an analytic seg_cross
  pairwise self-check — the first draft's alphabetical tie-break inverted the
  slot order into a same-hub visual crossing the certificate's
  shared-endpoint exemption could not see), delivers via the
  constructed-route injection channel, and the trial gate re-runs the
  unified hard gates on the result; certificate meta.comb.fan=facing-border
  marker, gate set unchanged; regression fixture tests/data/hdd-wide-tickers.cld
  joined the CI AUTO_EXAMPLES (grade best, 11/11 gates) + 7 unit tests;
  20-graph corpus sweep byte-identical vs f86f1d3 (tier-0 path untouched);

- **v0.7.7 version closure** (implementation card ref-scrubbed, closure
  card ref-scrubbed): **comb-bilateral placement mode** — K_{m,2}-type
  supply-chain graphs (two non-adjacent hubs whose neighborhoods are
  identical = a shared source set with m>=3, all remaining core nodes
  pendant trees on the sources) get the bilateral comb layout per jacky's
  hand-pulled HDD baseline: sources in one vertical column (axis deviation
  0), the two hubs in mirrored slots (symmetry error 0), all hub edges a
  straight fan; comb outranks column only when the source column is longer
  than the best spine, and the ring-ratio branch refuses entry when best
  k<=4 and comb detection hits (classic-cld ratio+k=4 legitimately kept) —
  structured fix for the ring false-trigger on the HDD supply-chain figure;
  line-style auto rules tightened (auto default = straight, baseline 11/11
  line, arcs only when structurally justified); per-edge line-style control
  (double-click cycles auto -> straight -> arc -> free; free = user
  waypoints capped at 3 per edge, tooltip "max 3 points per edge") with
  export `edges[].style`/`waypoints` and deterministic `--from-layout`
  replay (arc = deterministic adaptive-k max-clearance side, JS/Python one
  caliber; forced edges frozen out of re-layout; certificates grade manual
  layouts honestly); interactive persistence API —
  `window.__stdrawApplyLayout` (nodes + edge_styles + waypoints, cap-clamped)
  and the `stdraw:layoutchanged` event (drag-release + applyLayout paths)
  plus the `--value-pad` CLI option; 19-graph corpus sweep byte-identical
  vs f337273 (demos changed only in toolbar hints + script = the
  interactive-layer upgrade);
- **v0.7.6 version closure** (implementation card ref-scrubbed, closure
  card ref-scrubbed): repo-wide bilingual governance — README / AGENTS.md
  fully English as canonical, dsl-spec English canonical + new zh-CN
  companion, engineering caliber docs kept Chinese with navigation
  notes; new language-policy CI gate (tests/check_language_policy.py)
  wired into ci_checks; grade tokens englishized (best / second / 3d /
  uncertified — zero semantic change, frozen baselines byte-identical,
  no re-baselining); gallery converged to 3 real success shots
  (before/after pair removed, all three re-rendered by headless
  Chrome);
- **v0.7.5 version closure** (landing card ref-scrubbed): pyproject / __init__ /
  README bilingual badges unified 0.7.4->0.7.5; certificate summary byte
  cross-check (the version string never enters output bytes); landed in the
  same batch — AGENTS.md caliber sync (gates example switched to spine-wing
  11 gates, anchor mid-band index row, version history filled for
  v0.7.2-v0.7.5, taking over ref-scrubbed's approved diff); publishing-face
  card-id sanitization (ref-scrubbed, dbe2890);
- **v0.7.4 version closure** (landing card ref-scrubbed): publishing-face
  alignment (README captions / auto-v2 description switched to mode-based
  caliber, SKILL.md mode list gained bowtie-vertex / spine-wing,
  demos/classic-certificate.json re-rendered to spine-wing 11 gates);
  batch-switch verification = 19-graph sweep (HEAD 69d49af) with only
  classic-cld hitting spine-wing, bullwhip / tragedy-of-the-commons being
  column-chain isomorphic families that don't trigger (W<=2),
  limits-to-growth rest=0 not triggering;
- **v0.7.3 anchor mid-band CI hard gate / v0.7.2 deliverable re-render +
  demo freshness gate** (ref-scrubbed series reworks);
- **v0.7.1 spine-wing** (landing card ref-scrubbed): detection conditions,
  placement template and regularity-gate caliber original =
  [docs/layout-modes.md](docs/layout-modes.md) (Chinese; English edition: [docs/layout-modes.en.md](docs/layout-modes.en.md)) section spine-wing;
  no copy in this document;
- **v0.7.0 bowtie-vertex** (landing card ref-scrubbed, aesthetics v3): caliber
  original = same document, section bowtie-vertex symmetric.
