<div align="center">

# stdraw

**Planarity-aware system-thinking (CLD) diagram engine. Honest grades, hard quality gates, metric-backed certificates.**

*Text DSL in → diagram with a quality certificate out. Honest grades, never fake "zero crossings" claims.*

English | [简体中文](README_zh-CN.md)

</div>

[![CI](https://github.com/jacky510/stdraw/actions/workflows/ci.yml/badge.svg)](https://github.com/jacky510/stdraw/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.7.5-blue.svg)](pyproject.toml)
[![Stars](https://img.shields.io/github/stars/jacky510/stdraw.svg?style=flat)](https://github.com/jacky510/stdraw/stargazers)

[Install](#install) · [Gallery](#gallery) · [Quickstart](#quickstart) · [DSL](#dsl-in-one-minute) · [Certificates](#certificates--quality-gates) · [Agent Integration](#agent-integration)

```bash
pip install stdraw
```

---

## What & Why

Mainstream diagram tools stop at "crossing minimization" heuristics, and **none of them make a verifiable promise about their own output**. stdraw is built the other way around:

- **auto-v2 (default recipe)**: **structure-aware mode layout** — a deterministic priority chain (bowtie-vertex → spine-wing → column-chain → ring-cycle → layered) picks one arrangement template per graph structure, each with a trial gate (non-triggering graphs stay byte-identical); plus straight/arc-first routing (optional CP-SAT refinement), enforced by **hard quality gates**: box-over-line = 0 (any angle), edge-to-box clearance ≥ 16px, smooth border anchors, and mode-specific regularity gates — see [docs/layout-modes.md](docs/layout-modes.md);
- **Ring layout for loop-dominated small graphs (v0.5.0)**: when a small graph (≤ 12 nodes) has a dominant simple cycle covering ≥ n−2 nodes (or ≥ 90% of its edges lie on cycles), the main loop is placed on **regular-polygon ring slots** in cycle order (declared loop order preferred, so R/B polarity colors read along the ring), chords route inside the ring, and residual nodes get deterministic inner/outer slots; the certificate switches to **ring-appropriate metrics** (ring-spacing CV + polygon template-fit error) instead of row alignment — layout mode is stated honestly, never judged by row-gate yardsticks; non-triggering graphs keep the layered path byte-identical;
- **Anchor-band hard gate (v0.7.3)**: delivered edge anchors clamped to the mid-band (edge midpoint ± 1/4 edge length, corner hits = 0) are now enforced per-figure in CI — spine-wing figures require 100% in-band; mutual-pair edges whose band-clamped anchors cannot pass the hard gates get a deterministic band-anchored local re-route (anchor-band candidates + nested-arc escape hatch + own-box interior check); other engines are locked to their v0.7.2 baseline ratios (ring mutual corridors / bowtie ±12px spoke corridors are registered legacy) — see [docs/layout-modes.md](docs/layout-modes.md);
- **Layout aesthetics v3.1 (v0.7.1)**: **spine-wing mode** — graphs with a dominant hub pair (an edge whose endpoints share ≥3 common neighbors = a midline "wing band") plus a constructible secondary cluster get the vertical-spine + midline-wing layout (jacky's hand-drawn classic-cld reference): spine strictly vertical on the axis, wings pressed to the horizontal midline, outer mirror pair symmetric about it; deterministic trigger (hub-pair common-neighbor count + rest-cluster pairing + spine length ratio ≤0.5), equivalent certificate gates (spine-axis ≤2px, midline ≤2px, mirror ≤2px); corpus sweep: only classic-cld-growth-and-burden switches, all other 18 byte-identical — see [docs/layout-modes.md](docs/layout-modes.md);
- **Layout aesthetics v3 (v0.7.0)**: **bowtie-vertex mode** — graphs whose topology is exactly two simple cycles sharing one node (e.g. wage-price-spiral, per jacky's hand-drawn reference) get an explicit double-mirror layout (shared node dead-center, one loop per half-plane, symmetric rows, all-straight lines with mutual-pair parallel corridors); **connection-point caliber** — line anchors clamp to each edge's mid-point ±1/4 band (corners excluded entirely, hit count always 0), multiple lines on the same side fan out symmetrically around the mid-point; **adaptive arc curvature** — bulge = min(6 + 0.06·chord, 40) px (short edges bend less, long edges capped), arcs within one symmetric structure share a single unified k for visual evenness — see [docs/layout-modes.md](docs/layout-modes.md);
- **Layout aesthetics v2 (v0.6.0)**: regularity first — long-chain / few-loop graphs (main cycle ≤ 4) get a **vertical column layout** (spine aligned on one axis, branches on neighbor side columns, the spine's closing edge drawn as a big side arc for the loop-closure feel); bowtie graphs (two triangles sharing an edge, e.g. learning-flywheel) get an **explicit mirror-symmetric layout** with a strict line-type rule (axis edge straight + mirrored side arcs); loop edges are **colored by polarity** (R = amber `#d97706`, B = sky `#0284c7`, mixed/acyclic = neutral, negative edges dashed) replacing the old R/B letter badges; isomorphic skeletons map to the same layout template (WL structural colors drive slot assignment, not declared-loop ids); crossings and row alignment are demoted from hard gates to **reported soft targets** (order & beauty first) while arrangement regularity stays hard-gated — see [docs/layout-modes.md](docs/layout-modes.md);
- **WS3 routing math**: detours are **provably shortest** — obstacles inflated by the clearance, then an exact Dijkstra shortest path over the corner visibility graph (graph-optimal); polyline corners are smoothed with tangent circular arcs (G1-continuous, bounded curvature, per-arc clearance re-verified); crossings are re-checked in **dual calibers** — the router's theoretical count on final geometry must equal the geometric recount on delivered coordinates, or no certificate is issued; loop polarity is expressed by **edge color** (amber = reinforcing R, sky = balancing B, dashed = negative edge) with no letter badges cluttering complex graphs; polyline detours carry a fixed type cost (arc > straight > polyline — folded corners are a last resort);
- **ortho-v1 (classic recipe, optional)**: planar embedding + st-numbering + visibility representation — all wires strictly vertical with a **theorem-level 0-crossing guarantee** on planar graphs (behavior frozen, byte-regression protected, safe for production callers to pin);
- **Honest grading**: if it can't earn a certificate it says so — **never claims 0 crossings for arbitrary graphs** (in auto-v2, crossings are minimized, not guaranteed);
- **Two-layer ground-truth box measurement**: the layout side plans box bounds from worst-case real-font metrics; the verification side measures actual DOM bounds in a real browser after rendering — certificates verify rendered reality, not estimates;
- **Quality certificates**: every deliverable ships with quantified metrics (crossings / box-over-line / clearance / alignment / CV / anchors), verified on the delivered coordinates;
- **Determinism**: same input → same output, byte-identical (CP-SAT pinned to a single worker + fixed seed); diagrams are safe to commit with clean diffs.

## Gallery

All images are real renderings produced by the current engine (v0.7.5) from the in-repo corpus — no mock-ups, no stale artifacts (click through to each demo).

| | |
|---|---|
| <a href="../demos/classic-cld-2d.html"><img src="docs/gallery/classic-cld-2d.png" alt="classic CLD 2D auto-v2 layout" width="420"/></a> | <a href="../demos/classic-cld-3d.html"><img src="docs/gallery/classic-cld-3d.png" alt="classic CLD 3D sphere layout" width="420"/></a> |
| **2D · auto-v2 spine-wing layout** (classic-cld-growth-and-burden, 8n/13e, vertical spine + midline wing band + mirrored right wing, 0 crossings) | **3D · sphere arrangement** (rotate freely; projection crossings solved by the camera) |
| <a href="../demos/classic-cld-2d.html"><img src="docs/gallery/certificate.png" alt="quality certificate panel" width="420"/></a> | <a href="../demos/classic-cld-2d.html"><img src="docs/gallery/before-after.png" alt="before/after comparison" width="420"/></a> |
| **Quality certificate panel** (hard gates + gate tally + honest grade, exactly as shipped in the demo; spine-wing caliber: spine-axis / midline-adherence / mirror deviation) | **Before/after** (same input, both rendered by the current engine: frozen ortho-v1 recipe with wires occluded under cards → auto-v2 spine-wing layout, gates 11/11, 0 crossings, R/B polarity colors with mutual-pair straight-line allocation) |

## Ask your agent in plain words

stdraw is agent-native: one `.cld` text file in, a certified diagram out. Tell your agent:

| You say | The agent runs |
|---|---|
| "Draw this causal-loop diagram with a quality certificate" | `stdraw layout model.cld --outdir out` |
| "Audit the declared feedback loops: unclosed loops? wrong polarity?" | reads `out/loops_audit.json` → `problems` (loops re-enumerated independently) |
| "Can this diagram be zero-crossing? Tell me straight, no bragging" | reads `out/certificate.json` → `grade` (honest grading, below) |
| "Give me a printable version" | opens `out/demo-2d.html` (inline SVG, zero network) |

## Project Structure

```text
stdraw/
├── stdraw/              # Python package
│   ├── recipes.py       #   recipe registry: auto-v2 (default) / ortho-v1 (frozen, pin-safe)
│   ├── layout_auto.py   #   auto-v2 layout (layering + crossings-in-objective + optional CP-SAT + local refinement)
│   ├── routing.py       #   straight/arc/detour routing (box-over-line=0, clearance>=16px hard gates)
│   ├── textmetrics.py   #   ground-truth box bounds (layout side: worst-case real-font metrics)
│   ├── rendercheck.py   #   ground-truth box bounds (CI side: headless-browser DOM measurement, optional layer)
│   ├── visibility.py    # WS3: 布线数学（膨胀障碍可见性图最短路 + 弧平滑）
│   ├── crossing_exact.py  # WS2: 精确交叉数层（OIL 插入 ILP + 平面化 oracle + B&B 夹逼，可选 ortools）
│   ├── regularity.py    # WS2: 结构检测 + 规律性可计算定义（正多边形偏差/直线度/对称轴）
│   ├── placement.py     # WS2: 槽位离散化放置（结构驱动槽型；general 分支 CP-SAT）
│   ├── ringlayout.py    # v0.5.0: 回路主导环形排布（触发判定 + 主环正多边形槽位 + 残节点指派）
│   ├── columnlayout.py  # v0.6.0: 纵列排布（长链/少环：主链一列 + 支路侧挂 + 闭合侧弧）
│   ├── symlayout.py     # v0.6.0: 领结对对称排布（双三角共边：纵轴镜像 + 线型一致）
│   ├── planar.py        #   ortho-v1: 2D planar layout (theorem-level 0 crossings, frozen behavior)
│   ├── layout3d.py      #   3D five-solid arrangements (sphere/cube/tetrahedron/cone)
│   ├── metrics.py       #   quality certificates v1/v2 + honest grading
│   ├── check.py         #   geometry self-checks (CI-gate form: v1 11 checks / v2 hard-gate checks)
│   ├── loops.py         #   loop-semantics audit (lint)
│   ├── dsl.py           #   .cld DSL parser
│   ├── model.py         #   graph data model
│   ├── render.py        #   2D HTML rendering (inline SVG, v1/v2 forms)
│   ├── render3d.py      #   3D HTML rendering (three.js)
│   └── __main__.py      #   CLI: stdraw layout ... [--recipe auto|ortho] [--linestyle straight|arc]
├── examples/            # .cld cases (limits-to-growth / limits-to-growth × shifting-the-burden)
├── demos/               # deliverable form: 2D/3D demos + certificate JSON
├── viewer/              # zero-dependency interactive viewer (four forms + live certificate)
├── skills/stdraw/       # Agent Skill (installable via skills add)
├── tests/baselines/     # ortho-v1 byte-regression baselines (frozen-behavior iron gate)
├── docs/                # DSL spec + gallery + OR-Tools comparison + crossing-exact math (WS2)
└── .github/workflows/   # CI: recipe regression + hard gates + DOM measurement + determinism
```

## Quickstart

```bash
# 1. Install (pure pip; the only hard dependency is networkx)
pip install stdraw

# 2. Run a case: text DSL in
stdraw layout examples/limits-to-growth.cld --outdir out --pitch 62

# 3. Look at the deliverables
#    out/demo-2d.html     — 2D layout + embedded quality certificate
#    out/demo-3d.html     — 3D sphere/cube/tetrahedron/cone (needs the in-repo assets/)
#    out/certificate.json — metrics + honest grade
#    out/loops_audit.json — loop-semantics audit
```

A ready-made deliverable ships in the repo: open [`demos/classic-cld-2d.html`](demos/classic-cld-2d.html) / [`demos/classic-cld-3d.html`](demos/classic-cld-3d.html).
Interactive viewer (four forms + node dragging + loop panel): open `viewer/index.html` in a browser, nothing to install.

### Manual touch-up loop (drag → export → re-certify)

Every `demo-2d.html` (auto recipe) ships with a built-in touch-up layer — drag
nodes (mouse or touch), live metrics recompute in the toolbar, then:

```bash
# 1. Open out/demo-2d.html, drag cards, click 「导出布局」 (Export layout)
#    -> downloads graph-manual-layout.json (layout.json-compatible subset)

# 2. Re-run routing + certificate on YOUR coordinates — same hard gates,
#    honest scoring (a manual layout is never graded leniently):
stdraw layout input.cld --outdir out-manual --skip-3d --from-layout graph-manual-layout.json

# 3. (optional) Side-by-side auto-vs-manual certificate comparison
#    (the gap is the engine-vs-human aesthetic distance):
stdraw layout input.cld --outdir out-manual --skip-3d \
    --from-layout graph-manual-layout.json --compare-auto

# 4. Three-layer diff (node-level moves / structural metrics / loop semantics)
#    — the data source for distilling aesthetic rules from human edits:
stdraw layout-diff out/layout.json out-manual/layout.json --cld input.cld --diff-out diff.json
```

### Waypoint handles (detour fold points are draggable, not fixed)

Since v0.5.3 the touch-up layer re-routes **all line styles live** while you drag
(straight / arc / visibility-graph fold lines alike — fold vertices are
recomputed every frame against current obstacles; nothing is pinned). Edges that
detour around obstacles render each fold point as a small **drag handle**
(hover shows a move cursor):

- drag a handle → that edge becomes *user-pinned*; node drags afterwards only
  re-anchor its endpoints, your waypoints stay;
- 「导出布局」 writes `edges: [{a, b, waypoints: [[x,y],...]}]` for pinned
  edges; `--from-layout` replays the exact same polyline (anchors recomputed on
  the box borders toward the first/last waypoint) and the certificate re-checks
  the delivered geometry honestly — including your waypoints;
- 「重置」 clears all pins and restores the engine layout.

```bash
# after dragging handles + export:
stdraw layout input.cld --outdir out-manual --skip-3d --from-layout graph-manual-layout.json
# layout.json now carries route kind "waypoints" with via = your fold points
```

## DSL in One Minute

Line-oriented text, `#` starts a comment:

```ld
graph "limits-to-growth × shifting-the-burden"
var rate "adoption rate"
rate -> + adopters @loops R1,B1,B2      # polarity edge + loop tags
loop R1 "word of mouth" "R" [rate, adopters, word]
```

A minimal closed loop = variables / polarity edges / loop tags / groups (optional; the layout
layer does not consume groups — layout is determined by relations alone). Loop tags are not
comments — the lint layer verifies closure and R/B polarity parity against an independent
enumeration of all loops. Full spec: [docs/dsl-spec-v0.1.md](docs/dsl-spec-v0.1.md)
(a Chinese translation is planned; no date promised).

## Certificates · Quality Gates

Every deliverable directory contains `certificate.json`:

```json
{
  "metrics": { "crossings": 0, "box_press_1px": 0, "edge_box_min_clear": 18.0,
               "min_card_gap": 36.0, "row_align_rate": null,
               "spacing_cv": 0.0, "column_axis_deviation": 0.0,
               "loop_cohesion_spread": { "R1": 0.43, "B1": 0.43 },
               "line_kind_counts": { "line": 5, "arc": 1 } },
  "gates":   { "box_press_zero": true, "edge_box_clear_ge_16": true,
               "anchors_smooth": true, "min_gap_ge_16": true,
               "cv_le_035": true, "column_axis_aligned": true,
               "spine_pitch_uniform": true,
               "mutual_pairs_separated": true, "routing_consistent": true,
               "lines_no_coincidence": true },
  "reports": { "crossings_zero": true,
               "crossings_note": "soft target: <=2 crossings allowed when arrangement regularity passes (order & beauty first)",
               "row_align_ge_060": true },
  "placement": "column-chain",
  "grade": "最优"
}
```

(Ring-layout certificate: row alignment / column snap are honestly `null` — the
regularity gates switch to ring spacing CV + polygon template fit, per placement;
v0.6.0 adds column/symmetric calibers and demotes crossings_zero and row alignment
to **reported soft targets** — see docs/layout-modes.md
mode. Layered layouts keep the row-alignment caliber.)

Honest grading semantics (iron rule: **never pass off a non-certificate as one**):

| Grade | Definition (auto-v2) |
|---|---|
| **最优** (best) | all hard gates pass (box-over-line 0 / clearance ≥ 16 / smooth anchors / regular arrangement) + 0 crossings |
| **其次** (second) | all hard gates pass + ≤ 2 crossings (coords in the certificate for review; when gates and crossings conflict, gates win) |
| **最次** (3D) | dimension-lift to 3D: rotate freely, no spatial crossings, projection crossings solved by the camera |
| **未获证书** (uncertified) | everything else — honestly ungraded |

`geometry_report.json` (geometry self-checks in CI-gate form; the CLI exits 1 on fail) can be used directly as a regression gate.

**Exactness layer (WS2, `--exact`)**: the CLI can compute the provable crossing
number cr(G) (ordering-style insertion ILP + planarization oracle + exhaustive
B&B over planar subgraphs × embeddings). The certificate then carries
`proven_optimal` / `gap` / `lb` / `crossing_number` in an `exactness` block —
with a rigorous scope note: optimality is claimed only relative to the model
class defined in [docs/crossing-exact.md](docs/crossing-exact.md) §0–5, never
over all conceivable metric sets. Requires the optional solver extra
(`pip install "stdraw[solver]"`); without it the fields honestly stay
`computed: false`. Layouts also carry a computable **regularity** block
(structure-driven: cycle → regular-polygon deviation, chain → straightness,
symmetry-axis alignment; definitions in docs/crossing-exact.md §7).

### Recipes

| Recipe | Line style | Guarantee | Use when |
|---|---|---|---|
| `auto-v2` (default) | straight/arc first-class (`--linestyle straight\|arc`) | hard quality gates + crossing minimization (optional CP-SAT via `pip install "stdraw[solver]"`); placement modes by structure: ring (loop-dominated) / vertical column (long-chain, few loops) / mirror-symmetric (bowtie), each with mode-caliber regularity gates; loop edges colored R=amber / B=sky, negative dashed | general CLDs / teaching / reports |
| `ortho-v1` (`--recipe ortho`) | all-vertical orthogonal | theorem-level 0 crossings on planar graphs (**frozen behavior**, byte-regression in CI) | production callers pinning behavior / orthogonal style preference |

## Agent Integration

| Agent host | Integration |
|---|---|
| Any agent that can read files | read [AGENTS.md](AGENTS.md) (repo root, agent manual, English) |
| Agent Skills ecosystem | `npx skills add jacky510/stdraw` → installs [skills/stdraw/SKILL.md](skills/stdraw/SKILL.md) (English) |
| Scripts / CI gates | `pip install stdraw` → `stdraw layout ...` → assert on `certificate.json` / `geometry_report.json` |
| MCP server | planned (see the placeholder in AGENTS.md) |

## Limitations (honest boundaries)

- **Never claims 0 crossings for arbitrary graphs**: in auto-v2, crossings are a minimized objective term, not a theorem guarantee; ortho-v1 raises `NotPlanarError` on non-planar input and degrades honestly instead of forcing a drawing.
- ortho-v1 (frozen recipe) allows "unrelated wires occluded under cards" as legacy design (cards are opaque) and counts it honestly in the certificate — a known v0.1 boundary; **the v0.2 default recipe auto-v2 makes box-over-line a hard gate (= 0)**.
- The 3D layer makes no 2D crossing promises — spatial chords don't intersect thanks to the extra dimension; projection crossings are solved by the camera.
- The layout layer is a replaceable implementation (currently: layering + crossing minimization + straight/arc routing; CP-SAT is an optional refinement layer — without it the engine degrades to the constructive method: full features, construct-tier quality).
- The local-search neighborhood covers in-row shifts and adjacent swaps, not cross-row moves — the last crossing of some graphs may need a larger neighborhood (roadmap M3).

## License

[MIT](LICENSE) © stdraw contributors
