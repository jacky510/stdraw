---
name: stdraw
description: Draw causal-loop (CLD) diagrams from .cld DSL with honest quality certificates via the stdraw CLI.
license: MIT
---

# stdraw — system-thinking diagram engine

Text DSL in → diagram with a quality certificate out. Use this skill whenever a
task involves drawing, auditing, or certifying causal-loop / system-thinking
diagrams (CLD). Full reference: the repo's `AGENTS.md`; DSL grammar:
`docs/dsl-spec-v0.1.md`.

## When to Use

- User asks to draw a causal-loop diagram / system map / feedback structure and
  wants a verifiable result (quality certificate), not just a picture.
- User asks to audit declared feedback loops (unclosed loops, wrong R/B polarity).
- User asks "can this diagram be zero-crossing?" — stdraw answers with an honest
  grade instead of a guess.
- Don't use for: generic graph prettification with no CLD semantics; hand-drawn
  mockups where honesty grading is not wanted.

## Prerequisites

```bash
pip install stdraw        # or inside the repo: pip install -e .
```

## How to Run

```bash
# Layout + certificate + loops audit + demo HTML (auto-v2 recipe, straight/arc lines; 2D only)
stdraw layout model.cld --outdir out --pitch 62
# Arc-prefixed lines (auto recipe)
stdraw layout model.cld --outdir out --linestyle arc
# Suppress the annotation layer in the demo (loop-center labels AND @delay
# marks, one switch); the certificate then records the two annotation gates
# as N/A (grade semantics unchanged)
stdraw layout model.cld --outdir out --no-loop-labels
# Exact crossing-number layer (proven-optimal cr(G), needs stdraw[solver])
stdraw layout model.cld --outdir out --exact
# Optional positioning refinement (better uniformity on dense graphs)
pip install "stdraw[solver]"
```

## Quick Reference

- Input: `.cld` DSL — `var id "label"` / `a -> + b @loops R1` /
  `loop R1 "label" "R" [a, b, c]` / `a -> + b @delay` (delay mark). JSON graph model also accepted.
- Outputs in `--outdir`: `certificate.json` (grade + metrics),
  `geometry_report.json` (checks; CLI exits 1 on fail),
  `loops_audit.json` (semantic lint), `demo-2d.html`,
  `layout.json`.
- Default recipe `auto-v2` enforces hard gates: box-over-line = 0 (any angle,
  1px margin), edge-to-box clearance >= 16px, smooth border anchors, and
  mode-aware arrangement regularity (bowtie-vertex / spine-wing / vertical-column /
  ring / mirror-symmetric / lens-chain / layered auto-selected by structure with trial gates; crossings and row
  alignment are reported soft targets since v0.6.0).
- Loop-reading aids (default on): every declared loop carries a loop-center
  label (id + name + direction glyph; `Loops: on/off` toggle on the demo page);
  loop-member edges (loops of >= 3 nodes) default to an arc bending along
  their loop - straight / polyline fallbacks are recorded with measured
  reasons in `certificate.json` -> `loop_arcs.fallbacks`; `@delay` edges carry
  a double-tick delay mark. All hard-gated (`loop_labels_clear`,
  `delay_marks_clear`). The whole annotation layer (labels + delay marks,
  one switch) can be suppressed at render time with the CLI flag
  `--no-loop-labels`; the certificate then records the two annotation gates
  as `N/A` (excluded from the pass count, never blocking; grade semantics
  unchanged). Note: the certificate field `line_style` (and the CLI
  `--linestyle` argument) is the REQUEST, not the delivered drawing - the
  delivered line-kind facts are `metrics.line_kind_counts` (also printed as
  "line kinds ..." in the demo headline and the CLI summary).

## Certificate Reading Rules (honest grading — pass through verbatim)

| `grade` | Meaning | What you may tell the user |
|---|---|---|
| `best` | hard gates all pass + 0 crossings | "hard gates pass, zero crossings" (auto-v2: crossings are minimized, not theorem-guaranteed) |
| `uncertified` | everything else — honestly ungraded | **never** dress this up as success |

Iron rule: stdraw never claims arbitrary graphs are 0-crossing. Relay grades as-is.

Caliber rule: read `certificate.json.caliber` before interpreting `grade` —
auto-v2 (`v2-hardgates`) emits only `best` / `uncertified`; `second` existed only in the
v1-legacy caliber, which was retired outright together with the ortho recipe's external
entry (owner ruling, 2026-11-24; D0 still bans vertical-orthogonal pages as
deliverables). Single source:
[docs/grading-contract.md](docs/grading-contract.md).

## Integrating Into an Existing Web App

**Do**

- Deliver `demo-2d.html` — it *is* the deliverable (embedded certificate;
  add `--interactive` to ship the drag touch-up layer). Embed it, e.g.
  `<iframe src="demo-2d.html">`.
- Persist manual touch-ups: render with `--interactive`, "Export layout"
  in `demo-2d.html` writes a
  layout JSON; re-run `stdraw layout model.cld --from-layout <that.json>`
  to re-route and re-grade on the same coordinates.
- Gate embedded deliverables on the certificate's delivery face: when the
  page must carry the touch-up layer (rendered with `--interactive`),
  `certificate.json` must carry `"interactive": "yes"` and
  `"drag_layer": "yes"` (the default static page stamps `"no"`).

**Don't**

- Don't bake a static SVG from `layout.json` coordinates: you lose live
  drag re-routing, waypoint handles, the export->recompute loop and the
  certificate. `layout.json` self-declares `"delivery":
  "coordinates-only"`, `"interactive": false` plus a warning — treat
  that as a stop sign, not noise to strip.
- Don't pass `suppress_delivery_warning=True` merely to silence the
  warning; use it only when you truly consume raw coordinates.

## Pitfalls

- Small graphs: pass `--pitch 62` to clear the min-gap gate.
- `loops_audit.json` `problems` must be 0 before trusting declared loops.
- Loop polarity is shown by edge color (light theme: single-loop R vermilion `#c2410c` /
B drafting blue `#1e6fae`; dark theme `#ffb454` / `#6ec6ff` - single source
`stdraw/themes.py`; mixed/acyclic neutral, negative edges dashed) - no
letter badges; the loop-center labels carry the loop id + name only. Manual
touch-up loop: render with `--interactive`, drag nodes in `demo-2d.html`,
export layout,
re-run with `--from-layout` (waypoints included) - see AGENTS.md.
- All outputs are deterministic — safe to commit; re-runs diff clean.
