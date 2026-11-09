# benchmarks/manual — jacky's hand-drawn samples, kept on file

This directory stores **manual layouts exported by jacky via hand-dragging**
(the ground truth) used as the acceptance baseline for the "structurally
equivalent" side of layout shape. Coordinates are not required to match
pixel-for-pixel, but the engine's automatic layout must reproduce the same
role grouping (endpoint columns / mid-row band / wing column / loner
placement) and relative geometric regularities as the samples.

## classic-cld-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the nodes
  on the stdraw demo-2d interactive page (Kanban card ref-scrubbed attachment,
  2026-11-06).
- **Graph**: `classic-cld-growth-and-burden` (Limits to Growth × Shifting the
  Burden, 8 nodes).
- **viewBox**: 856×760.
- **Structural regularities** (the regression test
  `tests/test_layout_modes.py::TestSpineWingManualEquivalence` derives the
  role grouping automatically from this file):
  - Endpoint columns: adopters(413,214) / rate(412,535) — same x column
    within 1px;
  - Mid-row band: word(308,368) / potential(112,368) / crowding(547,369) —
    same row within ±1px;
  - Right-wing column: quickfix(741,289) / sideeffect(747,453) — same x
    column within 6px;
  - Loner mid-lower: fundamental(594,533) (in the same row band as rate).
- **Copy discipline**: this file is the in-repo ground truth; the regression
  tests tied to engine behavior read only this file and derive expectations
  from it — no coordinate copies are written inside the tests.

## Historical incident (recurrence guard)

v0.7.1 (ref-scrubbed): the engine-side spine-wing layout had landed and was
structurally correct, but `demos/classic-cld-2d.html` and
`docs/gallery/*.png` had not been re-rendered with the engine, so jacky's
visual inspection saw the old ring-construct rendering and misjudged it as
"structurally inconsistent" (rework card ref-scrubbed, v0.7.2). Recurrence
guard: `tests/ci_checks.py` deliverable freshness check — demo-2d.html is
byte-compared against a fresh render by the current engine.
