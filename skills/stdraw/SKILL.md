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
# Layout + certificate + loops audit + 2D/3D demo HTML
stdraw layout model.cld --outdir out --pitch 62
# 2D only (faster)
stdraw layout model.cld --outdir out --skip-3d
```

## Quick Reference

- Input: `.cld` DSL — `var id "label"` / `a -> + b @loops R1` /
  `loop R1 "label" "R" [a, b, c]`. JSON graph model also accepted.
- Outputs in `--outdir`: `certificate.json` (grade + metrics),
  `geometry_report.json` (11 checks; CLI exits 1 on fail),
  `loops_audit.json` (semantic lint), `demo-2d.html`, `demo-3d.html`,
  `layout.json`, `positions3d.json`.

## Certificate Reading Rules (honest grading — pass through verbatim)

| `grade` | Meaning | What you may tell the user |
|---|---|---|
| `最优` | arrangement OK + provably 0 crossings | "zero crossings, guaranteed" |
| `其次` | arrangement OK + ≤2 crossings (coords in cert) | report crossing count + coords |
| `最次` | 3D delivery (rotate freely; projection crossings solved by camera) | no 2D crossing claim |
| `未获证书` | everything else — honestly ungraded | **never** dress this up as success |

Iron rule: stdraw never claims arbitrary graphs are 0-crossing; non-planar
input raises `NotPlanarError` and degrades honestly to 3D. Relay grades as-is.

## Pitfalls

- Small graphs: pass `--pitch 62` to clear the min-gap gate.
- `demo-3d.html` needs the repo's `assets/three.min.js` at the relative path.
- `loops_audit.json` `problems` must be 0 before trusting declared loops.
- All outputs are deterministic — safe to commit; re-runs diff clean.
