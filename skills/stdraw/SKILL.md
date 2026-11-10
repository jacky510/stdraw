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
# Layout + certificate + loops audit + 2D/3D demo HTML (auto-v2 recipe, straight/arc lines)
stdraw layout model.cld --outdir out --pitch 62
# 2D only (faster)
stdraw layout model.cld --outdir out --skip-3d
# Classic orthogonal recipe (all-vertical wires, provably 0 crossings on planar graphs;
# behavior frozen — pinned by production callers, byte-regression protected)
stdraw layout model.cld --outdir out --recipe ortho
# Arc-prefixed lines (auto recipe)
stdraw layout model.cld --outdir out --linestyle arc
# Exact crossing-number layer (proven-optimal cr(G), needs stdraw[solver])
stdraw layout model.cld --outdir out --exact
# Optional positioning refinement (better uniformity on dense graphs)
pip install "stdraw[solver]"
```

## Quick Reference

- Input: `.cld` DSL — `var id "label"` / `a -> + b @loops R1` /
  `loop R1 "label" "R" [a, b, c]`. JSON graph model also accepted.
- Outputs in `--outdir`: `certificate.json` (grade + metrics),
  `geometry_report.json` (checks; CLI exits 1 on fail),
  `loops_audit.json` (semantic lint), `demo-2d.html`, `demo-3d.html`,
  `layout.json`, `positions3d.json`.
- Default recipe `auto-v2` enforces hard gates: box-over-line = 0 (any angle,
  1px margin), edge-to-box clearance >= 16px, smooth border anchors, and
  mode-aware arrangement regularity (bowtie-vertex / spine-wing / vertical-column /
  ring / mirror-symmetric / layered auto-selected by structure with trial gates; crossings and row
  alignment are reported soft targets since v0.6.0).

## Certificate Reading Rules (honest grading — pass through verbatim)

| `grade` | Meaning | What you may tell the user |
|---|---|---|
| `best` | hard gates all pass + 0 crossings | "hard gates pass, zero crossings" (auto-v2: crossings are minimized, not theorem-guaranteed; ortho recipe: theorem-guaranteed) |
| `3d` | 3D delivery (rotate freely; projection crossings solved by camera) | no 2D crossing claim |
| `uncertified` | everything else — honestly ungraded | **never** dress this up as success |

Iron rule: stdraw never claims arbitrary graphs are 0-crossing. Relay grades as-is.

## Integrating Into an Existing Web App

**Do**

- Deliver `demo-2d.html` — it *is* the deliverable (drag touch-up layer +
  embedded certificate). Embed it, e.g. `<iframe src="demo-2d.html">`.
- Persist manual touch-ups: "Export layout" in `demo-2d.html` writes a
  layout JSON; re-run `stdraw layout model.cld --from-layout <that.json>`
  to re-route and re-grade on the same coordinates.
- Gate embedded deliverables on the certificate's delivery face:
  `certificate.json` must carry `"interactive": "yes"` and
  `"drag_layer": "yes"`.

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
- `demo-3d.html` needs the repo's `assets/three.min.js` at the relative path.
- `loops_audit.json` `problems` must be 0 before trusting declared loops.
- Loop polarity is shown by edge color (single-loop R amber `#d97706` /
B sky `#0284c7`, mixed/acyclic neutral, negative edges dashed) - no letter
badges. Manual touch-up loop: drag nodes in `demo-2d.html`, export layout,
re-run with `--from-layout` (waypoints included) - see AGENTS.md.
- All outputs are deterministic — safe to commit; re-runs diff clean.
